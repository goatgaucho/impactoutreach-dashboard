import csv
import io
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Request, UploadFile, File, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Constituent, Campaign, Send
from app.auth import auth_redirect_if_needed

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.post("/campaigns/{campaign_id}/upload-csv")
async def upload_csv(
    request: Request,
    campaign_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    redirect = auth_redirect_if_needed(request)
    if redirect:
        return redirect

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        return RedirectResponse(url="/", status_code=303)

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    count = 0
    for row in reader:
        # Normalize header keys
        row = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items() if k}

        first_name = row.get("first_name", "")
        last_name = row.get("last_name", "")
        email = row.get("email", "")
        city = row.get("city", "")
        postal_code = row.get("postal_code", "")

        if not all([first_name, last_name, email, city, postal_code]):
            continue

        constituent = Constituent(
            campaign_id=campaign_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            city=city,
            postal_code=postal_code,
            riding=row.get("riding", ""),
            personal_concern=row.get("personal_concern", ""),
            consent_given=True,
            consent_timestamp=datetime.utcnow(),
        )
        db.add(constituent)
        count += 1

    db.commit()
    return RedirectResponse(url=f"/campaigns/{campaign_id}?uploaded={count}", status_code=303)


@router.get("/campaigns/{campaign_id}/constituents", response_class=HTMLResponse)
def list_constituents(
    request: Request,
    campaign_id: UUID,
    db: Session = Depends(get_db),
):
    redirect = auth_redirect_if_needed(request)
    if redirect:
        return redirect

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        return RedirectResponse(url="/", status_code=303)

    constituents = db.query(Constituent).filter(
        Constituent.campaign_id == campaign_id
    ).order_by(Constituent.created_at.desc()).all()

    # For each constituent, get their send status
    constituent_data = []
    for c in constituents:
        sends = db.query(Send).filter(Send.constituent_id == c.id).all()
        sent = sum(1 for s in sends if s.status == "sent")
        replied = sum(1 for s in sends if s.status == "replied")
        constituent_data.append({
            "constituent": c,
            "total_sends": len(sends),
            "sent": sent,
            "replied": replied,
        })

    return templates.TemplateResponse("campaign_detail.html", {
        "request": request,
        "campaign": campaign,
        "constituents": [cd["constituent"] for cd in constituent_data],
        "constituent_data": constituent_data,
        "sends": [],
        "replies": [],
        "stats": {},
    })
