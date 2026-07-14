import json

from django.utils.safestring import mark_safe

from core.models import CompanySettings
from growth.models import GrowthSettings
from growth.services import ANALYTICS_SESSION_KEY
from marketing.models import SocialProfileSettings


def growth_context(request):
    growth = GrowthSettings.load()
    pending = request.session.pop(ANALYTICS_SESSION_KEY, [])
    if pending:
        request.session.modified = True

    company = CompanySettings.load()
    social = SocialProfileSettings.load()
    same_as = [
        value
        for value in (
            social.facebook_url,
            social.instagram_url,
            social.tiktok_url,
            social.x_url,
            social.linkedin_url,
            social.youtube_url,
            growth.google_business_profile_url,
        )
        if value
    ]
    schema = {
        "@context": "https://schema.org",
        "@type": "ComputerStore",
        "name": company.legal_name or company.company_name,
        "url": company.website or request.build_absolute_uri("/"),
    }
    if company.logo:
        schema["logo"] = request.build_absolute_uri(company.logo.url)
    if company.phone:
        schema["telephone"] = company.phone
    if company.email:
        schema["email"] = company.email
    if growth.google_place_id:
        schema["identifier"] = growth.google_place_id
    if growth.google_business_profile_url:
        schema["hasMap"] = growth.google_business_profile_url
    if same_as:
        schema["sameAs"] = same_as
    if company.address_line or company.city or company.country:
        schema["address"] = {
            "@type": "PostalAddress",
            "streetAddress": company.address_line,
            "addressLocality": company.city,
            "addressRegion": company.region,
            "postalCode": company.postal_code,
            "addressCountry": company.country,
        }

    return {
        "growth_settings": growth,
        "analytics_pending_events": pending if isinstance(pending, list) else [],
        "local_business_schema_json": mark_safe(
            json.dumps(schema, separators=(",", ":")).replace("</", "<\\/")
        ),
    }
