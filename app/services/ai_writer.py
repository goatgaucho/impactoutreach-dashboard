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
        "weight": 5,
        "description": "Write in a formal, polished style. Use complete sentences and proper grammar. This person is comfortable with professional correspondence.",
    },
    {
        "formality": "conversational",
        "weight": 20,
        "description": "Write in a warm, conversational style. Friendly but earnest — like someone writing to a neighbor they respect. Shorter sentences. Sincere but not stiff.",
    },
    {
        "formality": "direct",
        "weight": 20,
        "description": "Write in a direct, no-nonsense style. Get to the point fast. This person doesn't mince words — they state their concern and expect action.",
    },
    {
        "formality": "passionate",
        "weight": 10,
        "description": "Write with visible passion. This person deeply cares and it shows. They're not angry, but they are fired up and want to be heard.",
    },
    {
        "formality": "casual",
        "weight": 25,
        "description": "Write in a casual, everyday style. This person doesn't write formal letters — the language is simple, maybe a bit rough around the edges, but genuine. Use contractions, sentence fragments are OK.",
    },
    {
        "formality": "rushed",
        "weight": 15,
        "description": "Write like someone who is busy and dashing off a quick email. Short, to the point, not perfectly structured. They care about the issue but aren't spending a lot of time crafting this. A few sentences is fine.",
    },
    {
        "formality": "folksy",
        "weight": 5,
        "description": "Write like a small-town person who speaks plainly. Use colloquial language, everyday expressions. This person talks the way they write — no pretense, just straight talk.",
    },
]

# Weighted length distribution: ~90% short, ~10% longer
LENGTH_INSTRUCTIONS = [
    {"instruction": "Write 3-5 sentences total. One short paragraph. This person keeps it brief.", "weight": 40},
    {"instruction": "Write 2 very short paragraphs, maybe 4-6 sentences total. Keep it tight.", "weight": 30},
    {"instruction": "Write 1 paragraph, 3-4 sentences. Very short and to the point.", "weight": 20},
    {"instruction": "Write 2-3 paragraphs of moderate length. This person had more to say.", "weight": 7},
    {"instruction": "Write 3 short paragraphs with some specific details.", "weight": 3},
]

OPENING_INSTRUCTIONS = [
    "Start by jumping right into the issue — no preamble.",
    "Open with why this issue affects you personally.",
    "Start with a brief mention of your city and what you've noticed.",
    "Open with a question about the issue.",
    "Start with a direct statement about what you want to see happen.",
    "Begin with something you heard or read about this issue recently.",
    "Just get right to the point — say what you need to say.",
]

CLOSING_STYLES = [
    "End with a simple thanks and your name.",
    "Just stop after your last point. Sign your name.",
    "End with a question, then sign off.",
    "Trail off with something like 'anyway, just wanted to say something' then your name.",
    "End with a short ask, then 'thanks' and your name.",
    "Just sign off with your name, no closing statement.",
    "End with 'appreciate your time' or similar, then name.",
    "Last sentence is about what you hope happens, then just your name.",
]

# ~20% of emails should have imperfections (typos, missing caps, etc.)
POLISH_LEVELS = [
    {
        "level": "clean",
        "weight": 40,
        "instruction": "",
    },
    {
        "level": "slightly_rough",
        "weight": 30,
        "instruction": "Write with slightly imperfect grammar — maybe a run-on sentence, a missing comma, or an awkward phrase. Nothing major, just not perfectly polished. Like a real person who didn't proofread carefully.",
    },
    {
        "level": "messy",
        "weight": 20,
        "instruction": "Include 1-2 small typos or spelling errors (e.g., 'teh' instead of 'the', 'goverment' instead of 'government', 'thier' instead of 'their'). Maybe miss a capital letter at the start of a sentence, or use a comma splice. This person typed this out quickly and didn't proofread. Keep the errors subtle and natural — NOT every sentence, just a couple spots.",
    },
    {
        "level": "very_rough",
        "weight": 10,
        "instruction": "Write with noticeable imperfections: 2-3 typos or misspellings, inconsistent capitalization (maybe 'i' instead of 'I' once or twice), a sentence fragment, or a missing period. This person is not a strong writer — they're writing from the heart but their grammar isn't perfect. Keep errors realistic, not exaggerated.",
    },
]


def _weighted_choice(options: list[dict]) -> dict:
    """Pick a random option using the 'weight' field."""
    weights = [o["weight"] for o in options]
    return random.choices(options, weights=weights, k=1)[0]


