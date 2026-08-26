from __future__ import annotations

from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from automation.models import PostAutomationPlan, SocialAutopilotSettings
from automation.services import configure_post_plan
from catalog.models import Product
from core.models import CompanySettings
from growth.services import absolute_public_url
from marketing.models import CampaignLink, ScheduledPost
from marketing.services import product_public_url

SUPPORTED_CHANNELS = {
    "facebook",
    "instagram",
    "telegram",
}
AUTOPILOT_MARKER = "[social-autopilot]"


def _posting_hours(settings_row: SocialAutopilotSettings) -> list[int]:
    values = []
    for value in settings_row.posting_hours or [9]:
        try:
            hour = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= hour <= 23 and hour not in values:
            values.append(hour)
    return sorted(values or [9])[: max(1, min(settings_row.posts_per_day, 4))]


def _candidate_products(settings_row, *, cutoff, used_ids):
    queryset = (
        Product.objects.filter(is_published=True)
        .select_related("category")
        .prefetch_related("gallery_images", "variants")
        .annotate(
            autopilot_clicks=Sum("marketing_links__click_count"),
            autopilot_leads=Sum("marketing_links__lead_count"),
        )
        .exclude(pk__in=used_ids)
        .order_by(
            "-is_featured",
            "-autopilot_leads",
            "-autopilot_clicks",
            "-updated_at",
            "pk",
        )
    )
    recently_posted = ScheduledPost.objects.filter(
        product_id__isnull=False,
        scheduled_for__gte=cutoff,
    ).exclude(
        status=ScheduledPost.STATUS_CANCELLED
    ).values_list("product_id", flat=True)
    queryset = queryset.exclude(pk__in=recently_posted)
    for product in queryset:
        if not product.primary_display_image:
            continue
        if settings_row.require_in_stock and not product.available_to_sell:
            continue
        if not (product.short_description or product.description):
            continue
        yield product


def _choose_product(settings_row, *, cutoff, used_ids):
    if settings_row.preferred_product_id:
        product = (
            Product.objects.filter(
                pk=settings_row.preferred_product_id,
                is_published=True,
            )
            .select_related("category")
            .prefetch_related("gallery_images", "variants")
            .first()
        )
        if (
            product
            and product.primary_display_image
            and (
                not settings_row.require_in_stock
                or product.available_to_sell
            )
        ):
            return product, True
    return next(
        _candidate_products(settings_row, cutoff=cutoff, used_ids=used_ids),
        None,
    ), False


def _content_style(product, slot) -> str:
    if product.kind == Product.KIND_SERVICE:
        return "service"
    styles = ("spotlight", "availability", "benefit")
    return styles[(slot.toordinal() + slot.hour) % len(styles)]


def _caption(product, channel: str, link_url: str, settings_row, *, style="spotlight") -> str:
    company = CompanySettings.load()
    currency = company.currency_code or "UGX"
    price = product.min_active_variant_price or product.price
    description = (product.short_description or product.description).strip()
    description = " ".join(description.split())[:220]
    price_line = (
        f" Price: {currency} {price:,.0f}." if settings_row.include_prices else ""
    )
    hashtags = (settings_row.default_hashtags or "").strip()
    if style == "availability":
        opening = f"Now available: {product.name}."
    elif style == "benefit":
        opening = f"Upgrade your setup with {product.name}."
    elif style == "service":
        opening = f"Need dependable {product.name}?"
    else:
        opening = f"Product spotlight: {product.name}."

    if channel == "instagram":
        return (
            f"{opening}\n\n{description}{price_line}\n\n"
            f"Available from {company.company_name}. Visit {link_url}\n\n{hashtags}"
        ).strip()
    if channel == "telegram":
        return (
            f"{opening}\n\n{description}{price_line}\n\n"
            f"View details or request a quotation: {link_url}\n\n{hashtags}"
        ).strip()
    return (
        f"{opening} {description}{price_line}\n\n"
        f"View full details and request a quotation from {company.company_name}: "
        f"{link_url}\n\n{hashtags}"
    ).strip()


def _slot_datetime(day, hour):
    naive = datetime.combine(day, time(hour=hour))
    return timezone.make_aware(naive, timezone.get_current_timezone())


