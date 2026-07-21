from django.contrib import messages
from django.db import DatabaseError, connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.views.generic import TemplateView

from core.forms import ContactForm


class HomeView(TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        from catalog.discovery import new_rotation_seed, order_for_discovery
        from catalog.models import Product

        ctx = super().get_context_data(**kwargs)
        featured_products = (
            Product.objects.filter(
                is_published=True,
                is_featured=True,
                kind=Product.KIND_PHYSICAL,
            )
            .select_related("category")
            .prefetch_related("gallery_images", "variants")
        )
        featured_services = Product.objects.filter(
            is_published=True,
            kind=Product.KIND_SERVICE,
            is_featured=True,
        ).select_related("category")

        ctx["featured_products"] = order_for_discovery(
            featured_products,
            new_rotation_seed(),
        )[:8]
        ctx["featured_services"] = order_for_discovery(
            featured_services,
            new_rotation_seed(),
        )[:6]
        return ctx


class AboutView(TemplateView):
    template_name = "core/about.html"


class OfflineView(TemplateView):
    template_name = "core/offline.html"


def healthz(request):
    """Return a small, non-cacheable readiness response.

    The check is deliberately read-only: monitoring should verify that the
    configured database can answer a trivial query without creating or
    updating application records.
    """

    status = 200
    payload = {"status": "ok"}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        status = 503
        payload = {"status": "unavailable"}

    response = JsonResponse(payload, status=status)
    response["Cache-Control"] = "no-store, max-age=0"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def service_worker(request):
    """Serve a privacy-safe service worker.

    Navigation responses are never written to the browser cache. This prevents
    staff, portal, order, quote, payment and customer pages from being retained
    on shared devices. Only versioned static assets and the generic offline page
    are cached.
    """

    offline_url = "/offline/"
    public_asset_urls = [
        static("css/site.css"),
        static("css/customer_experience.css"),
        static("css/foundation.css"),
        static("js/alltech_ui.js"),
        static("site.webmanifest"),
    ]
    precache_urls = ",\n  ".join(f'"{url}"' for url in [offline_url, *public_asset_urls])
    body = f"""
const CACHE_NAME = "leosoft-public-assets-v3";
const PRECACHE_URLS = [
  {precache_urls}
];

self.addEventListener("install", event => {{
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
}});

self.addEventListener("activate", event => {{
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.map(key => {{
        if (key !== CACHE_NAME) return caches.delete(key);
        return Promise.resolve();
      }})))
      .then(() => self.clients.claim())
  );
}});

self.addEventListener("fetch", event => {{
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Never cache HTML/navigation responses. Online requests go directly to the
  // server; offline requests receive only the generic offline page.
  if (request.mode === "navigate") {{
    event.respondWith(
      fetch(request, {{ cache: "no-store" }})
        .catch(() => caches.match("{offline_url}"))
    );
    return;
  }}

  // Cache only public static assets. Media, API, portal, payment and staff
  // responses always remain network-only.
  if (!url.pathname.startsWith("/static/")) return;

  event.respondWith(
    caches.match(request).then(cached => {{
      if (cached) return cached;
      return fetch(request).then(response => {{
        if (response.ok && response.type === "basic") {{
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
        }}
        return response;
      }});
    }})
  );
}});
""".strip()
    response = HttpResponse(body, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


def contact_view(request):
    from core.models import hours_summary, is_open_now

    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            contact_message = form.save()
            from marketing.services import create_lead_from_contact

            create_lead_from_contact(request, contact_message)
            messages.success(request, "Thanks — we will get back to you shortly.")
            return redirect("contact")
    else:
        form = ContactForm()
    return render(
        request,
        "core/contact.html",
        {
            "form": form,
            "business_hours": hours_summary(),
            "is_open_now": is_open_now(),
        },
    )
