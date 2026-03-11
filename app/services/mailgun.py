import httpx
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def send_email(
    from_address: str,
    from_display_name: str,
    to_email: str,
    subject: str,
    body: str,
    riding: str = "",
) -> dict:
    """Send an email via Mailgun HTTP API. Returns response dict with 'id' on success."""
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

    async with httpx.AsyncClient() as client:
        response = await client.post(
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
