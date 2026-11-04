"""
Knights Reactor — Script Generation (GPT-4o)
"""
import json, re
import requests
from config import Config, log
from phases.story import script_story_block
from phases.film_blueprint import select_character, film_assignment, validate_film_blueprint


# Note: this used to say "Wears the Armor of God (Ephesians 6) symbolically"
# — that explicit verse citation, appearing in EVERY script prompt regardless
# of topic, was why nearly every generated script quoted Ephesians 6 no
# matter what the topic's own assigned scripture was. The actual verse to
# use now comes from each topic's "scripture" field via the {scripture}
# placeholder in default_script_prompt()'s reveal_line below, so the
# character description no longer needs (or should) name one itself.
KNIGHTS_PERSONA = (
    "A battle-hardened Christian knight:\n"
    "- Strong, disciplined, capable, calm\n"
    "- Not cruel, not cold—firm and compassionate\n"
    "- Protector of faith, family, duty, truth\n"
    "- Lives in peace but ready for war\n"
    "- Wears the Armor of God symbolically\n"
    "- Unwavering allegiance: Christ is King"
)
KNIGHTS_VOICE = (
    "- Low, controlled, resonant\n"
    "- Calm intensity; authoritative without shouting\n"
    "- Short, declarative sentences\n"
    "- Measured pacing\n"
    "- Dark, mysterious presence—disciplined resolve\n"
    "- Masculine and grounded\n"
    "- NO hype. NO motivational fluff."
)
KNIGHTS_THEMES = (
    "Address real daily battles: Finances, family leadership, temptation, fatigue, doubt, lust, anger, responsibility, endurance, obedience.\n\n"
    "Core themes: Discipline over comfort. Duty over desire. Endurance over escape. Faith over fear. Action over emotion."
)
KNIGHTS_AVOID = "Warmth or sentimentality, soft encouragement, modern slang, politics, long scripture quotations, hashtags."

CATEGORY_CONFIG = {
    "Shocking Revelations": {
        "hook_patterns": ["Direct: 'The enemy already moved. Did you?'", "Challenge: 'Most men quit before the real fight starts.'"],
        "tone": "battlefield urgency, commanding presence",
        "angle": "expose the spiritual battle most men are losing",
    },
    "Shocking Reveal": {
        "hook_patterns": ["Direct: 'You were trained for this. Act like it.'", "Challenge: 'The armor is there. Why aren't you wearing it?'"],
        "tone": "commanding, no excuses",
        "angle": "call men to immediate action",
    },
    "Behind-the-Scenes": {
        "hook_patterns": ["Direct: 'This is what the daily grind actually looks like.'", "Challenge: 'Nobody sees the battle before dawn.'"],
        "tone": "raw insider, unfiltered reality",
        "angle": "show the invisible daily war",
    },
    "Myths Debunked": {
        "hook_patterns": ["Direct: 'Strength without discipline is just noise.'", "Challenge: 'That comfort zone? It is your cage.'"],
        "tone": "myth-breaking, direct challenge",
        "angle": "shatter comfortable lies",
    },
    "Deep Dive Analysis": {
        "hook_patterns": ["Direct: 'Look deeper. The answer is in the text.'", "Challenge: 'Surface reading misses the sword.'"],
        "tone": "scholarly intensity, focused revelation",
        "angle": "deep scripture analysis",
    },
}



def render_script_prompt(template: str, topic_idea: str, category: str, angle: str, scripture: str = "") -> str:
    """Fill {topic}/{category}/{angle}/{scripture} placeholders via plain
    substring replacement rather than str.format() — a Settings-tab prompt
    override can contain a literal JSON example (unescaped { }) without
    needing to know about Python format-string escaping."""
    scripture_line = scripture.strip() if scripture else (
        "one that genuinely fits this specific topic — pick a DIFFERENT "
        "verse than you'd use for other topics, don't default to a single "
        "go-to reference"
    )
    return (template
            .replace("{topic}", topic_idea)
            .replace("{category}", category)
            .replace("{angle}", angle)
            .replace("{scripture}", scripture_line))


def build_script_prompt():
    """Return the script prompt template. If Settings > Script has a custom
    override (Config.SCRIPT_PROMPT_TEMPLATE), use it verbatim — otherwise
    build the brand-aware default. Either way the result still contains
    {topic}/{category}/{angle} placeholders for render_script_prompt() to
    fill in per-generation."""
    override = getattr(Config, 'SCRIPT_PROMPT_TEMPLATE', '')
    if override:
        return override
    return default_script_prompt()


