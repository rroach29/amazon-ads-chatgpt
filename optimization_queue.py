from datetime import datetime

from database import SessionLocal
from models import OptimizationQueue


def serialize_queue_item(row):
    return {
        "id": row.id,
        "created_at": str(row.created_at),
        "channel": row.channel,
        "status": row.status,
        "priority": row.priority,
        "recommendation_type": row.recommendation_type,
        "campaign_id": row.campaign_id,
        "campaign_name": row.campaign_name,
        "ad_group_id": row.ad_group_id,
        "ad_group_name": row.ad_group_name,
        "search_term": row.search_term,
        "keyword": row.keyword,
        "title": row.title,
        "reason": row.reason,
        "recommended_action": row.recommended_action,
        "confidence": row.confidence,
        "estimated_monthly_savings": row.estimated_monthly_savings,
        "payload": row.payload,
        "approved_at": str(row.approved_at) if row.approved_at else None,
        "rejected_at": str(row.rejected_at) if row.rejected_at else None,
        "executed_at": str(row.executed_at) if row.executed_at else None,
        "execution_result": row.execution_result,
    }


def get_queue(status: str = "PENDING", limit: int = 100):
    db = SessionLocal()

    try:
        rows = (
            db.query(OptimizationQueue)
            .filter(OptimizationQueue.channel == "amazon_ads")
            .filter(OptimizationQueue.status == status)
            .order_by(OptimizationQueue.created_at.desc())
            .limit(limit)
            .all()
        )

        return {
            "status": "OK",
            "count": len(rows),
            "items": [serialize_queue_item(row) for row in rows],
        }

    finally:
        db.close()


def get_queue_history(limit: int = 250):
    db = SessionLocal()

    try:
        rows = (
            db.query(OptimizationQueue)
            .filter(OptimizationQueue.channel == "amazon_ads")
            .order_by(OptimizationQueue.created_at.desc())
            .limit(limit)
            .all()
        )

        return {
            "status": "OK",
            "count": len(rows),
            "items": [serialize_queue_item(row) for row in rows],
        }

    finally:
        db.close()


def approve_queue_item(item_id: int):
    db = SessionLocal()

    try:
        item = db.query(OptimizationQueue).filter(OptimizationQueue.id == item_id).first()

        if not item:
            return {"status": "NOT_FOUND", "message": "Optimization item not found."}

        item.status = "APPROVED"
        item.approved_at = datetime.utcnow()

        db.commit()

        return {
            "status": "OK",
            "message": "Optimization approved.",
            "item": serialize_queue_item(item),
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def reject_queue_item(item_id: int):
    db = SessionLocal()

    try:
        item = db.query(OptimizationQueue).filter(OptimizationQueue.id == item_id).first()

        if not item:
            return {"status": "NOT_FOUND", "message": "Optimization item not found."}

        item.status = "REJECTED"
        item.rejected_at = datetime.utcnow()

        db.commit()

        return {
            "status": "OK",
            "message": "Optimization rejected.",
            "item": serialize_queue_item(item),
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
