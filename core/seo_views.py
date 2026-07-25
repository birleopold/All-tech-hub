from __future__ import annotations

from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_GET

from core.seo import public_base_url, public_url


@require_GET
def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /staff/",
        "Disallow: /accounts/",
        "Disallow: /cart/",
        "Disallow: /checkout/",
        "Disallow: /quote/",
        "Disallow: /pay/",
        "Disallow: /api/",
        "Disallow: /preferences/",
        "Disallow: /portal/",
        "",
        f"Host: {public_base_url()}",
        f"Sitemap: {public_url('/sitemap.xml')}",
        f"Sitemap: {public_url('/image-sitemap.xml')}",
    ]
    response = HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = "public, max-age=3600"
    return response


@require_GET
def indexnow_key(request):
    key = (getattr(settings, "INDEXNOW_KEY", "") or "").strip()
    if not key:
        raise Http404
    response = HttpResponse(f"{key}\n", content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = "public, max-age=86400"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response
