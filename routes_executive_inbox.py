"""Business OS v0.5.0 — Executive Inbox routes."""

from fastapi import APIRouter, Header

from auth import verify_key
from business_os.executive_inbox.service import ExecutiveInboxService

router = APIRouter()


@router.get("/executive-inbox")
def executive_inbox(
    limit: int = 50,
    x_api_key: str = Header(...),
):
    verify_key(x_api_key)
    return ExecutiveInboxService.inbox(limit=limit)
