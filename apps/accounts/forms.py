from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password

from .models import User, Batch


INPUT_CLASS = "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
SELECT_CLASS = "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"


class LoginForm(forms.Form):
    email = forms.EmailField(
        label="البريد الإلكتروني",
        widget=forms.EmailInput(attrs={
            "class": INPUT_CLASS,
            "placeholder": "example@email.com",
            "autocomplete": "email",
        })
    )
    password = forms.CharField(
        label="كلمة المرور",
        widget=forms.PasswordInput(attrs={
            "class": INPUT_CLASS,
            "placeholder": "••••••••",
            "autocomplete": "current-password",
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True
            field.widget.attrs["required"] = "required"


class SignupForm(forms.ModelForm):
    gender = forms.ChoiceField(
        label="الجنس",
        choices=[("", "اختر الجنس"), ("male", "ذكر"), ("female", "أنثى")],
        widget=forms.Select(attrs={"class": SELECT_CLASS}),
    )
    password1 = forms.CharField(
        label="كلمة المرور",
        help_text="8 أحرف على الأقل.",
        widget=forms.PasswordInput(attrs={
            "class": INPUT_CLASS,
            "placeholder": "••••••••",
            "autocomplete": "new-password",
        })
    )
    password2 = forms.CharField(
        label="تأكيد كلمة المرور",
        help_text="أعد كتابة كلمة المرور للتأكد.",
        widget=forms.PasswordInput(attrs={
            "class": INPUT_CLASS,
            "placeholder": "••••••••",
            "autocomplete": "new-password",
        })
    )

    class Meta:
        model = User
        fields = ["full_name_ar", "email", "phone", "gender", "role", "specialization", "state", "level", "memorization_amount"]
        widgets = {
            "full_name_ar": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "مثال: أحمد بن محمد",
                "autocomplete": "name",
            }),
            "email": forms.EmailInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "example@email.com",
                "autocomplete": "email",
            }),
            "phone": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "05XXXXXXXX",
                "autocomplete": "tel",
            }),
            "role": forms.Select(attrs={
                "class": SELECT_CLASS,
            }),
            "specialization": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "مثال: علوم إسلامية",
            }),
            "state": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "مثال: الجزائر",
            }),
            "level": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "مثال: متوسط",
            }),
            "memorization_amount": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "مثال: 5 أجزاء",
            }),
        }
        help_texts = {
            "full_name_ar": "اكتب الاسم كما سيظهر في لوحة التحكم والشهادات.",
            "email": "سنستخدمه لتسجيل الدخول وإرسال نتيجة الاعتماد.",
            "phone": "رقم يمكن للإدارة التواصل معك عليه.",
            "gender": "اختر الجنس حتى تظهر البيانات بشكل صحيح في الإدارة.",
            "role": "اختر نوع الحساب المطلوب مراجعته.",
            "specialization": "اختياري للمعلمين أو أصحاب التخصص.",
            "state": "اختياري.",
            "level": "اختياري، مثال: مبتدئ أو متوسط.",
            "memorization_amount": "اختياري، مثال: جزءان أو 5 أجزاء.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [("", "اختر الدور")] + [
            c for c in User.Role.choices if c[0] not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
        ]
        for field_name in ("full_name_ar", "email", "phone", "gender", "role", "password1", "password2"):
            self.fields[field_name].required = True
        for field_name, field in self.fields.items():
            if field.required:
                field.widget.attrs["required"] = "required"
            field.widget.attrs.setdefault("aria-describedby", f"id_{field_name}_help")

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError("هذا البريد الإلكتروني مسجل مسبقاً")
        return email

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if len(phone) < 8:
            raise ValidationError("يرجى إدخال رقم هاتف صحيح")
        return phone

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError("كلمتا المرور غير متطابقتين")
        if password1 and len(password1) < 8:
            raise ValidationError("كلمة المرور يجب أن تكون 8 أحرف على الأقل")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.set_password(self.cleaned_data["password1"])
        user.is_approved = User.ApprovalStatus.PENDING
        user.is_active = True
        if commit:
            user.save()
        return user


class ApprovalForm(forms.Form):
    action = forms.ChoiceField(
        choices=[("approve", "قبول"), ("reject", "رفض")],
        widget=forms.HiddenInput()
    )
    rejection_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "w-full px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500",
            "rows": 3,
            "placeholder": "سبب الرفض (اختياري)",
        })
    )
    batch = forms.ModelChoiceField(
        queryset=Batch.objects.filter(status=Batch.Status.ACTIVE),
        required=False, label="الدفعة",
    )


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["full_name_ar", "email", "phone", "gender", "specialization", "state", "level", "memorization_amount"]
        widgets = {
            "full_name_ar": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors",
                "placeholder": "الاسم الكامل",
            }),
            "email": forms.EmailInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors",
                "placeholder": "example@email.com",
            }),
            "phone": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors",
                "placeholder": "05XXXXXXXX",
            }),
            "gender": forms.Select(attrs={
                "class": "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["gender"].required = False
        self.fields["gender"].choices = [("", "اختر الجنس"), ("male", "ذكر"), ("female", "أنثى")]

    def clean_email(self):
        email = self.cleaned_data.get("email")
        qs = User.objects.filter(email=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("هذا البريد الإلكتروني مسجل مسبقاً")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        label="البريد الإلكتروني",
        widget=forms.EmailInput(attrs={
            "class": INPUT_CLASS,
            "placeholder": "example@email.com",
            "autocomplete": "email",
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True


class PasswordResetVerifyForm(forms.Form):
    code = forms.CharField(
        label="رمز الاستعادة",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            "class": INPUT_CLASS,
            "placeholder": "000000",
            "autocomplete": "off",
            "inputmode": "numeric",
            "pattern": "[0-9]{6}",
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].required = True


class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = ["name", "number", "year", "description", "status", "start_date", "end_date", "sub_admins"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "اسم الدفعة"}),
            "number": forms.NumberInput(attrs={"class": INPUT_CLASS, "placeholder": "رقم الدفعة"}),
            "year": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "مثال: 1446-1447"}),
            "description": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 3, "placeholder": "وصف الدفعة"}),
            "start_date": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
            "status": forms.Select(attrs={"class": SELECT_CLASS}),
            "sub_admins": forms.SelectMultiple(attrs={"class": SELECT_CLASS, "size": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sub_admins"].queryset = User.objects.filter(
            role=User.Role.SUB_ADMIN, is_approved=User.ApprovalStatus.APPROVED,
        )
        self.fields["sub_admins"].required = False
        self.fields["sub_admins"].label = "المشرفون المسؤولون"

    def save(self, commit=True):
        batch = super().save(commit=False)
        supervisors = list(self.cleaned_data.get("sub_admins") or [])
        batch.sub_admin = supervisors[0] if supervisors else None
        if commit:
            batch.save()
            self.save_m2m()
        return batch


class PasswordResetSetForm(forms.Form):
    new_password1 = forms.CharField(
        label="كلمة المرور الجديدة",
        widget=forms.PasswordInput(attrs={
            "class": INPUT_CLASS,
            "placeholder": "••••••••",
            "autocomplete": "new-password",
        })
    )
    new_password2 = forms.CharField(
        label="تأكيد كلمة المرور",
        widget=forms.PasswordInput(attrs={
            "class": INPUT_CLASS,
            "placeholder": "••••••••",
            "autocomplete": "new-password",
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True

    def clean_new_password1(self):
        password = self.cleaned_data.get("new_password1", "")
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError("كلمتا المرور غير متطابقتين")
        return cleaned
