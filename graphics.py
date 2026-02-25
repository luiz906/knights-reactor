"""
Knights Reactor — Graphics Engine v2
======================================
Multi-brand image content pipeline with FULL UI control.
Each phase is visible and editable before proceeding.

Flow: Brand → Topic (edit) → Quote (edit) → Prompt (edit) → Image (preview) → Captions (edit) → Publish

Mounted at /graphics as a FastAPI sub-application.
"""

import json, os, time, uuid, threading, re, logging
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

import requests
import boto3

from config import Config, DATA_DIR, log

glog = logging.getLogger("graphics")
gfx_app = FastAPI(title="Graphics Engine")

# ─── STORAGE ──────────────────────────────────────────────────
BRANDS_DIR = DATA_DIR / "brands"
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


# ─── INDIVIDUAL PHASE ENDPOINTS ──────────────────────────────
# Each phase is its own API call so the UI controls the flow

@gfx_app.get("/api/brands")
async def api_brands():
    return get_brands()

@gfx_app.post("/api/phase/topic")
async def api_phase_topic(req: Request):
    """Generate a topic for the brand. Returns topic text."""
    body = await req.json()
    brand_id = body.get("brand_id", "")
    brand = next((b for b in get_brands() if b["id"] == brand_id), None)
    if not brand: return JSONResponse({"error": "Brand not found"}, 400)
    try:
        topic = _gpt(
            f"Generate ONE viral image post topic for '{brand['name']}'. "
            f"Brand: {brand.get('guidelines','')}. Themes: {brand.get('themes','')}. "
            "Return ONLY the topic as a short phrase (5-12 words).", max_tok=80)
        return {"topic": topic}
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)

@gfx_app.post("/api/phase/quote")
async def api_phase_quote(req: Request):
    """Generate a quote from the topic."""
    body = await req.json()
    brand = next((b for b in get_brands() if b["id"] == body.get("brand_id")), {})
    topic = body.get("topic", "")
    try:
        quote = _gpt(
            f"Write a powerful quote for an image post about: {topic}. "
            f"Brand: {brand.get('name','')}. Tone: {brand.get('tone','Bold')}. "
            "Max 15 words. Punchy, memorable, shareable. Return ONLY the quote.", max_tok=60)
        return {"quote": quote}
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)

@gfx_app.post("/api/phase/prompt")
async def api_phase_prompt(req: Request):
    """Build an image generation prompt."""
    body = await req.json()
    brand = next((b for b in get_brands() if b["id"] == body.get("brand_id")), {})
    topic = body.get("topic", "")
    quote = body.get("quote", "")
    try:
        prompt = _gpt(
            f"Create a detailed image generation prompt for: '{topic}'. "
            f"Style: {brand.get('visual_style','cinematic')}. Context: {brand.get('guidelines','')}. "
            "Social media post background. Include lighting, composition, mood. 1-3 sentences max.", max_tok=250)
        return {"prompt": prompt}
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)

@gfx_app.post("/api/phase/image")
async def api_phase_image(req: Request):
    """Generate the image. Returns job_id for polling."""
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
            # Upload to R2
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

@gfx_app.get("/api/phase/image/{job_id}")
async def api_poll_image(job_id: str):
    """Poll image generation status."""
    return JOBS.get(job_id, {"status": "unknown"})

@gfx_app.post("/api/phase/captions")
async def api_phase_captions(req: Request):
    """Generate platform captions."""
    body = await req.json()
    brand = next((b for b in get_brands() if b["id"] == body.get("brand_id")), {})
    topic = body.get("topic", "")
    quote = body.get("quote", "")
    try:
        text = _gpt(
            f"Create social media captions for an image post. Brand: {brand.get('name','')}. "
            f"Tone: {brand.get('tone','Bold')}. Topic: {topic}. Quote on image: {quote}. "
            "Return JSON: {\"instagram\":\"400 chars 8-12 hashtags\",\"facebook\":\"300 chars 3-5 hashtags\","
            "\"tiktok\":\"200 chars 3-5 hashtags\",\"twitter\":\"280 chars no hashtags\",\"threads\":\"400 chars\"}. "
            "ONLY valid JSON.", temp=0.8, max_tok=1500)
        raw = re.sub(r'^```json\s*\n?', '', text, flags=re.IGNORECASE)
        raw = re.sub(r'\n?```\s*$', '', raw).strip()
        return {"captions": json.loads(raw)}
    except json.JSONDecodeError:
        return {"captions": {"instagram": topic, "facebook": topic, "twitter": topic, "threads": topic, "tiktok": topic}}
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)

