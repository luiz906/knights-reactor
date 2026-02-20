"""
Biblical Knights Content Reactor — Pipeline Engine v2
=====================================================
Phase 2: Local Topic DB, Prompt Editing Gates, Video Approval Gates

Pipeline: Topic DB → Script → Scenes → [EDIT PROMPTS] → Images → Videos →
          [APPROVE VIDEOS] → Voice → Transcribe → Render → Upload → Publish
"""

import os, json, time, random, re, io, csv, logging, base64
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

DATA_DIR = Path("/var/data") if Path("/var/data").exists() else Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

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
    VOICE_MODEL       = "eleven_turbo_v2"
    VOICE_STABILITY   = 0.5
    VOICE_SIMILARITY  = 0.75
    VOICE_SPEED       = 1.0
    VOICE_STYLE       = 0.0

    # Script
    SCRIPT_MODEL      = "gpt-4o"
    SCRIPT_TEMP       = 0.85
    SCRIPT_WORDS      = 90   # word count target (integer, used by slider)

    # Scene Engine
    SCENE_STYLE       = "photorealistic"  # photorealistic | cinematic | painterly | anime
    SCENE_CAMERA      = "steady"          # steady | dynamic | handheld
    SCENE_MOOD_BIAS   = "auto"            # auto | storm | fire | dawn | night | grey | battle

    # Video clips
    CLIP_COUNT        = 3
    CLIP_DURATION     = 10.0
    VIDEO_TIMEOUT     = 600

    # Render output
    RENDER_FPS        = 30
    RENDER_RES        = "1080"
    RENDER_ASPECT     = "9:16"
    RENDER_BG         = "#000000"

    # Logo / Watermark
    LOGO_URL          = env("LOGO_URL", "https://pub-8d4a1338211a44a7875ebe6ac8487129.r2.dev/gods_knights.png")
    LOGO_ENABLED      = True
    LOGO_POSITION     = "topRight"
    LOGO_SCALE        = 0.12
    LOGO_OPACITY      = 0.8

    # CTA clip
    CTA_ENABLED       = True
    CTA_URL           = env("CTA_URL", "https://pub-8d4a1338211a44a7875ebe6ac8487129.r2.dev/ChristCTA.mp4")
    CTA_DURATION      = 5.0

    # Platform toggles
    ON_TT = True; ON_YT = True; ON_IG = True; ON_FB = True
    ON_TW = True; ON_TH = True; ON_PN = False

    # Shotstack
    SHOTSTACK_KEY     = env("SHOTSTACK_API_KEY")
    SHOTSTACK_ENV     = env("SHOTSTACK_ENV", "stage")

    # Cloudflare R2
    R2_ACCESS_KEY     = env("R2_ACCESS_KEY")
    R2_SECRET_KEY     = env("R2_SECRET_KEY")
    R2_ENDPOINT       = env("R2_ENDPOINT")
    R2_BUCKET         = env("R2_BUCKET", "app-knight-videos")
    R2_PUBLIC_URL     = env("R2_PUBLIC_URL", "https://pub-8d4a1338211a44a7875ebe6ac8487129.r2.dev")

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


# ══════════════════════════════════════════════════════════════
# TOPIC DATABASE (replaces Airtable)
# ══════════════════════════════════════════════════════════════
TOPICS_FILE = DATA_DIR / "topics.json"
CATEGORIES = ["Shocking Revelations","Shocking Reveal","Behind-the-Scenes","Myths Debunked","Deep Dive Analysis"]

def load_topics():
    if TOPICS_FILE.exists():
        try: return json.loads(TOPICS_FILE.read_text())
        except: pass
    return []

def save_topics(topics):
    TOPICS_FILE.write_text(json.dumps(topics, indent=2))

def add_topic(idea, category, scripture=""):
    topics = load_topics()
    t = {"id": f"t_{int(time.time()*1000)}_{random.randint(100,999)}", "idea": idea.strip(),
         "category": category.strip(), "scripture": scripture.strip(), "status": "new",
         "created": datetime.now().isoformat()}
    topics.append(t); save_topics(topics); return t

def delete_topic(topic_id):
    topics = load_topics()
    topics = [t for t in topics if t.get("id") != topic_id]
    save_topics(topics)

def fetch_next_topic(topic_id=None):
    """Get next new topic, or specific one by ID."""
    topics = load_topics()
    if topic_id:
        for t in topics:
            if t.get("id") == topic_id:
                t["status"] = "processing"; save_topics(topics); return t
        raise RuntimeError(f"Topic {topic_id} not found")
    for t in topics:
        if t.get("status") == "new":
            t["status"] = "processing"; save_topics(topics); return t
    raise RuntimeError("No new topics - add topics or generate with AI")

def update_topic_status(topic_id, status, extra=None):
    topics = load_topics()
    for t in topics:
        if t.get("id") == topic_id:
            t["status"] = status
            if extra: t.update(extra)
            break
    save_topics(topics)

