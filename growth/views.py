import hashlib
from io import BytesIO
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import qrcode
from qrcode.image.svg import SvgPathImage
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import user_passes_test
from django.db.models import F, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from catalog.models import Product
from commerce import cart as cart_mod
from core.mixins import StaffRequiredMixin
from growth.forms import (
    AmbassadorForm,
    ContentAssetGeneratorForm,
    DistributionGroupForm,
    GrowthSettingsForm,
    ProductGrowthDataForm,
    SavedCartOptInForm,
    StockAlertForm,
)
from growth.models import (
    Ambassador,
    AmbassadorClick,
    AmbassadorConversion,
    ContentAsset,
    DistributionGroup,
    GrowthSettings,
    ProductGrowthData,
    SavedCart,
    StockAlertSubscription,
)
from growth.services import (
    AMBASSADOR_SESSION_KEY,
    approve_ambassador_conversion,
    generate_content_assets,
    restore_saved_cart,
    pay_ambassador_conversion,
    save_cart_for_recovery,
    send_saved_cart_message,
)


class GrowthDashboardView(StaffRequiredMixin, TemplateView):
    template_name = "growth/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        settings_row = GrowthSettings.load()
        published_physical = Product.objects.filter(
            is_published=True,
            kind=Product.KIND_PHYSICAL,
        )
        configured_product_ids = ProductGrowthData.objects.values_list(
            "product_id", flat=True
        )
        ctx.update(
            {
                "growth_settings": settings_row,
                "active_saved_carts": SavedCart.objects.filter(
                    status=SavedCart.STATUS_ACTIVE
                ).count(),
                "recovered_carts": SavedCart.objects.filter(
                    status=SavedCart.STATUS_RECOVERED
                ).count(),
                "active_stock_alerts": StockAlertSubscription.objects.filter(
                    is_active=True
                ).count(),
                "content_assets": ContentAsset.objects.count(),
                "distribution_groups": DistributionGroup.objects.filter(
                    is_active=True
                ).count(),
                "active_ambassadors": Ambassador.objects.filter(
                    is_active=True
                ).count(),
                "ambassador_revenue": Ambassador.objects.aggregate(
                    total=Sum("revenue_total")
                )["total"]
                or 0,
                "feed_products_total": published_physical.count(),
                "feed_products_missing_metadata": published_physical.exclude(
                    pk__in=configured_product_ids
                ).count(),
                "recent_assets": ContentAsset.objects.select_related(
                    "product", "campaign"
                )[:6],
                "recent_conversions": AmbassadorConversion.objects.select_related(
                    "ambassador", "order"
                )[:6],
            }
        )
        return ctx


class GrowthFormMixin(StaffRequiredMixin):
    template_name = "marketing/form.html"
    page_title = "Growth marketing"
    cancel_url_name = "staff_growth_dashboard"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "page_title": self.page_title,
                "cancel_url_name": self.cancel_url_name,
            }
        )
        return ctx


class CreatedByMixin:
    def form_valid(self, form):
        if hasattr(form.instance, "created_by") and not form.instance.created_by_id:
            form.instance.created_by = self.request.user
        messages.success(self.request, self.success_message)
        return super().form_valid(form)


class GrowthSettingsUpdateView(GrowthFormMixin, UpdateView):
    model = GrowthSettings
    form_class = GrowthSettingsForm
    page_title = "Analytics, Google and automation settings"
    success_url = reverse_lazy("staff_growth_dashboard")

    def get_object(self, queryset=None):
        return GrowthSettings.load()

    def form_valid(self, form):
        messages.success(self.request, "Growth integration settings updated.")
        return super().form_valid(form)


class ProductMetadataListView(StaffRequiredMixin, ListView):
    model = ProductGrowthData
    template_name = "growth/list.html"
    context_object_name = "items"
    paginate_by = 40

    def get_queryset(self):
        return ProductGrowthData.objects.select_related("product", "product__category")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "page_title": "Merchant feed metadata",
                "page_kind": "product_metadata",
                "create_url_name": "staff_growth_product_metadata_create",
            }
        )
        return ctx


