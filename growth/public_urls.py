from django.urls import path

from growth import views


urlpatterns = [
    path("cart/save/", views.save_cart, name="growth_saved_cart_save"),
    path("cart/recover/<uuid:token>/", views.recover_saved_cart, name="growth_saved_cart_recover"),
    path("cart/unsubscribe/<uuid:token>/", views.unsubscribe_saved_cart, name="growth_saved_cart_unsubscribe"),
    path("alerts/<slug:slug>/", views.subscribe_stock_alert, name="growth_stock_alert_subscribe"),
    path("alerts/unsubscribe/<uuid:token>/", views.unsubscribe_stock_alert, name="growth_stock_alert_unsubscribe"),
    path("ref/<slug:code>/", views.ambassador_referral, name="growth_ambassador_referral"),
]
