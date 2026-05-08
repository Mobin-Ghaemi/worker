import re
from datetime import datetime, time

from django import forms
from django.utils import timezone

from .jalali import normalize_digits, parse_flexible_date
from .models import LeaveRequest


def _parse_time_value(raw_value):
    text = normalize_digits(raw_value).strip()
    match = re.fullmatch(r'(\d{1,2}):(\d{1,2})', text)
    if not match:
        raise ValueError('فرمت ساعت باید به صورت HH:MM باشد.')

    hour_value, minute_value = map(int, match.groups())
    if not (0 <= hour_value <= 23 and 0 <= minute_value <= 59):
        raise ValueError('ساعت واردشده نامعتبر است.')

    return time(hour=hour_value, minute=minute_value)


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
                cleaned['start_time'] = _parse_time_value(start_time_raw)
                cleaned['end_time'] = _parse_time_value(end_time_raw)
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


class AttendanceAddForm(forms.Form):
    work_date = forms.CharField()
    start_time = forms.CharField()
    end_time = forms.CharField()
    note = forms.CharField(required=False, max_length=255)

    def clean(self):
        cleaned = super().clean()
        work_date_raw = cleaned.get('work_date', '')
        start_time_raw = cleaned.get('start_time', '')
        end_time_raw = cleaned.get('end_time', '')

        if not work_date_raw or not start_time_raw or not end_time_raw:
            raise forms.ValidationError('تاریخ و ساعات شروع/پایان باید کامل وارد شوند.')

        try:
            work_date = parse_flexible_date(work_date_raw)
            start_clock = _parse_time_value(start_time_raw)
            end_clock = _parse_time_value(end_time_raw)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc

        tz = timezone.get_current_timezone()
        start_dt = timezone.make_aware(datetime.combine(work_date, start_clock), timezone=tz)
        end_dt = timezone.make_aware(datetime.combine(work_date, end_clock), timezone=tz)

        if end_dt <= start_dt:
            raise forms.ValidationError('ساعت پایان باید بعد از ساعت شروع باشد.')
        if int((end_dt - start_dt).total_seconds()) > 24 * 3600:
            raise forms.ValidationError('مدت تردد نباید بیشتر از ۲۴ ساعت باشد.')

        cleaned['start_datetime'] = start_dt
        cleaned['end_datetime'] = end_dt
        cleaned['duration_minutes'] = int((end_dt - start_dt).total_seconds()) // 60
        cleaned['note'] = (cleaned.get('note') or '').strip()
        return cleaned


class AttendanceEditForm(forms.Form):
    session_id = forms.IntegerField(widget=forms.HiddenInput())
    work_date = forms.CharField(
        label='تاریخ',
        widget=forms.TextInput(
            attrs={
                'class': 'f-input',
                'placeholder': 'مثال: 1405/02/08',
                'dir': 'ltr',
                'inputmode': 'numeric',
                'autocomplete': 'off',
            }
        ),
    )
    start_time = forms.CharField(
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
        label='ساعت پایان',
        widget=forms.TextInput(
            attrs={
                'class': 'f-input',
                'placeholder': 'مثال: 17:45',
                'dir': 'ltr',
                'inputmode': 'numeric',
                'autocomplete': 'off',
            }
        ),
    )
    note = forms.CharField(
        required=False,
        max_length=255,
        label='توضیحات',
        widget=forms.TextInput(
            attrs={
                'class': 'f-input',
                'placeholder': 'اختیاری',
            }
        ),
    )

    def clean(self):
        cleaned = super().clean()
        work_date_raw = cleaned.get('work_date', '')
        start_time_raw = cleaned.get('start_time', '')
        end_time_raw = cleaned.get('end_time', '')

        if not work_date_raw or not start_time_raw or not end_time_raw:
            raise forms.ValidationError('تاریخ و ساعات شروع/پایان باید کامل وارد شوند.')

        try:
            work_date = parse_flexible_date(work_date_raw)
            start_clock = _parse_time_value(start_time_raw)
            end_clock = _parse_time_value(end_time_raw)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc

        tz = timezone.get_current_timezone()
        start_dt = timezone.make_aware(
            datetime.combine(work_date, start_clock),
            timezone=tz,
        )
        end_dt = timezone.make_aware(
            datetime.combine(work_date, end_clock),
            timezone=tz,
        )

        if end_dt <= start_dt:
            raise forms.ValidationError('ساعت پایان باید بعد از ساعت شروع باشد.')

        duration_seconds = int((end_dt - start_dt).total_seconds())
        if duration_seconds > 24 * 3600:
            raise forms.ValidationError('مدت تردد نباید بیشتر از ۲۴ ساعت باشد.')

        cleaned['start_datetime'] = start_dt
        cleaned['end_datetime'] = end_dt
        cleaned['duration_minutes'] = duration_seconds // 60
        cleaned['work_date_obj'] = work_date
        cleaned['start_time_obj'] = start_clock
        cleaned['end_time_obj'] = end_clock
        cleaned['work_date'] = work_date.strftime('%Y-%m-%d')
        cleaned['start_time'] = start_clock.strftime('%H:%M')
        cleaned['end_time'] = end_clock.strftime('%H:%M')
        cleaned['note'] = (cleaned.get('note') or '').strip()
        return cleaned
