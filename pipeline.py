"""
Biblical Knights Content Reactor — Pipeline Engine
=====================================================
Replaces: 87-node n8n workflow (Biblical_Knights_V5_NANO_WAN)
Same APIs: OpenAI GPT-4o, Replicate (GPT-Image-1.5, Seedance-1-Lite),
           ElevenLabs, Shotstack, Blotato, Airtable, Cloudflare R2

Pipeline: Airtable → Script → Scenes → Images → Videos → Voice →
          Transcribe → Render → Upload → Publish (7 platforms)
"""

import os, json, time, random, re, io, csv, logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
import boto3

# ─── LOGGING ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("knights")

# ─── CONFIG (from .env or environment) ────────────────────────
def env(key, default=""):
    return os.environ.get(key, default)

class Config:
    # OpenAI
    OPENAI_KEY        = env("OPENAI_API_KEY")
    OPENAI_MODEL      = "gpt-4o"

    # Replicate
    REPLICATE_TOKEN   = env("REPLICATE_API_TOKEN")

    # Image & Video models (switchable via Settings)
    IMAGE_MODEL       = env("IMAGE_MODEL", "black-forest-labs/flux-1.1-pro")
    IMAGE_QUALITY     = env("IMAGE_QUALITY", "high")             # low | medium | high
    VIDEO_PROVIDER    = env("VIDEO_PROVIDER", "replicate")       # replicate
    VIDEO_MODEL       = env("VIDEO_MODEL", "bytedance/seedance-1-lite")

    # ElevenLabs
    ELEVEN_KEY        = env("ELEVENLABS_API_KEY")
    VOICE_ID          = env("ELEVENLABS_VOICE_ID", "bwCXcoVxWNYMlC6Esa8u")  # Austin

    # Shotstack
    SHOTSTACK_KEY     = env("SHOTSTACK_API_KEY")

    # Cloudflare R2
    R2_ACCESS_KEY     = env("R2_ACCESS_KEY")
    R2_SECRET_KEY     = env("R2_SECRET_KEY")
    R2_ENDPOINT       = env("R2_ENDPOINT")
    R2_BUCKET         = env("R2_BUCKET", "knights-videos")
    R2_PUBLIC_URL     = env("R2_PUBLIC_URL", "https://pub-f92dbf6db5984f8da62f9e837891f0f4.r2.dev")

    # Airtable
    AIRTABLE_KEY      = env("AIRTABLE_API_KEY")
    AIRTABLE_BASE     = env("AIRTABLE_BASE_ID", "appNDCADOHinuotY1")
    AIRTABLE_TABLE    = env("AIRTABLE_TABLE", "Scripture Topics")

    # Blotato
    BLOTATO_KEY       = env("BLOTATO_API_KEY")
    BLOTATO_ACCOUNTS  = {
        "tiktok":    env("BLOTATO_TIKTOK_ID"),
        "youtube":   env("BLOTATO_YOUTUBE_ID"),
        "instagram": env("BLOTATO_INSTAGRAM_ID", "31177"),
        "facebook":  env("BLOTATO_FACEBOOK_ID"),
        "facebook_page": env("BLOTATO_FACEBOOK_PAGE_ID"),
        "pinterest": env("BLOTATO_PINTEREST_ID"),
        "pinterest_board": env("BLOTATO_PINTEREST_BOARD_ID"),
        "twitter":   env("BLOTATO_TWITTER_ID"),
        "threads":   env("BLOTATO_THREADS_ID"),
    }

    # Logo
    LOGO_URL = "https://pub-b96dc727407242919393b2bef35ade2f.r2.dev/gods_knights.png"


# ══════════════════════════════════════════════════════════════
# PHASE 1: FETCH TOPIC FROM AIRTABLE
# ══════════════════════════════════════════════════════════════

def fetch_topic() -> dict:
    """Get next 'New' item from Airtable Scripture Topics."""
    log.info("📋 Phase 1: Fetching topic from Airtable...")

    url = f"https://api.airtable.com/v0/{Config.AIRTABLE_BASE}/{Config.AIRTABLE_TABLE}"
    r = requests.get(url, headers={
        "Authorization": f"Bearer {Config.AIRTABLE_KEY}",
    }, params={
        "filterByFormula": "{Status} = 'New'",
        "maxRecords": 1,
    })
    r.raise_for_status()
    records = r.json().get("records", [])

    if not records:
        raise RuntimeError("No new topics in Airtable")

    rec = records[0]
    fields = rec["fields"]
    topic = {
        "airtable_id": rec["id"],
        "idea": fields.get("Idea", ""),
        "category": fields.get("Category", ""),
        "scripture": fields.get("Scripture", ""),
    }
    log.info(f"   Topic: {topic['idea']} [{topic['category']}]")
    return topic


def update_airtable(record_id: str, fields: dict):
    """Update an Airtable record."""
    url = f"https://api.airtable.com/v0/{Config.AIRTABLE_BASE}/{Config.AIRTABLE_TABLE}/{record_id}"
    requests.patch(url, headers={
        "Authorization": f"Bearer {Config.AIRTABLE_KEY}",
        "Content-Type": "application/json",
    }, json={"fields": fields})


# ══════════════════════════════════════════════════════════════
# PHASE 2: GENERATE VIRAL SCRIPT (GPT-4o)
# ══════════════════════════════════════════════════════════════

# Category configs — exact match from n8n Prepare Data node
CATEGORY_CONFIG = {
    "Shocking Revelations": {
        "hook_patterns": [
            "Direct: 'The enemy already moved. Did you?'",
            "Challenge: 'Most men quit before the real fight starts.'",
        ],
        "tone": "battlefield urgency, commanding presence",
        "angle": "expose the spiritual battle most men are losing",
    },
    "Shocking Reveal": {
        "hook_patterns": [
            "Direct: 'You were trained for this. Act like it.'",
            "Challenge: 'The armor is there. Why aren't you wearing it?'",
        ],
        "tone": "commanding, no excuses",
        "angle": "call men to immediate action",
    },
    "Behind-the-Scenes": {
        "hook_patterns": [
            "Direct: 'This is what the daily grind actually looks like.'",
            "Challenge: 'Nobody sees the battle before dawn.'",
        ],
        "tone": "raw insider, unfiltered reality",
        "angle": "show the invisible daily war",
    },
    "Myths Debunked": {
        "hook_patterns": [
            "Direct: 'Strength without discipline is just noise.'",
            "Challenge: 'That comfort zone? It is your cage.'",
        ],
        "tone": "myth-breaking, direct challenge",
        "angle": "shatter comfortable lies",
    },
    "Deep Dive Analysis": {
        "hook_patterns": [
            "Direct: 'Look deeper. The answer is in the text.'",
            "Challenge: 'Surface reading misses the sword.'",
        ],
        "tone": "scholarly intensity, focused revelation",
        "angle": "deep scripture analysis",
    },
}

SCRIPT_PROMPT = """## ⚠️ WORD COUNT: 40-50 WORDS MAXIMUM ⚠️

TOTAL SCRIPT: 40-50 WORDS (15-20 seconds at measured pace)

Before you output, COUNT YOUR WORDS. If over 50, DELETE words until under 50.

WORD LIMITS PER SECTION:
- Hook: 6-8 words MAX
- Build: 10-12 words MAX
- Reveal: 10-12 words MAX
- Command: 8-10 words MAX

IF YOUR SCRIPT IS OVER 50 WORDS, YOU HAVE FAILED.

---

You are writing as a seasoned medieval knight addressing other men in the faith.

## CHARACTER

A battle-hardened Christian knight:
- Strong, disciplined, capable, calm
- Not cruel, not cold—firm and compassionate
- Protector of faith, family, duty, truth
- Lives in peace but ready for war
- Wears the Armor of God (Ephesians 6) symbolically
- Unwavering allegiance: Christ is King

## VOICE

- Low, controlled, resonant
- Calm intensity; authoritative without shouting
- Short, declarative sentences
- Measured pacing
- Dark, mysterious presence—disciplined resolve
- Masculine and grounded
- NO hype. NO motivational fluff.

## TONE & MESSAGE

Address real daily battles: Finances, family leadership, temptation, fatigue, doubt, lust, anger, responsibility, endurance, obedience.

Core themes: Discipline over comfort. Duty over desire. Endurance over escape. Faith over fear. Action over emotion.

What to AVOID: Warmth or sentimentality, soft encouragement, modern slang, politics, long scripture quotations, hashtags.

What to USE: Direct honest practical language, military/warfare metaphors, duty and honor language, brief scripture paraphrases, one clear action for today.

## VOICEOVER RULES

- Short, declarative sentences
- Period after each complete thought
- NO quotes around any words
- ONE continuous paragraph
- Clean punctuation: periods only (rarely commas)

## SCRIPT STRUCTURE (15-20 seconds / 40-50 words MAX)

### 1. HOOK (0-3 sec) — 6-8 words
Immediate call to attention. VARY the opener.

### 2. BUILD (3-9 sec) — 10-12 words
Name the specific battle. The real struggle men face daily.

### 3. REVEAL (9-15 sec) — 10-12 words
The truth. Brief scripture reference. Military language.

### 4. COMMAND (15-20 sec) — 8-10 words
One clear action. Today. Now. End with one-word imperative.

## YOUR ASSIGNMENT

**TOPIC:** {topic}
**CATEGORY:** {category}
**SUGGESTED FOCUS:** {angle}

## OUTPUT FORMAT (JSON only, no markdown):

{{
  "hook": "Bold opener, 6-8 words, NO QUOTES",
  "build": "Name the battle, 10-12 words, NO QUOTES",
  "reveal": "Scripture truth, 10-12 words, NO QUOTES",
  "command": "Clear action for today, 8-10 words, NO QUOTES",
  "script_full": "Complete script 40-50 words - SHORT DECLARATIVE SENTENCES - NO QUOTES",
  "tone": "disciplined|resolute|commanding|unwavering"
}}
"""

