from django import template

register = template.Library()


STAFF_PAGE_LABELS = {
    "dashboard": "Overview",
    "search": "Global search",
    "reports": "Reports & analytics",
    "conversion_lifecycle": "Conversion lifecycle",
    "retention_dashboard": "Retention & reviews",
    "customer_growth_dashboard": "Customer growth & loyalty",
    "customer_campaigns": "Email campaigns",
    "customer_campaign_create": "New email campaign",
    "customer_campaign_detail": "Campaign details",
    "customer_campaign_edit": "Edit campaign",
    "automation_control": "Automation control",
    "automation_job_detail": "Automation job",
    "email_deliverability": "Email deliverability",
    "email_suppression_detail": "Suppression details",
    "email_log": "Email log",
    "email_log_detail": "Email details",
    "marketing_dashboard": "Marketing automation",
    "growth_dashboard": "Growth analytics",
    "audit_log": "Audit log",
    "security_diagnostics": "Security diagnostics",
    "orders": "Shop orders",
    "order_detail": "Order details",
    "documents": "Quotes & invoices",
    "document_create": "New document",
    "document_edit": "Edit document",
    "document_view": "Document details",
    "account_payment_create": "Account payment",
    "payment_reconciliation": "Payment reconciliation",
    "customer_statement": "Customer statement",
    "inventory": "Inventory overview",
    "stock_movements": "Stock movements",
    "products": "Products",
    "product_create": "New product",
    "product_edit": "Edit product",
    "product_labels": "Product labels",
    "serial_labels": "Serial labels",
    "warranty_center": "Warranty / RMA",
    "stocktakes": "Stock takes",
    "stocktake_create": "New stock take",
    "stocktake_detail": "Stock take details",
    "purchasing": "Purchasing",
    "po_create": "New purchase order",
    "po_edit": "Purchase order",
    "job_bench": "Technician bench",
    "job_bench_detail": "Bench job",
    "jobs": "Job cards",
    "job_create": "New job card",
    "job_detail": "Job details",
    "job_edit": "Edit job card",
    "job_calendar": "Job calendar",
    "tickets": "Support tickets",
    "ticket_create": "New support ticket",
    "ticket_detail": "Ticket details",
    "ticket_edit": "Edit support ticket",
    "contact_messages": "Contact inbox",
    "notifications": "Notifications",
    "business_hours": "Business hours",
    "two_factor_setup": "Two-factor security",
}

STATUS_TONES = {
    "pending": "warning",
    "confirmed": "info",
    "processing": "info",
    "ready": "primary",
    "ready_pickup": "success",
    "dispatched": "primary",
    "delivered": "success",
    "fulfilled": "success",
    "cancelled": "danger",
    "draft": "neutral",
    "queued": "info",
    "sent": "info",
    "issued": "primary",
    "partial": "warning",
    "partially_received": "warning",
    "received": "success",
    "posted": "success",
    "paid": "success",
    "expired": "danger",
    "intake": "neutral",
    "diagnosing": "info",
    "awaiting_parts": "warning",
    "in_repair": "primary",
    "qa": "info",
    "completed": "success",
    "open": "primary",
    "in_progress": "info",
    "resolved": "success",
    "closed": "neutral",
    "failed": "danger",
    "soft_bounced": "warning",
    "bounced": "danger",
    "complained": "danger",
    "refunded": "neutral",
    "suppressed": "danger",
    "scheduled": "info",
    "paused": "warning",
    "running": "primary",
    "succeeded": "success",
}

PRIORITY_TONES = {
    "urgent": "danger",
    "high": "warning",
    "normal": "primary",
    "low": "neutral",
}


@register.filter
def staff_page_label(url_name):
    """Turn staff URL names into readable breadcrumb labels."""

    name = str(url_name or "").strip()
    if name.startswith("staff_"):
        name = name[6:]
    if not name:
        return "Workspace"
    return STAFF_PAGE_LABELS.get(name, name.replace("_", " ").title())


@register.filter
def staff_status_tone(value):
    """Return a stable visual tone name for workflow statuses."""

    return STATUS_TONES.get(str(value or "").strip().lower(), "neutral")


@register.filter
def staff_priority_tone(value):
    """Return a stable visual tone name for priority levels."""

    return PRIORITY_TONES.get(str(value or "").strip().lower(), "neutral")
