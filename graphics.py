"""
Knights Reactor — Graphics Engine
===================================
Standalone image + video generation tool.
Prompt editor, batch mode, gallery, R2 upload.
Mounted as /graphics on the main app.
"""

import json, os, time, uuid, threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

import requests
import boto3

from pipeline import Config

# ─── REPLICATE HELPERS (self-contained) ───────────────────────
def replicate_create(model: str, input_data: dict) -> str:
    """Create a Replicate prediction, return the GET URL for polling."""
    for attempt in range(5):
        r = requests.post(
            f"https://api.replicate.com/v1/models/{model}/predictions",
            headers={"Authorization": f"Bearer {Config.REPLICATE_TOKEN}", "Content-Type": "application/json"},
            json={"input": input_data}, timeout=30,
        )
        if r.status_code == 429:
            import time as _t; _t.sleep(min(30 * (attempt + 1), 120)); continue
        r.raise_for_status()
        return r.json()["urls"]["get"]
    raise Exception("Replicate rate limit: 5 retries exhausted")

def replicate_poll(get_url: str, timeout: int = 300) -> str:
    """Poll a Replicate prediction until complete. Returns output URL."""
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
    raise TimeoutError("Replicate prediction timed out")

def get_s3_client():
    return boto3.client("s3", endpoint_url=Config.R2_ENDPOINT,
        aws_access_key_id=Config.R2_ACCESS_KEY, aws_secret_access_key=Config.R2_SECRET_KEY, region_name="auto")

def upload_to_r2(folder: str, filename: str, data, content_type: str) -> str:
    """Upload to R2, return public URL."""
    s3 = get_s3_client()
    key = f"{folder}/{filename}"
    if isinstance(data, bytes):
        s3.put_object(Bucket=Config.R2_BUCKET, Key=key, Body=data, ContentType=content_type)
    elif isinstance(data, str) and data.startswith("http"):
        r = requests.get(data, timeout=120); r.raise_for_status()
        body = r.content
        ct = content_type
        if body[:4] == b'\x1a\x45\xdf\xa3': ct = "video/webm"; key = key.rsplit(".",1)[0] + ".webm"
        elif body[4:8] == b'ftyp': ct = "video/mp4"
        s3.put_object(Bucket=Config.R2_BUCKET, Key=key, Body=body, ContentType=ct)
    else:
        s3.put_object(Bucket=Config.R2_BUCKET, Key=key, Body=str(data).encode(), ContentType=content_type)
    return f"{Config.R2_PUBLIC_URL}/{key}"

router = APIRouter(prefix="/graphics", tags=["graphics"])

# ─── PERSISTENT STATE ────────────────────────────────────────
DATA_DIR = Path("/var/data") if Path("/var/data").exists() else Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
JOBS_FILE = DATA_DIR / "graphics_jobs.json"
GALLERY_FILE = DATA_DIR / "graphics_gallery.json"

def load_json(path, default=None):
    if path.exists():
        try: return json.loads(path.read_text())
        except: pass
    return default if default is not None else []

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))

# In-memory job tracking
JOBS = {}  # {job_id: {status, type, prompt, model, result, error, created}}

def get_gallery():
    return load_json(GALLERY_FILE, [])

def save_gallery(items):
    save_json(GALLERY_FILE, items[-500:])  # keep last 500

# ─── IMAGE GENERATION ────────────────────────────────────────

def _gen_image(job_id: str, prompt: str, model: str, aspect: str, quality: str):
    """Background worker: generate image via Replicate."""
    try:
        JOBS[job_id]["status"] = "processing"
        params = {"prompt": prompt, "aspect_ratio": aspect}
        if "recraft" not in model:
            params["quality"] = quality

        poll_url = replicate_create(model, params)
        JOBS[job_id]["poll_url"] = poll_url

        result_url = replicate_poll(poll_url, timeout=300)
        
        # Upload to R2
        folder = "graphics"
        fname = f"img_{job_id[:8]}.png"
        r2_url = upload_to_r2(folder, fname, result_url, "image/png")

        JOBS[job_id].update({"status": "complete", "result": r2_url, "replicate_url": result_url})
        
        # Add to gallery
        gallery = get_gallery()
        gallery.insert(0, {
            "id": job_id, "type": "image", "url": r2_url,
            "prompt": prompt, "model": model, "aspect": aspect,
            "created": datetime.now().isoformat(),
        })
        save_gallery(gallery)

    except Exception as e:
        JOBS[job_id].update({"status": "failed", "error": str(e)})

