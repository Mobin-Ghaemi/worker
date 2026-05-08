from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.contrib.auth.views import LoginView
from django.db.models import Count, Sum
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from task.forms import AttendanceAddForm, AttendanceEditForm, LeaveRequestForm
from task.jalali import (
    format_jalali_date,
    format_jalali_month_year,
    gregorian_to_jalali,
    jalali_to_gregorian,
    _jalali_month_days,
)
from task.models import AttendanceSession, LeaveRequest

from .forms import EditProfileForm, EmployeeCreateForm, EmployeeEditForm, StyledAuthenticationForm
from .models import ChatMessage, EmployeeProfile, PAGE_PERMISSIONS, Position, SiteSettings


def _get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '').strip()


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
    total_hours = (int(total_minutes or 0)) / 60
    return f'{total_hours:.2f} ساعت'


def _format_hours(total_hours):
    return f'{float(total_hours):.2f}'.rstrip('0').rstrip('.')


def _overlap_days(start_date, end_date, month_start, month_end):
    start = max(start_date, month_start)
    end = min(end_date, month_end)
    if end < start:
        return 0
    return (end - start).days + 1


def _weekday_index_saturday_first(day):
    return (day.weekday() + 2) % 7


def _resolve_jalali_month(month_key):
    """Parse a 'JYYY-MM' Jalali key; fall back to current Jalali month."""
    if month_key:
        try:
            jy_text, jm_text = month_key.split('-', 1)
            jy = int(jy_text)
            jm = int(jm_text)
            if 1 <= jm <= 12:
                return jy, jm
        except (ValueError, TypeError):
            pass
    today = timezone.localdate()
    jy, jm, _ = gregorian_to_jalali(today.year, today.month, today.day)
    return jy, jm


def _jalali_month_bounds(jy, jm):
    """Return (greg_start, greg_next_start, greg_end) for a Jalali month."""
    jd_count = _jalali_month_days(jy, jm)
    gy_s, gm_s, gd_s = jalali_to_gregorian(jy, jm, 1)
    gy_e, gm_e, gd_e = jalali_to_gregorian(jy, jm, jd_count)
    month_start = date(gy_s, gm_s, gd_s)
    month_end = date(gy_e, gm_e, gd_e)
    next_start = month_end + timedelta(days=1)
    return month_start, next_start, month_end


def _jalali_prev_next(jy, jm):
    if jm == 1:
        prev = (jy - 1, 12)
    else:
        prev = (jy, jm - 1)
    if jm == 12:
        nxt = (jy + 1, 1)
    else:
        nxt = (jy, jm + 1)
    return prev, nxt


