from __future__ import annotations

import os
import socket
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from automation.connectors import ConnectorError, channel_is_configured, publish_social_post
from automation.models import AutomationJob, PostAutomationPlan, PostChannelDelivery
from core.audit import log_audit_event
from core.models import CompanySettings
from growth.models import GrowthSettings, SavedCart, StockAlertSubscription
from growth.services import absolute_public_url, send_saved_cart_message
from marketing.models import ScheduledPost

AUTO_CHANNELS = {"facebook", "instagram", "telegram"}
OPEN_JOB_STATUSES = {
    AutomationJob.STATUS_QUEUED,
    AutomationJob.STATUS_RUNNING,
    AutomationJob.STATUS_RETRY,
}


def configure_post_plan(post: ScheduledPost, *, mode: str, media_url: str = "") -> PostAutomationPlan:
    mode = (
        PostAutomationPlan.MODE_AUTOMATIC
        if mode == PostAutomationPlan.MODE_AUTOMATIC
        else PostAutomationPlan.MODE_MANUAL
    )
    plan, _ = PostAutomationPlan.objects.get_or_create(post=post)
    changed = plan.mode != mode or plan.media_url != (media_url or "").strip()
    plan.mode = mode
    plan.media_url = (media_url or "").strip()
    if post.status == ScheduledPost.STATUS_CANCELLED:
        plan.status = PostAutomationPlan.STATUS_CANCELLED
    elif post.status == ScheduledPost.STATUS_PUBLISHED:
        plan.status = PostAutomationPlan.STATUS_PUBLISHED
    elif changed:
        plan.status = PostAutomationPlan.STATUS_SCHEDULED
        plan.last_error = ""
    plan.save()

    if changed:
        unpublished = plan.deliveries.exclude(
            status=PostChannelDelivery.STATUS_PUBLISHED
        )
        AutomationJob.objects.filter(
            delivery__in=unpublished,
            status__in=OPEN_JOB_STATUSES,
        ).update(
            status=AutomationJob.STATUS_CANCELLED,
            completed_at=timezone.now(),
            locked_at=None,
            locked_by="",
            last_error="Post publishing settings were changed.",
        )
        unpublished.delete()
    return plan


def _public_image_url(plan: PostAutomationPlan) -> str:
    if plan.media_url:
        return plan.media_url
    post = plan.post
    if post.product_id and post.product:
        image = post.product.primary_display_image
        if image:
            return absolute_public_url(image.url)
    return ""


def _mark_manual(delivery: PostChannelDelivery, reason: str) -> None:
    if delivery.status == PostChannelDelivery.STATUS_PUBLISHED:
        return
    delivery.method = PostChannelDelivery.METHOD_MANUAL
    delivery.status = PostChannelDelivery.STATUS_MANUAL
    delivery.last_error = reason[:2000]
    delivery.next_attempt_at = None
    delivery.save(
        update_fields=[
            "method",
            "status",
            "last_error",
            "next_attempt_at",
            "updated_at",
        ]
    )


def _queue_social_delivery(delivery: PostChannelDelivery, now) -> bool:
    job, created = AutomationJob.objects.get_or_create(
        idempotency_key=f"social:{delivery.post_id}:{delivery.channel}",
        defaults={
            "job_type": AutomationJob.TYPE_SOCIAL_POST,
            "delivery": delivery,
            "payload": {
                "post_id": delivery.post_id,
                "channel": delivery.channel,
            },
            "scheduled_for": now,
            "next_attempt_at": now,
            "max_attempts": max(
                1,
                int(getattr(settings, "AUTOMATION_JOB_MAX_ATTEMPTS", 5)),
            ),
        },
    )
    if not created and job.status in {
        AutomationJob.STATUS_FAILED,
        AutomationJob.STATUS_CANCELLED,
    }:
        job.status = AutomationJob.STATUS_QUEUED
        job.next_attempt_at = now
        job.completed_at = None
        job.locked_at = None
        job.locked_by = ""
        job.last_error = ""
        job.save(
            update_fields=[
                "status",
                "next_attempt_at",
                "completed_at",
                "locked_at",
                "locked_by",
                "last_error",
                "updated_at",
            ]
        )
    delivery.method = PostChannelDelivery.METHOD_AUTOMATIC
    delivery.status = (
        PostChannelDelivery.STATUS_RETRYING
        if job.status == AutomationJob.STATUS_RETRY
        else PostChannelDelivery.STATUS_QUEUED
    )
    delivery.next_attempt_at = job.next_attempt_at
    delivery.last_error = job.last_error
    delivery.save(
        update_fields=[
            "method",
            "status",
            "next_attempt_at",
            "last_error",
            "updated_at",
        ]
    )
    return created