@gfx_app.post("/api/save")
async def api_save(req: Request):
    """Save completed post to gallery."""
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
    }
    gallery.insert(0, entry)
    save_json(GFX_GALLERY_FILE, gallery[:500])
    return {"status": "saved", "id": entry["id"]}

@gfx_app.get("/api/gallery")
async def api_gallery():
    return load_json(GFX_GALLERY_FILE, [])[:100]

@gfx_app.delete("/api/gallery/{item_id}")
async def api_del_gallery(item_id: str):
    g = load_json(GFX_GALLERY_FILE, [])
    save_json(GFX_GALLERY_FILE, [x for x in g if x.get("id") != item_id])
    return {"status": "deleted"}


# ─── DASHBOARD ────────────────────────────────────────────────
@gfx_app.get("/", response_class=HTMLResponse)
async def gfx_page():
    return GFX_HTML

GFX_HTML = r"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Graphics Engine</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;800&family=Rajdhani:wght@400;500;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
:root{--bg:#08080a;--bg2:#0c0c10;--bg3:#111118;--panel:#0d0d12;--bd:rgba(227,160,40,.12);--bd2:rgba(227,160,40,.06);--amb:#e3a028;--amb2:#c88a1a;--amblo:rgba(227,160,40,.05);--txt:#e3a028;--txtd:#7a5a18;--txtdd:#3a2a08;--grn:#28e060;--grn2:rgba(40,224,96,.08);--red:#e04028;--red2:rgba(224,64,40,.08);--blu:#28a0e0;--blu2:rgba(40,160,224,.08);--wht:#c8c0a8;--f1:'Orbitron',monospace;--f2:'Rajdhani',sans-serif;--f3:'Share Tech Mono',monospace}
*{margin:0;padding:0;box-sizing:border-box}body{background:var(--bg);color:var(--txt);font-family:var(--f3);min-height:100vh}
::-webkit-scrollbar{width:3px}::-webkit-scrollbar-thumb{background:var(--amb2)}::-webkit-scrollbar-track{background:var(--bg)}
.wrap{max-width:1100px;margin:0 auto;padding:12px}
.hdr{display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--bd);margin-bottom:12px}
.hdr h1{font-family:var(--f1);font-size:.85em;font-weight:800;letter-spacing:.15em}
.hdr a{color:var(--txtd);font-size:.65em;text-decoration:none;letter-spacing:.1em}.hdr a:hover{color:var(--amb)}
.tabs{display:flex;gap:2px;border-bottom:1px solid var(--bd2);margin-bottom:12px}
.tab{font-family:var(--f1);font-size:.55em;color:var(--txtd);background:none;border:none;border-bottom:2px solid transparent;padding:.6em .8em;cursor:pointer;letter-spacing:.12em}.tab:hover{color:var(--amb)}.tab.on{color:var(--amb);border-bottom-color:var(--amb)}
.page{display:none}.page.on{display:block}
.card{background:var(--panel);border:1px solid var(--bd2);padding:.8em;margin-bottom:.5em}
.card-t{font-family:var(--f1);font-size:.6em;font-weight:600;letter-spacing:.12em;color:var(--txtd);margin-bottom:.5em;display:flex;align-items:center;gap:.5em}
.card-t::before{content:'';width:3px;height:.8em;background:var(--amb)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:.8em}
@media(max-width:600px){.row{grid-template-columns:1fr}}
.fi{margin-bottom:.5em}.lbl{font-size:.6em;color:var(--txtd);letter-spacing:.1em;margin-bottom:.2em;text-transform:uppercase}
.inp{width:100%;padding:.5em .6em;background:var(--bg);border:1px solid var(--bd2);color:var(--amb);font-family:var(--f3);font-size:.85em;outline:none;border-radius:0}
.inp:focus{border-color:var(--amb);box-shadow:0 0 6px rgba(227,160,40,.1)}
select.inp{-webkit-appearance:none;appearance:none;cursor:pointer;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23e3a028'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center;padding-right:28px}
textarea.inp{min-height:3.5em;resize:vertical;line-height:1.5}
.btn{font-family:var(--f1);font-size:.55em;padding:.5em 1em;border:none;cursor:pointer;letter-spacing:.12em;transition:all .15s}
.btn-go{background:var(--amb);color:var(--bg)}.btn-go:hover{box-shadow:0 0 12px rgba(227,160,40,.35)}
.btn-out{background:none;border:1px solid var(--bd);color:var(--amb)}.btn-out:hover{background:var(--amblo)}
.btn-grn{background:var(--grn);color:var(--bg)}.btn-grn:hover{box-shadow:0 0 12px rgba(40,224,96,.3)}
.btn-red{background:var(--red2);border:1px solid rgba(224,64,40,.15);color:var(--red)}
.btn-blu{background:var(--blu2);border:1px solid rgba(40,160,224,.15);color:var(--blu)}
.btn:disabled{opacity:.3;cursor:not-allowed}

/* PHASE STEPS */
.step{background:var(--panel);border:1px solid var(--bd2);padding:1em;margin-bottom:.5em;border-left:3px solid var(--txtdd);transition:all .3s}
.step.active{border-left-color:var(--blu);background:rgba(40,160,224,.02)}
.step.done{border-left-color:var(--grn);background:rgba(40,224,96,.015)}
.step.locked{opacity:.35;pointer-events:none}
.step-head{display:flex;align-items:center;gap:.6em;margin-bottom:.5em}
.step-num{font-family:var(--f1);font-size:.55em;font-weight:800;width:1.6em;height:1.6em;display:flex;align-items:center;justify-content:center;border:1px solid var(--bd);color:var(--txtd)}
.step.active .step-num{border-color:var(--blu);color:var(--blu)}
.step.done .step-num{border-color:var(--grn);color:var(--grn);background:var(--grn2)}
.step-title{font-family:var(--f1);font-size:.65em;font-weight:600;letter-spacing:.12em}
.step.active .step-title{color:var(--blu)}
.step.done .step-title{color:var(--grn)}
.step-actions{display:flex;gap:6px;margin-top:.6em;flex-wrap:wrap}
.step-status{font-size:.6em;color:var(--txtd);margin-top:.3em}
.spin{display:inline-block;animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

/* IMAGE PREVIEW */
.img-preview{border:1px solid var(--amb);padding:3px;background:var(--bg);margin:.5em 0;max-width:400px}
.img-preview img{width:100%;display:block}

/* CAPTIONS */
.cap-block{border:1px solid var(--bd2);padding:.5em;margin-bottom:.4em}
.cap-plat{font-family:var(--f1);font-size:.5em;letter-spacing:.12em;color:var(--txtd);margin-bottom:.25em;text-transform:uppercase}
.cap-text{width:100%;min-height:3em;padding:.4em;background:var(--bg);border:1px solid var(--bd2);color:var(--wht);font-family:var(--f3);font-size:.8em;resize:vertical;outline:none}
.cap-text:focus{border-color:var(--amb)}

/* GALLERY */
.gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px}
.gi{background:var(--panel);border:1px solid var(--bd2);overflow:hidden;position:relative;cursor:pointer;transition:border-color .15s}
.gi img{width:100%;display:block}.gi:hover{border-color:var(--amb)}
.gi-info{padding:5px 8px}.gi-topic{font-size:.65em;color:var(--wht);font-family:var(--f2);font-weight:600}
.gi-meta{font-size:.5em;color:var(--txtd);margin-top:2px}
.gi-quote{font-size:.55em;color:var(--txtdd);margin-top:2px;font-style:italic}
.gi-del{position:absolute;top:4px;right:4px;background:rgba(8,8,10,.85);border:1px solid var(--bd);color:var(--red);font-size:.55em;padding:2px 6px;cursor:pointer;display:none}
.gi:hover .gi-del{display:block}

/* MODAL */
.mbg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:999;align-items:center;justify-content:center;flex-direction:column;padding:20px}
.mbg.show{display:flex}
.mimg{max-width:90vw;max-height:70vh;object-fit:contain;border:1px solid var(--amb)}
.mx{position:fixed;top:12px;right:16px;background:none;border:none;color:var(--amb);font-size:1.5em;cursor:pointer;z-index:1000}
.mdet{color:var(--wht);font-size:.7em;margin-top:10px;text-align:center;max-width:80vw;line-height:1.6}
.mdet b{color:var(--amb);font-family:var(--f1);font-size:.85em;letter-spacing:.08em}
</style></head><body>
<div class="wrap">
<div class="hdr"><h1>⬡ GRAPHICS ENGINE</h1><a href="/">← VIDEO PIPELINE</a></div>

