import logging
import secrets

from django.contrib import messages

logger = logging.getLogger(__name__)
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.decorators import auth_rate_limit
from apps.accounts.models import User, PasswordResetCode
from apps.accounts.forms import (
    LoginForm, SignupForm,
    PasswordResetRequestForm, PasswordResetVerifyForm, PasswordResetSetForm,
)
from apps.accounts.utils.email import send_verification_email, send_password_reset_code


def _safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next") or reverse("accounts:dashboard")
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse("accounts:dashboard")


def _auth_error_response(request, form, message, status=403):
    if getattr(request, "htmx", None):
        return render(request, "accounts/partials/auth_message.html", {
            "type": "error",
            "message": message,
        }, status=status)
    form.add_error(None, message)
    return render(request, "accounts/login_page.html", {
        "form": form,
        "error_message": message,
        "next": _safe_next_url(request),
    }, status=status)


def landing_page(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    return render(request, "landing.html")


@auth_rate_limit("login", limit=10, window_seconds=300)
def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    is_htmx = bool(getattr(request, "htmx", None))
    error_message = None
    next_url = _safe_next_url(request)

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]

            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                error_message = "البريد الإلكتروني غير مسجل لدينا"
                form.add_error("email", error_message)

            else:
                if user.check_password(password):
                    if user.is_approved == User.ApprovalStatus.PENDING:
                        return _auth_error_response(
                            request,
                            form,
                            "حسابك قيد المراجعة. سنرسل لك رسالة بريد إلكتروني بعد مراجعة الإدارة.",
                        )
                    if user.is_approved == User.ApprovalStatus.REJECTED:
                        reason = user.rejection_reason or "لم يتم تحديد سبب"
                        return _auth_error_response(
                            request,
                            form,
                            f"عذراً، لم يتم اعتماد حسابك. السبب: {reason}",
                        )
                    if not user.is_active:
                        return _auth_error_response(request, form, "حسابك معطّل. تواصل مع الإدارة.")

                    login(request, user)
                    if is_htmx:
                        return HttpResponse(headers={"HX-Redirect": next_url})
                    return redirect(next_url)
                else:
                    error_message = "كلمة المرور غير صحيحة"
                    form.add_error("password", error_message)
        else:
            error_message = "يرجى تصحيح الأخطاء أدناه"

        if is_htmx:
            return render(request, "accounts/partials/login_form.html", {
                "form": form,
                "next": next_url,
            }, status=400)

    else:
        form = LoginForm()

    return render(request, "accounts/login_page.html", {
        "form": form,
        "error_message": error_message,
        "next": next_url,
    })


@auth_rate_limit("signup", limit=5, window_seconds=3600)
def signup_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()

            user.email_verification_token = secrets.token_urlsafe(48)
            user.save(update_fields=["email_verification_token", "updated_at"])

            verification_url = request.build_absolute_uri(
                reverse("accounts:verify_email", kwargs={"token": user.email_verification_token})
            )
            email_sent = send_verification_email(user, verification_url)
            if email_sent:
                success_message = "تم تسجيل حسابك بنجاح. يرجى التحقق من بريدك الإلكتروني لتأكيد الحساب. حسابك قيد المراجعة وسنرسل لك رسالة عند الاعتماد."
            else:
                # Be honest when SMTP failed so the user knows to use
                # "إعادة إرسال التأكيد" instead of watching an empty inbox.
                logger.error("Failed to send verification email to %s", user.email)
                success_message = "تم تسجيل حسابك بنجاح وهو قيد المراجعة، لكن تعذر إرسال رسالة تأكيد البريد حالياً. يمكنك طلب إعادة الإرسال من صفحة تسجيل الدخول."

            is_htmx = getattr(request, "htmx", None)
            if is_htmx:
                return render(request, "accounts/partials/auth_message.html", {
                    "type": "success",
                    "message": success_message,
                    "show_login_link": True,
                })
            messages.success(request, success_message)
            return redirect("accounts:login")
        else:
            is_htmx = getattr(request, "htmx", None)
            if is_htmx:
                return render(request, "accounts/partials/signup_form.html", {"form": form}, status=400)

    else:
        form = SignupForm()

    return render(request, "accounts/signup_page.html", {"form": form})


def verify_email_view(request, token):
    user = get_object_or_404(User, email_verification_token=token)
    if not user.is_email_verified:
        user.is_email_verified = True
        user.email_verification_token = None
        user.save(update_fields=["is_email_verified", "email_verification_token", "updated_at"])
        messages.success(request, "تم تأكيد بريدك الإلكتروني بنجاح.")
    else:
        messages.info(request, "بريدك الإلكتروني مؤكد مسبقاً.")
    return redirect("accounts:login")


