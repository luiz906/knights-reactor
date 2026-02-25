"""
Knights Reactor — Graphics Engine
===================================
Multi-brand image content pipeline.
Brand Manager → AI Topic → Quote → Prompt → Image → Caption → Publish

Each brand = its own config profile (guidelines, accounts, logo, palette, tone).
Mounted at /graphics as a FastAPI router.
"""

import json, os, time, uuid, threading, re, logging
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

import requests
import boto3

from pipeline import Config

log = logging.getLogger("graphics")

router = APIRouter(prefix="/graphics", tags=["graphics"])

# ─── PERSISTENT STORAGE ──────────────────────────────────────
DATA_DIR = Path("/var/data") if Path("/var/data").exists() else Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
BRANDS_FILE = DATA_DIR / "brands.json"
GFX_RUNS_FILE = DATA_DIR / "graphics_runs.json"
GFX_GALLERY_FILE = DATA_DIR / "graphics_gallery.json"

def load_json(path, default=None):
    if path.exists():
        try: return json.loads(path.read_text())
        except: pass
    return default if default is not None else []

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))

# ─── BRAND MANAGER ───────────────────────────────────────────

def get_brands():
    return load_json(BRANDS_FILE, [])

def save_brands(brands):
    save_json(BRANDS_FILE, brands)

def get_brand(brand_id):
    for b in get_brands():
        if b["id"] == brand_id: return b
    return None

# ─── REPLICATE / R2 HELPERS ──────────────────────────────────

def replicate_create(model, input_data):
    for attempt in range(5):
        r = requests.post(f"https://api.replicate.com/v1/models/{model}/predictions",
            headers={"Authorization": f"Bearer {Config.REPLICATE_TOKEN}", "Content-Type": "application/json"},
            json={"input": input_data}, timeout=30)
        if r.status_code == 429:
            time.sleep(min(30 * (attempt + 1), 120)); continue
        r.raise_for_status()
        return r.json()["urls"]["get"]
    raise Exception("Replicate rate limit: 5 retries exhausted")

