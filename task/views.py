from datetime import date, timedelta
from math import ceil

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from account.models import EmployeeProfile

from .jalali import format_jalali_datetime, format_jalali_month_year
from .models import AttendanceSession, LeaveRequest

MIN_ATTENDANCE_SECONDS = 60


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


def _overlap_days(start_date, end_date, month_start, month_end):
    start = max(start_date, month_start)
    end = min(end_date, month_end)
    if end < start:
        return 0
    return (end - start).days + 1


def _monthly_work_snapshot(user, month_start, next_month_start):
    monthly_sessions = AttendanceSession.objects.filter(
        user=user,
        end_time__isnull=False,
        start_time__date__gte=month_start,
        start_time__date__lt=next_month_start,
    )
    total_minutes = monthly_sessions.aggregate(total=Sum('duration_minutes'))['total'] or 0
    sessions_count = monthly_sessions.count()
    return total_minutes, sessions_count


def _session_elapsed_seconds(session):
    return int((timezone.now() - session.start_time).total_seconds())


@login_required
def attendance_action(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'message': 'درخواست نامعتبر است.'}, status=405)

    action = request.POST.get('action')
    if action not in {'start', 'end'}:
        return JsonResponse({'ok': False, 'message': 'عملیات نامعتبر است.'}, status=400)

    active_session = (
        AttendanceSession.objects.filter(user=request.user, end_time__isnull=True)
        .order_by('-start_time')
        .first()
    )

    if action == 'start':
        if active_session:
            return JsonResponse({'ok': False, 'message': 'یک تایمر فعال دارید. ابتدا پایان بزنید.'}, status=400)

        note = request.POST.get('note', '').strip()
        AttendanceSession.objects.create(user=request.user, note=note)
        user_message = 'ورود ثبت شد و تایمر شروع شد.'

    else:
        if not active_session:
            return JsonResponse({'ok': False, 'message': 'تایمر فعالی برای پایان وجود ندارد.'}, status=400)

        elapsed_seconds = _session_elapsed_seconds(active_session)
        if elapsed_seconds < MIN_ATTENDANCE_SECONDS:
            remaining = ceil(MIN_ATTENDANCE_SECONDS - elapsed_seconds)
            return JsonResponse(
                {
                    'ok': False,
                    'message': f'برای ثبت پایان باید حداقل ۱ دقیقه از شروع بگذرد. {remaining} ثانیه باقی مانده است.',
                },
                status=400,
            )

        note = request.POST.get('note', '').strip()
        if note:
            active_session.note = note
            active_session.save(update_fields=['note'])
        active_session.close_session()
        user_message = 'پایان ثبت شد و تردد ذخیره شد.'

    active_session = (
        AttendanceSession.objects.filter(user=request.user, end_time__isnull=True)
        .order_by('-start_time')
        .first()
    )

    today = timezone.localdate()
    month_start, next_month_start, _ = _month_bounds(today)
    total_minutes, sessions_count = _monthly_work_snapshot(request.user, month_start, next_month_start)

    active_elapsed_seconds = 0
    active_started_at = 'در انتظار شروع شیفت'
    if active_session:
        active_elapsed_seconds = int((timezone.now() - active_session.start_time).total_seconds())
        active_started_at = f'شروع: {format_jalali_datetime(active_session.start_time)}'

    return JsonResponse(
        {
            'ok': True,
            'message': user_message,
            'active_session': bool(active_session),
            'active_elapsed_seconds': active_elapsed_seconds,
            'active_started_at': active_started_at,
            'monthly_total_time_text': _format_minutes(total_minutes),
            'monthly_sessions_count': sessions_count,
            'monthly_sessions_hint': f'{sessions_count} تردد ثبت شده',
        }
    )


