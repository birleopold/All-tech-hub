"""Truthful channel capability summaries; a profile alone is not an API connection."""


def integration_capabilities(*, facebook_connected=False, instagram_connected=False,
                             whatsapp_available=False, email_connected=False,
                             analytics_connected=False):
    return [
        {"name": "Facebook publishing", "state": "Connected" if facebook_connected else "Needs Meta API setup", "ready": bool(facebook_connected)},
        {"name": "Instagram publishing", "state": "Connected" if instagram_connected else "Needs Meta API setup", "ready": bool(instagram_connected)},
        {"name": "WhatsApp customer messaging", "state": "Staff-assisted click-to-chat" if whatsapp_available else "Needs WhatsApp number", "ready": bool(whatsapp_available)},
        {"name": "Customer email delivery", "state": "SMTP configured" if email_connected else "Needs SMTP setup", "ready": bool(email_connected)},
        {"name": "Traffic and conversion analytics", "state": "Configured" if analytics_connected else "Needs analytics setup", "ready": bool(analytics_connected)},
        {"name": "Online payment gateway", "state": "Provider contract and API integration required", "ready": False},
        {"name": "TikTok, YouTube and LinkedIn publishing", "state": "Manual publishing; provider access required", "ready": False},
    ]