def generate_script(topic: dict) -> dict:
    """Generate viral knight script via GPT-4o."""
    log.info("📝 Phase 2: Generating script via GPT-4o...")

    cat = topic["category"]
    config = CATEGORY_CONFIG.get(cat, list(CATEGORY_CONFIG.values())[0])
    angle = config["angle"]

    prompt = SCRIPT_PROMPT.format(
        topic=topic["idea"],
        category=cat,
        angle=angle,
    )

    r = requests.post("https://api.openai.com/v1/chat/completions", headers={
        "Authorization": f"Bearer {Config.OPENAI_KEY}",
        "Content-Type": "application/json",
    }, json={
        "model": Config.OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.85,
        "max_tokens": 800,
    })
    r.raise_for_status()

    text = r.json()["choices"][0]["message"]["content"]

    # Parse — same logic as n8n Parse Script node
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


# ══════════════════════════════════════════════════════════════
# PHASE 3: SCENE ENGINE v6 — STRUCTURED SLOT SYSTEM
# ══════════════════════════════════════════════════════════════

# Direct port of n8n Scene Engine v6
pick = lambda arr: random.choice(arr)

THEME_KEYWORDS = {
    "temptation": ["tempt","lust","desire","flesh","crave","hunger","pull","urge","resist","want","pleasure","indulge","forbidden"],
    "endurance": ["endure","tired","weary","exhaust","fatigue","press on","keep going","persist","carry","weight","heavy","burden","grind","worn"],
    "doubt": ["doubt","fear","uncertain","question","waver","hesitat","lost","confused","wonder","shake","weak","fail","falling","anxiety"],
    "discipline": ["disciplin","routine","habit","daily","practice","train","prepare","ready","order","structure","ritual","commit","consistent"],
    "courage": ["courage","brave","bold","stand","rise","fight","warrior","strong","strength","power","lion","fire","forge","iron","conquer","victory"],
    "duty": ["duty","responsib","protect","guard","watch","serve","family","wife","children","son","father","husband","provide","lead","sacrifice"],
    "loss": ["loss","lost","grief","pain","suffer","wound","broken","fall","fallen","hurt","scar","dark","night","shadow","alone","death","gone"],
    "patience": ["wait","patient","still","quiet","silent","peace","calm","rest","trust","faith","pray","kneel","surrender","submit","obey"],
    "anger": ["anger","rage","fury","wrath","burn","fire","destroy","control","contain","restrain","channel","storm","thunder","bitter"],
    "identity": ["who you are","identity","purpose","call","chosen","anointed","crown","king","knight","armor of god","ephesians","helmet"],
}

FIGURES = [
    "a battle-scarred knight in dented steel plate armor, torn dark cape, closed scratched helm",
    "a lone knight in battered grey steel armor, heavy mud-stained cape, weathered closed helm",
    "a medieval warrior in blackened steel plate, tattered cape in shreds, scarred closed helm",
    "a weary knight in ancient dulled steel plate, faded torn surcoat, heavy hooded cape, scratched helm",
    "a solitary knight in tarnished steel armor, stained campaign cape, closed dented helm",
]

IMAGE_SUFFIXES = {
    "storm": "Cinematic dark atmosphere, cold blue-grey tones, rain, fog, 9:16 vertical, photorealistic.",
    "fire": "Cinematic dark atmosphere, orange ember glow against darkness, smoke, ash particles, 9:16 vertical, photorealistic.",
    "dawn": "Cinematic golden hour light, warm amber highlights, cold shadows, fog, 9:16 vertical, photorealistic.",
    "night": "Cinematic moonlit scene, silver-blue cold tones, deep shadows, mist, 9:16 vertical, photorealistic.",
    "grey": "Cinematic overcast atmosphere, muted grey tones, rain, wet surfaces, 9:16 vertical, photorealistic.",
    "battle": "Cinematic dark atmosphere, smoke, distant fire, debris, dramatic lighting, 9:16 vertical, photorealistic.",
}

TECH_SUFFIX = "Steady camera. 9:16 vertical."