def generate_topics_ai(count=10):
    """Generate topics via GPT-4o."""
    log.info(f"Generating {count} topics via GPT-4o...")
    prompt = (f"Generate {count} unique viral short-form video topics for a Christian mens faith channel called Gods Knights. "
              "The brand voice is a battle-hardened medieval knight speaking to modern men about real daily struggles through scripture and warfare metaphors. "
              "CATEGORIES: Shocking Revelations, Shocking Reveal, Behind-the-Scenes, Myths Debunked, Deep Dive Analysis. "
              "Each topic must address a REAL daily battle men face: finances, marriage, temptation, lust, anger, fatherhood, discipline, doubt, purpose, leadership, addiction, laziness, fear. "
              'Return ONLY a JSON array: [{"idea":"topic title","category":"one category","scripture":"verse ref"}]. '
              "Make them provocative and scroll-stopping. No generic churchy language.")
    r = requests.post("https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {Config.OPENAI_KEY}", "Content-Type": "application/json"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": prompt}], "temperature": 0.9, "max_tokens": 3000}, timeout=30)
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    raw = re.sub(r'^```json\s*\n?', '', text, flags=re.IGNORECASE)
    raw = re.sub(r'\n?```\s*$', '', raw).strip()
    try: items = json.loads(raw)
    except: return []
    added = []
    for item in items:
        if isinstance(item, dict) and item.get("idea"):
            added.append(add_topic(item["idea"], item.get("category", random.choice(CATEGORIES)), item.get("scripture", "")))
    log.info(f"   Generated {len(added)} topics")
    return added

def seed_default_topics():
    """Seed 100 default topics if DB is empty."""
    if load_topics(): return
    log.info("Seeding 100 default topics...")
    defaults = [
        ("The Sword You Never Picked Up","Shocking Revelations","Ephesians 6:17"),
        ("Your Silence Is Killing Your Family","Shocking Reveal","Joshua 24:15"),
        ("Why Most Christian Men Are Losing","Myths Debunked","1 Corinthians 16:13"),
        ("The Battle Before Sunrise","Behind-the-Scenes","Mark 1:35"),
        ("Armor of God Is Not Decoration","Deep Dive Analysis","Ephesians 6:11"),
        ("Stop Praying Safe Prayers","Shocking Revelations","James 5:16"),
        ("The Enemy Knows Your Routine","Shocking Reveal","1 Peter 5:8"),
        ("Discipline Is the Weapon You Lack","Myths Debunked","Proverbs 25:28"),
        ("Your Wife Needs a Warrior Not a Roommate","Behind-the-Scenes","Ephesians 5:25"),
        ("The Cost of Comfortable Christianity","Deep Dive Analysis","Revelation 3:16"),
        ("Lust Is a Siege Not a Surprise","Shocking Revelations","James 1:14-15"),
        ("You Were Built for War Not Comfort","Shocking Reveal","2 Timothy 2:3-4"),
        ("The Shield of Faith Is Not Optional","Deep Dive Analysis","Ephesians 6:16"),
        ("Anger Unchanneled Destroys Everything","Myths Debunked","Proverbs 29:11"),
        ("Rise Before the Enemy Does","Behind-the-Scenes","Psalm 5:3"),
        ("Debt Is a Chain Not a Tool","Shocking Revelations","Proverbs 22:7"),
        ("Your Sons Are Watching Your Fight","Shocking Reveal","Deuteronomy 6:7"),
        ("The Night Watch No One Sees","Behind-the-Scenes","Psalm 130:6"),
        ("Doubt Is Not the Opposite of Faith","Deep Dive Analysis","Mark 9:24"),
        ("Forgiveness Is a Battlefield Decision","Myths Debunked","Matthew 6:14-15"),
        ("The Helmet of Salvation Protects Your Mind","Deep Dive Analysis","Ephesians 6:17"),
        ("Pornography Is the Silent Siege","Shocking Revelations","Matthew 5:28"),
        ("Most Men Die Without Purpose","Shocking Reveal","Proverbs 29:18"),
        ("The Forge That Makes the Sword","Behind-the-Scenes","Isaiah 48:10"),
        ("Patience Is Not Passive","Myths Debunked","James 1:4"),
        ("Stop Waiting for Permission to Lead","Shocking Reveal","1 Timothy 4:12"),
        ("The Graveyard of Wasted Potential","Shocking Revelations","Matthew 25:25"),
        ("One Decision Away from Ruin","Behind-the-Scenes","Proverbs 14:12"),
        ("Brotherhood Was Never Optional","Myths Debunked","Ecclesiastes 4:9-10"),
        ("The Weight Only You Can Carry","Deep Dive Analysis","Galatians 6:5"),
        ("Fear Dressed as Wisdom","Shocking Revelations","2 Timothy 1:7"),
        ("The Morning Ritual That Changes Everything","Behind-the-Scenes","Psalm 143:8"),
        ("Your Excuses Sound Like Retreat","Shocking Reveal","Judges 6:15-16"),
        ("The Belt of Truth Holds Everything Together","Deep Dive Analysis","Ephesians 6:14"),
        ("Comparison Is the Thief of Calling","Myths Debunked","Galatians 6:4"),
        ("Lead Your Home or Someone Else Will","Shocking Reveal","1 Timothy 5:8"),
        ("Fatigue Is Not an Excuse to Surrender","Behind-the-Scenes","Galatians 6:9"),
        ("The Cross Was Not Comfortable","Shocking Revelations","Luke 9:23"),
        ("Obedience Over Understanding","Deep Dive Analysis","Proverbs 3:5-6"),
        ("Pride Goes Before the Ambush","Myths Debunked","Proverbs 16:18"),
        ("Your Marriage Is a Fortress","Behind-the-Scenes","Ecclesiastes 4:12"),
        ("The Breastplate Guards What Matters","Deep Dive Analysis","Ephesians 6:14"),
        ("Addiction Is a Stronghold Not a Habit","Shocking Revelations","2 Corinthians 10:4"),
        ("The Narrow Path Was Never Popular","Shocking Reveal","Matthew 7:14"),
        ("Guard Your Eyes Like the City Gate","Behind-the-Scenes","Job 31:1"),
        ("Surrender Is Not Weakness","Myths Debunked","Romans 12:1"),
        ("Built for the Storm","Deep Dive Analysis","Matthew 7:25"),
        ("Every Knight Has Scars","Behind-the-Scenes","2 Corinthians 11:25"),
        ("The Sword of the Spirit Is Your Only Offense","Deep Dive Analysis","Ephesians 6:17"),
        ("Stop Negotiating with Temptation","Shocking Reveal","Genesis 39:12"),
        ("The Watch That Never Ends","Behind-the-Scenes","1 Thessalonians 5:6"),
        ("Grace Is Not a License to Be Soft","Myths Debunked","Romans 6:1-2"),
        ("Prepare in Secret Win in Public","Shocking Revelations","Matthew 6:6"),
        ("Your Prayer Life Is Your Battle Plan","Deep Dive Analysis","Ephesians 6:18"),
        ("Laziness Wears a Crown of Excuses","Shocking Reveal","Proverbs 13:4"),
        ("The Desert Was Always Part of the Journey","Behind-the-Scenes","Deuteronomy 8:2"),
        ("Truth Without Love Is a Weapon Misused","Myths Debunked","Ephesians 4:15"),
        ("Every Day Is a Battle Whether You Show Up or Not","Shocking Revelations","Ephesians 6:12"),
        ("You Cannot Protect What You Will Not Face","Shocking Reveal","Nehemiah 4:14"),
        ("The Campfire Before the War","Behind-the-Scenes","Psalm 27:3"),
        ("Faith Without Works Is a Dull Sword","Myths Debunked","James 2:26"),
        ("The River You Must Cross Alone","Deep Dive Analysis","Joshua 3:13"),
        ("Tithing Is Training Not Taxation","Shocking Revelations","Malachi 3:10"),
        ("Your Anger Belongs to God Not You","Myths Debunked","Ephesians 4:26"),
        ("The Gatekeeper of Your Household","Behind-the-Scenes","Psalm 101:2"),
        ("Endurance Is Not Glamorous","Deep Dive Analysis","Hebrews 12:1"),
        ("The Battle You Are Avoiding Is the One You Need","Shocking Reveal","1 Samuel 17:32"),
        ("Social Media Is the New Colosseum","Shocking Revelations","Romans 12:2"),
        ("Fasting Is the Weapon You Forgot","Myths Debunked","Matthew 17:21"),
        ("The Quiet Obedience Nobody Celebrates","Behind-the-Scenes","1 Samuel 15:22"),
        ("Financial Stewardship Is Spiritual Warfare","Deep Dive Analysis","Luke 16:11"),
        ("The Tower You Built Without God","Shocking Reveal","Genesis 11:4"),
        ("Grief Is Not Defeat","Myths Debunked","Psalm 34:18"),
        ("Standing Alone When Everyone Retreats","Behind-the-Scenes","2 Timothy 4:16"),
        ("The Covenant You Made and Forgot","Shocking Revelations","Ecclesiastes 5:5"),
        ("Teach Your Sons to Fight","Shocking Reveal","Proverbs 22:6"),
        ("The Midnight Hour Before Breakthrough","Deep Dive Analysis","Acts 16:25"),
        ("Comfort Is the Enemy of Calling","Myths Debunked","Hebrews 11:8"),
        ("The March Nobody Sees","Behind-the-Scenes","Hebrews 11:1"),
        ("Integrity Is Armor Not Image","Shocking Revelations","Proverbs 10:9"),
        ("You Were Called to Build Not Just Believe","Shocking Reveal","Nehemiah 2:18"),
        ("Rest Is a Command Not a Reward","Myths Debunked","Mark 6:31"),
        ("The Valley of the Shadow Is a Path Not a Prison","Deep Dive Analysis","Psalm 23:4"),
        ("Your Legacy Starts Today Not Tomorrow","Shocking Reveal","Psalm 78:4"),
        ("Lukewarm Men Build Nothing","Shocking Revelations","Revelation 3:16"),
        ("The Shield Wall Requires Brothers","Behind-the-Scenes","Proverbs 27:17"),
        ("Suffering Produces Something You Cannot Buy","Deep Dive Analysis","Romans 5:3-4"),
        ("The Idol You Call Normal","Myths Debunked","Exodus 20:3"),
        ("Guard the Gate of Your Mouth","Behind-the-Scenes","Proverbs 18:21"),
        ("Victory Was Already Decided","Deep Dive Analysis","1 Corinthians 15:57"),
        ("The Man Who Knelt Before He Stood","Shocking Reveal","Daniel 6:10"),
        ("Generosity Is a Weapon Against Greed","Myths Debunked","2 Corinthians 9:7"),
        ("The Long Road Home","Behind-the-Scenes","Luke 15:20"),
        ("Wolves Dress Like Shepherds","Shocking Revelations","Matthew 7:15"),
        ("The Test You Cannot Cheat","Deep Dive Analysis","James 1:12"),
        ("Your Body Is a Temple Not a Playground","Myths Debunked","1 Corinthians 6:19"),
        ("The Preparation That Takes Years","Behind-the-Scenes","Galatians 1:17-18"),
        ("You Do Not Need Permission to Obey God","Shocking Reveal","Acts 5:29"),
        ("The Fire That Purifies Not Destroys","Deep Dive Analysis","1 Peter 1:7"),
        ("Repentance Is Strength Not Shame","Myths Debunked","Acts 3:19"),
    ]
    for idea, cat, scripture in defaults:
        add_topic(idea, cat, scripture)
    log.info(f"   Seeded {len(defaults)} topics")


def fetch_topic() -> dict:
    """Get next new topic from local DB (backward compat wrapper)."""
    return fetch_next_topic()


def update_airtable(record_id: str, fields: dict):
    """Update topic status (backward compat wrapper)."""
    status = fields.get("Status", "").lower()
    if status:
        update_topic_status(record_id, status, fields)


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

def build_script_prompt():
    """Build the script prompt dynamically from Config values."""
    words = int(Config.SCRIPT_WORDS)  # integer e.g. 90
    secs = round(words / 3)  # ~3 words per second
    low = max(words - 10, 20)
    high = words + 10
    
    return f"""## ⚠️ WORD COUNT: ~{words} WORDS ⚠️

TOTAL SCRIPT: {low}-{high} WORDS ({secs} seconds at measured pace — 3 words/sec)

Before you output, COUNT YOUR WORDS. Target exactly {words}. Too short sounds rushed. Too long gets cut off.

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

    prompt = build_script_prompt().format(
        topic=topic["idea"],
        category=cat,
        angle=angle,
    )

    r = requests.post("https://api.openai.com/v1/chat/completions", headers={
        "Authorization": f"Bearer {Config.OPENAI_KEY}",
        "Content-Type": "application/json",
    }, json={
        "model": Config.SCRIPT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": Config.SCRIPT_TEMP,
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
    "storm": "Cinematic dark atmosphere, cold blue-grey tones, rain, fog, 9:16 vertical, {style}.",
    "fire": "Cinematic dark atmosphere, orange ember glow against darkness, smoke, ash particles, 9:16 vertical, {style}.",
    "dawn": "Cinematic golden hour light, warm amber highlights, cold shadows, fog, 9:16 vertical, {style}.",
    "night": "Cinematic moonlit scene, silver-blue cold tones, deep shadows, mist, 9:16 vertical, {style}.",
    "grey": "Cinematic overcast atmosphere, muted grey tones, rain, wet surfaces, 9:16 vertical, {style}.",
    "battle": "Cinematic dark atmosphere, smoke, distant fire, debris, dramatic lighting, 9:16 vertical, {style}.",
}

CAMERA_STYLES = {
    "steady": "Steady camera.",
    "dynamic": "Dynamic cinematic camera movement.",
    "handheld": "Handheld shaky camera, raw documentary feel.",
}


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
    """Generate clip prompt pairs (image + motion). Direct port of Scene Engine v6."""
    log.info(f"🎬 Phase 3: Scene Engine v6 | Clips: {Config.CLIP_COUNT} | Style: {Config.SCENE_STYLE} | Camera: {Config.SCENE_CAMERA}")

    all_text = " ".join([
        script["hook"], script["build"], script["reveal"],
        script.get("tone", ""), topic.get("category", ""), topic.get("idea", ""),
    ]).lower()

    # Mood: use config bias or auto-detect from script
    if Config.SCENE_MOOD_BIAS != "auto" and Config.SCENE_MOOD_BIAS in IMAGE_SUFFIXES:
        theme = Config.SCENE_MOOD_BIAS
        # Match stories to forced mood
        matching = [s for s in STORY_SEEDS if s["mood"] == Config.SCENE_MOOD_BIAS]
        if not matching:
            matching = STORY_SEEDS
    else:
        theme = detect_theme(all_text)
        if theme == "random":
            matching = STORY_SEEDS
        else:
            matching = [s for s in STORY_SEEDS if theme in s["themes"]]
            if not matching:
                matching = STORY_SEEDS

    story = pick(matching)
    figure = pick(FIGURES)
    # Apply configurable style to image suffix
    img_suffix = IMAGE_SUFFIXES.get(story["mood"], IMAGE_SUFFIXES["dawn"]).format(style=Config.SCENE_STYLE)
    # Apply configurable camera to tech suffix
    tech_suffix = CAMERA_STYLES.get(Config.SCENE_CAMERA, CAMERA_STYLES["steady"]) + " 9:16 vertical."

    clips = []
    story_clips = story["clips"]
    target_count = Config.CLIP_COUNT
    # Extend or trim clips to match target count
    while len(story_clips) < target_count:
        story_clips = story_clips + story["clips"]  # cycle through
    story_clips = story_clips[:target_count]

    for i, clip in enumerate(story_clips):
        image_prompt = f"{figure} {clip['action']}. {clip['setting']}. {clip['composition']}. {clip['lighting']}. {clip['atmosphere']}. {img_suffix}"
        motion_prompt = f"{clip['camera']}. {clip['subject']}. {clip['ambient']}. {clip['pace']} {tech_suffix}"
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
    for attempt in range(5):
        r = requests.post(
            f"https://api.replicate.com/v1/models/{model}/predictions",
            headers={
                "Authorization": f"Bearer {Config.REPLICATE_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"input": input_data},
            timeout=30,
        )
        if r.status_code == 429:
            wait = min(30 * (attempt + 1), 120)
            log.warning(f"   Rate limited (429), waiting {wait}s before retry {attempt+2}/5...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()["urls"]["get"]
    raise Exception("Replicate rate limit: 5 retries exhausted")


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
        time.sleep(8)  # Avoid 429 rate limits

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
# PHASE 5b: REGENERATE SINGLE VIDEO CLIP
# ══════════════════════════════════════════════════════════════

def generate_video_single(clip: dict) -> dict:
    """Regenerate a single video clip. Used by video approval gate."""
    model = Config.VIDEO_MODEL
    log.info(f"🎥 Regenerating clip {clip.get('index','')} via {model}...")

    if "grok-imagine" in model.lower():
        params = {"image_url": clip["image_url"], "prompt": clip["motion_prompt"], "mode": "normal"}
    elif "minimax" in model.lower():
        params = {"first_frame_image": clip["image_url"], "prompt": clip["motion_prompt"]}
    else:
        params = {"image": clip["image_url"], "prompt": clip["motion_prompt"]}
    if "seedance" in model.lower() or "wan" in model.lower():
        params["aspect_ratio"] = "9:16"

    url = replicate_create(model, params)
    clip["video_poll_url"] = url
    clip["video_url"] = replicate_poll(url, timeout=600)
    log.info(f"   Clip {clip.get('index','')}: video regenerated ✓")
    return clip


# ══════════════════════════════════════════════════════════════
# PHASE 6: VOICEOVER (ElevenLabs)
# ══════════════════════════════════════════════════════════════

def generate_voiceover(script: dict) -> bytes:
    """Generate voiceover audio via ElevenLabs."""
    log.info(f"🔊 Phase 6: Generating voiceover via ElevenLabs | Voice: {Config.VOICE_ID} | Model: {Config.VOICE_MODEL}")

    text = script["script_full"]
    # Clean for ElevenLabs (prevent chuckling)
    text = re.sub(r'["""]', '', text)

    voice_settings = {
        "stability": Config.VOICE_STABILITY,
        "similarity_boost": Config.VOICE_SIMILARITY,
    }
    if Config.VOICE_STYLE > 0:
        voice_settings["style"] = Config.VOICE_STYLE
    if Config.VOICE_SPEED != 1.0:
        voice_settings["speed"] = Config.VOICE_SPEED

    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{Config.VOICE_ID}",
        headers={
            "xi-api-key": Config.ELEVEN_KEY,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": Config.VOICE_MODEL,
            "voice_settings": voice_settings,
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
        # Check if bytes are actually webm when named mp4
        if filename.endswith(".mp4") and data[:4] == b'\x1a\x45\xdf\xa3':
            filename = filename.rsplit(".", 1)[0] + ".webm"
            content_type = "video/webm"
            key = f"{folder}/{filename}"
        s3.put_object(Bucket=Config.R2_BUCKET, Key=key, Body=data, ContentType=content_type)
    elif isinstance(data, str) and data.startswith("http"):
        # URL — download first, detect real format
        r = requests.get(data, timeout=120)
        r.raise_for_status()
        body = r.content
        hdr_ct = r.headers.get("content-type", "").split(";")[0].strip().lower()
        src_ext = data.rsplit(".", 1)[-1].split("?")[0].lower() if "." in data else ""

        # Detect format: source URL ext → response header → magic bytes
        real_ct = content_type
        is_webm = False

        # 1) Source URL extension (Replicate URLs often end in .webm)
        if src_ext == "webm" or "webm" in hdr_ct:
            is_webm = True
        # 2) Magic bytes: WebM/MKV (EBML header)
        elif len(body) >= 4 and body[:4] == b'\x1a\x45\xdf\xa3':
            is_webm = True
        # 3) Extended WebM detection: check for 'webm' doctype in first 64 bytes
        elif len(body) >= 64 and b'webm' in body[:64]:
            is_webm = True

        if is_webm:
            real_ct = "video/webm"
            key = key.rsplit(".", 1)[0] + ".webm"
        elif len(body) >= 8 and (body[4:8] == b'ftyp' or body[:4] in (b'\x00\x00\x00\x18', b'\x00\x00\x00\x1c', b'\x00\x00\x00\x20')):
            real_ct = "video/mp4"
        elif len(body) >= 3 and (body[:3] == b'ID3' or body[:2] == b'\xff\xfb' or body[:2] == b'\xff\xf3'):
            real_ct = "audio/mpeg"
        elif "mp4" in hdr_ct:
            real_ct = "video/mp4"
        elif "mpeg" in hdr_ct or "mp3" in hdr_ct:
            real_ct = "audio/mpeg"

        s3.put_object(Bucket=Config.R2_BUCKET, Key=key, Body=body, ContentType=real_ct)
        log.info(f"   R2 upload: {key} ({real_ct}, {len(body)//1024}KB) [src_ext={src_ext}, hdr={hdr_ct}]")
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
    ss_env = getattr(Config, 'SHOTSTACK_ENV', 'stage')
    ss_base = f"https://api.shotstack.io/{ss_env}"
    log.info(f"🎞️  Phase 9: Rendering final video via Shotstack ({ss_env}) | {Config.RENDER_RES}p {Config.RENDER_ASPECT} {Config.RENDER_FPS}fps")

    # Build video clips timeline
    video_clips = []
    cursor = 0.0
    for clip in clips:
        dur = Config.CLIP_DURATION
        video_clips.append({
            "asset": {"type": "video", "src": clip["r2_url"], "volume": 0, "transcode": True},
            "start": round(cursor, 3),
            "length": dur,
            "fit": "cover",
        })
        cursor += dur

    # CTA clip at end (static image held for CTA_DURATION)
    if getattr(Config, 'CTA_ENABLED', False) and getattr(Config, 'CTA_URL', ''):
        cta_dur = getattr(Config, 'CTA_DURATION', 4.0)
        video_clips.append({
            "asset": {"type": "image", "src": Config.CTA_URL},
            "start": round(cursor, 3),
            "length": cta_dur,
            "fit": "cover",
        })
        cursor += cta_dur
        log.info(f"   CTA clip: {cta_dur}s from {Config.CTA_URL}")

    total_dur = round(cursor, 3)

    tracks = []

    # Logo overlay (conditional)
    if Config.LOGO_ENABLED and Config.LOGO_URL:
        logo_url = Config.LOGO_URL
        # Re-upload logo to our working R2 bucket to guarantee Shotstack can access it
        try:
            log.info(f"   Fetching logo from {logo_url}...")
            lr = requests.get(logo_url, timeout=15)
            lr.raise_for_status()
            # Detect format from content-type or magic bytes
            ct = lr.headers.get("content-type", "image/png").split(";")[0].strip()
            body = lr.content
            ext = "png"
            if body[:4] == b'\x89PNG':
                ct = "image/png"; ext = "png"
            elif body[:2] == b'\xff\xd8':
                ct = "image/jpeg"; ext = "jpg"
            elif body[:4] == b'RIFF' and body[8:12] == b'WEBP':
                ct = "image/webp"; ext = "webp"
            s3 = get_s3_client()
            logo_key = f"_assets/logo.{ext}"
            s3.put_object(Bucket=Config.R2_BUCKET, Key=logo_key, Body=body, ContentType=ct)
            logo_url = f"{Config.R2_PUBLIC_URL}/{logo_key}"
            log.info(f"   Logo re-uploaded to {logo_url} ({ct}, {len(body)//1024}KB)")
        except Exception as e:
            log.warning(f"   Logo fetch/upload failed: {e}, skipping logo overlay")
            logo_url = None

        if logo_url:
            # Offset map for positions
            offsets = {
                "topRight": {"x": -0.03, "y": 0.03},
                "topLeft": {"x": 0.03, "y": 0.03},
                "bottomRight": {"x": -0.03, "y": -0.03},
                "bottomLeft": {"x": 0.03, "y": -0.03},
                "center": {"x": 0, "y": 0},
            }
            tracks.append({"clips": [{
                "asset": {"type": "image", "src": logo_url},
                "start": 0, "length": total_dur,
                "position": Config.LOGO_POSITION,
                "offset": offsets.get(Config.LOGO_POSITION, {"x": -0.03, "y": 0.03}),
                "scale": Config.LOGO_SCALE, "opacity": Config.LOGO_OPACITY,
            }]})

    # Video clips
    tracks.append({"clips": video_clips})

    # Audio
    tracks.append({"clips": [{
        "asset": {"type": "audio", "src": voiceover_url},
        "start": 0, "length": total_dur,
    }]})

    timeline = {
        "tracks": tracks,
        "background": Config.RENDER_BG,
    }

    payload = {
        "timeline": timeline,
        "output": {
            "format": "mp4",
            "resolution": Config.RENDER_RES,
            "aspectRatio": Config.RENDER_ASPECT,
            "fps": Config.RENDER_FPS,
        },
    }

    # Pre-flight: probe all asset URLs to catch format issues early
    all_asset_urls = []
    for track in tracks:
        for clip in track.get("clips", []):
            asset = clip.get("asset", {})
            src = asset.get("src", "")
            if src:
                all_asset_urls.append((asset.get("type", "?"), src))

    for atype, aurl in all_asset_urls:
        try:
            encoded_url = requests.utils.quote(aurl, safe='')
            probe_r = requests.get(f"{ss_base}/probe/{aurl}",
                                   headers={"x-api-key": Config.SHOTSTACK_KEY}, timeout=15)
            if probe_r.status_code == 200:
                probe_data = probe_r.json().get("response", {}).get("metadata", {})
                streams = probe_data.get("streams", [])
                fmt = probe_data.get("format", {}).get("format_name", "?")
                log.info(f"   Probe OK: {atype} — {fmt} — {aurl.split('/')[-1]}")
            else:
                log.warning(f"   Probe FAIL ({probe_r.status_code}): {atype} — {aurl}")
                log.warning(f"   Response: {probe_r.text[:300]}")
        except Exception as e:
            log.warning(f"   Probe error for {aurl}: {e}")

    r = requests.post(f"{ss_base}/render", headers={
        "x-api-key": Config.SHOTSTACK_KEY,
        "Content-Type": "application/json",
    }, json=payload, timeout=30)
    r.raise_for_status()
    job_id = r.json()["response"]["id"]
    log.info(f"   Render job: {job_id}")

    # Poll for completion
    for _ in range(60):
        time.sleep(15)
        r = requests.get(f"{ss_base}/render/{job_id}", headers={
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

def run_pipeline(progress_cb=None, resume_from: int = 0, topic_id: str = None) -> dict:
    """Execute the full pipeline with checkpoint/resume and approval gates.
    
    resume_from: Phase index to resume from (0 = start fresh).
    topic_id: Specific topic ID to use (None = next available).
    
    Gates:
      - After phase 2 (Scene Engine): pauses for prompt editing (gate="prompts")
      - After phase 4 (Generate Videos): pauses for video approval (gate="videos")
    
    Checkpoints saved after each phase to DATA_DIR/pipeline_checkpoint.json
    """
    CHECKPOINT_FILE = str(DATA_DIR / "pipeline_checkpoint.json")
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
        # ── Phase 0: Fetch topic ────────────────────────────────
        if resume_from <= 0:
            notify(0, "Fetch Topic", "running")
            topic = fetch_topic(topic_id)
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

        # ── Phase 1: Generate script ────────────────────────────
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

        # ── Phase 2: Scene engine ───────────────────────────────
        if resume_from <= 2:
            notify(2, "Scene Engine", "running")
            clips = scene_engine(script, topic) if resume_from < 2 else ckpt.get("clips") or scene_engine(script, topic)
            result["phases"].append({"name": "Scene Engine", "status": "done"})
            save_checkpoint(2, {"clips": clips})
            notify(2, "Scene Engine", "done")

            # ═══ GATE 1: Prompt Editing ═══
            # Pause pipeline so user can review/edit image & motion prompts
            result["status"] = "awaiting_prompt_approval"
            result["gate"] = "prompts"
            result["gate_phase"] = 3  # resume from here after approval
            result["clips"] = clips
            result["script"] = script
            log.info("⏸️  Gate 1: Awaiting prompt approval — edit prompts then resume")
            return result
        else:
            # Resuming past the prompt gate — check for edited clips
            clips = ckpt.get("clips_edited") or ckpt.get("clips")
            result["phases"].append({"name": "Scene Engine", "status": "done"})
            notify(2, "Scene Engine", "done")

        # ── Phase 3: Generate images ────────────────────────────
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

        # ── Phase 4: Generate videos ────────────────────────────
        if resume_from <= 4:
            notify(4, "Generate Videos", "running")
            clips = generate_videos(clips) if resume_from < 4 else (ckpt.get("clips_with_videos") or generate_videos(clips))
            result["phases"].append({"name": "Generate Videos", "status": "done"})
            result["videos"] = [{"index": c["index"], "url": c["video_url"]} for c in clips]
            save_checkpoint(4, {"clips_with_videos": clips})
            notify(4, "Generate Videos", "done")

            # ═══ GATE 2: Video Approval ═══
            # Pause pipeline so user can review videos, approve or regenerate clips
            result["status"] = "awaiting_video_approval"
            result["gate"] = "videos"
            result["gate_phase"] = 5  # resume from here after approval
            result["clips"] = clips
            result["images"] = [{"index": c["index"], "url": c["image_url"], "prompt": c.get("image_prompt","")} for c in clips]
            result["script"] = script
            log.info("⏸️  Gate 2: Awaiting video approval — review clips then resume")
            return result
        else:
            clips = ckpt.get("clips_approved") or ckpt.get("clips_with_videos")
            result["videos"] = [{"index": c["index"], "url": c["video_url"]} for c in clips]
            result["phases"].append({"name": "Generate Videos", "status": "done"})
            notify(4, "Generate Videos", "done")

        # ── Phase 5: Voiceover ──────────────────────────────────
        if resume_from <= 5:
            notify(5, "Voiceover", "running")
            audio = generate_voiceover(script)
            result["phases"].append({"name": "Voiceover", "status": "done"})
            result["voiceover_size"] = len(audio)
            save_checkpoint(5, {"audio_b64": base64.b64encode(audio).decode()})
            notify(5, "Voiceover", "done")
        else:
            audio = base64.b64decode(ckpt["audio_b64"])
            result["voiceover_size"] = len(audio)
            result["phases"].append({"name": "Voiceover", "status": "done"})
            notify(5, "Voiceover", "done")

        # ── Phase 6: Transcribe ─────────────────────────────────
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

        # ── Phase 7: Upload to R2 ──────────────────────────────
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

        # ── Phase 8: Final render ──────────────────────────────
        if resume_from <= 8:
            notify(8, "Final Render", "running")
            # Fix-up: ensure R2 clips have correct format/extension
            s3 = get_s3_client()
            for clip in clips:
                r2_url = clip.get("r2_url", "")
                if not r2_url or not r2_url.endswith(".mp4"):
                    continue
                try:
                    pr = requests.get(r2_url, timeout=15, headers={"Range": "bytes=0-63"})
                    if pr.status_code in (200, 206):
                        sample = pr.content[:64]
                    else:
                        sample = b''
                    ct = pr.headers.get("content-type", "").lower()
                    is_webm = (
                        (len(sample) >= 4 and sample[:4] == b'\x1a\x45\xdf\xa3') or
                        (len(sample) >= 64 and b'webm' in sample[:64]) or
                        "webm" in ct
                    )
                    log.info(f"   Format check {r2_url.split('/')[-1]}: ct={ct}, magic={sample[:4].hex() if sample else '?'}, webm={is_webm}")
                    if is_webm:
                        log.warning(f"   Fixing {r2_url} — WebM detected, renaming to .webm")
                        full = requests.get(r2_url, timeout=120)
                        old_key = r2_url.split(Config.R2_PUBLIC_URL + "/")[-1]
                        new_key = old_key.rsplit(".", 1)[0] + ".webm"
                        s3.put_object(Bucket=Config.R2_BUCKET, Key=new_key, Body=full.content, ContentType="video/webm")
                        clip["r2_url"] = f"{Config.R2_PUBLIC_URL}/{new_key}"
                        log.info(f"   Fixed: {clip['r2_url']}")
                except Exception as e:
                    log.warning(f"   Format check failed for {r2_url}: {e}")

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

        # ── Phase 9: Captions ──────────────────────────────────
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

        # ── Phase 10: Publish ───────────────────────────────────
        notify(10, "Publish", "running")
        publish_everywhere(final_r2_url, captions, topic)
        result["phases"].append({"name": "Publish", "status": "done"})
        notify(10, "Publish", "done")

        # Update topic status
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
        result["failed_phase"] = ckpt.get("_last_phase", 0) + 1 if ckpt.get("_last_phase") is not None else 0
        log.error(f"\n❌ Pipeline failed at phase {result['failed_phase']}: {e}")

        if "topic" in result:
            update_airtable(result["topic"]["airtable_id"], {
                "Status": "Failed",
                "Error": str(e),
            })

    return result


if __name__ == "__main__":
    run_pipeline()
