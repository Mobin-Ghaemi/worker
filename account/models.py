from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class EmployeeProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee_profile')
    job_title = models.CharField(max_length=120, blank=True)
    hire_date = models.DateField(default=timezone.localdate)
    daily_target_hours = models.PositiveIntegerField(default=8)
    monthly_target_hours = models.PositiveIntegerField(default=160)
    annual_leave_days = models.PositiveIntegerField(default=24)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'پروفایل کارمند'
        verbose_name_plural = 'پروفایل کارمندان'

    def __str__(self):
        full_name = self.user.get_full_name().strip()
        return full_name or self.user.username