# Common first names for gender inference (not exhaustive, but covers most cases)
FEMALE_NAMES = {
    "abigail", "alison", "amanda", "amber", "amy", "andrea", "angela", "anna",
    "anne", "ashley", "barb", "barbara", "beth", "bonnie", "brenda", "caitlin",
    "carol", "caroline", "catherine", "celine", "charlene", "charlotte",
    "cheryl", "christine", "cindy", "claire", "colleen", "courtney", "crystal",
    "dana", "dawn", "debbie", "deborah", "denise", "diana", "diane", "donna",
    "dorothy", "eileen", "elizabeth", "emily", "emma", "erin", "fatima",
    "fiona", "frances", "grace", "heather", "helen", "iryna", "isabel",
    "jackie", "jaeda", "jane", "janet", "jasmine", "jennifer", "jessica",
    "jill", "joanne", "julie", "karen", "kate", "katherine", "katie", "kayla",
    "kelley", "kelly", "kimberly", "laura", "lauren", "leanne", "linda",
    "lindsay", "lisa", "lori", "lynn", "mai", "margaret", "maria", "marie",
    "marjorie", "mary", "megan", "melissa", "michelle", "monica", "nancy",
    "natalie", "nicole", "olena", "olivia", "pam", "pamela", "patricia",
    "pauline", "priya", "rachel", "rebecca", "renee", "robin", "rosa", "ruth",
    "sandra", "sarah", "sharon", "sherry", "sophie", "stacey", "stephanie",
    "susan", "tammy", "tanya", "tara", "teresa", "theresa", "tina", "tracy",
    "valerie", "vanessa", "victoria", "wendy", "ying", "asha", "phuong",
    "linh",
}

MALE_NAMES = {
    "aaron", "abdi", "adam", "ahmed", "alan", "alex", "andrew", "anthony",
    "balwinder", "ben", "benjamin", "bill", "brad", "brandon", "brent",
    "brett", "brian", "bruce", "carlo", "chad", "charles", "chris",
    "christopher", "craig", "curtis", "dale", "daniel", "darren", "dave",
    "david", "dean", "derek", "diego", "donald", "doug", "douglas", "dustin",
    "earl", "ed", "edward", "eric", "frank", "gary", "george", "glen",
    "gordon", "grant", "greg", "gregory", "gurpreet", "hai", "harpreet",
    "jack", "james", "jason", "jeff", "jeffrey", "jerome", "jim", "joe",
    "john", "jonathan", "jordan", "joseph", "josh", "joshua", "jun", "justin",
    "keith", "ken", "kenneth", "kevin", "kyle", "larry", "lee", "mark",
    "martin", "matt", "matthew", "michael", "mike", "mohammed", "nathan",
    "neil", "nick", "patrick", "paul", "peter", "phil", "philip", "rajvir",
    "mandeep", "amrit", "randy", "ray", "richard", "rick", "rob", "robert",
    "roger", "ron", "russell", "ryan", "samuel", "scott", "sean", "shane",
    "steve", "steven", "thomas", "tim", "timothy", "todd", "tom", "tony",
    "travis", "trevor", "troy", "tyler", "wade", "wayne", "wei",
    "william",
}


def _infer_gender(first_name: str) -> str:
    """Infer likely gender from first name. Returns 'male', 'female', or 'unknown'."""
    name = first_name.strip().lower()
    if name in FEMALE_NAMES:
        return "female"
    if name in MALE_NAMES:
        return "male"
    return "unknown"


def _is_actual_minister(title: str) -> bool:
    """Check if the title indicates the person IS a minister (not just an advisor to one)."""
    t = (title or "").strip().lower()
    # "Minister of X" or "Minister for X" = actual minister
    # "Advisor to the Minister" or "Regional Advisor to the Minister" = NOT a minister
    if not t:
        return False
    return t.startswith("minister")


def _is_mp(title: str) -> bool:
    """Check if the title indicates the person is an MP."""
    t = (title or "").strip().lower()
    return "member of parliament" in t or t == "mp" or t.startswith("mp ")