# ─── VIDEO GENERATION (Image-to-Video) ───────────────────────

def _gen_video(job_id: str, image_url: str, motion_prompt: str, model: str, aspect: str):
    """Background worker: generate video from image via Replicate."""
    try:
        JOBS[job_id]["status"] = "processing"
        
        # Model-specific params
        if "minimax" in model.lower():
            params = {"first_frame_image": image_url, "prompt": motion_prompt}
        elif "grok" in model.lower():
            params = {"image_url": image_url, "prompt": motion_prompt, "mode": "normal"}
        else:
            params = {"image": image_url, "prompt": motion_prompt}

        if "seedance" in model.lower() or "wan" in model.lower():
            params["aspect_ratio"] = aspect

        poll_url = replicate_create(model, params)
        JOBS[job_id]["poll_url"] = poll_url

        result_url = replicate_poll(poll_url, timeout=600)

        # Upload to R2
        folder = "graphics"
        fname = f"vid_{job_id[:8]}.mp4"
        r2_url = upload_to_r2(folder, fname, result_url, "video/mp4")

        JOBS[job_id].update({"status": "complete", "result": r2_url, "replicate_url": result_url})

        # Add to gallery
        gallery = get_gallery()
        gallery.insert(0, {
            "id": job_id, "type": "video", "url": r2_url,
            "prompt": motion_prompt, "source_image": image_url,
            "model": model, "created": datetime.now().isoformat(),
        })
        save_gallery(gallery)

    except Exception as e:
        JOBS[job_id].update({"status": "failed", "error": str(e)})

# ─── API ENDPOINTS ────────────────────────────────────────────

@router.post("/api/generate-image")
async def generate_image(req: Request):
    body = await req.json()
    prompt = body.get("prompt", "").strip()
    model = body.get("model", Config.IMAGE_MODEL)
    aspect = body.get("aspect", "9:16")
    quality = body.get("quality", "high")
    if not prompt:
        return JSONResponse({"error": "No prompt"}, 400)

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "id": job_id, "type": "image", "status": "queued",
        "prompt": prompt, "model": model, "aspect": aspect,
        "created": datetime.now().isoformat(),
    }
    t = threading.Thread(target=_gen_image, args=(job_id, prompt, model, aspect, quality), daemon=True)
    t.start()
    return {"job_id": job_id, "status": "queued"}

@router.post("/api/generate-video")
async def generate_video(req: Request):
    body = await req.json()
    image_url = body.get("image_url", "").strip()
    motion = body.get("motion_prompt", "").strip()
    model = body.get("model", Config.VIDEO_MODEL)
    aspect = body.get("aspect", "9:16")
    if not image_url:
        return JSONResponse({"error": "No image URL"}, 400)

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "id": job_id, "type": "video", "status": "queued",
        "image_url": image_url, "motion_prompt": motion, "model": model,
        "created": datetime.now().isoformat(),
    }
    t = threading.Thread(target=_gen_video, args=(job_id, image_url, motion, model, aspect), daemon=True)
    t.start()
    return {"job_id": job_id, "status": "queued"}

@router.post("/api/batch-images")
async def batch_images(req: Request):
    """Generate multiple images from newline-separated prompts."""
    body = await req.json()
    prompts = [p.strip() for p in body.get("prompts", "").split("\n") if p.strip()]
    model = body.get("model", Config.IMAGE_MODEL)
    aspect = body.get("aspect", "9:16")
    quality = body.get("quality", "high")

    job_ids = []
    for prompt in prompts[:10]:  # max 10
        job_id = str(uuid.uuid4())
        JOBS[job_id] = {
            "id": job_id, "type": "image", "status": "queued",
            "prompt": prompt, "model": model, "aspect": aspect,
            "created": datetime.now().isoformat(),
        }
        t = threading.Thread(target=_gen_image, args=(job_id, prompt, model, aspect, quality), daemon=True)
        t.start()
        job_ids.append(job_id)
        time.sleep(1)  # stagger to avoid 429

    return {"job_ids": job_ids, "count": len(job_ids)}

