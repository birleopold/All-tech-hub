from django.urls import path

from marketing import views


urlpatterns = [
    path("", views.MarketingDashboardView.as_view(), name="staff_marketing_dashboard"),
    path(
        "market-readiness/",
        views.MarketReadinessView.as_view(),
        name="staff_marketing_market_readiness",
    ),
    path("campaigns/", views.CampaignListView.as_view(), name="staff_marketing_campaigns"),
    path("campaigns/new/", views.CampaignCreateView.as_view(), name="staff_marketing_campaign_create"),
    path("campaigns/<int:pk>/edit/", views.CampaignUpdateView.as_view(), name="staff_marketing_campaign_edit"),
    path("captions/", views.CaptionListView.as_view(), name="staff_marketing_captions"),
    path("captions/new/", views.CaptionCreateView.as_view(), name="staff_marketing_caption_create"),
    path("captions/<int:pk>/edit/", views.CaptionUpdateView.as_view(), name="staff_marketing_caption_edit"),
    path("links/", views.LinkListView.as_view(), name="staff_marketing_links"),
    path("links/new/", views.LinkCreateView.as_view(), name="staff_marketing_link_create"),
    path("links/<int:pk>/edit/", views.LinkUpdateView.as_view(), name="staff_marketing_link_edit"),
    path("links/<int:pk>/qr/", views.campaign_link_qr, name="staff_marketing_link_qr"),
    path("posts/", views.PostListView.as_view(), name="staff_marketing_posts"),
    path("posts/new/", views.PostCreateView.as_view(), name="staff_marketing_post_create"),
    path("posts/<int:pk>/edit/", views.PostUpdateView.as_view(), name="staff_marketing_post_edit"),
    path("posts/<int:pk>/published/", views.mark_post_published, name="staff_marketing_post_published"),
    path("leads/", views.LeadListView.as_view(), name="staff_marketing_leads"),
    path("leads/new/", views.LeadCreateView.as_view(), name="staff_marketing_lead_create"),
    path("leads/<int:pk>/edit/", views.LeadUpdateView.as_view(), name="staff_marketing_lead_edit"),
    path("leads/<int:pk>/claim/", views.LeadClaimView.as_view(), name="staff_marketing_lead_claim"),
    path("leads/<int:pk>/contacted/", views.LeadMarkContactedView.as_view(), name="staff_marketing_lead_contacted"),
    path("leads/<int:pk>/quote/", views.LeadCreateQuoteView.as_view(), name="staff_marketing_lead_quote"),
]
