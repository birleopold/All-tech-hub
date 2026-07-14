from django.urls import path

from growth import feeds as growth_feeds
from marketing import views

urlpatterns = [
    path("r/<str:code>/", views.track_campaign_link, name="marketing_track"),
    path("feeds/products.csv", growth_feeds.product_feed_csv, name="marketing_product_feed_csv"),
    path("feeds/products.json", growth_feeds.product_feed_json, name="marketing_product_feed_json"),
    path("feeds/products.xml", growth_feeds.product_feed_xml, name="marketing_product_feed_xml"),
]
