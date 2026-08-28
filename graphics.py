"""
Knights Reactor — Graphics Engine v2
======================================
Multi-brand image content pipeline with FULL UI control.
Each phase is visible and editable before proceeding.

Flow: Brand → Topic (edit) → Quote (edit) → Prompt (edit) → Image (preview) → Captions (edit) → Publish

Mounted at /graphics as a FastAPI sub-application.
"""

import json, os, time, uuid, threading, re, logging, shutil
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

import requests
import boto3

from config import Config, DATA_DIR, log

glog = logging.getLogger("graphics")
router = APIRouter(prefix="/graphics", tags=["graphics"])

# ─── STORAGE ──────────────────────────────────────────────────
# Graphics Engine keeps its own, completely separate brand directory — NOT the
# Pipeline's `brands/` folder. Pipeline and Graphics Engine are two independent
# halves of one deployment: each brand belongs to exactly one of them, and
# nothing (brand list, active selection, topics, settings) is shared between
# the two anymore. This is what stops the kind of cross-tool bugs (wrong
# brand's topics/state showing up) seen when they shared state before.
BRANDS_DIR = DATA_DIR / "graphics_brands"
BRANDS_DIR.mkdir(exist_ok=True)
GFX_GALLERY_FILE = DATA_DIR / "graphics_gallery.json"

def load_json(path, default=None):
    if path.exists():
        try: return json.loads(path.read_text())
        except: pass
    return default if default is not None else {}

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))

def get_brands() -> list:
    brands = []
    if not BRANDS_DIR.exists(): return brands
    for d in sorted(BRANDS_DIR.iterdir()):
        if d.is_dir():
            s = load_json(d / "settings.json", {})
            brands.append({
                "id": d.name,
                "name": s.get("brand_name", d.name.replace("_", " ").title()),
                "tone": s.get("brand_voice", ""),
                "visual_style": s.get("scene_style", ""),
                "logo_url": s.get("logo_url", ""),
                "guidelines": s.get("brand_persona", ""),
                "themes": s.get("brand_themes", ""),
                "image_prompt_template": s.get("image_prompt_template", ""),
                "prompt_sections": s.get("prompt_sections", {}),
                "blotato": {
                    "instagram": s.get("blotato_instagram_id", os.environ.get("BLOTATO_INSTAGRAM_ID", "")),
                    "facebook": s.get("blotato_facebook_id", os.environ.get("BLOTATO_FACEBOOK_ID", "")),
                    "facebook_page": s.get("blotato_facebook_page_id", os.environ.get("BLOTATO_FACEBOOK_PAGE_ID", "")),
                    "twitter": s.get("blotato_twitter_id", os.environ.get("BLOTATO_TWITTER_ID", "")),
                    "threads": s.get("blotato_threads_id", os.environ.get("BLOTATO_THREADS_ID", "")),
                    "pinterest": s.get("blotato_pinterest_id", os.environ.get("BLOTATO_PINTEREST_ID", "")),
                    "pinterest_board": s.get("blotato_pinterest_board_id", os.environ.get("BLOTATO_PINTEREST_BOARD_ID", "")),
                    "tiktok": s.get("blotato_tiktok_id", os.environ.get("BLOTATO_TIKTOK_ID", "")),
                    "youtube": s.get("blotato_youtube_id", os.environ.get("BLOTATO_YOUTUBE_ID", "")),
                },
            })
    return brands

# ─── HELPERS ──────────────────────────────────────────────────
def _rep_create(model, inp):
    for attempt in range(5):
        r = requests.post(f"https://api.replicate.com/v1/models/{model}/predictions",
            headers={"Authorization": f"Bearer {Config.REPLICATE_TOKEN}", "Content-Type": "application/json"},
            json={"input": inp}, timeout=30)
        if r.status_code == 429:
            time.sleep(min(30 * (attempt + 1), 120)); continue
        r.raise_for_status()
        return r.json()["urls"]["get"]
    raise Exception("Replicate rate limit exhausted")

def _rep_poll(url, timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(url, headers={"Authorization": f"Bearer {Config.REPLICATE_TOKEN}"})
        r.raise_for_status(); data = r.json()
        if data["status"] == "succeeded":
            out = data.get("output")
            return out[0] if isinstance(out, list) else out
        if data["status"] == "failed":
            raise RuntimeError(f"Replicate failed: {data.get('error')}")
        time.sleep(8)
    raise TimeoutError("Replicate timed out")

def _r2_upload(key, data, ct):
    s3 = boto3.client("s3", endpoint_url=Config.R2_ENDPOINT,
        aws_access_key_id=Config.R2_ACCESS_KEY, aws_secret_access_key=Config.R2_SECRET_KEY, region_name="auto")
    s3.put_object(Bucket=Config.R2_BUCKET, Key=key, Body=data, ContentType=ct)
    return f"{Config.R2_PUBLIC_URL}/{key}"

def _gpt(prompt, temp=0.9, max_tok=200):
    r = requests.post("https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {Config.OPENAI_KEY}", "Content-Type": "application/json"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": prompt}],
              "temperature": temp, "max_tokens": max_tok}, timeout=25)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip().strip('"')


# ─── GRAPHICS SCENE ENGINE (ported from n8n JS v10) ──────────
import random as _rng

def _pick(arr): return _rng.choice(arr)
def _pickN(arr, n):
    copy = list(arr); out = []
    while copy and len(out) < n:
        out.append(copy.pop(_rng.randint(0, len(copy)-1)))
    return out
def _pick_weighted(items, weights):
    total = sum(weights); r = _rng.random() * total
    for i, w in enumerate(weights):
        r -= w
        if r <= 0: return items[i]
    return items[-1]
def _join(*parts): return " ".join(p for p in parts if p).strip()

# ── MOOD POOLS ──
_MOODS = [
    {"key": "NATURAL_DAY", "w": 35},
    {"key": "WARM_INTERIOR", "w": 30},
    {"key": "NIGHT_COLOR", "w": 20},
    {"key": "MIXED_LIGHT", "w": 15},
]

_MOOD_POOLS = {
    "NATURAL_DAY": {
        "lighting": [
            "natural daylight with clean contrast and readable midtones",
            "open shade daylight with gentle direction and natural falloff",
            "late afternoon daylight with soft side-shadows (not moody, just real)",
            "bright but neutral daylight with accurate white balance",
        ],
        "color": [
            "natural chroma and honest color: concrete shows beige/olive/blue undertones, paint has real pigment, metal reflects ambient color, skin tones stay believable",
            "neutral documentary color with accurate white balance and natural contrast (no stylized grading, no grey wash)",
            "true-to-life color and exposure: avoid desaturated filters and muddy mid-greys",
        ],
        "exposure": "exposure is normal and balanced: no underexposure, no crushed blacks, no grey haze filter",
    },
    "WARM_INTERIOR": {
        "lighting": [
            "fluorescent interior light with real-world color temperature variation (no green cast exaggeration)",
            "mixed indoor lighting with natural falloff and practical highlights",
            "storefront spill light that feels real and readable, not cinematic",
        ],
        "color": [
            "natural indoor color: whites stay neutral, warm tones stay believable, no muddy grey overlay",
            "documentary indoor color with accurate white balance and clean midtones",
            "preserve natural colors in signage/glass/skin—no bland filter",
        ],
        "exposure": "clean midtones and readable shadows: avoid dark, avoid wet/grey look",
    },
    "NIGHT_COLOR": {
        "lighting": [
            "night lighting with readable exposure and clean midtones (not underexposed)",
            "streetlight + storefront spill with balanced exposure so the carrier reads clearly",
            "neon/signage glow with realistic spill and controlled bloom, text stays crisp",
        ],
        "color": [
            "natural night color (not monochrome): retain real reds/ambers/greens from street and signage without overgrading",
            "night documentary color with clean highlights and uncrushed shadows",
            "no teal/orange grade—keep it real",
        ],
        "exposure": "night exposure is lifted enough to avoid a dark, moody look; text plane is properly lit",
    },
    "MIXED_LIGHT": {
        "lighting": [
            "mixed practical lighting with believable white balance tension (fluorescent + signage), still clean",
            "two-source lighting (cool overhead + warm spill) with normal exposure and readable midtones",
            "dynamic light transitions (passing headlights, signage flicker) without dark underexposure",
        ],
        "color": [
            "natural mixed-light color with real chroma—avoid grey wash and avoid heavy desaturation",
            "documentary color with clean midtones and true whites",
            "natural contrast and pigment—no bland filter",
        ],
        "exposure": "balanced exposure; avoid underexposed corners and muddy mid-grey haze",
    },
}

_CENTER_SAFE = [
    "Text sits centered in the frame safe area for cropping safety.",
    "Leave visible surface border around the text on all sides (at least 12-15% padding).",
    "Keep the full message fully in-frame. No edge cropping. No cutoff letters.",
    "Camera is level and vertically true. No Dutch angle. Architectural lines stay straight.",
]
_HIERARCHY = [
    "The text plane is the sharpest point in the image. Background falls off naturally.",
    "Strong contrast between text and its surface. No shadows, glare, or reflections obscuring letters.",
    "No competing focal points stronger than the text.",
]
_CLEANLINESS = "Underground culture energy, but not dirty or fetishized grime. Real wear is fine: scuffs, dust, fingerprints, sun fade—nothing gross."
_ANTI_MOCKUP = [
    "No poster mockup look. No studio lighting. No centered product-shot vibe.",
    "Observed candid framing, real depth layers, real environment.",
    "Avoid overly perfect typography and overly perfect surfaces.",
]

_TYPO_STYLES = [
    "plain sans-serif lettering, clear and commercial, like a real-world sign shop would produce",
    "bold condensed sans-serif, clean and readable at distance, uniform stroke weight",
    "simple grotesque sans-serif, neutral tone, no personality tricks",
    "utilitarian sans-serif, evenly spaced, legible first, style second",
]

