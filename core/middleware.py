"""Cross-cutting request middleware."""

import logging
import re
import time
import uuid

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import resolve

request_logger = logging.getLogger("alltech.request")

URL_PERMISSION_PREFIXES = {
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
        if (
            getattr(settings, "REQUIRE_STAFF_2FA", False)
            and request.path.startswith("/staff/")
            and request.user.is_authenticated
            and request.user.is_staff
            and not request.user.is_superuser
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
            if name not in allowed and not (profile and profile.enabled):
                return redirect("staff_two_factor_setup")
        if (
            getattr(settings, "ENFORCE_STAFF_ROLES", False)
            and request.path.startswith("/staff/")
            and request.user.is_authenticated
            and request.user.is_staff
            and not request.user.is_superuser
        ):
            match = getattr(request, "resolver_match", None) or resolve(request.path_info)
            name = getattr(match, "url_name", "") or ""
            for prefix, permission in URL_PERMISSION_PREFIXES.items():
                if name.startswith(prefix) and not request.user.has_perm(permission):
                    raise PermissionDenied
        return self.get_response(request)