@router.get("/api/job/{job_id}")
async def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return JSONResponse({"error": "Not found"}, 404)
    return job

@router.get("/api/jobs")
async def list_jobs():
    """Return all active/recent jobs."""
    return sorted(JOBS.values(), key=lambda j: j.get("created", ""), reverse=True)[:50]

@router.get("/api/gallery")
async def gallery():
    return get_gallery()[:100]

@router.delete("/api/gallery/{item_id}")
async def delete_gallery_item(item_id: str):
    gallery = get_gallery()
    gallery = [g for g in gallery if g.get("id") != item_id]
    save_gallery(gallery)
    return {"status": "deleted"}

# ─── DASHBOARD HTML ───────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def graphics_dashboard():
    return GRAPHICS_HTML

GRAPHICS_HTML = r"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Knights Reactor — Graphics Engine</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;800&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
:root{--bg:#08080a;--bg2:#0c0c10;--bg3:#111118;--panel:#0d0d12;--bd:rgba(227,160,40,.12);--bd2:rgba(227,160,40,.06);--amb:#e3a028;--amb2:#c88a1a;--amblo:rgba(227,160,40,.05);--txt:#e3a028;--txtd:#7a5a18;--txtdd:#3a2a08;--grn:#28e060;--grn2:rgba(40,224,96,.08);--red:#e04028;--red2:rgba(224,64,40,.08);--blu:#28a0e0;--blu2:rgba(40,160,224,.08);--wht:#c8c0a8;--f1:'Orbitron',monospace;--f3:'Share Tech Mono',monospace}
*{margin:0;padding:0;box-sizing:border-box}
html{font-size:clamp(14px,1.25vw,22px)}
body{background:var(--bg);color:var(--txt);font-family:var(--f3);min-height:100vh}
::-webkit-scrollbar{width:3px}::-webkit-scrollbar-thumb{background:var(--amb2)}::-webkit-scrollbar-track{background:var(--bg)}
button{font-family:var(--f3);cursor:pointer}
input,select,textarea{font-family:var(--f3)}
a{color:var(--amb)}

.top{background:var(--bg2);border-bottom:1px solid var(--bd);padding:.7em 1.2em;display:flex;align-items:center;justify-content:space-between}
.top h1{font-family:var(--f1);font-size:.75em;font-weight:800;color:var(--amb);letter-spacing:.15em}
.top a{font-size:.6em;color:var(--txtd);text-decoration:none;letter-spacing:.1em}
.top a:hover{color:var(--amb)}

.wrap{max-width:72em;margin:0 auto;padding:1em}

.tabs{display:flex;gap:2px;border-bottom:1px solid var(--bd);margin-bottom:1em}
.tab{font-family:var(--f1);font-size:.6em;color:var(--txtd);background:none;border:none;border-bottom:2px solid transparent;padding:.7em 1em;letter-spacing:.12em}
.tab:hover{color:var(--amb)}
.tab.on{color:var(--amb);border-bottom-color:var(--amb)}
.page{display:none}.page.on{display:block}

/* Forms */
.lbl{font-size:.65em;color:var(--txtd);text-transform:uppercase;letter-spacing:.15em;margin-bottom:.3em}
.inp{width:100%;padding:.6em .8em;background:var(--bg);border:1px solid var(--bd2);color:var(--amb);font-size:.85em;outline:none}
.inp:focus{border-color:var(--amb)}
textarea.inp{resize:vertical;min-height:5em;line-height:1.5}
select.inp{-webkit-appearance:none;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23e3a028'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center;padding-right:28px;cursor:pointer;background-color:var(--bg)}
select.inp option{background:var(--bg2);color:var(--amb)}

.btn{padding:.65em 1.2em;font-family:var(--f1);font-size:.6em;font-weight:600;letter-spacing:.15em;border:none}
.btn-go{background:var(--amb);color:var(--bg)}
.btn-go:hover{box-shadow:0 0 12px rgba(227,160,40,.3)}
.btn-out{background:none;border:1px solid var(--bd);color:var(--amb)}
.btn-out:hover{background:var(--amblo)}
.btn-red{background:var(--red2);border:1px solid rgba(224,64,40,.15);color:var(--red);font-size:.55em;padding:.4em .7em}
.btn-sm{font-size:.55em;padding:.4em .8em;letter-spacing:.1em}

.row{display:flex;gap:.8em;flex-wrap:wrap}
.col{flex:1;min-width:12em}

/* Jobs */
.job{background:var(--panel);border:1px solid var(--bd2);padding:.65em .85em;margin-bottom:4px;display:flex;align-items:center;gap:.6em}
.job-dot{width:.4em;height:.4em;border-radius:50%;flex-shrink:0}
.job-q{background:var(--txtdd)}
.job-p{background:var(--blu);animation:pulse 1.2s infinite}
.job-c{background:var(--grn)}
.job-f{background:var(--red)}
.job-info{flex:1;overflow:hidden}
.job-prompt{font-size:.7em;color:var(--wht);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.job-meta{font-size:.5em;color:var(--txtd);letter-spacing:.08em;margin-top:.1em}
.job-thumb{width:3em;height:3em;object-fit:cover;border:1px solid var(--bd2)}

@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

/* Gallery */
.gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(10em,1fr));gap:.5em}
.card{background:var(--panel);border:1px solid var(--bd2);overflow:hidden;position:relative}
.card img,.card video{width:100%;display:block;cursor:pointer}
.card-bar{display:flex;align-items:center;justify-content:space-between;padding:.25em .4em}
.card-lbl{font-size:.45em;color:var(--txtd);letter-spacing:.08em;text-transform:uppercase}
.card-acts{display:flex;gap:3px}
.card-acts button{font-size:.5em;padding:.2em .4em;background:var(--bg);border:1px solid var(--bd2);color:var(--amb);cursor:pointer}
.card-acts button:hover{border-color:var(--amb)}
.card-acts .del{color:var(--red);border-color:rgba(224,64,40,.15)}

/* Modal */
.modal-bg{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.85);z-index:999;display:none;align-items:center;justify-content:center}
.modal-bg.on{display:flex}
.modal{max-width:90vw;max-height:90vh;position:relative}
.modal img,.modal video{max-width:90vw;max-height:85vh;display:block}
.modal-close{position:absolute;top:-1.5em;right:0;background:none;border:none;color:var(--amb);font-size:1.2em;cursor:pointer}
.modal-info{background:var(--panel);padding:.5em .7em;font-size:.6em;color:var(--wht);max-width:90vw;word-break:break-all}

