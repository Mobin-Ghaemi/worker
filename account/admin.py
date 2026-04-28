from django.contrib import admin

from .models import EmployeeProfile


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'job_title',
        'hire_date',
        'daily_target_hours',
        'monthly_target_hours',
        'annual_leave_days',
    )
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'job_title')
