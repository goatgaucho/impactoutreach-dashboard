import json
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Campaign, Constituent, Send, Reply
from app.auth import auth_redirect_if_needed

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def dashboard_home(request: Request, db: Session = Depends(get_db)):
    redirect = auth_redirect_if_needed(request)
    if redirect:
        return redirect

    campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()

    campaign_data = []
    for c in campaigns:
        send_count = db.query(func.count(Send.id)).filter(Send.campaign_id == c.id, Send.status == "sent").scalar() or 0
        reply_count = db.query(func.count(Send.id)).filter(Send.campaign_id == c.id, Send.status == "replied").scalar() or 0
        constituent_count = db.query(func.count(Constituent.id)).filter(Constituent.campaign_id == c.id).scalar() or 0
        total_sends = db.query(func.count(Send.id)).filter(Send.campaign_id == c.id).scalar() or 0

        campaign_data.append({
            "campaign": c,
            "sent_count": send_count,
            "reply_count": reply_count,
            "constituent_count": constituent_count,
            "total_sends": total_sends,
        })

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "campaigns": campaign_data,
    })


@router.get("/campaigns/new", response_class=HTMLResponse)
def campaign_new_form(request: Request):
    redirect = auth_redirect_if_needed(request)
    if redirect:
        return redirect
    return templates.TemplateResponse("campaign_new.html", {"request": request})


@router.post("/campaigns")
def create_campaign(
    request: Request,
    name: str = Form(...),
    issue_brief: str = Form(...),
    tone_instructions: str = Form(""),
    stakeholders_json: str = Form("[]"),
    emails_per_day: int = Form(10),
    start_date: str = Form(""),
    db: Session = Depends(get_db),
):
    redirect = auth_redirect_if_needed(request)
    if redirect:
        return redirect

    try:
        stakeholders = json.loads(stakeholders_json)
    except json.JSONDecodeError:
        stakeholders = []

    parsed_date = None
    if start_date:
        try:
            parsed_date = date.fromisoformat(start_date)
        except ValueError:
            pass

    campaign = Campaign(
        name=name,
        issue_brief=issue_brief,
        tone_instructions=tone_instructions or None,
        stakeholders=stakeholders,
        emails_per_day=emails_per_day,
        start_date=parsed_date,
        status="draft",
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    return RedirectResponse(url=f"/campaigns/{campaign.id}", status_code=303)


@router.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
def campaign_detail(request: Request, campaign_id: UUID, db: Session = Depends(get_db)):
    redirect = auth_redirect_if_needed(request)
    if redirect:
        return redirect

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        return RedirectResponse(url="/", status_code=303)

    constituents = db.query(Constituent).filter(Constituent.campaign_id == campaign_id).order_by(Constituent.created_at.desc()).all()

    sends = db.query(Send).filter(Send.campaign_id == campaign_id).order_by(Send.created_at.desc()).limit(50).all()

    # Get replies for this campaign
    reply_sends = db.query(Send).filter(
        Send.campaign_id == campaign_id,
        Send.status == "replied",
    ).all()
    reply_send_ids = [s.id for s in reply_sends]
    replies = []
    if reply_send_ids:
        replies = db.query(Reply).filter(Reply.send_id.in_(reply_send_ids)).order_by(Reply.received_at.desc()).all()

    # Stats
    total_constituents = len(constituents)
    total_sends = db.query(func.count(Send.id)).filter(Send.campaign_id == campaign_id).scalar() or 0
    sent_count = db.query(func.count(Send.id)).filter(Send.campaign_id == campaign_id, Send.status == "sent").scalar() or 0
    pending_count = db.query(func.count(Send.id)).filter(Send.campaign_id == campaign_id, Send.status.in_(["pending", "scheduled"])).scalar() or 0
    bounced_count = db.query(func.count(Send.id)).filter(Send.campaign_id == campaign_id, Send.status == "bounced").scalar() or 0
    replied_count = db.query(func.count(Send.id)).filter(Send.campaign_id == campaign_id, Send.status == "replied").scalar() or 0
    failed_count = db.query(func.count(Send.id)).filter(Send.campaign_id == campaign_id, Send.status == "failed").scalar() or 0

    today = date.today()
    emails_today = db.query(func.count(Send.id)).filter(
        Send.campaign_id == campaign_id,
        Send.scheduled_for == today,
        Send.status.in_(["sent", "scheduled", "generating"]),
    ).scalar() or 0

    return templates.TemplateResponse("campaign_detail.html", {
        "request": request,
        "campaign": campaign,
        "constituents": constituents,
        "sends": sends,
        "replies": replies,
        "stats": {
            "total_constituents": total_constituents,
            "total_sends": total_sends,
            "sent_count": sent_count,
            "pending_count": pending_count,
            "bounced_count": bounced_count,
            "replied_count": replied_count,
            "failed_count": failed_count,
            "emails_today": emails_today,
        },
    })


@router.get("/campaigns/{campaign_id}/edit", response_class=HTMLResponse)
def campaign_edit_form(request: Request, campaign_id: UUID, db: Session = Depends(get_db)):
    redirect = auth_redirect_if_needed(request)
    if redirect:
        return redirect

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse("campaign_edit.html", {
        "request": request,
        "campaign": campaign,
    })


@router.post("/campaigns/{campaign_id}/edit")
def update_campaign(
    request: Request,
    campaign_id: UUID,
    name: str = Form(...),
    issue_brief: str = Form(...),
    tone_instructions: str = Form(""),
    stakeholders_json: str = Form("[]"),
    emails_per_day: int = Form(10),
    start_date: str = Form(""),
    db: Session = Depends(get_db),
):
    redirect = auth_redirect_if_needed(request)
    if redirect:
        return redirect

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        return RedirectResponse(url="/", status_code=303)

    try:
        stakeholders = json.loads(stakeholders_json)
    except json.JSONDecodeError:
        stakeholders = campaign.stakeholders or []

    campaign.name = name
    campaign.issue_brief = issue_brief
    campaign.tone_instructions = tone_instructions or None
    campaign.stakeholders = stakeholders
    campaign.emails_per_day = emails_per_day

    if start_date:
        try:
            campaign.start_date = date.fromisoformat(start_date)
        except ValueError:
            pass

    db.commit()
    return RedirectResponse(url=f"/campaigns/{campaign_id}", status_code=303)


@router.post("/campaigns/{campaign_id}/activate")
def activate_campaign(request: Request, campaign_id: UUID, db: Session = Depends(get_db)):
    redirect = auth_redirect_if_needed(request)
    if redirect:
        return redirect

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if campaign:
        campaign.status = "active"
        if not campaign.start_date:
            campaign.start_date = date.today()
        db.commit()
    return RedirectResponse(url=f"/campaigns/{campaign_id}", status_code=303)


@router.post("/campaigns/{campaign_id}/pause")
def pause_campaign(request: Request, campaign_id: UUID, db: Session = Depends(get_db)):
    redirect = auth_redirect_if_needed(request)
    if redirect:
        return redirect

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if campaign:
        campaign.status = "paused"
        db.commit()
    return RedirectResponse(url=f"/campaigns/{campaign_id}", status_code=303)


@router.post("/campaigns/{campaign_id}/complete")
def complete_campaign(request: Request, campaign_id: UUID, db: Session = Depends(get_db)):
    redirect = auth_redirect_if_needed(request)
    if redirect:
        return redirect

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if campaign:
        campaign.status = "complete"
        db.commit()
    return RedirectResponse(url=f"/campaigns/{campaign_id}", status_code=303)
