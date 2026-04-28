import re
from datetime import date, datetime

from django.utils import timezone

PERSIAN_MONTH_NAMES = [
    'فروردین',
    'اردیبهشت',
    'خرداد',
    'تیر',
    'مرداد',
    'شهریور',
    'مهر',
    'آبان',
    'آذر',
    'دی',
    'بهمن',
    'اسفند',
]

_EN_TO_FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
_FA_TO_EN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def to_persian_digits(value):
    return str(value).translate(_EN_TO_FA_DIGITS)


def normalize_digits(value):
    return str(value).translate(_FA_TO_EN_DIGITS)


def gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]

    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621

    gy2 = gy + 1 if gm > 2 else gy
    days = (
        (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        - 80
        + gd
        + g_d_m[gm - 1]
    )

    jy += 33 * (days // 12053)
    days %= 12053

    jy += 4 * (days // 1461)
    days %= 1461

    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365

    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)

    return jy, jm, jd


def jalali_to_gregorian(jy, jm, jd):
    if jy > 979:
        gy = 1600
        jy -= 979
    else:
        gy = 621

    days = (
        (365 * jy)
        + ((jy // 33) * 8)
        + (((jy % 33) + 3) // 4)
        + 78
        + jd
        + ((jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186)
    )

    gy += 400 * (days // 146097)
    days %= 146097

    if days > 36524:
        gy += 100 * ((days - 1) // 36524)
        days = (days - 1) % 36524
        if days >= 365:
            days += 1

    gy += 4 * (days // 1461)
    days %= 1461

    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365

    gd = days + 1

    leap = (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)
    sal_a = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    gm = 1
    while gm <= 12 and gd > sal_a[gm]:
        gd -= sal_a[gm]
        gm += 1

    return gy, gm, gd


def _is_jalali_leap_year(jy):
    gy1, gm1, gd1 = jalali_to_gregorian(jy, 1, 1)
    gy2, gm2, gd2 = jalali_to_gregorian(jy + 1, 1, 1)
    return (date(gy2, gm2, gd2) - date(gy1, gm1, gd1)).days == 366


def _jalali_month_days(jy, jm):
    if 1 <= jm <= 6:
        return 31
    if 7 <= jm <= 11:
        return 30
    return 30 if _is_jalali_leap_year(jy) else 29


def parse_jalali_date(value):
    text = normalize_digits(value).strip().replace('-', '/').replace('.', '/')
    match = re.fullmatch(r'(\d{4})\/(\d{1,2})\/(\d{1,2})', text)
    if not match:
        raise ValueError('فرمت تاریخ باید به صورت YYYY/MM/DD باشد.')

    jy, jm, jd = map(int, match.groups())

    if not (1 <= jm <= 12):
        raise ValueError('ماه شمسی نامعتبر است.')

    max_day = _jalali_month_days(jy, jm)
    if not (1 <= jd <= max_day):
        raise ValueError('روز شمسی نامعتبر است.')

    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    return date(gy, gm, gd)


def parse_flexible_date(value):
    text = normalize_digits(value).strip()
    if not text:
        raise ValueError('تاریخ وارد نشده است.')

    normalized = text.replace('.', '-').replace('/', '-')
    parts = normalized.split('-')
    if len(parts) != 3:
        raise ValueError('فرمت تاریخ نامعتبر است.')

    try:
        year, month, day = map(int, parts)
    except ValueError as exc:
        raise ValueError('فرمت تاریخ نامعتبر است.') from exc

    # If year looks Gregorian (e.g., 2026), parse directly.
    if year >= 1700:
        try:
            return date(year, month, day)
        except ValueError as exc:
            raise ValueError('تاریخ میلادی نامعتبر است.') from exc

    # Otherwise treat it as Jalali.
    return parse_jalali_date(f'{year:04d}/{month:02d}/{day:02d}')


def format_jalali_date(value, persian_digits=True):
    if isinstance(value, datetime):
        value = timezone.localtime(value).date() if timezone.is_aware(value) else value.date()

    jy, jm, jd = gregorian_to_jalali(value.year, value.month, value.day)
    rendered = f'{jy:04d}/{jm:02d}/{jd:02d}'
    return to_persian_digits(rendered) if persian_digits else rendered


def format_jalali_datetime(value, persian_digits=True):
    local_dt = timezone.localtime(value) if timezone.is_aware(value) else value
    jy, jm, jd = gregorian_to_jalali(local_dt.year, local_dt.month, local_dt.day)
    rendered = f'{jy:04d}/{jm:02d}/{jd:02d} - {local_dt:%H:%M}'
    return to_persian_digits(rendered) if persian_digits else rendered


def format_jalali_month_year(value, persian_digits=True):
    if isinstance(value, datetime):
        value = timezone.localtime(value).date() if timezone.is_aware(value) else value.date()

    jy, jm, _ = gregorian_to_jalali(value.year, value.month, value.day)
    rendered = f'{PERSIAN_MONTH_NAMES[jm - 1]} {jy}'
    return to_persian_digits(rendered) if persian_digits else rendered
