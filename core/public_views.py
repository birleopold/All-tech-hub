from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

from catalog.models import Product
from catalog.presentation import prepare_public_products
from core.forms import ContactForm
from core.models import hours_summary, is_open_now
from core.views import HomeView


class PublicHomeView(HomeView):
    """Homepage with card-ready products prepared from prefetched relations."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["featured_products"] = prepare_public_products(
            context.get("featured_products", [])
        )
        context["featured_services"] = prepare_public_products(
            context.get("featured_services", [])
        )
        return context


def _contact_initial(request):
    initial = {}
    user = request.user
    if user.is_authenticated:
        initial["name"] = user.get_full_name().strip() or user.get_username()
        if user.email:
            initial["email"] = user.email
        try:
            customer = user.customer_profile
        except Exception:
            customer = None
        if customer:
            initial["name"] = customer.name or initial.get("name", "")
            initial["email"] = customer.email or initial.get("email", "")
            initial["phone"] = customer.phone

    requested_type = (request.GET.get("type") or "").strip().lower()
    allowed_types = {value for value, _ in ContactForm.REQUEST_TYPE_CHOICES}
    if requested_type in allowed_types:
        initial["request_type"] = requested_type

    product = None
    product_slug = (request.GET.get("product") or "").strip()
    if product_slug:
        product = (
            Product.objects.filter(slug=product_slug, is_published=True)
            .select_related("category")
            .first()
        )
        if product:
            if "request_type" not in initial:
                initial["request_type"] = ContactForm.REQUEST_PRODUCT
            request_label = dict(ContactForm.REQUEST_TYPE_CHOICES).get(
                initial["request_type"], "Product enquiry"
            )
            initial["subject"] = f"{product.name} — {request_label.lower()}"
            initial["message"] = (
                f"I am interested in {product.name}.\n\n"
                "Please advise on availability, final price, options, delivery or collection, "
                "and any setup or warranty information that applies."
            )

    initial.setdefault("request_type", ContactForm.REQUEST_PRODUCT)
    return initial, product


def public_contact_view(request):
    """Guided contact page with safe product and customer prefill."""

    initial, contact_product = _contact_initial(request)
    if request.method == "POST":
        data = request.POST.copy()
        if not data.get("request_type"):
            data["request_type"] = ContactForm.REQUEST_OTHER
        form = ContactForm(data)
        if form.is_valid():
            contact_message = form.save()
            from marketing.services import create_lead_from_contact

            create_lead_from_contact(request, contact_message)
            messages.success(
                request,
                "Your request has been received. The team will review it and respond using the details you provided.",
            )
            return redirect("contact")
    else:
        form = ContactForm(initial=initial)

    return render(
        request,
        "core/contact.html",
        {
            "form": form,
            "business_hours": hours_summary(),
            "is_open_now": is_open_now(),
            "contact_product": contact_product,
            "request_type_choices": ContactForm.REQUEST_TYPE_CHOICES,
            "contact_canonical_url": request.build_absolute_uri(reverse("contact")),
        },
    )