def update_plan_status(plan: PostAutomationPlan) -> None:
    plan = PostAutomationPlan.objects.select_related("post").get(pk=plan.pk)
    post = plan.post
    if post.status == ScheduledPost.STATUS_CANCELLED:
        plan.status = PostAutomationPlan.STATUS_CANCELLED
        plan.save(update_fields=["status", "updated_at"])
        return

    channels = {str(channel) for channel in (post.channels or []) if channel}
    deliveries = list(plan.deliveries.filter(channel__in=channels))
    if not channels:
        plan.status = PostAutomationPlan.STATUS_MANUAL
        plan.last_error = "No publishing channels were selected."
    elif not deliveries:
        plan.status = PostAutomationPlan.STATUS_SCHEDULED
        plan.last_error = ""
    else:
        statuses = {delivery.status for delivery in deliveries}
        published_count = sum(
            1 for delivery in deliveries if delivery.status == PostChannelDelivery.STATUS_PUBLISHED
        )
        errors = [delivery.last_error for delivery in deliveries if delivery.last_error]
        plan.last_error = " | ".join(errors)[:4000]
        if published_count == len(channels):
            plan.status = PostAutomationPlan.STATUS_PUBLISHED
            published_at = max(
                (delivery.published_at for delivery in deliveries if delivery.published_at),
                default=timezone.now(),
            )
            external_urls = [delivery.external_url for delivery in deliveries if delivery.external_url]
            ScheduledPost.objects.filter(pk=post.pk).update(
                status=ScheduledPost.STATUS_PUBLISHED,
                published_at=published_at,
                external_url=external_urls[0] if len(external_urls) == 1 else post.external_url,
                updated_at=timezone.now(),
            )
        elif statuses & {
            PostChannelDelivery.STATUS_RUNNING,
            PostChannelDelivery.STATUS_RETRYING,
        }:
            plan.status = PostAutomationPlan.STATUS_RUNNING
        elif PostChannelDelivery.STATUS_QUEUED in statuses:
            plan.status = PostAutomationPlan.STATUS_QUEUED
        elif published_count:
            plan.status = PostAutomationPlan.STATUS_PARTIAL
        elif statuses == {PostChannelDelivery.STATUS_MANUAL}:
            plan.status = PostAutomationPlan.STATUS_MANUAL
        elif statuses == {PostChannelDelivery.STATUS_FAILED}:
            plan.status = PostAutomationPlan.STATUS_FAILED
        elif PostChannelDelivery.STATUS_FAILED in statuses:
            plan.status = PostAutomationPlan.STATUS_FAILED
        else:
            plan.status = PostAutomationPlan.STATUS_SCHEDULED
    plan.save(update_fields=["status", "last_error", "updated_at"])


@transaction.atomic
def prepare_post(post: ScheduledPost, *, now=None) -> dict:
    now = now or timezone.now()
    post = (
        ScheduledPost.objects.select_for_update().get(pk=post.pk)
    )
    plan, _ = PostAutomationPlan.objects.select_for_update().get_or_create(post=post)
    channels = {str(channel) for channel in (post.channels or []) if channel}
    image_url = _public_image_url(plan)

    for delivery in plan.deliveries.exclude(channel__in=channels).exclude(
        status=PostChannelDelivery.STATUS_PUBLISHED
    ):
        AutomationJob.objects.filter(
            delivery=delivery,
            status__in=OPEN_JOB_STATUSES,
        ).update(
            status=AutomationJob.STATUS_CANCELLED,
            completed_at=now,
            locked_at=None,
            locked_by="",
            last_error="Channel was removed from the post.",
        )
        delivery.status = PostChannelDelivery.STATUS_CANCELLED
        delivery.last_error = "Channel was removed from the post."
        delivery.save(update_fields=["status", "last_error", "updated_at"])

    queued = manual = 0
    for channel in sorted(channels):
        delivery, _ = PostChannelDelivery.objects.get_or_create(
            plan=plan,
            post=post,
            channel=channel,
        )
        if delivery.status == PostChannelDelivery.STATUS_PUBLISHED:
            continue
        if plan.mode != PostAutomationPlan.MODE_AUTOMATIC:
            _mark_manual(delivery, "This post is configured for manual publishing.")
            manual += 1
            continue
        if channel not in AUTO_CHANNELS:
            _mark_manual(delivery, f"{channel.title()} requires manual publishing.")
            manual += 1
            continue
        if not channel_is_configured(channel):
            _mark_manual(
                delivery,
                f"{channel.title()} automatic publishing is not configured or enabled.",
            )
            manual += 1
            continue
        if channel == "instagram" and not image_url:
            _mark_manual(
                delivery,
                "Instagram requires a public HTTPS image. Select a product image or enter a media URL.",
            )
            manual += 1
            continue
        _queue_social_delivery(delivery, now)
        queued += 1

    if post.status == ScheduledPost.STATUS_SCHEDULED:
        ScheduledPost.objects.filter(pk=post.pk).update(
            status=ScheduledPost.STATUS_READY,
            updated_at=now,
        )
        post.status = ScheduledPost.STATUS_READY
    update_plan_status(plan)
    return {"queued": queued, "manual": manual}