# All 21 story seeds from the n8n Scene Engine v6
STORY_SEEDS = [
    {"name":"last_stand_defeat","themes":["loss","endurance","courage"],"mood":"battle","clips":[
        {"action":"kneels on the muddy battlefield, greatsword thrust blade-down into the ground","setting":"devastated battlefield at blood-red dawn, broken weapons and toppled siege engines scattered around him","lighting":"blood-red dawn light raking across the battlefield from the horizon","atmosphere":"smoke drifting low across the ground","composition":"Low angle wide shot","camera":"Slow pull back","subject":"Knight's shoulders drop with exhaustion","ambient":"Smoke drifts across frame","pace":"Heavy weighted motion."},
        {"action":"stands alone on the ruined battlefield, sword at his side","setting":"open battlefield at dawn, fallen banners and debris stretching to the horizon","lighting":"blood-red dawn sky behind him, dark foreground","atmosphere":"smoke and ash hanging in the air","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight shifts weight, head turns slowly","ambient":"Smoke drifts past him","pace":"Steady motion."},
        {"action":"raises his sword overhead with both hands on the empty battlefield","setting":"open battlefield, shattered shield at his feet","lighting":"dark red dawn light from behind","atmosphere":"smoke rising in the distance","composition":"Side profile full body","camera":"Side profile, slow push-in","subject":"Knight lifts sword slowly overhead","ambient":"Smoke drifts behind him","pace":"Controlled motion."},
    ]},
    {"name":"last_man_standing","themes":["courage","endurance","loss"],"mood":"dawn","clips":[
        {"action":"stands at the crest of a ridge, hand resting on his sword hilt","setting":"ridge overlooking a wide valley at first dawn","lighting":"golden dawn light breaking through low clouds","atmosphere":"morning fog in the valley below","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight turns head slowly toward the valley","ambient":"Cape drifts in morning wind","pace":"Slow smooth motion."},
        {"action":"stands on the ridge looking out over the empty valley below","setting":"ridge above empty battlefield, amber morning sky stretching behind him","lighting":"amber dawn light on his armor","atmosphere":"mist in the valley below","composition":"Three-quarter rear view","camera":"Slow pan left to right","subject":"Knight adjusts grip on sword hilt","ambient":"Cape moves in morning wind","pace":"Slow smooth motion."},
        {"action":"walks forward along the ridge toward the rising sun","setting":"ridge crest, open golden sky ahead, long shadow behind him","lighting":"golden sun rising directly ahead of him","atmosphere":"morning mist burning off the ridge below","composition":"Front-facing medium shot","camera":"Slow push-in from behind","subject":"Knight walks forward, deliberate steps","ambient":"Cape billows behind him","pace":"Steady motion."},
    ]},
    {"name":"dawn_march","themes":["courage","duty","endurance"],"mood":"dawn","clips":[
        {"action":"stands at the head of a dark road, shield on his arm, sword at his hip","setting":"dark road at pre-dawn, mist filling the valley stretching ahead","lighting":"pale pre-dawn grey light, horizon barely brightening","atmosphere":"mist drifting across the road","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight rolls shoulders forward, settling armor","ambient":"Mist drifts past him","pace":"Slow smooth motion."},
        {"action":"strides down a muddy road through rolling hills","setting":"winding country road, dawn horizon warming ahead of him","lighting":"warm amber dawn light on the horizon","atmosphere":"morning mist low on the fields","composition":"Side profile full body","camera":"Slow push-in from the front","subject":"Knight walks toward camera, deliberate steps","ambient":"Cape flows behind him","pace":"Steady motion."},
        {"action":"crests a hill, pausing at the top","setting":"hilltop at full dawn, stone fortress silhouetted in the far distance","lighting":"golden dawn light flooding the scene from the east","atmosphere":"morning haze between him and the distant fortress","composition":"Low angle full body","camera":"Pull back reveals knight on hill crest","subject":"Knight plants sword tip on the ground","ambient":"Cape drifts in wind","pace":"Slow smooth motion."},
    ]},
    {"name":"outnumbered_ridge","themes":["courage","doubt","duty"],"mood":"storm","clips":[
        {"action":"stands alone on a ridge, sword at his hip","setting":"exposed ridge top, dark storm clouds churning overhead","lighting":"flat grey storm light, lightning flashing in the far distance","atmosphere":"rain beginning to fall, fog rolling in from behind","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight draws sword slowly from hip","ambient":"Storm clouds roll in behind him","pace":"Controlled motion."},
        {"action":"grips his drawn sword with both hands, braced against the storm","setting":"exposed ridge in full storm, dark sky above and below","lighting":"lightning blazing across the sky behind him","atmosphere":"rain hammering his armor and the ground","composition":"Extreme close-up on gauntlet gripping sword","camera":"Close on gauntlet gripping sword hilt","subject":"Knuckles tighten on the hilt","ambient":"Rain pounds the ground","pace":"Controlled motion."},
        {"action":"holds his ground, cape torn and snapping in the gale","setting":"ridge in the full storm, dark clouds pressing down","lighting":"cold flat grey storm light from above","atmosphere":"rain pouring from his helm, wind tearing at his cape","composition":"Front-facing medium shot","camera":"Slow push-in","subject":"Knight holds ground, cape whips violently","ambient":"Rain falls heavy around him","pace":"Controlled motion."},
    ]},
    {"name":"vigil_before_battle","themes":["discipline","patience","duty"],"mood":"night","clips":[
        {"action":"kneels on the stone floor, head bowed","setting":"small stone medieval chapel at night, altar and candle before him","lighting":"single candle on the altar casting warm orange light on the stone","atmosphere":"deep shadows pressing in from all sides of the chapel","composition":"Wide full-body shot","camera":"Crane shot descending slowly","subject":"Knight bows head deeper toward the altar","ambient":"Candlelight flickers on the stone walls","pace":"Slow smooth motion."},
        {"action":"kneels with head bowed, sword across his knees","setting":"dark stone chapel, single candle burning low on the altar","lighting":"dim candlelight on his closed helm and shoulders","atmosphere":"deep shadows filling the room around him","composition":"Close-up on helm and chest","camera":"Close on helmet visor","subject":"Knight's gauntlet tightens on the sword across his knees","ambient":"Candle flame wavers in stillness","pace":"Slow smooth motion."},
        {"action":"stands in the stone archway of the chapel doorway, sword at his hip","setting":"stone chapel doorway, moonlit courtyard visible behind him","lighting":"moonlight from behind, faint candlelight at his back","atmosphere":"mist drifting in the courtyard beyond the doorway","composition":"Three-quarter rear view","camera":"Slow push-in from outside","subject":"Knight shifts weight forward in the archway","ambient":"Mist drifts across the doorway","pace":"Steady motion."},
    ]},
    {"name":"the_watch","themes":["duty","endurance","patience"],"mood":"night","clips":[
        {"action":"stands watch on the stone tower battlement, sword at his side","setting":"stone tower battlement at night, dark landscape stretching below","lighting":"moonlight on his armor from above","atmosphere":"stars above, cold night air","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight turns head scanning the horizon","ambient":"Cape drifts in cold night wind","pace":"Slow smooth motion."},
        {"action":"holds his sword at the ready, scanning the darkness below","setting":"tower battlement at deep night, vast dark sky above, forest below","lighting":"moonlight and starlight above, total darkness below","atmosphere":"cold wind across the open battlements","composition":"Side profile full body","camera":"Slow pan across the battlements","subject":"Knight raises sword slightly, scanning below","ambient":"Cape moves in cold wind","pace":"Steady motion."},
        {"action":"stands watch as the first grey light of dawn appears at the horizon","setting":"tower battlement, pale pre-dawn grey at the horizon, night sky still above","lighting":"cold grey pre-dawn light on his armor","atmosphere":"mist in the valley below","composition":"Front-facing medium shot","camera":"Slow push-in","subject":"Knight lowers sword slowly to his side","ambient":"Mist drifts in the valley below","pace":"Slow smooth motion."},
    ]},
    {"name":"the_cliff_prayer","themes":["patience","doubt","identity"],"mood":"night","clips":[
        {"action":"stands at the cliff edge, arms at his sides, facing the ocean","setting":"sea cliff at night, moonlit ocean stretching below","lighting":"moonlight on his cape and shoulders from above","atmosphere":"sea wind moving his cape","composition":"Extreme wide shot from behind","camera":"Wide locked shot from behind","subject":"Knight's cape lifts heavy in the ocean wind","ambient":"Cape drifts in sea wind","pace":"Slow smooth motion."},
        {"action":"kneels at the cliff edge, head bowed toward the ocean","setting":"sea cliff at night, vast moonlit ocean below, stars above","lighting":"silver moonlight on his armor","atmosphere":"sea wind at the cliff edge","composition":"Low angle full body","camera":"Low angle looking up at the knight","subject":"Knight's shoulders rise and fall with heavy breath","ambient":"Cape moves in sea wind","pace":"Slow smooth motion."},
        {"action":"stands at the cliff edge, arms at his sides, turning away","setting":"sea cliff at night, ocean horizon stretching below and behind him","lighting":"full moonlight on his armor and cape","atmosphere":"stars blazing across the full sky above","composition":"Side profile full body","camera":"Slow push-in from behind","subject":"Knight turns slowly away from the cliff","ambient":"Cape fills frame in the wind","pace":"Steady motion."},
    ]},
    {"name":"the_long_night","themes":["endurance","patience","loss"],"mood":"night","clips":[
        {"action":"stands alone in an open field, sword at his side","setting":"open flat ground at deep night, nothing but darkness and sky","lighting":"moonlight on his armor, full dark surrounding him","atmosphere":"stars above, cold night air","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight shifts weight from one leg to the other","ambient":"Cape drifts slowly in night wind","pace":"Slow smooth motion."},
        {"action":"sits with his back against a stone wall, sword across his knees","setting":"stone wall at night, moonlit open ground stretching before him","lighting":"cold moonlight on his helm from above","atmosphere":"cold still night air","composition":"Close-up on helm and chest","camera":"Close on helmet visor","subject":"Knight tilts head back against the stone wall","ambient":"Cape settles against stone wall","pace":"Heavy weighted motion."},
        {"action":"stands as pale grey light begins at the horizon, sword drawn","setting":"open ground, night sky still above, pale grey dawn at the horizon","lighting":"pale grey dawn light beginning at the far horizon","atmosphere":"mist rising from the ground","composition":"Front-facing medium shot","camera":"Slow push-in","subject":"Knight raises sword to ready position","ambient":"Mist rises from the ground","pace":"Steady motion."},
    ]},
    {"name":"preparation_ritual","themes":["discipline","identity","duty"],"mood":"dawn","clips":[
        {"action":"stands at a rough wooden table, gauntlets and breastplate laid out before him","setting":"stone chamber at pre-dawn, armor pieces and sword laid flat on the table","lighting":"pale grey pre-dawn light through a narrow stone window","atmosphere":"dust motes drifting in the shaft of window light","composition":"Wide full-body shot","camera":"Close on gauntlet on the table","subject":"Knight reaches for the gauntlet","ambient":"Dust drifts in window light","pace":"Slow smooth motion."},
        {"action":"pulls a chest plate strap tight, chin down","setting":"stone chamber, worn armor on his frame, narrow window behind him","lighting":"dawn light through a narrow stone window on his armor","atmosphere":"grey morning light filling the stone chamber","composition":"Close-up on gauntlet and armor on the table","camera":"Slow push-in","subject":"Knight pulls strap tight","ambient":"Cape hangs still in morning air","pace":"Steady motion."},
        {"action":"stands fully armed in the stone doorway, shield raised","setting":"stone doorway at full dawn, golden light ahead of him","lighting":"golden dawn light flooding in from outside","atmosphere":"morning mist just beyond the doorway","composition":"Front-facing medium shot","camera":"Slow push-in from outside","subject":"Knight steps forward into the doorway","ambient":"Mist drifts in the door opening","pace":"Steady motion."},
    ]},
    {"name":"the_reflection","themes":["identity","doubt","discipline"],"mood":"dawn","clips":[
        {"action":"stands at the edge of a perfectly still lake, arms at his sides","setting":"still lake at first dawn, misty treeline reflected in the water below","lighting":"first pale dawn light on the horizon, pink and grey","atmosphere":"mist drifting low on the water surface","composition":"Wide full-body shot","camera":"Slow push-in","subject":"Knight tilts head down toward the water","ambient":"Mist drifts on the water surface","pace":"Slow smooth motion."},
        {"action":"kneels at the lake edge, looking down at the still water","setting":"lake edge at dawn, still water before him, misty treeline behind","lighting":"warm golden dawn light on his armor","atmosphere":"low mist on the water surface","composition":"Low angle full body","camera":"Low angle looking up at the knight","subject":"Knight reaches gauntlet toward the water surface","ambient":"Mist drifts low on water","pace":"Slow smooth motion."},
        {"action":"stands at the lake, sword raised overhead with both hands","setting":"lake at full dawn, still water behind him reflecting the golden sky","lighting":"full golden dawn light on his armor and raised blade","atmosphere":"mist burning off the water in the morning light","composition":"Side profile full body","camera":"Side profile","subject":"Knight raises sword overhead, holds position","ambient":"Mist drifts behind him on the water","pace":"Steady motion."},
    ]},
    {"name":"the_oath","themes":["identity","duty","discipline"],"mood":"dawn","clips":[
        {"action":"kneels with his sword planted before him, both hands on the hilt","setting":"open ground at dawn, brightening horizon behind him","lighting":"golden dawn light on his bowed helm","atmosphere":"morning mist around him at ground level","composition":"Wide full-body shot","camera":"Overhead angle tilting down","subject":"Knight's grip tightens on the planted sword hilt","ambient":"Mist drifts around him","pace":"Slow smooth motion."},
        {"action":"kneels with his head bowed over his planted sword","setting":"open ground at dawn, mist at knee level around him","lighting":"warm golden dawn light on his armor","atmosphere":"mist swirling around the base of the planted sword","composition":"Overhead downward angle","camera":"Close on helmet visor","subject":"Knight bows head lower over the sword","ambient":"Mist swirls low around him","pace":"Slow smooth motion."},
        {"action":"rises with his sword raised in one hand, cape flowing","setting":"open ground at full dawn, golden sky behind him","lighting":"golden dawn light on his raised sword and armor","atmosphere":"morning mist at ground level","composition":"Side profile full body","camera":"Side profile","subject":"Knight raises sword overhead, holds position","ambient":"Cape flows in morning wind","pace":"Steady motion."},
    ]},
    {"name":"the_return","themes":["loss","endurance","patience"],"mood":"grey","clips":[
        {"action":"walks alone down a wet grey road, shoulders set forward","setting":"flat grey countryside under overcast sky, wet road stretching ahead","lighting":"flat grey overcast light, no shadows","atmosphere":"light rain falling on the road","composition":"Wide full-body shot","camera":"Slow push-in from the front","subject":"Knight walks toward camera, deliberate steps","ambient":"Rain falls lightly around him","pace":"Heavy weighted motion."},
        {"action":"walks toward a stone wall and iron gate ahead","setting":"muddy road leading to an iron gate in a stone wall, overcast sky","lighting":"flat grey overcast light on wet stone","atmosphere":"rain on the stone and muddy ground","composition":"Front-facing medium shot","camera":"Slow push-in from behind","subject":"Knight walks toward the gate","ambient":"Rain falls on wet ground","pace":"Heavy weighted motion."},
        {"action":"stands at the open stone gate, facing the threshold","setting":"open iron gate in stone wall, wet road behind him","lighting":"flat grey overcast light","atmosphere":"rain falling behind him on the road","composition":"Side profile full body","camera":"Slow push-in from outside","subject":"Knight steps into the doorway","ambient":"Rain falls on wet road behind him","pace":"Steady motion."},
    ]},
    {"name":"the_grave","themes":["loss","patience","duty"],"mood":"grey","clips":[
        {"action":"stands before a simple stone grave marker, arms at his sides","setting":"flat open ground under grey sky, stone marker before him, wet grass around","lighting":"flat grey overcast light, no shadows","atmosphere":"light rain falling on the wet grass","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight's head drops slowly toward the grave","ambient":"Rain falls on wet grass","pace":"Heavy weighted motion."},
        {"action":"kneels before the stone grave marker, head bowed","setting":"grave site, flat grey sky above, wet grass around him","lighting":"flat grey light, no directional shadows","atmosphere":"light rain falling on him and the stone","composition":"Overhead downward angle","camera":"Overhead angle tilting down","subject":"Knight presses gauntlet to the wet ground","ambient":"Rain falls on wet ground","pace":"Heavy weighted motion."},
        {"action":"stands from the grave, shoulders set, facing away","setting":"grave site, stone marker at his feet, grey sky behind him","lighting":"flat grey overcast light","atmosphere":"rain falling around him","composition":"Three-quarter rear view","camera":"Wide shot from behind","subject":"Knight turns away from camera","ambient":"Cape moves in grey wind","pace":"Steady motion."},
    ]},
    {"name":"crossing_the_river","themes":["courage","endurance","doubt"],"mood":"grey","clips":[
        {"action":"stands at the river bank, facing the far shore","setting":"wide grey river at the bank, overcast sky, far shore barely visible","lighting":"flat grey overcast light on the water","atmosphere":"fog on the river surface","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight steps one foot forward to the water edge","ambient":"Fog rolls across the river surface","pace":"Steady motion."},
        {"action":"wades through the river, water at his waist, sword held above the surface","setting":"mid-river crossing, grey sky above, both banks visible","lighting":"flat grey overcast light, water reflecting the sky","atmosphere":"water rushing around him","composition":"Side profile full body","camera":"Tight shot from the side","subject":"Knight wades forward, slow heavy steps","ambient":"Water flows past him","pace":"Heavy weighted motion."},
        {"action":"emerges from the river onto the far bank, water dripping from his armor","setting":"far river bank, river behind him, overcast sky above","lighting":"flat grey overcast light","atmosphere":"fog on the river behind him","composition":"Front-facing medium shot","camera":"Slow push-in from the front","subject":"Knight walks toward camera, deliberate steps","ambient":"Fog drifts on the river behind him","pace":"Steady motion."},
    ]},
    {"name":"kneeling_in_rain","themes":["patience","loss","temptation"],"mood":"storm","clips":[
        {"action":"kneels on a stone road in the heavy rain, head bowed","setting":"stone road in storm, puddles forming around him","lighting":"dark grey storm light from above","atmosphere":"heavy rain pounding the stone and ground","composition":"Wide full-body shot","camera":"Overhead angle tilting down","subject":"Knight's shoulders heave with labored breath","ambient":"Rain pounds around him","pace":"Heavy weighted motion."},
        {"action":"kneels with both gauntleted hands pressed flat to the wet stone","setting":"stone road in storm, water rushing across the ground","lighting":"dark grey storm light","atmosphere":"water rushing across the stone road","composition":"Extreme close-up on gauntlet on wet stone","camera":"Close on gauntlet on wet stone","subject":"Knight's fingers dig into the wet stone","ambient":"Water rushes across the stone","pace":"Heavy weighted motion."},
        {"action":"rises to standing in the rain, shoulders straight","setting":"stone road in storm, dark sky above","lighting":"dark storm light from above","atmosphere":"rain falling around him","composition":"Front-facing medium shot","camera":"Slow push-in","subject":"Knight rises to standing","ambient":"Rain falls around him","pace":"Controlled motion."},
    ]},
    {"name":"controlled_fury","themes":["anger","discipline","courage"],"mood":"storm","clips":[
        {"action":"stands rigid in the violent storm, fists at his sides, cape snapping","setting":"open ground in a violent storm, rain hammering all around him","lighting":"dark grey storm light, lightning on the distant horizon","atmosphere":"rain hammering the ground around him","composition":"Wide full-body shot","camera":"Wide locked shot","subject":"Knight's fists clench tighter at his sides","ambient":"Rain pounds around him","pace":"Controlled motion."},
        {"action":"stands with gauntleted fists clenched at his sides","setting":"open ground in storm, dark sky pressing down","lighting":"lightning flash across the sky above him","atmosphere":"rain pouring from his helm","composition":"Extreme close-up on gauntlet","camera":"Close on gauntlet gripping sword hilt","subject":"Fist tightens","ambient":"Rain hammers down","pace":"Controlled motion."},
        {"action":"stands as the storm begins to ease, shoulders releasing tension","setting":"open ground, dark clouds beginning to thin above him","lighting":"faint grey light breaking through thinning clouds","atmosphere":"rain lightening around him","composition":"Front-facing medium shot","camera":"Slow push-in","subject":"Knight's shoulders slowly release downward","ambient":"Rain eases around him","pace":"Slow smooth motion."},
    ]},
    {"name":"the_burden","themes":["endurance","duty","loss"],"mood":"fire","clips":[
        {"action":"walks through a burning village, carrying a large wooden cross beam on his shoulder","setting":"burning medieval village at night, thatched roofs ablaze, smoke filling the streets","lighting":"orange firelight from the burning buildings on all sides","atmosphere":"smoke rising from the buildings around him","composition":"Wide full-body shot","camera":"Slow push-in from the front","subject":"Knight walks forward under the weight of the beam","ambient":"Smoke rises from the buildings","pace":"Heavy weighted motion."},
        {"action":"kneels under the weight of the beam, one knee on the cobblestone","setting":"burning village street, fire on both sides, smoke filling the air","lighting":"orange firelight from burning buildings on his armor","atmosphere":"embers drifting past him","composition":"Side profile full body","camera":"Side profile","subject":"Knight sinks to one knee under the weight","ambient":"Embers drift past him","pace":"Heavy weighted motion."},
        {"action":"rises with the beam and walks forward through the smoke","setting":"edge of the burning village, dark road ahead, fire behind him","lighting":"orange firelight from behind, dark road ahead","atmosphere":"smoke surrounding him from behind","composition":"Three-quarter rear view","camera":"Slow push-in from behind","subject":"Knight rises and walks forward","ambient":"Smoke drifts behind him","pace":"Steady motion."},
    ]},
    {"name":"the_forge","themes":["discipline","identity","anger"],"mood":"fire","clips":[
        {"action":"stands at a blacksmith anvil, holding a glowing sword blank with tongs","setting":"dark stone forge at night, fire pit blazing to one side, tools hung on the walls","lighting":"orange firelight from the forge pit on his armor","atmosphere":"sparks drifting from the forge fire","composition":"Wide full-body shot","camera":"Close on the glowing metal on the anvil","subject":"Knight lifts hammer above the anvil","ambient":"Sparks drift from the fire","pace":"Controlled motion."},
        {"action":"strikes the glowing metal on the anvil with a heavy hammer","setting":"dark forge, sparks flying from the impact, fire blazing in the pit","lighting":"orange sparks from the hammer strike illuminating his helm","atmosphere":"sparks spraying from the anvil","composition":"Extreme close-up on hammer strike","camera":"Close on hammer striking metal","subject":"Hammer strikes the glowing metal","ambient":"Sparks fly from the anvil","pace":"Controlled motion."},
        {"action":"holds the finished sword up, examining the blade in the firelight","setting":"dark forge, fire burning low in the pit, the completed sword in his gauntlet","lighting":"orange firelight on the blade surface","atmosphere":"embers drifting from the dying fire","composition":"Low angle full body","camera":"Low angle looking up at the raised sword","subject":"Knight raises sword slowly, examining the blade","ambient":"Embers drift from the fire","pace":"Slow smooth motion."},
    ]},
    {"name":"the_desert","themes":["endurance","temptation","patience"],"mood":"fire","clips":[
        {"action":"walks across empty cracked desert ground, sword at his hip","setting":"vast empty desert at high noon, cracked earth stretching in all directions","lighting":"harsh bright sunlight from directly overhead","atmosphere":"heat shimmer on the desert surface","composition":"Wide full-body shot","camera":"Wide locked shot from the front","subject":"Knight walks forward, heavy deliberate steps","ambient":"Heat shimmer distorts the horizon","pace":"Heavy weighted motion."},
        {"action":"kneels on the cracked desert ground, head bowed against the heat","setting":"empty desert, cracked earth, blazing sky above","lighting":"harsh overhead sunlight beating down on his helm","atmosphere":"heat waves rising from the cracked ground","composition":"Overhead downward angle","camera":"Overhead angle tilting down","subject":"Knight bows head low, shoulders slumped","ambient":"Heat shimmer rises from the ground","pace":"Heavy weighted motion."},
        {"action":"stands and walks forward across the desert toward a distant dark shape on the horizon","setting":"empty desert, faint dark shape on the far horizon, blazing sky","lighting":"harsh sunlight from above, dark shape ahead","atmosphere":"heat shimmer between him and the distant shape","composition":"Front-facing medium shot","camera":"Slow push-in from behind","subject":"Knight walks forward, picking up pace","ambient":"Heat shimmer distorts the distant shape","pace":"Steady motion."},
    ]},
    {"name":"the_shield_wall","themes":["duty","courage","anger"],"mood":"battle","clips":[
        {"action":"stands at the center of a shield wall, shield locked with others on either side","setting":"open field before battle, enemy torches visible in the distant darkness","lighting":"orange torchlight from the enemy lines in the distance","atmosphere":"smoke drifting between the two lines","composition":"Front-facing medium shot","camera":"Slow push-in from the front","subject":"Knight raises shield higher, bracing","ambient":"Smoke drifts between the lines","pace":"Controlled motion."},
        {"action":"braces behind his shield as impact hits the wall","setting":"shield wall under attack, dust and debris in the air","lighting":"dark chaotic light, flash of steel and fire","atmosphere":"dust and debris in the air around the impact","composition":"Extreme close-up on shield edge","camera":"Close on shield taking impact","subject":"Shield arm absorbs the blow","ambient":"Dust and debris fly past","pace":"Controlled motion."},
        {"action":"steps forward from the shield wall, sword drawn, advancing","setting":"broken shield wall, enemy retreating, dust settling","lighting":"dark battlefield, orange fire in the distance","atmosphere":"smoke and dust settling around him","composition":"Side profile full body","camera":"Side profile, slow push-in","subject":"Knight steps forward, sword drawn","ambient":"Smoke settles around him","pace":"Steady motion."},
    ]},
    {"name":"the_gate","themes":["courage","duty","anger"],"mood":"fire","clips":[
        {"action":"stands before two massive iron gates wreathed in fire","setting":"large iron gates in a stone archway, fire burning on the metal and arch above","lighting":"orange firelight from above on his armor","atmosphere":"smoke rising from the gate arch","composition":"Wide full-body shot","camera":"Wide shot, knight small against the towering gates","subject":"Knight steps forward toward the burning gate","ambient":"Smoke rises from the arch above","pace":"Controlled motion."},
        {"action":"places a gauntleted hand flat against the burning iron gate","setting":"iron gate up close, fire on the metal, stone arch above","lighting":"orange firelight on his gauntlet and armor","atmosphere":"embers around his gauntlet from the burning gate","composition":"Extreme close-up on gauntlet on gate","camera":"Close on gauntlet on the burning gate","subject":"Knight presses hand to gate","ambient":"Embers drift around his gauntlet","pace":"Slow smooth motion."},
        {"action":"pushes through the burning iron gate, stepping into the archway","setting":"iron archway with fire and smoke, orange light beyond the gate","lighting":"orange firelight from behind and from beyond the gate","atmosphere":"smoke surrounding the archway","composition":"Three-quarter rear view","camera":"Slow push-in from behind","subject":"Knight steps forward through the gate","ambient":"Smoke drifts around him","pace":"Steady motion."},
    ]},
]


