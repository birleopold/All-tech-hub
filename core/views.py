from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.generic import TemplateView

from core.forms import ContactForm
from core.models import CompanySettings


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
    CompanySettings.load()
    return JsonResponse({"status": "ok"})


def service_worker(request):
    body = """
const CACHE_NAME = "alltech-hub-v1";
const PRECACHE_URLS = [
  "/",
  "/offline/",
  "/static/css/site.css",
  "/static/site.webmanifest"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.map(key => {
        if (key !== CACHE_NAME) return caches.delete(key);
        return Promise.resolve();
      })))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then(response => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request).then(cached => cached || caches.match("/offline/")))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(cached => {
      if (cached) return cached;
      return fetch(request).then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
        }
        return response;
      });
    })
  );
});
""".strip()
    response = HttpResponse(body, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
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