def queue_due_posts(*, limit: int = 100, dry_run: bool = False) -> dict:
    now = timezone.now()
    autopilot = {"created": 0}
    if not dry_run:
        from automation.autopilot import generate_autopilot_calendar

        autopilot = generate_autopilot_calendar(now=now)
    ids = list(
        ScheduledPost.objects.filter(
            status=ScheduledPost.STATUS_SCHEDULED,
            scheduled_for__isnull=False,
            scheduled_for__lte=now,
        )
        .order_by("scheduled_for", "id")
        .values_list("pk", flat=True)[:limit]
    )
    if dry_run:
        return {"due": len(ids), "queued": 0, "manual": 0}
    queued = manual = 0
    for post_id in ids:
        result = prepare_post(ScheduledPost(pk=post_id), now=now)
        queued += result["queued"]
        manual += result["manual"]
    return {
        "due": len(ids),
        "queued": queued,
        "manual": manual,
        "autopilot_created": autopilot.get("created", 0),
    }


def _queue_job(*, key: str, job_type: str, payload: dict, when, max_attempts=None) -> bool:
    _job, created = AutomationJob.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "job_type": job_type,
            "payload": payload,
            "scheduled_for": when,
            "next_attempt_at": when,
            "max_attempts": max_attempts
            or max(1, int(getattr(settings, "AUTOMATION_JOB_MAX_ATTEMPTS", 5))),
        },
    )
    return created


def _stock_alert_trigger(subscription: StockAlertSubscription) -> tuple[bool, str, Decimal]:
    product = subscription.product
    price = product.min_active_variant_price or product.price
    if (
        subscription.alert_type == StockAlertSubscription.ALERT_BACK_IN_STOCK
        and product.available_to_sell
    ):
        return True, "is back in stock", price
    if (
        subscription.alert_type == StockAlertSubscription.ALERT_PRICE_DROP
        and subscription.target_price is not None
        and price <= subscription.target_price
    ):
        company = CompanySettings.load()
        return True, f"is now {company.currency_code} {price}", price
    return False, "", price


