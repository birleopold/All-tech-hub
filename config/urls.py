from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from billing import views as billing_views
from catalog import seo_feeds
from core import api_views as core_api
from core import auth_views as core_auth
from core import health as core_health
from core import seo_views as core_seo
from merchandising import seo_views as merchandising_seo
from merchandising.merchant import strict_google_merchant_feed

handler400 = "core.error_views.bad_request"
handler403 = "core.error_views.permission_denied"
handler404 = "core.error_views.page_not_found"
handler500 = "core.error_views.server_error"

urlpatterns = [
    path("robots.txt", core_seo.robots_txt, name="robots_txt"),
    path("sitemap.xml", merchandising_seo.sitemap_index, name="sitemap_index"),
    path(
        "sitemap.xml",
        merchandising_seo.sitemap_index,
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path(
        "sitemaps/commercial.xml",
        merchandising_seo.commercial_sitemap,
        name="commercial_sitemap",
    ),
    path(
        "sitemaps/<slug:section>.xml",
        seo_feeds.seo_sitemap,
        name="seo_sitemap",
    ),
    path("image-sitemap.xml", seo_feeds.image_sitemap, name="image_sitemap"),
    path(
        "feeds/google-merchant.xml",
        strict_google_merchant_feed,
        name="google_merchant_feed",
    ),
    path("indexnow-key.txt", core_seo.indexnow_key, name="indexnow_key"),
    path("health/live/", core_health.live, name="health_live"),
    path("health/ready/", core_health.ready, name="health_ready"),
    path("healthz/", core_health.healthz, name="healthz"),
    path("api/v1/products/", core_api.api_products, name="api_products"),
    path(
        "api/v1/products/<slug:slug>/",
        core_api.api_product_detail,
        name="api_product_detail",
    ),
    path("api/v1/orders/lookup/", core_api.api_order_lookup, name="api_order_lookup"),
    path(
        "quote/<uuid:token>/",
        billing_views.quote_customer_portal,
        name="quote_customer_portal",
    ),
    path(
        "pay/<uuid:token>/",
        billing_views.payment_request_portal,
        name="payment_request_portal",
    ),
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        core_auth.StaffLoginView.as_view(),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "staff/security/two-factor/",
        core_auth.two_factor_setup,
        name="staff_two_factor_setup",
    ),
    path(
        "staff/security/two-factor/confirm/",
        core_auth.two_factor_confirm,
        name="staff_two_factor_confirm",
    ),
    path(
        "staff/security/two-factor/disable/",
        core_auth.two_factor_disable,
        name="staff_two_factor_disable",
    ),
    path("preferences/", include("loyalty.urls")),
    path("marketing/", include("marketing.public_urls")),
    path("marketing/", include("growth.public_urls")),
    path("staff/marketing/growth/", include("growth.staff_urls")),
    path("staff/marketing/", include("marketing.staff_urls")),
    path("staff/customer-campaigns/", include("customer_campaigns.urls")),
    path("", include("merchandising.urls")),
    path("", include("core.urls")),
    path("catalog/", include("catalog.urls")),
    path("cart/", include("commerce.urls")),
    path("staff/", include("automation.urls")),
    path("staff/", include("dashboard.urls")),
    path("staff/", include("core.staff_urls")),
    path("staff/", include("commerce.staff_urls")),
    path("staff/", include("crm.urls")),
    path("staff/", include("billing.urls")),
    path("staff/", include("operations.urls")),
    path("staff/", include("reports.urls")),
    path("staff/", include("purchasing.urls")),
    path("portal/", include("portal.urls")),
    path("staff/", include("messaging.urls")),
    path("staff/", include("inventory.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "LEOSOFT UG LTD Administration"
admin.site.site_title = "LEOSOFT UG LTD"
admin.site.index_title = "Business administration"