<div class="tabs">
<button class="tab on" onclick="gN('create',this)">✦ CREATE</button>
<button class="tab" onclick="gN('gallery',this)">◉ GALLERY</button>
</div>

<!-- ═══ CREATE TAB — Step-by-step pipeline ═══ -->
<div class="page on" id="p-create">

  <!-- SETUP -->
  <div class="card">
    <div class="card-t">SETUP</div>
    <div class="row">
      <div class="fi"><div class="lbl">BRAND</div><select class="inp" id="s-brand"></select></div>
      <div class="fi"><div class="lbl">ASPECT RATIO</div><select class="inp" id="s-aspect">
        <option value="1:1">1:1 Square</option><option value="9:16">9:16 Vertical</option>
        <option value="4:5">4:5 Portrait</option><option value="16:9">16:9 Landscape</option>
      </select></div>
    </div>
    <div class="fi"><div class="lbl">IMAGE MODEL</div><select class="inp" id="s-model">
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

  <!-- STEP 1: TOPIC -->
  <div class="step active" id="st-1">
    <div class="step-head"><div class="step-num">1</div><div class="step-title">TOPIC</div></div>
    <div class="fi"><div class="lbl">AI-generated topic (edit or write your own)</div>
      <textarea class="inp" id="f-topic" rows="2" placeholder="Click Generate to get an AI topic, or type your own..."></textarea>
    </div>
    <div class="step-actions">
      <button class="btn btn-go" onclick="genTopic()">⚡ GENERATE TOPIC</button>
      <button class="btn btn-grn" onclick="lockStep(1)" id="btn-lock1">APPROVE & NEXT →</button>
    </div>
    <div class="step-status" id="st1-status"></div>
  </div>

  <!-- STEP 2: QUOTE -->
  <div class="step locked" id="st-2">
    <div class="step-head"><div class="step-num">2</div><div class="step-title">QUOTE</div></div>
    <div class="fi"><div class="lbl">Quote / text overlay for the image</div>
      <textarea class="inp" id="f-quote" rows="2" placeholder="AI will generate a quote from your topic..."></textarea>
    </div>
    <div class="step-actions">
      <button class="btn btn-go" onclick="genQuote()">⚡ GENERATE QUOTE</button>
      <button class="btn btn-out" onclick="genQuote()">↻ REGENERATE</button>
      <button class="btn btn-grn" onclick="lockStep(2)">APPROVE & NEXT →</button>
    </div>
    <div class="step-status" id="st2-status"></div>
  </div>

  <!-- STEP 3: IMAGE PROMPT -->
  <div class="step locked" id="st-3">
    <div class="step-head"><div class="step-num">3</div><div class="step-title">IMAGE PROMPT</div></div>
    <div class="fi"><div class="lbl">Detailed prompt for the image generator</div>
      <textarea class="inp" id="f-prompt" rows="4" placeholder="AI builds a detailed image prompt from your topic + brand style..."></textarea>
    </div>
    <div class="step-actions">
      <button class="btn btn-go" onclick="genPrompt()">⚡ GENERATE PROMPT</button>
      <button class="btn btn-out" onclick="genPrompt()">↻ REGENERATE</button>
      <button class="btn btn-grn" onclick="lockStep(3)">APPROVE & GENERATE IMAGE →</button>
    </div>
    <div class="step-status" id="st3-status"></div>
  </div>

  <!-- STEP 4: IMAGE -->
  <div class="step locked" id="st-4">
    <div class="step-head"><div class="step-num">4</div><div class="step-title">IMAGE GENERATION</div></div>
    <div id="img-area"></div>
    <div class="step-actions">
      <button class="btn btn-go" onclick="genImage()" id="btn-genimg">⚡ GENERATE IMAGE</button>
      <button class="btn btn-out" onclick="genImage()">↻ REGENERATE</button>
      <button class="btn btn-grn" onclick="lockStep(4)" id="btn-lock4" disabled>APPROVE IMAGE & NEXT →</button>
    </div>
    <div class="step-status" id="st4-status"></div>
  </div>

  <!-- STEP 5: CAPTIONS -->
  <div class="step locked" id="st-5">
    <div class="step-head"><div class="step-num">5</div><div class="step-title">CAPTIONS</div></div>
    <div id="cap-area"></div>
    <div class="step-actions">
      <button class="btn btn-go" onclick="genCaptions()">⚡ GENERATE CAPTIONS</button>
      <button class="btn btn-out" onclick="genCaptions()">↻ REGENERATE</button>
      <button class="btn btn-grn" onclick="lockStep(5)">APPROVE & SAVE →</button>
    </div>
    <div class="step-status" id="st5-status"></div>
  </div>

  <!-- STEP 6: SAVE / PUBLISH -->
  <div class="step locked" id="st-6">
    <div class="step-head"><div class="step-num">6</div><div class="step-title">SAVE & PUBLISH</div></div>
    <div id="final-summary"></div>
    <div class="step-actions">
      <button class="btn btn-grn" onclick="savePost()">💾 SAVE TO GALLERY</button>
      <button class="btn btn-go" onclick="resetFlow()">✦ START NEW POST</button>
    </div>
    <div class="step-status" id="st6-status"></div>
  </div>

