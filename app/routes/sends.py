from datetime import date
from uuid import UUID

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Campaign, Constituent, Send
from app.auth import auth_redirect_if_needed

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/campaigns/{campaign_id}/sends", response_class=HTMLResponse)
def list_sends(
    request: Request,
    campaign_id: UUID,
    status: str = Query(default=""),
    db: Session = Depends(get_db),
):
    redirect = auth_redirect_if_needed(request)
    if redirect:
        return redirect

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        return templates.TemplateResponse("sends.html", {
            "request": request,
            "campaign": None,
            "sends": [],
            "filter_status": status,
        })

    query = db.query(Send).filter(Send.campaign_id == campaign_id)
    if status:
        query = query.filter(Send.status == status)
    sends = query.order_by(Send.created_at.desc()).all()

    return templates.TemplateResponse("sends.html", {
        "request": request,
        "campaign": campaign,
        "sends": sends,
        "filter_status": status,
    })