_SCENES = [
    {"id": "S01", "desc": "city sidewalk in daylight near small storefronts, real street colors, clean concrete and glass", "tags": ["day","street","urban"]},
    {"id": "S02", "desc": "parking lot edge in daylight with sunlit cars, natural color, no rain, no fog", "tags": ["day","street","commercial"]},
    {"id": "S03", "desc": "industrial corridor in daylight with painted walls and metal doors, honest color", "tags": ["day","industrial"]},
    {"id": "S04", "desc": "underpass in daylight with directional side light, normal exposure, not moody", "tags": ["day","infrastructure"]},
    {"id": "S05", "desc": "convenience store entrance with fluorescent interior and colored signage glow outside", "tags": ["interior","mixed","commercial"]},
    {"id": "S06", "desc": "late-night diner threshold with mixed fluorescent and window reflections (balanced exposure)", "tags": ["interior","mixed","night"]},
    {"id": "S07", "desc": "bus interior with practical lighting and reflections, normal exposure, natural colors", "tags": ["interior","transit","mixed"]},
    {"id": "S08", "desc": "street corner at night with storefront signage providing real color and readable exposure", "tags": ["night","street","urban"]},
    {"id": "S09", "desc": "parking garage entrance at night with practical lights and readable midtones", "tags": ["night","industrial"]},
]

_MOOD_SCENE_PREF = {
    "NATURAL_DAY": ["day"],
    "WARM_INTERIOR": ["interior","mixed"],
    "NIGHT_COLOR": ["night"],
    "MIXED_LIGHT": ["mixed","interior","night"],
}

_CARRIERS = [
    {"carrier": "white vinyl cut lettering on the back window of a parked car", "cat": "vehicle"},
    {"carrier": "a message on a car window written with paint marker (imperfect stroke edges)", "cat": "vehicle"},
    {"carrier": "vinyl lettering on the back door of a box truck", "cat": "vehicle"},
    {"carrier": "a cardboard sign casually held in a crowd", "cat": "human"},
    {"carrier": "text printed across the back of a hoodie worn in public", "cat": "human"},
    {"carrier": "a wheat-pasted poster on a clean wall (slight wrinkles, no tears)", "cat": "poster"},
    {"carrier": "a photocopied flyer taped to glass (edges lifting slightly)", "cat": "poster"},
    {"carrier": "an LED transit destination board", "cat": "led"},
    {"carrier": "a dot-matrix electronic road sign (temporary message board)", "cat": "led"},
    {"carrier": "a bulb-lit marquee sign (real bulbs, real glare control)", "cat": "light"},
    {"carrier": "a neon tube sign photographed as a real object", "cat": "light"},
    {"carrier": "a projected phrase cast onto a wall (real keystone and spill, readable)", "cat": "projection"},
    {"carrier": "a sprayed stencil on concrete with visible overspray and speckling", "cat": "marking"},
    {"carrier": "chalk lettering on pavement (slight smudge from foot traffic)", "cat": "marking"},
]

_BEHAVIORS = {
    "vehicle": [
        "reflections slide across glass or paint near the lettering, but do not obscure characters",
        "small scuffs and real-world dust exist around the surface, not over the text",
        "natural ambient color reflections appear in the glass/paint",
    ],
    "human": [
        "real crowd context with unstaged posture; depth blur isolates the text plane",
        "fabric drape or hand grip creates slight warping consistent with reality",
        "no posing; candid street moment",
    ],
    "poster": [
        "paper wrinkles create micro-shadows; surface stays clean",
        "tape edges or paste bubbles add realism without grime",
        "raking light reveals paper texture",
    ],
    "led": [
        "visible pixel grid with slight brightness variance; characters remain crisp",
        "controlled bloom around bright pixels; no blown-out unreadable highlights",
        "realistic refresh/flicker implied subtly",
    ],
    "light": [
        "realistic glow bloom and subtle spill onto nearby surfaces",
        "controlled glare; readable letters",
        "minor lens flare possible but never covers text",
    ],
    "projection": [
        "keystone distortion and feathered edges from light spill; still fully readable",
        "projection falloff across texture is visible but not destructive to legibility",
        "faint dust/haze catches the beam lightly",
    ],
    "marking": [
        "surface pores and micro-cracks interact with paint/chalk",
        "overspray halo and speckling visible at edges if stencil",
        "minor drip marks allowed, but letters remain readable",
    ],
}

_LIFE_MOMENTS = [
    "a skateboard or bike passes through the lower corner as a soft streak",
    "a passerby crosses far background in motion blur",
    "headlights sweep across the ground nearby, changing reflections",
    "a quick hand movement slightly shifts the cardboard sign angle",
    "a door opens behind the scene, changing interior spill light briefly",
]

_CAMERA_RULES = [
    "neutral 35-50mm perspective with gentle compression",
    "level camera, no tilt; architectural lines remain straight",
    "handheld candid feel without crooked horizons",
    "depth layering: soft foreground element, crisp text plane, softer background",
]


def build_graphics_prompt(quote_text: str, brand: dict = None) -> str:
    """Build a full photorealistic lettering prompt from quote + brand.
    If this brand has its own custom Image Prompt template saved, that
    template is used verbatim (with {TEXT} swapped for the quote) instead of
    the shared randomized photorealistic-lettering engine below — each brand
    can fully own its visual style, not just tweak the generic one."""
    TEXT = quote_text
    template = (brand or {}).get("image_prompt_template", "").strip()
    if template:
        if "{TEXT}" in template:
            return template.replace("{TEXT}", TEXT)
        # No placeholder in the template — still make sure the exact text
        # requirement is present so lettering generation doesn't silently omit it.
        return _join(template, f"The exact text displayed must be: {TEXT}.")

    guidelines = (brand or {}).get("guidelines", "")
    if guidelines:
        brand_visual = f"Brand art direction: align with these guidelines — {str(guidelines)[:600]}. Translate voice into photography choices (composition, light, restraint)."
    else:
        brand_visual = "Overall mood: intentional, editorial, human. Not trendy. Not mockup."

    # Per-section overrides: a brand can pin any one piece of the prompt (the
    # environment, the mood/lighting, the surface the text sits on, the
    # typography, the camera feel, or the small real-life detail) while
    # leaving the rest randomized for variety. Ignored if a full raw template
    # is set above (that already returned before reaching here).
    sections = (brand or {}).get("prompt_sections") or {}
    custom_scene = (sections.get("scene") or "").strip()
    custom_mood = (sections.get("mood") or "").strip()
    custom_carrier = (sections.get("carrier") or "").strip()
    custom_typography = (sections.get("typography") or "").strip()
    custom_camera = (sections.get("camera") or "").strip()
    custom_moment = (sections.get("life_moment") or "").strip()

    mood_key = _pick_weighted([m["key"] for m in _MOODS], [m["w"] for m in _MOODS])
    if custom_mood:
        mood_line = custom_mood.rstrip(".") + "."
    else:
        mood = _MOOD_POOLS[mood_key]
        mood_line = _join(mood["exposure"] + ".", _pick(mood["color"]) + ".", f"Lighting: {_pick(mood['lighting'])}.")

    if custom_scene:
        scene_line = f"Scene: {custom_scene}."
    else:
        pref_tags = _MOOD_SCENE_PREF.get(mood_key, ["day"])
        compatible = [s for s in _SCENES if any(t in pref_tags for t in s["tags"])]
        scene = _pick(compatible) if compatible else _pick(_SCENES)
        scene_line = f"Scene: {scene['desc']}."

    if custom_carrier:
        carrier_line = f"The phrase appears on {custom_carrier}."
        behavior_line = ""
    else:
        carrier_def = _pick(_CARRIERS)
        cat = carrier_def["cat"]
        behaviors = _pickN(_BEHAVIORS.get(cat, []), 2)
        carrier_line = f"The phrase appears on {carrier_def['carrier']}."
        behavior_line = ". ".join(behaviors) + "." if behaviors else ""

    typography_line = f"Typography: {custom_typography}." if custom_typography else f"Typography: {_pick(_TYPO_STYLES)}."
    camera_line = f"Lens/feel: {custom_camera}." if custom_camera else f"Lens/feel: {_pick(_CAMERA_RULES)}."
    moment_line = f"Include a subtle real-life moment: {custom_moment}." if custom_moment else f"Include a subtle real-life moment: {_pick(_LIFE_MOMENTS)}."

    prompt = _join(
        "Photorealistic candid vertical photograph.",
        f"The exact text displayed must be: {TEXT}.",
        "Do not include quotation marks in the rendered text.",
        _pick(_CENTER_SAFE), _pick(_CENTER_SAFE),
        "Keep the text centered in the frame safe area. Leave visible border around it on all sides.",
        typography_line, _pick(_HIERARCHY), _pick(_HIERARCHY),
        mood_line,
        scene_line,
        carrier_line,
        behavior_line,
        camera_line, moment_line,
        _CLEANLINESS, brand_visual, _pick(_ANTI_MOCKUP), _pick(_ANTI_MOCKUP),
    )
    return prompt


# ─── INDIVIDUAL PHASE ENDPOINTS ──────────────────────────────

@router.get("/api/brands")
async def api_brands():
    return get_brands()

@router.post("/api/brands")
async def api_create_brand(req: Request):
    """Create a new Graphics Engine brand. This is Graphics Engine's own
    registry (graphics_brands/) — entirely separate from the Pipeline's
    brand list. Each brand lives in exactly one tool, never both."""
    body = await req.json()
    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "Brand name required"}, 400)
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "brand"
    brand_id = slug
    n = 2
    while (BRANDS_DIR / brand_id).exists():
        brand_id = f"{slug}_{n}"
        n += 1
    bd = BRANDS_DIR / brand_id
    bd.mkdir(parents=True, exist_ok=True)
    save_json(bd / "settings.json", {"brand_name": name})
    save_json(bd / "topics.json", [])
    return {"status": "created", "id": brand_id, "name": name}

