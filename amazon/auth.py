
from amazon_ads import get_access_token


def get_headers():
    token = get_access_token()

    return {
        "Authorization": f"Bearer {token}",
        "Amazon-Advertising-API-ClientId": __import__("os").environ["AMAZON_CLIENT_ID"],
        "Amazon-Advertising-API-Scope": __import__("os").environ["AMAZON_PROFILE_ID"],
        "Content-Type": "application/json",
    }