@auth_rate_limit("resend-verification", limit=3, window_seconds=900)
def resend_verification_view(request):
    if request.method == "POST":
        email = request.POST.get("email", "")
        try:
            user = User.objects.get(email=email, is_email_verified=False)
            user.email_verification_token = secrets.token_urlsafe(48)
            user.save(update_fields=["email_verification_token", "updated_at"])
            verification_url = request.build_absolute_uri(
                reverse("accounts:verify_email", kwargs={"token": user.email_verification_token})
            )
            email_sent = send_verification_email(user, verification_url)
            if not email_sent:
                logger.error("Failed to resend verification email to %s", user.email)
            messages.success(request, "تم إرسال رابط التأكيد مجدداً. يرجى التحقق من بريدك الإلكتروني.")
        except User.DoesNotExist:
            messages.error(request, "لم نجد حساباً غير مؤكد بهذا البريد الإلكتروني.")
    return redirect("accounts:login")


@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:landing")


@login_required
def dashboard_redirect(request):
    if request.user.role == User.Role.MAIN_ADMIN:
        return redirect("accounts:admin_dashboard")
    if request.user.role == User.Role.SUB_ADMIN:
        return redirect("accounts:admin_dashboard")
    if request.user.role == User.Role.TEACHER:
        return redirect("accounts:teacher_dashboard")
    if request.user.role == User.Role.STUDENT:
        return redirect("accounts:student_dashboard")
    return redirect("accounts:landing")


@auth_rate_limit("password-reset", limit=5, window_seconds=900)
def password_reset_request_view(request):
    # GET must render the form: the login page's "نسيت كلمة المرور؟" link and the
    # verify page's "إعادة إرسال الرمز" link both navigate here (was 405 under
    # the old @require_POST, which made the whole reset flow unreachable).
    if request.method != "POST":
        return render(request, "registration/password_reset_form.html", {
            "form": PasswordResetRequestForm(),
        })

    form = PasswordResetRequestForm(request.POST)
    if form.is_valid():
        email = form.cleaned_data["email"]
        user = User.objects.filter(email=email).first()

        if user:
            PasswordResetCode.objects.filter(email=email, is_used=False).delete()
            code = PasswordResetCode.generate_code()
            PasswordResetCode.objects.create(email=email, code=code)
            if not send_password_reset_code(email, code):
                # Don't pretend a code is on its way when SMTP failed — the
                # user would sit on the verify page waiting forever.
                logger.error("Failed to send password reset code to %s", email)
                form.add_error(None, "تعذر إرسال رمز الاستعادة حالياً. يرجى المحاولة بعد قليل.")
                return render(request, "registration/password_reset_form.html", {"form": form})

        # Unknown emails fall through identically — no account enumeration.
        request.session["reset_email"] = email
        return redirect("accounts:password_reset_verify")
    return render(request, "registration/password_reset_form.html", {"form": form})


def password_reset_verify_view(request):
    email = request.session.get("reset_email")
    if not email:
        return redirect("accounts:password_reset")

    if request.method == "POST":
        form = PasswordResetVerifyForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["code"]
            try:
                reset_code = PasswordResetCode.objects.get(
                    email=email, code=code, is_used=False
                )
            except PasswordResetCode.DoesNotExist:
                form.add_error("code", "الرمز غير صحيح")
                return render(request, "registration/password_reset_code.html", {
                    "form": form, "email": email,
                })

            if reset_code.is_expired:
                reset_code.is_used = True
                reset_code.save(update_fields=["is_used"])
                request.session.pop("reset_email", None)
                form.add_error("code", "انتهت صلاحية الرمز. يرجى طلب رمز جديد.")
                return render(request, "registration/password_reset_code.html", {
                    "form": form, "email": email,
                })

            request.session["reset_code_id"] = str(reset_code.pk)
            return redirect("accounts:password_reset_set")
    else:
        form = PasswordResetVerifyForm()

    return render(request, "registration/password_reset_code.html", {
        "form": form, "email": email,
    })


def password_reset_set_view(request):
    email = request.session.get("reset_email")
    code_id = request.session.get("reset_code_id")
    if not email or not code_id:
        return redirect("accounts:password_reset")

    if request.method == "POST":
        form = PasswordResetSetForm(request.POST)
        if form.is_valid():
            try:
                reset_code = PasswordResetCode.objects.get(
                    pk=code_id, email=email, is_used=False
                )
            except PasswordResetCode.DoesNotExist:
                return redirect("accounts:password_reset")

            if reset_code.is_expired:
                return redirect("accounts:password_reset")

            user = User.objects.get(email=email)
            user.set_password(form.cleaned_data["new_password1"])
            user.save(update_fields=["password", "updated_at"])

            reset_code.is_used = True
            reset_code.save(update_fields=["is_used"])
            PasswordResetCode.objects.filter(email=email, is_used=False).delete()

            request.session.pop("reset_email", None)
            request.session.pop("reset_code_id", None)
            return redirect("accounts:password_reset_complete")
    else:
        form = PasswordResetSetForm()

    return render(request, "registration/password_reset_confirm.html", {
        "form": form, "validlink": True,
    })
