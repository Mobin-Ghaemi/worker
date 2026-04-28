from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from task.jalali import parse_flexible_date


class StyledAuthenticationForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'input', 'placeholder': 'نام کاربری'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'input', 'placeholder': 'رمز عبور'}))


class EmployeeCreateForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, required=True, label='نام')
    last_name = forms.CharField(max_length=150, required=True, label='نام خانوادگی')
    email = forms.EmailField(required=False, label='ایمیل')
    job_title = forms.CharField(max_length=120, required=False, label='سمت')
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
            profile.job_title = self.cleaned_data.get('job_title', '')
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

    def clean_hire_date(self):
        raw = (self.cleaned_data.get('hire_date') or '').strip()
        if not raw:
            return None
        try:
            return parse_flexible_date(raw)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
