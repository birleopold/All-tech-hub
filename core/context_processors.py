from core.models import CompanySettings, StaffNotification


def company(request):
    m = getattr(request, "resolver_match", None)
    url_name = getattr(m, "url_name", "") or ""
    ctx = {
        "company": CompanySettings.load(),
        "resolve_url_name": url_name,
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_staff:
        ctx["staff_unread_notifications"] = StaffNotification.objects.filter(
            recipient=user, is_read=False
        ).count()
    else:
        ctx["staff_unread_notifications"] = 0
    return ctx