def build_greeting(recipient_name: str, recipient_title: str) -> str:
    """Build an appropriate greeting based on name, title, and inferred gender."""
    recipient_first = recipient_name.split()[0] if recipient_name else recipient_name
    recipient_last = recipient_name.split()[-1] if recipient_name else recipient_name
    gender = _infer_gender(recipient_first)

    # Determine honorific based on gender
    if gender == "female":
        honorific = "Ms."
    elif gender == "male":
        honorific = "Mr."
    else:
        honorific = None  # Skip Mr./Ms. if we can't tell

    # Base greeting options using first name or full name
    greeting_options = [
        f"Hi {recipient_name},",
        f"Hey {recipient_name},",
        f"Dear {recipient_name},",
        f"To {recipient_name},",
        f"{recipient_name},",
        f"Hello {recipient_name},",
        f"Hello,",
    ]

    # Add honorific options only if we know the gender
    if honorific:
        greeting_options += [
            f"Dear {honorific} {recipient_last},",
            f"{honorific} {recipient_last},",
            f"Hi {honorific} {recipient_last},",
        ]

    # Add title-based options only if they actually hold that title
    if _is_actual_minister(recipient_title):
        greeting_options += [
            f"Dear Minister {recipient_last},",
            f"To Minister {recipient_last},",
            f"Hi Minister {recipient_last},",
            f"Minister {recipient_last},",
        ]
    elif _is_mp(recipient_title):
        greeting_options += [
            f"Dear MP {recipient_last},",
            f"To MP {recipient_last},",
            f"Hi MP {recipient_last},",
            f"MP {recipient_last},",
        ]

    return random.choice(greeting_options)


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
    style = _weighted_choice(WRITING_STYLES)
    opening = random.choice(OPENING_INSTRUCTIONS)
    length = _weighted_choice(LENGTH_INSTRUCTIONS)
    closing = random.choice(CLOSING_STYLES)
    polish = _weighted_choice(POLISH_LEVELS)

    polish_instruction = ""
    if polish["instruction"]:
        polish_instruction = f"\nIMPERFECTIONS: {polish['instruction']}\n"

    greeting = build_greeting(recipient_name, recipient_title)

    system_prompt = f"""You are writing an email from a real person to their elected representative.

The person is: {first_name} {last_initial}., from {city} ({riding}).
They are writing to: {recipient_name}, {recipient_title}.

Issue brief:
{issue_brief}
{concern_line}{tone_line}
WRITING STYLE: {style['description']}

LENGTH: {length['instruction']}
{polish_instruction}
STRUCTURE:
- {opening}
- {closing}

GREETING: Start the email with exactly this greeting: {greeting}

CRITICAL RULES:
- NEVER use: "I am writing to express my concern", "Furthermore", "Moreover", "Additionally", "It's worth noting", "It's important to understand", "In conclusion", "delve", "landscape", "nuanced", "invaluable", "shed light", "groundbreaking", "endeavor".
- NEVER use em dashes (—). Real people use commas, periods, or just mash two thoughts together with "and".
- NEVER use "It's not about X, it's about Y" constructions.
- NEVER use "Whether you're A, B, or C..." patterns or repeated rule-of-three lists.
- NO bullet points, headers, bold text, or any formatting. It's an email, not a report.
- NO tidy recap or closing summary. Some emails just stop. Some end with "thanks" or just a name. Some trail off with a question.
- Emotion comes through word choice. People say "this is ridiculous" not "I am deeply troubled."
- Vary sentence length. Some short. Some that go on a bit longer than they probably should because the person is mid-thought and just keeps typing.
- This must read like a real person typed it, not a polished template.
- Keep it natural. Real emails are often short, imperfect, and to the point.

Sign off as: {display_name}, {city}

Output ONLY the email body. No headers, subject lines, or metadata."""

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=512,
        temperature=1.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Write the email now."},
        ],
    )

    body = response.choices[0].message.content.strip()

    # Hard post-processing: remove em dashes no matter what GPT outputs
    body = body.replace("\u2014", ",")   # em dash
    body = body.replace("\u2013", ",")   # en dash
    body = body.replace(" ,", ",")       # clean up double spaces before comma
    body = body.replace(",,", ",")       # clean up double commas

    logger.info(f"Generated email for {first_name} {last_initial}. (style={style['formality']}, polish={polish['level']}, {len(body)} chars)")
    return body


def generate_subject_line(
    recipient_name: str,
    recipient_title: str,
    campaign_name: str,
    constituent_name: str = "",
) -> str:
    """Generate a consistent subject line: '<Name> | <Campaign Name> Campaign'."""
    subject = f"{constituent_name} | {campaign_name} Campaign"
    logger.info(f"Generated subject: {subject}")
    return subject
