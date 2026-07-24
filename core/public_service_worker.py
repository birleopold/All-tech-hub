from django.http import HttpResponse
from django.templatetags.static import static


def service_worker(request):
    """Serve a privacy-safe service worker for public static assets only."""

    offline_url = "/offline/"
    public_asset_urls = [
        static("css/site.css"),
        static("css/customer_experience.css"),
        static("css/foundation.css"),
        static("css/public_experience.css"),
        static("css/marketplace_experience.css"),
        static("css/public_detail_contact.css"),
        static("js/alltech_ui.js"),
        static("js/public_experience.js"),
        static("js/marketplace_experience.js"),
        static("js/public_detail_contact.js"),
        static("site.webmanifest"),
    ]
    precache_urls = ",\n  ".join(
        f'"{url}"' for url in [offline_url, *public_asset_urls]
    )
    body = f"""
const CACHE_NAME = "leosoft-public-assets-v6";
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

  // Never cache HTML, portal, staff, payment, media or API responses.
  if (request.mode === "navigate") {{
    event.respondWith(
      fetch(request, {{ cache: "no-store" }})
        .catch(() => caches.match("{offline_url}"))
    );
    return;
  }}

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