/* Responsive */
@media(max-width:768px){
  .row{flex-direction:column}
  .gal{grid-template-columns:repeat(2,1fr)}
  .top h1{font-size:.65em}
  textarea.inp{min-height:4em}
}
</style></head><body>

<div class="top">
  <h1>◈ GRAPHICS ENGINE</h1>
  <a href="/">← REACTOR DASHBOARD</a>
</div>

<div class="wrap">
<div class="tabs">
  <button class="tab on" onclick="nav('gen',this)">◉ GENERATE</button>
  <button class="tab" onclick="nav('jobs',this)">⚡ JOBS</button>
  <button class="tab" onclick="nav('gallery',this)">▤ GALLERY</button>
</div>

<!-- ═══ GENERATE TAB ═══ -->
<div class="page on" id="p-gen">
  <div class="row">
    <div class="col" style="flex:2">
      <div class="lbl">PROMPT (one per line for batch)</div>
      <textarea class="inp" id="g-prompt" placeholder="A battle-scarred knight in dented steel plate armor standing on a misty cliff at dawn, cinematic lighting, 9:16 vertical, photorealistic"></textarea>
      
      <div style="display:flex;gap:.5em;margin-top:.6em;flex-wrap:wrap">
        <div style="flex:1;min-width:8em">
          <div class="lbl">IMAGE MODEL</div>
          <select class="inp" id="g-img-model"></select>
        </div>
        <div style="min-width:5em">
          <div class="lbl">ASPECT</div>
          <select class="inp" id="g-aspect">
            <option value="9:16" selected>9:16</option>
            <option value="16:9">16:9</option>
            <option value="1:1">1:1</option>
            <option value="4:5">4:5</option>
          </select>
        </div>
        <div style="min-width:5em">
          <div class="lbl">QUALITY</div>
          <select class="inp" id="g-quality">
            <option value="high" selected>High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>
      </div>
      <div style="display:flex;gap:.5em;margin-top:.5em">
        <button class="btn btn-go" onclick="genImage()" id="btn-gen">▶ GENERATE IMAGE</button>
        <button class="btn btn-out btn-sm" onclick="genBatch()">▶▶ BATCH</button>
      </div>
    </div>

    <div class="col">
      <div class="lbl">IMAGE → VIDEO</div>
      <div style="background:var(--panel);border:1px solid var(--bd2);padding:.7em">
        <div class="lbl">SOURCE IMAGE URL</div>
        <input class="inp" id="g-vid-src" placeholder="Paste image URL or click 📹 on gallery item">
        <div class="lbl" style="margin-top:.5em">MOTION PROMPT</div>
        <input class="inp" id="g-vid-motion" placeholder="Slow push-in, cape drifts in wind, steady camera">
        <div class="lbl" style="margin-top:.5em">VIDEO MODEL</div>
        <select class="inp" id="g-vid-model"></select>
        <button class="btn btn-go" style="width:100%;margin-top:.5em" onclick="genVideo()">▶ ANIMATE</button>
      </div>
    </div>
  </div>
