import logging
from fastapi import APIRouter, Form, Request
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Send, Reply

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhooks/mailgun/inbound")
async def mailgun_inbound(
    request: Request,
    sender: str = Form(default="", alias="sender"),
    recipient: str = Form(default="", alias="recipient"),
    subject: str = Form(default="", alias="subject"),
    body_plain: str = Form(default="", alias="body-plain"),
    stripped_text: str = Form(default="", alias="stripped-text"),
):
    """Handle inbound email from Mailgun (form-encoded POST)."""
    logger.info(f"Inbound email from {sender} to {recipient}")

    db: Session = SessionLocal()
    try:
        # Match recipient to sends.from_address
        send_record = db.query(Send).filter(Send.from_address == recipient).order_by(Send.created_at.desc()).first()

        if not send_record:
            logger.warning(f"No matching send found for recipient {recipient}")
            return {"status": "ok", "message": "no matching send"}

        reply = Reply(
            send_id=send_record.id,
            from_email=sender,
            subject=subject,
            body=stripped_text or body_plain,
        )
        db.add(reply)

        send_record.status = "replied"
        db.commit()

        logger.info(f"Reply stored for send {send_record.id}")
        return {"status": "ok", "message": "reply stored"}

    except Exception:
        db.rollback()
        logger.exception("Error processing inbound email")
        return {"status": "error"}
    finally:
        db.close()


@router.post("/webhooks/mailgun/events")
async def mailgun_events(request: Request):
    """Handle Mailgun event webhooks (bounces, delivery failures)."""
    try:
        data = await request.json()
    except Exception:
        # Might be form-encoded
        form = await request.form()
        data = dict(form)

    logger.info(f"Mailgun event: {data}")

    db: Session = SessionLocal()
    try:
        # Mailgun event structure varies, try to extract event data
        event_data = data.get("event-data", data)
        event_type = event_data.get("event", "")
        message_id = ""

        # Try to get message ID from headers
        message_headers = event_data.get("message", {}).get("headers", {})
        message_id = message_headers.get("message-id", "")

        if not message_id:
            # Fallback: try top-level
            message_id = event_data.get("Message-Id", event_data.get("message-id", ""))

        if message_id and event_type in ("bounced", "dropped", "failed"):
            # Clean up message ID format
            clean_id = message_id.strip("<>")
            send_record = db.query(Send).filter(
                Send.mailgun_message_id.contains(clean_id)
            ).first()

            if send_record:
                send_record.status = "bounced"
                error_desc = event_data.get("delivery-status", {}).get("description", "")
                if not error_desc:
                    error_desc = event_data.get("reason", event_type)
                send_record.error_message = error_desc
                db.commit()
                logger.info(f"Updated send {send_record.id} to bounced")

        return {"status": "ok"}

    except Exception:
        db.rollback()
        logger.exception("Error processing Mailgun event")
        return {"status": "error"}
    finally:
        db.close()
