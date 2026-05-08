from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class SiteSettings(models.Model):
    """Singleton model — only one row should exist (pk=1)."""

    ip_restriction_enabled = models.BooleanField(
        default=False,
        verbose_name='محدودیت IP فعال',
        help_text='اگر فعال باشد، فقط آی‌پی‌های لیست زیر اجازه دسترسی دارند.',
    )
    allowed_ips = models.TextField(
        blank=True,
        verbose_name='آی‌پی‌های مجاز',
        help_text='هر آی‌پی را در یک خط بنویسید. مثال: 185.10.20.30',
    )

    class Meta:
        verbose_name = 'تنظیمات سایت'
        verbose_name_plural = 'تنظیمات سایت'

    def __str__(self):
        status = 'فعال' if self.ip_restriction_enabled else 'غیرفعال'
        return f'تنظیمات سایت (محدودیت IP: {status})'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def get_allowed_ip_list(self):
        return [ip.strip() for ip in self.allowed_ips.splitlines() if ip.strip()]


ONLINE_THRESHOLD_SECONDS = 5 * 60  # 5 minutes


def avatar_upload_path(instance, filename):
    return f'avatars/{instance.user_id}/{filename}'


# Pages that can be restricted per position
PAGE_PERMISSIONS = [
    ('task:dashboard',          'داشبورد'),
    ('account:profile',         'پروفایل'),
    ('account:edit_profile',    'ویرایش پروفایل'),
    ('account:attendances',     'ترددها'),
    ('account:leaves',          'مرخصی'),
    ('account:chat_list',       'پیام‌رسان'),
    ('account:leave_management','مدیریت مرخصی'),
]


class Position(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='عنوان سمت')
    description = models.TextField(blank=True, verbose_name='توضیحات')
    color = models.CharField(
        max_length=7, default='#2563eb',
        verbose_name='رنگ برچسب',
        help_text='کد رنگ HEX مثل #2563eb',
    )
    allowed_pages = models.JSONField(
        default=list, blank=True,
        verbose_name='صفحات مجاز',
        help_text='لیست نام URL‌هایی که این سمت مجاز به دسترسی است. خالی = همه صفحات.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'سمت'
        verbose_name_plural = 'سمت‌ها'
        ordering = ['name']

    def __str__(self):
        return self.name


class EmployeeProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee_profile')
    position = models.ForeignKey(
        Position, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='سمت', related_name='employees',
    )
    job_title = models.CharField(max_length=120, blank=True)
    hire_date = models.DateField(default=timezone.localdate)
    daily_target_hours = models.PositiveIntegerField(default=8)
    monthly_target_hours = models.PositiveIntegerField(default=160)
    annual_leave_days = models.PositiveIntegerField(default=24)
    last_seen = models.DateTimeField(null=True, blank=True, verbose_name='آخرین فعالیت')
    avatar = models.ImageField(upload_to=avatar_upload_path, null=True, blank=True, verbose_name='تصویر پروفایل')
    bio = models.TextField(blank=True, verbose_name='درباره من')
    birth_date = models.DateField(null=True, blank=True, verbose_name='تاریخ تولد')
    national_id = models.CharField(max_length=10, blank=True, verbose_name='کد ملی')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'پروفایل کارمند'
        verbose_name_plural = 'پروفایل کارمندان'

    def __str__(self):
        full_name = self.user.get_full_name().strip()
        return full_name or self.user.username

    @property
    def is_online(self):
        """User is online if they have an open (started but not ended) attendance session."""
        from task.models import AttendanceSession
        return AttendanceSession.objects.filter(
            user=self.user,
            end_time__isnull=True,
        ).exists()

    @classmethod
    def get_online_employees(cls):
        from task.models import AttendanceSession
        online_user_ids = AttendanceSession.objects.filter(
            end_time__isnull=True,
        ).values_list('user_id', flat=True)
        return cls.objects.filter(user_id__in=online_user_ids).select_related('user')
def chat_upload_path(instance, filename):
    return f'chat/{instance.sender_id}/{filename}'


class ChatMessage(models.Model):
    FILE_TYPE_NONE  = 'none'
    FILE_TYPE_IMAGE = 'image'
    FILE_TYPE_FILE  = 'file'
    FILE_TYPE_CHOICES = [
        (FILE_TYPE_NONE,  'متن'),
        (FILE_TYPE_IMAGE, 'تصویر'),
        (FILE_TYPE_FILE,  'فایل'),
    ]

    sender   = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    content  = models.TextField(blank=True)
    file     = models.FileField(upload_to=chat_upload_path, blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True)
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES, default=FILE_TYPE_NONE)
    is_read  = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'پیام چت'
        verbose_name_plural = 'پیام‌های چت'

    def __str__(self):
        return f'{self.sender} → {self.receiver}: {self.content[:40]}'
