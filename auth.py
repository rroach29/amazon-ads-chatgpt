import os
from fastapi import HTTPException

CHATGPT_API_KEY = os.getenv("CHATGPT_API_KEY")


def verify_key(x_api_key: str):
    if not CHATGPT_API_KEY:
        raise HTTPException(status_code=500, detail="CHATGPT_API_KEY is not set")

    if x_api_key != CHATGPT_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
