"""Cross-cutting request middleware."""

import logging
import re
import time
import uuid

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import resolve

from core.security import staff_two_factor_is_verified

request_logger = logging.getLogger("alltech.request")

URL_ACTION_PERMISSIONS = {
    "staff_account_payment_create": "billing.add_accountpayment",
    "staff_automation_pause": "automation.change_automationjob",
    "staff_automation_resume": "automation.change_automationjob",
    "staff_automation_job_replay": "automation.change_automationjob",
    "staff_automation_job_cancel": "automation.change_automationjob",
    "staff_apply_customer_credit": "billing.change_customercredit",
    "staff_catalogue_bulk_enrichment": "catalog.change_product",
    "staff_contact_to_ticket": "core.add_supportticket",
    "staff_contact_toggle": "core.change_contactmessage",
    "staff_customer_create": "crm.add_customer",
    "staff_customer_edit": "crm.change_customer",
    "staff_document_create": "billing.add_commercialdocument",
    "staff_document_duplicate": "billing.add_commercialdocument",
    "staff_document_edit": "billing.change_commercialdocument",
    "staff_document_issue": "billing.change_commercialdocument",
    "staff_document_payment": "billing.add_documentpayment",
    "staff_document_payment_link": "billing.change_commercialdocument",
    "staff_document_quote_approve": "billing.change_commercialdocument",
    "staff_document_quote_customer_link": "billing.change_commercialdocument",
    "staff_document_revise": "billing.revise_issued_document",
    "staff_document_cancel": "billing.void_commercial_document",
    "staff_document_to_credit_note": "billing.add_commercialdocument",
    "staff_document_to_delivery_note": "billing.add_commercialdocument",
    "staff_document_to_demand_note": "billing.add_commercialdocument",
    "staff_document_to_invoice": "billing.add_commercialdocument",
    "staff_document_to_proforma": "billing.add_commercialdocument",
    "staff_document_to_receipt": "billing.add_commercialdocument",
    "staff_email_jobcard": "operations.view_jobcard",
    "staff_email_job_update": "operations.view_jobcard",
    "staff_job_bench_status": "operations.change_jobcard",
    "staff_job_create": "operations.add_jobcard",
    "staff_job_edit": "operations.change_jobcard",
    "staff_job_attachment": "operations.add_jobattachment",
    "staff_job_note": "operations.add_jobnote",
    "staff_job_reschedule": "operations.change_jobcard",
    "staff_job_stock_use": "inventory.add_stockmovement",
    "staff_job_time": "operations.add_timeentry",
    "staff_marketing_campaign_create": "marketing.add_marketingcampaign",
    "staff_marketing_campaign_edit": "marketing.change_marketingcampaign",
    "staff_marketing_caption_create": "marketing.add_captiontemplate",
    "staff_marketing_caption_edit": "marketing.change_captiontemplate",
    "staff_marketing_lead_create": "marketing.add_marketinglead",
    "staff_marketing_lead_claim": "marketing.change_marketinglead",
    "staff_marketing_lead_contacted": "marketing.change_marketinglead",
    "staff_marketing_lead_edit": "marketing.change_marketinglead",
    "staff_marketing_lead_quote": "billing.add_commercialdocument",
    "staff_loyalty_redeem": "billing.add_customercredit",
    "staff_growth_conversion_approve": "growth.change_ambassadorconversion",
    "staff_growth_conversion_pay": "billing.add_documentpayment",
    "staff_replenishment_create_po": "purchasing.add_purchaseorder",
    "staff_marketing_link_create": "marketing.add_campaignlink",
    "staff_marketing_link_edit": "marketing.change_campaignlink",
    "staff_marketing_post_create": "marketing.add_scheduledpost",
    "staff_marketing_post_edit": "marketing.change_scheduledpost",
    "staff_marketing_post_published": "marketing.change_scheduledpost",
    "staff_order_invoice": "billing.add_commercialdocument",
    "staff_order_return": "commerce.add_customerreturn",
    "staff_order_transition": "commerce.change_order",
    "staff_order_shipment": "commerce.change_shipment",
    "staff_payment_reconcile": "billing.change_documentpayment",
    "staff_payment_submission_approve": "billing.add_documentpayment",
    "staff_payment_submission_reject": "billing.change_paymentsubmission",
    "staff_retention_followup_refresh": "reports.add_customerfollowup",
    "staff_retention_followup_claim": "reports.change_customerfollowup",
    "staff_retention_followup_email": "reports.change_customerfollowup",
    "staff_retention_followup_whatsapp": "reports.change_customerfollowup",
    "staff_retention_followup_close": "reports.change_customerfollowup",
    "staff_payment_refund": "billing.add_paymentrefund",
    "staff_po_create": "purchasing.add_purchaseorder",
    "staff_po_edit": "purchasing.change_purchaseorder",
    "staff_po_receive": "purchasing.add_stockreceipt",
    "staff_po_return": "purchasing.add_supplierreturn",
    "staff_product_create": "catalog.add_product",
    "staff_product_edit": "catalog.change_product",
    "staff_product_commercial_review": "catalog.change_product",
    "staff_serial_labels": "catalog.view_productserial",
    "staff_stock_adjust": "inventory.add_stockadjustment",
    "staff_stocktake_add_line": "inventory.change_stocktake",
    "staff_stocktake_create": "inventory.add_stocktake",
    "staff_stocktake_post": "inventory.change_stocktake",
    "staff_ticket_comment_create": "core.add_ticketcomment",
    "staff_ticket_create": "core.add_supportticket",
    "staff_ticket_edit": "core.change_supportticket",
    "staff_warranty_center": "catalog.view_productserial",
}

