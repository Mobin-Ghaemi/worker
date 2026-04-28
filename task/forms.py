import re
from datetime import time

from django import forms

from .jalali import normalize_digits, parse_flexible_date
from .models import LeaveRequest


class LeaveRequestForm(forms.ModelForm):
    start_date = forms.CharField(
        required=False,
        label='شروع مرخصی روزانه',
        widget=forms.DateInput(
            attrs={
                'class': 'f-input',
                'type': 'text',
                'placeholder': 'مثال: 1405/02/08',
                'dir': 'ltr',
                'inputmode': 'numeric',
                'autocomplete': 'off',
            }
        ),
    )
    end_date = forms.CharField(
        required=False,
        label='پایان مرخصی روزانه',
        widget=forms.DateInput(
            attrs={
                'class': 'f-input',
                'type': 'text',
                'placeholder': 'مثال: 1405/02/08',
                'dir': 'ltr',
                'inputmode': 'numeric',
                'autocomplete': 'off',
            }
        ),
    )
    leave_date = forms.CharField(
        required=False,
        label='تاریخ مرخصی ساعتی',
        widget=forms.DateInput(
            attrs={
                'class': 'f-input',
                'type': 'text',
                'placeholder': 'مثال: 1405/02/08',
                'dir': 'ltr',
                'inputmode': 'numeric',
                'autocomplete': 'off',
            }
        ),
    )
    start_time = forms.CharField(
        required=False,
        label='ساعت شروع',
        widget=forms.TextInput(
            attrs={
                'class': 'f-input',
                'placeholder': 'مثال: 08:30',
                'dir': 'ltr',
                'inputmode': 'numeric',
                'autocomplete': 'off',
            }
        ),
    )
    end_time = forms.CharField(
        required=False,
        label='ساعت پایان',
        widget=forms.TextInput(
            attrs={
                'class': 'f-input',
                'placeholder': 'مثال: 12:45',
                'dir': 'ltr',
                'inputmode': 'numeric',
                'autocomplete': 'off',
            }
        ),
    )

    class Meta:
        model = LeaveRequest
        fields = ['leave_type', 'start_date', 'end_date', 'leave_date', 'start_time', 'end_time', 'reason']
        widgets = {
            'leave_type': forms.Select(attrs={'class': 'f-input', 'id': 'leave-type-selector'}),
            'reason': forms.Textarea(attrs={'rows': 3, 'class': 'f-input', 'placeholder': 'علت مرخصی'}),
        }
        labels = {
            'leave_type': 'نوع مرخصی',
            'start_time': 'ساعت شروع',
            'end_time': 'ساعت پایان',
            'reason': 'توضیحات',
        }

    @staticmethod
    def _parse_time_value(raw_value):
        text = normalize_digits(raw_value).strip()
        match = re.fullmatch(r'(\d{1,2}):(\d{1,2})', text)
        if not match:
            raise ValueError('فرمت ساعت باید به صورت HH:MM باشد.')

        hour_value, minute_value = map(int, match.groups())
        if not (0 <= hour_value <= 23 and 0 <= minute_value <= 59):
            raise ValueError('ساعت واردشده نامعتبر است.')

        return time(hour=hour_value, minute=minute_value)

    def clean(self):
        cleaned = super().clean()
        leave_type = cleaned.get('leave_type')

        if leave_type == LeaveRequest.LEAVE_TYPE_DAILY:
            start_raw = cleaned.get('start_date', '')
            end_raw = cleaned.get('end_date', '')

            if not start_raw or not end_raw:
                raise forms.ValidationError('برای مرخصی روزانه، تاریخ شروع و پایان را وارد کنید.')

            try:
                cleaned['start_date'] = parse_flexible_date(start_raw)
                cleaned['end_date'] = parse_flexible_date(end_raw)
            except ValueError as exc:
                raise forms.ValidationError(str(exc)) from exc

            cleaned['leave_date'] = None
            cleaned['start_time'] = None
            cleaned['end_time'] = None

        elif leave_type == LeaveRequest.LEAVE_TYPE_HOURLY:
            date_raw = cleaned.get('leave_date', '')
            start_time_raw = cleaned.get('start_time', '')
            end_time_raw = cleaned.get('end_time', '')

            if not date_raw or not start_time_raw or not end_time_raw:
                raise forms.ValidationError('برای مرخصی ساعتی، تاریخ و ساعت شروع/پایان را وارد کنید.')

            try:
                cleaned['leave_date'] = parse_flexible_date(date_raw)
            except ValueError as exc:
                raise forms.ValidationError(str(exc)) from exc

            try:
                cleaned['start_time'] = self._parse_time_value(start_time_raw)
                cleaned['end_time'] = self._parse_time_value(end_time_raw)
            except ValueError as exc:
                raise forms.ValidationError(str(exc)) from exc

            start_time = cleaned['start_time']
            end_time = cleaned['end_time']
            if end_time <= start_time:
                raise forms.ValidationError('ساعت پایان باید بعد از ساعت شروع باشد.')

            cleaned['start_date'] = None
            cleaned['end_date'] = None

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)

        instance.leave_type = self.cleaned_data['leave_type']
        instance.start_date = self.cleaned_data.get('start_date')
        instance.end_date = self.cleaned_data.get('end_date')
        instance.leave_date = self.cleaned_data.get('leave_date')
        instance.start_time = self.cleaned_data.get('start_time')
        instance.end_time = self.cleaned_data.get('end_time')
        instance.reason = self.cleaned_data.get('reason', '')

        if commit:
            instance.save()

        return instance
