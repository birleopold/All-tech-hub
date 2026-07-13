import csv
import hashlib
from io import BytesIO
from xml.etree import ElementTree as ET

import qrcode
from qrcode.image.svg import SvgPathImage
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import F, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from catalog.models import Product
from core.mixins import StaffRequiredMixin
from marketing.forms import (
    CampaignLinkForm,
    CaptionTemplateForm,
    MarketingCampaignForm,
    MarketingLeadForm,
    ScheduledPostForm,
)
from marketing.models import (
    CampaignClick,
    CampaignLink,
    CaptionTemplate,
    MarketingCampaign,
    MarketingLead,
    ScheduledPost,
    SocialProfileSettings,
)


class MarketingDashboardView(StaffRequiredMixin, TemplateView):
    template_name = "marketing/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        now = timezone.now()
        thirty_days_ago = now - timezone.timedelta(days=30)
        clicks_30d = CampaignClick.objects.filter(
            occurred_at__gte=thirty_days_ago
        ).count()
        leads_30d = MarketingLead.objects.filter(created_at__gte=thirty_days_ago).count()

        ctx.update(
            {
                "active_campaigns": MarketingCampaign.objects.filter(
                    status=MarketingCampaign.STATUS_ACTIVE
                ).count(),
                "scheduled_posts": ScheduledPost.objects.filter(
                    status=ScheduledPost.STATUS_SCHEDULED
                ).count(),
                "ready_posts": ScheduledPost.objects.filter(
                    status=ScheduledPost.STATUS_READY
                ).count(),
                "clicks_30d": clicks_30d,
                "leads_30d": leads_30d,
                "conversion_rate": round((leads_30d / clicks_30d) * 100, 1)
                if clicks_30d
                else 0,
                "upcoming_posts": ScheduledPost.objects.select_related(
                    "campaign", "product"
                )
                .filter(
                    status__in=(
                        ScheduledPost.STATUS_SCHEDULED,
                        ScheduledPost.STATUS_READY,
                    )
                )
                .order_by("scheduled_for", "created_at")[:8],
                "recent_leads": MarketingLead.objects.select_related(
                    "campaign", "product", "assigned_to"
                )[:8],
                "top_links": CampaignLink.objects.select_related(
                    "campaign", "product"
                ).order_by("-click_count", "-lead_count")[:8],
                "channel_performance": CampaignLink.objects.values("source")
                .annotate(clicks=Sum("click_count"), leads=Sum("lead_count"))
                .order_by("-clicks"),
                "social_settings": SocialProfileSettings.load(),
                "feed_csv_url": self.request.build_absolute_uri(
                    reverse("marketing_product_feed_csv")
                ),
                "feed_json_url": self.request.build_absolute_uri(
                    reverse("marketing_product_feed_json")
                ),
                "feed_xml_url": self.request.build_absolute_uri(
                    reverse("marketing_product_feed_xml")
                ),
            }
        )
        return ctx


class CreatedByFormMixin:
    def form_valid(self, form):
        if hasattr(form.instance, "created_by") and not form.instance.created_by_id:
            form.instance.created_by = self.request.user
        messages.success(self.request, self.success_message)
        return super().form_valid(form)


class MarketingListMixin(StaffRequiredMixin):
    template_name = "marketing/list.html"
    paginate_by = 30
    page_title = "Marketing"
    page_kind = ""
    create_url_name = ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "page_title": self.page_title,
                "page_kind": self.page_kind,
                "create_url_name": self.create_url_name,
            }
        )
        return ctx


class MarketingFormMixin(StaffRequiredMixin):
    template_name = "marketing/form.html"
    page_title = "Marketing item"
    cancel_url_name = "staff_marketing_dashboard"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "page_title": self.page_title,
                "cancel_url_name": self.cancel_url_name,
            }
        )
        return ctx


class CampaignListView(MarketingListMixin, ListView):
    model = MarketingCampaign
    page_title = "Campaigns"
    page_kind = "campaigns"
    create_url_name = "staff_marketing_campaign_create"


class CampaignCreateView(CreatedByFormMixin, MarketingFormMixin, CreateView):
    model = MarketingCampaign
    form_class = MarketingCampaignForm
    page_title = "Create campaign"
    cancel_url_name = "staff_marketing_campaigns"
    success_url = reverse_lazy("staff_marketing_campaigns")
    success_message = "Campaign created."


