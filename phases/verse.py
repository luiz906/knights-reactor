"""
Knights Reactor — Verse of the Day
A separate content mode from the normal Topic -> GPT-script pipeline: no
hook/build/reveal/command narrative, no "battle" framing — the entire video
is just a straight reading of one Bible verse (King James Version, public
domain), picked from a curated pool of well-known references.

Verse TEXT is never hand-typed into this file (beyond a small emergency
fallback set) — it's always fetched live from bible-api.com so the wording
is authoritative and this module stays tiny. Only REFERENCES live here.
"""
import json, random, time
import requests

from config import Config, DATA_DIR, log

BRANDS_DIR = DATA_DIR / "brands"


def _verse_state_file(brand=None):
    """Per-brand file tracking which references have already been used, so
    Verse of the Day cycles through the whole pool before repeating — same
    idea as topics.py's "new"/"processing" status, just for a fixed list
    instead of a growing topic database."""
    if brand is None:
        ab_file = DATA_DIR / "active_brand.txt"
        brand = ab_file.read_text().strip() if ab_file.exists() else "knights"
    bd = BRANDS_DIR / brand
    bd.mkdir(exist_ok=True)
    return bd / "verse_state.json"


# Curated pool of well-known KJV references — picked for clarity when read
# aloud in roughly 5-20 seconds and for broad emotional range (comfort,
# strength, guidance, hope, faith, perseverance, love, praise). Add more any
# time; only the reference needs to be correct, the actual verse text is
# always pulled fresh from the API at generation time.
VERSE_REFS = [
    "John 3:16", "Psalm 23:1", "Philippians 4:13", "Romans 8:28", "Joshua 1:9",
    "Proverbs 3:5-6", "Isaiah 41:10", "Jeremiah 29:11", "Psalm 46:1", "Matthew 6:33",
    "Romans 12:2", "Philippians 4:6-7", "2 Timothy 1:7", "Psalm 27:1", "Isaiah 40:31",
    "Proverbs 16:3", "Psalm 119:105", "Ephesians 6:10", "Ephesians 6:11", "1 Corinthians 16:13",
    "Deuteronomy 31:6", "Psalm 34:18", "Matthew 11:28", "James 1:2-3", "Romans 8:31",
    "Galatians 5:22-23", "Psalm 91:1-2", "Proverbs 18:10", "Isaiah 54:17", "2 Corinthians 5:17",
    "Hebrews 11:1", "Psalm 37:4", "Matthew 5:14", "John 14:6", "John 14:27",
    "Romans 5:8", "1 Peter 5:7", "Psalm 121:1-2", "Nahum 1:7", "Proverbs 27:17",
    "2 Chronicles 7:14", "Isaiah 26:3", "Psalm 56:3", "Matthew 17:20", "Mark 9:23",
    "Romans 15:13", "Colossians 3:23", "1 John 4:18", "Psalm 139:14", "Zephaniah 3:17",
    "Habakkuk 3:19", "Psalm 18:2", "Proverbs 4:23", "Ecclesiastes 3:1", "Isaiah 43:2",
    "Lamentations 3:22-23", "Micah 6:8", "Nehemiah 8:10", "Psalm 32:8", "Psalm 55:22",
    "Matthew 28:19-20", "John 8:32", "John 15:5", "Acts 1:8", "Romans 10:9",
    "Romans 12:1", "1 Corinthians 10:13", "1 Corinthians 13:4-7", "2 Corinthians 12:9", "Galatians 2:20",
    "Ephesians 2:8-9", "Ephesians 4:32", "Philippians 1:6", "Philippians 2:3-4", "Philippians 4:8",
    "Colossians 3:2", "1 Thessalonians 5:16-18", "2 Timothy 4:7", "Hebrews 12:1", "Hebrews 13:5",
    "James 1:5", "James 4:7", "1 Peter 2:9", "1 Peter 4:8", "2 Peter 1:3",
    "1 John 1:9", "1 John 5:4", "Jude 1:24-25", "Revelation 21:4", "Genesis 1:1",
    "Exodus 14:14", "Numbers 6:24-26", "Deuteronomy 6:5", "Joshua 24:15", "1 Samuel 17:47",
    "Psalm 1:1-2", "Psalm 16:11", "Psalm 62:1-2", "Psalm 100:4-5", "Proverbs 31:25",
]