</div>

<!-- ═══ JOBS TAB ═══ -->
<div class="page" id="p-jobs">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5em">
    <div class="lbl" style="margin:0">ACTIVE JOBS</div>
    <button class="btn btn-out btn-sm" onclick="loadJobs()">↻ REFRESH</button>
  </div>
  <div id="jobs-list"></div>
</div>

<!-- ═══ GALLERY TAB ═══ -->
<div class="page" id="p-gallery">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5em">
    <div class="lbl" style="margin:0">GENERATED ASSETS</div>
    <button class="btn btn-out btn-sm" onclick="loadGallery()">↻ REFRESH</button>
  </div>
  <div class="gal" id="gal-grid"></div>
</div>
</div>

<!-- PREVIEW MODAL -->
<div class="modal-bg" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <div id="modal-content"></div>
    <div class="modal-info" id="modal-info"></div>
  </div>
</div>

<script>
const $=id=>document.getElementById(id);
const API='/graphics/api';

const IMG_MODELS=[
  {v:"google/nano-banana-pro",l:"Nano Banana Pro ~$0.10"},
  {v:"google/nano-banana",l:"Nano Banana ~$0.02"},
  {v:"xai/grok-imagine-image",l:"Grok Aurora ~$0.07"},
  {v:"bytedance/seedream-4.5",l:"Seedream 4.5 ~$0.03"},
  {v:"black-forest-labs/flux-1.1-pro",l:"Flux 1.1 Pro ~$0.04"},
  {v:"black-forest-labs/flux-schnell",l:"Flux Schnell ~$0.003"},
  {v:"black-forest-labs/flux-dev",l:"Flux Dev ~$0.03"},
  {v:"ideogram-ai/ideogram-v3-quality",l:"Ideogram v3 Q ~$0.08"},
  {v:"ideogram-ai/ideogram-v3-turbo",l:"Ideogram v3 T ~$0.02"},
  {v:"recraft-ai/recraft-v3",l:"Recraft v3 ~$0.04"},
  {v:"stability-ai/stable-diffusion-3.5-large",l:"SD 3.5 L ~$0.035"},
  {v:"google-deepmind/imagen-4-preview",l:"Imagen 4 ~$0.04"},
];
const VID_MODELS=[
  {v:"bytedance/seedance-1-lite",l:"Seedance Lite ~$0.25"},
  {v:"bytedance/seedance-1",l:"Seedance Pro ~$0.50"},
  {v:"wavespeedai/wan-2.1-i2v-480p",l:"Wan 480p ~$0.10"},
  {v:"wavespeedai/wan-2.1-i2v-720p",l:"Wan 720p ~$0.20"},
  {v:"xai/grok-imagine-video",l:"Grok Video ~$0.30"},
  {v:"minimax/video-01-live",l:"Minimax Live ~$0.25"},
  {v:"minimax/video-01",l:"Minimax v01 ~$0.50"},
  {v:"kwaivgi/kling-v2.0-image-to-video",l:"Kling v2.0 ~$0.30"},
  {v:"luma/ray-2-flash",l:"Luma Flash ~$0.20"},
  {v:"luma/ray-2",l:"Luma Ray 2 ~$0.40"},
  {v:"google-deepmind/veo-3",l:"Veo 3 ~$0.50"},
];