def replicate_poll(get_url, timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(get_url, headers={"Authorization": f"Bearer {Config.REPLICATE_TOKEN}"})
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "succeeded":
            output = data.get("output")
            return output[0] if isinstance(output, list) else output
        elif data.get("status") == "failed":
            raise RuntimeError(f"Replicate failed: {data.get('error')}")
        time.sleep(10)
    raise TimeoutError("Replicate timed out")

def get_s3_client():
    return boto3.client("s3", endpoint_url=Config.R2_ENDPOINT,
        aws_access_key_id=Config.R2_ACCESS_KEY, aws_secret_access_key=Config.R2_SECRET_KEY, region_name="auto")

def upload_to_r2(folder, filename, data, content_type):
    s3 = get_s3_client()
    key = f"{folder}/{filename}"
    if isinstance(data, str) and data.startswith("http"):
        r = requests.get(data, timeout=120); r.raise_for_status()
        body = r.content
        ct = content_type
        if body[:4] == b'\x89PNG': ct = "image/png"
        elif body[:2] == b'\xff\xd8': ct = "image/jpeg"
        elif body[:4] == b'RIFF': ct = "image/webp"
        s3.put_object(Bucket=Config.R2_BUCKET, Key=key, Body=body, ContentType=ct)
    elif isinstance(data, bytes):
        s3.put_object(Bucket=Config.R2_BUCKET, Key=key, Body=data, ContentType=content_type)
    return f"{Config.R2_PUBLIC_URL}/{key}"


# ═══════════════════════════════════════════════════════════════
# GRAPHICS PIPELINE PHASES
# ═══════════════════════════════════════════════════════════════

def gfx_generate_topic(brand):
    prompt = f"""You are a content strategist for "{brand.get('name','')}".
Brand guidelines: {brand.get('guidelines','')}
Tone: {brand.get('tone','')}

Generate ONE short, viral social media topic (5-15 words) that fits this brand.
The topic should inspire a single powerful image post with a quote overlay.
Return ONLY the topic text."""

    r = requests.post("https://api.openai.com/v1/chat/completions", headers={
        "Authorization": f"Bearer {Config.OPENAI_KEY}", "Content-Type": "application/json"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.9, "max_tokens": 100})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip().strip('"')

def gfx_generate_quote(brand, topic):
    prompt = f"""You are a quote writer for "{brand.get('name','')}".
Brand guidelines: {brand.get('guidelines','')}
Tone: {brand.get('tone','')}
Topic: {topic}

Write ONE powerful, original quote (10-25 words) for text overlay on a social media image.
No attribution, no quotation marks. Short, punchy, brand-voice perfect.
Return ONLY the quote text."""

    r = requests.post("https://api.openai.com/v1/chat/completions", headers={
        "Authorization": f"Bearer {Config.OPENAI_KEY}", "Content-Type": "application/json"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.85, "max_tokens": 100})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip().strip('"')

def gfx_build_image_prompt(brand, topic, quote):
    style = brand.get("visual_style", "cinematic, photorealistic")
    prompt = f"""You are an art director for "{brand.get('name','')}".
Visual style: {style}
Color palette: {brand.get('palette','')}
Tone: {brand.get('tone','')}
Topic: {topic}
Quote overlay: {quote}

Create a detailed image prompt (50-80 words) for an AI image model. The image:
- Stunning background for text overlay
- 9:16 vertical for social media
- NO text/letters/words in the image
- Areas of negative space for text placement
- Style: {style}

Return ONLY the prompt."""

    r = requests.post("https://api.openai.com/v1/chat/completions", headers={
        "Authorization": f"Bearer {Config.OPENAI_KEY}", "Content-Type": "application/json"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.8, "max_tokens": 200})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

def gfx_generate_image(prompt, model=None, aspect="9:16"):
    model = model or Config.IMAGE_MODEL
    params = {"prompt": prompt, "aspect_ratio": aspect}
    if "recraft" not in model: params["quality"] = "high"
    poll_url = replicate_create(model, params)
    return replicate_poll(poll_url, timeout=300)

def gfx_generate_captions(brand, topic, quote):
    accounts = brand.get("accounts", {})
    platforms = []
    if accounts.get("instagram"): platforms.append("Instagram: 400 chars, 8-12 hashtags")
    if accounts.get("facebook"): platforms.append("Facebook: 400 chars, conversational, 3-5 hashtags")
    if accounts.get("twitter"): platforms.append("X/Twitter: 280 chars, NO hashtags")
    if accounts.get("threads"): platforms.append("Threads: 500 chars, conversational")
    if accounts.get("tiktok"): platforms.append("TikTok: 300 chars, 3-5 hashtags")
    if accounts.get("pinterest"): platforms.append("Pinterest: 400-500 chars, 5-7 hashtags")
    if not platforms: platforms = ["Instagram: 400 chars, 8-12 hashtags"]

    prompt = f"""Social media manager for "{brand.get('name','')}".
Voice: {brand.get('tone','')}  Guidelines: {brand.get('guidelines','')}
Topic: {topic}  Quote on image: {quote}

Write captions for: {'; '.join(platforms)}
Minimal emojis. CTA on own line. Hashtags at end.
Return JSON with lowercase keys: {{"instagram":"...","facebook":"...","twitter":"...","threads":"...","tiktok":"...","pinterest":"..."}}
Only include listed platforms."""

    r = requests.post("https://api.openai.com/v1/chat/completions", headers={
        "Authorization": f"Bearer {Config.OPENAI_KEY}", "Content-Type": "application/json"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.8, "max_tokens": 1500})
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    raw = re.sub(r'^```json\s*\n?', '', text, flags=re.IGNORECASE)
    raw = re.sub(r'\n?```\s*$', '', raw).strip()
    try: return json.loads(raw)
    except: return {"instagram": quote}

def gfx_publish(brand, image_url, captions):
    accounts = brand.get("accounts", {})
    blotato_key = brand.get("blotato_key") or Config.BLOTATO_KEY
    if not blotato_key: return {}

    try:
        r = requests.post("https://backend.blotato.com/v2/media", headers={
            "Authorization": f"Bearer {blotato_key}", "Content-Type": "application/json"},
            json={"url": image_url})
        r.raise_for_status()
        media_url = r.json().get("url", image_url)
    except:
        media_url = image_url

    results = {}
    pmap = {"instagram": {}, "facebook": {"pageId": accounts.get("facebook_page")},
            "twitter": {}, "threads": {}, "tiktok": {"privacyLevel": "PUBLIC_TO_EVERYONE"},
            "pinterest": {"boardId": accounts.get("pinterest_board")}}

    for plat, extra in pmap.items():
        acct = accounts.get(plat)
        cap = captions.get(plat)
        if not acct or not cap: continue
        extra = {k: v for k, v in extra.items() if v}
        payload = {"post": {"accountId": acct, "content": {"text": cap, "mediaUrls": [media_url], "platform": plat},
                   "target": {"targetType": plat, **extra}}}
        try:
            r = requests.post("https://backend.blotato.com/v2/posts", headers={
                "Authorization": f"Bearer {blotato_key}", "Content-Type": "application/json"},
                json=payload, timeout=30)
            results[plat] = "ok" if r.ok else f"fail:{r.status_code}"
        except Exception as e:
            results[plat] = f"error:{e}"
    return results


# ═══════════════════════════════════════════════════════════════
# PIPELINE RUNNER
# ═══════════════════════════════════════════════════════════════

GFX_JOBS = {}

def _run_gfx(job_id, brand, image_model=None):
    job = GFX_JOBS[job_id]
    try:
        job.update({"status": "topic", "phase": "Generating topic..."})
        topic = gfx_generate_topic(brand)
        job["topic"] = topic

        job.update({"status": "quote", "phase": "Writing quote..."})
        quote = gfx_generate_quote(brand, topic)
        job["quote"] = quote

        job.update({"status": "prompt", "phase": "Building image prompt..."})
        img_prompt = gfx_build_image_prompt(brand, topic, quote)
        job["image_prompt"] = img_prompt

        job.update({"status": "image", "phase": "Generating image..."})
        image_url = gfx_generate_image(img_prompt, model=image_model)
        folder = f"graphics/{brand['id']}"
        fname = f"img_{job_id[:8]}_{int(time.time())}.png"
        r2_url = upload_to_r2(folder, fname, image_url, "image/png")
        job["image_url"] = r2_url

        job.update({"status": "captions", "phase": "Writing captions..."})
        captions = gfx_generate_captions(brand, topic, quote)
        job["captions"] = captions

        job.update({"status": "publishing", "phase": "Publishing..."})
        pub = gfx_publish(brand, r2_url, captions)
        job["publish_results"] = pub

        job.update({"status": "complete", "phase": "Done", "completed": datetime.now().isoformat()})

        gallery = load_json(GFX_GALLERY_FILE, [])
        gallery.insert(0, {"id": job_id, "brand_id": brand["id"], "brand_name": brand.get("name","?"),
            "topic": topic, "quote": quote, "image_prompt": img_prompt, "image_url": r2_url,
            "captions": captions, "publish_results": pub, "created": datetime.now().isoformat()})
        save_json(GFX_GALLERY_FILE, gallery[:500])

        runs = load_json(GFX_RUNS_FILE, [])
        runs.insert(0, {"id": job_id, "brand": brand.get("name","?"), "topic": topic,
            "status": "complete", "created": datetime.now().isoformat()})
        save_json(GFX_RUNS_FILE, runs[:200])

    except Exception as e:
        job.update({"status": "failed", "phase": f"Error: {e}", "error": str(e)})
        log.error(f"Graphics pipeline failed: {e}")


# ═══════════════════════════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════════════════════════

@router.get("/api/brands")
async def api_brands(): return get_brands()

@router.post("/api/brands")
async def api_create_brand(req: Request):
    body = await req.json()
    brands = get_brands()
    brand = {"id": str(uuid.uuid4())[:8], "name": body.get("name","New Brand"),
        "guidelines": body.get("guidelines",""), "tone": body.get("tone",""),
        "palette": body.get("palette",""), "visual_style": body.get("visual_style","cinematic, photorealistic"),
        "logo_url": body.get("logo_url",""), "accounts": body.get("accounts",{}),
        "blotato_key": body.get("blotato_key",""), "created": datetime.now().isoformat()}
    brands.append(brand)
    save_brands(brands)
    return brand

@router.put("/api/brands/{bid}")
async def api_update_brand(bid: str, req: Request):
    body = await req.json()
    brands = get_brands()
    for b in brands:
        if b["id"] == bid:
            b.update({k: v for k, v in body.items() if k != "id"})
            save_brands(brands)
            return b
    return JSONResponse({"error": "Not found"}, 404)

@router.delete("/api/brands/{bid}")
async def api_delete_brand(bid: str):
    save_brands([b for b in get_brands() if b["id"] != bid])
    return {"ok": True}

@router.post("/api/run")
async def api_run(req: Request):
    body = await req.json()
    brand_id = body.get("brand_id")
    run_all = body.get("run_all", False)
    image_model = body.get("image_model")
    brands = get_brands()
    if not brands: return JSONResponse({"error": "No brands"}, 400)
    targets = brands if run_all else [get_brand(brand_id) or brands[0]]
    jids = []
    for brand in targets:
        jid = str(uuid.uuid4())[:12]
        GFX_JOBS[jid] = {"id": jid, "brand_id": brand["id"], "brand_name": brand.get("name"),
            "status": "queued", "phase": "Queued", "created": datetime.now().isoformat()}
        threading.Thread(target=_run_gfx, args=(jid, brand, image_model), daemon=True).start()
        jids.append(jid)
        time.sleep(1)
    return {"job_ids": jids}

@router.get("/api/jobs")
async def api_jobs():
    return sorted(GFX_JOBS.values(), key=lambda j: j.get("created",""), reverse=True)[:50]

@router.get("/api/gallery")
async def api_gallery(): return load_json(GFX_GALLERY_FILE, [])[:100]

@router.delete("/api/gallery/{iid}")
async def api_del_gallery(iid: str):
    save_json(GFX_GALLERY_FILE, [g for g in load_json(GFX_GALLERY_FILE, []) if g.get("id") != iid])
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════
# DASHBOARD HTML
# ═══════════════════════════════════════════════════════════════

@router.get("/", response_class=HTMLResponse)
async def gfx_dashboard(): return GFX_HTML

GFX_HTML = r"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Graphics Engine</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;800&family=Rajdhani:wght@400;500;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
:root{--bg:#08080a;--bg2:#0c0c10;--bg3:#111118;--panel:#0d0d12;--bd:rgba(227,160,40,.12);--bd2:rgba(227,160,40,.06);--amb:#e3a028;--amb2:#c88a1a;--amblo:rgba(227,160,40,.05);--txt:#e3a028;--txtd:#7a5a18;--txtdd:#3a2a08;--grn:#28e060;--grn2:rgba(40,224,96,.08);--red:#e04028;--red2:rgba(224,64,40,.08);--blu:#28a0e0;--wht:#c8c0a8;--f1:'Orbitron',monospace;--f2:'Rajdhani',sans-serif;--f3:'Share Tech Mono',monospace}
*{margin:0;padding:0;box-sizing:border-box}html{font-size:clamp(14px,1.25vw,22px)}
body{background:var(--bg);color:var(--txt);font-family:var(--f3);min-height:100vh}
::-webkit-scrollbar{width:3px}::-webkit-scrollbar-thumb{background:var(--amb2)}
button{font-family:var(--f3);cursor:pointer}input,select,textarea{font-family:var(--f3)}a{color:var(--amb)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
@keyframes scan{0%{top:-100%}100%{top:100%}}

.top{background:var(--bg2);border-bottom:1px solid var(--bd);padding:.7em 1.2em;display:flex;align-items:center;justify-content:space-between}
.top h1{font-family:var(--f1);font-size:.75em;font-weight:800;color:var(--amb);letter-spacing:.15em}
.top a{font-size:.6em;color:var(--txtd);text-decoration:none;letter-spacing:.1em}.top a:hover{color:var(--amb)}
.wrap{max-width:72em;margin:0 auto;padding:1em}
.tabs{display:flex;gap:2px;border-bottom:1px solid var(--bd);margin-bottom:1em;overflow-x:auto}
.tab{font-family:var(--f1);font-size:.6em;color:var(--txtd);background:none;border:none;border-bottom:2px solid transparent;padding:.7em 1em;letter-spacing:.12em;white-space:nowrap}
.tab:hover{color:var(--amb)}.tab.on{color:var(--amb);border-bottom-color:var(--amb)}
.page{display:none}.page.on{display:block}
.lbl{font-size:.65em;color:var(--txtd);text-transform:uppercase;letter-spacing:.15em;margin-bottom:.3em}
.inp{width:100%;padding:.6em .8em;background:var(--bg);border:1px solid var(--bd2);color:var(--amb);font-size:.85em;outline:none;font-family:var(--f3)}
.inp:focus{border-color:var(--amb);box-shadow:0 0 6px rgba(227,160,40,.1)}
textarea.inp{resize:vertical;min-height:3.5em;line-height:1.5}
select.inp{-webkit-appearance:none;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23e3a028'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center;padding-right:28px;cursor:pointer;background-color:var(--bg)}
.btn{padding:.65em 1.2em;font-family:var(--f1);font-size:.6em;font-weight:600;letter-spacing:.15em;border:none}
.btn-go{background:var(--amb);color:var(--bg)}.btn-go:hover{box-shadow:0 0 12px rgba(227,160,40,.3)}
.btn-out{background:none;border:1px solid var(--bd);color:var(--amb)}.btn-out:hover{background:var(--amblo)}
.btn-red{background:var(--red2);border:1px solid rgba(224,64,40,.15);color:var(--red)}.btn-red:hover{opacity:.8}
.btn-grn{background:var(--grn2);border:1px solid rgba(40,224,96,.15);color:var(--grn)}
.row{display:flex;gap:.8em;flex-wrap:wrap}.col{flex:1;min-width:14em}
.card{background:var(--panel);border:1px solid var(--bd2);padding:.8em;margin-bottom:.5em}
.card-t{font-family:var(--f1);font-size:.65em;font-weight:600;color:var(--amb);letter-spacing:.1em;margin-bottom:.5em;display:flex;align-items:center;gap:.5em}
.card-t::before{content:'';width:.2em;height:.7em;background:var(--amb)}
.fi{margin-bottom:.55em}
.sm{background:var(--grn2);border:1px solid rgba(40,224,96,.15);padding:.4em .7em;font-size:.65em;color:var(--grn);margin-bottom:.5em}

/* Brand cards */
.bc{background:var(--panel);border:1px solid var(--bd2);padding:.7em;margin-bottom:.4em;display:flex;align-items:center;gap:.7em}
.bc-color{width:2em;height:2em;border:1px solid var(--bd);flex-shrink:0}
.bc-info{flex:1}
.bc-name{font-family:var(--f1);font-size:.7em;font-weight:600;letter-spacing:.1em;color:var(--wht)}
.bc-tone{font-size:.55em;color:var(--txtd);margin-top:.1em;letter-spacing:.08em}
.bc-acts{display:flex;gap:3px;margin-top:.2em;flex-wrap:wrap}
.bc-dot{font-size:.45em;padding:.1em .35em;background:var(--amblo);border:1px solid var(--bd);color:var(--txtd);letter-spacing:.05em}

/* Gallery */
.gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(14em,1fr));gap:.6em}
.gi{background:var(--panel);border:1px solid var(--bd2);overflow:hidden;position:relative}
.gi img{width:100%;display:block;cursor:pointer}
.gi-info{padding:.5em}
.gi-q{font-size:.65em;color:var(--wht);line-height:1.4;margin-bottom:.2em;font-style:italic}
.gi-brand{font-size:.5em;color:var(--amb);letter-spacing:.08em}
.gi-meta{font-size:.45em;color:var(--txtd);letter-spacing:.06em;margin-top:.15em}
.gi-acts{position:absolute;top:4px;right:4px;display:flex;gap:3px}
.gi-btn{background:rgba(8,8,10,.85);border:1px solid var(--bd);color:var(--amb);font-size:.5em;padding:.2em .4em;cursor:pointer}
.gi-btn:hover{background:var(--amblo)}

/* Jobs */
.job{background:var(--panel);border:1px solid var(--bd2);padding:.55em .7em;margin-bottom:3px;display:flex;align-items:center;gap:.5em;position:relative;overflow:hidden}
.jdot{width:.4em;height:.4em;flex-shrink:0}
.jdot.q{background:var(--txtdd)}.jdot.r{background:var(--blu);animation:pulse 1.2s infinite}.jdot.c{background:var(--grn)}.jdot.f{background:var(--red)}
.job.active{border-left:3px solid var(--blu)}
.job.active::after{content:'';position:absolute;top:0;left:0;width:100%;height:2px;background:linear-gradient(90deg,transparent,var(--blu),transparent);animation:scan 2s linear infinite}

/* Modal */
.modal-bg{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.88);z-index:999;display:none;align-items:center;justify-content:center;flex-direction:column}
.modal-bg.on{display:flex}
.modal-x{position:absolute;top:1em;right:1em;background:none;border:none;color:var(--amb);font-size:1.2em;cursor:pointer;z-index:1000}
.modal-img{max-width:90vw;max-height:80vh;display:block}
.modal-info{background:var(--panel);padding:.5em .7em;font-size:.55em;color:var(--wht);max-width:90vw;word-break:break-all;margin-top:.3em}

@media(max-width:768px){.row{flex-direction:column}.gal{grid-template-columns:1fr 1fr}.col{min-width:100%}}
</style></head><body>

<div class="top">
  <h1>◈ GRAPHICS ENGINE</h1>
  <a href="/">← REACTOR</a>
</div>
<div class="wrap">
<div class="tabs">
  <button class="tab on" onclick="nav('run',this)">▶ RUN</button>
  <button class="tab" onclick="nav('brands',this)">◉ BRANDS</button>
  <button class="tab" onclick="nav('gallery',this)">▤ GALLERY</button>
  <button class="tab" onclick="nav('jobs',this)">⚡ JOBS</button>
</div>

<!-- ═══ RUN TAB ═══ -->
<div class="page on" id="p-run">
  <div class="card">
    <div class="card-t">EXECUTE GRAPHICS PIPELINE</div>
    <div class="row">
      <div class="col">
        <div class="fi"><div class="lbl">BRAND</div>
          <select class="inp" id="r-brand"><option value="">Loading...</option></select>
        </div>
        <div class="fi"><div class="lbl">IMAGE MODEL</div>
          <select class="inp" id="r-model">
            <option value="black-forest-labs/flux-1.1-pro">Flux 1.1 Pro ~$0.04</option>
            <option value="google/nano-banana-pro">Nano Banana Pro ~$0.10</option>
            <option value="google/nano-banana">Nano Banana ~$0.02</option>
            <option value="xai/grok-imagine-image">Grok Aurora ~$0.07</option>
            <option value="bytedance/seedream-4.5">Seedream 4.5 ~$0.03</option>
            <option value="black-forest-labs/flux-schnell">Flux Schnell ~$0.003</option>
            <option value="ideogram-ai/ideogram-v3-quality">Ideogram v3 Q ~$0.08</option>
            <option value="ideogram-ai/ideogram-v3-turbo">Ideogram v3 T ~$0.02</option>
            <option value="recraft-ai/recraft-v3">Recraft v3 ~$0.04</option>
            <option value="google-deepmind/imagen-4-preview">Imagen 4 ~$0.04</option>
          </select>
        </div>
      </div>
      <div class="col" style="display:flex;flex-direction:column;justify-content:flex-end;gap:.4em">
        <button class="btn btn-go" style="width:100%" onclick="runOne()">▶ RUN SELECTED BRAND</button>
        <button class="btn btn-out" style="width:100%" onclick="runAll()">◈ RUN ALL BRANDS</button>
      </div>
    </div>
  </div>
  <div id="r-live"></div>
</div>

<!-- ═══ BRANDS TAB ═══ -->
<div class="page" id="p-brands">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.6em">
    <span style="font-family:var(--f1);font-size:.65em;letter-spacing:.15em;color:var(--txtd)">BRAND PROFILES</span>
    <button class="btn btn-out" onclick="showAddBrand()">+ ADD BRAND</button>
  </div>
  <div id="b-list"></div>
  <div id="b-form" style="display:none">
    <div class="card">
      <div class="card-t" id="bf-title">NEW BRAND</div>
      <input type="hidden" id="bf-id">
      <div class="row">
        <div class="col">
          <div class="fi"><div class="lbl">BRAND NAME</div><input class="inp" id="bf-name" placeholder="God's Knights"></div>
          <div class="fi"><div class="lbl">TONE / VOICE</div><input class="inp" id="bf-tone" placeholder="commanding, disciplined, masculine"></div>
          <div class="fi"><div class="lbl">COLOR PALETTE</div><input class="inp" id="bf-palette" placeholder="dark amber, steel grey, midnight blue"></div>
          <div class="fi"><div class="lbl">VISUAL STYLE</div><input class="inp" id="bf-style" placeholder="cinematic, photorealistic, dark atmosphere"></div>
          <div class="fi"><div class="lbl">LOGO URL</div><input class="inp" id="bf-logo" placeholder="https://..."></div>
        </div>
        <div class="col">
          <div class="fi"><div class="lbl">BRAND GUIDELINES</div><textarea class="inp" id="bf-guide" placeholder="Biblical masculinity brand. Medieval knight aesthetic. Dark, commanding, no-nonsense..."></textarea></div>
          <div class="fi"><div class="lbl">BLOTATO API KEY (brand-specific, or leave blank for global)</div><input class="inp" id="bf-bkey" placeholder="Optional override"></div>
        </div>
      </div>
      <div class="card" style="margin-top:.4em">
        <div class="card-t">SOCIAL ACCOUNTS (Blotato IDs)</div>
        <div class="row">
          <div class="col">
            <div class="fi"><div class="lbl">INSTAGRAM</div><input class="inp" id="bf-ig" placeholder="acct_..."></div>
            <div class="fi"><div class="lbl">FACEBOOK</div><input class="inp" id="bf-fb" placeholder="acct_..."></div>
            <div class="fi"><div class="lbl">FACEBOOK PAGE</div><input class="inp" id="bf-fbp" placeholder="page_..."></div>
            <div class="fi"><div class="lbl">TIKTOK</div><input class="inp" id="bf-tt" placeholder="acct_..."></div>
          </div>
          <div class="col">
            <div class="fi"><div class="lbl">X / TWITTER</div><input class="inp" id="bf-tw" placeholder="acct_..."></div>
            <div class="fi"><div class="lbl">THREADS</div><input class="inp" id="bf-th" placeholder="acct_..."></div>
            <div class="fi"><div class="lbl">PINTEREST</div><input class="inp" id="bf-pn" placeholder="acct_..."></div>
            <div class="fi"><div class="lbl">PINTEREST BOARD</div><input class="inp" id="bf-pnb" placeholder="board_..."></div>
          </div>
        </div>
      </div>
      <div style="display:flex;gap:.4em;margin-top:.6em">
        <button class="btn btn-go" onclick="saveBrand()">SAVE BRAND</button>
        <button class="btn btn-out" onclick="cancelBrand()">CANCEL</button>
        <button class="btn btn-red" id="bf-del" style="display:none;margin-left:auto" onclick="deleteBrand()">DELETE</button>
      </div>
    </div>
  </div>
</div>

<!-- ═══ GALLERY TAB ═══ -->
<div class="page" id="p-gallery">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.6em">
    <span style="font-family:var(--f1);font-size:.65em;letter-spacing:.15em;color:var(--txtd)">GENERATED IMAGES</span>
    <span id="g-count" style="font-size:.55em;color:var(--txtdd)"></span>
  </div>
  <div class="gal" id="g-grid"></div>
</div>

<!-- ═══ JOBS TAB ═══ -->
<div class="page" id="p-jobs">
  <div style="font-family:var(--f1);font-size:.65em;letter-spacing:.15em;color:var(--txtd);margin-bottom:.5em">PIPELINE JOBS</div>
  <div id="j-list"></div>
</div>

<!-- ═══ MODAL ═══ -->
<div class="modal-bg" id="modal" onclick="if(event.target===this)closeModal()">
  <button class="modal-x" onclick="closeModal()">✕</button>
  <img class="modal-img" id="modal-img">
  <div class="modal-info" id="modal-info"></div>
</div>

</div>
<script>
const $=id=>document.getElementById(id);
const API='/graphics/api';
let BRANDS=[],EDITING=null;

function nav(p,btn){document.querySelectorAll('.page').forEach(e=>e.classList.remove('on'));document.querySelectorAll('.tab').forEach(b=>b.classList.remove('on'));$(('p-'+p)).classList.add('on');if(btn)btn.classList.add('on');if(p==='brands')loadBrands();if(p==='gallery')loadGallery();if(p==='jobs')loadJobs();}

// ─── BRANDS ──────────────────────────────────────────────────
async function loadBrands(){
  BRANDS=await(await fetch(API+'/brands')).json();
  renderBrands();populateBrandDropdown();
}
function renderBrands(){
  const el=$('b-list');
  if(!BRANDS.length){el.innerHTML='<div class="card" style="text-align:center;color:var(--txtd);font-size:.7em;padding:2em">No brands yet. Click + ADD BRAND to create one.</div>';return;}
  el.innerHTML=BRANDS.map(b=>{
    const acts=b.accounts||{};
    const dots=Object.keys(acts).filter(k=>acts[k]&&!k.includes('page')&&!k.includes('board')).map(k=>`<span class="bc-dot">${k}</span>`).join('');
    const col=b.palette?b.palette.split(',')[0].trim():'#e3a028';
    return`<div class="bc" onclick="editBrand('${b.id}')" style="cursor:pointer"><div class="bc-color" style="background:${col}"></div><div class="bc-info"><div class="bc-name">${b.name}</div><div class="bc-tone">${b.tone||'No tone set'}</div><div class="bc-acts">${dots||'<span class="bc-dot" style="color:var(--red)">no accounts</span>'}</div></div></div>`;
  }).join('');
}
function populateBrandDropdown(){
  const sel=$('r-brand');
  sel.innerHTML=BRANDS.map(b=>`<option value="${b.id}">${b.name}</option>`).join('')||'<option value="">No brands</option>';
}
function showAddBrand(){EDITING=null;$('bf-title').textContent='NEW BRAND';$('bf-id').value='';$('bf-del').style.display='none';
  ['bf-name','bf-tone','bf-palette','bf-style','bf-logo','bf-guide','bf-bkey','bf-ig','bf-fb','bf-fbp','bf-tt','bf-tw','bf-th','bf-pn','bf-pnb'].forEach(id=>$(id).value='');
  $('b-form').style.display='block';$('b-list').style.display='none';}
function editBrand(id){
  const b=BRANDS.find(x=>x.id===id);if(!b)return;EDITING=id;
  $('bf-title').textContent='EDIT: '+b.name;$('bf-id').value=id;$('bf-del').style.display='block';
  $('bf-name').value=b.name||'';$('bf-tone').value=b.tone||'';$('bf-palette').value=b.palette||'';
  $('bf-style').value=b.visual_style||'';$('bf-logo').value=b.logo_url||'';$('bf-guide').value=b.guidelines||'';
  $('bf-bkey').value=b.blotato_key||'';
  const a=b.accounts||{};$('bf-ig').value=a.instagram||'';$('bf-fb').value=a.facebook||'';
  $('bf-fbp').value=a.facebook_page||'';$('bf-tt').value=a.tiktok||'';$('bf-tw').value=a.twitter||'';
  $('bf-th').value=a.threads||'';$('bf-pn').value=a.pinterest||'';$('bf-pnb').value=a.pinterest_board||'';
  $('b-form').style.display='block';$('b-list').style.display='none';
}
function cancelBrand(){$('b-form').style.display='none';$('b-list').style.display='block';}
async function saveBrand(){
  const data={name:$('bf-name').value,tone:$('bf-tone').value,palette:$('bf-palette').value,
    visual_style:$('bf-style').value,logo_url:$('bf-logo').value,guidelines:$('bf-guide').value,
    blotato_key:$('bf-bkey').value,
    accounts:{instagram:$('bf-ig').value,facebook:$('bf-fb').value,facebook_page:$('bf-fbp').value,
      tiktok:$('bf-tt').value,twitter:$('bf-tw').value,threads:$('bf-th').value,
      pinterest:$('bf-pn').value,pinterest_board:$('bf-pnb').value}};
  if(EDITING){await fetch(API+'/brands/'+EDITING,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});}
  else{await fetch(API+'/brands',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});}
  cancelBrand();loadBrands();
}
async function deleteBrand(){
  if(!EDITING||!confirm('Delete this brand?'))return;
  await fetch(API+'/brands/'+EDITING,{method:'DELETE'});
  cancelBrand();loadBrands();
}

