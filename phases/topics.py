"""
Knights Reactor — Topic Database
Local JSON-based topic storage with AI generation.
"""
import json, time, random, re
from datetime import datetime

import requests

from config import Config, DATA_DIR, log

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



def fetch_topic(topic_id=None):
    """Get next new topic from local DB."""
    return fetch_next_topic(topic_id)

def update_topic(record_id, fields):
    """Update topic status in local DB."""
    status = fields.get("Status", "").lower()
    if status:
        update_topic_status(record_id, status, fields)