class CampaignUpdateView(CreatedByFormMixin, MarketingFormMixin, UpdateView):
    model = MarketingCampaign
    form_class = MarketingCampaignForm
    page_title = "Edit campaign"
    cancel_url_name = "staff_marketing_campaigns"
    success_url = reverse_lazy("staff_marketing_campaigns")
    success_message = "Campaign updated."


class CaptionListView(MarketingListMixin, ListView):
    model = CaptionTemplate
    page_title = "Reusable captions"
    page_kind = "captions"
    create_url_name = "staff_marketing_caption_create"


class CaptionCreateView(CreatedByFormMixin, MarketingFormMixin, CreateView):
    model = CaptionTemplate
    form_class = CaptionTemplateForm
    page_title = "Create caption template"
    cancel_url_name = "staff_marketing_captions"
    success_url = reverse_lazy("staff_marketing_captions")
    success_message = "Caption template created."


class CaptionUpdateView(CreatedByFormMixin, MarketingFormMixin, UpdateView):
    model = CaptionTemplate
    form_class = CaptionTemplateForm
    page_title = "Edit caption template"
    cancel_url_name = "staff_marketing_captions"
    success_url = reverse_lazy("staff_marketing_captions")
    success_message = "Caption template updated."


class LinkListView(MarketingListMixin, ListView):
    model = CampaignLink
    page_title = "Campaign links and QR codes"
    page_kind = "links"
    create_url_name = "staff_marketing_link_create"

    def get_queryset(self):
        return super().get_queryset().select_related("campaign", "product")


class LinkCreateView(CreatedByFormMixin, MarketingFormMixin, CreateView):
    model = CampaignLink
    form_class = CampaignLinkForm
    page_title = "Create tracked link"
    cancel_url_name = "staff_marketing_links"
    success_url = reverse_lazy("staff_marketing_links")
    success_message = "Tracked link created."


class LinkUpdateView(CreatedByFormMixin, MarketingFormMixin, UpdateView):
    model = CampaignLink
    form_class = CampaignLinkForm
    page_title = "Edit tracked link"
    cancel_url_name = "staff_marketing_links"
    success_url = reverse_lazy("staff_marketing_links")
    success_message = "Tracked link updated."


class PostListView(MarketingListMixin, ListView):
    model = ScheduledPost
    page_title = "Scheduled posts"
    page_kind = "posts"
    create_url_name = "staff_marketing_post_create"

    def get_queryset(self):
        return super().get_queryset().select_related("campaign", "product")


class PostCreateView(CreatedByFormMixin, MarketingFormMixin, CreateView):
    model = ScheduledPost
    form_class = ScheduledPostForm
    page_title = "Create scheduled post"
    cancel_url_name = "staff_marketing_posts"
    success_url = reverse_lazy("staff_marketing_posts")
    success_message = "Marketing post saved."


class PostUpdateView(CreatedByFormMixin, MarketingFormMixin, UpdateView):
    model = ScheduledPost
    form_class = ScheduledPostForm
    page_title = "Edit scheduled post"
    cancel_url_name = "staff_marketing_posts"
    success_url = reverse_lazy("staff_marketing_posts")
    success_message = "Marketing post updated."


class LeadListView(MarketingListMixin, ListView):
    model = MarketingLead
    page_title = "Marketing leads"
    page_kind = "leads"
    create_url_name = "staff_marketing_lead_create"

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "campaign", "link", "product", "assigned_to"
        )
        status = self.request.GET.get("status")
        source = self.request.GET.get("source")
        if status:
            qs = qs.filter(status=status)
        if source:
            qs = qs.filter(source=source)
        return qs


class LeadCreateView(MarketingFormMixin, CreateView):
    model = MarketingLead
    form_class = MarketingLeadForm
    page_title = "Add marketing lead"
    cancel_url_name = "staff_marketing_leads"
    success_url = reverse_lazy("staff_marketing_leads")

    def form_valid(self, form):
        messages.success(self.request, "Lead added.")
        return super().form_valid(form)


class LeadUpdateView(MarketingFormMixin, UpdateView):
    model = MarketingLead
    form_class = MarketingLeadForm
    page_title = "Update marketing lead"
    cancel_url_name = "staff_marketing_leads"
    success_url = reverse_lazy("staff_marketing_leads")

    def form_valid(self, form):
        messages.success(self.request, "Lead updated.")
        return super().form_valid(form)


