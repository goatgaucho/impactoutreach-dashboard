from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Campaign, Constituent, Send
from app.auth import require_auth

router = APIRouter()


@router.get("/campaigns/{campaign_id}/stats")
def campaign_stats(campaign_id: UUID, auth: dict = Depends(require_auth), db: Session = Depends(get_db)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    today = date.today()

    total_constituents = db.query(func.count(Constituent.id)).filter(
        Constituent.campaign_id == campaign_id
    ).scalar() or 0

    total_sends = db.query(func.count(Send.id)).filter(
        Send.campaign_id == campaign_id
    ).scalar() or 0

    sent_count = db.query(func.count(Send.id)).filter(
        Send.campaign_id == campaign_id, Send.status == "sent"
    ).scalar() or 0

    pending_count = db.query(func.count(Send.id)).filter(
        Send.campaign_id == campaign_id, Send.status.in_(["pending", "scheduled"])
    ).scalar() or 0

    bounced_count = db.query(func.count(Send.id)).filter(
        Send.campaign_id == campaign_id, Send.status == "bounced"
    ).scalar() or 0

    replied_count = db.query(func.count(Send.id)).filter(
        Send.campaign_id == campaign_id, Send.status == "replied"
    ).scalar() or 0

    emails_today = db.query(func.count(Send.id)).filter(
        Send.campaign_id == campaign_id,
        Send.scheduled_for == today,
        Send.status.in_(["sent", "scheduled", "generating"]),
    ).scalar() or 0

    return {
        "total_constituents": total_constituents,
        "total_sends": total_sends,
        "sent_count": sent_count,
        "pending_count": pending_count,
        "bounced_count": bounced_count,
        "replied_count": replied_count,
        "emails_today": emails_today,
    }