// ─── RUN ─────────────────────────────────────────────────────
async function runOne(){
  const bid=$('r-brand').value;const model=$('r-model').value;
  if(!bid){alert('Select a brand first');return;}
  const r=await(await fetch(API+'/run',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({brand_id:bid,image_model:model})})).json();
  if(r.error){alert(r.error);return;}
  pollJobs(r.job_id?[r.job_id]:r.job_ids);
}
async function runAll(){
  const model=$('r-model').value;
  const r=await(await fetch(API+'/run',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({run_all:true,image_model:model})})).json();
  if(r.error){alert(r.error);return;}
  pollJobs(r.job_ids||[]);
}
let POLL_IDS=[];
function pollJobs(ids){POLL_IDS=ids;_poll();}
async function _poll(){
  if(!POLL_IDS.length)return;
  const jobs=await(await fetch(API+'/jobs')).json();
  const tracked=jobs.filter(j=>POLL_IDS.includes(j.id));
  let html='';
  tracked.forEach(j=>{
    const sc=j.status==='complete'?'c':j.status==='failed'?'f':j.status==='queued'?'q':'r';
    const active=!['complete','failed','queued'].includes(j.status);
    html+=`<div class="job${active?' active':''}"><span class="jdot ${sc}"></span><div style="flex:1"><div style="font-family:var(--f1);font-size:.6em;letter-spacing:.1em;color:var(--wht)">${j.brand_name||'?'}</div><div style="font-size:.55em;color:var(--txtd);margin-top:.1em">${j.phase||j.status}</div></div>`;
    if(j.image_url)html+=`<img src="${j.image_url}" style="width:2.5em;height:2.5em;object-fit:cover;border:1px solid var(--bd)">`;
    if(j.quote)html+=`<div style="flex:1;font-size:.55em;color:var(--wht);font-style:italic">"${j.quote}"</div>`;
    html+=`</div>`;
  });
  $('r-live').innerHTML=html;
  const allDone=tracked.every(j=>j.status==='complete'||j.status==='failed');
  if(!allDone)setTimeout(_poll,2000);
  else{loadGallery();}
}

