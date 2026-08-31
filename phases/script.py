"""
Knights Reactor — Script Generation (GPT-4o)
"""
import json, re
import requests
from config import Config, log


def _active_brand_name() -> str:
    """Get the active brand id — used to scope the hardcoded knight defaults
    (persona, voice, themes, category framing) to the 'knights' brand only.
    Any other brand gets brand-neutral fallbacks instead of inheriting
    Knights' biblical/military voice by accident."""
    try:
        from server import get_active_brand
        return get_active_brand()
    except Exception:
        return "knights"


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
GENERIC_PERSONA = (
    "A confident, knowledgeable expert:\n"
    "- Direct, practical, trustworthy\n"
    "- Not salesy, not preachy—clear and helpful\n"
    "- Focused on real results for the viewer\n"
    "- Speaks plainly, backs claims with specifics"
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
GENERIC_VOICE = (
    "- Clear, confident, easy to follow\n"
    "- Short, declarative sentences\n"
    "- Measured pacing\n"
    "- Grounded and credible\n"
    "- NO hype. NO motivational fluff."
)
KNIGHTS_THEMES = (
    "Address real daily battles: Finances, family leadership, temptation, fatigue, doubt, lust, anger, responsibility, endurance, obedience.\n\n"
    "Core themes: Discipline over comfort. Duty over desire. Endurance over escape. Faith over fear. Action over emotion."
)
GENERIC_THEMES = (
    "Address a real, specific problem the viewer is dealing with right now.\n\n"
    "Core themes: Clarity over confusion. Action over hesitation. Results over excuses."
)
KNIGHTS_AVOID = "Warmth or sentimentality, soft encouragement, modern slang, politics, long scripture quotations, hashtags."
GENERIC_AVOID = "Vague generalities, corporate jargon, modern slang, politics, hashtags."

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

# Brand-neutral equivalent of CATEGORY_CONFIG — used for every brand except
# "knights", so a non-faith brand doesn't get military/scripture framing
# baked into its hook/tone/angle regardless of its own persona settings.
GENERIC_CATEGORY_CONFIG = {
    "Shocking Revelations": {
        "hook_patterns": ["Direct: 'Most people miss this until it's too late.'", "Challenge: 'You're closer to this problem than you think.'"],
        "tone": "urgent, attention-grabbing",
        "angle": "expose a problem most people are overlooking",
    },
    "Shocking Reveal": {
        "hook_patterns": ["Direct: 'Here's what nobody tells you.'", "Challenge: 'The fix is simpler than you think — why aren't you doing it?'"],
        "tone": "confident, no-nonsense",
        "angle": "call viewers to take immediate action",
    },
    "Behind-the-Scenes": {
        "hook_patterns": ["Direct: 'This is what actually happens behind the scenes.'", "Challenge: 'Nobody sees the work before the result.'"],
        "tone": "raw, insider perspective",
        "angle": "show the hidden day-to-day reality",
    },
    "Myths Debunked": {
        "hook_patterns": ["Direct: 'Everything you've heard about this is wrong.'", "Challenge: 'That common advice? It's costing you.'"],
        "tone": "myth-breaking, direct challenge",
        "angle": "correct a widely-believed misconception",
    },
    "Deep Dive Analysis": {
        "hook_patterns": ["Direct: 'Look closer — the real answer is easy to miss.'", "Challenge: 'A surface glance won't cut it here.'"],
        "tone": "thoughtful, focused",
        "angle": "unpack the topic in depth",
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
    """Build the script prompt dynamically from Config values and brand persona.
    Falls back to the Knights persona/voice/themes/structure only for the
    'knights' brand — any other brand gets brand-neutral fallbacks so an
    unrelated business (e.g. a home-services brand) doesn't inherit
    biblical/military framing it never asked for."""
    words = int(Config.SCRIPT_WORDS)
    secs = round(words / 3)
    low = max(words - 10, 20)
    high = words + 10
    is_knights = _active_brand_name() == "knights"

    # Brand persona (from settings) or brand-appropriate defaults
    persona = getattr(Config, 'BRAND_PERSONA', '') or (KNIGHTS_PERSONA if is_knights else GENERIC_PERSONA)
    voice = getattr(Config, 'BRAND_VOICE', '') or (KNIGHTS_VOICE if is_knights else GENERIC_VOICE)
    themes = getattr(Config, 'BRAND_THEMES', '') or (KNIGHTS_THEMES if is_knights else GENERIC_THEMES)
    avoid = getattr(Config, 'BRAND_AVOID', '') or (KNIGHTS_AVOID if is_knights else GENERIC_AVOID)

    # The structure section below is worded around Knights' military/scripture
    # framing — genericize it for every other brand regardless of persona,
    # since these lines are baked into the template, not sourced from Config.
    if is_knights:
        build_line = "Name the specific battle. The real struggle men face daily. Paint the scene with military imagery."
        # {scripture} is filled per-generation by render_script_prompt() from
        # THIS topic's own assigned scripture field — naming the exact verse
        # here (instead of leaving GPT to pick one) is what actually varies
        # the reference video-to-video instead of it defaulting to whatever
        # verse happens to be named elsewhere in the prompt.
        reveal_line = "The truth. Weave in this scripture naturally, in your own words (not a direct quote): {scripture}. Military language. The weapon or shield for this battle."
        reveal_json_hint = "Scripture truth, NO QUOTES"
        tone_options = "disciplined|resolute|commanding|unwavering"
        use_line = "Direct honest practical language, brief scripture references woven naturally, one clear action for today."
    else:
        build_line = "Name the specific problem. The real struggle the viewer is dealing with. Paint a vivid, concrete scene."
        reveal_line = "The insight or solution. Concrete and specific — the thing that actually fixes the problem."
        reveal_json_hint = "The core insight or solution, NO QUOTES"
        tone_options = "confident|direct|practical|urgent"
        use_line = "Direct honest practical language, concrete specifics, one clear action for today."

    return f"""## ⚠️ WORD COUNT: ~{words} WORDS ⚠️

TOTAL SCRIPT: {low}-{high} WORDS ({secs} seconds at measured pace — 3 words/sec)

Before you output, COUNT YOUR WORDS. Target exactly {words}. Too short sounds rushed. Too long gets cut off.

---

## CHARACTER

{persona}

## VOICE

{voice}

## TONE & MESSAGE

{themes}

What to AVOID: {avoid}

What to USE: {use_line}

## VOICEOVER RULES

- Short, declarative sentences
- Period after each complete thought
- NO quotes around any words
- ONE continuous paragraph
- Clean punctuation: periods only (rarely commas)

## SCRIPT STRUCTURE ({secs} seconds / ~{words} words)

### 1. HOOK (first ~15% of words)
Immediate call to attention. VARY the opener. Draw them in with a bold statement or question.

### 2. BUILD (next ~30% of words)
{build_line}

### 3. REVEAL (next ~30% of words)
{reveal_line}

### 4. COMMAND (final ~25% of words)
One clear action. Today. Now. End with a strong imperative. Leave them ready to move.

## YOUR ASSIGNMENT

**TOPIC:** {{topic}}
**CATEGORY:** {{category}}
**SUGGESTED FOCUS:** {{angle}}

## OUTPUT FORMAT (JSON only, no markdown):

{{
  "hook": "Bold opener, NO QUOTES",
  "build": "Name the core problem or challenge, NO QUOTES",
  "reveal": "{reveal_json_hint}",
  "command": "Clear action for today, NO QUOTES",
  "script_full": "Complete script ~{words} words - SHORT DECLARATIVE SENTENCES - NO QUOTES - ONE PARAGRAPH",
  "tone": "{tone_options}"
}}
"""


def generate_script(topic: dict) -> dict:
    """Generate viral knight script via GPT-4o."""
    log.info(f"📝 Phase 2: Generating script via {Config.SCRIPT_MODEL} | Words: {Config.SCRIPT_WORDS} | ~{round(int(Config.SCRIPT_WORDS)/3)}s")

    cat = topic["category"]
    cfg_source = CATEGORY_CONFIG if _active_brand_name() == "knights" else GENERIC_CATEGORY_CONFIG
    config = cfg_source.get(cat, list(cfg_source.values())[0])
    angle = config["angle"]

    prompt = render_script_prompt(build_script_prompt(), topic["idea"], cat, angle, topic.get("scripture", ""))

    r = requests.post("https://api.openai.com/v1/chat/completions", headers={
        "Authorization": f"Bearer {Config.OPENAI_KEY}", "Content-Type": "application/json",
    }, json={
        "model": Config.SCRIPT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": Config.SCRIPT_TEMP, "max_tokens": 800,
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

    wc = len(script["script_full"].split())
    log.info(f"   Script: {wc} words — {script['hook'][:60]}...")
    return script