URL_PERMISSION_PREFIXES = {
    "staff_customers": "crm.view_customer",
    "staff_customer_detail": "crm.view_customer",
    "staff_catalogue_quality": "catalog.view_product",
    "staff_document": "billing.view_commercialdocument",
    "staff_email_document": "billing.view_commercialdocument",
    "staff_order": "commerce.view_order",
    "staff_inventory": "inventory.view_stockadjustment",
    "staff_product": "catalog.view_product",
    "staff_stocktake": "inventory.view_stocktake",
    "staff_po": "purchasing.view_purchaseorder",
    "staff_purchasing": "purchasing.view_purchaseorder",
    "staff_job": "operations.view_jobcard",
    "staff_ticket": "core.view_supportticket",
    "staff_contact": "core.view_contactmessage",
    "staff_reports": "billing.view_commercialdocument",
    "staff_conversion": "commerce.view_order",
    "staff_retention": "commerce.view_order",
    "staff_customer_growth": "commerce.view_order",
    "staff_customer_campaign": "marketing.change_marketingcampaign",
    "staff_automation": "automation.view_automationjob",
    "staff_marketing": "marketing.view_marketingcampaign",
    "staff_growth": "growth.view_growthsettings",
    "staff_export": "billing.view_commercialdocument",
    "staff_audit": "core.view_auditevent",
    "staff_security": "core.view_auditevent",
    "staff_business": "core.change_businesshours",
    "staff_email_log": "messaging.view_outboundemail",
    "staff_stock_movements": "inventory.view_stockmovement",
    "staff_payment": "billing.change_documentpayment",
    "staff_account_payment": "billing.add_accountpayment",
    "staff_customer_statement": "billing.view_commercialdocument",
    "staff_apply_customer_credit": "billing.change_customercredit",
}

PRIVATE_RESPONSE_PREFIXES = (
    "/staff/",
    "/admin/",
    "/accounts/",
    "/cart/",
    "/quote/",
    "/pay/",
)
PRIVATE_RESPONSE_PATHS = {
    "/api/v1/orders/lookup/",
}
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def _is_private_response_path(path: str) -> bool:
    if path.startswith("/portal/") and not path.startswith("/portal/kb/"):
        return True
    return path in PRIVATE_RESPONSE_PATHS or path.startswith(PRIVATE_RESPONSE_PREFIXES)