@router.delete("/api/brands/{brand_id}")
async def api_delete_brand(brand_id: str):
    """Permanently delete a Graphics Engine brand — settings, topics, and any
    custom prompt template. Only touches graphics_brands/; the Pipeline's own
    brands are untouched. No undo — the client requires typing the brand's
    exact name before calling this."""
    bd = BRANDS_DIR / brand_id
    if not bd.exists() or not bd.is_dir():
        return JSONResponse({"error": "Brand not found"}, 404)
    shutil.rmtree(bd)
    return {"status": "deleted"}

@router.post("/api/brand-guidelines/{brand_id}")
async def api_save_brand_guidelines(brand_id: str, req: Request):
    """Save this brand's Voice & Guidelines. This is the field that actually
    drives tone across the whole flow: it's fed into AI topic generation, the
    quote-writing prompt ("brand voice and positioning"), and the image
    prompt's art-direction line — so it's the one setting that answers
    'how do I make the graphics sound/feel like THIS brand'."""
    body = await req.json()
    guidelines = body.get("guidelines", "")
    bd = BRANDS_DIR / brand_id
    bd.mkdir(exist_ok=True)
    sf = bd / "settings.json"
    settings = load_json(sf, {})
    settings["brand_persona"] = guidelines
    save_json(sf, settings)
    return {"status": "saved"}

@router.post("/api/brand-prompt-sections/{brand_id}")
async def api_save_prompt_sections(brand_id: str, req: Request):
    """Save this brand's per-section Image Prompt overrides (scene, mood,
    carrier, typography, camera, life_moment). Any section left blank stays
    randomized by the shared engine for variety; a filled section is pinned
    for this brand on every future prompt. Ignored entirely if this brand
    also has a full raw template set (that takes priority)."""
    body = await req.json()
    sections = body.get("sections", {})
    if not isinstance(sections, dict):
        return JSONResponse({"error": "sections must be an object"}, 400)
    allowed = {"scene", "mood", "carrier", "typography", "camera", "life_moment"}
    clean = {k: str(v) for k, v in sections.items() if k in allowed}
    bd = BRANDS_DIR / brand_id
    bd.mkdir(exist_ok=True)
    sf = bd / "settings.json"
    settings = load_json(sf, {})
    settings["prompt_sections"] = clean
    save_json(sf, settings)
    return {"status": "saved", "sections": clean}

@router.post("/api/brand-prompt-template/{brand_id}")
async def api_save_prompt_template(brand_id: str, req: Request):
    """Save this brand's custom Image Prompt template. When set (non-empty),
    it replaces the shared randomized photorealistic-lettering engine for this
    brand's Image Prompt step entirely — {TEXT} in the template is swapped for
    the quote at generation time. An empty template falls back to the shared
    generic engine, same as before this existed."""
    body = await req.json()
    template = body.get("template", "")
    bd = BRANDS_DIR / brand_id
    bd.mkdir(exist_ok=True)
    sf = bd / "settings.json"
    settings = load_json(sf, {})
    settings["image_prompt_template"] = template
    save_json(sf, settings)
    return {"status": "saved", "template": template}

@router.get("/api/topics/{brand_id}")
async def api_get_topics(brand_id: str):
    bd = BRANDS_DIR / brand_id
    tf = bd / "topics.json"
    if not tf.exists():
        return {"topics": [], "total": 0, "new": 0}
    try:
        topics = json.loads(tf.read_text())
    except:
        topics = []
    return {"topics": topics, "total": len(topics), "new": sum(1 for t in topics if t.get("status") == "new")}

@router.delete("/api/topics/{brand_id}/{topic_id}")
async def api_delete_topic(brand_id: str, topic_id: str):
    """Delete one topic for a Graphics Engine brand. This is Graphics Engine's
    own topics.json (under graphics_brands/), entirely separate from the
    Pipeline's topics — deleting here has no effect on any Pipeline brand."""
    bd = BRANDS_DIR / brand_id
    tf = bd / "topics.json"
    topics = []
    if tf.exists():
        try: topics = json.loads(tf.read_text())
        except: pass
    remaining = [t for t in topics if t.get("id") != topic_id]
    found = len(remaining) != len(topics)
    tf.write_text(json.dumps(remaining, indent=2))
    return {"status": "deleted" if found else "not_found"}

@router.post("/api/topics/{brand_id}")
async def api_add_topic(brand_id: str, req: Request):
    """Save a topic into this Graphics Engine brand's OWN topics.json (under
    graphics_brands/). Needed since the directory split — Graphics Engine no
    longer inherits topics from the Pipeline's shared file, so this is the
    only way new topics land in a brand's Topics DB now (manual entry, or
    Random/AI Generate + this Save button)."""
    body = await req.json()
    idea = (body.get("idea") or "").strip()
    if not idea:
        return JSONResponse({"error": "Topic text required"}, 400)
    category = (body.get("category") or "").strip()
    bd = BRANDS_DIR / brand_id
    bd.mkdir(parents=True, exist_ok=True)
    tf = bd / "topics.json"
    topics = []
    if tf.exists():
        try: topics = json.loads(tf.read_text())
        except: pass
    new_topic = {"id": uuid.uuid4().hex[:12], "idea": idea, "category": category, "status": "new"}
    topics.append(new_topic)
    tf.write_text(json.dumps(topics, indent=2))
    return {"status": "saved", "topic": new_topic}

@router.post("/api/phase/topic")
async def api_phase_topic(req: Request):
    body = await req.json()
    brand_id = body.get("brand_id", "")
    mode = body.get("mode", "random")
    brand = next((b for b in get_brands() if b["id"] == brand_id), None)
    if not brand: return JSONResponse({"error": "Brand not found"}, 400)

    if mode == "random":
        bd = BRANDS_DIR / brand_id
        tf = bd / "topics.json"
        topics = []
        if tf.exists():
            try: topics = json.loads(tf.read_text())
            except: pass
        new_topics = [t for t in topics if t.get("status") == "new"]
        if not new_topics:
            return JSONResponse({"error": "No new topics — add topics on the Topics page first"}, 400)
        pick = _rng.choice(new_topics)
        return {"topic": pick["idea"], "topic_id": pick.get("id", ""), "category": pick.get("category", ""), "scripture": pick.get("scripture", "")}

    try:
        topic = _gpt(
            f"Generate ONE viral image post topic for '{brand['name']}'. "
            f"Brand: {brand.get('guidelines','')}. Themes: {brand.get('themes','')}. "
            "Return ONLY the topic as a short phrase (5-12 words).", max_tok=80)
        return {"topic": topic}
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)

@router.post("/api/phase/quote")
async def api_phase_quote(req: Request):
    body = await req.json()
    brand = next((b for b in get_brands() if b["id"] == body.get("brand_id")), {})
    topic = body.get("topic", "")
    guidelines = brand.get("guidelines", "")
    try:
        quote = _gpt(
            f"You are a senior brand designer and creative director. You design for real businesses, not creators. "
            f"You speak plainly, confidently, and without hype.\n\n"
            f"SOURCE TITLE (raw idea, not final copy):\n\"{topic}\"\n\n"
            f"TASK:\nCreate NEW graphic copy derived from the title. KEEP VERY SIMPLE and common language lamen terms.\n\n"
            f"This is not a rewrite the brand voice from:\n\n{guidelines}\n\n"
            f"RULES:\n- 1 line only\n- Max 12 words\n- Editorial, blunt, calm confidence\n"
            f"- Observational, not advice\n- Uncomfortable truth is acceptable\n"
            f"- Designed to live ON a physical sign\n- Non apologetic.\n\n"
            f"LANGUAGE RULES:\n- No emojis\n- No hashtags\n- No questions\n- No calls to action\n"
            f"- No advice\n- No motivational language\n- No \"you should\"\n- No hype or buzzwords\n- No sales tone\n\n"
            f"FINAL OUTPUT RULE:\nReturn ONLY the final line of text.\nNothing else. No period at the end.",
            max_tok=60)
        return {"quote": quote}
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)

@router.post("/api/phase/prompt")
async def api_phase_prompt(req: Request):
    body = await req.json()
    brand = next((b for b in get_brands() if b["id"] == body.get("brand_id")), {})
    quote = body.get("quote", "")
    if not quote:
        return JSONResponse({"error": "Quote text is required"}, 400)
    try:
        prompt = build_graphics_prompt(quote, brand)
        return {"prompt": prompt, "meta": prompt.get("_meta", {}) if isinstance(prompt, dict) else {}}
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)

@router.post("/api/phase/image")
async def api_phase_image(req: Request):
    body = await req.json()
    prompt = body.get("prompt", "")
    model = body.get("model", Config.IMAGE_MODEL)
    aspect = body.get("aspect", "1:1")
    job_id = str(uuid.uuid4())[:8]
    JOBS[job_id] = {"status": "running", "phase": "generating"}

    def worker():
        try:
            params = {"prompt": prompt, "aspect_ratio": aspect}
            if "flux" in model.lower(): params["quality"] = "high"
            url = _rep_create(model, params)
            JOBS[job_id]["phase"] = "polling"
            image_url = _rep_poll(url, timeout=180)
            r = requests.get(image_url, timeout=60); r.raise_for_status()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            brand_id = body.get("brand_id", "unknown")
            key = f"graphics/{brand_id}/{ts}_{job_id}.png"
            r2_url = _r2_upload(key, r.content, "image/png")
            JOBS[job_id].update({"status": "done", "image_url": image_url, "r2_url": r2_url})
        except Exception as e:
            JOBS[job_id].update({"status": "failed", "error": str(e)})

    threading.Thread(target=worker, daemon=True).start()
    return {"job_id": job_id}

JOBS = {}

@router.get("/api/phase/image/{job_id}")
async def api_poll_image(job_id: str):
    return JOBS.get(job_id, {"status": "unknown"})

