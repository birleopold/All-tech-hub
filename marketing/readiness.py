"""Evaluate practical coverage across the complete commercial customer journey."""

from __future__ import annotations


def _check(label: str, ready: bool, action: str, route: str) -> dict:
    return {
        "label": label,
        "ready": bool(ready),
        "action": action,
        "route": route,
    }


def evaluate_growth_phases(metrics: dict) -> dict:
    """Convert measured business activity into actionable, honest phase coverage."""
    published = metrics.get("published_count", 0)
    phases = [
        {
            "name": "Discovery",
            "description": "Help buyers find the business and measure their visits.",
            "checks": [
                _check("Products published", published > 0, "Publish products with clear UGX prices.", "staff_products"),
                _check("At least two public channels", metrics.get("connected_channels", 0) >= 2, "Configure your WhatsApp and social profiles.", "staff_growth_settings"),
                _check("Website analytics configured", metrics.get("analytics_ready", False), "Connect Google Analytics or Microsoft Clarity.", "staff_growth_settings"),
            ],
        },
        {
            "name": "Trust",
            "description": "Give customers proof, complete information, and confidence.",
            "checks": [
                _check("Every published item has an image", published > 0 and metrics.get("missing_images", 0) == 0, "Add genuine photos to every published product.", "staff_catalogue_quality"),
                _check("Product descriptions are complete", published > 0 and metrics.get("missing_descriptions", 0) == 0, "Explain specifications, condition, warranty, and delivery.", "staff_catalogue_quality"),
                _check("Public reviews or business profile", metrics.get("published_reviews", 0) > 0 or metrics.get("business_profile_ready", False), "Publish verified reviews and configure your Google Business profile.", "staff_retention_dashboard"),
            ],
        },
        {
            "name": "Acquisition",
            "description": "Publish consistent campaigns and identify useful channels.",
            "checks": [
                _check("Tracked campaign links", metrics.get("tracked_links", 0) > 0, "Create a tracked link for every marketing channel.", "staff_marketing_link_create"),
                _check("Content ready to publish", metrics.get("scheduled_content", 0) > 0, "Schedule product demos, comparison videos, and practical tips.", "staff_marketing_post_create"),
                _check("Recent tracked visitors", metrics.get("clicks_30d", 0) > 0, "Distribute tracked offers through your active channels.", "staff_growth_distribution_groups"),
            ],
        },
        {
            "name": "Conversion",
            "description": "Respond quickly and turn genuine enquiries into orders.",
            "checks": [
                _check("Enquiries are being generated", metrics.get("leads_30d", 0) > 0, "Capture and assign incoming customer enquiries.", "staff_marketing_leads"),
                _check("No overdue follow-ups", metrics.get("overdue_follow_ups", 0) == 0, "Contact customers whose promised follow-up is overdue.", "staff_marketing_leads"),
                _check("Orders recorded in the last 30 days", metrics.get("orders_30d", 0) > 0, "Follow up qualified leads and complete their purchase.", "staff_orders"),
            ],
        },
        {
            "name": "Fulfillment",
            "description": "Keep offers available and resolve delayed delivery work.",
            "checks": [
                _check("Published products are in stock", published > 0 and metrics.get("unavailable_products", 0) == 0, "Restock unavailable advertised products or unpublish them.", "staff_inventory"),
                _check("No orders waiting over 24 hours", metrics.get("aged_open_orders", 0) == 0, "Confirm, prepare, or dispatch aging customer orders.", "staff_orders"),
                _check("No shipment exceptions", metrics.get("shipment_exceptions", 0) == 0, "Resolve delivery problems and update affected customers.", "staff_orders"),
            ],
        },
        {
            "name": "Retention",
            "description": "Recover unfinished purchases and grow repeat business.",
            "checks": [
                _check("Cart recovery is operational", metrics.get("cart_recovery_ready", False), "Enable abandoned-cart recovery and configure live email delivery.", "staff_growth_saved_carts"),
                _check("Customers enrolled in loyalty", metrics.get("loyalty_accounts", 0) > 0, "Enroll customers and award points after completed purchases.", "staff_customer_growth_dashboard"),
                _check("Repeat customers recorded", metrics.get("repeat_customers", 0) > 0, "Send consent-based follow-ups and relevant return-customer offers.", "staff_customer_campaign_create"),
            ],
        },
        {
            "name": "Advocacy",
            "description": "Turn verified customer satisfaction into recommendations.",
            "checks": [
                _check("Published customer reviews", metrics.get("published_reviews", 0) > 0, "Request and moderate genuine verified-purchase reviews.", "staff_retention_dashboard"),
                _check("Active referral ambassadors", metrics.get("active_ambassadors", 0) > 0, "Register trusted customers or creators as ambassadors.", "staff_growth_ambassador_create"),
                _check("Referral sales recorded", metrics.get("ambassador_conversions", 0) > 0, "Share referral links and track the resulting completed sales.", "staff_growth_ambassadors"),
            ],
        },
    ]

    actions = []
    completed_checks = 0
    for phase_index, phase in enumerate(phases):
        ready_count = sum(check["ready"] for check in phase["checks"])
        completed_checks += ready_count
        phase["ready_count"] = ready_count
        phase["total_checks"] = len(phase["checks"])
        phase["score"] = round(ready_count * 100 / phase["total_checks"])
        phase["status"] = (
            "ready" if ready_count == phase["total_checks"]
            else "attention" if ready_count
            else "missing"
        )
        for check in phase["checks"]:
            if not check["ready"]:
                actions.append({"phase": phase["name"], "priority": phase_index, **check})

    total_checks = sum(phase["total_checks"] for phase in phases)
    return {
        "phases": phases,
        "priority_actions": actions,
        "completed_checks": completed_checks,
        "total_checks": total_checks,
        "coverage_score": round(completed_checks * 100 / total_checks) if total_checks else 0,
        "ready_phases": sum(phase["status"] == "ready" for phase in phases),
    }
