from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from task.jalali import parse_flexible_date
from .models import EmployeeProfile


class StyledAuthenticationForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'نام کاربری'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'input', 'placeholder': 'رمز عبور'}))


class EmployeeCreateForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, required=True, label='نام')
    last_name = forms.CharField(max_length=150, required=True, label='نام خانوادگی')
    email = forms.EmailField(required=False, label='ایمیل')
    hire_date = forms.CharField(
        required=False,
        label='تاریخ استخدام',
        widget=forms.TextInput(
            attrs={
                'placeholder': 'مثال: 1405/02/08',
                'dir': 'ltr',
                'inputmode': 'numeric',
                'autocomplete': 'off',
            }
        ),
    )
    daily_target_hours = forms.IntegerField(required=False, min_value=1, label='هدف ساعت روزانه')
    monthly_target_hours = forms.IntegerField(required=False, min_value=1, label='هدف ساعت ماهانه')
    annual_leave_days = forms.IntegerField(required=False, min_value=0, label='مرخصی سالانه (روز)')

    class Meta:
        model = User
        fields = (
            'username',
            'first_name',
            'last_name',
            'email',
            'password1',
            'password2',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing_classes = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{existing_classes} input'.strip()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = self.cleaned_data['email']

        if commit:
            user.save()
            profile = user.employee_profile
            if self.cleaned_data.get('hire_date'):
                profile.hire_date = self.cleaned_data['hire_date']
            if self.cleaned_data.get('daily_target_hours'):
                profile.daily_target_hours = self.cleaned_data['daily_target_hours']
            if self.cleaned_data.get('monthly_target_hours'):
                profile.monthly_target_hours = self.cleaned_data['monthly_target_hours']
            if self.cleaned_data.get('annual_leave_days') is not None:
                profile.annual_leave_days = self.cleaned_data['annual_leave_days']
            profile.save()

        return user

    @staticmethod
    def _to_latin_digits(value):
        """Convert Persian/Arabic-Indic digits to ASCII digits."""
        persian = '۰۱۲۳۴۵۶۷۸۹'
        arabic  = '٠١٢٣٤٥٦٧٨٩'
        for i in range(10):
            value = value.replace(persian[i], str(i)).replace(arabic[i], str(i))
        return value

    def clean_daily_target_hours(self):
        raw = str(self.cleaned_data.get('daily_target_hours') or '').strip()
        raw = self._to_latin_digits(raw)
        if not raw:
            return None
        try:
            val = int(raw)
        except (ValueError, TypeError):
            raise forms.ValidationError('عدد صحیح وارد کنید.')
        if val < 1:
            raise forms.ValidationError('مقدار باید حداقل ۱ باشد.')
        return val

    def clean_monthly_target_hours(self):
        raw = str(self.cleaned_data.get('monthly_target_hours') or '').strip()
        raw = self._to_latin_digits(raw)
        if not raw:
            return None
        try:
            val = int(raw)
        except (ValueError, TypeError):
            raise forms.ValidationError('عدد صحیح وارد کنید.')
        if val < 1:
            raise forms.ValidationError('مقدار باید حداقل ۱ باشد.')
        return val

    def clean_hire_date(self):
        raw = (self.cleaned_data.get('hire_date') or '').strip()
        if not raw:
            return None
        try:
            return parse_flexible_date(raw)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc


class EditProfileForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False, label='نام',
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'نام'}))
    last_name = forms.CharField(max_length=150, required=False, label='نام خانوادگی',
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'نام خانوادگی'}))
    email = forms.EmailField(required=False, label='ایمیل',
        widget=forms.EmailInput(attrs={'class': 'input', 'placeholder': 'example@email.com', 'dir': 'ltr'}))
    bio = forms.CharField(required=False, label='درباره من',
        widget=forms.Textarea(attrs={'class': 'input', 'rows': 3, 'placeholder': 'چند جمله درباره خودت...'}))
    birth_date = forms.CharField(required=False, label='تاریخ تولد',
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': '۱۳۷۰/۰۱/۱۵', 'dir': 'ltr', 'inputmode': 'numeric'}))
    national_id = forms.CharField(required=False, label='کد ملی',
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'مثال: ۰۰۱۲۳۴۵۶۷۸', 'dir': 'ltr', 'inputmode': 'numeric', 'maxlength': '10'}))
    avatar = forms.ImageField(required=False, label='تصویر پروفایل',
        widget=forms.ClearableFileInput(attrs={'class': 'input', 'accept': 'image/*'}))
    remove_avatar = forms.BooleanField(required=False, label='حذف تصویر فعلی')

    def clean_birth_date(self):
        raw = self.cleaned_data.get('birth_date', '').strip()
        if not raw:
            return None
        try:
            return parse_flexible_date(raw)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc


class EmployeeEditForm(forms.Form):
    username = forms.CharField(max_length=150, label='نام کاربری',
        widget=forms.TextInput(attrs={'class': 'input', 'dir': 'ltr', 'autocomplete': 'off'}))
    first_name = forms.CharField(max_length=150, required=False, label='نام',
        widget=forms.TextInput(attrs={'class': 'input'}))
    last_name = forms.CharField(max_length=150, required=False, label='نام خانوادگی',
        widget=forms.TextInput(attrs={'class': 'input'}))
    email = forms.EmailField(required=False, label='ایمیل',
        widget=forms.EmailInput(attrs={'class': 'input', 'dir': 'ltr'}))
    new_password = forms.CharField(required=False, label='رمز عبور جدید (خالی = بدون تغییر)',
        widget=forms.PasswordInput(attrs={'class': 'input', 'autocomplete': 'new-password', 'placeholder': 'خالی = بدون تغییر'}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user

    def clean_username(self):
        uname = self.cleaned_data['username'].strip()
        from django.contrib.auth.models import User
        qs = User.objects.filter(username=uname)
        if self._user:
            qs = qs.exclude(pk=self._user.pk)
        if qs.exists():
            raise forms.ValidationError('این نام کاربری قبلاً استفاده شده.')
        return uname