</div>

<!-- ═══ GALLERY TAB ═══ -->
<div class="page" id="p-gallery">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.6em">
    <span style="font-family:var(--f1);font-size:.6em;letter-spacing:.12em;color:var(--txtd)">SAVED POSTS</span>
    <span id="g-count" style="font-size:.55em;color:var(--txtdd)"></span>
  </div>
  <div class="gal" id="g-grid"></div>
</div>

<!-- MODAL -->
<div class="mbg" id="modal" onclick="if(event.target===this)cM()">
  <button class="mx" onclick="cM()">✕</button>
  <img class="mimg" id="m-img">
  <div class="mdet" id="m-det"></div>
</div>

</div>
<script>
const $=id=>document.getElementById(id), API='/graphics/api';
let STATE={step:1, brand_id:'', topic:'', quote:'', prompt:'', image_url:'', captions:{}};

// ─── NAV ─────────────────────────────────────────────────────
function gN(p,b){document.querySelectorAll('.page').forEach(e=>e.classList.remove('on'));document.querySelectorAll('.tab').forEach(b=>b.classList.remove('on'));$('p-'+p).classList.add('on');if(b)b.classList.add('on');if(p==='gallery')lG();}

// ─── BRANDS ──────────────────────────────────────────────────
async function lB(){
  try{
    const brands=await(await fetch(API+'/brands')).json();
    $('s-brand').innerHTML=brands.map(b=>`<option value="${b.id}">${b.name}</option>`).join('')||'<option>No brands</option>';
  }catch(e){}
}