def _redirect_with_month(request, month_key, day_key=None):
    query_params = {}
    if month_key:
        query_params['month'] = month_key
    if day_key:
        query_params['day'] = day_key
    query = urlencode(query_params)
    url = request.path
    if query:
        url = f'{url}?{query}'
    return HttpResponseRedirect(url)


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

        elif action == 'edit_employee':
            employee_id = request.POST.get('user_id')
            employee = get_object_or_404(User, id=employee_id)
            form = EmployeeEditForm(request.POST, user=employee)
            if form.is_valid():
                employee.username = form.cleaned_data['username']
                employee.first_name = form.cleaned_data['first_name']
                employee.last_name = form.cleaned_data['last_name']
                employee.email = form.cleaned_data['email']
                new_pw = form.cleaned_data.get('new_password', '').strip()
                if new_pw:
                    employee.set_password(new_pw)
                employee.save()
                messages.success(request, f'اطلاعات {employee.username} ویرایش شد.')
            else:
                for field_errors in form.errors.values():
                    for err in field_errors:
                        messages.error(request, err)
            return redirect('account:employee_management')

    employees = (
        User.objects.all()
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
def edit_profile(request):
    profile_obj, _ = EmployeeProfile.objects.get_or_create(user=request.user)
    from task.jalali import gregorian_to_jalali

    initial = {
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
        'email': request.user.email,
        'bio': profile_obj.bio,
        'national_id': profile_obj.national_id,
        'birth_date': (
            '{:04d}/{:02d}/{:02d}'.format(*gregorian_to_jalali(
                profile_obj.birth_date.year,
                profile_obj.birth_date.month,
                profile_obj.birth_date.day,
            ))
            if profile_obj.birth_date else ''
        ),
    }

    if request.method == 'POST':
        form = EditProfileForm(request.POST, request.FILES)
        if form.is_valid():
            cd = form.cleaned_data
            request.user.first_name = cd['first_name']
            request.user.last_name = cd['last_name']
            request.user.email = cd['email']
            request.user.save()

            profile_obj.bio = cd['bio']
            profile_obj.national_id = cd.get('national_id', '')
            if cd.get('birth_date'):
                profile_obj.birth_date = cd['birth_date']
            if cd.get('remove_avatar') and profile_obj.avatar:
                profile_obj.avatar.delete(save=False)
                profile_obj.avatar = None
            elif cd.get('avatar'):
                if profile_obj.avatar:
                    profile_obj.avatar.delete(save=False)
                profile_obj.avatar = cd['avatar']
            profile_obj.save()
            messages.success(request, 'پروفایل با موفقیت ذخیره شد.')
            return redirect('account:edit_profile')
    else:
        form = EditProfileForm(initial=initial)

    return render(request, 'account/edit_profile.html', {
        'form': form,
        'profile_obj': profile_obj,
    })


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


@login_required
def attendances(request):
    selected_month_key = request.GET.get('month') or request.POST.get('month')

    # --- Resolve Jalali month ---
    jy, jm = _resolve_jalali_month(selected_month_key)
    jm_days = _jalali_month_days(jy, jm)
    month_start, next_month_start, month_end = _jalali_month_bounds(jy, jm)
    selected_month_key = f'{jy:04d}-{jm:02d}'

    profile_obj, _ = EmployeeProfile.objects.get_or_create(user=request.user)
    daily_target_minutes = int(profile_obj.daily_target_hours or 0) * 60
    today = timezone.localdate()

    selected_day_raw = request.GET.get('day') or request.POST.get('day')
    if selected_day_raw:
        try:
            selected_day = date.fromisoformat(selected_day_raw)
        except ValueError:
            selected_day = today if month_start <= today <= month_end else month_start
    else:
        selected_day = today if month_start <= today <= month_end else month_start

    if selected_day < month_start or selected_day > month_end:
        selected_day = today if month_start <= today <= month_end else month_start
    selected_day_key = selected_day.strftime('%Y-%m-%d')

    # --- Check if selected month is the current Jalali month ---
    today_jy, today_jm, _ = gregorian_to_jalali(today.year, today.month, today.day)
    is_current_month = (jy == today_jy and jm == today_jm)

    if request.method == 'POST':
        action = request.POST.get('action')

        # Block any write action on past (or future) months
        if action in ('update_attendance', 'delete_attendance', 'add_attendance') and not is_current_month:
            messages.error(request, 'ثبت و ویرایش تردد فقط برای ماه جاری مجاز است.')
            return _redirect_with_month(request, selected_month_key, selected_day_key)

        if action == 'update_attendance':
            edit_form = AttendanceEditForm(request.POST)
            if edit_form.is_valid():
                session = get_object_or_404(
                    AttendanceSession,
                    id=edit_form.cleaned_data['session_id'],
                    user=request.user,
                )
                if session.end_time is None:
                    messages.error(request, 'تردد فعال قابل ویرایش نیست. ابتدا آن را پایان دهید.')
                    return _redirect_with_month(request, selected_month_key, selected_day_key)

                session.start_time = edit_form.cleaned_data['start_datetime']
                session.end_time = edit_form.cleaned_data['end_datetime']
                session.note = edit_form.cleaned_data['note']
                try:
                    session.save(update_fields=['start_time', 'end_time', 'duration_minutes', 'note'])
                except ValidationError as exc:
                    messages.error(request, ' | '.join(exc.messages))
                else:
                    messages.success(request, 'تردد با موفقیت ویرایش شد.')
                return _redirect_with_month(request, selected_month_key, selected_day_key)

            messages.error(
                request,
                edit_form.non_field_errors()[0] if edit_form.non_field_errors() else 'اطلاعات ویرایش معتبر نیست.',
            )
            return _redirect_with_month(request, selected_month_key, selected_day_key)

        if action == 'delete_attendance':
            session_id = request.POST.get('session_id')
            session = get_object_or_404(AttendanceSession, id=session_id, user=request.user)
            session.delete()
            messages.success(request, 'تردد با موفقیت حذف شد.')
            return _redirect_with_month(request, selected_month_key, selected_day_key)

        if action == 'add_attendance':
            add_form = AttendanceAddForm(request.POST)
            if add_form.is_valid():
                new_session = AttendanceSession(
                    user=request.user,
                    start_time=add_form.cleaned_data['start_datetime'],
                    end_time=add_form.cleaned_data['end_datetime'],
                    note=add_form.cleaned_data['note'],
                )
                try:
                    new_session.save()
                    messages.success(request, 'تردد جدید با موفقیت ثبت شد.')
                except ValidationError as exc:
                    messages.error(request, ' | '.join(exc.messages))
            else:
                err = add_form.non_field_errors()
                messages.error(request, err[0] if err else 'اطلاعات تردد جدید معتبر نیست.')
            return _redirect_with_month(request, selected_month_key, selected_day_key)

    monthly_sessions = (
        AttendanceSession.objects.filter(
            user=request.user,
            start_time__date__gte=month_start,
            start_time__date__lt=next_month_start,
        )
        .order_by('-start_time')
    )
    closed_monthly_sessions = monthly_sessions.filter(end_time__isnull=False)
    total_sessions_count = monthly_sessions.count()
    closed_sessions_count = closed_monthly_sessions.count()
    active_sessions_count = monthly_sessions.filter(end_time__isnull=True).count()
    monthly_total_minutes = closed_monthly_sessions.aggregate(total=Sum('duration_minutes')).get('total') or 0

    # ----- leave dates for current month -----
    leave_dates: set[str] = set()
    daily_leaves_qs = LeaveRequest.objects.filter(
        user=request.user,
        status=LeaveRequest.STATUS_APPROVED,
        leave_type=LeaveRequest.LEAVE_TYPE_DAILY,
        start_date__lte=month_end,
        end_date__gte=month_start,
    )
    for lv in daily_leaves_qs:
        cur = max(lv.start_date, month_start)
        end_lv = min(lv.end_date, month_end)
        while cur <= end_lv:
            leave_dates.add(cur.isoformat())
            cur += timedelta(days=1)
    hourly_leaves_qs = LeaveRequest.objects.filter(
        user=request.user,
        status=LeaveRequest.STATUS_APPROVED,
        leave_type=LeaveRequest.LEAVE_TYPE_HOURLY,
        leave_date__gte=month_start,
        leave_date__lte=month_end,
    )
    for lv in hourly_leaves_qs:
        if lv.leave_date:
            leave_dates.add(lv.leave_date.isoformat())

    # Jalali month bounds for JS validation (ASCII digits)
    jalali_month_start_ascii = f'{jy:04d}/{jm:02d}/01'
    jalali_month_end_ascii = f'{jy:04d}/{jm:02d}/{jm_days:02d}'

    day_sessions_map = {}
    for session in monthly_sessions.order_by('start_time'):
        session_day = timezone.localtime(session.start_time).date()
        day_sessions_map.setdefault(session_day, []).append(session)

    # Build month_days iterating over Jalali days (1..jm_days) to ensure
    # we always start from Jalali 1st regardless of Gregorian alignment.
    month_days = []
    for jd in range(1, jm_days + 1):
        gy_d, gm_d, gd_d = jalali_to_gregorian(jy, jm, jd)
        day_date = date(gy_d, gm_d, gd_d)
        sessions = day_sessions_map.get(day_date, [])
        closed_sessions = [s for s in sessions if s.end_time]
        total_minutes = sum(int(s.duration_minutes or 0) for s in closed_sessions)
        first_start = timezone.localtime(sessions[0].start_time).strftime('%H:%M') if sessions else '-'
        last_end = timezone.localtime(closed_sessions[-1].end_time).strftime('%H:%M') if closed_sessions else '-'
        remaining_minutes = max(daily_target_minutes - total_minutes, 0)
        overtime_minutes = max(total_minutes - daily_target_minutes, 0)
        progress_percent = 0
        if daily_target_minutes > 0:
            progress_percent = min((total_minutes / daily_target_minutes) * 100, 100)

        month_days.append(
            {
                'date': day_date,
                'jalali_day': jd,
                'sessions': sessions,
                'sessions_count': len(sessions),
                'minutes': total_minutes,
                'hours_text': f'{total_minutes / 60:.2f}',
                'remaining_minutes': remaining_minutes,
                'remaining_hours_text': f'{remaining_minutes / 60:.2f}',
                'overtime_minutes': overtime_minutes,
                'overtime_hours_text': f'{overtime_minutes / 60:.2f}',
                'progress_percent': progress_percent,
                'first_start_text': first_start,
                'last_end_text': last_end,
                'is_today': day_date == today,
                'is_selected': day_date == selected_day,
                'is_leave': day_date.isoformat() in leave_dates,
                'day_iso': day_date.strftime('%Y-%m-%d'),
            }
        )

    selected_day_sessions = day_sessions_map.get(selected_day, [])
    selected_day_closed = [session for session in selected_day_sessions if session.end_time]
    selected_day_minutes = sum(int(session.duration_minutes or 0) for session in selected_day_closed)
    selected_day_remaining_minutes = max(daily_target_minutes - selected_day_minutes, 0)
    selected_day_overtime_minutes = max(selected_day_minutes - daily_target_minutes, 0)
    selected_day_first_start = (
        timezone.localtime(selected_day_sessions[0].start_time).strftime('%H:%M')
        if selected_day_sessions
        else '-'
    )
    selected_day_last_end = (
        timezone.localtime(selected_day_closed[-1].end_time).strftime('%H:%M')
        if selected_day_closed
        else '-'
    )

    (prev_jy, prev_jm), (next_jy, next_jm) = _jalali_prev_next(jy, jm)
    max_day_minutes = max((day['minutes'] for day in month_days), default=0)

    today_jy, today_jm, _ = gregorian_to_jalali(today.year, today.month, today.day)
    next_month_disabled = (next_jy * 100 + next_jm) > (today_jy * 100 + today_jm)

    prev_jm_start_g = jalali_to_gregorian(prev_jy, prev_jm, 1)
    next_jm_start_g = jalali_to_gregorian(next_jy, next_jm, 1)
    prev_month_label = format_jalali_month_year(date(*prev_jm_start_g))
    next_month_label = format_jalali_month_year(date(*next_jm_start_g))

    context = {
        'month_label': format_jalali_month_year(month_start),
        'profile_obj': profile_obj,
        'is_current_month': is_current_month,
        'selected_month_key': selected_month_key,
        'prev_month_key': f'{prev_jy:04d}-{prev_jm:02d}',
        'next_month_key': f'{next_jy:04d}-{next_jm:02d}',
        'month_days': month_days,
        'month_days_count': jm_days,
        'daily_target_minutes': daily_target_minutes,
        'daily_target_hours_text': f'{daily_target_minutes / 60:.2f}',
        'selected_day': selected_day,
        'selected_day_iso': selected_day_key,
        'selected_day_sessions': selected_day_sessions,
        'selected_day_sessions_count': len(selected_day_sessions),
        'selected_day_hours_text': f'{selected_day_minutes / 60:.2f}',
        'selected_day_remaining_hours_text': f'{selected_day_remaining_minutes / 60:.2f}',
        'selected_day_overtime_hours_text': f'{selected_day_overtime_minutes / 60:.2f}',
        'selected_day_first_start': selected_day_first_start,
        'selected_day_last_end': selected_day_last_end,
        'monthly_sessions': monthly_sessions,
        'monthly_total_minutes': monthly_total_minutes,
        'monthly_total_hours_text': f'{monthly_total_minutes / 60:.2f}',
        'total_sessions_count': total_sessions_count,
        'closed_sessions_count': closed_sessions_count,
        'active_sessions_count': active_sessions_count,
        'max_day_minutes': max_day_minutes,
        'max_day_hours_text': f'{max_day_minutes / 60:.2f}',
        'next_month_disabled': next_month_disabled,
        'prev_month_label': prev_month_label,
        'next_month_label': next_month_label,
        'jalali_month_start': jalali_month_start_ascii,
        'jalali_month_end': jalali_month_end_ascii,
    }
    return render(request, 'account/attendances.html', context)


@login_required
def site_settings(request):
    if not request.user.is_superuser:
        messages.error(request, 'دسترسی غیرمجاز.')
        return redirect('task:dashboard')

    settings_obj = SiteSettings.get()

    if request.method == 'POST':
        settings_obj.ip_restriction_enabled = 'ip_restriction_enabled' in request.POST
        ips = [ip.strip() for ip in request.POST.getlist('allowed_ips') if ip.strip()]
        settings_obj.allowed_ips = '\n'.join(ips)
        settings_obj.save()
        messages.success(request, 'تنظیمات با موفقیت ذخیره شد.')
        return redirect('account:site_settings')

    return render(request, 'account/site_settings.html', {
        'current_client_ip': _get_client_ip(request),
        'settings_obj': settings_obj,
    })


@login_required
def detect_my_ip(request):
    if not request.user.is_superuser:
        return JsonResponse({'ok': False, 'error': 'unauthorized'}, status=403)
    return JsonResponse({
        'ok': True,
        'ip': _get_client_ip(request),
    })


# ─────────────────────────── Positions ───────────────────────────

def positions_management(request):
    if not request.user.is_superuser:
        messages.error(request, 'این بخش فقط برای سوپر یوزر قابل دسترسی است.')
        return redirect('task:dashboard')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_position':
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            color = request.POST.get('color', '#2563eb').strip()
            allowed_pages = request.POST.getlist('allowed_pages')
            if name:
                if Position.objects.filter(name=name).exists():
                    messages.error(request, f'سمت "{name}" قبلاً ثبت شده.')
                else:
                    Position.objects.create(name=name, description=description, color=color, allowed_pages=allowed_pages)
                    messages.success(request, f'سمت "{name}" اضافه شد.')
            else:
                messages.error(request, 'نام سمت نمی‌تواند خالی باشد.')
            return redirect('account:positions_management')

        elif action == 'edit_position':
            pos_id = request.POST.get('position_id')
            position = get_object_or_404(Position, id=pos_id)
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            color = request.POST.get('color', '#2563eb').strip()
            allowed_pages = request.POST.getlist('allowed_pages')
            if name:
                position.name = name
                position.description = description
                position.color = color
                position.allowed_pages = allowed_pages
                position.save()
                messages.success(request, f'سمت "{name}" ویرایش شد.')
            else:
                messages.error(request, 'نام سمت نمی‌تواند خالی باشد.')
            return redirect('account:positions_management')

        elif action == 'delete_position':
            pos_id = request.POST.get('position_id')
            position = get_object_or_404(Position, id=pos_id)
            name = position.name
            position.delete()
            messages.success(request, f'سمت "{name}" حذف شد.')
            return redirect('account:positions_management')

        elif action == 'assign_position':
            user_id = request.POST.get('user_id')
            pos_id = request.POST.get('position_id') or None
            employee = get_object_or_404(User, id=user_id, is_superuser=False)
            profile = employee.employee_profile
            if pos_id:
                position = get_object_or_404(Position, id=pos_id)
                profile.position = position
                profile.save(update_fields=['position', 'updated_at'])
                messages.success(request, f'سمت {position.name} به {employee.get_full_name() or employee.username} اختصاص یافت.')
            else:
                profile.position = None
                profile.save(update_fields=['position', 'updated_at'])
                messages.success(request, f'سمت {employee.get_full_name() or employee.username} حذف شد.')
            return redirect('account:positions_management')

    positions = Position.objects.prefetch_related('employees__user').all()
    employees = (
        EmployeeProfile.objects
        .filter(user__is_superuser=False)
        .select_related('user', 'position')
        .order_by('user__first_name', 'user__username')
    )
    return render(request, 'account/positions.html', {
        'positions': positions,
        'employees': employees,
        'page_permissions': PAGE_PERMISSIONS,
    })


# ─────────────────────────── Chat ───────────────────────────

import json
import mimetypes

from django.db.models import Max, OuterRef, Q, Subquery
from django.http import JsonResponse
from django.views.decorators.http import require_POST


@login_required
def chat_list(request):
    """Show all users the current user has chatted with, plus all other users."""
    me = request.user
    all_users = User.objects.exclude(pk=me.pk).select_related('employee_profile').order_by('first_name', 'username')

    # Last message per conversation partner
    partner_ids = (
        ChatMessage.objects.filter(Q(sender=me) | Q(receiver=me))
        .values_list('sender_id', 'receiver_id')
    )
    talked_ids = set()
    for s, r in partner_ids:
        talked_ids.add(s if s != me.pk else r)

    # Unread per partner
    unread_by_partner = {}
    for msg in ChatMessage.objects.filter(receiver=me, is_read=False).values('sender_id').annotate(cnt=Count('id')):
        unread_by_partner[msg['sender_id']] = msg['cnt']

    # Last message per partner
    last_msg = {}
    for msg in ChatMessage.objects.filter(
        Q(sender=me) | Q(receiver=me)
    ).order_by('sender_id', 'receiver_id', '-created_at').select_related('sender', 'receiver'):
        partner = msg.receiver if msg.sender == me else msg.sender
        if partner.pk not in last_msg:
            last_msg[partner.pk] = msg

    users_data = []
    for u in all_users:
        try:
            is_online = u.employee_profile.is_online
        except Exception:
            is_online = False
        users_data.append({
            'user': u,
            'unread': unread_by_partner.get(u.pk, 0),
            'last_msg': last_msg.get(u.pk),
            'talked': u.pk in talked_ids,
            'is_online': is_online,
        })

    # Sort: talked first, then by unread desc
    users_data.sort(key=lambda x: (not x['talked'], -x['unread']))

    total_unread = sum(unread_by_partner.values())
    return render(request, 'account/chat_list.html', {
        'users_data': users_data,
        'total_unread': total_unread,
    })


@login_required
def chat_with(request, user_id):
    me = request.user
    other = get_object_or_404(User, pk=user_id)
    if other == me:
        return redirect('account:chat_list')

    # Mark all incoming as read
    ChatMessage.objects.filter(sender=other, receiver=me, is_read=False).update(is_read=True)

    msgs = ChatMessage.objects.filter(
        Q(sender=me, receiver=other) | Q(sender=other, receiver=me)
    ).select_related('sender').order_by('created_at')

    # Online status
    try:
        profile = other.employee_profile
        other_online = profile.is_online
        other_profile_avatar = profile.avatar.url if profile.avatar else None
    except Exception:
        other_online = False
        other_profile_avatar = None

    # Build sidebar user list (same as chat_list)
    all_users = User.objects.exclude(pk=me.pk).select_related('employee_profile').order_by('first_name', 'username')
    unread_by_partner = {}
    for row in ChatMessage.objects.filter(receiver=me, is_read=False).values('sender_id').annotate(cnt=Count('id')):
        unread_by_partner[row['sender_id']] = row['cnt']
    sidebar_users = []
    for u in all_users:
        try:
            is_online = u.employee_profile.is_online
        except Exception:
            is_online = False
        sidebar_users.append({
            'user': u,
            'unread': unread_by_partner.get(u.pk, 0),
            'is_online': is_online,
            'active': u.pk == other.pk,
        })

    return render(request, 'account/chat_detail.html', {
        'other': other,
        'other_online': other_online,
        'other_profile_avatar': other_profile_avatar,
        'messages_qs': msgs,
        'sidebar_users': sidebar_users,
    })


@login_required
@require_POST
def chat_send(request, user_id):
    me = request.user
    other = get_object_or_404(User, pk=user_id)
    content = request.POST.get('content', '').strip()
    uploaded = request.FILES.get('file')

    if not content and not uploaded:
        return JsonResponse({'ok': False, 'error': 'پیام خالی است'}, status=400)

    msg = ChatMessage(sender=me, receiver=other, content=content)

    if uploaded:
        msg.file = uploaded
        msg.file_name = uploaded.name
        mime = mimetypes.guess_type(uploaded.name)[0] or ''
        msg.file_type = ChatMessage.FILE_TYPE_IMAGE if mime.startswith('image/') else ChatMessage.FILE_TYPE_FILE

    msg.save()

    file_url = msg.file.url if msg.file else None
    return JsonResponse({
        'ok': True,
        'id': msg.pk,
        'content': msg.content,
        'file_url': file_url,
        'file_name': msg.file_name,
        'file_type': msg.file_type,
        'created_at': msg.created_at.strftime('%H:%M'),
        'is_read': msg.is_read,
        'mine': True,
    })


@login_required
def chat_poll(request, user_id):
    """Return messages newer than `after` (message pk)."""
    me = request.user
    other = get_object_or_404(User, pk=user_id)
    after = int(request.GET.get('after', 0))

    # Mark newly fetched as read
    new_msgs = ChatMessage.objects.filter(
        sender=other, receiver=me, pk__gt=after
    ).order_by('created_at')
    new_msgs.filter(is_read=False).update(is_read=True)

    data = []
    for m in new_msgs:
        data.append({
            'id': m.pk,
            'content': m.content,
            'file_url': m.file.url if m.file else None,
            'file_name': m.file_name,
            'file_type': m.file_type,
            'created_at': m.created_at.strftime('%H:%M'),
            'mine': False,
        })

    try:
        profile = other.employee_profile
        other_online = profile.is_online
    except Exception:
        other_online = False

    # Return which of my messages to this user have been read
    read_ids = list(
        ChatMessage.objects.filter(
            sender=me, receiver=other, is_read=True
        ).values_list('pk', flat=True)
    )

    return JsonResponse({'messages': data, 'other_online': other_online, 'read_ids': read_ids})


@login_required
def chat_unread_count(request):
    count = ChatMessage.objects.filter(receiver=request.user, is_read=False).count()
    return JsonResponse({'count': count})


@login_required
def chat_unread_per_user(request):
    """Return per-sender unread counts for the current user."""
    from django.db.models import Count as _Count
    rows = (
        ChatMessage.objects
        .filter(receiver=request.user, is_read=False)
        .values('sender_id')
        .annotate(cnt=_Count('id'))
    )
    return JsonResponse({str(row['sender_id']): row['cnt'] for row in rows})


@login_required
def leave_management(request):
    """Superuser page: view & approve/reject all pending leave requests."""
    if not request.user.is_superuser:
        return redirect('task:dashboard')

    if request.method == 'POST':
        action = request.POST.get('action')
        leave_id = request.POST.get('leave_id')
        leave = get_object_or_404(LeaveRequest, pk=leave_id)
        admin_note = request.POST.get('admin_note', '').strip()
        if action == 'approve':
            leave.status = LeaveRequest.STATUS_APPROVED
            leave.reviewer = request.user
            leave.reviewed_at = timezone.now()
            if admin_note:
                leave.admin_note = admin_note
            leave.save(update_fields=['status', 'reviewer', 'reviewed_at', 'admin_note'])
            messages.success(request, f'درخواست مرخصی {leave.user.get_full_name() or leave.user.username} تایید شد.')
        elif action == 'reject':
            leave.status = LeaveRequest.STATUS_REJECTED
            leave.reviewer = request.user
            leave.reviewed_at = timezone.now()
            if admin_note:
                leave.admin_note = admin_note
            leave.save(update_fields=['status', 'reviewer', 'reviewed_at', 'admin_note'])
            messages.success(request, f'درخواست مرخصی {leave.user.get_full_name() or leave.user.username} رد شد.')
        return redirect('account:leave_management')

    status_filter = request.GET.get('status', 'pending')
    qs = LeaveRequest.objects.select_related('user').order_by('-created_at')
    if status_filter == 'all':
        leaves_qs = qs
    else:
        leaves_qs = qs.filter(status=status_filter)

    pending_count = LeaveRequest.objects.filter(status=LeaveRequest.STATUS_PENDING).count()

    context = {
        'leaves_qs': leaves_qs,
        'status_filter': status_filter,
        'pending_count': pending_count,
    }
    return render(request, 'account/leave_management.html', context)


@login_required
def pending_leaves_count(request):
    """JSON API: return count of pending leave requests (superuser only)."""
    if not request.user.is_superuser:
        return JsonResponse({'count': 0})
    count = LeaveRequest.objects.filter(status=LeaveRequest.STATUS_PENDING).count()
    return JsonResponse({'count': count})
