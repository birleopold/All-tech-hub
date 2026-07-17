from django.urls import path

from customer_campaigns import views

urlpatterns = [
    path("", views.CustomerCampaignListView.as_view(), name="staff_customer_campaigns"),
    path("new/", views.CustomerCampaignCreateView.as_view(), name="staff_customer_campaign_create"),
    path("<int:pk>/", views.customer_campaign_detail, name="staff_customer_campaign_detail"),
    path("<int:pk>/edit/", views.CustomerCampaignUpdateView.as_view(), name="staff_customer_campaign_edit"),
    path("<int:pk>/prepare/", views.customer_campaign_prepare, name="staff_customer_campaign_prepare"),
    path("<int:pk>/approve/", views.customer_campaign_approve, name="staff_customer_campaign_approve"),
    path("<int:pk>/send/", views.customer_campaign_send, name="staff_customer_campaign_send"),
    path("<int:pk>/schedule/", views.customer_campaign_schedule, name="staff_customer_campaign_schedule"),
    path("<int:pk>/pause/", views.customer_campaign_pause, name="staff_customer_campaign_pause"),
    path("<int:pk>/resume/", views.customer_campaign_resume, name="staff_customer_campaign_resume"),
    path("<int:pk>/cancel/", views.customer_campaign_cancel, name="staff_customer_campaign_cancel"),
]
