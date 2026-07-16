from django.shortcuts import redirect, render

from catalog.models import ProductSerial


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
    return render(
        request,
        "portal/warranties.html",
        {
            "warranties": warranties,
            "active_warranty_count": active_count,
            "expired_warranty_count": len(warranties) - active_count,
        },
    )
