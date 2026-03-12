import logging
import random
from openai import OpenAI
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

client = OpenAI(api_key=settings.OPENAI_API_KEY)

MODEL = "gpt-4o"

# Writing style variations to make each email sound like a different person
WRITING_STYLES = [
    {
        "formality": "formal",
        "description": "Write in a formal, polished style. Use complete sentences, proper grammar, and a respectful tone throughout. This person writes like someone comfortable with professional correspondence.",
    },
    {
        "formality": "conversational",
        "description": "Write in a warm, conversational style. Use a friendly but earnest tone — like someone writing to a neighbor they respect. Shorter sentences are fine. This person is sincere but not stiff.",
    },
    {
        "formality": "direct",
        "description": "Write in a direct, no-nonsense style. Get to the point quickly. This person doesn't mince words — they state their concern clearly and expect action. Keep it concise.",
    },
    {
        "formality": "passionate",
        "description": "Write with visible passion and emotion. This person deeply cares about this issue and it shows in their word choice. They're not angry, but they are fired up and want to be heard.",
    },
    {
        "formality": "thoughtful",
        "description": "Write in a measured, thoughtful style. This person has clearly done their research and thinks carefully before writing. They ask good questions and present nuanced arguments.",
    },
    {
        "formality": "casual",
        "description": "Write in a casual, everyday style. This person doesn't write formal letters often — the language is simple and straightforward, maybe a bit rough around the edges, but genuine and heartfelt.",
    },
]

OPENING_INSTRUCTIONS = [
    "Start the letter by introducing yourself and your connection to the community.",
    "Open by referencing the specific issue and why it matters to you personally.",
    "Begin with a brief mention of your city and what you've noticed locally.",
    "Start by expressing why you felt compelled to write today.",
    "Open with a direct statement about what you'd like to see happen.",
    "Begin by sharing a brief personal anecdote related to this issue.",
    "Start with a question directed at the recipient about the issue.",
    "Open by referencing something specific about the recipient's role or recent actions.",
]

LENGTH_INSTRUCTIONS = [
    "Write 2-3 short paragraphs. Keep it brief — this person values brevity.",
    "Write 3-4 paragraphs of moderate length.",
    "Write 3 well-developed paragraphs with specific details.",
    "Write 4 paragraphs — this person has a lot to say on this topic.",
]

CLOSING_STYLES = [
    "End with a forward-looking statement about what you hope to see.",
    "Close by reiterating your main concern in one sentence.",
    "End by thanking them for their time and public service.",
    "Close with a specific ask — what action do you want them to take?",
    "End on a personal note about why this matters to your family or community.",
    "Close by expressing confidence that the recipient will do the right thing.",
]


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

    # Randomly select writing style parameters for this email
    style = random.choice(WRITING_STYLES)
    opening = random.choice(OPENING_INSTRUCTIONS)
    length = random.choice(LENGTH_INSTRUCTIONS)
    closing = random.choice(CLOSING_STYLES)

    system_prompt = f"""You are writing a letter from a real constituent to their elected representative.

The constituent is: {first_name} {last_initial}., from {city} ({riding}).
They are writing to: {recipient_name}, {recipient_title}.

Issue brief:
{issue_brief}
{concern_line}{tone_line}
WRITING STYLE: {style['description']}

STRUCTURE:
- {opening}
- {length}
- {closing}

CRITICAL RULES:
- Do NOT start with "I hope this message finds you well" or any variation of that phrase.
- Do NOT use generic openings like "I am writing to express my concern" — be specific and natural.
- This must read like a real person wrote it, not a template. Vary vocabulary, sentence length, and rhythm.
- Reference the constituent's city naturally but don't force it.
- The greeting should fit the formality level — "Dear {recipient_name}," or "Hello," or just the name, etc.

Sign the letter as: {display_name}, {city}

Do not include any headers, subject lines, or metadata. Just the letter body."""

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=1024,
        temperature=1.1,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Write the letter now."},
        ],
    )

    body = response.choices[0].message.content.strip()
    logger.info(f"Generated email body for {first_name} {last_initial}. (style={style['formality']}, {len(body)} chars)")
    return body


def generate_subject_line(
    recipient_name: str,
    recipient_title: str,
    campaign_name: str,
    constituent_name: str = "",
) -> str:
    """Generate a consistent subject line: '<Constituent Name> Feedback for <Campaign Name>'."""
    subject = f"{constituent_name} Feedback for {campaign_name}"
    logger.info(f"Generated subject: {subject}")
    return subject