def detect_theme(text: str) -> str:
    scores = {}
    for theme, keywords in THEME_KEYWORDS.items():
        scores[theme] = sum(1 for kw in keywords if kw in text)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "random"


def scene_engine(script: dict, topic: dict) -> list:
    """Generate 3 clip prompt pairs (image + motion). Direct port of Scene Engine v6."""
    log.info("🎬 Phase 3: Scene Engine v6 — generating prompts...")

    all_text = " ".join([
        script["hook"], script["build"], script["reveal"],
        script.get("tone", ""), topic.get("category", ""), topic.get("idea", ""),
    ]).lower()

    theme = detect_theme(all_text)

    # Match stories to theme
    if theme == "random":
        matching = STORY_SEEDS
    else:
        matching = [s for s in STORY_SEEDS if theme in s["themes"]]
        if not matching:
            matching = STORY_SEEDS

    story = pick(matching)
    figure = pick(FIGURES)
    img_suffix = IMAGE_SUFFIXES.get(story["mood"], IMAGE_SUFFIXES["dawn"])

    clips = []
    for i, clip in enumerate(story["clips"]):
        image_prompt = f"{figure} {clip['action']}. {clip['setting']}. {clip['composition']}. {clip['lighting']}. {clip['atmosphere']}. {img_suffix}"
        motion_prompt = f"{clip['camera']}. {clip['subject']}. {clip['ambient']}. {clip['pace']} {TECH_SUFFIX}"
        clips.append({
            "index": i + 1,
            "image_prompt": image_prompt,
            "motion_prompt": motion_prompt,
        })

    log.info(f"   Theme: {theme} → Story: {story['name']} [{story['mood']}]")
    log.info(f"   Figure: {figure[:50]}...")
    return clips


