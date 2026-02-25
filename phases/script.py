"""
Knights Reactor — Script Generation (GPT-4o)
"""
import json, re
import requests
from config import Config, log

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


def build_script_prompt():
    """Build the script prompt dynamically from Config values and brand persona."""
    words = int(Config.SCRIPT_WORDS)
    secs = round(words / 3)
    low = max(words - 10, 20)
    high = words + 10

    # Brand persona (from settings) or defaults
    persona = getattr(Config, 'BRAND_PERSONA', '') or (
        "A battle-hardened Christian knight:\n"
        "- Strong, disciplined, capable, calm\n"
        "- Not cruel, not cold—firm and compassionate\n"
        "- Protector of faith, family, duty, truth\n"
        "- Lives in peace but ready for war\n"
        "- Wears the Armor of God (Ephesians 6) symbolically\n"
        "- Unwavering allegiance: Christ is King"
    )
    voice = getattr(Config, 'BRAND_VOICE', '') or (
        "- Low, controlled, resonant\n"
        "- Calm intensity; authoritative without shouting\n"
        "- Short, declarative sentences\n"
        "- Measured pacing\n"
        "- Dark, mysterious presence—disciplined resolve\n"
        "- Masculine and grounded\n"
        "- NO hype. NO motivational fluff."
    )
    themes = getattr(Config, 'BRAND_THEMES', '') or (
        "Address real daily battles: Finances, family leadership, temptation, fatigue, doubt, lust, anger, responsibility, endurance, obedience.\n\n"
        "Core themes: Discipline over comfort. Duty over desire. Endurance over escape. Faith over fear. Action over emotion."
    )
    avoid = getattr(Config, 'BRAND_AVOID', '') or (
        "Warmth or sentimentality, soft encouragement, modern slang, politics, long scripture quotations, hashtags."
    )
    
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

What to USE: Direct honest practical language, brief references woven naturally, one clear action for today.

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
Name the specific battle. The real struggle men face daily. Paint the scene with military imagery.

### 3. REVEAL (next ~30% of words)
The truth. Brief scripture reference woven naturally. Military language. The weapon or shield for this battle.

### 4. COMMAND (final ~25% of words)
One clear action. Today. Now. End with a strong imperative. Leave them ready to move.

## YOUR ASSIGNMENT

**TOPIC:** {{topic}}
**CATEGORY:** {{category}}
**SUGGESTED FOCUS:** {{angle}}

## OUTPUT FORMAT (JSON only, no markdown):

{{{{
  "hook": "Bold opener, NO QUOTES",
  "build": "Name the battle, NO QUOTES",
  "reveal": "Scripture truth, NO QUOTES",
  "command": "Clear action for today, NO QUOTES",
  "script_full": "Complete script ~{words} words - SHORT DECLARATIVE SENTENCES - NO QUOTES - ONE PARAGRAPH",
  "tone": "disciplined|resolute|commanding|unwavering"
}}}}
"""


def generate_script(topic: dict) -> dict:
    """Generate viral knight script via GPT-4o."""
    log.info(f"📝 Phase 2: Generating script via {Config.SCRIPT_MODEL} | Words: {Config.SCRIPT_WORDS} | ~{round(int(Config.SCRIPT_WORDS)/3)}s")

    cat = topic["category"]
    config = CATEGORY_CONFIG.get(cat, list(CATEGORY_CONFIG.values())[0])
    angle = config["angle"]

    prompt = build_script_prompt().format(topic=topic["idea"], category=cat, angle=angle)

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
