from django.contrib import messages
from django.db.models import Count, F, Q
from django.shortcuts import redirect, render
from django.urls import reverse

from catalog.discovery import new_rotation_seed, order_for_discovery
from catalog.experience import recent_products
from catalog.models import Product
from catalog.presentation import prepare_public_products
from core.forms import ContactForm
from core.models import hours_summary, is_open_now
from core.views import HomeView
from growth.models import ProductGrowthData


class PublicHomeView(HomeView):
    """Marketplace-style homepage with fast, card-ready discovery collections."""

    PURPOSE_COLLECTIONS = [
        {
            "slug": "student",
            "title": "For students",
            "description": "Dependable laptops and essentials for learning, research and coursework.",
            "icon": "bi-mortarboard",
        },
        {
            "slug": "business",
            "title": "For business",
            "description": "Professional computers and workplace technology for productive teams.",
            "icon": "bi-briefcase",
        },
        {
            "slug": "creative",
            "title": "Creative and technical work",
            "description": "Performance options for design, engineering, editing and demanding software.",
            "icon": "bi-bezier2",
        },
        {
            "slug": "gaming",
            "title": "Gaming and performance",
            "description": "Powerful computers, graphics capability and performance-focused equipment.",
            "icon": "bi-controller",
        },
        {
            "slug": "home",
            "title": "Home and everyday use",
            "description": "Simple, practical technology for communication, entertainment and daily tasks.",
            "icon": "bi-house-door",
        },
        {
            "slug": "available",
            "title": "Available now",
            "description": "Start with products currently available to order and services ready to book.",
            "icon": "bi-check-circle",
        },
    ]

    BUDGET_COLLECTIONS = [
        {
            "title": "Under UGX 1 million",
            "description": "Entry-level and budget-friendly options.",
            "max_price": "1000000",
        },
        {
            "title": "UGX 1–2 million",
            "description": "Balanced choices for school, home and office work.",
            "min_price": "1000000",
            "max_price": "2000000",
        },
        {
            "title": "UGX 2–4 million",
            "description": "Stronger performance and premium business features.",
            "min_price": "2000000",
            "max_price": "4000000",
        },
        {
            "title": "Premium performance",
            "description": "High-end systems for demanding professional work.",
            "min_price": "4000000",
        },
    ]

    @staticmethod
    def _published_products():
        return (
            Product.objects.filter(is_published=True)
            .select_related("category", "category__parent", "growth_data")
            .prefetch_related("gallery_images", "variants")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        published = self._published_products()

        featured_products = published.filter(
            kind=Product.KIND_PHYSICAL,
            is_featured=True,
        )
        if not featured_products.exists():
            featured_products = published.filter(kind=Product.KIND_PHYSICAL)
        featured_services = published.filter(
            kind=Product.KIND_SERVICE,
            is_featured=True,
        )
        if not featured_services.exists():
            featured_services = published.filter(kind=Product.KIND_SERVICE)

        context["featured_products"] = prepare_public_products(
            order_for_discovery(featured_products, new_rotation_seed())[:8]
        )
        context["featured_services"] = prepare_public_products(
            order_for_discovery(featured_services, new_rotation_seed())[:6]
        )
        context["new_arrivals"] = prepare_public_products(
            published.filter(kind=Product.KIND_PHYSICAL).order_by("-created_at", "-pk")[:8]
        )
        context["deal_products"] = prepare_public_products(
            published.filter(kind=Product.KIND_PHYSICAL)
            .filter(
                Q(compare_at_price__gt=F("price"))
                | Q(variants__compare_at_price__gt=F("variants__price"))
            )
            .distinct()
            .order_by("-updated_at", "name")[:8]
        )
        context["refurbished_products"] = prepare_public_products(
            published.filter(
                kind=Product.KIND_PHYSICAL,
                growth_data__condition=ProductGrowthData.CONDITION_REFURBISHED,
            ).order_by("-is_featured", "-updated_at")[:8]
        )
        context["recently_viewed_products"] = prepare_public_products(
            recent_products(self.request, limit=8)
        )
        context["brand_collections"] = list(
            ProductGrowthData.objects.filter(
                product__is_published=True,
                product__kind=Product.KIND_PHYSICAL,
                brand__gt="",
            )
            .values("brand")
            .annotate(product_count=Count("product_id", distinct=True))
            .order_by("-product_count", "brand")[:10]
        )
        context["purpose_collections"] = self.PURPOSE_COLLECTIONS
        context["budget_collections"] = self.BUDGET_COLLECTIONS
        context["condition_guide"] = [
            {
                "name": "New",
                "code": ProductGrowthData.CONDITION_NEW,
                "copy": "New equipment presented as supplied by the manufacturer or distributor.",
            },
            {
                "name": "Refurbished",
                "code": ProductGrowthData.CONDITION_REFURBISHED,
                "copy": "Previously owned equipment prepared for resale and clearly identified.",
            },
            {
                "name": "Used",
                "code": ProductGrowthData.CONDITION_USED,
                "copy": "Pre-owned equipment whose condition should be confirmed before purchase.",
            },
        ]
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