def queue_due_growth_jobs(*, limit: int = 100, dry_run: bool = False) -> dict:
    config = GrowthSettings.load()
    now = timezone.now()
    queued_cart = queued_alerts = 0

    if config.abandoned_cart_enabled:
        first_cutoff = now - timedelta(hours=config.abandoned_cart_first_delay_hours)
        second_cutoff = now - timedelta(hours=config.abandoned_cart_second_delay_hours)
        first_ids = list(
            SavedCart.objects.filter(
                status=SavedCart.STATUS_ACTIVE,
                first_reminder_sent_at__isnull=True,
                last_activity__lte=first_cutoff,
            )
            .order_by("last_activity")
            .values_list("pk", flat=True)[:limit]
        )
        second_ids = list(
            SavedCart.objects.filter(
                status=SavedCart.STATUS_ACTIVE,
                first_reminder_sent_at__isnull=False,
                first_reminder_sent_at__lte=second_cutoff,
                second_reminder_sent_at__isnull=True,
            )
            .order_by("first_reminder_sent_at")
            .values_list("pk", flat=True)[:limit]
        )
        if not dry_run:
            for saved_id in first_ids:
                queued_cart += int(
                    _queue_job(
                        key=f"saved-cart:{saved_id}:1",
                        job_type=AutomationJob.TYPE_SAVED_CART_EMAIL,
                        payload={"saved_cart_id": saved_id, "reminder_number": 1},
                        when=now,
                    )
                )
            for saved_id in second_ids:
                queued_cart += int(
                    _queue_job(
                        key=f"saved-cart:{saved_id}:2",
                        job_type=AutomationJob.TYPE_SAVED_CART_EMAIL,
                        payload={"saved_cart_id": saved_id, "reminder_number": 2},
                        when=now,
                    )
                )
    else:
        first_ids = second_ids = []

    alert_ids = []
    if config.back_in_stock_enabled:
        subscriptions = StockAlertSubscription.objects.filter(is_active=True).select_related(
            "product", "product__category"
        )[:limit]
        for subscription in subscriptions:
            triggered, _reason, _price = _stock_alert_trigger(subscription)
            if not triggered:
                continue
            alert_ids.append(subscription.pk)
            if not dry_run:
                product_stamp = int(subscription.product.updated_at.timestamp())
                queued_alerts += int(
                    _queue_job(
                        key=f"stock-alert:{subscription.pk}:{product_stamp}",
                        job_type=AutomationJob.TYPE_STOCK_ALERT_EMAIL,
                        payload={"subscription_id": subscription.pk},
                        when=now,
                    )
                )

    from marketing.services import process_due_lead_followups

    followups = process_due_lead_followups(limit=limit, dry_run=dry_run)
    return {
        "due_cart": len(first_ids) + len(second_ids),
        "due_alerts": len(alert_ids),
        "queued_cart": queued_cart,
        "queued_alerts": queued_alerts,
        "lead_reminders": followups["reminded"],
        "lead_escalations": followups["escalated"],
    }


def recover_stale_jobs(*, stale_minutes: int = 15) -> int:
    cutoff = timezone.now() - timedelta(minutes=max(5, stale_minutes))
    stale = AutomationJob.objects.filter(
        status=AutomationJob.STATUS_RUNNING,
        locked_at__lt=cutoff,
    )
    recovered = 0
    for job in stale:
        job.status = (
            AutomationJob.STATUS_RETRY
            if job.attempt_count < job.max_attempts
            else AutomationJob.STATUS_FAILED
        )
        job.next_attempt_at = timezone.now()
        job.locked_at = None
        job.locked_by = ""
        job.last_error = "Recovered after a stale worker lock."
        if job.status == AutomationJob.STATUS_FAILED:
            job.completed_at = timezone.now()
        job.save()
        recovered += 1
    return recovered


def _claim_job(worker_id: str) -> AutomationJob | None:
    now = timezone.now()
    with transaction.atomic():
        queryset = AutomationJob.objects.filter(
            status__in=[AutomationJob.STATUS_QUEUED, AutomationJob.STATUS_RETRY],
            next_attempt_at__lte=now,
        ).order_by("next_attempt_at", "id")
        if connection.features.has_select_for_update_skip_locked:
            queryset = queryset.select_for_update(skip_locked=True)
        else:
            queryset = queryset.select_for_update()
        job = queryset.first()
        if job is None:
            return None
        job.status = AutomationJob.STATUS_RUNNING
        job.attempt_count += 1
        job.locked_at = now
        job.locked_by = worker_id[:120]
        job.save(
            update_fields=[
                "status",
                "attempt_count",
                "locked_at",
                "locked_by",
                "updated_at",
            ]
        )
        if job.delivery_id:
            PostChannelDelivery.objects.filter(pk=job.delivery_id).update(
                status=PostChannelDelivery.STATUS_RUNNING,
                attempt_count=job.attempt_count,
                last_attempt_at=now,
                next_attempt_at=None,
                updated_at=now,
            )
        return job