# ══════════════════════════════════════════════════════════════
# PHASE 4: GENERATE IMAGES (Replicate → GPT-Image-1.5)
# ══════════════════════════════════════════════════════════════

def replicate_create(model: str, input_data: dict) -> str:
    """Create a Replicate prediction, return the GET URL for polling."""
    r = requests.post(
        f"https://api.replicate.com/v1/models/{model}/predictions",
        headers={
            "Authorization": f"Bearer {Config.REPLICATE_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"input": input_data},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["urls"]["get"]


def replicate_poll(get_url: str, timeout: int = 300) -> str:
    """Poll a Replicate prediction until complete. Returns output URL."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(get_url, headers={
            "Authorization": f"Bearer {Config.REPLICATE_TOKEN}",
        })
        r.raise_for_status()
        data = r.json()
        status = data.get("status")

        if status == "succeeded":
            output = data.get("output")
            if isinstance(output, list):
                return output[0]
            return output
        elif status == "failed":
            raise RuntimeError(f"Replicate failed: {data.get('error')}")

        time.sleep(10)

    raise TimeoutError("Replicate prediction timed out")


def generate_images(clips: list) -> list:
    """Generate cinematic images via Replicate (all models support 9:16)."""
    model = Config.IMAGE_MODEL
    quality = getattr(Config, 'IMAGE_QUALITY', 'high')
    log.info(f"🖼️  Phase 4: Generating images via Replicate ({model}) | Quality: {quality} | Aspect: 9:16")

    for clip in clips:
        params = {"prompt": clip["image_prompt"]}

        # Model-specific parameter mapping
        if "grok-imagine" in model:
            # xAI Grok Aurora — uses prompt + aspect_ratio
            params["aspect_ratio"] = "9:16"
        elif "nano-banana" in model:
            # Google Nano Banana / Pro — uses aspect_ratio
            params["aspect_ratio"] = "9:16"
        elif "seedream" in model:
            # ByteDance Seedream — uses aspect_ratio
            params["aspect_ratio"] = "9:16"
        elif "ideogram" in model:
            # Ideogram v3 — uses aspect_ratio
            params["aspect_ratio"] = "9:16"
        elif "recraft" in model:
            # Recraft v3 — uses aspect_ratio (no quality param)
            params["aspect_ratio"] = "9:16"
        elif "imagen" in model:
            # Google Imagen — uses aspect_ratio
            params["aspect_ratio"] = "9:16"
        else:
            # Flux, SD, and most others
            params["aspect_ratio"] = "9:16"
            params["quality"] = quality

        url = replicate_create(model, params)
        clip["image_poll_url"] = url
        log.info(f"   Clip {clip['index']}: submitted")
        time.sleep(3)

    for clip in clips:
        clip["image_url"] = replicate_poll(clip["image_poll_url"])
        log.info(f"   Clip {clip['index']}: image ready ✓")

    return clips


# ══════════════════════════════════════════════════════════════
# PHASE 5: GENERATE VIDEOS (Replicate → Seedance-1-Lite)
# ══════════════════════════════════════════════════════════════

def generate_videos(clips: list) -> list:
    """Animate images into videos via configured provider."""
    model = Config.VIDEO_MODEL
    log.info(f"🎥 Phase 5: Generating videos via {model}...")

    # Build params based on model (different models accept different params)
    for clip in clips:
        if "grok-imagine" in model.lower():
            # xAI Grok Imagine Video — uses image_url, mode, prompt
            params = {
                "image_url": clip["image_url"],
                "prompt": clip["motion_prompt"],
                "mode": "normal",
            }
        elif "minimax" in model.lower():
            # Minimax — uses first_frame_image
            params = {
                "first_frame_image": clip["image_url"],
                "prompt": clip["motion_prompt"],
            }
        else:
            # Most models: Seedance, Wan, Kling, Luma, Veo
            params = {
                "image": clip["image_url"],
                "prompt": clip["motion_prompt"],
            }
        # Pass 9:16 where supported
        if "seedance" in model.lower() or "wan" in model.lower():
            params["aspect_ratio"] = "9:16"

        url = replicate_create(model, params)
        clip["video_poll_url"] = url
        log.info(f"   Clip {clip['index']}: submitted")
        time.sleep(3)

    for clip in clips:
        clip["video_url"] = replicate_poll(clip["video_poll_url"], timeout=600)
        log.info(f"   Clip {clip['index']}: video ready ✓")

    return clips


# ══════════════════════════════════════════════════════════════
# PHASE 6: VOICEOVER (ElevenLabs)
# ══════════════════════════════════════════════════════════════

def generate_voiceover(script: dict) -> bytes:
    """Generate voiceover audio via ElevenLabs."""
    log.info("🔊 Phase 6: Generating voiceover via ElevenLabs...")

    text = script["script_full"]
    # Clean for ElevenLabs (prevent chuckling)
    text = re.sub(r'["""]', '', text)

    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{Config.VOICE_ID}",
        headers={
            "xi-api-key": Config.ELEVEN_KEY,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        },
        timeout=30,
    )
    r.raise_for_status()
    audio = r.content
    log.info(f"   Voiceover: {len(audio)} bytes")
    return audio


