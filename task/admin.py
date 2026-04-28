from django.contrib import admin

from .models import AttendanceSession, LeaveRequest


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'start_time', 'end_time', 'duration_minutes', 'note')
    list_filter = ('start_time', 'end_time')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'note')


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'leave_type',
        'start_date',
        'end_date',
        'leave_date',
        'start_time',
        'end_time',
        'days_count',
        'hours_count',
        'status',
        'reviewer',
        'reviewed_at',
    )
    list_filter = ('leave_type', 'status', 'start_date', 'end_date', 'leave_date')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'reason')