// ─── STEP MANAGEMENT ─────────────────────────────────────────
function updateSteps(){
  for(let i=1;i<=6;i++){
    const el=$('st-'+i);
    el.classList.remove('active','done','locked');
    if(i<STATE.step) el.classList.add('done');
    else if(i===STATE.step) el.classList.add('active');
    else el.classList.add('locked');
  }
}
function lockStep(n){
  // Validate current step has content
  if(n===1 && !$('f-topic').value.trim()){alert('Enter or generate a topic first');return;}
  if(n===2 && !$('f-quote').value.trim()){alert('Enter or generate a quote first');return;}
  if(n===3 && !$('f-prompt').value.trim()){alert('Enter or generate an image prompt first');return;}
  if(n===4 && !STATE.image_url){alert('Generate an image first');return;}
  if(n===5){
    // Collect edited captions
    const caps={};
    document.querySelectorAll('.cap-text').forEach(el=>{caps[el.dataset.plat]=el.value;});
    STATE.captions=caps;
  }

  // Save state
  if(n===1) STATE.topic=$('f-topic').value.trim();
  if(n===2) STATE.quote=$('f-quote').value.trim();
  if(n===3) STATE.prompt=$('f-prompt').value.trim();

  STATE.step=n+1;
  updateSteps();

  // Auto-trigger next phase
  if(n===1) genQuote();
  if(n===2) genPrompt();
  if(n===3) genImage();
  if(n===4) genCaptions();
  if(n===5) showSummary();
}