# Small emergency backup (public-domain KJV text, safe to embed verbatim) for
# when bible-api.com is unreachable — it's a free hobby project with no SLA,
# so this step must not hard-fail the whole pipeline just because that one
# server happens to be down. Only covers a subset of VERSE_REFS; if the
# picked reference isn't here and the API is down, the phase fails loudly
# (like any other phase) rather than fabricate or misquote scripture.
FALLBACK_VERSES = {
    "John 3:16": "For God so loved the world, that he gave his only begotten Son, that whosoever believeth in him should not perish, but have everlasting life.",
    "Psalm 23:1": "The LORD is my shepherd; I shall not want.",
    "Philippians 4:13": "I can do all things through Christ which strengtheneth me.",
    "Romans 8:28": "And we know that all things work together for good to them that love God, to them who are the called according to his purpose.",
    "Joshua 1:9": "Have not I commanded thee? Be strong and of a good courage; be not afraid, neither be thou dismayed: for the LORD thy God is with thee whithersoever thou goest.",
    "Proverbs 3:5-6": "Trust in the LORD with all thine heart; and lean not unto thine own understanding. In all thy ways acknowledge him, and he shall direct thy paths.",
    "Isaiah 41:10": "Fear thou not; for I am with thee: be not dismayed; for I am thy God: I will strengthen thee; yea, I will help thee; yea, I will uphold thee with the right hand of my righteousness.",
    "Jeremiah 29:11": "For I know the thoughts that I think toward you, saith the LORD, thoughts of peace, and not of evil, to give you an expected end.",
    "Psalm 46:1": "God is our refuge and strength, a very present help in trouble.",
    "Matthew 6:33": "But seek ye first the kingdom of God, and his righteousness; and all these things shall be added unto you.",
    "2 Timothy 1:7": "For God hath not given us the spirit of fear; but of power, and of love, and of a sound mind.",
    "Isaiah 40:31": "But they that wait upon the LORD shall renew their strength; they shall mount up with wings as eagles; they shall run, and not be weary; and they shall walk, and not faint.",
    "Psalm 27:1": "The LORD is my light and my salvation; whom shall I fear? the LORD is the strength of my life; of whom shall I be afraid?",
    "Deuteronomy 31:6": "Be strong and of a good courage, fear not, nor be afraid of them: for the LORD thy God, he it is that doth go with thee; he will not fail thee, nor forsake thee.",
    "1 Corinthians 16:13": "Watch ye, stand fast in the faith, quit you like men, be strong.",
    "Psalm 119:105": "Thy word is a lamp unto my feet, and a light unto my path.",
    "Matthew 11:28": "Come unto me, all ye that labour and are heavy laden, and I will give you rest.",
    "Psalm 121:1-2": "I will lift up mine eyes unto the hills, from whence cometh my help. My help cometh from the LORD, which made heaven and earth.",
    "Romans 8:31": "What shall we then say to these things? If God be for us, who can be against us?",
    "Hebrews 13:5": "Let your conversation be without covetousness; and be content with such things as ye have: for he hath said, I will never leave thee, nor forsake thee.",
}


def fetch_verse_text(reference: str) -> str:
    """Fetch KJV verse text for `reference` from bible-api.com (free,
    no-key, public-domain KJV). Retries briefly, then falls back to the
    small embedded set above — the API's own docs say it "can and will go
    down from time to time" with no uptime guarantee, so this can't be a
    hard dependency."""
    url = f"https://bible-api.com/{reference.replace(' ', '+')}"
    last_err = None
    for attempt in range(3):
        try:
            r = requests.get(url, params={"translation": "kjv"}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                text = (data.get("text") or "").strip()
                text = " ".join(text.split())  # collapse the API's embedded \n/padding
                if text:
                    return text
            last_err = f"HTTP {r.status_code}"
        except Exception as e:
            last_err = str(e)
        if attempt < 2:
            log.warning(f"   Verse API attempt {attempt+1}/3 failed ({last_err}), retrying...")
            time.sleep(2)

    if reference in FALLBACK_VERSES:
        log.warning(f"   Verse API unreachable ({last_err}) — using embedded fallback text for {reference}")
        return FALLBACK_VERSES[reference]
    raise RuntimeError(
        f"Could not fetch verse text for '{reference}' — bible-api.com unreachable "
        f"({last_err}) and no embedded fallback exists for this specific reference"
    )


def _load_state(brand=None):
    f = _verse_state_file(brand)
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    return {"used": []}


def _save_state(state, brand=None):
    _verse_state_file(brand).write_text(json.dumps(state, indent=2))


def pick_next_reference(brand=None) -> str:
    """Cycle through VERSE_REFS without repeating until the whole pool has
    been used once, then reset and start over — so 100 consecutive runs
    give 100 different verses before anything repeats."""
    state = _load_state(brand)
    used = set(state.get("used", []))
    remaining = [r for r in VERSE_REFS if r not in used]
    if not remaining:
        used = set()
        remaining = list(VERSE_REFS)
    ref = random.choice(remaining)
    used.add(ref)
    state["used"] = list(used)
    _save_state(state, brand)
    return ref


def build_verse_topic(brand=None) -> dict:
    """Build a topic-shaped dict for Verse of the Day mode. Shaped just like
    a normal phases.topics topic (id/idea/category/scripture) so nothing
    downstream (Scene Engine, captions, Airtable-replacement topic status)
    needs to know this didn't come from the topic database — plus a
    verse_text field the script step reads directly instead of re-fetching."""
    reference = pick_next_reference(brand)
    log.info(f"📖 Verse of the Day: {reference}")
    verse_text = fetch_verse_text(reference)
    return {
        "id": f"verse_{int(time.time()*1000)}",
        "idea": f"Verse of the Day: {reference}",
        "category": "Verse of the Day",
        "scripture": reference,
        "verse_text": verse_text,
        "status": "processing",
    }


def build_verse_script(topic: dict) -> dict:
    """Build the 'script' straight from the verse text — no GPT call, no
    hook/build/reveal/command story structure. The whole script IS the
    verse, read as-is. Shaped like a normal script.py output (same keys)
    so Scene Engine / voiceover / captions consume it identically."""
    reference = topic.get("scripture", "")
    verse_text = topic.get("verse_text") or fetch_verse_text(reference)
    script_full = f"{reference}. {verse_text}" if reference else verse_text
    return {
        "hook": reference,
        "build": "",
        "reveal": verse_text,
        "command": "",
        "script_full": script_full,
        "tone": "reverent|calm|still",
        "scripture": reference,
    }
