from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.views.generic import TemplateView

from core.forms import ContactForm


class HomeView(TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        from django.db.models import Count, Q

        from catalog.discovery import new_rotation_seed, order_for_discovery
        from catalog.models import Category, Product

        ctx = super().get_context_data(**kwargs)
        published = Product.objects.filter(is_published=True)

        featured_products = (
            published.filter(
                is_featured=True,
                kind=Product.KIND_PHYSICAL,
            )
            .select_related("category")
            .prefetch_related("gallery_images", "variants")
        )
        if not featured_products.exists():
            featured_products = (
                published.filter(kind=Product.KIND_PHYSICAL)
                .select_related("category")
                .prefetch_related("gallery_images", "variants")
            )

        featured_services = published.filter(
            kind=Product.KIND_SERVICE,
            is_featured=True,
        ).select_related("category")
        if not featured_services.exists():
            featured_services = published.filter(
                kind=Product.KIND_SERVICE
            ).select_related("category")

        ctx["featured_products"] = order_for_discovery(
            featured_products,
            new_rotation_seed(),
        )[:8]
        ctx["featured_services"] = order_for_discovery(
            featured_services,
            new_rotation_seed(),
        )[:6]

        catalog_categories = list(
            Category.objects.filter(parent__isnull=True)
            .annotate(
                direct_item_count=Count(
                    "products",
                    filter=Q(products__is_published=True),
                    distinct=True,
                ),
                child_item_count=Count(
                    "subcategories__products",
                    filter=Q(subcategories__products__is_published=True),
                    distinct=True,
                ),
            )
            .order_by("sort_order", "name")[:6]
        )
        for category in catalog_categories:
            category.public_item_count = (
                category.direct_item_count + category.child_item_count
            )

        ctx["catalog_categories"] = catalog_categories
        ctx["catalog_stats"] = published.aggregate(
            total=Count("pk"),
            products=Count(
                "pk",
                filter=Q(kind=Product.KIND_PHYSICAL),
            ),
            services=Count(
                "pk",
                filter=Q(kind=Product.KIND_SERVICE),
            ),
        )
        return ctx


class AboutView(TemplateView):
    template_name = "core/about.html"

    def get_context_data(self, **kwargs):
        from django.db.models import Q

        from catalog.models import Product
        from catalog.presentation import prepare_public_products

        context = super().get_context_data(**kwargs)
        # Use real published catalogue photographs without exposing drafts or
        # making a gallery lookup for every card on the About page.
        products = (
            Product.objects.filter(is_published=True, kind=Product.KIND_PHYSICAL)
            .filter(Q(image__gt="") | Q(gallery_images__image__gt=""))
            .select_related("category", "growth_data", "commerce_profile")
            .prefetch_related("gallery_images", "variants")
            .distinct()
            .order_by("-is_featured", "name")[:4]
        )
        context["about_products"] = prepare_public_products(products)
        return context


class OfflineView(TemplateView):
    template_name = "core/offline.html"


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
        static("css/public_experience.css"),
        static("js/alltech_ui.js"),
        static("js/public_experience.js"),
        static("site.webmanifest"),
    ]
    precache_urls = ",\n  ".join(f'"{url}"' for url in [offline_url, *public_asset_urls])
    body = f"""
const CACHE_NAME = "leosoft-public-assets-v4";
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
