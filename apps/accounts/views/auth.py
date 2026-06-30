from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from apps.accounts.models import User
from apps.accounts.forms import LoginForm, SignupForm



def landing_page(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    return render(request, "landing.html")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    is_htmx = bool(getattr(request, "htmx", None))
    error_message = None

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]

            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                user = None

            if user and user.check_password(password):
                if user.is_approved == User.ApprovalStatus.PENDING:
                    return render(request, "accounts/partials/auth_message.html", {
                        "type": "error",
                        "message": "حسابك قيد المراجعة. يرجى الانتظار حتى يتم اعتمادك.",
                    }, status=403)
                if user.is_approved == User.ApprovalStatus.REJECTED:
                    reason = user.rejection_reason or "لم يتم تحديد سبب"
                    return render(request, "accounts/partials/auth_message.html", {
                        "type": "error",
                        "message": f"عذراً، لم يتم اعتماد حسابك. السبب: {reason}",
                    }, status=403)
                if not user.is_active:
                    return render(request, "accounts/partials/auth_message.html", {
                        "type": "error",
                        "message": "حسابك معطّل. تواصل مع الإدارة.",
                    }, status=403)

                login(request, user)
                next_url = request.POST.get("next", "/dashboard/")
                if is_htmx:
                    return HttpResponse(headers={"HX-Redirect": next_url})
                return redirect(next_url)
            else:
                error_message = "البريد الإلكتروني أو كلمة المرور غير صحيحة"
                form.add_error(None, error_message)
        else:
            error_message = "يرجى تصحيح الأخطاء أدناه"

        if is_htmx:
            return render(request, "accounts/partials/login_form.html", {"form": form}, status=400)

    else:
        form = LoginForm()

    return render(request, "accounts/login_page.html", {
        "form": form,
        "error_message": error_message,
    })


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            is_htmx = getattr(request, "htmx", None)
            if is_htmx:
                return render(request, "accounts/partials/auth_message.html", {
                    "type": "success",
                    "message": "تم تسجيل حسابك بنجاح! سيتم مراجعته من قبل الإدارة.",
                    "show_login_link": True,
                })
            return render(request, "accounts/login_page.html", {
                "form": LoginForm(),
                "signup_success": True,
            })
        else:
            is_htmx = getattr(request, "htmx", None)
            if is_htmx:
                return render(request, "accounts/partials/signup_form.html", {"form": form}, status=400)

    else:
        form = SignupForm()

    return render(request, "accounts/signup_page.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("accounts:landing")
@login_required
def dashboard_redirect(request):
    if request.user.role == User.Role.ADMIN:
        return redirect("accounts:admin_dashboard")
    if request.user.role == User.Role.SUPERVISOR:
        return redirect("accounts:admin_dashboard")
    if request.user.role == User.Role.TEACHER:
        return redirect("accounts:teacher_dashboard")
    if request.user.role == User.Role.STUDENT:
        return redirect("accounts:student_dashboard")
    return redirect("accounts:landing")