// ─── GALLERY ─────────────────────────────────────────────────
async function loadGallery(){
  const items=await(await fetch(API+'/gallery')).json();
  $('g-count').textContent=items.length+' images';
  if(!items.length){$('g-grid').innerHTML='<div style="grid-column:1/-1;text-align:center;color:var(--txtd);font-size:.7em;padding:3em">No images yet. Run the pipeline to generate content.</div>';return;}
  $('g-grid').innerHTML=items.map(g=>`<div class="gi"><img src="${g.image_url}" loading="lazy" onclick="openModal('${g.image_url}','${(g.quote||'').replace(/'/g,"\\'")}','${(g.brand_name||'').replace(/'/g,"\\'")}','${(g.image_prompt||'').replace(/'/g,"\\'").substring(0,200)}')"><div class="gi-acts"><a class="gi-btn" href="${g.image_url}" download target="_blank">⬇</a><span class="gi-btn" onclick="event.stopPropagation();delGallery('${g.id}')">✕</span></div><div class="gi-info"><div class="gi-q">"${g.quote||''}"</div><div class="gi-brand">${g.brand_name||'?'}</div><div class="gi-meta">${g.topic||''}</div></div></div>`).join('');
}
async function delGallery(id){
  if(!confirm('Delete?'))return;
  await fetch(API+'/gallery/'+id,{method:'DELETE'});loadGallery();
}