class RequestContextMiddleware:
    """Attach a safe request ID and log actionable request outcomes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = (request.headers.get("X-Request-ID") or "").strip()
        request.request_id = (
            supplied if _REQUEST_ID_PATTERN.fullmatch(supplied) else uuid.uuid4().hex
        )
        started = time.perf_counter()
        try:
            response = self.get_response(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            request_logger.exception(
                "request_failed request_id=%s method=%s path=%s duration_ms=%s",
                request.request_id,
                request.method,
                request.path,
                duration_ms,
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        response.setdefault("X-Request-ID", request.request_id)
        if response.status_code >= 500:
            log_method = request_logger.error
        elif response.status_code >= 400:
            log_method = request_logger.info
        else:
            log_method = request_logger.debug
        log_method(
            "request_completed request_id=%s method=%s path=%s status=%s duration_ms=%s",
            request.request_id,
            request.method,
            request.path,
            response.status_code,
            duration_ms,
        )
        return response


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not getattr(settings, "SECURITY_HEADERS_ENABLED", True):
            return response

        self._set_header(
            response,
            "Referrer-Policy",
            getattr(settings, "REFERRER_POLICY", ""),
        )
        self._set_header(
            response,
            "Permissions-Policy",
            getattr(settings, "PERMISSIONS_POLICY", ""),
        )
        self._set_header(response, "X-Permitted-Cross-Domain-Policies", "none")
        self._set_header(response, "Cross-Origin-Resource-Policy", "same-site")

        if _is_private_response_path(request.path_info):
            self._set_header(response, "X-Robots-Tag", "noindex, nofollow, noarchive")
            self._set_header(response, "Cache-Control", "private, no-store")

        csp = getattr(settings, "CONTENT_SECURITY_POLICY", "")
        if csp:
            csp_header = (
                "Content-Security-Policy-Report-Only"
                if getattr(settings, "CONTENT_SECURITY_POLICY_REPORT_ONLY", True)
                else "Content-Security-Policy"
            )
            self._set_header(response, csp_header, csp)
        return response

    @staticmethod
    def _set_header(response, name: str, value: str):
        if value and name not in response:
            response[name] = value


class StaffRoleRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        protected_staff_path = request.path.startswith(("/staff/", "/admin/"))
        if (
            getattr(settings, "REQUIRE_STAFF_2FA", False)
            and protected_staff_path
            and request.user.is_authenticated
            and request.user.is_staff
        ):
            name = getattr(
                getattr(request, "resolver_match", None) or resolve(request.path_info),
                "url_name",
                "",
            )
            allowed = {
                "staff_two_factor_setup",
                "staff_two_factor_confirm",
                "staff_two_factor_disable",
            }
            profile = getattr(request.user, "two_factor", None)
            if name not in allowed:
                if not (profile and profile.enabled):
                    return redirect("staff_two_factor_setup")
                if not staff_two_factor_is_verified(request, request.user):
                    response = redirect("login")
                    response["Location"] += f"?next={request.path}"
                    return response
        if (
            getattr(settings, "ENFORCE_STAFF_ROLES", False)
            and request.path.startswith("/staff/")
            and request.user.is_authenticated
            and request.user.is_staff
            and not request.user.is_superuser
        ):
            match = getattr(request, "resolver_match", None) or resolve(request.path_info)
            name = getattr(match, "url_name", "") or ""
            action_permission = URL_ACTION_PERMISSIONS.get(name)
            if action_permission:
                if not request.user.has_perm(action_permission):
                    raise PermissionDenied
            else:
                for prefix, permission in URL_PERMISSION_PREFIXES.items():
                    if name.startswith(prefix) and not request.user.has_perm(permission):
                        raise PermissionDenied
        return self.get_response(request)