def _staff(user):
    return user.is_authenticated and user.is_staff


@user_passes_test(_staff)
def mark_post_published(request, pk):
    if request.method != "POST":
        return redirect("staff_marketing_posts")
    post = get_object_or_404(ScheduledPost, pk=pk)
    post.status = ScheduledPost.STATUS_PUBLISHED
    post.published_at = timezone.now()
    post.save(update_fields=["status", "published_at", "updated_at"])
    messages.success(request, "Post marked as published.")
    return redirect("staff_marketing_posts")


@user_passes_test(_staff)
def campaign_link_qr(request, pk):
    link = get_object_or_404(CampaignLink, pk=pk)
    tracking_url = request.build_absolute_uri(link.get_tracking_path())
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2)
    qr.add_data(tracking_url)
    qr.make(fit=True)
    image = qr.make_image(image_factory=SvgPathImage)
    output = BytesIO()
    image.save(output)
    response = HttpResponse(output.getvalue(), content_type="image/svg+xml")
    response["Content-Disposition"] = (
        f'attachment; filename="leosoft-{link.code}-qr.svg"'
    )
    return response


def track_campaign_link(request, code):
    link = get_object_or_404(
        CampaignLink.objects.select_related("campaign", "product"), code=code
    )
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
    now = timezone.now()
    CampaignLink.objects.filter(pk=link.pk).update(
        click_count=F("click_count") + 1, last_clicked_at=now
    )
    CampaignClick.objects.create(
        link=link,
        session_key=request.session.session_key or "",
        ip_hash=ip_hash,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
        referrer=request.META.get("HTTP_REFERER", ""),
    )
    request.session["marketing_attribution"] = {
        "source": link.source,
        "medium": link.medium,
        "campaign": link.campaign.slug if link.campaign else "leosoft",
        "content": link.content or (link.product.slug if link.product else link.code),
        "link_id": link.pk,
    }
    return redirect(link.destination_with_utm())


def _feed_products():
    return (
        Product.objects.filter(is_published=True)
        .select_related("category")
        .prefetch_related("gallery_images", "variants")
        .order_by("name")
    )


def _product_feed_row(request, product):
    image = product.primary_display_image
    price = product.min_active_variant_price or product.price
    return {
        "id": product.sku or str(product.pk),
        "title": product.name,
        "description": product.short_description or product.description,
        "availability": "in stock" if product.available_to_sell else "out of stock",
        "condition": "new",
        "price": f"{price}",
        "currency": "UGX",
        "link": request.build_absolute_uri(product.get_absolute_url()),
        "image_link": request.build_absolute_uri(image.url) if image else "",
        "category": product.category.name,
        "type": product.kind,
    }


def product_feed_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="leosoft-products.csv"'
    fields = [
        "id",
        "title",
        "description",
        "availability",
        "condition",
        "price",
        "currency",
        "link",
        "image_link",
        "category",
        "type",
    ]
    writer = csv.DictWriter(response, fieldnames=fields)
    writer.writeheader()
    for product in _feed_products():
        writer.writerow(_product_feed_row(request, product))
    return response


def product_feed_json(request):
    rows = [_product_feed_row(request, product) for product in _feed_products()]
    return JsonResponse({"store": "LEOSOFT UG LTD", "products": rows})


def product_feed_xml(request):
    ET.register_namespace("g", "http://base.google.com/ns/1.0")
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "LEOSOFT UG LTD product feed"
    ET.SubElement(channel, "link").text = request.build_absolute_uri("/")
    ET.SubElement(channel, "description").text = "Published LEOSOFT products and services"
    namespace = "{http://base.google.com/ns/1.0}"
    for product in _feed_products():
        row = _product_feed_row(request, product)
        item = ET.SubElement(channel, "item")
        for key in (
            "id",
            "title",
            "description",
            "availability",
            "condition",
            "link",
            "image_link",
        ):
            ET.SubElement(item, f"{namespace}{key}").text = str(row[key])
        ET.SubElement(item, f"{namespace}price").text = (
            f"{row['price']} {row['currency']}"
        )
        ET.SubElement(item, f"{namespace}product_type").text = row["category"]
    return HttpResponse(
        ET.tostring(rss, encoding="utf-8", xml_declaration=True),
        content_type="application/xml",
    )