class ProductMetadataCreateView(GrowthFormMixin, CreateView):
    model = ProductGrowthData
    form_class = ProductGrowthDataForm
    page_title = "Add Merchant Center product metadata"
    cancel_url_name = "staff_growth_product_metadata"
    success_url = reverse_lazy("staff_growth_product_metadata")

    def form_valid(self, form):
        messages.success(self.request, "Product feed metadata created.")
        return super().form_valid(form)


class ProductMetadataUpdateView(GrowthFormMixin, UpdateView):
    model = ProductGrowthData
    form_class = ProductGrowthDataForm
    page_title = "Edit Merchant Center product metadata"
    cancel_url_name = "staff_growth_product_metadata"
    success_url = reverse_lazy("staff_growth_product_metadata")

    def form_valid(self, form):
        messages.success(self.request, "Product feed metadata updated.")
        return super().form_valid(form)


class DistributionGroupListView(StaffRequiredMixin, ListView):
    model = DistributionGroup
    template_name = "growth/list.html"
    context_object_name = "items"
    paginate_by = 40

    def get_queryset(self):
        return DistributionGroup.objects.select_related("tracking_link")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "page_title": "Distribution groups directory",
                "page_kind": "distribution_groups",
                "create_url_name": "staff_growth_distribution_create",
            }
        )
        return ctx


class DistributionGroupCreateView(CreatedByMixin, GrowthFormMixin, CreateView):
    model = DistributionGroup
    form_class = DistributionGroupForm
    page_title = "Add distribution group"
    cancel_url_name = "staff_growth_distribution_groups"
    success_url = reverse_lazy("staff_growth_distribution_groups")
    success_message = "Distribution group added."


class DistributionGroupUpdateView(CreatedByMixin, GrowthFormMixin, UpdateView):
    model = DistributionGroup
    form_class = DistributionGroupForm
    page_title = "Edit distribution group"
    cancel_url_name = "staff_growth_distribution_groups"
    success_url = reverse_lazy("staff_growth_distribution_groups")
    success_message = "Distribution group updated."


class AmbassadorListView(StaffRequiredMixin, ListView):
    model = Ambassador
    template_name = "growth/list.html"
    context_object_name = "items"
    paginate_by = 40

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "page_title": "Referral ambassadors",
                "page_kind": "ambassadors",
                "create_url_name": "staff_growth_ambassador_create",
            }
        )
        return ctx


class AmbassadorCreateView(CreatedByMixin, GrowthFormMixin, CreateView):
    model = Ambassador
    form_class = AmbassadorForm
    page_title = "Add referral ambassador"
    cancel_url_name = "staff_growth_ambassadors"
    success_url = reverse_lazy("staff_growth_ambassadors")
    success_message = "Ambassador created."


class AmbassadorUpdateView(CreatedByMixin, GrowthFormMixin, UpdateView):
    model = Ambassador
    form_class = AmbassadorForm
    page_title = "Edit referral ambassador"
    cancel_url_name = "staff_growth_ambassadors"
    success_url = reverse_lazy("staff_growth_ambassadors")
    success_message = "Ambassador updated."


class SavedCartListView(StaffRequiredMixin, ListView):
    model = SavedCart
    template_name = "growth/list.html"
    context_object_name = "items"
    paginate_by = 40

    def get_queryset(self):
        return SavedCart.objects.select_related("recovered_order")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "page_title": "Saved and abandoned carts",
                "page_kind": "saved_carts",
                "create_url_name": "",
            }
        )
        return ctx


class StockAlertListView(StaffRequiredMixin, ListView):
    model = StockAlertSubscription
    template_name = "growth/list.html"
    context_object_name = "items"
    paginate_by = 40

    def get_queryset(self):
        return StockAlertSubscription.objects.select_related("product")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "page_title": "Back-in-stock and price alerts",
                "page_kind": "stock_alerts",
                "create_url_name": "",
            }
        )
        return ctx