@login_required
def dashboard(request):
    today = timezone.localdate()
    month_start, next_month_start, month_end = _month_bounds(today)

    profile, _ = EmployeeProfile.objects.get_or_create(user=request.user)
    active_session = (
        AttendanceSession.objects.filter(user=request.user, end_time__isnull=True)
        .order_by('-start_time')
        .first()
    )

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'start':
            if active_session:
                messages.warning(request, 'یک تایمر فعال دارید. ابتدا پایان را ثبت کنید.')
            else:
                note = request.POST.get('note', '').strip()
                AttendanceSession.objects.create(user=request.user, note=note)
                messages.success(request, 'ورود ثبت شد و تایمر شروع شد.')

        elif action == 'end':
            if not active_session:
                messages.warning(request, 'تایمر فعالی برای پایان وجود ندارد.')
            else:
                elapsed_seconds = _session_elapsed_seconds(active_session)
                if elapsed_seconds < MIN_ATTENDANCE_SECONDS:
                    remaining = ceil(MIN_ATTENDANCE_SECONDS - elapsed_seconds)
                    messages.warning(
                        request,
                        f'برای ثبت پایان باید حداقل ۱ دقیقه از شروع بگذرد. {remaining} ثانیه باقی مانده است.',
                    )
                    return redirect('task:dashboard')

                note = request.POST.get('note', '').strip()
                if note:
                    active_session.note = note
                    active_session.save(update_fields=['note'])
                active_session.close_session()
                messages.success(request, 'پایان ثبت شد و تردد با موفقیت ذخیره شد.')

        elif action in {'approve_leave', 'reject_leave'} and request.user.is_superuser:
            leave = get_object_or_404(LeaveRequest, id=request.POST.get('leave_id'))
            leave.status = (
                LeaveRequest.STATUS_APPROVED
                if action == 'approve_leave'
                else LeaveRequest.STATUS_REJECTED
            )
            leave.reviewer = request.user
            leave.reviewed_at = timezone.now()
            leave.admin_note = request.POST.get('admin_note', '')
            leave.save(update_fields=['status', 'reviewer', 'reviewed_at', 'admin_note', 'updated_at'])
            messages.success(request, 'وضعیت مرخصی به‌روز شد.')

        return redirect('task:dashboard')

    total_minutes, sessions_count = _monthly_work_snapshot(request.user, month_start, next_month_start)

    approved_month_leaves = LeaveRequest.objects.filter(
        user=request.user,
        status=LeaveRequest.STATUS_APPROVED,
        leave_type=LeaveRequest.LEAVE_TYPE_DAILY,
        start_date__lte=month_end,
        end_date__gte=month_start,
    )
    approved_leave_days = sum(
        _overlap_days(leave.start_date, leave.end_date, month_start, month_end)
        for leave in approved_month_leaves
    )

    pending_leave_days = (
        LeaveRequest.objects.filter(user=request.user, status=LeaveRequest.STATUS_PENDING)
        .aggregate(total=Sum('days_count'))
        .get('total')
        or 0
    )

    recent_sessions = AttendanceSession.objects.filter(user=request.user)[:10]
    team_overview = None
    pending_team_leaves = None
    if request.user.is_superuser:
        employees = User.objects.filter(is_superuser=False)
        team_overview = {
            'employees_count': employees.count(),
            'active_now': AttendanceSession.objects.filter(end_time__isnull=True)
            .values('user')
            .distinct()
            .count(),
            'pending_leaves': LeaveRequest.objects.filter(status=LeaveRequest.STATUS_PENDING).count(),
        }
        pending_team_leaves = LeaveRequest.objects.filter(status=LeaveRequest.STATUS_PENDING).select_related('user')

    active_elapsed_seconds = 0
    if active_session:
        active_elapsed_seconds = int((timezone.now() - active_session.start_time).total_seconds())

    context = {
        'profile': profile,
        'active_session': active_session,
        'active_elapsed_seconds': active_elapsed_seconds,
        'monthly_total_minutes': total_minutes,
        'monthly_total_time_text': _format_minutes(total_minutes),
        'daily_target_hours': profile.daily_target_hours,
        'daily_target_seconds': profile.daily_target_hours * 3600,
        'monthly_target_hours': profile.monthly_target_hours,
        'monthly_target_minutes': profile.monthly_target_hours * 60,
        'monthly_sessions_count': sessions_count,
        'approved_leave_days': approved_leave_days,
        'pending_leave_days': pending_leave_days,
        'recent_sessions': recent_sessions,
        'team_overview': team_overview,
        'pending_team_leaves': pending_team_leaves,
        'month_label': format_jalali_month_year(today),
    }
    return render(request, 'task/dashboard.html', context)