@router.post("/api/phase/captions")
async def api_phase_captions(req: Request):
    body = await req.json()
    brand = next((b for b in get_brands() if b["id"] == body.get("brand_id")), {})
    quote = body.get("quote", "")
    guidelines = brand.get("guidelines", "")
    try:
        text = _gpt(
            f"You are an experienced brand designer and strategist. Write like a senior graphic designer "
            f"who understands business, positioning, and visual systems. Use simple, confident language.\n\n"
            f"Write a high-impact social media caption for this quote: {quote}\n\n"
            f"Use the brand voice and positioning defined here: {guidelines}\n\n"
            f"Structure the caption with the following flow, but do not label sections:\n\n"
            f"Start with a bold, polarizing hook that challenges a common belief or exposes a hard truth.\n"
            f"Follow with one short rehook line that builds tension or curiosity.\n"
            f"Develop the main body:\n- Write with natural rhythm and pacing.\n- Vary sentence length.\n"
            f"- Treat each line as if it could stand alone.\n- No bold formatting.\n- No filler language.\n"
            f"- No buzzwords.\n- Use short vertical spacing.\n- Keep tone human, strategic, and confident.\n"
            f"- Add exactly 2 emojis placed naturally for emphasis or pause.\n\n"
            f"After the body, end with one strong, definitive statement that feels like an undeniable truth.\n"
            f"Finish with a short reflective question that invites engagement.\n\n"
            f"Add exactly 3 hashtags at the end:\n- 1 topic specific hashtag\n- 1 target audience hashtag\n- 1 general hashtag\n\n"
            f"Do not include any section titles or formatting instructions.\n"
            f"Output only the caption text.\n\n"
            f"Now return this as JSON with platform keys. Adapt length per platform:\n"
            f"{{\"instagram\":\"full caption with hashtags\","
            f"\"facebook\":\"shorter, conversational, 3-5 hashtags\","
            f"\"tiktok\":\"200 chars max, 3-5 hashtags\","
            f"\"twitter\":\"280 chars max, no hashtags, single viral tweet\","
            f"\"threads\":\"conversational, 400 chars\"}}\n"
            f"Return ONLY valid JSON.",
            temp=0.8, max_tok=2000)
        raw = re.sub(r'^```json\s*\n?', '', text, flags=re.IGNORECASE)
        raw = re.sub(r'\n?```\s*$', '', raw).strip()
        return {"captions": json.loads(raw)}
    except json.JSONDecodeError:
        return {"captions": {"instagram": quote, "facebook": quote, "twitter": quote, "threads": quote, "tiktok": quote}}
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)

@router.post("/api/save")
async def api_save(req: Request):
    body = await req.json()
    gallery = load_json(GFX_GALLERY_FILE, [])
    entry = {
        "id": str(uuid.uuid4())[:8],
        "brand": body.get("brand_id", ""),
        "brand_name": body.get("brand_name", ""),
        "topic": body.get("topic", ""),
        "quote": body.get("quote", ""),
        "image_prompt": body.get("prompt", ""),
        "image_url": body.get("image_url", ""),
        "captions": body.get("captions", {}),
        "model": body.get("model", ""),
        "aspect": body.get("aspect", ""),
        "created": datetime.now().isoformat(),
        "published": False,
    }
    gallery.insert(0, entry)
    save_json(GFX_GALLERY_FILE, gallery[:500])
    return {"status": "saved", "id": entry["id"]}


@router.post("/api/publish")
async def api_publish(req: Request):
    body = await req.json()
    brand_id = body.get("brand_id", "")
    image_url = body.get("image_url", "")
    captions = body.get("captions", {})
    platforms = body.get("platforms", [])
    gallery_id = body.get("gallery_id", "")

    brand = next((b for b in get_brands() if b["id"] == brand_id), None)
    if not brand:
        return JSONResponse({"error": "Brand not found"}, 400)

    blotato_key = os.environ.get("BLOTATO_API_KEY", "")
    if not blotato_key:
        return JSONResponse({"error": "BLOTATO_API_KEY not set"}, 400)

    acct = brand.get("blotato", {})
    results = {}

    media_url = image_url
    try:
        r = requests.post("https://backend.blotato.com/v2/media",
            headers={"Authorization": f"Bearer {blotato_key}", "Content-Type": "application/json"},
            json={"url": image_url}, timeout=30)
        r.raise_for_status()
        media_url = r.json().get("url", image_url)
    except Exception as e:
        return JSONResponse({"error": f"Media upload failed: {e}"}, 500)

    for plat in platforms:
        acct_id = acct.get(plat, "")
        if not acct_id:
            results[plat] = {"ok": False, "error": "No account ID configured"}
            continue

        caption = captions.get(plat, captions.get("instagram", ""))
        payload = {
            "post": {
                "accountId": acct_id,
                "content": {"text": caption, "mediaUrls": [media_url], "platform": plat},
                "target": {"targetType": plat},
            }
        }
        if plat == "facebook" and acct.get("facebook_page"):
            payload["post"]["target"]["pageId"] = acct["facebook_page"]
        if plat == "tiktok":
            payload["post"]["target"]["privacyLevel"] = "PUBLIC_TO_EVERYONE"
            payload["post"]["target"]["isAiGenerated"] = True
        if plat == "pinterest" and acct.get("pinterest_board"):
            payload["post"]["target"]["boardId"] = acct["pinterest_board"]

        try:
            r = requests.post("https://backend.blotato.com/v2/posts",
                headers={"Authorization": f"Bearer {blotato_key}", "Content-Type": "application/json"},
                json=payload, timeout=30)
            if r.ok:
                results[plat] = {"ok": True}
            else:
                results[plat] = {"ok": False, "error": f"{r.status_code}: {r.text[:200]}"}
        except Exception as e:
            results[plat] = {"ok": False, "error": str(e)}

    if gallery_id:
        gallery = load_json(GFX_GALLERY_FILE, [])
        for item in gallery:
            if item.get("id") == gallery_id:
                item["published"] = True
                item["published_at"] = datetime.now().isoformat()
                item["published_platforms"] = [p for p in results if results[p].get("ok")]
                break
        save_json(GFX_GALLERY_FILE, gallery)

    ok_count = sum(1 for r in results.values() if r.get("ok"))
    return {"status": "published", "results": results, "ok_count": ok_count, "total": len(platforms)}

@router.get("/api/gallery")
async def api_gallery():
    return load_json(GFX_GALLERY_FILE, [])[:100]

@router.delete("/api/gallery/{item_id}")
async def api_del_gallery(item_id: str):
    g = load_json(GFX_GALLERY_FILE, [])
    save_json(GFX_GALLERY_FILE, [x for x in g if x.get("id") != item_id])
    return {"status": "deleted"}


# ─── DASHBOARD HTML ──────────────────────────────────────────
# Loads shared /static/style.css + supplemental /static/graphics.css
# No inline <style> block — single source of truth for design system

@router.get("/", response_class=HTMLResponse)
async def gfx_page():
    return GFX_HTML

GFX_HTML = r"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Graphics Engine — Knights Reactor</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/style.css">
<link rel="stylesheet" href="/static/graphics.css">
</head><body>

<div class="gfx-shell">
<!-- ═══ SIDEBAR ═══ -->
<aside class="sidebar">
<div class="sb-logo"><h1>Knights<br>Reactor</h1><p>GRAPHICS ENGINE v2</p></div>
<nav class="sb-nav">
<a class="sb-i" href="/"><span class="material-symbols-outlined">bolt</span>PIPELINE</a>
<a class="sb-i on" href="/graphics"><span class="material-symbols-outlined">palette</span>GRAPHICS</a>
</nav>
<div style="padding:.8em 1.2em;border-top:1px solid rgba(var(--fg),.06)">
<button onclick="document.documentElement.classList.toggle('light');localStorage.setItem('kr-theme',document.documentElement.classList.contains('light')?'light':'dark')" style="width:100%;padding:6px;font-size:.5em;letter-spacing:.15em;color:var(--txtd);background:none;border:1px solid var(--bd2);font-family:var(--f3);cursor:pointer;border-radius:var(--r)">☀ TOGGLE THEME</button>
</div>
</aside>

<!-- ═══ MAIN ═══ -->
<div class="main-area">
<div class="topbar">
  <div class="topbar-t">Graphics &amp; Assets</div>
  <div class="top-tabs">
    <button class="top-tab on" onclick="gN('create',this)">Create</button>
    <button class="top-tab" onclick="gN('gallery',this)">Library</button>
  </div>
</div>

<div class="content">