// ─── JOBS ────────────────────────────────────────────────────
async function loadJobs(){
  const jobs=await(await fetch(API+'/jobs')).json();
  if(!jobs.length){$('j-list').innerHTML='<div style="text-align:center;color:var(--txtd);font-size:.7em;padding:2em">No jobs yet.</div>';return;}
  $('j-list').innerHTML=jobs.map(j=>{
    const sc=j.status==='complete'?'c':j.status==='failed'?'f':j.status==='queued'?'q':'r';
    return`<div class="job"><span class="jdot ${sc}"></span><div style="flex:1"><div style="font-family:var(--f2);font-size:.8em;font-weight:600;color:var(--wht)">${j.brand_name||'?'}</div><div style="font-size:.5em;color:var(--txtd);margin-top:.1em">${j.phase||j.status} · ${j.topic||''}</div></div>${j.error?`<div style="font-size:.5em;color:var(--red);max-width:12em;word-break:break-all">${j.error}</div>`:''}${j.image_url?`<img src="${j.image_url}" style="width:2.5em;height:2.5em;object-fit:cover;border:1px solid var(--bd)">`:''}
    </div>`;
  }).join('');
}

// ─── MODAL ───────────────────────────────────────────────────
function openModal(url,quote,brand,prompt){
  $('modal-img').src=url;
  $('modal-info').innerHTML=`<b>${brand}</b> — "${quote}"<br><span style="color:var(--txtd)">${prompt}</span>`;
  $('modal').classList.add('on');
}
function closeModal(){$('modal').classList.remove('on');}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();});

// ─── INIT ────────────────────────────────────────────────────
loadBrands();
</script></body></html>"""
