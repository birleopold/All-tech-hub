from datetime import timedelta
from ipaddress import ip_address

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_POST

from core.audit import log_audit_event
from core.field_encryption import (
    ensure_profile_secret_protected,
    protect_totp_secret,
    reveal_totp_secret,
)
from core.models import LoginAttempt, StaffTwoFactor
from core.security import (
    clear_staff_two_factor_verification,
    mark_staff_two_factor_verified,
    staff_two_factor_is_verified,
)
from core.totp import generate_secret, provisioning_uri, verify_token

MAX_FAILURES = 5
LOCK_MINUTES = 15


def _client_ip(request):
    # Nginx sets X-Real-IP from its actual peer. Never trust the leftmost
    # X-Forwarded-For value because clients can supply that header themselves.
    candidate = (
        request.META.get("HTTP_X_REAL_IP")
        or request.META.get("REMOTE_ADDR")
        or ""
    ).strip()
    try:
        return str(ip_address(candidate))
    except ValueError:
        return None


class StaffLoginView(View):
    template_name = "registration/login.html"

    def get(self, request):
        return render(request, self.template_name, {"next": request.GET.get("next", "")})

    def post(self, request):
        username = (request.POST.get("username") or "").strip()
        ip = _client_ip(request)
        since = timezone.now() - timedelta(minutes=LOCK_MINUTES)
        failures = LoginAttempt.objects.filter(
            username__iexact=username,
            ip_address=ip,
            successful=False,
            attempted_at__gte=since,
        ).count()
        if failures >= MAX_FAILURES:
            messages.error(request, "Too many failed attempts. Try again in 15 minutes.")
            return render(request, self.template_name, {"next": request.POST.get("next", "")}, status=429)

        user = authenticate(
            request,
            username=username,
            password=request.POST.get("password") or "",
        )
        valid = user is not None
        profile = None
        if valid and user.is_staff:
            profile = StaffTwoFactor.objects.filter(user=user, enabled=True).first()
            if profile:
                clear_secret = ensure_profile_secret_protected(profile)
                if not verify_token(clear_secret, request.POST.get("otp") or ""):
                    valid = False
        LoginAttempt.objects.create(
            username=username, ip_address=ip, successful=valid
        )
        if not valid:
            messages.error(request, "Invalid credentials or authentication code.")
            return render(request, self.template_name, {"next": request.POST.get("next", "")})
        LoginAttempt.objects.filter(
            username__iexact=username, ip_address=ip, successful=False
        ).delete()
        login(request, user)
        if user.is_staff and profile and profile.enabled:
            mark_staff_two_factor_verified(request, user)
        else:
            clear_staff_two_factor_verification(request)
        target = request.POST.get("next") or reverse("staff_dashboard")
        if not url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()):
            target = reverse("staff_dashboard")
        return redirect(target)


def two_factor_setup(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect("login")
    profile, _ = StaffTwoFactor.objects.get_or_create(
        user=request.user,
        defaults={"secret": protect_totp_secret(generate_secret())},
    )
    if not profile.secret:
        profile.secret = protect_totp_secret(generate_secret())
        profile.save(update_fields=["secret", "updated_at"])
    if profile.enabled and not staff_two_factor_is_verified(request, request.user):
        messages.error(request, "Complete your authenticator challenge before managing 2FA.")
        return redirect("login")
    display_secret = "" if profile.enabled else ensure_profile_secret_protected(profile)
    return render(
        request,
        "registration/two_factor_setup.html",
        {
            "profile": profile,
            "display_secret": display_secret,
            "provisioning_uri": (
                provisioning_uri(display_secret, request.user.get_username())
                if display_secret
                else ""
            ),
        },
    )


@require_POST
def two_factor_confirm(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect("login")
    profile = get_object_or_404(StaffTwoFactor, user=request.user)
    clear_secret = ensure_profile_secret_protected(profile)
    if verify_token(clear_secret, request.POST.get("otp") or ""):
        profile.enabled = True
        profile.confirmed_at = timezone.now()
        profile.save(update_fields=["enabled", "confirmed_at", "updated_at"])
        mark_staff_two_factor_verified(request, request.user)
        log_audit_event(
            actor=request.user,
            verb="security.2fa_enabled",
            summary=f"2FA enabled for {request.user.get_username()}",
            target=profile,
        )
        messages.success(request, "Two-factor authentication enabled.")
    else:
        messages.error(request, "That authentication code was not valid.")
    return redirect("staff_two_factor_setup")


@require_POST
def two_factor_disable(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect("login")
    profile = get_object_or_404(StaffTwoFactor, user=request.user, enabled=True)
    password = request.POST.get("password") or ""
    otp = request.POST.get("otp") or ""
    clear_secret = reveal_totp_secret(profile.secret)
    if not request.user.check_password(password) or not verify_token(clear_secret, otp):
        messages.error(
            request,
            "Enter your current password and a valid authenticator code to disable 2FA.",
        )
        return redirect("staff_two_factor_setup")
    profile.enabled = False
    profile.save(update_fields=["enabled", "updated_at"])
    clear_staff_two_factor_verification(request)
    log_audit_event(
        actor=request.user,
        verb="security.2fa_disabled",
        summary=f"2FA disabled by {request.user.get_username()}",
        target=profile,
    )
    messages.warning(request, "Two-factor authentication disabled.")
    return redirect("staff_two_factor_setup")
