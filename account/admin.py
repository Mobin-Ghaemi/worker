from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from .models import EmployeeProfile, SiteSettings


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


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ('ip_restriction_status', 'ip_count')
    fields = ('ip_restriction_enabled', 'allowed_ips')

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """Skip the list view — go straight to the single settings object."""
        obj = SiteSettings.get()
        return HttpResponseRedirect(
            reverse('admin:account_sitesettings_change', args=(obj.pk,))
        )

    def ip_restriction_status(self, obj):
        if obj.ip_restriction_enabled:
            return format_html('<span style="color:green;font-weight:bold;">✔ فعال</span>')
        return format_html('<span style="color:gray;">✘ غیرفعال</span>')
    ip_restriction_status.short_description = 'وضعیت محدودیت IP'

    def ip_count(self, obj):
        ips = obj.get_allowed_ip_list()
        return f'{len(ips)} آی‌پی ثبت شده'
    ip_count.short_description = 'تعداد آی‌پی‌ها'