<!-- ════════════════════════════════════════════════ -->
<!-- CREATE PAGE -->
<!-- ════════════════════════════════════════════════ -->
<div class="page on" id="p-create">

  <!-- ── 01 SETUP ── -->
  <div class="sec-head"><div class="sec-num">01</div><div class="sec-title">Setup</div></div>
  <div class="panel">
    <div class="fg-3">
      <div class="fi"><div class="fl">Brand <span style="font-weight:400;text-transform:none;letter-spacing:0">(Graphics Engine only — separate from Pipeline)</span></div>
        <select class="fin" id="s-brand" style="margin-bottom:.4em"></select>
        <div style="display:flex;gap:6px">
          <button class="btn btn-out" style="flex:1" onclick="createGfxBrand()">+ New Brand</button>
          <button class="btn btn-out" style="flex:1;color:var(--red,#e04)" onclick="deleteGfxBrand()">Delete Brand</button>
        </div>
      </div>
      <div class="fi"><div class="fl">Aspect Ratio</div><select class="fin" id="s-aspect">
        <option value="1:1">1:1 Square</option><option value="9:16">9:16 Vertical</option>
        <option value="4:5">4:5 Portrait</option><option value="16:9">16:9 Landscape</option>
      </select></div>
      <div class="fi"><div class="fl">Image Model</div><select class="fin" id="s-model">
        <option value="black-forest-labs/flux-1.1-pro">Flux 1.1 Pro ~$0.04</option>
        <option value="black-forest-labs/flux-schnell">Flux Schnell ~$0.003</option>
        <option value="google/nano-banana-pro">Nano Banana Pro ~$0.10</option>
        <option value="google/nano-banana">Nano Banana ~$0.02</option>
        <option value="xai/grok-imagine-image">Grok Aurora ~$0.07</option>
        <option value="bytedance/seedream-4.5">Seedream 4.5 ~$0.03</option>
        <option value="ideogram-ai/ideogram-v3-quality">Ideogram v3 Q ~$0.08</option>
        <option value="ideogram-ai/ideogram-v3-turbo">Ideogram v3 T ~$0.02</option>
        <option value="recraft-ai/recraft-v3">Recraft v3 ~$0.04</option>
        <option value="google-deepmind/imagen-4-preview">Imagen 4 ~$0.04</option>
      </select></div>
    </div>
    <div class="fi" style="margin-top:.8em">
      <div class="fl">Brand Voice &amp; Guidelines <span style="font-weight:400;text-transform:none;letter-spacing:0">(drives this brand's topic ideas, quote tone, and image art direction)</span></div>
      <textarea class="fin" id="s-guidelines" rows="3" placeholder="Describe how this brand should sound and look — e.g. &quot;Confident, no-hype brand designer speaking to small business owners. Calm, editorial, blunt truths. Never salesy or motivational.&quot;"></textarea>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:.4em">
        <span class="status" id="guidelines-status" style="font-size:.6em"></span>
        <button class="btn btn-out" style="padding:.3em 1.2em" onclick="saveGuidelines()">Save Voice &amp; Guidelines</button>
      </div>
    </div>
  </div>

  <!-- ── 02 TOPIC ── -->
  <div class="sec-head"><div class="sec-num">02</div><div class="sec-title">Topic</div></div>
  <div class="panel" id="st-1">
    <div class="fi"><div class="fl">Select from Topics DB or type your own</div>
      <select class="fin" id="f-topic-list" onchange="pickTopic(this.value)" style="margin-bottom:.5em">
        <option value="">— Select a topic —</option>
      </select>
      <div style="display:flex;justify-content:flex-end;margin:-.3em 0 .5em">
        <span style="font-size:.6em;color:var(--txtd,#888);cursor:pointer;text-decoration:underline" onclick="toggleTopicMgr()" id="topic-mgr-toggle">Manage topics ▾</span>
      </div>
      <div id="topic-mgr" style="display:none;max-height:12em;overflow-y:auto;border:1px solid var(--bd2,#ddd);border-radius:var(--r,4px);margin-bottom:.6em"></div>
      <textarea class="fin" id="f-topic" rows="2" placeholder="Select above, use Random, or type freely..."></textarea>
    </div>
    <div class="btn-row">
      <button class="btn btn-out" onclick="loadTopics()"><span class="material-symbols-outlined" style="font-size:1em;vertical-align:middle">refresh</span> Refresh</button>
      <button class="btn btn-out" onclick="randomTopic()"><span class="material-symbols-outlined" style="font-size:1em;vertical-align:middle">casino</span> Random</button>
      <button class="btn btn-amb" onclick="genTopicAI()"><span class="material-symbols-outlined" style="font-size:1em;vertical-align:middle">auto_awesome</span> AI Generate</button>
      <button class="btn btn-out" onclick="saveCurrentTopic()"><span class="material-symbols-outlined" style="font-size:1em;vertical-align:middle">bookmark_add</span> Save to Topics DB</button>
    </div>
    <div class="btn-row-end">
      <button class="btn btn-grn" onclick="lockStep(1)" id="btn-lock1">Apply &amp; Next →</button>
    </div>
    <div class="status" id="st1-status"></div>
  </div>

  <!-- ── 03 QUOTE ── -->
  <div class="sec-head"><div class="sec-num">03</div><div class="sec-title">Quote</div></div>
  <div class="panel panel-locked" id="st-2">
    <div class="fi"><div class="fl">Quote / text overlay for the image</div>
      <textarea class="fin" id="f-quote" rows="2" placeholder="AI generates from your topic..."></textarea>
    </div>
    <div class="btn-row">
      <button class="btn btn-amb" onclick="genQuote()"><span class="material-symbols-outlined" style="font-size:1em;vertical-align:middle">auto_awesome</span> Generate</button>
      <button class="btn btn-out" onclick="genQuote()"><span class="material-symbols-outlined" style="font-size:1em;vertical-align:middle">refresh</span> Regenerate</button>
    </div>
    <div class="btn-row-end">
      <button class="btn btn-grn" onclick="lockStep(2)">Apply &amp; Next →</button>
    </div>
    <div class="status" id="st2-status"></div>
  </div>

  <!-- ── 04 IMAGE PROMPT ── -->
  <div class="sec-head"><div class="sec-num">04</div><div class="sec-title">Image Prompt</div></div>
  <div class="panel panel-locked" id="st-3">
    <div class="fi"><div class="fl">Scene Engine builds a photorealistic lettering prompt</div>
      <textarea class="fin" id="f-prompt" rows="5" placeholder="Click Generate to build a randomized scene, or write your own..."></textarea>
    </div>
    <div style="display:flex;justify-content:flex-end;gap:14px;margin:-.3em 0 .5em">
      <span style="font-size:.6em;color:var(--txtd,#888);cursor:pointer;text-decoration:underline" onclick="toggleSectionsEditor()" id="sec-toggle">Customize this brand's scene sections ▾</span>
      <span style="font-size:.6em;color:var(--txtd,#888);cursor:pointer;text-decoration:underline" onclick="toggleTplEditor()" id="tpl-toggle">Advanced: full raw template ▾</span>
    </div>
    <div id="sec-editor" style="display:none;border:1px solid var(--bd2,#ddd);border-radius:var(--r,4px);padding:10px;margin-bottom:.6em">
      <div class="fl" style="margin-bottom:4px">This brand's scene sections (optional, per-section)</div>
      <div style="font-size:.6em;color:var(--txtd,#888);margin-bottom:8px">Every generated prompt is built from these pieces: environment, lighting/mood, surface the text appears on, typography, camera feel, and a small real-life detail. Leave any section blank to keep it randomized (for variety); fill one in to pin it for this brand only. Ignored if a full raw template below is set.</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.6em 1.2em">
        <div class="fi"><div class="fl" style="font-size:.55em">Environment / Scene</div>
          <textarea class="fin" id="sec-scene" rows="2" placeholder="e.g. modern minimalist studio with a clean neutral backdrop and soft daylight"></textarea></div>
        <div class="fi"><div class="fl" style="font-size:.55em">Lighting &amp; Mood</div>
          <textarea class="fin" id="sec-mood" rows="2" placeholder="e.g. soft even studio light, neutral color, calm and controlled — no harsh shadows"></textarea></div>
        <div class="fi"><div class="fl" style="font-size:.55em">Surface / Carrier</div>
          <textarea class="fin" id="sec-carrier" rows="2" placeholder="e.g. lettering printed on matte cardstock resting on a wood desk"></textarea></div>
        <div class="fi"><div class="fl" style="font-size:.55em">Typography Style</div>
          <textarea class="fin" id="sec-typography" rows="2" placeholder="e.g. modern serif, confident and editorial, generous letter spacing"></textarea></div>
        <div class="fi"><div class="fl" style="font-size:.55em">Camera / Lens Feel</div>
          <textarea class="fin" id="sec-camera" rows="2" placeholder="e.g. clean overhead flat-lay, shallow depth of field, no distortion"></textarea></div>
        <div class="fi"><div class="fl" style="font-size:.55em">Real-life Detail</div>
          <textarea class="fin" id="sec-moment" rows="2" placeholder="e.g. a coffee cup sits just out of frame at the edge of the desk"></textarea></div>
      </div>
      <div class="btn-row" style="margin-top:6px">
        <button class="btn btn-grn" onclick="saveSections()">Save Sections</button>
        <button class="btn btn-out" onclick="clearSections()">Clear All (fully randomized)</button>
      </div>
      <div class="status" id="sec-status"></div>
    </div>
    <div id="tpl-editor" style="display:none;border:1px solid var(--bd2,#ddd);border-radius:var(--r,4px);padding:10px;margin-bottom:.6em">
      <div class="fl" style="margin-bottom:4px">This brand's Image Prompt template (optional, replaces everything above)</div>
      <div style="font-size:.6em;color:var(--txtd,#888);margin-bottom:6px">Leave empty to use the sections above (or the shared randomized engine). Fill this in to replace the whole prompt with your own exact wording for this brand only — use <code>{TEXT}</code> anywhere you want the quote inserted.</div>
      <textarea class="fin" id="tpl-text" rows="6" placeholder="e.g. A clean flat-lay product photo. The exact text displayed must be: {TEXT}. Minimal, bright, on-brand colors..."></textarea>
      <div class="btn-row" style="margin-top:6px">
        <button class="btn btn-grn" onclick="saveTpl()">Save Template</button>
        <button class="btn btn-out" onclick="clearTpl()">Clear (use sections/default engine)</button>
      </div>
      <div class="status" id="tpl-status"></div>
    </div>
    <div class="btn-row">
      <button class="btn btn-amb" onclick="genPrompt()"><span class="material-symbols-outlined" style="font-size:1em;vertical-align:middle">auto_awesome</span> Generate</button>
      <button class="btn btn-out" onclick="genPrompt()"><span class="material-symbols-outlined" style="font-size:1em;vertical-align:middle">refresh</span> Regenerate</button>
    </div>
    <div class="btn-row-end">
      <button class="btn btn-grn" onclick="lockStep(3)">Apply &amp; Generate Image →</button>
    </div>
    <div class="status" id="st3-status"></div>
  </div>

  <!-- ── 05 IMAGE ── -->
  <div class="sec-head"><div class="sec-num">05</div><div class="sec-title">Image Generation</div></div>
  <div class="panel panel-locked" id="st-4">
    <div id="img-area"></div>
    <div class="btn-row">
      <button class="btn btn-amb" onclick="genImage()" id="btn-genimg"><span class="material-symbols-outlined" style="font-size:1em;vertical-align:middle">image</span> Generate Image</button>
      <button class="btn btn-out" onclick="genImage()"><span class="material-symbols-outlined" style="font-size:1em;vertical-align:middle">refresh</span> Regenerate</button>
    </div>
    <div class="btn-row-end">
      <button class="btn btn-grn" onclick="lockStep(4)" id="btn-lock4" disabled>Approve &amp; Next →</button>
    </div>
    <div class="status" id="st4-status"></div>
  </div>

  <!-- ── 06 CAPTIONS ── -->
  <div class="sec-head"><div class="sec-num">06</div><div class="sec-title">Captions</div></div>
  <div class="panel panel-locked" id="st-5">
    <div id="cap-area"></div>
    <div class="btn-row">
      <button class="btn btn-amb" onclick="genCaptions()"><span class="material-symbols-outlined" style="font-size:1em;vertical-align:middle">auto_awesome</span> Generate Captions</button>
      <button class="btn btn-out" onclick="genCaptions()"><span class="material-symbols-outlined" style="font-size:1em;vertical-align:middle">refresh</span> Regenerate</button>
    </div>
    <div class="btn-row-end">
      <button class="btn btn-grn" onclick="lockStep(5)">Approve &amp; Save →</button>
    </div>
    <div class="status" id="st5-status"></div>
  </div>

  <!-- ── 07 SAVE & PUBLISH ── -->
  <div class="sec-head"><div class="sec-num">07</div><div class="sec-title">Save &amp; Publish</div></div>
  <div class="panel panel-locked" id="st-6">
    <div id="final-summary"></div>
    <div style="margin:.6em 0">
      <div class="fl">Publish to platforms</div>
      <div class="pub-grid" id="pub-toggles">
        <label class="pub-chip"><input type="checkbox" class="pub-plat" value="instagram" checked><span class="material-symbols-outlined" style="font-size:1em">photo_camera</span> Instagram</label>
        <label class="pub-chip"><input type="checkbox" class="pub-plat" value="facebook" checked><span class="material-symbols-outlined" style="font-size:1em">groups</span> Facebook</label>
        <label class="pub-chip"><input type="checkbox" class="pub-plat" value="twitter" checked><span class="material-symbols-outlined" style="font-size:1em">tag</span> X / Twitter</label>
        <label class="pub-chip"><input type="checkbox" class="pub-plat" value="threads" checked><span class="material-symbols-outlined" style="font-size:1em">thread_unread</span> Threads</label>
        <label class="pub-chip"><input type="checkbox" class="pub-plat" value="tiktok"><span class="material-symbols-outlined" style="font-size:1em">music_note</span> TikTok</label>
        <label class="pub-chip"><input type="checkbox" class="pub-plat" value="pinterest"><span class="material-symbols-outlined" style="font-size:1em">push_pin</span> Pinterest</label>
      </div>
    </div>
    <div class="btn-row">
      <button class="btn btn-grn" onclick="savePost()"><span class="material-symbols-outlined" style="font-size:1em;vertical-align:middle">save</span> Save to Gallery</button>
      <button class="btn btn-blu" onclick="publishPost()"><span class="material-symbols-outlined" style="font-size:1em;vertical-align:middle">cell_tower</span> Publish Now</button>
      <button class="btn btn-amb" onclick="resetFlow()"><span class="material-symbols-outlined" style="font-size:1em;vertical-align:middle">add</span> New Post</button>
    </div>
    <div class="status" id="st6-status"></div>
  </div>

  <div style="height:3em"></div>
</div>

<!-- ════════════════════════════════════════════════ -->
<!-- GALLERY PAGE -->
<!-- ════════════════════════════════════════════════ -->
<div class="page" id="p-gallery">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.8em">
    <div class="sec-head" style="margin:0"><div class="sec-title">Saved Posts</div></div>
    <span id="g-count" style="font-family:var(--f2);font-size:.55em;color:var(--txtd)"></span>
  </div>
  <div class="gal" id="g-grid"></div>
</div>

</div><!-- /content -->

<div class="gfx-footer">
  <div><span>SYSTEM STATE: </span><span class="ok" id="footer-state">READY</span></div>
  <span id="footer-time"></span>
</div>

</div><!-- /main-area -->
</div><!-- /shell -->

<!-- ═══ MOBILE BOTTOM NAV ═══ -->
<nav class="bnav gfx-bnav">
<a class="bnav-i" href="/"><span class="bnav-icon"><span class="material-symbols-outlined">bolt</span></span><span class="bnav-lbl">Pipeline</span></a>
<button class="bnav-i on" onclick="gN('create',null);updBnav(this)"><span class="bnav-icon"><span class="material-symbols-outlined">brush</span></span><span class="bnav-lbl">Create</span></button>
<button class="bnav-i" onclick="gN('gallery',null);updBnav(this)"><span class="bnav-icon"><span class="material-symbols-outlined">collections</span></span><span class="bnav-lbl">Library</span></button>
<button class="bnav-i" onclick="document.documentElement.classList.toggle('light');localStorage.setItem('kr-theme',document.documentElement.classList.contains('light')?'light':'dark')"><span class="bnav-icon"><span class="material-symbols-outlined">contrast</span></span><span class="bnav-lbl">Theme</span></button>
</nav>

<!-- MODAL -->
<div class="mbg" id="modal" onclick="cM()">
<button class="mx" onclick="cM()">✕</button>
<img class="mimg" id="m-img" src="">
<div class="mdet" id="m-det"></div>
</div>

<script>
const $=id=>document.getElementById(id), API='/graphics/api';
let STATE={step:1, brand_id:'', topic:'', quote:'', prompt:'', image_url:'', captions:{}, gallery_id:''};

// ─── MOBILE BOTTOM NAV ──────────────────────────────────────
function updBnav(btn){document.querySelectorAll('.gfx-bnav .bnav-i').forEach(b=>b.classList.remove('on'));if(btn)btn.classList.add('on');}

// ─── NAV ─────────────────────────────────────────────────────
function gN(p,b){
  document.querySelectorAll('.page').forEach(e=>e.classList.remove('on'));
  document.querySelectorAll('.top-tab').forEach(b=>b.classList.remove('on'));
  $('p-'+p).classList.add('on');
  if(b)b.classList.add('on');
  if(p==='gallery')lG();
}

// ─── THEME ────────────────────────────────────────────────────
(function(){if(localStorage.getItem('kr-theme')==='light')document.documentElement.classList.add('light');})();

// ─── BRANDS ──────────────────────────────────────────────────
// Graphics Engine owns its own brand list (graphics_brands/) — it never reads
// the Pipeline's shared /api/brands or its "active brand" pointer. The last
// brand picked here is remembered locally (per-browser) just for convenience.
function onBrandChange(){
  const b=$('s-brand').value;
  if(b)localStorage.setItem('gfx-last-brand',b);
  loadTopics();loadBrandInfo();
}
async function lB(){
  try{
    const brands=await(await fetch(API+'/brands')).json();
    const list=Array.isArray(brands)?brands:[];
    const last=localStorage.getItem('gfx-last-brand');
    $('s-brand').innerHTML=list.length
      ? list.map(b=>`<option value="${b.id}"${b.id===last?' selected':''}>${b.name}</option>`).join('')
      : '<option value="">No brands yet — click + New Brand</option>';
    $('s-brand').onchange=onBrandChange;
    if(list.length)onBrandChange();
  }catch(e){}
}
async function createGfxBrand(){
  const name=prompt('New brand name:');
  if(!name||!name.trim())return;
  try{
    const r=await(await fetch(API+'/brands',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name.trim()})})).json();
    if(r.error){alert('Error: '+r.error);return;}
    localStorage.setItem('gfx-last-brand',r.id);
    await lB();
  }catch(e){alert('Create failed: '+e);}
}
async function deleteGfxBrand(){
  const brand=$('s-brand').value;if(!brand)return;
  const opt=$('s-brand').selectedOptions[0];
  const name=opt?opt.textContent:brand;
  const typed=prompt(`Type the brand name "${name}" exactly to permanently delete it — settings, all topics, and its prompt template. This cannot be undone.`);
  if(typed===null)return;
  if(typed!==name){alert('Name did not match — nothing was deleted.');return;}
  try{
    await fetch(API+'/brands/'+brand,{method:'DELETE'});
    localStorage.removeItem('gfx-last-brand');
    await lB();
  }catch(e){alert('Delete failed: '+e);}
}

