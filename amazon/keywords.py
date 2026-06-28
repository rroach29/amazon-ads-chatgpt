
def create_exact_keyword(payload, dry_run=True):
    return {
        "dry_run": dry_run,
        "action": "CREATE_EXACT_KEYWORD",
        "message": "Future live action: create exact match keyword through Amazon Ads API.",
        "payload": payload,
    }


def update_bid(payload, dry_run=True):
    return {
        "dry_run": dry_run,
        "action": "UPDATE_BID",
        "message": "Future live action: update keyword or target bid through Amazon Ads API.",
        "payload": payload,
    }