@transaction.atomic
def reconcile_autopilot_state(settings_row: SocialAutopilotSettings, *, now=None) -> dict:
    from automation.services import cancel_post_automation

    now = now or timezone.now()
    posts = list(
        ScheduledPost.objects.select_for_update()
        .filter(
            notes__startswith=AUTOPILOT_MARKER,
            status__in=[
                ScheduledPost.STATUS_DRAFT,
                ScheduledPost.STATUS_SCHEDULED,
                ScheduledPost.STATUS_READY,
            ],
        )
        .filter(scheduled_for__gte=now)
        .order_by("scheduled_for", "pk")
    )
    changed = 0
    for post in posts:
        if not settings_row.enabled:
            cancel_post_automation(post)
            post.status = ScheduledPost.STATUS_CANCELLED
            post.save(update_fields=["status", "updated_at"])
            changed += 1
        elif settings_row.mode == SocialAutopilotSettings.MODE_CONTROLLED:
            cancel_post_automation(post)
            post.status = ScheduledPost.STATUS_DRAFT
            post.save(update_fields=["status", "updated_at"])
            configure_post_plan(post, mode=PostAutomationPlan.MODE_MANUAL)
            changed += 1
        else:
            post.status = ScheduledPost.STATUS_SCHEDULED
            post.save(update_fields=["status", "updated_at"])
            configure_post_plan(post, mode=PostAutomationPlan.MODE_AUTOMATIC)
            changed += 1
    return {"changed": changed, "enabled": settings_row.enabled, "mode": settings_row.mode}


@transaction.atomic
def generate_autopilot_calendar(*, now=None) -> dict:
    now = now or timezone.now()
    settings_row = SocialAutopilotSettings.objects.select_for_update().filter(
        singleton_key="primary"
    ).first()
    if settings_row is None or not settings_row.enabled:
        return {"enabled": False, "created": 0, "reason": "disabled"}

    channels = [
        channel
        for channel in (settings_row.channels or [])
        if channel in SUPPORTED_CHANNELS
    ]
    if not channels:
        settings_row.last_error = "Select at least one supported publishing channel."
        settings_row.last_generated_at = now
        settings_row.save(
            update_fields=["last_error", "last_generated_at", "updated_at"]
        )
        return {"enabled": True, "created": 0, "reason": "no_channels"}

    hours = _posting_hours(settings_row)
    horizon = max(1, min(int(settings_row.queue_days), 14))
    cooldown = max(1, min(int(settings_row.product_cooldown_days), 90))
    cutoff = now - timedelta(days=cooldown)
    used_ids = set()
    created = 0
    preferred_consumed = False

    for offset in range(horizon):
        day = timezone.localdate(now) + timedelta(days=offset)
        for hour in hours:
            slot = _slot_datetime(day, hour)
            if slot <= now:
                continue
            slot_key = f"{AUTOPILOT_MARKER}:{slot:%Y%m%d%H}"
            if ScheduledPost.objects.filter(notes__startswith=slot_key).exclude(
                status=ScheduledPost.STATUS_CANCELLED
            ).exists():
                continue

            product, was_preferred = _choose_product(
                settings_row,
                cutoff=cutoff,
                used_ids=used_ids,
            )
            if product is None:
                continue
            used_ids.add(product.pk)
            preferred_consumed = preferred_consumed or was_preferred

            for channel in channels:
                link = CampaignLink.objects.create(
                    product=product,
                    name=f"Autopilot: {product.name} — {channel} — {slot:%Y-%m-%d}",
                    destination_url=product_public_url(product),
                    source=channel,
                    medium="organic-social",
                    content=product.slug,
                )
                tracking_url = absolute_public_url(link.get_tracking_path())
                post = ScheduledPost.objects.create(
                    product=product,
                    title=f"{product.name} — {channel.title()}",
                    caption=_caption(
                        product,
                        channel,
                        tracking_url,
                        settings_row,
                        style=_content_style(product, slot),
                    ),
                    channels=[channel],
                    status=(
                        ScheduledPost.STATUS_SCHEDULED
                        if settings_row.mode == SocialAutopilotSettings.MODE_FULL
                        else ScheduledPost.STATUS_DRAFT
                    ),
                    scheduled_for=slot,
                    notes=f"{slot_key}:{product.pk}:{channel}",
                )
                configure_post_plan(
                    post,
                    mode=(
                        PostAutomationPlan.MODE_AUTOMATIC
                        if settings_row.mode == SocialAutopilotSettings.MODE_FULL
                        else PostAutomationPlan.MODE_MANUAL
                    ),
                )
                created += 1

    if preferred_consumed:
        settings_row.preferred_product = None
    settings_row.last_generated_at = now
    settings_row.last_error = ""
    fields = ["last_generated_at", "last_error", "updated_at"]
    if preferred_consumed:
        fields.append("preferred_product")
    settings_row.save(update_fields=fields)
    return {
        "enabled": True,
        "created": created,
        "channels": channels,
        "mode": settings_row.mode,
    }


