
from amazon_ads import get_sponsored_products_campaigns


def pause_campaign(payload, dry_run=True):
    return {
        "dry_run": dry_run,
        "action": "PAUSE_CAMPAIGN",
        "message": "Future live action: pause campaign through Amazon Ads API.",
        "payload": payload,
    }