// ─── PER-BRAND IMAGE PROMPT TEMPLATE ────────────────────────────
let BRAND_INFO=null;
let TPL_OPEN=false;
async function loadBrandInfo(){
  const brand=$('s-brand').value;if(!brand)return;
  try{
    const brands=await(await fetch(API+'/brands')).json();
    BRAND_INFO=(Array.isArray(brands)?brands:[]).find(b=>b.id===brand)||null;
    const box=$('tpl-text');
    if(box)box.value=(BRAND_INFO&&BRAND_INFO.image_prompt_template)||'';
    const secs=(BRAND_INFO&&BRAND_INFO.prompt_sections)||{};
    ['scene','mood','carrier','typography','camera','life_moment'].forEach(k=>{
      const el=$('sec-'+k); if(el)el.value=secs[k]||'';
    });
    if($('sec-status'))$('sec-status').innerHTML='';
    const g=$('s-guidelines');
    if(g)g.value=(BRAND_INFO&&BRAND_INFO.guidelines)||'';
    if($('guidelines-status'))$('guidelines-status').innerHTML='';
  }catch(e){BRAND_INFO=null;}
}
async function saveGuidelines(){
  const brand=$('s-brand').value;if(!brand){alert('Pick a brand first');return;}
  const guidelines=($('s-guidelines')||{}).value||'';
  $('guidelines-status').innerHTML='<span class="spin">⏳</span> Saving...';
  try{
    await fetch(API+'/brand-guidelines/'+brand,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({guidelines})});
    if(BRAND_INFO)BRAND_INFO.guidelines=guidelines;
    $('guidelines-status').innerHTML='<span style="color:var(--grn)">✓ Saved</span>';
  }catch(e){$('guidelines-status').innerHTML=`<span style="color:var(--red)">Save failed: ${e}</span>`;}
}
function toggleTplEditor(){
  TPL_OPEN=!TPL_OPEN;
  const el=$('tpl-editor'), tg=$('tpl-toggle');
  if(el)el.style.display=TPL_OPEN?'block':'none';
  if(tg)tg.textContent=TPL_OPEN?"Advanced: full raw template ▴":"Advanced: full raw template ▾";
}
async function saveTpl(){
  const brand=$('s-brand').value;if(!brand)return;
  const template=($('tpl-text')||{}).value||'';
  try{
    await fetch(API+'/brand-prompt-template/'+brand,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({template})});
    if(BRAND_INFO)BRAND_INFO.image_prompt_template=template;
    $('tpl-status').innerHTML='<span style="color:var(--grn)">✓ Saved — this brand will use it from now on</span>';
  }catch(e){$('tpl-status').innerHTML=`<span style="color:var(--red)">Save failed: ${e}</span>`;}
}
async function clearTpl(){
  if(!confirm("Clear this brand's custom prompt template? It will go back to the section overrides / shared default engine."))return;
  const t=$('tpl-text');if(t)t.value='';
  await saveTpl();
}

