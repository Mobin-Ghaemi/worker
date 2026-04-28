from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from task.forms import LeaveRequestForm
from task.jalali import format_jalali_month_year
from task.models import AttendanceSession, LeaveRequest

from .forms import EmployeeCreateForm, StyledAuthenticationForm
from .models import EmployeeProfile


class CustomLoginView(LoginView):
    template_name = 'account/login.html'
    authentication_form = StyledAuthenticationForm


def _month_bounds(current_date):
    first_day = current_date.replace(day=1)
    if current_date.month == 12:
        next_month = date(current_date.year + 1, 1, 1)
    else:
        next_month = date(current_date.year, current_date.month + 1, 1)
    last_day = next_month - timedelta(days=1)
    return first_day, next_month, last_day


def _format_minutes(total_minutes):
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f'{hours}:{minutes:02d}'


def _format_hours(total_hours):
    return f'{float(total_hours):.2f}'.rstrip('0').rstrip('.')


def _overlap_days(start_date, end_date, month_start, month_end):
    start = max(start_date, month_start)
    end = min(end_date, month_end)
    if end < start:
        return 0
    return (end - start).days + 1


@login_required
def employee_management(request):
    if not request.user.is_superuser:
        messages.error(request, 'این بخش فقط برای سوپر یوزر قابل دسترسی است.')
        return redirect('task:dashboard')

    add_form = EmployeeCreateForm()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_employee':
            add_form = EmployeeCreateForm(request.POST)
            if add_form.is_valid():
                user = add_form.save()
                messages.success(request, f'کارمند {user.username} با موفقیت اضافه شد.')
                return redirect('account:employee_management')
            messages.error(request, 'فرم افزودن کارمند کامل نیست.')

        elif action == 'update_targets':
            employee_id = request.POST.get('user_id')
            employee = get_object_or_404(User, id=employee_id, is_superuser=False)

            daily_raw = (request.POST.get('daily_target_hours') or '').strip()
            monthly_raw = (request.POST.get('monthly_target_hours') or '').strip()

            try:
                daily_hours = int(daily_raw)
                monthly_hours = int(monthly_raw)
                if daily_hours < 1 or monthly_hours < 1:
                    raise ValueError
            except ValueError:
                messages.error(request, f'تارگت‌های {employee.username} نامعتبر است.')
                return redirect('account:employee_management')

            profile = employee.employee_profile
            profile.daily_target_hours = daily_hours
            profile.monthly_target_hours = monthly_hours
            profile.save(update_fields=['daily_target_hours', 'monthly_target_hours', 'updated_at'])

            messages.success(request, f'تارگت {employee.username} به‌روزرسانی شد.')
            return redirect('account:employee_management')

        elif action == 'delete_employee':
            employee_id = request.POST.get('user_id')
            employee = get_object_or_404(User, id=employee_id, is_superuser=False)

            username = employee.username
            employee.delete()
            messages.success(request, f'کارمند {username} حذف شد.')
            return redirect('account:employee_management')

    employees = (
        User.objects.filter(is_superuser=False)
        .select_related('employee_profile')
        .order_by('username')
    )

    return render(
        request,
        'account/employee_management.html',
        {
            'add_form': add_form,
            'employees': employees,
        },
    )


@login_required
def profile(request):
    today = timezone.localdate()
    month_start, next_month_start, _ = _month_bounds(today)

    profile_obj, _ = EmployeeProfile.objects.get_or_create(user=request.user)

    attendance_qs = AttendanceSession.objects.filter(user=request.user)
    total_attendance_count = attendance_qs.count()

    daily_minutes = (
        attendance_qs.filter(end_time__isnull=False, start_time__date=today)
        .aggregate(total=Sum('duration_minutes'))
        .get('total')
        or 0
    )

    monthly_minutes = (
        attendance_qs.filter(
            end_time__isnull=False,
            start_time__date__gte=month_start,
            start_time__date__lt=next_month_start,
        )
        .aggregate(total=Sum('duration_minutes'))
        .get('total')
        or 0
    )

    leave_qs = LeaveRequest.objects.filter(user=request.user)
    total_leave_count = leave_qs.count()

    recent_attendance = attendance_qs[:10]

    context = {
        'profile_obj': profile_obj,
        'month_label': format_jalali_month_year(today),
        'total_attendance_count': total_attendance_count,
        'total_leave_count': total_leave_count,
        'daily_work_text': _format_minutes(daily_minutes),
        'monthly_work_text': _format_minutes(monthly_minutes),
        'recent_attendance': recent_attendance,
        'monthly_target_hours': profile_obj.monthly_target_hours,
        'daily_target_hours': profile_obj.daily_target_hours,
    }
    return render(request, 'account/profile.html', context)


@login_required
def leaves(request):
    today = timezone.localdate()
    month_start, next_month_start, month_end = _month_bounds(today)

    if request.method == 'POST' and request.POST.get('action') == 'leave':
        leave_form = LeaveRequestForm(request.POST)
        if leave_form.is_valid():
            leave = leave_form.save(commit=False)
            leave.user = request.user
            leave.save()
            messages.success(request, 'درخواست مرخصی ثبت شد.')
            return redirect('account:leaves')
        messages.error(request, 'فرم مرخصی کامل نیست.')
    else:
        leave_form = LeaveRequestForm()

    leave_qs = LeaveRequest.objects.filter(user=request.user)
    recent_leaves = leave_qs[:20]

    total_leave_count = leave_qs.count()
    pending_leave_count = leave_qs.filter(status=LeaveRequest.STATUS_PENDING).count()
    approved_leave_count = leave_qs.filter(status=LeaveRequest.STATUS_APPROVED).count()

    approved_daily_leaves = leave_qs.filter(
        status=LeaveRequest.STATUS_APPROVED,
        leave_type=LeaveRequest.LEAVE_TYPE_DAILY,
        start_date__lte=month_end,
        end_date__gte=month_start,
    )
    monthly_leave_days = sum(
        _overlap_days(leave.start_date, leave.end_date, month_start, month_end)
        for leave in approved_daily_leaves
    )

    monthly_hourly_leave = (
        leave_qs.filter(
            status=LeaveRequest.STATUS_APPROVED,
            leave_type=LeaveRequest.LEAVE_TYPE_HOURLY,
            leave_date__gte=month_start,
            leave_date__lt=next_month_start,
        )
        .aggregate(total=Sum('hours_count'))
        .get('total')
        or 0
    )

    context = {
        'month_label': format_jalali_month_year(today),
        'leave_form': leave_form,
        'recent_leaves': recent_leaves,
        'total_leave_count': total_leave_count,
        'pending_leave_count': pending_leave_count,
        'approved_leave_count': approved_leave_count,
        'monthly_leave_days': monthly_leave_days,
        'monthly_hourly_leave': _format_hours(monthly_hourly_leave),
    }
    return render(request, 'account/leaves.html', context)
