import logging
import random
import unicodedata
import re
from datetime import datetime, date, timedelta, time
from zoneinfo import ZoneInfo

from sqlalchemy import func, and_, text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Campaign, Constituent, Send, Reply
from app.services.ai_writer import generate_email_body, generate_subject_line, build_greeting
from app.services.mailgun import send_email
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

ET = ZoneInfo("America/Toronto")


def sanitize_email_local(first_name: str, last_name: str, use_full_name: bool = False) -> str:
    """Create a sanitized email local part from a name.
    E.g. 'Marie-Claire Cote' -> 'marie-claire.c' or 'marie-claire.cote' if full name.
    """
    def normalize(s: str) -> str:
        # Remove accents
        nfkd = unicodedata.normalize("NFKD", s)
        ascii_str = nfkd.encode("ASCII", "ignore").decode("ASCII")
        # Lowercase, replace spaces with dots
        ascii_str = ascii_str.lower().replace(" ", ".")
        # Strip non a-z, dot, hyphen
        ascii_str = re.sub(r"[^a-z.\-]", "", ascii_str)
        return ascii_str

    first = normalize(first_name)
    if use_full_name:
        last = normalize(last_name)
        return f"{first}.{last}"
    else:
        last_initial = normalize(last_name[:1]) if last_name else "x"
        return f"{first}.{last_initial}"


def build_from_address(constituent: Constituent) -> tuple[str, str]:
    """Returns (from_address, display_name) for a constituent."""
    local = sanitize_email_local(
        constituent.first_name,
        constituent.last_name,
        use_full_name=constituent.opted_full_name,
    )
    from_address = f"{local}@{settings.MAILGUN_DOMAIN}"

    if constituent.opted_full_name:
        display_name = f"{constituent.first_name} {constituent.last_name}"
    else:
        last_initial = constituent.last_name[0] if constituent.last_name else ""
        display_name = f"{constituent.first_name} {last_initial}."

    return from_address, display_name


def schedule_daily_sends():
    """8:55 AM ET - Schedule sends for active campaigns."""
    logger.info("Running daily send scheduling job...")
    db: Session = SessionLocal()

    try:
        today = datetime.now(ET).date()
        campaigns = db.query(Campaign).filter(
            Campaign.status == "active",
            Campaign.start_date <= today,
        ).all()

        for campaign in campaigns:
            stakeholders = campaign.stakeholders or []
            if not stakeholders:
                logger.warning(f"Campaign {campaign.name} has no stakeholders, skipping")
                continue

            # Count sends already scheduled/sent today
            today_count = db.query(func.count(Send.id)).filter(
                Send.campaign_id == campaign.id,
                Send.scheduled_for == today,
            ).scalar() or 0

            remaining_slots = campaign.emails_per_day - today_count
            if remaining_slots <= 0:
                logger.info(f"Campaign {campaign.name} already at daily limit ({today_count})")
                continue

            # Get constituents who haven't been fully matched to all stakeholders
            constituents = db.query(Constituent).filter(
                Constituent.campaign_id == campaign.id,
                Constituent.consent_given == True,
            ).all()

            # Collect eligible constituents (those who haven't sent to ALL stakeholders yet)
            eligible_constituents = []
            for constituent in constituents:
                unsent_stakeholders = []
                for stakeholder in stakeholders:
                    existing = db.query(Send).filter(
                        Send.campaign_id == campaign.id,
                        Send.constituent_id == constituent.id,
                        Send.recipient_email == stakeholder["email"],
                    ).first()
                    if not existing:
                        unsent_stakeholders.append(stakeholder)

                if unsent_stakeholders:
                    eligible_constituents.append((constituent, unsent_stakeholders))

            # Shuffle constituents, then select enough to fill the daily quota
            # Each constituent sends to ALL their unsent stakeholders as a batch
            random.shuffle(eligible_constituents)
            pairs_today = []
            for constituent, unsent_stakeholders in eligible_constituents:
                # Check if adding this constituent's sends would exceed the limit
                if len(pairs_today) + len(unsent_stakeholders) > remaining_slots:
                    continue
                for stakeholder in unsent_stakeholders:
                    pairs_today.append((constituent, stakeholder))
            num_sends = len(pairs_today)

            # Distribute sends evenly across the 9 AM – 9 PM ET window (12 hours)
            # with random jitter so they don't land on exact intervals
            WINDOW_START_HOUR = 9
            WINDOW_END_HOUR = 21  # 9 PM
            window_minutes = (WINDOW_END_HOUR - WINDOW_START_HOUR) * 60  # 720 min

            if num_sends > 0:
                # Divide window into equal slots, then add jitter within each slot
                slot_size = window_minutes / num_sends
                send_times = []
                for i in range(num_sends):
                    slot_start = int(i * slot_size)
                    slot_end = int((i + 1) * slot_size)
                    # Random minute within this slot
                    chosen_minute = random.randint(slot_start, max(slot_start, slot_end - 1))
                    send_times.append(chosen_minute)
            else:
                send_times = []

            new_sends = []
            for idx, (constituent, stakeholder) in enumerate(pairs_today):
                from_address, display_name = build_from_address(constituent)

                minutes_offset = send_times[idx]
                scheduled_dt = datetime.combine(
                    today,
                    time(WINDOW_START_HOUR, 0),
                    tzinfo=ET,
                ) + timedelta(minutes=minutes_offset)

                send = Send(
                    campaign_id=campaign.id,
                    constituent_id=constituent.id,
                    recipient_name=stakeholder.get("name", ""),
                    recipient_email=stakeholder["email"],
                    from_address=from_address,
                    from_display_name=display_name,
                    status="scheduled",
                    scheduled_for=today,
                    scheduled_time=scheduled_dt,
                )
                new_sends.append(send)

            # Enforce 45-min gap: no two sends to same recipient within 45 min
            # Group by recipient, sort by time, adjust if needed
            by_recipient: dict[str, list[Send]] = {}
            for s in new_sends:
                by_recipient.setdefault(s.recipient_email, []).append(s)

            for recipient_email, sends_list in by_recipient.items():
                # Also include existing scheduled sends to this recipient today
                existing_times = db.query(Send.scheduled_time).filter(
                    Send.recipient_email == recipient_email,
                    Send.scheduled_for == today,
                    Send.scheduled_time.isnot(None),
                ).all()
                occupied = [et[0] for et in existing_times]

                sends_list.sort(key=lambda s: s.scheduled_time)
                for s in sends_list:
                    while any(
                        abs((s.scheduled_time - occ).total_seconds()) < 2700  # 45 min
                        for occ in occupied
                    ):
                        # Bump by 45 min
                        s.scheduled_time = s.scheduled_time + timedelta(minutes=45)
                        # Don't go past 9 PM ET
                        if s.scheduled_time.astimezone(ET).hour >= 21:
                            s.scheduled_time = None
                            s.status = "pending"
                            break
                    if s.scheduled_time:
                        occupied.append(s.scheduled_time)

            for s in new_sends:
                db.add(s)

            db.commit()
            logger.info(f"Campaign {campaign.name}: scheduled {len(new_sends)} new sends for today")

    except Exception:
        db.rollback()
        logger.exception("Error in daily send scheduling")
    finally:
        db.close()