// ─── PHASE 1: TOPIC ─────────────────────────────────────────
async function genTopic(){
  const brand=$('s-brand').value;if(!brand){alert('Select a brand');return;}
  $('st1-status').innerHTML='<span class="spin">⏳</span> Generating topic...';
  try{
    const r=await(await fetch(API+'/phase/topic',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brand_id:brand})})).json();
    if(r.error){$('st1-status').innerHTML=`<span style="color:var(--red)">${r.error}</span>`;return;}
    $('f-topic').value=r.topic;
    $('st1-status').innerHTML='<span style="color:var(--grn)">✓ Topic generated — edit if needed, then approve</span>';
  }catch(e){$('st1-status').innerHTML=`<span style="color:var(--red)">Error: ${e}</span>`;}
}

// ─── PHASE 2: QUOTE ──────────────────────────────────────────
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
  const brand=$('s-brand').value;const topic=$('f-topic').value.trim();const quote=$('f-quote').value.trim();
  $('st3-status').innerHTML='<span class="spin">⏳</span> Building image prompt...';
  try{
    const r=await(await fetch(API+'/phase/prompt',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brand_id:brand,topic,quote})})).json();
    if(r.error){$('st3-status').innerHTML=`<span style="color:var(--red)">${r.error}</span>`;return;}
    $('f-prompt').value=r.prompt;
    $('st3-status').innerHTML='<span style="color:var(--grn)">✓ Prompt built — edit if needed</span>';
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
    // Poll
    const jid=r.job_id;
    const poll=setInterval(async()=>{
      const s=await(await fetch(API+'/phase/image/'+jid)).json();
      if(s.status==='done'){
        clearInterval(poll);
        STATE.image_url=s.r2_url||s.image_url;
        $('img-area').innerHTML=`<div class="img-preview"><img src="${STATE.image_url}"></div>`;
        $('st4-status').innerHTML='<span style="color:var(--grn)">✓ Image generated — approve or regenerate</span>';
        $('btn-lock4').disabled=false;
      }else if(s.status==='failed'){
        clearInterval(poll);
        $('st4-status').innerHTML=`<span style="color:var(--red)">Failed: ${s.error||'Unknown error'}</span>`;
      }else{
        $('st4-status').innerHTML=`<span class="spin">⏳</span> ${s.phase||'Generating'}...`;
      }
    },4000);
  }catch(e){$('st4-status').innerHTML=`<span style="color:var(--red)">Error: ${e}</span>`;}
}

// ─── PHASE 5: CAPTIONS ───────────────────────────────────────
const PLATFORMS=['instagram','facebook','tiktok','twitter','threads'];
async function genCaptions(){
  $('st5-status').innerHTML='<span class="spin">⏳</span> Generating captions...';
  try{
    const r=await(await fetch(API+'/phase/captions',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brand_id:$('s-brand').value,topic:$('f-topic').value,quote:$('f-quote').value})})).json();
    if(r.error){$('st5-status').innerHTML=`<span style="color:var(--red)">${r.error}</span>`;return;}
    STATE.captions=r.captions||{};
    renderCaptions();
    $('st5-status').innerHTML='<span style="color:var(--grn)">✓ Captions generated — edit each platform as needed</span>';
  }catch(e){$('st5-status').innerHTML=`<span style="color:var(--red)">Error: ${e}</span>`;}
}
function renderCaptions(){
  $('cap-area').innerHTML=PLATFORMS.map(p=>{
    const txt=STATE.captions[p]||'';
    const icon={instagram:'📸',facebook:'👥',tiktok:'🎵',twitter:'𝕏',threads:'🧵'}[p]||'';
    return`<div class="cap-block"><div class="cap-plat">${icon} ${p}</div><textarea class="cap-text" data-plat="${p}" rows="3">${txt}</textarea></div>`;
  }).join('');
}

