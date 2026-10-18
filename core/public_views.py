from django.contrib import messages
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.urls import reverse

from catalog.discovery import new_rotation_seed, order_for_discovery
from catalog.models import Category, Product
from catalog.presentation import prepare_public_products
from core.forms import ContactForm
from core.models import hours_summary, is_open_now
from core.seo import public_url
from core.views import HomeView
from merchandising.models import HomepagePromotion


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
            "description": "Browse products available to order and services with confirmed listed prices.",
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
        now = timezone.now()
        recently_checked = now - timedelta(days=30)

        # Read a bounded pool, then show credible, sellable listings first.
        # Randomization happens only inside each availability tier. Never
        # assert stock verification just because quantity is nonzero.
        candidates = prepare_public_products(
            order_for_discovery(
                published.filter(kind=Product.KIND_PHYSICAL),
                new_rotation_seed(),
            )[:120]
        )
        def listing_order(card):
            confirmed = bool(
                card.public_available and card.public_stock_confirmed_at
                and card.public_stock_confirmed_at >= recently_checked
            )
            return (
                not confirmed,
                not card.public_available,
                not card.is_featured,
                not bool(card.primary_display_image),
            )

        candidates.sort(key=listing_order)
        featured = candidates[:8]
        context["featured_products"] = featured
        services = published.filter(kind=Product.KIND_SERVICE)
        selected_services = services.filter(is_featured=True)
        if not selected_services.exists():
            selected_services = services
        context["featured_services"] = prepare_public_products(
            order_for_discovery(selected_services, new_rotation_seed())[:3]
        )

        # Campaigns are managed from staff. Scheduled/expired campaigns are
        # never rendered, nor are promotions for unpublished products.
        active = (
            HomepagePromotion.objects.filter(is_active=True)
            .filter(Q(start_at__isnull=True) | Q(start_at__lte=now))
            .filter(Q(end_at__isnull=True) | Q(end_at__gt=now))
            .filter(Q(product__isnull=True) | Q(product__is_published=True))
            .select_related("product")
            .order_by("-priority", "-updated_at", "-pk")
        )
        promotions = {}
        for item in active:
            promotions.setdefault(item.slot, item)
            if len(promotions) == 3:
                break
        context["hero_promotion"] = promotions.get(HomepagePromotion.HERO)
        context["upper_promotion"] = promotions.get(HomepagePromotion.SIDE_TOP)
        context["lower_promotion"] = promotions.get(HomepagePromotion.SIDE_BOTTOM)
        context["hero_product"] = next(
            (item for item in featured if item.primary_display_image), None
        )

        # Show authentic product photos as visual category tiles; fill missing
        # departments without inventing category imagery or stock.
        tiles = []
        used_ids = set()
        for product in candidates:
            category = product.category
            if category.pk not in used_ids:
                used_ids.add(category.pk)
                tiles.append({"category": category, "cover": product})
            if len(tiles) >= 6:
                break
        if len(tiles) < 6:
            categories = (
                Category.objects.filter(
                    products__is_published=True,
                    products__kind=Product.KIND_PHYSICAL,
                ).distinct().order_by("sort_order", "name")[:12]
            )
            for category in categories:
                if category.pk not in used_ids:
                    used_ids.add(category.pk)
                    tiles.append({"category": category, "cover": None})
                if len(tiles) >= 6:
                    break
        context["home_category_tiles"] = tiles

        context["deal_products"] = prepare_public_products(
            published.filter(kind=Product.KIND_PHYSICAL)
            .filter(
                Q(compare_at_price__gt=F("price"))
                | Q(variants__compare_at_price__gt=F("variants__price"))
            )
            .distinct()
            .order_by("-updated_at", "name")[:4]
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
    product_slug = (
        request.POST.get("product") if request.method == "POST" else request.GET.get("product")
    ) or request.GET.get("product") or ""
    product_slug = product_slug.strip()
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
            if product.kind == Product.KIND_SERVICE:
                initial["message"] = (
                    f"I would like a quotation for {product.name}.\n\n"
                    "Location or site: \n"
                    "Work required or problem to solve: \n"
                    "Preferred date or timeframe: \n\n"
                    "Please confirm the scope, estimated cost, assessment charges "
                    "(if any), and availability before booking."
                )
            else:
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
            from marketing.services import create_lead_from_contact

            with transaction.atomic():
                contact_message = form.save(commit=False)
                contact_message.product = contact_product
                contact_message.save()
                create_lead_from_contact(request, contact_message, product=contact_product)
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
            "contact_canonical_url": public_url(reverse("contact")),
        },
    )
