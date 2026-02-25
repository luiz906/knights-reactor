"""
Knights Reactor — Graphics Engine
===================================
Multi-brand image content pipeline.
Brand flow: Select Brand → AI Topic → Quote → Prompt Engine → Image Gen → Caption → Publish

Mounted at /graphics as a FastAPI sub-application.
Uses same brand system from server.py (brands in /var/data/brands/).
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

# ─── PERSISTENT STORAGE ──────────────────────────────────────
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


# ─── BRAND HELPERS ────────────────────────────────────────────
def get_brands() -> list:
    """Read brands from the shared brand system."""
    brands = []
    if not BRANDS_DIR.exists():
        return brands
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


# ─── REPLICATE HELPERS ────────────────────────────────────────
def _rep_create(model: str, inp: dict) -> str:
    for attempt in range(5):
        r = requests.post(f"https://api.replicate.com/v1/models/{model}/predictions",
            headers={"Authorization": f"Bearer {Config.REPLICATE_TOKEN}", "Content-Type": "application/json"},
            json={"input": inp}, timeout=30)
        if r.status_code == 429:
            time.sleep(min(30 * (attempt + 1), 120)); continue
        r.raise_for_status()
        return r.json()["urls"]["get"]
    raise Exception("Replicate rate limit exhausted")

def _rep_poll(url: str, timeout: int = 300) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(url, headers={"Authorization": f"Bearer {Config.REPLICATE_TOKEN}"})
        r.raise_for_status(); data = r.json()
        if data["status"] == "succeeded":
            out = data.get("output")
            return out[0] if isinstance(out, list) else out
        if data["status"] == "failed":
            raise RuntimeError(f"Replicate failed: {data.get('error')}")
        time.sleep(10)
    raise TimeoutError("Replicate timed out")


# ─── R2 UPLOAD ────────────────────────────────────────────────
def _r2_upload(key: str, data: bytes, ct: str) -> str:
    s3 = boto3.client("s3", endpoint_url=Config.R2_ENDPOINT,
        aws_access_key_id=Config.R2_ACCESS_KEY, aws_secret_access_key=Config.R2_SECRET_KEY, region_name="auto")
    s3.put_object(Bucket=Config.R2_BUCKET, Key=key, Body=data, ContentType=ct)
    return f"{Config.R2_PUBLIC_URL}/{key}"


# ─── PIPELINE PHASES ─────────────────────────────────────────
def _gpt(prompt, temp=0.9, max_tok=200):
    r = requests.post("https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {Config.OPENAI_KEY}", "Content-Type": "application/json"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": prompt}],
              "temperature": temp, "max_tokens": max_tok}, timeout=20)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip().strip('"')

def phase_topic(brand):
    return _gpt(f"Generate ONE viral image post topic for '{brand.get('name','')}'. "
                f"Brand: {brand.get('guidelines','')}. Themes: {brand.get('themes','')}. "
                "Return ONLY the topic as a short phrase (5-12 words).", max_tok=80)

def phase_quote(brand, topic):
    return _gpt(f"Write a powerful quote for an image post about: {topic}. "
                f"Brand: {brand.get('name','')}. Tone: {brand.get('tone','Bold')}. "
                "Max 15 words. Punchy, shareable. Return ONLY the quote.", max_tok=60)

def phase_prompt(brand, topic, quote):
    return _gpt(f"Create a detailed image generation prompt for: '{topic}'. "
                f"Style: {brand.get('visual_style','cinematic')}. Context: {brand.get('guidelines','')}. "
                "Social media post background. Include lighting, composition, mood. 1-3 sentences.", max_tok=200)

def phase_image(prompt, model, aspect="1:1"):
    params = {"prompt": prompt, "aspect_ratio": aspect}
    if "flux" in model.lower():
        params["quality"] = "high"
    url = _rep_create(model, params)
    return _rep_poll(url, timeout=120)

def phase_caption(brand, topic, quote):
    text = _gpt(f"Create social media captions for an image post. Brand: {brand.get('name','')}. "
                f"Tone: {brand.get('tone','Bold')}. Topic: {topic}. Quote: {quote}. "
                "Return JSON: {{\"instagram\":\"...\",\"facebook\":\"...\",\"tiktok\":\"...\",\"twitter\":\"...\",\"threads\":\"...\"}}. "
                "ONLY valid JSON, no markdown.", temp=0.8, max_tok=1500)
    raw = re.sub(r'^```json\s*\n?', '', text, flags=re.IGNORECASE)
    raw = re.sub(r'\n?```\s*$', '', raw).strip()
    try: return json.loads(raw)
    except: return {"instagram": topic, "facebook": topic, "twitter": topic}


# ─── JOB TRACKING ─────────────────────────────────────────────
JOBS = {}

def run_job(brand_id, model, aspect):
    brands = get_brands()
    brand = next((b for b in brands if b["id"] == brand_id), None)
    if not brand: return None
    job_id = str(uuid.uuid4())[:8]
    JOBS[job_id] = {"id": job_id, "brand": brand_id, "brand_name": brand["name"],
                    "status": "running", "phase": "topic", "started": datetime.now().isoformat()}

    def worker():
        try:
            JOBS[job_id]["phase"] = "topic"
            topic = phase_topic(brand); JOBS[job_id]["topic"] = topic

            JOBS[job_id]["phase"] = "quote"
            quote = phase_quote(brand, topic); JOBS[job_id]["quote"] = quote

            JOBS[job_id]["phase"] = "prompt"
            img_prompt = phase_prompt(brand, topic, quote); JOBS[job_id]["image_prompt"] = img_prompt

            JOBS[job_id]["phase"] = "image"
            image_url = phase_image(img_prompt, model, aspect); JOBS[job_id]["image_url"] = image_url

            JOBS[job_id]["phase"] = "upload"
            r = requests.get(image_url, timeout=60); r.raise_for_status()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            r2_url = _r2_upload(f"graphics/{brand_id}/{ts}_{job_id}.png", r.content, "image/png")
            JOBS[job_id]["r2_url"] = r2_url

            JOBS[job_id]["phase"] = "caption"
            captions = phase_caption(brand, topic, quote); JOBS[job_id]["captions"] = captions

            gallery = load_json(GFX_GALLERY_FILE, [])
            gallery.insert(0, {"id": job_id, "brand": brand_id, "brand_name": brand["name"],
                "topic": topic, "quote": quote, "image_prompt": img_prompt,
                "image_url": r2_url, "captions": captions, "model": model,
                "aspect": aspect, "created": datetime.now().isoformat()})
            save_json(GFX_GALLERY_FILE, gallery[:500])

            JOBS[job_id]["status"] = "done"; JOBS[job_id]["phase"] = "complete"
            glog.info(f"Graphics job {job_id} done: {topic}")
        except Exception as e:
            JOBS[job_id]["status"] = "failed"; JOBS[job_id]["error"] = str(e)
            glog.error(f"Graphics job {job_id} failed: {e}")

    threading.Thread(target=worker, daemon=True).start()
    return job_id


# ─── API ROUTES ───────────────────────────────────────────────
@gfx_app.get("/api/brands")
async def api_brands():
    return get_brands()

@gfx_app.post("/api/run")
async def api_run(req: Request):
    body = await req.json()
    brand_id = body.get("brand_id", "")
    if not brand_id: return JSONResponse({"error": "No brand"}, 400)
    jid = run_job(brand_id, body.get("model", Config.IMAGE_MODEL), body.get("aspect", "1:1"))
    return {"status": "started", "job_id": jid}

@gfx_app.post("/api/run-all")
async def api_run_all(req: Request):
    body = await req.json()
    model = body.get("model", Config.IMAGE_MODEL); aspect = body.get("aspect", "1:1")
    jobs = [run_job(b["id"], model, aspect) for b in get_brands()]
    return {"status": "started", "jobs": [j for j in jobs if j]}

@gfx_app.get("/api/jobs")
async def api_jobs():
    return list(JOBS.values())

@gfx_app.get("/api/gallery")
async def api_gallery():
    return load_json(GFX_GALLERY_FILE, [])[:100]

@gfx_app.delete("/api/gallery/{item_id}")
async def api_del_gallery(item_id: str):
    g = load_json(GFX_GALLERY_FILE, [])
    save_json(GFX_GALLERY_FILE, [x for x in g if x.get("id") != item_id])
    return {"status": "deleted"}


# ─── STANDALONE DASHBOARD (at /graphics/) ─────────────────────
@gfx_app.get("/", response_class=HTMLResponse)
async def gfx_page():
    return GFX_HTML

GFX_HTML = r"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Graphics Engine</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;800&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
:root{--bg:#08080a;--bg2:#0c0c10;--panel:#0d0d12;--bd:rgba(227,160,40,.12);--bd2:rgba(227,160,40,.06);--amb:#e3a028;--amblo:rgba(227,160,40,.05);--txt:#e3a028;--txtd:#7a5a18;--txtdd:#3a2a08;--grn:#28e060;--grn2:rgba(40,224,96,.08);--red:#e04028;--red2:rgba(224,64,40,.08);--blu:#28a0e0;--wht:#c8c0a8;--f1:'Orbitron',monospace;--f3:'Share Tech Mono',monospace}
*{margin:0;padding:0;box-sizing:border-box}body{background:var(--bg);color:var(--txt);font-family:var(--f3);min-height:100vh}
.wrap{max-width:1100px;margin:0 auto;padding:12px}
.hdr{display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--bd);margin-bottom:12px}
.hdr h1{font-family:var(--f1);font-size:.85em;font-weight:800;letter-spacing:.15em}
.hdr a{color:var(--txtd);font-size:.65em;text-decoration:none;letter-spacing:.1em}.hdr a:hover{color:var(--amb)}
.tabs{display:flex;gap:2px;border-bottom:1px solid var(--bd2);margin-bottom:12px}
.tab{font-family:var(--f1);font-size:.55em;color:var(--txtd);background:none;border:none;border-bottom:2px solid transparent;padding:.6em .8em;cursor:pointer;letter-spacing:.12em}.tab:hover{color:var(--amb)}.tab.on{color:var(--amb);border-bottom-color:var(--amb)}
.page{display:none}.page.on{display:block}
.card{background:var(--panel);border:1px solid var(--bd2);padding:.8em;margin-bottom:.5em}
.card-t{font-family:var(--f1);font-size:.6em;font-weight:600;letter-spacing:.12em;color:var(--txtd);margin-bottom:.5em}
.row{display:grid;grid-template-columns:1fr 1fr;gap:.8em}@media(max-width:600px){.row{grid-template-columns:1fr}}
.fi{margin-bottom:.5em}.lbl{font-size:.6em;color:var(--txtd);letter-spacing:.1em;margin-bottom:.2em;text-transform:uppercase}
.inp{width:100%;padding:.5em .6em;background:var(--bg);border:1px solid var(--bd2);color:var(--amb);font-family:var(--f3);font-size:.85em;outline:none}.inp:focus{border-color:var(--amb)}select.inp{-webkit-appearance:none;appearance:none;cursor:pointer}
.btn{font-family:var(--f1);font-size:.55em;padding:.5em 1em;border:none;cursor:pointer;letter-spacing:.12em}
.btn-go{background:var(--amb);color:var(--bg)}.btn-go:hover{box-shadow:0 0 10px rgba(227,160,40,.3)}
.btn-out{background:none;border:1px solid var(--bd);color:var(--amb)}.btn-out:hover{background:var(--amblo)}
.gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px}
.gi{background:var(--panel);border:1px solid var(--bd2);overflow:hidden;position:relative;cursor:pointer}.gi img{width:100%;display:block}.gi:hover{border-color:var(--amb)}
.gi-info{padding:4px 6px;font-size:.55em;color:var(--txtd)}
.gi-del{position:absolute;top:3px;right:3px;background:rgba(8,8,10,.85);border:1px solid var(--bd);color:var(--red);font-size:.55em;padding:2px 5px;cursor:pointer;display:none}.gi:hover .gi-del{display:block}
.job{background:var(--panel);border:1px solid var(--bd2);padding:.6em;margin-bottom:4px;display:flex;align-items:center;gap:.6em}
.jd{width:.5em;height:.5em;border-radius:50%}.jd-r{background:var(--blu);animation:pulse 1.2s infinite}.jd-d{background:var(--grn)}.jd-f{background:var(--red)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.mbg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.9);z-index:999;align-items:center;justify-content:center;flex-direction:column}.mbg.show{display:flex}
.mimg{max-width:90vw;max-height:80vh;object-fit:contain}
.mx{position:fixed;top:12px;right:16px;background:none;border:none;color:var(--amb);font-size:1.5em;cursor:pointer;z-index:1000}
.minfo{color:var(--wht);font-size:.7em;margin-top:8px;text-align:center;max-width:80vw}
</style></head><body>
<div class="wrap">
<div class="hdr"><h1>GRAPHICS ENGINE</h1><a href="/">← VIDEO PIPELINE</a></div>
<div class="tabs">
<button class="tab on" onclick="gN('run',this)">▶ RUN</button>
<button class="tab" onclick="gN('gallery',this)">◉ GALLERY</button>
<button class="tab" onclick="gN('jobs',this)">◈ JOBS</button>
</div>
<div class="page on" id="p-run">
  <div class="card"><div class="card-t">GENERATE IMAGE POST</div>
    <div class="row"><div>
      <div class="fi"><div class="lbl">BRAND</div><select class="inp" id="r-brand"></select></div>
      <div class="fi"><div class="lbl">IMAGE MODEL</div><select class="inp" id="r-model">
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
    </div><div>
      <div class="fi"><div class="lbl">ASPECT RATIO</div><select class="inp" id="r-aspect">
        <option value="1:1">1:1 Square</option><option value="9:16">9:16 Vertical</option>
        <option value="4:5">4:5 Portrait</option><option value="16:9">16:9 Landscape</option>
      </select></div>
      <div style="display:flex;gap:6px;margin-top:1.2em">
        <button class="btn btn-go" style="flex:1" onclick="runOne()">▶ RUN SELECTED</button>
        <button class="btn btn-out" onclick="runAll()">◈ ALL BRANDS</button>
      </div>
    </div></div>
  </div>
  <div id="r-live"></div>
</div>
<div class="page" id="p-gallery">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5em">
    <span style="font-family:var(--f1);font-size:.6em;letter-spacing:.12em;color:var(--txtd)">GENERATED IMAGES</span>
    <span id="g-count" style="font-size:.55em;color:var(--txtdd)"></span></div>
  <div class="gal" id="g-grid"></div>
</div>
<div class="page" id="p-jobs">
  <div style="font-family:var(--f1);font-size:.6em;letter-spacing:.12em;color:var(--txtd);margin-bottom:.5em">PIPELINE JOBS</div>
  <div id="j-list"></div>
</div>
<div class="mbg" id="modal" onclick="if(event.target===this)cM()">
  <button class="mx" onclick="cM()">✕</button>
  <img class="mimg" id="m-img"><div class="minfo" id="m-info"></div>
</div>
</div>
<script>
const $=id=>document.getElementById(id),API='/graphics/api';let PT=null;
function gN(p,b){document.querySelectorAll('.page').forEach(e=>e.classList.remove('on'));document.querySelectorAll('.tab').forEach(b=>b.classList.remove('on'));$('p-'+p).classList.add('on');if(b)b.classList.add('on');if(p==='gallery')lG();if(p==='jobs')lJ();}
async function lB(){try{const b=await(await fetch(API+'/brands')).json();$('r-brand').innerHTML=b.map(x=>`<option value="${x.id}">${x.name}</option>`).join('')||'<option>No brands</option>';}catch(e){}}
async function runOne(){const b=$('r-brand').value;if(!b){alert('Select a brand');return;}const r=await(await fetch(API+'/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({brand_id:b,model:$('r-model').value,aspect:$('r-aspect').value})})).json();if(r.job_id){$('r-live').innerHTML=`<div class="card" style="border-left:3px solid var(--blu)"><span style="font-size:.7em;color:var(--blu)">⏳ Job started...</span></div>`;sP();}}
async function runAll(){const r=await(await fetch(API+'/run-all',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:$('r-model').value,aspect:$('r-aspect').value})})).json();if(r.jobs){$('r-live').innerHTML=`<div class="card" style="border-left:3px solid var(--blu)"><span style="font-size:.7em;color:var(--blu)">⏳ ${r.jobs.length} jobs started...</span></div>`;sP();}}
function sP(){if(PT)clearInterval(PT);PT=setInterval(pJ,3000);pJ();}
async function pJ(){try{const jobs=await(await fetch(API+'/jobs')).json();rJ(jobs);const a=jobs.filter(j=>j.status==='running');if(a.length){$('r-live').innerHTML=a.map(j=>`<div class="card" style="border-left:3px solid var(--blu)"><span style="font-size:.7em;color:var(--blu)">⏳ ${j.brand_name||j.brand} — ${j.phase||'...'}</span></div>`).join('');}else{const l=jobs.filter(j=>j.status==='done').sort((a,b)=>(b.started||'').localeCompare(a.started||''));if(l.length){const j=l[0];$('r-live').innerHTML=`<div class="card" style="border-left:3px solid var(--grn)"><div style="font-size:.7em;color:var(--grn);margin-bottom:.3em">✓ ${j.brand_name} — ${j.topic||'Done'}</div>${j.r2_url?`<img src="${j.r2_url}" style="max-width:200px;border:1px solid var(--bd)">`:''}<div style="font-size:.6em;color:var(--txtd);margin-top:.2em">${j.quote||''}</div></div>`;}if(PT){clearInterval(PT);PT=null;}}}catch(e){}}
function rJ(jobs){const el=$('j-list');if(!jobs.length){el.innerHTML='<div class="card" style="color:var(--txtd);font-size:.7em">No jobs yet</div>';return;}el.innerHTML=jobs.slice(0,50).map(j=>{const c=j.status==='running'?'jd-r':j.status==='done'?'jd-d':'jd-f';const tc=j.status==='running'?'var(--blu)':j.status==='done'?'var(--grn)':'var(--red)';return`<div class="job"><span class="jd ${c}"></span><div style="flex:1"><div style="font-size:.7em;color:${tc}">${j.brand_name||j.brand} — ${j.status} ${j.phase?'('+j.phase+')':''}</div><div style="font-size:.55em;color:var(--txtd)">${j.topic||''}</div></div>${j.error?`<span style="font-size:.55em;color:var(--red)">${j.error.substring(0,60)}</span>`:''}</div>`;}).join('');}
async function lJ(){try{rJ(await(await fetch(API+'/jobs')).json());}catch(e){}}
async function lG(){try{const items=await(await fetch(API+'/gallery')).json();$('g-count').textContent=items.length+' images';if(!items.length){$('g-grid').innerHTML='<div style="color:var(--txtd);font-size:.7em;padding:2em;text-align:center">No images yet</div>';return;}$('g-grid').innerHTML=items.map(g=>`<div class="gi" onclick="sM('${g.image_url}','${(g.quote||'').replace(/'/g,"\\'")}','${(g.topic||'').replace(/'/g,"\\'")}')"><img src="${g.image_url}" loading="lazy"><div class="gi-info">${g.brand_name||g.brand} · ${(g.topic||'').substring(0,30)}</div><div class="gi-del" onclick="event.stopPropagation();dG('${g.id}')">✕</div></div>`).join('');}catch(e){}}
async function dG(id){if(!confirm('Delete?'))return;await fetch(API+'/gallery/'+id,{method:'DELETE'});lG();}
function sM(u,q,t){$('modal').classList.add('show');$('m-img').src=u;$('m-info').textContent=(q||'')+(t?' — '+t:'');}
function cM(){$('modal').classList.remove('show');}
lB();
</script></body></html>"""
