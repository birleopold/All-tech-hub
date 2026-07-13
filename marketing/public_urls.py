from django.urls import path

from marketing import views


urlpatterns = [
    path("r/<str:code>/", views.track_campaign_link, name="marketing_track"),
    path("feeds/products.csv", views.product_feed_csv, name="marketing_product_feed_csv"),
    path("feeds/products.json", views.product_feed_json, name="marketing_product_feed_json"),
    path("feeds/products.xml", views.product_feed_xml, name="marketing_product_feed_xml"),
]
