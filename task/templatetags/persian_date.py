from datetime import date, datetime

from django import template

from task.jalali import format_jalali_date, format_jalali_datetime, format_jalali_month_year

register = template.Library()


@register.filter
def jalali_date(value):
    if not value:
        return '-'

    if isinstance(value, (date, datetime)):
        return format_jalali_date(value)

    return value


@register.filter
def jalali_datetime(value):
    if not value:
        return '-'

    if isinstance(value, datetime):
        return format_jalali_datetime(value)

    if isinstance(value, date):
        return format_jalali_date(value)

    return value


@register.filter
def jalali_month(value):
    if not value:
        return '-'

    if isinstance(value, (date, datetime)):
        return format_jalali_month_year(value)

    return value


@register.filter
def minutes_hhmm(value):
    try:
        total_minutes = int(value or 0)
    except (TypeError, ValueError):
        return '0:00'

    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f'{hours}:{minutes:02d}'


@register.filter
def minutes_to_hours(value):
    try:
        total_minutes = int(value or 0)
    except (TypeError, ValueError):
        return '0.00'

    return f'{(total_minutes / 60):.2f}'
