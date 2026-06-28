from fastapi import APIRouter, Header

from auth import verify_key
from optimization_queue import (
    get_queue,
    get_queue_history,
    approve_queue_item,
    reject_queue_item,
)

router = APIRouter()


@router.get("")
def queue(status: str = "PENDING", limit: int = 100, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return get_queue(status, limit)


@router.get("/history")
def queue_history(limit: int = 250, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return get_queue_history(limit)


@router.post("/{item_id}/approve")
def approve_item(item_id: int, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return approve_queue_item(item_id)


@router.post("/{item_id}/reject")
def reject_item(item_id: int, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return reject_queue_item(item_id)