def _send_email_sync(
    from_address: str,
    from_display_name: str,
    to_email: str,
    subject: str,
    body: str,
    riding: str,
) -> dict:
    """Synchronous wrapper around the async send_email function."""
    import httpx

    footer = f"\n\n---\nThis message was sent via ImpactOutreach on behalf of a constituent of {riding}. To respond to this constituent, reply directly to this email."
    full_body = body + footer

    url = f"https://api.mailgun.net/v3/{settings.MAILGUN_DOMAIN}/messages"
    data = {
        "from": f'"{from_display_name}" <{from_address}>',
        "to": to_email,
        "subject": subject,
        "text": full_body,
        "h:Reply-To": from_address,
    }

    response = httpx.post(
        url,
        auth=("api", settings.MAILGUN_API_KEY),
        data=data,
        timeout=30.0,
    )

    if response.status_code == 200:
        result = response.json()
        logger.info(f"Email sent successfully: {result.get('id')}")
        return result
    else:
        logger.error(f"Mailgun error {response.status_code}: {response.text}")
        raise Exception(f"Mailgun API error {response.status_code}: {response.text}")


def execute_pending_sends():
    """Every 5 min - execute scheduled sends that are due."""
    logger.info("Running send executor...")
    db: Session = SessionLocal()

    try:
        now = datetime.now(ET)
        today = now.date()

        sends = db.query(Send).filter(
            Send.status == "scheduled",
            Send.scheduled_for == today,
            Send.scheduled_time <= now,
        ).order_by(Send.scheduled_time).limit(5).with_for_update(skip_locked=True).all()

        # Claim all sends atomically by marking as "generating" first
        send_ids = [s.id for s in sends]
        for send_record in sends:
            send_record.status = "generating"
        db.commit()

        if not send_ids:
            logger.info("No pending sends to process")
            return

        # Re-load the claimed sends (now safe from race conditions)
        sends = db.query(Send).filter(Send.id.in_(send_ids)).all()

        for send_record in sends:
            try:
                constituent = send_record.constituent
                campaign = send_record.campaign

                # Skip sends for stakeholders that have been removed from the campaign
                current_stakeholder_emails = {sh.get("email") for sh in (campaign.stakeholders or [])}
                if send_record.recipient_email not in current_stakeholder_emails:
                    logger.info(f"Skipping send {send_record.id} — stakeholder {send_record.recipient_email} removed from campaign")
                    send_record.status = "failed"
                    send_record.error_message = "Stakeholder removed from campaign"
                    db.commit()
                    continue

                last_initial = constituent.last_name[0] if constituent.last_name else ""
                riding = constituent.riding or constituent.city or ""

                # Look up this stakeholder's title
                stakeholder_title = ""
                for sh in (campaign.stakeholders or []):
                    if sh.get("email") == send_record.recipient_email:
                        stakeholder_title = sh.get("title", "")
                        break

                # Check if this constituent already has a sent/generating email
                # for this campaign — if so, reuse that body with a new greeting
                existing_send = db.query(Send).filter(
                    Send.campaign_id == campaign.id,
                    Send.constituent_id == constituent.id,
                    Send.body.isnot(None),
                    Send.status.in_(["sent", "generating"]),
                    Send.id != send_record.id,
                ).first()

                if existing_send and existing_send.body:
                    # Reuse existing body, just swap the greeting line
                    logger.info(f"Reusing email body from send {existing_send.id} for constituent {constituent.first_name}")
                    send_body = _replace_greeting(
                        existing_send.body,
                        send_record.recipient_name,
                        stakeholder_title,
                    )
                else:
                    # First email for this constituent — generate fresh
                    send_body = generate_email_body(
                        first_name=constituent.first_name,
                        last_initial=last_initial,
                        city=constituent.city,
                        riding=riding,
                        recipient_name=send_record.recipient_name,
                        recipient_title=stakeholder_title,
                        issue_brief=campaign.issue_brief,
                        personal_concern=constituent.personal_concern,
                        tone_instructions=campaign.tone_instructions,
                        display_name=send_record.from_display_name,
                    )

                subject = generate_subject_line(
                    recipient_name=send_record.recipient_name,
                    recipient_title=stakeholder_title,
                    campaign_name=campaign.name,
                    constituent_name=send_record.from_display_name,
                )

                send_record.subject = subject
                send_record.body = send_body

                # Send via Mailgun (synchronous)
                result = _send_email_sync(
                    from_address=send_record.from_address,
                    from_display_name=send_record.from_display_name,
                    to_email=send_record.recipient_email,
                    subject=subject,
                    body=send_body,
                    riding=riding,
                )

                send_record.mailgun_message_id = result.get("id", "")
                send_record.status = "sent"
                send_record.sent_at = datetime.now(ET)
                db.commit()

                logger.info(f"Sent email {send_record.id} to {send_record.recipient_email}")

                # Random delay 30-90s between sends
                delay = random.randint(30, 90)
                import time as _time
                _time.sleep(delay)

            except Exception as e:
                logger.exception(f"Failed to send email {send_record.id}")
                send_record.status = "failed"
                send_record.error_message = str(e)
                db.commit()

    except Exception:
        logger.exception("Error in send executor")
    finally:
        db.close()


