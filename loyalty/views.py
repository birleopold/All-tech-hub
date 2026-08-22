from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from loyalty.forms import MarketingPreferenceForm
from loyalty.models import CustomerMarketingPreference
from loyalty.services import (
    ensure_loyalty_account,
    ensure_marketing_preference,
    update_marketing_preference,
    withdraw_all_marketing,
)


def _portal_customer(request):
    if not request.user.is_authenticated:
        return None
    return getattr(request.user, "customer_profile", None)


def _masked_email(value: str) -> str:
    email = (value or "").strip()
    if "@" not in email:
        return "the linked customer record"
    local, domain = email.split("@", 1)
    visible = local[:1] or "*"
    return f"{visible}***@{domain}"


@never_cache
def portal_marketing_preferences(request):
    customer = _portal_customer(request)
    if customer is None:
        return redirect("portal_login")
    preference = ensure_marketing_preference(customer)
    if request.method == "POST":
        form = MarketingPreferenceForm(request.POST, preference=preference)
        if form.is_valid():
            preference = update_marketing_preference(
                customer,
                email_marketing=form.cleaned_data["email_marketing"],
                whatsapp_marketing=form.cleaned_data["whatsapp_marketing"],
                product_updates=form.cleaned_data["product_updates"],
                special_offers=form.cleaned_data["special_offers"],
                source=CustomerMarketingPreference.SOURCE_PORTAL,
            )
            messages.success(request, "Your communication preferences were updated.")
            return redirect("portal_marketing_preferences")
    else:
        form = MarketingPreferenceForm(preference=preference)
    return render(
        request,
        "loyalty/portal_preferences.html",
        {"form": form, "preference": preference},
    )


@never_cache
def portal_loyalty_account(request):
    customer = _portal_customer(request)
    if customer is None:
        return redirect("portal_login")
    account = ensure_loyalty_account(customer)
    return render(
        request,
        "loyalty/portal_loyalty.html",
        {
            "account": account,
            "transactions": account.transactions.all()[:50],
            "points_enabled": bool(getattr(settings, "LOYALTY_POINTS_ENABLED", False)),
            "reward_value": account.points_balance * int(getattr(settings, "LOYALTY_POINT_VALUE_UGX", 100)),
            "minimum_redemption": int(getattr(settings, "LOYALTY_MIN_REDEMPTION_POINTS", 50)),
        },
    )


@never_cache
@require_http_methods(["GET", "POST"])
def unsubscribe_all(request, token):
    preference = get_object_or_404(
        CustomerMarketingPreference.objects.select_related("customer"),
        unsubscribe_token=token,
    )
    changed = False
    if request.method == "POST":
        changed = preference.has_any_consent
        withdraw_all_marketing(preference)
    response = render(
        request,
        "loyalty/unsubscribe.html",
        {
            "preference": preference,
            "email_hint": _masked_email(preference.customer.email),
            "changed": changed,
            "completed": request.method == "POST",
        },
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response