@transaction.atomic
def queue_product_promotion(product: Product, *, actor=None, now=None) -> dict:
    now = now or timezone.now()
    settings_row = SocialAutopilotSettings.objects.select_for_update().filter(
        singleton_key="primary"
    ).first()
    if settings_row is None:
        settings_row = SocialAutopilotSettings.load()
    product = (
        Product.objects.select_related("category")
        .prefetch_related("gallery_images", "variants")
        .get(pk=product.pk)
    )
    if not product.is_published:
        return {"created": 0, "error": "Publish the product before promoting it."}
    if not product.primary_display_image:
        return {"created": 0, "error": "Add a main product image before promoting it."}
    if not (product.short_description or product.description):
        return {"created": 0, "error": "Add a product description before promoting it."}
    if settings_row.require_in_stock and not product.available_to_sell:
        return {"created": 0, "error": "This product is not currently available to sell."}

    channels = [
        channel
        for channel in (settings_row.channels or [])
        if channel in SUPPORTED_CHANNELS
    ]
    if not channels:
        return {"created": 0, "error": "Select at least one social channel first."}

    full = bool(
        settings_row.enabled
        and settings_row.mode == SocialAutopilotSettings.MODE_FULL
    )
    slot = now + timedelta(minutes=5)
    marker = f"[social-priority]:{slot:%Y%m%d%H%M}:{product.pk}"
    created = 0
    for channel in channels:
        link = CampaignLink.objects.create(
            product=product,
            name=f"Priority: {product.name} — {channel} — {slot:%Y-%m-%d}",
            destination_url=product_public_url(product),
            source=channel,
            medium="priority-organic-social",
            content=product.slug,
            created_by=actor,
        )
        tracking_url = absolute_public_url(link.get_tracking_path())
        post = ScheduledPost.objects.create(
            product=product,
            title=f"Priority: {product.name} — {channel.title()}",
            caption=_caption(
                product,
                channel,
                tracking_url,
                settings_row,
                style=_content_style(product, slot),
            ),
            channels=[channel],
            status=(
                ScheduledPost.STATUS_SCHEDULED
                if full
                else ScheduledPost.STATUS_DRAFT
            ),
            scheduled_for=slot,
            notes=f"{marker}:{channel}",
            created_by=actor,
        )
        configure_post_plan(
            post,
            mode=(
                PostAutomationPlan.MODE_AUTOMATIC
                if full
                else PostAutomationPlan.MODE_MANUAL
            ),
        )
        created += 1
    return {"created": created, "scheduled_for": slot, "automatic": full}


@transaction.atomic
def rebuild_autopilot_calendar(*, now=None) -> dict:
    now = now or timezone.now()
    settings_row = SocialAutopilotSettings.objects.select_for_update().filter(
        singleton_key="primary"
    ).first()
    if settings_row is None:
        return {"cancelled": 0, "created": 0}
    posts = list(
        ScheduledPost.objects.select_for_update().filter(
            notes__startswith=AUTOPILOT_MARKER,
            scheduled_for__gte=now,
            status__in=[
                ScheduledPost.STATUS_DRAFT,
                ScheduledPost.STATUS_SCHEDULED,
                ScheduledPost.STATUS_READY,
            ],
        )
    )
    from automation.services import cancel_post_automation

    for post in posts:
        cancel_post_automation(post)
        post.status = ScheduledPost.STATUS_CANCELLED
        post.save(update_fields=["status", "updated_at"])
    generated = (
        generate_autopilot_calendar(now=now)
        if settings_row.enabled
        else {"created": 0}
    )
    return {"cancelled": len(posts), "created": generated.get("created", 0)}


