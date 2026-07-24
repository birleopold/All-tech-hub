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
    "automation_control": "Automation control",
    "email_deliverability": "Email deliverability",
    "marketing_dashboard": "Marketing automation",
    "growth_dashboard": "Growth analytics",
    "audit_log": "Audit log",
    "security_diagnostics": "Security diagnostics",
    "orders": "Shop orders",
    "order_detail": "Order details",
    "documents": "Quotes & invoices",
    "document_create": "New document",
    "document_view": "Document details",
    "account_payment_create": "Account payment",
    "payment_reconciliation": "Payment reconciliation",
    "inventory": "Inventory overview",
    "products": "Products",
    "product_create": "New product",
    "product_edit": "Edit product",
    "warranty_center": "Warranty / RMA",
    "stocktakes": "Stock takes",
    "purchasing": "Purchasing",
    "job_bench": "Technician bench",
    "jobs": "Job cards",
    "job_create": "New job card",
    "job_detail": "Job details",
    "job_calendar": "Job calendar",
    "tickets": "Support tickets",
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
    "issued": "primary",
    "partial": "warning",
    "paid": "success",
    "expired": "danger",
    "intake": "neutral",
    "diagnosing": "info",
    "awaiting_parts": "warning",
    "in_repair": "primary",
    "qa": "info",
    "completed": "success",
    "open": "primary",
    "resolved": "success",
    "closed": "neutral",
    "failed": "danger",
    "refunded": "neutral",
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
