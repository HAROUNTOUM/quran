from django import forms
from django.core.exceptions import ValidationError
from .models import User


class LoginForm(forms.Form):
    email = forms.EmailField(
        label="البريد الإلكتروني",
        widget=forms.EmailInput(attrs={
            "class": "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors",
            "placeholder": "example@email.com",
        })
    )
    password = forms.CharField(
        label="كلمة المرور",
        widget=forms.PasswordInput(attrs={
            "class": "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors",
            "placeholder": "••••••••",
        })
    )


class SignupForm(forms.ModelForm):
    password1 = forms.CharField(
        label="كلمة المرور",
        widget=forms.PasswordInput(attrs={
            "class": "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors",
            "placeholder": "••••••••",
        })
    )
    password2 = forms.CharField(
        label="تأكيد كلمة المرور",
        widget=forms.PasswordInput(attrs={
            "class": "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors",
            "placeholder": "••••••••",
        })
    )

    class Meta:
        model = User
        fields = ["full_name_ar", "email", "phone", "gender", "role", "specialization", "state", "level", "memorization_amount"]
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
            "role": forms.Select(attrs={
                "class": "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors",
            }),
            "gender": forms.Select(attrs={
                "class": "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors",
            }),
            "specialization": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors",
                "placeholder": "مثال: علوم إسلامية",
            }),
            "state": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors",
                "placeholder": "مثال: الجزائر",
            }),
            "level": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors",
                "placeholder": "مثال: متوسط",
            }),
            "memorization_amount": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors",
                "placeholder": "مثال: 5 أجزاء",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["gender"].choices = [("", "اختر الجنس"), ("male", "ذكر"), ("female", "أنثى")]
        self.fields["role"].choices = [("", "اختر الدور")] + [
            c for c in User.Role.choices if c[0] not in ("admin", "supervisor")
        ]

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise ValidationError("هذا البريد الإلكتروني مسجل مسبقاً")
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError("كلمتا المرور غير متطابقتين")
        if len(password1) < 8:
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
