
def add_negative_keyword(payload, dry_run=True):
    return {
        "dry_run": dry_run,
        "action": "ADD_NEGATIVE_KEYWORD",
        "message": "Future live action: add negative keyword through Amazon Ads API.",
        "payload": payload,
    }
