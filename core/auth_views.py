from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_POST

from core.models import LoginAttempt, StaffTwoFactor
from core.totp import generate_secret, provisioning_uri, verify_token

MAX_FAILURES = 5
LOCK_MINUTES = 15


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None


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
            if profile and not verify_token(profile.secret, request.POST.get("otp") or ""):
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
        target = request.POST.get("next") or reverse("staff_dashboard")
        if not url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()):
            target = reverse("staff_dashboard")
        return redirect(target)


def two_factor_setup(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect("login")
    profile, _ = StaffTwoFactor.objects.get_or_create(
        user=request.user, defaults={"secret": generate_secret()}
    )
    if not profile.secret:
        profile.secret = generate_secret()
        profile.save(update_fields=["secret", "updated_at"])
    return render(
        request,
        "registration/two_factor_setup.html",
        {
            "profile": profile,
            "provisioning_uri": provisioning_uri(profile.secret, request.user.get_username()),
        },
    )


@require_POST
def two_factor_confirm(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect("login")
    profile = StaffTwoFactor.objects.get(user=request.user)
    if verify_token(profile.secret, request.POST.get("otp") or ""):
        profile.enabled = True
        profile.confirmed_at = timezone.now()
        profile.save(update_fields=["enabled", "confirmed_at", "updated_at"])
        messages.success(request, "Two-factor authentication enabled.")
    else:
        messages.error(request, "That authentication code was not valid.")
    return redirect("staff_two_factor_setup")


@require_POST
def two_factor_disable(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect("login")
    StaffTwoFactor.objects.filter(user=request.user).update(enabled=False)
    messages.success(request, "Two-factor authentication disabled.")
    return redirect("staff_two_factor_setup")