def default_script_prompt():
    """Film screenplay + narration, generated as one creative work."""
    words = int(Config.SCRIPT_WORDS)
    low, high = max(words - 10, 20), words + 10
    return f"""You are an experienced short-film screenwriter. Write a complete
dramatic story with a protagonist, obstacle, an observable choice and a
consequence. The visual action and voiceover are ONE screenplay.

NARRATION: {low}-{high} words total; about {round(words / 3)} seconds.
The narration must be natural, contemporary and human. Do not recite a
motivational speech or explain everything visible on screen. The character's
actions must tell the core story if the audio is muted.

TOPIC: {{topic}}
CATEGORY: {{category}}
FOCUS: {{angle}}
SCRIPTURE / FAITH CONTEXT: {{scripture}}

If a specific verse is supplied, reflect its meaning accurately without
forcing an unrelated quotation or theological claim.
Avoid sermons, commands to the audience, archaic diction, vague symbols,
stock cinematic imagery, grandiose slogans and fake medieval speech.
Make the decision and its cost concrete. The ending should feel earned.

The FILM STUDIO RULES and complete JSON screenplay schema appended below
are authoritative. Return one complete JSON object.
"""


def generate_script(topic: dict) -> dict:
    """Generate viral knight script via GPT-4o."""
    log.info(f"📝 Phase 2: Generating script via {Config.SCRIPT_MODEL} | Words: {Config.SCRIPT_WORDS} | ~{round(int(Config.SCRIPT_WORDS)/3)}s")

    cat = topic["category"]
    config = CATEGORY_CONFIG.get(cat, list(CATEGORY_CONFIG.values())[0])
    angle = config["angle"]

    prompt = render_script_prompt(build_script_prompt(), topic["idea"], cat, angle, topic.get("scripture", ""))
    prompt += script_story_block(topic)   # episode of The Last Watch, if this topic is one
    # Cast is chosen BEFORE writing and locked into the film and every shot.
    locked_character = select_character(topic)
    prompt += "\n\n" + film_assignment(locked_character)
    director_brief = str(getattr(Config, "CREATIVE_DIRECTION", "") or "").strip()
    if director_brief:
        prompt += "\n\n## CREATIVE BRIEF — APPLY TO THIS VIDEO\n" + director_brief[:3000]

    r = requests.post("https://api.openai.com/v1/chat/completions", headers={
        "Authorization": f"Bearer {Config.OPENAI_KEY}", "Content-Type": "application/json",
    }, json={
        "model": Config.SCRIPT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": Config.SCRIPT_TEMP, "max_tokens": 2400,
        "response_format": {"type": "json_object"}, "timeout": 90,
    })
    r.raise_for_status()

    text = r.json()["choices"][0]["message"]["content"]
    raw = re.sub(r'^```json\s*\n?', '', text, flags=re.IGNORECASE)
    raw = re.sub(r'\n?```\s*$', '', raw).strip()

    try:
        script = json.loads(raw)
    except json.JSONDecodeError:
        sentences = re.findall(r'[^.!?]+[.!?]+', raw) or [raw]
        script = {
            "hook": sentences[0].strip() if len(sentences) > 0 else "",
            "build": sentences[1].strip() if len(sentences) > 1 else "",
            "reveal": sentences[2].strip() if len(sentences) > 2 else "",
            "command": sentences[3].strip() if len(sentences) > 3 else "",
            "script_full": raw.strip(),
        }

    script = {
        "hook": str(script.get("hook", "")).strip(),
        "build": str(script.get("build", "")).strip(),
        "reveal": str(script.get("reveal", "")).strip(),
        "command": str(script.get("command", "")).strip(),
        "script_full": str(script.get("script_full", "")).strip(),
        "tone": str(script.get("tone", "commanding")),
    }

    script["film_blueprint"] = validate_film_blueprint(
        json.loads(raw).get("film_blueprint") if isinstance(json.loads(raw), dict) else None,
        locked_character,
    )
    wc = len(script["script_full"].split())
    log.info(f"   Script: {wc} words — {script['hook'][:60]}...")
    return script
