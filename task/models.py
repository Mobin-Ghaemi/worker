from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class AttendanceSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendance_sessions')
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_time']
        verbose_name = 'تردد'
        verbose_name_plural = 'ترددها'

    def __str__(self):
        return f'{self.user.username} | {self.start_time:%Y-%m-%d %H:%M}'

    @property
    def is_open(self):
        return self.end_time is None

    @staticmethod
    def _to_local(dt):
        if timezone.is_aware(dt):
            return timezone.localtime(dt)
        return dt

    def clean(self):
        if not self.end_time:
            return

        start_local = self._to_local(self.start_time)
        end_local = self._to_local(self.end_time)

        if end_local <= start_local:
            raise ValidationError('ساعت پایان باید بعد از ساعت شروع باشد.')

        if end_local.date() != start_local.date():
            raise ValidationError('تردد نباید به روز بعد منتقل شود.')

        if (end_local - start_local) > timedelta(hours=24):
            raise ValidationError('مدت هر تردد نباید بیشتر از ۲۴ ساعت باشد.')

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.end_time:
            total_seconds = max(0, int((self.end_time - self.start_time).total_seconds()))
            self.duration_minutes = total_seconds // 60
        else:
            self.duration_minutes = 0
        super().save(*args, **kwargs)

    def close_session(self, end_time=None):
        if self.end_time:
            return

        end = end_time or timezone.now()
        self.end_time = end
        self.save(update_fields=['end_time', 'duration_minutes'])


class LeaveRequest(models.Model):
    LEAVE_TYPE_DAILY = 'daily'
    LEAVE_TYPE_HOURLY = 'hourly'

    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'

    LEAVE_TYPE_CHOICES = [
        (LEAVE_TYPE_DAILY, 'مرخصی روزانه'),
        (LEAVE_TYPE_HOURLY, 'مرخصی ساعتی'),
    ]

    STATUS_CHOICES = [
        (STATUS_PENDING, 'در انتظار بررسی'),
        (STATUS_APPROVED, 'تایید شده'),
        (STATUS_REJECTED, 'رد شده'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPE_CHOICES, default=LEAVE_TYPE_DAILY)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    leave_date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    days_count = models.PositiveIntegerField(default=0)
    hours_count = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_leave_requests',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'درخواست مرخصی'
        verbose_name_plural = 'درخواست‌های مرخصی'

    def __str__(self):
        if self.leave_type == self.LEAVE_TYPE_HOURLY and self.leave_date:
            return f'{self.user.username} | ساعتی {self.leave_date}'
        return f'{self.user.username} | {self.start_date} تا {self.end_date}'

    def clean(self):
        if self.leave_type == self.LEAVE_TYPE_DAILY:
            if not self.start_date or not self.end_date:
                raise ValidationError('برای مرخصی روزانه باید تاریخ شروع و پایان مشخص شود.')

            if self.end_date < self.start_date:
                raise ValidationError('تاریخ پایان باید بعد از تاریخ شروع باشد.')

        elif self.leave_type == self.LEAVE_TYPE_HOURLY:
            if not self.leave_date or not self.start_time or not self.end_time:
                raise ValidationError('برای مرخصی ساعتی باید تاریخ و ساعت شروع/پایان مشخص شود.')

            if self.end_time <= self.start_time:
                raise ValidationError('ساعت پایان باید بعد از ساعت شروع باشد.')

    def save(self, *args, **kwargs):
        self.full_clean()

        if self.leave_type == self.LEAVE_TYPE_DAILY:
            self.days_count = (self.end_date - self.start_date).days + 1
            self.hours_count = 0
            self.leave_date = None
            self.start_time = None
            self.end_time = None
        else:
            delta_seconds = (
                (self.end_time.hour * 3600 + self.end_time.minute * 60 + self.end_time.second)
                - (self.start_time.hour * 3600 + self.start_time.minute * 60 + self.start_time.second)
            )
            self.hours_count = (Decimal(delta_seconds) / Decimal(3600)).quantize(
                Decimal('0.01'),
                rounding=ROUND_HALF_UP,
            )
            self.days_count = 0
            self.start_date = None
            self.end_date = None

        super().save(*args, **kwargs)