// ─── PHASE 6: SUMMARY & SAVE ─────────────────────────────────
function showSummary(){
  const brand=$('s-brand');const bn=brand.options[brand.selectedIndex]?.text||'';
  $('final-summary').innerHTML=`
    <div class="row"><div>
      ${STATE.image_url?`<div class="img-preview"><img src="${STATE.image_url}"></div>`:''}
    </div><div>
      <div style="margin-bottom:.5em"><div class="lbl">BRAND</div><div style="font-size:.85em;color:var(--wht)">${bn}</div></div>
      <div style="margin-bottom:.5em"><div class="lbl">TOPIC</div><div style="font-size:.85em;color:var(--wht)">${STATE.topic}</div></div>
      <div style="margin-bottom:.5em"><div class="lbl">QUOTE</div><div style="font-size:.85em;color:var(--amb);font-style:italic">"${STATE.quote}"</div></div>
      <div><div class="lbl">CAPTIONS</div><div style="font-size:.65em;color:var(--txtd)">${Object.keys(STATE.captions).length} platforms ready</div></div>
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
    $('st6-status').innerHTML=`<span style="color:var(--grn)">✓ Saved to gallery! ID: ${r.id||'OK'}</span>`;
  }catch(e){$('st6-status').innerHTML=`<span style="color:var(--red)">Error: ${e}</span>`;}
}

function resetFlow(){
  STATE={step:1,brand_id:'',topic:'',quote:'',prompt:'',image_url:'',captions:{}};
  $('f-topic').value='';$('f-quote').value='';$('f-prompt').value='';
  $('img-area').innerHTML='';$('cap-area').innerHTML='';$('final-summary').innerHTML='';
  $('btn-lock4').disabled=true;
  ['st1-status','st2-status','st3-status','st4-status','st5-status','st6-status'].forEach(id=>$(id).innerHTML='');
  updateSteps();
}

// ─── GALLERY ─────────────────────────────────────────────────
async function lG(){
  try{
    const items=await(await fetch(API+'/gallery')).json();
    $('g-count').textContent=items.length+' posts';
    if(!items.length){$('g-grid').innerHTML='<div style="color:var(--txtd);font-size:.7em;padding:2em;text-align:center">No posts yet. Create one in the CREATE tab.</div>';return;}
    $('g-grid').innerHTML=items.map(g=>`<div class="gi" onclick="sM('${g.image_url}','${esc(g.quote)}','${esc(g.topic)}','${g.brand_name||g.brand}')"><img src="${g.image_url}" loading="lazy"><div class="gi-info"><div class="gi-topic">${g.topic||''}</div><div class="gi-quote">"${(g.quote||'').substring(0,50)}"</div><div class="gi-meta">${g.brand_name||g.brand} · ${(g.created||'').substring(0,10)}</div></div><div class="gi-del" onclick="event.stopPropagation();dG('${g.id}')">✕</div></div>`).join('');
  }catch(e){}
}
function esc(s){return(s||'').replace(/'/g,"\\'").replace(/"/g,'&quot;');}
async function dG(id){if(!confirm('Delete this post?'))return;await fetch(API+'/gallery/'+id,{method:'DELETE'});lG();}

// ─── MODAL ───────────────────────────────────────────────────
function sM(url,quote,topic,brand){$('modal').classList.add('show');$('m-img').src=url;$('m-det').innerHTML=`<b>${brand}</b><br>${topic}<br><i>"${quote}"</i>`;}
function cM(){$('modal').classList.remove('show');}

// ─── INIT ────────────────────────────────────────────────────
lB();updateSteps();
</script></body></html>"""
