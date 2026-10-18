"""Manage the public homepage without modifying templates or pricing."""
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from catalog.models import Product
from core.audit import log_audit_event
from merchandising.models import HomepagePromotion


class HomepagePromotionForm(forms.ModelForm):
    class Meta:
        model = HomepagePromotion
        fields = (
            "slot", "eyebrow", "headline", "supporting_text",
            "button_label", "link_path", "product", "creative_image",
            "image_alt", "start_at", "end_at", "priority", "is_active",
        )
        widgets = {
            "start_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "end_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["end_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["product"].queryset = Product.objects.filter(
            is_published=True, kind=Product.KIND_PHYSICAL
        ).order_by("name")
        for name, field in self.fields.items():
            widget = field.widget
            widget.attrs["class"] = (
                "form-check-input" if isinstance(widget, forms.CheckboxInput)
                else "form-select" if isinstance(widget, forms.Select)
                else "form-control"
            )


def _authorised(user):
    return bool(
        user.is_authenticated
        and user.is_staff
        and (
            user.is_superuser
            or user.has_perm("merchandising.change_homepagepromotion")
            or user.has_perm("marketing.change_scheduledpost")
        )
    )


@require_http_methods(["GET", "POST"])
def staff_homepage_promotions(request, pk=None):
    if not _authorised(request.user):
        raise PermissionDenied
    promotion = get_object_or_404(HomepagePromotion, pk=pk) if pk else None
    form = HomepagePromotionForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
        instance=promotion,
    )
    if request.method == "POST" and form.is_valid():
        edited = form.save()
        log_audit_event(
            actor=request.user,
            verb="storefront.promotion_saved",
            summary=f"Homepage {edited.get_slot_display()} campaign updated: {edited.headline}",
            target=edited,
        )
        messages.success(request, "Homepage campaign saved. Active campaigns appear within their scheduled dates.")
        return redirect("staff_homepage_promotions")
    campaigns = HomepagePromotion.objects.select_related("product").order_by(
        "slot", "-priority", "-updated_at"
    )
    return render(request, "dashboard/homepage_promotions.html", {
        "form": form,
        "promotion": promotion,
        "campaigns": campaigns,
        "public_preview_url": "/",
        "form_heading": "Edit campaign" if promotion else "Add homepage campaign",
    })
