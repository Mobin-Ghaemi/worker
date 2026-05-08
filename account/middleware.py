from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin

# Update last_seen at most every N seconds to avoid excessive DB writes
LAST_SEEN_UPDATE_INTERVAL = 60


def _get_client_ip(request):
    """Return the real client IP, respecting common proxy headers."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


class IPRestrictionMiddleware(MiddlewareMixin):
    """Block requests whose IP is not in SiteSettings.allowed_ips when restriction is enabled.

    Exempt:
    - The Django admin (so superuser can always manage settings)
    - The site-settings page itself
    """

    EXEMPT_PATHS = ('/admin/',)
    # These exact paths are always open (views themselves enforce superuser check)
    EXEMPT_PATHS_EXACT = (
        '/account/settings/',
        '/account/login/',
    )

    def process_request(self, request):
        # Avoid circular import — import here
        from account.models import SiteSettings

        # Always allow Django admin and login/settings pages
        if any(request.path.startswith(p) for p in self.EXEMPT_PATHS):
            return None
        if request.path.rstrip('/') + '/' in [p.rstrip('/') + '/' for p in self.EXEMPT_PATHS_EXACT]:
            return None

        settings = SiteSettings.get()
        if not settings.ip_restriction_enabled:
            return None  # restriction off — everyone passes

        # Superuser is always allowed regardless of IP
        if request.user.is_authenticated and request.user.is_superuser:
            return None

        client_ip = _get_client_ip(request)
        allowed = settings.get_allowed_ip_list()

        if client_ip in allowed:
            return None  # allowed

        # Blocked
        return render(request, 'account/ip_blocked.html', {
            'client_ip': client_ip,
        }, status=403)

    def process_response(self, request, response):
        """Update last_seen for authenticated non-superuser employees."""
        from django.utils import timezone
        try:
            if request.user.is_authenticated:
                profile = getattr(request.user, 'employee_profile', None)
                if profile:
                    now = timezone.now()
                    if (
                        not profile.last_seen
                        or (now - profile.last_seen).total_seconds() >= LAST_SEEN_UPDATE_INTERVAL
                    ):
                        profile.last_seen = now
                        profile.save(update_fields=['last_seen'])
        except Exception:
            pass
        return response


class PositionAccessMiddleware:
    """
    For authenticated non-superuser employees that have a Position assigned,
    restrict access to only the pages listed in position.allowed_pages.
    If allowed_pages is empty, no restriction is applied.
    Always exempts login/logout and admin.
    """

    ALWAYS_ALLOWED = {'account:login', 'account:logout'}
    EXEMPT_PREFIXES = ('/admin/',)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and not request.user.is_superuser
            and not any(request.path.startswith(p) for p in self.EXEMPT_PREFIXES)
        ):
            profile = getattr(request.user, 'employee_profile', None)
            if profile:
                position = profile.position
                if position and position.allowed_pages:
                    from django.urls import resolve, Resolver404
                    try:
                        match = resolve(request.path)
                        ns = match.namespace
                        url_name = match.url_name
                        full_name = f'{ns}:{url_name}' if ns else url_name
                    except Resolver404:
                        full_name = None

                    if full_name and full_name not in self.ALWAYS_ALLOWED:
                        if full_name not in position.allowed_pages:
                            from django.contrib import messages
                            from django.shortcuts import redirect
                            messages.error(request, 'شما دسترسی به این صفحه را ندارید.')
                            return redirect('task:dashboard')
        return self.get_response(request)
