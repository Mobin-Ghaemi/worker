def user_avatar(request):
    """Inject user_avatar_url into every template context."""
    if not request.user.is_authenticated:
        return {'user_avatar_url': None}
    try:
        avatar = request.user.employee_profile.avatar
        url = avatar.url if avatar else None
    except Exception:
        url = None
    return {'user_avatar_url': url}