def autopilot_readiness(settings_row: SocialAutopilotSettings, *, now=None) -> dict:
    """Return actionable queue coverage and channel preflight information."""
    from automation.connectors import channel_is_configured

    now = now or timezone.now()
    selected_channels = [
        channel
        for channel in (settings_row.channels or [])
        if channel in SUPPORTED_CHANNELS
    ]
    channel_status = {
        channel: channel_is_configured(channel) for channel in selected_channels
    }
    cooldown = max(1, min(int(settings_row.product_cooldown_days), 90))
    eligible_products = sum(
        1
        for _product in _candidate_products(
            settings_row,
            cutoff=now - timedelta(days=cooldown),
            used_ids=set(),
        )
    )
    open_posts = ScheduledPost.objects.filter(
        notes__startswith=AUTOPILOT_MARKER,
        scheduled_for__gte=now,
        status__in=[
            ScheduledPost.STATUS_DRAFT,
            ScheduledPost.STATUS_SCHEDULED,
            ScheduledPost.STATUS_READY,
        ],
    )
    queued_posts = open_posts.count()
    covered_days = open_posts.dates("scheduled_for", "day").count()
    expected_posts = (
        len(_posting_hours(settings_row))
        * max(1, min(int(settings_row.queue_days), 14))
        * len(selected_channels)
    )
    issues = []
    if not selected_channels:
        issues.append("No publishing channels are selected.")
    unconfigured = [
        channel.title() for channel, configured in channel_status.items() if not configured
    ]
    if unconfigured:
        issues.append(
            "Automatic publishing needs credentials for: " + ", ".join(unconfigured) + "."
        )
    if eligible_products == 0:
        issues.append(
            "No eligible products currently have an image, description, publication status "
            "and required stock."
        )
    if settings_row.enabled and queued_posts == 0:
        issues.append("Autopilot is running but has no upcoming posts.")
    return {
        "selected_channels": selected_channels,
        "channel_status": channel_status,
        "eligible_products": eligible_products,
        "queued_posts": queued_posts,
        "covered_days": covered_days,
        "expected_posts": expected_posts,
        "issues": issues,
        "ready": bool(settings_row.enabled and not issues),
    }


@transaction.atomic
def publish_autopilot_post_now(post: ScheduledPost, *, actor=None, now=None) -> dict:
    """Move one automatic post to the durable queue without changing later slots."""
    now = now or timezone.now()
    post = (
        ScheduledPost.objects.select_for_update().get(pk=post.pk)
    )
    if post.status != ScheduledPost.STATUS_SCHEDULED:
        return {"queued": 0, "error": "Only an upcoming scheduled post can be published now."}

    plan = PostAutomationPlan.objects.select_for_update().filter(post=post).first()
    if plan is None or plan.mode != PostAutomationPlan.MODE_AUTOMATIC:
        return {
            "queued": 0,
            "error": "This post is waiting for manual review and cannot publish automatically.",
        }

    settings_row = SocialAutopilotSettings.load()
    if not settings_row.enabled or settings_row.mode != SocialAutopilotSettings.MODE_FULL:
        return {
            "queued": 0,
            "error": "Turn on Full autopilot before publishing an item immediately.",
        }

    original_time = post.scheduled_for
    post.scheduled_for = now
    post.save(update_fields=["scheduled_for", "updated_at"])

    from automation.services import prepare_post
    from core.audit import log_audit_event

    result = prepare_post(post, now=now)
    if not result.get("queued"):
        transaction.set_rollback(True)
        return {
            **result,
            "error": (
                "The post could not be queued automatically. "
                "Check the selected channel connection and product image."
            ),
        }

    log_audit_event(
        actor=actor,
        verb="automation.social_post_publish_now",
        summary=(
            f"Queued social post #{post.pk} immediately instead of "
            f"{original_time.isoformat() if original_time else 'an unscheduled time'}."
        ),
        target=post,
    )
    return {**result, "original_time": original_time}


@transaction.atomic
def cancel_autopilot_post(post: ScheduledPost, *, actor=None) -> dict:
    """Cancel one unpublished autopilot item without rebuilding the whole calendar."""
    from automation.services import cancel_post_automation
    from core.audit import log_audit_event

    locked = ScheduledPost.objects.select_for_update().get(pk=post.pk)
    is_autopilot = locked.notes.startswith(AUTOPILOT_MARKER) or locked.notes.startswith(
        "[social-priority]"
    )
    if not is_autopilot:
        return {"cancelled": False, "error": "Only autopilot queue items can be removed here."}
    if locked.status in {
        ScheduledPost.STATUS_PUBLISHED,
        ScheduledPost.STATUS_CANCELLED,
    }:
        return {"cancelled": False, "error": "This post is no longer in the active queue."}

    cancel_post_automation(locked)
    locked.status = ScheduledPost.STATUS_CANCELLED
    locked.save(update_fields=["status", "updated_at"])
    log_audit_event(
        actor=actor,
        verb="automation.social_post_cancelled",
        summary=f"Removed autopilot post from queue: {locked.title}",
        target=locked,
    )
    return {"cancelled": True, "post_id": locked.pk}