class AmbassadorConversionListView(StaffRequiredMixin, ListView):
    model = AmbassadorConversion
    template_name = "growth/list.html"
    context_object_name = "items"
    paginate_by = 40

    def get_queryset(self):
        queryset = AmbassadorConversion.objects.select_related("ambassador", "order", "approved_by", "paid_by")
        status = self.request.GET.get("status", "").strip()
        if status in dict(AmbassadorConversion.STATUS_CHOICES):
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "page_title": "Ambassador conversions and commissions",
                "page_kind": "ambassador_conversions",
                "create_url_name": "",
                "commission_totals": AmbassadorConversion.objects.aggregate(
                    pending=Sum("commission_amount", filter=Q(status=AmbassadorConversion.STATUS_PENDING)),
                    approved=Sum("commission_amount", filter=Q(status=AmbassadorConversion.STATUS_APPROVED)),
                    paid=Sum("commission_amount", filter=Q(status=AmbassadorConversion.STATUS_PAID)),
                ),
                "selected_status": self.request.GET.get("status", ""),
            }
        )
        return ctx


class AmbassadorConversionApproveView(StaffRequiredMixin, View):
    def post(self, request, pk):
        conversion = get_object_or_404(AmbassadorConversion, pk=pk)
        try:
            approve_ambassador_conversion(conversion, actor=request.user)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, f"Commission approved for {conversion.ambassador.name}.")
        return redirect("staff_growth_ambassador_conversions")


class AmbassadorConversionPayView(StaffRequiredMixin, View):
    def post(self, request, pk):
        conversion = get_object_or_404(AmbassadorConversion, pk=pk)
        try:
            result = pay_ambassador_conversion(conversion, actor=request.user, payout_reference=request.POST.get("payout_reference", ""))
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, f"Ambassador payment recorded: {result.payout_reference}.")
        return redirect("staff_growth_ambassador_conversions")


def content_asset_workspace(request):
    form = ContentAssetGeneratorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        assets = generate_content_assets(
            product=form.cleaned_data["product"],
            campaign=form.cleaned_data.get("campaign"),
            created_by=request.user,
        )
        requested = set(form.cleaned_data.get("asset_types") or [])
        if requested:
            for asset in assets:
                if asset.asset_type not in requested:
                    asset.delete()
        messages.success(request, "Content asset pack generated.")
        return redirect("staff_growth_content_assets")
    assets = ContentAsset.objects.select_related("product", "campaign")[:60]
    return render(
        request,
        "growth/content_assets.html",
        {"form": form, "assets": assets},
    )


def _staff(user):
    return user.is_authenticated and user.is_staff


@user_passes_test(_staff)
def ambassador_qr(request, pk):
    ambassador = get_object_or_404(Ambassador, pk=pk)
    referral_url = request.build_absolute_uri(ambassador.get_referral_path())
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2)
    qr.add_data(referral_url)
    qr.make(fit=True)
    image = qr.make_image(image_factory=SvgPathImage)
    output = BytesIO()
    image.save(output)
    response = HttpResponse(output.getvalue(), content_type="image/svg+xml")
    response["Content-Disposition"] = (
        f'attachment; filename="leosoft-ambassador-{ambassador.code}.svg"'
    )
    return response


@require_POST
def save_cart(request):
    if not list(cart_mod.iter_cart_lines(request.session)):
        messages.error(request, "Add an item before saving your cart.")
        return redirect("cart")
    form = SavedCartOptInForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a valid email and accept the reminder consent.")
        return redirect("cart")
    saved = save_cart_for_recovery(
        request,
        name=form.cleaned_data.get("name") or "",
        email=form.cleaned_data["email"],
        phone=form.cleaned_data.get("phone") or "",
    )
    try:
        send_saved_cart_message(saved, reminder_number=0)
        messages.success(
            request,
            "Your cart was saved and the recovery link was emailed to you.",
        )
    except Exception:
        messages.warning(
            request,
            "Your cart was saved, but the email could not be sent. "
            "Check the website email settings.",
        )
    return redirect("cart")