function populateModels(){
  const im=$('g-img-model'),vm=$('g-vid-model');
  im.innerHTML=IMG_MODELS.map(m=>`<option value="${m.v}">${m.l}</option>`).join('');
  vm.innerHTML=VID_MODELS.map(m=>`<option value="${m.v}">${m.l}</option>`).join('');
}

function nav(p,btn){
  document.querySelectorAll('.page').forEach(e=>e.classList.remove('on'));
  document.querySelectorAll('.tab').forEach(b=>b.classList.remove('on'));
  $('p-'+p).classList.add('on');
  btn.classList.add('on');
  if(p==='jobs')loadJobs();
  if(p==='gallery')loadGallery();
}

// ─── GENERATE ────────────────────────────────────────────────
async function genImage(){
  const prompt=$('g-prompt').value.trim();
  if(!prompt)return;
  const b=$('btn-gen');b.textContent='⏳...';b.disabled=true;
  try{
    const r=await fetch(API+'/generate-image',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      prompt, model:$('g-img-model').value, aspect:$('g-aspect').value, quality:$('g-quality').value
    })});
    const d=await r.json();
    if(d.job_id){nav('jobs',document.querySelectorAll('.tab')[1]);pollJob(d.job_id);}
  }catch(e){alert('Error: '+e);}
  b.textContent='▶ GENERATE IMAGE';b.disabled=false;
}

async function genBatch(){
  const prompts=$('g-prompt').value.trim();
  if(!prompts)return;
  try{
    const r=await fetch(API+'/batch-images',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      prompts, model:$('g-img-model').value, aspect:$('g-aspect').value, quality:$('g-quality').value
    })});
    const d=await r.json();
    if(d.count>0){nav('jobs',document.querySelectorAll('.tab')[1]);d.job_ids.forEach(id=>pollJob(id));}
  }catch(e){alert('Error: '+e);}
}

async function genVideo(){
  const src=$('g-vid-src').value.trim();
  if(!src){alert('Paste an image URL first');return;}
  try{
    const r=await fetch(API+'/generate-video',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      image_url:src, motion_prompt:$('g-vid-motion').value, model:$('g-vid-model').value, aspect:$('g-aspect').value
    })});
    const d=await r.json();
    if(d.job_id){nav('jobs',document.querySelectorAll('.tab')[1]);pollJob(d.job_id);}
  }catch(e){alert('Error: '+e);}
}

// ─── JOBS ────────────────────────────────────────────────────
let POLLING={};