def _replace_greeting(body: str, new_recipient_name: str, new_recipient_title: str) -> str:
    """Replace the greeting line of an email body with a new one for a different recipient.

    Instead of trying to pattern-match and swap the old name, we just replace
    the entire first line (which is always the greeting) with a freshly built one.
    """
    new_greeting = build_greeting(new_recipient_name, new_recipient_title)

    lines = body.split("\n", 1)
    if len(lines) == 2:
        return new_greeting + "\n" + lines[1]
    else:
        return new_greeting + "\n" + body


def daily_summary():
    """5 PM ET - Log a daily summary for each active campaign."""
    logger.info("Running daily summary...")
    db: Session = SessionLocal()

    try:
        today = datetime.now(ET).date()
        campaigns = db.query(Campaign).filter(Campaign.status == "active").all()

        for campaign in campaigns:
            sent_today = db.query(func.count(Send.id)).filter(
                Send.campaign_id == campaign.id,
                Send.status == "sent",
                Send.scheduled_for == today,
            ).scalar() or 0

            total_sent = db.query(func.count(Send.id)).filter(
                Send.campaign_id == campaign.id,
                Send.status == "sent",
            ).scalar() or 0

            bounced_today = db.query(func.count(Send.id)).filter(
                Send.campaign_id == campaign.id,
                Send.status == "bounced",
                Send.scheduled_for == today,
            ).scalar() or 0

            replied_today = db.query(func.count(Send.id)).filter(
                Send.campaign_id == campaign.id,
                Send.status == "replied",
                Send.scheduled_for == today,
            ).scalar() or 0

            total_constituents = db.query(func.count(Constituent.id)).filter(
                Constituent.campaign_id == campaign.id,
            ).scalar() or 0

            logger.info(
                f"[{campaign.name}] "
                f"Sent today: {sent_today} | Total sent: {total_sent} | "
                f"Bounces today: {bounced_today} | Replies today: {replied_today} | "
                f"Constituents: {total_constituents}"
            )

    except Exception:
        logger.exception("Error in daily summary")
    finally:
        db.close()