def recover_saved_cart(request, token):
    saved = get_object_or_404(SavedCart, recovery_token=token)
    if saved.status == SavedCart.STATUS_UNSUBSCRIBED:
        messages.info(request, "This saved-cart link was unsubscribed.")
        return redirect("product_list")
    restore_saved_cart(request, saved)
    saved.last_activity = timezone.now()
    saved.save(update_fields=["last_activity", "updated_at"])
    messages.success(request, "Your saved cart has been restored.")
    return redirect("cart")


def unsubscribe_saved_cart(request, token):
    saved = get_object_or_404(SavedCart, recovery_token=token)
    saved.status = SavedCart.STATUS_UNSUBSCRIBED
    saved.save(update_fields=["status", "updated_at"])
    messages.success(request, "Cart reminder emails have been stopped.")
    return redirect("home")


@require_POST
def subscribe_stock_alert(request, slug):
    product = get_object_or_404(
        Product,
        slug=slug,
        is_published=True,
        kind=Product.KIND_PHYSICAL,
    )
    if not GrowthSettings.load().back_in_stock_enabled:
        messages.info(request, "Product alerts are not currently enabled.")
        return redirect(product.get_absolute_url())
    form = StockAlertForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Check the alert details and try again.")
        return redirect(product.get_absolute_url())
    alert_type = form.cleaned_data["alert_type"]
    if (
        alert_type == StockAlertSubscription.ALERT_BACK_IN_STOCK
        and product.available_to_sell
    ):
        messages.info(request, "This product is already available to order.")
        return redirect(product.get_absolute_url())
    subscription, created = StockAlertSubscription.objects.update_or_create(
        product=product,
        email=form.cleaned_data["email"],
        alert_type=alert_type,
        defaults={
            "phone": form.cleaned_data.get("phone") or "",
            "target_price": form.cleaned_data.get("target_price"),
            "is_active": True,
            "notified_at": None,
        },
    )
    messages.success(
        request,
        "Alert created." if created else "Your existing alert was updated.",
    )
    return redirect(product.get_absolute_url())


def unsubscribe_stock_alert(request, token):
    subscription = get_object_or_404(StockAlertSubscription, token=token)
    subscription.is_active = False
    subscription.save(update_fields=["is_active"])
    messages.success(request, "Product alert stopped.")
    return redirect(subscription.product.get_absolute_url())


def ambassador_referral(request, code):
    ambassador = get_object_or_404(Ambassador, code=code, is_active=True)
    if not request.session.session_key:
        request.session.create()
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get(
        "REMOTE_ADDR", ""
    )
    ip_hash = (
        hashlib.sha256(f"{settings.SECRET_KEY}:{ip}".encode()).hexdigest()
        if ip
        else ""
    )
    AmbassadorClick.objects.create(
        ambassador=ambassador,
        session_key=request.session.session_key or "",
        ip_hash=ip_hash,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
        referrer=request.META.get("HTTP_REFERER", ""),
    )
    Ambassador.objects.filter(pk=ambassador.pk).update(
        click_count=F("click_count") + 1
    )
    source = f"ambassador:{ambassador.code}"[:60]
    request.session[AMBASSADOR_SESSION_KEY] = ambassador.code
    request.session["marketing_attribution"] = {
        "source": source,
        "medium": "referral",
        "campaign": f"ambassador-{ambassador.code}",
        "content": ambassador.code,
        "clicked_at": timezone.now().isoformat(),
    }
    request.session.modified = True

    destination = ambassador.destination_url or request.build_absolute_uri(
        reverse("product_list")
    )
    parts = urlsplit(destination)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(
        {
            "utm_source": f"ambassador_{ambassador.code}",
            "utm_medium": "referral",
            "utm_campaign": "ambassador_program",
            "utm_content": ambassador.code,
        }
    )
    return redirect(
        urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )
    )