# ══════════════════════════════════════════════════════════════
# PHASE 7: TRANSCRIBE (OpenAI Whisper)
# ══════════════════════════════════════════════════════════════

def transcribe_voiceover(audio_bytes: bytes) -> dict:
    """Transcribe voiceover for word-level timestamps via Whisper."""
    log.info("📝 Phase 7: Transcribing via OpenAI Whisper...")

    r = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {Config.OPENAI_KEY}"},
        files={"file": ("voiceover.mp3", audio_bytes, "audio/mpeg")},
        data={
            "model": "whisper-1",
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word",
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    words = data.get("words", [])
    log.info(f"   Transcription: {len(words)} words")
    return data


# ══════════════════════════════════════════════════════════════
# PHASE 8: UPLOAD TO R2
# ══════════════════════════════════════════════════════════════

def get_s3_client():
    return boto3.client("s3",
        endpoint_url=Config.R2_ENDPOINT,
        aws_access_key_id=Config.R2_ACCESS_KEY,
        aws_secret_access_key=Config.R2_SECRET_KEY,
        region_name="auto",
    )


def upload_to_r2(folder: str, filename: str, data, content_type: str) -> str:
    """Upload a file to R2, return public URL."""
    s3 = get_s3_client()
    key = f"{folder}/{filename}"

    if isinstance(data, bytes):
        s3.put_object(Bucket=Config.R2_BUCKET, Key=key, Body=data, ContentType=content_type)
    elif isinstance(data, str) and data.startswith("http"):
        # URL — download first, detect real format
        r = requests.get(data, timeout=120)
        r.raise_for_status()
        # Detect actual content type from response or URL
        real_ct = r.headers.get("content-type", content_type).split(";")[0].strip()
        # Fix extension mismatch: if we named it .mp4 but got webm
        if "webm" in real_ct or data.lower().endswith(".webm"):
            key = key.rsplit(".", 1)[0] + ".webm"
            real_ct = "video/webm"
        elif "mp4" in real_ct or data.lower().endswith(".mp4"):
            real_ct = "video/mp4"
        else:
            real_ct = content_type  # fallback to what caller said
        s3.put_object(Bucket=Config.R2_BUCKET, Key=key, Body=r.content, ContentType=real_ct)
        log.info(f"   R2 upload: {key} ({real_ct}, {len(r.content)//1024}KB)")
    elif isinstance(data, str):
        s3.put_object(Bucket=Config.R2_BUCKET, Key=key, Body=data.encode(), ContentType=content_type)

    url = f"{Config.R2_PUBLIC_URL}/{key}"
    return url


def upload_assets(folder: str, clips: list, audio: bytes, srt: str) -> dict:
    """Upload all assets to R2."""
    log.info("☁️  Phase 8: Uploading assets to R2...")

    urls = {"clips": []}

    for clip in clips:
        url = upload_to_r2(folder, f"clip_{clip['index']}.mp4", clip["video_url"], "video/mp4")
        clip["r2_url"] = url
        urls["clips"].append(url)
        log.info(f"   clip_{clip['index']}.mp4 ✓")

    urls["voiceover"] = upload_to_r2(folder, "voiceover.mp3", audio, "audio/mpeg")
    log.info("   voiceover.mp3 ✓")

    urls["srt"] = upload_to_r2(folder, "subtitles.srt", srt, "text/plain")
    log.info("   subtitles.srt ✓")

    return urls


# ══════════════════════════════════════════════════════════════
# PHASE 9: FINAL RENDER (Shotstack)
# ══════════════════════════════════════════════════════════════

def create_srt(script_text: str) -> str:
    """Create simple SRT content."""
    return f"1\n00:00:00,000 --> 00:59:59,000\n{script_text}\n"


def render_video(clips: list, voiceover_url: str, srt_url: str) -> str:
    """Render final video via Shotstack. Returns download URL."""
    log.info("🎞️  Phase 9: Rendering final video via Shotstack...")

    # Build video clips timeline
    video_clips = []
    cursor = 0.0
    for clip in clips:
        dur = 10.0  # Default clip duration
        video_clips.append({
            "asset": {"type": "video", "src": clip["r2_url"], "volume": 0, "transcode": True},
            "start": round(cursor, 3),
            "length": dur,
            "fit": "cover",
        })
        cursor += dur

    total_dur = round(cursor, 3)

    timeline = {
        "tracks": [
            # Logo overlay
            {"clips": [{
                "asset": {"type": "image", "src": Config.LOGO_URL},
                "start": 0, "length": total_dur,
                "position": "topRight",
                "offset": {"x": -0.03, "y": 0.03},
                "scale": 0.12, "opacity": 0.8,
            }]},
            # Video clips
            {"clips": video_clips},
            # Audio
            {"clips": [{
                "asset": {"type": "audio", "src": voiceover_url},
                "start": 0, "length": total_dur,
            }]},
        ],
        "background": "#000000",
    }

    payload = {
        "timeline": timeline,
        "output": {
            "format": "mp4",
            "resolution": "1080",
            "aspectRatio": "9:16",
            "fps": 30,
        },
    }

    r = requests.post("https://api.shotstack.io/v1/render", headers={
        "x-api-key": Config.SHOTSTACK_KEY,
        "Content-Type": "application/json",
    }, json=payload, timeout=30)
    r.raise_for_status()
    job_id = r.json()["response"]["id"]
    log.info(f"   Render job: {job_id}")

    # Poll for completion
    for _ in range(60):
        time.sleep(15)
        r = requests.get(f"https://api.shotstack.io/v1/render/{job_id}", headers={
            "x-api-key": Config.SHOTSTACK_KEY,
        })
        r.raise_for_status()
        data = r.json()["response"]
        status = data.get("status")

        if status == "done":
            download_url = data["url"]
            log.info(f"   Render complete ✓")
            return download_url
        elif status == "failed":
            raise RuntimeError(f"Shotstack render failed: {data}")

    raise TimeoutError("Shotstack render timed out")


# ══════════════════════════════════════════════════════════════
# PHASE 10: GENERATE CAPTIONS (GPT-4o)
# ══════════════════════════════════════════════════════════════

CAPTION_PROMPT = """You are a social media expert. Create platform-optimized content from this viral video.

Video Script: {script}
Topic: {topic}
Category: {category}

PLATFORM REQUIREMENTS:

VIDEO PLATFORMS (with captions):
- TikTok: 300 chars max, trendy casual, 3-5 hashtags
- YouTube Shorts: 500 chars max, searchable keywords, 5-8 hashtags. Also provide a title.
- Instagram Reels: 400 chars max, hashtag-rich, 8-12 hashtags
- Facebook Reels: 400 chars max, conversational, 3-5 hashtags

Use line breaks to separate thoughts. MINIMAL emojis (0-2 per caption).
CTA must be on its own line. Hashtags grouped at end.

Return as JSON:
{{
  "tiktok": "caption text",
  "youtube": "caption text",
  "youtube_title": "short title",
  "instagram": "caption text",
  "facebook": "caption text"
}}
"""

TEXT_POST_PROMPT = """You are a multi-platform content strategist. Transform this viral video into TEXT-ONLY content.

Video Script: {script}
Topic: {topic}
Category: {category}

1. X/TWITTER: Single viral tweet, 280 chars max, NO hashtags
2. THREADS: Conversational, 500 chars max
3. PINTEREST: 400-500 chars, educational, 5-7 hashtags

Return as JSON:
{{
  "twitter": "tweet text",
  "threads": "threads text",
  "pinterest": "pinterest caption"
}}
"""

def generate_captions(script: dict, topic: dict) -> dict:
    """Generate platform-specific captions via GPT-4o."""
    log.info("💬 Phase 10: Generating captions via GPT-4o...")

    captions = {}

    for label, prompt_tpl in [("video", CAPTION_PROMPT), ("text", TEXT_POST_PROMPT)]:
        prompt = prompt_tpl.format(
            script=script["script_full"],
            topic=topic["idea"],
            category=topic["category"],
        )

        r = requests.post("https://api.openai.com/v1/chat/completions", headers={
            "Authorization": f"Bearer {Config.OPENAI_KEY}",
            "Content-Type": "application/json",
        }, json={
            "model": Config.OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,
            "max_tokens": 2000,
        })
        r.raise_for_status()

        text = r.json()["choices"][0]["message"]["content"]
        raw = re.sub(r'^```json\s*\n?', '', text, flags=re.IGNORECASE)
        raw = re.sub(r'\n?```\s*$', '', raw).strip()

        try:
            parsed = json.loads(raw)
            captions.update(parsed)
        except json.JSONDecodeError:
            log.warning(f"   Failed to parse {label} captions")

    log.info(f"   Captions: {len(captions)} platforms")
    return captions


# ══════════════════════════════════════════════════════════════
# PHASE 11: PUBLISH VIA BLOTATO
# ══════════════════════════════════════════════════════════════

def blotato_upload_media(video_url: str) -> str:
    """Upload video to Blotato, return media URL."""
    r = requests.post("https://backend.blotato.com/v2/media", headers={
        "Authorization": f"Bearer {Config.BLOTATO_KEY}",
        "Content-Type": "application/json",
    }, json={"url": video_url})
    r.raise_for_status()
    return r.json().get("url", video_url)


def blotato_post(account_id: str, platform: str, caption: str,
                 media_urls: list = None, schedule_time: str = None, **kwargs):
    """Post to a platform via Blotato."""
    if not account_id:
        log.info(f"   ⏭️  {platform}: no account ID, skipping")
        return None

    payload = {
        "post": {
            "accountId": account_id,
            "content": {
                "text": caption,
                "mediaUrls": media_urls or [],
                "platform": platform,
            },
            "target": {"targetType": platform, **kwargs},
        },
    }
    if schedule_time:
        payload["scheduledTime"] = schedule_time

    r = requests.post("https://backend.blotato.com/v2/posts", headers={
        "Authorization": f"Bearer {Config.BLOTATO_KEY}",
        "Content-Type": "application/json",
    }, json=payload, timeout=30)

    if r.ok:
        log.info(f"   ✓ {platform}")
    else:
        log.warning(f"   ✗ {platform}: {r.status_code}")

    return r.json() if r.ok else None


def publish_everywhere(final_video_url: str, captions: dict, topic: dict):
    """Publish video + text to all platforms via Blotato."""
    log.info("📡 Phase 11: Publishing to all platforms via Blotato...")

    acct = Config.BLOTATO_ACCOUNTS

    # Upload media to Blotato
    media_url = blotato_upload_media(final_video_url)

    # Schedule times (tomorrow, optimal hours EST→UTC)
    tomorrow = datetime.now() + timedelta(days=1)
    times = {
        "tiktok":    tomorrow.replace(hour=20, minute=0).isoformat() + "Z",  # 3pm EST
        "youtube":   tomorrow.replace(hour=18, minute=30).isoformat() + "Z",
        "instagram": tomorrow.replace(hour=17, minute=0).isoformat() + "Z",
        "facebook":  tomorrow.replace(hour=19, minute=0).isoformat() + "Z",
    }

    # Video platforms
    blotato_post(acct["tiktok"], "tiktok", captions.get("tiktok", ""),
                 [media_url], times["tiktok"],
                 privacyLevel="PUBLIC_TO_EVERYONE", isAiGenerated=True)

    blotato_post(acct["youtube"], "youtube", captions.get("youtube", ""),
                 [media_url], times["youtube"],
                 title=captions.get("youtube_title", topic["idea"]),
                 privacyStatus="public", shouldNotifySubscribers=True)

    blotato_post(acct["instagram"], "instagram", captions.get("instagram", ""),
                 [media_url], times["instagram"])

    blotato_post(acct["facebook"], "facebook", captions.get("facebook", ""),
                 [media_url], times["facebook"],
                 pageId=acct.get("facebook_page"))

    # Text platforms
    blotato_post(acct["twitter"], "twitter", captions.get("twitter", ""))
    blotato_post(acct["threads"], "threads", captions.get("threads", ""))


# ══════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════════

def run_pipeline(progress_cb=None, resume_from: int = 0) -> dict:
    """Execute the full pipeline with checkpoint/resume support.
    
    resume_from: Phase index to resume from (0 = start fresh).
    Checkpoints are saved after each phase to /tmp/pipeline_checkpoint.json
    """
    CHECKPOINT_FILE = "/tmp/pipeline_checkpoint.json"
    start = time.time()
    result = {"status": "running", "phases": [], "error": None}

    # Load checkpoint if resuming
    ckpt = {}
    if resume_from > 0:
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                ckpt = json.load(f)
            log.info(f"♻️  Resuming from phase {resume_from} (checkpoint loaded)")
        except Exception as e:
            log.error(f"No checkpoint found: {e}")
            return {"status": "failed", "error": f"No checkpoint found for resume: {e}", "phases": []}

    def save_checkpoint(phase_idx, data):
        """Save accumulated state after each phase."""
        ckpt.update(data)
        ckpt["_last_phase"] = phase_idx
        try:
            with open(CHECKPOINT_FILE, "w") as f:
                json.dump(ckpt, f)
        except Exception as e:
            log.warning(f"Checkpoint save failed: {e}")

    def notify(idx, name, status):
        if progress_cb:
            try: progress_cb(idx, name, status)
            except: pass

    try:
        # ── Phase 1: Fetch topic ────────────────────────────────
        if resume_from <= 0:
            notify(0, "Fetch Topic", "running")
            topic = fetch_topic()
            update_airtable(topic["airtable_id"], {"Status": "Processing"})
            result["phases"].append({"name": "Fetch Topic", "status": "done"})
            result["topic"] = topic
            save_checkpoint(0, {"topic": topic})
            notify(0, "Fetch Topic", "done")
        else:
            topic = ckpt["topic"]
            result["topic"] = topic
            result["phases"].append({"name": "Fetch Topic", "status": "done"})
            notify(0, "Fetch Topic", "done")

        # ── Phase 2: Generate script ────────────────────────────
        if resume_from <= 1:
            notify(1, "Generate Script", "running")
            script = generate_script(topic) if resume_from < 1 else ckpt.get("script") or generate_script(topic)
            result["phases"].append({"name": "Generate Script", "status": "done"})
            result["script"] = script
            save_checkpoint(1, {"script": script})
            notify(1, "Generate Script", "done")
        else:
            script = ckpt["script"]
            result["script"] = script
            result["phases"].append({"name": "Generate Script", "status": "done"})
            notify(1, "Generate Script", "done")

        # ── Phase 3: Scene engine ───────────────────────────────
        if resume_from <= 2:
            notify(2, "Scene Engine", "running")
            clips = scene_engine(script, topic) if resume_from < 2 else ckpt.get("clips") or scene_engine(script, topic)
            result["phases"].append({"name": "Scene Engine", "status": "done"})
            save_checkpoint(2, {"clips": clips})
            notify(2, "Scene Engine", "done")
        else:
            clips = ckpt["clips"]
            result["phases"].append({"name": "Scene Engine", "status": "done"})
            notify(2, "Scene Engine", "done")

        # ── Phase 4: Generate images ────────────────────────────
        if resume_from <= 3:
            notify(3, "Generate Images", "running")
            clips = generate_images(clips) if resume_from < 3 else (ckpt.get("clips_with_images") or generate_images(clips))
            result["phases"].append({"name": "Generate Images", "status": "done"})
            result["images"] = [{"index": c["index"], "url": c["image_url"], "prompt": c.get("image_prompt","")} for c in clips]
            save_checkpoint(3, {"clips_with_images": clips})
            notify(3, "Generate Images", "done")
        else:
            clips = ckpt["clips_with_images"]
            result["images"] = [{"index": c["index"], "url": c["image_url"], "prompt": c.get("image_prompt","")} for c in clips]
            result["phases"].append({"name": "Generate Images", "status": "done"})
            notify(3, "Generate Images", "done")

        # ── Phase 5: Generate videos ────────────────────────────
        if resume_from <= 4:
            notify(4, "Generate Videos", "running")
            clips = generate_videos(clips) if resume_from < 4 else (ckpt.get("clips_with_videos") or generate_videos(clips))
            result["phases"].append({"name": "Generate Videos", "status": "done"})
            result["videos"] = [{"index": c["index"], "url": c["video_url"]} for c in clips]
            save_checkpoint(4, {"clips_with_videos": clips})
            notify(4, "Generate Videos", "done")
        else:
            clips = ckpt["clips_with_videos"]
            result["videos"] = [{"index": c["index"], "url": c["video_url"]} for c in clips]
            result["phases"].append({"name": "Generate Videos", "status": "done"})
            notify(4, "Generate Videos", "done")

        # ── Phase 6: Voiceover ──────────────────────────────────
        if resume_from <= 5:
            notify(5, "Voiceover", "running")
            audio = generate_voiceover(script)
            result["phases"].append({"name": "Voiceover", "status": "done"})
            result["voiceover_size"] = len(audio)
            # Save audio as base64 in checkpoint (it's bytes)
            import base64
            save_checkpoint(5, {"audio_b64": base64.b64encode(audio).decode()})
            notify(5, "Voiceover", "done")
        else:
            import base64
            audio = base64.b64decode(ckpt["audio_b64"])
            result["voiceover_size"] = len(audio)
            result["phases"].append({"name": "Voiceover", "status": "done"})
            notify(5, "Voiceover", "done")

        # ── Phase 7: Transcribe ─────────────────────────────────
        if resume_from <= 6:
            notify(6, "Transcribe", "running")
            transcription = transcribe_voiceover(audio)
            result["phases"].append({"name": "Transcribe", "status": "done"})
            save_checkpoint(6, {"transcription": transcription})
            notify(6, "Transcribe", "done")
        else:
            transcription = ckpt["transcription"]
            result["phases"].append({"name": "Transcribe", "status": "done"})
            notify(6, "Transcribe", "done")

        # ── Phase 8: Upload to R2 ──────────────────────────────
        if resume_from <= 7:
            notify(7, "Upload Assets", "running")
            folder = f"{topic['airtable_id']}_{topic['idea'][:30]}"
            folder = re.sub(r'[^a-zA-Z0-9_-]', '_', folder)
            srt = create_srt(script["script_full"])
            urls = upload_assets(folder, clips, audio, srt)
            result["phases"].append({"name": "Upload to R2", "status": "done"})
            save_checkpoint(7, {"folder": folder, "urls": urls, "clips_uploaded": clips})
            notify(7, "Upload Assets", "done")
        else:
            folder = ckpt["folder"]
            urls = ckpt["urls"]
            clips = ckpt.get("clips_uploaded", clips)
            result["phases"].append({"name": "Upload to R2", "status": "done"})
            notify(7, "Upload Assets", "done")

        # ── Phase 9: Final render ──────────────────────────────
        if resume_from <= 8:
            notify(8, "Final Render", "running")
            final_url = render_video(clips, urls["voiceover"], urls["srt"])
            final_r2_url = upload_to_r2(folder, "final.mp4", final_url, "video/mp4")
            result["phases"].append({"name": "Final Render", "status": "done"})
            result["final_video"] = final_r2_url
            save_checkpoint(8, {"final_r2_url": final_r2_url})
            notify(8, "Final Render", "done")
        else:
            final_r2_url = ckpt["final_r2_url"]
            result["final_video"] = final_r2_url
            result["phases"].append({"name": "Final Render", "status": "done"})
            notify(8, "Final Render", "done")

        # ── Phase 10: Captions ──────────────────────────────────
        if resume_from <= 9:
            notify(9, "Captions", "running")
            captions = generate_captions(script, topic)
            result["phases"].append({"name": "Generate Captions", "status": "done"})
            save_checkpoint(9, {"captions": captions})
            notify(9, "Captions", "done")
        else:
            captions = ckpt["captions"]
            result["phases"].append({"name": "Generate Captions", "status": "done"})
            notify(9, "Captions", "done")

        # ── Phase 11: Publish ───────────────────────────────────
        notify(10, "Publish", "running")
        publish_everywhere(final_r2_url, captions, topic)
        result["phases"].append({"name": "Publish", "status": "done"})
        notify(10, "Publish", "done")

        # Update Airtable
        update_airtable(topic["airtable_id"], {
            "Status": "Published",
            "Final Video URL": final_r2_url,
        })

        result["status"] = "complete"
        elapsed = round(time.time() - start, 1)
        result["duration"] = f"{elapsed}s"
        log.info(f"\n✅ Pipeline complete in {elapsed}s — {final_r2_url}")

        # Clean up checkpoint on success
        try: os.remove(CHECKPOINT_FILE)
        except: pass

    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        # Track which phase we were on for resume
        result["failed_phase"] = ckpt.get("_last_phase", 0) + 1 if ckpt.get("_last_phase") is not None else 0
        log.error(f"\n❌ Pipeline failed at phase {result['failed_phase']}: {e}")

        # Update Airtable if we have the topic
        if "topic" in result:
            update_airtable(result["topic"]["airtable_id"], {
                "Status": "Failed",
                "Error": str(e),
            })

    return result


if __name__ == "__main__":
    run_pipeline()
