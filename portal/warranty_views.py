from django.shortcuts import redirect, render

from catalog.models import ProductSerial
from core.models import SupportTicket


def customer_warranties(request):
    if not request.user.is_authenticated:
        return redirect("portal_login")
    customer = getattr(request.user, "customer_profile", None)
    if customer is None:
        return redirect("portal_login")

    warranties = list(
        ProductSerial.objects.filter(sold_to=customer)
        .select_related("product", "product_variant")
        .order_by("-sold_at", "product__name", "serial_number")
    )
    active_count = sum(1 for item in warranties if item.is_under_warranty)
    open_claims = (
        SupportTicket.objects.filter(
            customer=customer,
            category=SupportTicket.CATEGORY_WARRANTY,
            related_serial_id__in=[item.pk for item in warranties],
        )
        .exclude(
            status__in=(
                SupportTicket.STATUS_RESOLVED,
                SupportTicket.STATUS_CLOSED,
            )
        )
        .order_by("-updated_at")
    )
    claims_by_serial = {}
    for claim in open_claims:
        claims_by_serial.setdefault(claim.related_serial_id, claim)
    for item in warranties:
        item.open_warranty_claim = claims_by_serial.get(item.pk)

    return render(
        request,
        "portal/warranties.html",
        {
            "warranties": warranties,
            "active_warranty_count": active_count,
            "expired_warranty_count": len(warranties) - active_count,
            "open_warranty_claim_count": len(claims_by_serial),
        },
    )
