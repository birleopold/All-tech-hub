"""Cross-cutting request middleware."""

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import resolve

URL_PERMISSION_PREFIXES = {
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


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not getattr(settings, "SECURITY_HEADERS_ENABLED", True):
            return response

        self._set_header(response, "Referrer-Policy", getattr(settings, "REFERRER_POLICY", ""))
        self._set_header(
            response,
            "Permissions-Policy",
            getattr(settings, "PERMISSIONS_POLICY", ""),
        )

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
