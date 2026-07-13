class CampaignAttributionMiddleware:
    """Persist UTM attribution so later contact submissions become measurable leads."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "GET":
            source = (request.GET.get("utm_source") or "").strip()[:60]
            medium = (request.GET.get("utm_medium") or "").strip()[:60]
            campaign = (request.GET.get("utm_campaign") or "").strip()[:200]
            content = (request.GET.get("utm_content") or "").strip()[:120]
            if source or medium or campaign or content:
                previous = request.session.get("marketing_attribution", {}) or {}
                request.session["marketing_attribution"] = {
                    "source": source or previous.get("source", "direct"),
                    "medium": medium or previous.get("medium", "website"),
                    "campaign": campaign or previous.get("campaign", ""),
                    "content": content or previous.get("content", ""),
                    "link_id": previous.get("link_id"),
                }
        request.marketing_attribution = request.session.get(
            "marketing_attribution", {}
        )
        return self.get_response(request)