def _send_stock_alert(subscription: StockAlertSubscription) -> dict:
    triggered, reason, price = _stock_alert_trigger(subscription)
    if not subscription.is_active or not triggered:
        return {"skipped": True, "reason": "Alert condition is no longer active."}
    product = subscription.product
    company = CompanySettings.load()
    unsubscribe_url = absolute_public_url(
        f"/marketing/alerts/unsubscribe/{subscription.token}/"
    )
    send_mail(
        f"{product.name} update from {company.company_name}",
        (
            f"Hello,\n\n{product.name} {reason}.\n\nView it here: "
            f"{absolute_public_url(product.get_absolute_url())}\n\n"
            "Availability can change quickly, so please confirm before payment.\n\n"
            f"Stop this alert: {unsubscribe_url}"
        ),
        settings.DEFAULT_FROM_EMAIL,
        [subscription.email],
        fail_silently=False,
    )
    subscription.is_active = False
    subscription.notified_at = timezone.now()
    subscription.save(update_fields=["is_active", "notified_at"])
    return {"sent": True, "price": str(price)}


def _execute_job(job: AutomationJob) -> dict:
    if job.job_type == AutomationJob.TYPE_SOCIAL_POST:
        delivery = (
            PostChannelDelivery.objects.select_related(
                "post", "post__product", "plan"
            ).get(pk=job.delivery_id)
        )
        return publish_social_post(
            channel=delivery.channel,
            post=delivery.post,
            image_url=_public_image_url(delivery.plan),
        )

    if job.job_type == AutomationJob.TYPE_SAVED_CART_EMAIL:
        saved = SavedCart.objects.get(pk=int(job.payload["saved_cart_id"]))
        reminder_number = int(job.payload["reminder_number"])
        if saved.status != SavedCart.STATUS_ACTIVE:
            return {"skipped": True, "reason": "Cart is no longer active."}
        if reminder_number == 1 and saved.first_reminder_sent_at:
            return {"skipped": True, "reason": "First reminder was already sent."}
        if reminder_number == 2 and saved.second_reminder_sent_at:
            return {"skipped": True, "reason": "Second reminder was already sent."}
        send_saved_cart_message(saved, reminder_number=reminder_number)
        now = timezone.now()
        if reminder_number == 1:
            saved.first_reminder_sent_at = now
            saved.save(update_fields=["first_reminder_sent_at", "updated_at"])
        else:
            saved.second_reminder_sent_at = now
            saved.save(update_fields=["second_reminder_sent_at", "updated_at"])
        return {"sent": True, "reminder_number": reminder_number}

    if job.job_type == AutomationJob.TYPE_STOCK_ALERT_EMAIL:
        subscription = StockAlertSubscription.objects.select_related(
            "product", "product__category"
        ).get(pk=int(job.payload["subscription_id"]))
        return _send_stock_alert(subscription)

    raise ConnectorError("Unknown automation job type.", retryable=False)


def _retry_delay(attempt_count: int) -> timedelta:
    seconds = min(6 * 60 * 60, 60 * (2 ** max(0, attempt_count - 1)))
    return timedelta(seconds=seconds)


def _finish_success(job: AutomationJob, result: dict) -> None:
    now = timezone.now()
    with transaction.atomic():
        locked = AutomationJob.objects.select_for_update().get(pk=job.pk)
        locked.status = AutomationJob.STATUS_SUCCEEDED
        locked.result = result or {}
        locked.last_error = ""
        locked.completed_at = now
        locked.locked_at = None
        locked.locked_by = ""
        locked.save()
        if locked.delivery_id:
            delivery = PostChannelDelivery.objects.select_for_update().get(
                pk=locked.delivery_id
            )
            delivery.status = PostChannelDelivery.STATUS_PUBLISHED
            delivery.external_id = str(result.get("external_id") or "")[:200]
            delivery.external_url = str(result.get("external_url") or "")
            delivery.published_at = now
            delivery.last_error = ""
            delivery.next_attempt_at = None
            delivery.save()
            update_plan_status(delivery.plan)
    log_audit_event(
        actor=None,
        verb="automation.job_succeeded",
        summary=f"Automation job succeeded: {job.idempotency_key}",
        target=job,
    )