// ─── PER-BRAND PROMPT SECTIONS (pin one piece of the prompt, randomize the rest) ───
let SEC_OPEN=false;
const SEC_KEYS=['scene','mood','carrier','typography','camera','life_moment'];
function toggleSectionsEditor(){
  SEC_OPEN=!SEC_OPEN;
  const el=$('sec-editor'), tg=$('sec-toggle');
  if(el)el.style.display=SEC_OPEN?'block':'none';
  if(tg)tg.textContent=SEC_OPEN?"Customize this brand's scene sections ▴":"Customize this brand's scene sections ▾";
}
async function saveSections(){
  const brand=$('s-brand').value;if(!brand)return;
  const sections={};
  SEC_KEYS.forEach(k=>{sections[k]=(($('sec-'+k)||{}).value||'').trim();});
  try{
    await fetch(API+'/brand-prompt-sections/'+brand,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sections})});
    if(BRAND_INFO)BRAND_INFO.prompt_sections=sections;
    $('sec-status').innerHTML='<span style="color:var(--grn)">✓ Saved — pinned sections apply from now on, blank ones stay randomized</span>';
  }catch(e){$('sec-status').innerHTML=`<span style="color:var(--red)">Save failed: ${e}</span>`;}
}
async function clearSections(){
  if(!confirm("Clear all scene section overrides for this brand? Every section goes back to fully randomized."))return;
  SEC_KEYS.forEach(k=>{const el=$('sec-'+k);if(el)el.value='';});
  await saveSections();
}

// ─── STEP MANAGEMENT ─────────────────────────────────────────
function updateSteps(){
  for(let i=1;i<=6;i++){
    const el=$('st-'+i);if(!el)continue;
    el.classList.remove('panel-active','panel-done','panel-locked');
    if(i<STATE.step) el.classList.add('panel-done');
    else if(i===STATE.step) el.classList.add('panel-active');
    else el.classList.add('panel-locked');
  }
  const fs=$('footer-state');
  if(fs){
    if(STATE.step<=1)fs.textContent='READY';
    else if(STATE.step<=6)fs.textContent='STEP_'+STATE.step+'_ACTIVE';
    else fs.textContent='COMPLETE';
  }
}
function lockStep(n){
  if(n===1 && !$('f-topic').value.trim()){alert('Enter or generate a topic first');return;}
  if(n===2 && !$('f-quote').value.trim()){alert('Enter or generate a quote first');return;}
  if(n===3 && !$('f-prompt').value.trim()){alert('Enter or generate an image prompt first');return;}
  if(n===4 && !STATE.image_url){alert('Generate an image first');return;}
  if(n===5){
    const caps={};
    document.querySelectorAll('.cap-text').forEach(el=>{caps[el.dataset.plat]=el.value;});
    STATE.captions=caps;
  }
  if(n===1) STATE.topic=$('f-topic').value.trim();
  if(n===2) STATE.quote=$('f-quote').value.trim();
  if(n===3) STATE.prompt=$('f-prompt').value.trim();
  STATE.step=n+1;
  updateSteps();
  const next=$('st-'+(n+1));
  if(next)next.scrollIntoView({behavior:'smooth',block:'center'});
  if(n===1) genQuote();
  if(n===2) genPrompt();
  if(n===3) genImage();
  if(n===4) genCaptions();
  if(n===5) showSummary();
}

// ─── PHASE 1: TOPIC ─────────────────────────────────────────
let TOPICS_CACHE=[];
let TOPICS_REQ_ID=0; // guards against a slow response from a previous brand landing after you've switched
async function loadTopics(){
  const brand=$('s-brand').value;if(!brand)return;
  const reqId=++TOPICS_REQ_ID;
  try{
    const r=await(await fetch(API+'/topics/'+brand)).json();
    if(reqId!==TOPICS_REQ_ID||$('s-brand').value!==brand)return; // brand changed while this was in flight — discard
    TOPICS_CACHE=r.topics||[];
    const sel=$('f-topic-list');
    sel.innerHTML='<option value="">— '+r.new+' new / '+r.total+' total —</option>';
    TOPICS_CACHE.filter(t=>t.status==='new').forEach(t=>{
      const o=document.createElement('option');o.value=t.idea;
      o.textContent=t.idea+(t.category?' ['+t.category+']':'');
      sel.appendChild(o);
    });
    $('st1-status').innerHTML='<span style="color:var(--grn)">✓ '+r.new+' new topics loaded</span>';
    renderTopicMgr();
  }catch(e){if($('s-brand').value===brand)$('st1-status').innerHTML=`<span style="color:var(--red)">Error: ${e}</span>`;}
}
function pickTopic(val){if(val)$('f-topic').value=val;}

// ─── MANAGE / DELETE TOPICS (Graphics Engine's own topics.json — not shared with the Pipeline) ───
let TOPIC_MGR_OPEN=false;
function toggleTopicMgr(){
  TOPIC_MGR_OPEN=!TOPIC_MGR_OPEN;
  const el=$('topic-mgr'), tg=$('topic-mgr-toggle');
  if(el)el.style.display=TOPIC_MGR_OPEN?'block':'none';
  if(tg)tg.textContent=TOPIC_MGR_OPEN?'Manage topics ▴':'Manage topics ▾';
  if(TOPIC_MGR_OPEN)renderTopicMgr();
}
function renderTopicMgr(){
  const el=$('topic-mgr');if(!el||!TOPIC_MGR_OPEN)return;
  if(!TOPICS_CACHE.length){el.innerHTML='<div style="padding:8px;font-size:.6em;color:var(--txtd,#888)">No topics for this brand yet.</div>';return;}
  el.innerHTML=TOPICS_CACHE.map(t=>`<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding:6px 8px;border-bottom:1px solid var(--bd2,#eee)">
    <div style="flex:1;min-width:0;font-size:.65em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${(t.idea||'').replace(/"/g,'&quot;')}">${t.idea}${t.category?' ['+t.category+']':''}</div>
    <button class="btn-sm btn-red" onclick="deleteGfxTopic('${t.id}')" title="Delete">✕</button>
  </div>`).join('');
}
async function deleteGfxTopic(id){
  const brand=$('s-brand').value;if(!brand)return;
  if(!confirm('Delete this topic from this brand?'))return;
  try{
    await fetch(API+'/topics/'+brand+'/'+id,{method:'DELETE'});
    await loadTopics();
  }catch(e){alert('Delete failed: '+e);}
}
async function randomTopic(){
  const brand=$('s-brand').value;if(!brand)return;
  $('st1-status').innerHTML='<span class="spin">⏳</span> Picking random...';
  try{
    const r=await(await fetch(API+'/phase/topic',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({brand_id:brand,mode:'random'})})).json();
    if($('s-brand').value!==brand)return; // brand changed while this was in flight — discard
    if(r.error){$('st1-status').innerHTML=`<span style="color:var(--red)">${r.error}</span>`;return;}
    $('f-topic').value=r.topic||'';
    $('st1-status').innerHTML='<span style="color:var(--grn)">✓ Random topic selected</span>';
  }catch(e){if($('s-brand').value===brand)$('st1-status').innerHTML=`<span style="color:var(--red)">Error: ${e}</span>`;}
}
async function genTopicAI(){
  const brand=$('s-brand').value;if(!brand)return;
  $('st1-status').innerHTML='<span class="spin">⏳</span> AI generating topic...';
  try{
    const r=await(await fetch(API+'/phase/topic',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({brand_id:brand,mode:'ai'})})).json();
    if($('s-brand').value!==brand)return; // brand changed while this was in flight — discard
    if(r.error){$('st1-status').innerHTML=`<span style="color:var(--red)">${r.error}</span>`;return;}
    $('f-topic').value=r.topic||'';
    $('st1-status').innerHTML='<span style="color:var(--grn)">✓ AI topic generated — click "Save to Topics DB" to keep it</span>';
  }catch(e){if($('s-brand').value===brand)$('st1-status').innerHTML=`<span style="color:var(--red)">Error: ${e}</span>`;}
}
async function saveCurrentTopic(){
  const brand=$('s-brand').value;if(!brand){alert('Pick a brand first');return;}
  const idea=$('f-topic').value.trim();
  if(!idea){alert('Type or generate a topic first');return;}
  $('st1-status').innerHTML='<span class="spin">⏳</span> Saving...';
  try{
    const r=await(await fetch(API+'/topics/'+brand,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idea})})).json();
    if(r.error){$('st1-status').innerHTML=`<span style="color:var(--red)">${r.error}</span>`;return;}
    $('st1-status').innerHTML='<span style="color:var(--grn)">✓ Saved to Topics DB</span>';
    await loadTopics();
  }catch(e){$('st1-status').innerHTML=`<span style="color:var(--red)">Save failed: ${e}</span>`;}
}

