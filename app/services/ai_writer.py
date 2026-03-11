import logging
from openai import OpenAI
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

client = OpenAI(api_key=settings.OPENAI_API_KEY)

MODEL = "gpt-4o"


def generate_email_body(
    first_name: str,
    last_initial: str,
    city: str,
    riding: str,
    recipient_name: str,
    recipient_title: str,
    issue_brief: str,
    personal_concern: str | None = None,
    tone_instructions: str | None = None,
    display_name: str = "",
) -> str:
    """Generate a personalized constituent letter using GPT-4o."""
    concern_line = ""
    if personal_concern:
        concern_line = f"\nThe constituent's personal concern: {personal_concern}\n"

    tone_line = ""
    if tone_instructions:
        tone_line = f"\nCampaign operator instructions for tone and content:\n{tone_instructions}\n"

    system_prompt = f"""You are writing a letter from a constituent to their elected representative about pending legislation.

The constituent is: {first_name} {last_initial}., from {city} ({riding}).
They are writing to: {recipient_name}, {recipient_title}.

Issue brief:
{issue_brief}
{concern_line}{tone_line}
Write a personalized, genuine-sounding letter. 3-4 paragraphs. The tone should be respectful but firm - this is a real person who cares about this issue. Reference their city naturally. Each letter must be unique - vary sentence structure, opening lines, arguments, and closing. Do not use form-letter language.

Sign the letter as: {display_name}, {city}

Do not include any headers, subject lines, or metadata. Just the letter body."""

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Write the letter now."},
        ],
    )

    body = response.choices[0].message.content.strip()
    logger.info(f"Generated email body for {first_name} {last_initial}. ({len(body)} chars)")
    return body


def generate_subject_line(
    recipient_name: str,
    recipient_title: str,
    campaign_name: str,
) -> str:
    """Generate a short, natural email subject line using GPT-4o."""
    prompt = f"""Write a short, natural email subject line (under 60 chars) for a constituent letter to {recipient_title} {recipient_name} about {campaign_name}. Make it sound personal, not like a form letter. Just output the subject line, nothing else."""

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=100,
        messages=[
            {"role": "user", "content": prompt},
        ],
    )

    subject = response.choices[0].message.content.strip().strip('"').strip("'")
    logger.info(f"Generated subject: {subject}")
    return subject