def _finish_failure(job: AutomationJob, exc: Exception, *, retryable: bool) -> None:
    now = timezone.now()
    message = str(exc)[:4000] or exc.__class__.__name__
    with transaction.atomic():
        locked = AutomationJob.objects.select_for_update().get(pk=job.pk)
        can_retry = retryable and locked.attempt_count < locked.max_attempts
        locked.status = (
            AutomationJob.STATUS_RETRY if can_retry else AutomationJob.STATUS_FAILED
        )
        locked.next_attempt_at = (
            now + _retry_delay(locked.attempt_count) if can_retry else now
        )
        locked.last_error = message
        locked.locked_at = None
        locked.locked_by = ""
        locked.completed_at = None if can_retry else now
        locked.save()
        if locked.delivery_id:
            delivery = PostChannelDelivery.objects.select_for_update().get(
                pk=locked.delivery_id
            )
            delivery.status = (
                PostChannelDelivery.STATUS_RETRYING
                if can_retry
                else PostChannelDelivery.STATUS_FAILED
            )
            delivery.last_error = message
            delivery.next_attempt_at = locked.next_attempt_at if can_retry else None
            delivery.save()
            update_plan_status(delivery.plan)
    log_audit_event(
        actor=None,
        verb=("automation.job_retry" if can_retry else "automation.job_failed"),
        summary=f"Automation job {locked.status}: {job.idempotency_key} — {message[:400]}",
        target=job,
    )


def process_automation_jobs(*, limit: int = 100, worker_id: str = "") -> dict:
    worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
    recover_stale_jobs()
    succeeded = retried = failed = 0
    for _ in range(max(1, limit)):
        job = _claim_job(worker_id)
        if job is None:
            break
        try:
            result = _execute_job(job)
            _finish_success(job, result)
            succeeded += 1
        except ConnectorError as exc:
            _finish_failure(job, exc, retryable=exc.retryable)
            if exc.retryable and job.attempt_count < job.max_attempts:
                retried += 1
            else:
                failed += 1
        except Exception as exc:
            _finish_failure(job, exc, retryable=True)
            if job.attempt_count < job.max_attempts:
                retried += 1
            else:
                failed += 1
    return {"succeeded": succeeded, "retried": retried, "failed": failed}


def retry_failed_jobs(*, limit: int = 100) -> int:
    now = timezone.now()
    jobs = AutomationJob.objects.filter(status=AutomationJob.STATUS_FAILED).order_by(
        "completed_at", "id"
    )[:limit]
    retried = 0
    for job in jobs:
        job.status = AutomationJob.STATUS_QUEUED
        job.next_attempt_at = now
        job.completed_at = None
        job.locked_at = None
        job.locked_by = ""
        job.last_error = ""
        job.attempt_count = 0
        job.save()
        if job.delivery_id:
            PostChannelDelivery.objects.filter(pk=job.delivery_id).update(
                status=PostChannelDelivery.STATUS_QUEUED,
                next_attempt_at=now,
                last_error="",
                updated_at=now,
            )
        retried += 1
    return retried


def mark_post_manually_published(post: ScheduledPost) -> None:
    plan, _ = PostAutomationPlan.objects.get_or_create(
        post=post,
        defaults={"mode": PostAutomationPlan.MODE_MANUAL},
    )
    now = post.published_at or timezone.now()
    for channel in {str(value) for value in (post.channels or []) if value}:
        delivery, _ = PostChannelDelivery.objects.get_or_create(
            plan=plan,
            post=post,
            channel=channel,
        )
        if delivery.status != PostChannelDelivery.STATUS_PUBLISHED:
            delivery.method = PostChannelDelivery.METHOD_MANUAL
            delivery.status = PostChannelDelivery.STATUS_PUBLISHED
            delivery.published_at = now
            delivery.last_error = ""
            delivery.save()
    plan.status = PostAutomationPlan.STATUS_PUBLISHED
    plan.last_error = ""
    plan.save(update_fields=["status", "last_error", "updated_at"])


def cancel_post_automation(post: ScheduledPost) -> None:
    plan = PostAutomationPlan.objects.filter(post=post).first()
    if not plan:
        return
    now = timezone.now()
    AutomationJob.objects.filter(
        delivery__plan=plan,
        status__in=OPEN_JOB_STATUSES,
    ).update(
        status=AutomationJob.STATUS_CANCELLED,
        completed_at=now,
        locked_at=None,
        locked_by="",
        last_error="Post was cancelled.",
    )
    plan.deliveries.exclude(status=PostChannelDelivery.STATUS_PUBLISHED).update(
        status=PostChannelDelivery.STATUS_CANCELLED,
        last_error="Post was cancelled.",
        next_attempt_at=None,
        updated_at=now,
    )
    plan.status = PostAutomationPlan.STATUS_CANCELLED
    plan.save(update_fields=["status", "updated_at"])