// ─── PHASE 2: QUOTE ─────────────────────────────────────────
async function genQuote(){
  const brand=$('s-brand').value;const topic=$('f-topic').value.trim();
  if(!topic){alert('Need a topic first');return;}
  $('st2-status').innerHTML='<span class="spin">⏳</span> Generating quote...';
  try{
    const r=await(await fetch(API+'/phase/quote',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brand_id:brand,topic})})).json();
    if(r.error){$('st2-status').innerHTML=`<span style="color:var(--red)">${r.error}</span>`;return;}
    $('f-quote').value=r.quote;
    $('st2-status').innerHTML='<span style="color:var(--grn)">✓ Quote generated — edit if needed</span>';
  }catch(e){$('st2-status').innerHTML=`<span style="color:var(--red)">Error: ${e}</span>`;}
}

// ─── PHASE 3: PROMPT ─────────────────────────────────────────
async function genPrompt(){
  const brand=$('s-brand').value;const quote=$('f-quote').value.trim();
  if(!quote){alert('Need a quote first');return;}
  $('st3-status').innerHTML='<span class="spin">⏳</span> Building scene prompt...';
  try{
    const r=await(await fetch(API+'/phase/prompt',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brand_id:brand,quote})})).json();
    if(r.error){$('st3-status').innerHTML=`<span style="color:var(--red)">${r.error}</span>`;return;}
    $('f-prompt').value=r.prompt;
    $('st3-status').innerHTML='<span style="color:var(--grn)">✓ Scene prompt built — edit or regenerate</span>';
  }catch(e){$('st3-status').innerHTML=`<span style="color:var(--red)">Error: ${e}</span>`;}
}

// ─── PHASE 4: IMAGE ──────────────────────────────────────────
async function genImage(){
  const prompt=$('f-prompt').value.trim();if(!prompt){alert('Need an image prompt');return;}
  $('st4-status').innerHTML='<span class="spin">⏳</span> Generating image... (30-120s)';
  $('btn-lock4').disabled=true;$('img-area').innerHTML='';
  try{
    const r=await(await fetch(API+'/phase/image',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brand_id:$('s-brand').value,prompt,model:$('s-model').value,aspect:$('s-aspect').value})})).json();
    if(r.error){$('st4-status').innerHTML=`<span style="color:var(--red)">${r.error}</span>`;return;}
    const jid=r.job_id;
    const poll=setInterval(async()=>{
      const s=await(await fetch(API+'/phase/image/'+jid)).json();
      if(s.status==='done'){
        clearInterval(poll);
        STATE.image_url=s.r2_url||s.image_url;
        $('img-area').innerHTML=`<div class="img-box"><img src="${STATE.image_url}"></div>`;
        $('st4-status').innerHTML='<span style="color:var(--grn)">✓ Image generated — approve or regenerate</span>';
        $('btn-lock4').disabled=false;
      }else if(s.status==='failed'){
        clearInterval(poll);
        $('st4-status').innerHTML=`<span style="color:var(--red)">Failed: ${s.error||'Unknown'}</span>`;
        $('btn-lock4').disabled=false;
      }else{
        $('st4-status').innerHTML=`<span class="spin">⏳</span> ${s.phase||'Generating'}...`;
      }
    },4000);
  }catch(e){$('st4-status').innerHTML=`<span style="color:var(--red)">Error: ${e}</span>`;}
}

// ─── PHASE 5: CAPTIONS ───────────────────────────────────────
const PLATFORMS=[
  {id:'instagram',icon:'photo_camera'},
  {id:'facebook',icon:'groups'},
  {id:'tiktok',icon:'music_note'},
  {id:'twitter',icon:'tag'},
  {id:'threads',icon:'thread_unread'}
];
async function genCaptions(){
  $('st5-status').innerHTML='<span class="spin">⏳</span> Generating captions...';
  try{
    const r=await(await fetch(API+'/phase/captions',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brand_id:$('s-brand').value,topic:$('f-topic').value,quote:$('f-quote').value})})).json();
    if(r.error){$('st5-status').innerHTML=`<span style="color:var(--red)">${r.error}</span>`;return;}
    STATE.captions=r.captions||{};
    renderCaptions();
    $('st5-status').innerHTML='<span style="color:var(--grn)">✓ Captions generated — edit each platform</span>';
  }catch(e){$('st5-status').innerHTML=`<span style="color:var(--red)">Error: ${e}</span>`;}
}
function renderCaptions(){
  $('cap-area').innerHTML=PLATFORMS.map(p=>{
    const txt=STATE.captions[p.id]||'';
    return`<div class="cap-block"><div class="cap-plat"><span class="material-symbols-outlined">${p.icon}</span>${p.id}</div><textarea class="cap-text" data-plat="${p.id}" rows="3">${txt}</textarea></div>`;
  }).join('');
}

// ─── PHASE 6: SUMMARY & SAVE ─────────────────────────────────
function showSummary(){
  const brand=$('s-brand');const bn=brand.options[brand.selectedIndex]?.text||'';
  $('final-summary').innerHTML=`<div class="sum-row">
    <div class="sum-img">${STATE.image_url?`<div class="img-box"><img src="${STATE.image_url}"></div>`:''}</div>
    <div class="sum-details">
      <div class="fl">Brand</div><div class="sum-val">${bn}</div>
      <div class="fl">Topic</div><div class="sum-val">${STATE.topic}</div>
      <div class="fl">Quote</div><div class="sum-val amber">"${STATE.quote}"</div>
      <div class="fl">Captions</div><div class="sum-val">${Object.keys(STATE.captions).length} platforms ready</div>
    </div></div>`;
}

async function savePost(){
  const brand=$('s-brand');const bn=brand.options[brand.selectedIndex]?.text||'';
  $('st6-status').innerHTML='<span class="spin">⏳</span> Saving...';
  try{
    const r=await(await fetch(API+'/save',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brand_id:$('s-brand').value,brand_name:bn,topic:STATE.topic,
        quote:STATE.quote,prompt:$('f-prompt').value,image_url:STATE.image_url,
        captions:STATE.captions,model:$('s-model').value,aspect:$('s-aspect').value})})).json();
    STATE.gallery_id=r.id||'';
    $('st6-status').innerHTML=`<span style="color:var(--grn)">✓ Saved to gallery</span>`;
  }catch(e){$('st6-status').innerHTML=`<span style="color:var(--red)">Error: ${e}</span>`;}
}

async function publishPost(){
  const plats=[...document.querySelectorAll('.pub-plat:checked')].map(c=>c.value);
  if(!plats.length){alert('Select at least one platform');return;}
  if(!STATE.image_url){alert('No image to publish');return;}
  if(!STATE.gallery_id)await savePost();
  $('st6-status').innerHTML='<span class="spin">⏳</span> Publishing to '+plats.length+' platforms...';
  try{
    const r=await(await fetch(API+'/publish',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brand_id:$('s-brand').value,image_url:STATE.image_url,
        captions:STATE.captions,platforms:plats,gallery_id:STATE.gallery_id||''})})).json();
    if(r.error){$('st6-status').innerHTML=`<span style="color:var(--red)">${r.error}</span>`;return;}
    let msg=`<span style="color:var(--grn)">Published ${r.ok_count}/${r.total} platforms</span>`;
    for(const[p,res]of Object.entries(r.results||{})){
      msg+=`<br><span style="font-size:.85em;color:${res.ok?'var(--grn)':'var(--red)'}"> ${res.ok?'✓':'✗'} ${p}${res.error?' — '+res.error:''}</span>`;
    }
    $('st6-status').innerHTML=msg;
  }catch(e){$('st6-status').innerHTML=`<span style="color:var(--red)">Error: ${e}</span>`;}
}

function resetFlow(){
  STATE={step:1,brand_id:'',topic:'',quote:'',prompt:'',image_url:'',captions:{},gallery_id:''};
  $('f-topic').value='';$('f-quote').value='';$('f-prompt').value='';
  $('img-area').innerHTML='';$('cap-area').innerHTML='';$('final-summary').innerHTML='';
  $('btn-lock4').disabled=true;
  ['st1-status','st2-status','st3-status','st4-status','st5-status','st6-status'].forEach(id=>{const e=$(id);if(e)e.innerHTML='';});
  updateSteps();
  window.scrollTo({top:0,behavior:'smooth'});
}

// ─── GALLERY ─────────────────────────────────────────────────
async function lG(){
  try{
    const items=await(await fetch(API+'/gallery')).json();
    $('g-count').textContent=items.length+' posts';
    if(!items.length){$('g-grid').innerHTML='<div style="color:var(--txtd);font-size:.7em;padding:3em;text-align:center">No posts yet. Create one in the Create tab.</div>';return;}
    $('g-grid').innerHTML=items.map(g=>`<div class="gi" onclick="sM('${g.image_url}','${esc(g.quote)}','${esc(g.topic)}','${g.brand_name||g.brand}')"><img src="${g.image_url}" loading="lazy"><div class="gi-info"><div class="gi-topic">${g.topic||''}</div><div class="gi-quote">"${(g.quote||'').substring(0,50)}"</div><div class="gi-meta">${g.brand_name||g.brand} · ${(g.created||'').substring(0,10)}</div></div><div class="gi-del" onclick="event.stopPropagation();dG('${g.id}')">✕</div></div>`).join('');
  }catch(e){}
}
function esc(s){return(s||'').replace(/'/g,"\\'").replace(/"/g,'&quot;');}
async function dG(id){if(!confirm('Delete this post?'))return;await fetch(API+'/gallery/'+id,{method:'DELETE'});lG();}

// ─── MODAL ───────────────────────────────────────────────────
function sM(url,quote,topic,brand){$('modal').classList.add('show');$('m-img').src=url;$('m-det').innerHTML=`<b>${brand}</b><br>${topic}<br><i>"${quote}"</i>`;}
function cM(){$('modal').classList.remove('show');}

// ─── CLOCK ───────────────────────────────────────────────────
setInterval(()=>{const ft=$('footer-time');if(ft)ft.textContent=new Date().toLocaleTimeString('en-US',{hour12:false});},1000);

// ─── INIT ────────────────────────────────────────────────────
lB();updateSteps();
</script></body></html>"""