async function loadJobs(){
  try{
    const jobs=await(await fetch(API+'/jobs')).json();
    const el=$('jobs-list');
    if(!jobs.length){el.innerHTML='<div style="padding:1em;color:var(--txtd);font-size:.7em">No jobs yet. Generate something!</div>';return;}
    el.innerHTML=jobs.map(j=>{
      const dc={queued:'q',processing:'p',complete:'c',failed:'f'}[j.status]||'q';
      const thumb=j.result&&j.type==='image'?`<img class="job-thumb" src="${j.result}">`:'';
      const vid=j.result&&j.type==='video'?`<video class="job-thumb" src="${j.result}" muted></video>`:'';
      return`<div class="job"><span class="job-dot job-${dc}"></span><div class="job-info"><div class="job-prompt">${j.prompt||j.motion_prompt||'—'}</div><div class="job-meta">${j.type} · ${j.model||'?'} · ${j.status}${j.error?' · '+j.error:''}</div></div>${thumb}${vid}</div>`;
    }).join('');
    // Auto-poll incomplete
    jobs.filter(j=>j.status==='queued'||j.status==='processing').forEach(j=>{if(!POLLING[j.id])pollJob(j.id);});
  }catch(e){}
}

function pollJob(id){
  if(POLLING[id])return;
  POLLING[id]=true;
  const check=async()=>{
    try{
      const j=await(await fetch(API+'/job/'+id)).json();
      if(j.status==='complete'||j.status==='failed'){delete POLLING[id];loadJobs();return;}
      setTimeout(check,5000);
    }catch(e){delete POLLING[id];}
  };
  setTimeout(check,3000);
}

// ─── GALLERY ─────────────────────────────────────────────────
async function loadGallery(){
  try{
    const items=await(await fetch(API+'/gallery')).json();
    const el=$('gal-grid');
    if(!items.length){el.innerHTML='<div style="grid-column:1/-1;padding:2em;text-align:center;color:var(--txtd);font-size:.7em">No assets yet</div>';return;}
    el.innerHTML=items.map(it=>{
      const media=it.type==='video'
        ?`<video src="${it.url}" muted loop playsinline onmouseenter="this.play()" onmouseleave="this.pause();this.currentTime=0" onclick="openModal('${it.id}')"></video>`
        :`<img src="${it.url}" loading="lazy" onclick="openModal('${it.id}')">`;
      return`<div class="card" data-id="${it.id}" data-url="${it.url}" data-type="${it.type}" data-prompt="${(it.prompt||'').replace(/"/g,'&quot;')}" data-model="${it.model||''}">${media}<div class="card-bar"><span class="card-lbl">${it.type} · ${(it.model||'?').split('/').pop()}</span><div class="card-acts">${it.type==='image'?`<button onclick="animateThis('${it.url}')" title="Animate">📹</button>`:''}<a href="${it.url}" download target="_blank" style="font-size:.5em;padding:.2em .4em;border:1px solid var(--bd2);color:var(--amb);text-decoration:none">⬇</a><button class="del" onclick="delItem('${it.id}')">✕</button></div></div></div>`;
    }).join('');
  }catch(e){}
}

function animateThis(url){
  $('g-vid-src').value=url;
  nav('gen',document.querySelectorAll('.tab')[0]);
  $('g-vid-motion').focus();
}

async function delItem(id){
  if(!confirm('Delete?'))return;
  await fetch(API+'/gallery/'+id,{method:'DELETE'});
  loadGallery();
}

// ─── MODAL ───────────────────────────────────────────────────
let GALLERY_CACHE=[];
function openModal(id){
  fetch(API+'/gallery').then(r=>r.json()).then(items=>{
    GALLERY_CACHE=items;
    const it=items.find(i=>i.id===id);
    if(!it)return;
    const mc=$('modal-content');
    if(it.type==='video')mc.innerHTML=`<video src="${it.url}" controls autoplay style="max-width:90vw;max-height:85vh"></video>`;
    else mc.innerHTML=`<img src="${it.url}" style="max-width:90vw;max-height:85vh">`;
    $('modal-info').textContent=`${it.type} · ${it.model||'?'} · ${it.prompt||''}`;
    $('modal').classList.add('on');
  });
}
function closeModal(){$('modal').classList.remove('on');}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();});

// ─── INIT ────────────────────────────────────────────────────
populateModels();
</script></body></html>"""
