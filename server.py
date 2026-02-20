"""
Knights Reactor — Web Server v2
Full admin dashboard: Pipeline, Runs, Logs, Settings, Credentials, Health
"""

import json, os, threading, time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse

from pipeline import run_pipeline, Config
import secrets

app = FastAPI(title="Knights Reactor")

# Session token (regenerates on restart, lives in memory)
SESSION_TOKEN = secrets.token_hex(32)

# ─── PERSISTENT STORAGE ──────────────────────────────────────
DATA_DIR = Path("/var/data") if Path("/var/data").exists() else Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
CREDS_FILE = DATA_DIR / "credentials.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
RUNS_FILE = DATA_DIR / "runs.json"

def load_json(path, default=None):
    if path.exists():
        try: return json.loads(path.read_text())
        except: pass
    return default if default is not None else {}

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))

def apply_credentials():
    creds = load_json(CREDS_FILE, {})
    for key, val in creds.items():
        if val and isinstance(val, str) and val.strip():
            os.environ[key] = val.strip()
    Config.OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
    Config.REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
    Config.ELEVEN_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    Config.ELEVEN_VOICE = os.getenv("ELEVENLABS_VOICE_ID", "bwCXcoVxWNYMlC6Esa8u")
    Config.SHOTSTACK_KEY = os.getenv("SHOTSTACK_API_KEY", "")
    Config.R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY", "")
    Config.R2_SECRET_KEY = os.getenv("R2_SECRET_KEY", "")
    Config.R2_ENDPOINT = os.getenv("R2_ENDPOINT", "")
    Config.R2_BUCKET = os.getenv("R2_BUCKET", "knights-videos")
    Config.R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "")
    Config.AIRTABLE_KEY = os.getenv("AIRTABLE_API_KEY", "")
    Config.AIRTABLE_BASE = os.getenv("AIRTABLE_BASE_ID", "")
    Config.AIRTABLE_TABLE = os.getenv("AIRTABLE_TABLE", "Scripture Topics")
    Config.BLOTATO_KEY = os.getenv("BLOTATO_API_KEY", "")

def apply_model_settings():
    """Load ALL settings from saved config into Config."""
    s = load_json(SETTINGS_FILE, {})
    # Image/Video models
    if s.get("image_model"):    Config.IMAGE_MODEL = s["image_model"]
    if s.get("image_quality"):  Config.IMAGE_QUALITY = s["image_quality"]
    if s.get("video_model"):    Config.VIDEO_MODEL = s["video_model"]
    # Script
    if s.get("script_model"):   Config.SCRIPT_MODEL = s["script_model"]
    if s.get("script_temp"):    Config.SCRIPT_TEMP = float(s["script_temp"])
    if s.get("script_words"):   Config.SCRIPT_WORDS = int(float(s["script_words"]))
    # Scene Engine
    if s.get("scene_style"):    Config.SCENE_STYLE = s["scene_style"]
    if s.get("scene_camera"):   Config.SCENE_CAMERA = s["scene_camera"]
    if s.get("scene_mood"):     Config.SCENE_MOOD_BIAS = s["scene_mood"]
    # Voice
    if s.get("voice_model"):    Config.VOICE_MODEL = s["voice_model"]
    if s.get("voice_stability"):Config.VOICE_STABILITY = float(s["voice_stability"])
    if s.get("voice_similarity"):Config.VOICE_SIMILARITY = float(s["voice_similarity"])
    if s.get("voice_speed"):    Config.VOICE_SPEED = float(s["voice_speed"])
    if s.get("voice_style"):    Config.VOICE_STYLE = float(s["voice_style"])
    if s.get("voice_id"):       Config.VOICE_ID = s["voice_id"]
    # Video clips
    if s.get("clip_count"):     Config.CLIP_COUNT = int(s["clip_count"])
    if s.get("clip_duration"):  Config.CLIP_DURATION = float(s["clip_duration"])
    # Render
    if s.get("render_fps"):     Config.RENDER_FPS = int(s["render_fps"])
    if s.get("render_res"):     Config.RENDER_RES = s["render_res"]
    if s.get("render_aspect"):  Config.RENDER_ASPECT = s["render_aspect"]
    if s.get("render_bg"):      Config.RENDER_BG = s["render_bg"]
    # Logo/Watermark
    if s.get("logo_url"):       Config.LOGO_URL = s["logo_url"]
    if s.get("logo_enabled"):   Config.LOGO_ENABLED = s["logo_enabled"] in (True, "true", "True")
    if s.get("logo_position"):  Config.LOGO_POSITION = s["logo_position"]
    if s.get("logo_scale"):     Config.LOGO_SCALE = float(s["logo_scale"])
    if s.get("logo_opacity"):   Config.LOGO_OPACITY = float(s["logo_opacity"])
    # Video timeout
    if s.get("video_timeout"):  Config.VIDEO_TIMEOUT = int(s["video_timeout"])
    # CTA clip
    if s.get("cta_enabled") is not None: Config.CTA_ENABLED = s["cta_enabled"] in (True, "true", "True")
    if s.get("cta_url"):        Config.CTA_URL = s["cta_url"]
    if s.get("cta_duration"):   Config.CTA_DURATION = float(s["cta_duration"])
    # Shotstack
    if s.get("shotstack_env"):  Config.SHOTSTACK_ENV = s["shotstack_env"]
    # Platforms
    for pk in ["on_tt","on_yt","on_ig","on_fb","on_tw","on_th","on_pn"]:
        if pk in s: setattr(Config, pk.upper(), s[pk] in (True, "true", "True"))

apply_credentials()
apply_model_settings()

# ─── STATE ────────────────────────────────────────────────────
RUNS = load_json(RUNS_FILE, []) if RUNS_FILE.exists() else []
CURRENT_RUN = {"active": False, "result": None, "phase": 0, "phase_name": "", "phases_done": []}
LOGS = []

# Restore last failed run state so Resume works after restart/deploy
if RUNS:
    _last_run = RUNS[0]  # most recent
    if _last_run.get("status") in ("failed", "error"):
        _fp = _last_run.get("failed_phase", 0)
        CURRENT_RUN["result"] = {"status": "failed", "failed_phase": _fp, "error": _last_run.get("error", "Previous run failed")}
        CURRENT_RUN["phases_done"] = list(range(_fp))

def log_entry(phase, level, msg):
    LOGS.append({"t": datetime.now().strftime("%H:%M:%S"), "phase": phase, "level": level, "msg": msg})
    if len(LOGS) > 500: LOGS.pop(0)

def execute_pipeline(resume_from: int = 0):
    apply_model_settings()  # Reload model selections before each run
    CURRENT_RUN.update({"active": True, "started": datetime.now().isoformat(), "result": None, "phase": 0, "phase_name": "", "phases_done": []})
    if resume_from == 0:
        LOGS.clear()
    log_entry("System", "info", f"Pipeline {'resumed from phase ' + str(resume_from) if resume_from else 'started'}")

    def on_phase(phase_index, phase_name, status):
        if status == "running":
            CURRENT_RUN["phase"] = phase_index
            CURRENT_RUN["phase_name"] = phase_name
            log_entry(phase_name, "info", f"Starting...")
        elif status == "done":
            if phase_index not in CURRENT_RUN["phases_done"]:
                CURRENT_RUN["phases_done"].append(phase_index)
            log_entry(phase_name, "ok", f"Complete ✓")

    result = run_pipeline(progress_cb=on_phase, resume_from=resume_from)
    CURRENT_RUN.update({"active": False, "result": result})
    run_entry = {
        "id": len(RUNS) + 1, "date": datetime.now().strftime("%b %d, %I:%M %p"),
        "topic": result.get("topic", {}).get("idea", "Unknown"),
        "category": result.get("topic", {}).get("category", ""),
        "status": result.get("status", "failed"), "duration": result.get("duration", "?"),
        "error": result.get("error"), "failed_phase": result.get("failed_phase", 0),
    }
    RUNS.insert(0, run_entry)
    save_json(RUNS_FILE, RUNS[:100])
    log_entry("System", "ok" if result.get("status") == "published" else "error", f"Pipeline finished: {result.get('status')}")

# ─── API ──────────────────────────────────────────────────────

# ─── GITHUB AUTO-DEPLOY ──────────────────────────────────────
@app.post("/api/deploy")
async def deploy_files(req: Request):
    """Accept file updates and commit them to GitHub.
    Body: {"files": {"pipeline.py": "content...", "server.py": "content..."}, "message": "commit msg"}
    Requires GITHUB_TOKEN env var (Personal Access Token with repo scope).
    """
    import base64 as b64
    body = await req.json()
    files = body.get("files", {})
    message = body.get("message", "Auto-deploy from Claude")
    
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        return JSONResponse({"error": "GITHUB_TOKEN not set in environment"}, 400)
    
    repo = "luiz906/knights-reactor"
    api = f"https://api.github.com/repos/{repo}/contents"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }
    
    import requests as rq
    results = {}
    for filename, content in files.items():
        # Get current file SHA (needed for updates)
        sha = None
        try:
            r = rq.get(f"{api}/{filename}", headers=headers, timeout=15)
            if r.status_code == 200:
                sha = r.json().get("sha")
        except:
            pass
        
        # Commit the file
        payload = {
            "message": f"{message} [{filename}]",
            "content": b64.b64encode(content.encode("utf-8")).decode("utf-8"),
        }
        if sha:
            payload["sha"] = sha  # Update existing file
        
        try:
            r = rq.put(f"{api}/{filename}", headers=headers, json=payload, timeout=30)
            if r.status_code in (200, 201):
                results[filename] = "committed"
            else:
                results[filename] = f"failed: {r.status_code} {r.text[:200]}"
        except Exception as e:
            results[filename] = f"error: {str(e)}"
    
    return {"status": "deployed", "files": results, "message": message}

@app.post("/api/run")
async def trigger_run(bg: BackgroundTasks):
    if CURRENT_RUN["active"]: return JSONResponse({"error": "Already running"}, 409)
    bg.add_task(execute_pipeline, 0)
    return {"status": "started"}

@app.post("/api/resume")
async def trigger_resume(bg: BackgroundTasks):
    """Resume pipeline from the last failed phase."""
    if CURRENT_RUN["active"]: return JSONResponse({"error": "Already running"}, 409)
    # Determine which phase to resume from
    last_result = CURRENT_RUN.get("result", {}) or {}
    failed_phase = last_result.get("failed_phase", 0)
    # Check checkpoint exists
    import os
    if not os.path.exists("/tmp/pipeline_checkpoint.json") and not os.path.exists(DATA_DIR / "pipeline_checkpoint.json"):
        return JSONResponse({"error": "No checkpoint found — run fresh pipeline instead"}, 400)
    bg.add_task(execute_pipeline, failed_phase)
    return {"status": "resuming", "from_phase": failed_phase}

@app.get("/api/status")
async def get_status():
    return {"running": CURRENT_RUN["active"], "phase": CURRENT_RUN.get("phase", 0),
            "phase_name": CURRENT_RUN.get("phase_name", ""), "phases_done": CURRENT_RUN.get("phases_done", []),
            "result": CURRENT_RUN.get("result")}

@app.get("/api/runs")
async def get_runs(): return RUNS[:50]

@app.get("/api/logs")
async def get_logs(): return LOGS[-200:]

@app.get("/api/config")
async def get_config():
    return {"openai": bool(Config.OPENAI_KEY), "replicate": bool(Config.REPLICATE_TOKEN),
            "elevenlabs": bool(Config.ELEVEN_KEY), "shotstack": bool(Config.SHOTSTACK_KEY),
            "r2": bool(Config.R2_ACCESS_KEY), "airtable": bool(Config.AIRTABLE_KEY), "blotato": bool(Config.BLOTATO_KEY)}

@app.get("/api/credentials")
async def get_credentials():
    """Return which creds are set (True/False only, never actual values)."""
    creds = load_json(CREDS_FILE, {})
    status = {}
    for k, v in creds.items():
        status[k] = bool(v and len(str(v).strip()) > 0)
    return status

@app.post("/api/credentials")
async def save_credentials(req: Request):
    body = await req.json()
    existing = load_json(CREDS_FILE, {})
    for k, v in body.items():
        if v is not None: existing[k] = v
    save_json(CREDS_FILE, existing)
    apply_credentials()
    return {"status": "saved"}

@app.post("/api/login")
async def login(req: Request):
    body = await req.json()
    pw = body.get("password", "")
    token = body.get("token", "")
    correct = os.getenv("ADMIN_PASSWORD", "")
    # Token-based session (survives refresh)
    if token and token == SESSION_TOKEN:
        return {"ok": True, "token": SESSION_TOKEN}
    if pw == correct:
        return {"ok": True, "token": SESSION_TOKEN}
    return JSONResponse({"ok": False, "error": "Wrong password"}, 401)

@app.get("/api/settings")
async def get_settings(): return load_json(SETTINGS_FILE, {})

@app.get("/api/last-result")
async def get_last_result():
    """Return the result of the most recent pipeline run for Preview tab."""
    return CURRENT_RUN.get("result") or {}

@app.post("/api/settings")
async def save_settings(req: Request):
    save_json(SETTINGS_FILE, await req.json())
    apply_model_settings()
    return {"status": "saved"}

@app.post("/api/test-connection")
async def test_conn(req: Request):
    body = await req.json()
    svc = body.get("service", "")
    import requests as rq
    try:
        if svc == "openai":
            r = rq.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {Config.OPENAI_KEY}"}, timeout=10)
            return {"ok": r.status_code == 200}
        if svc == "replicate":
            r = rq.get("https://api.replicate.com/v1/models", headers={"Authorization": f"Bearer {Config.REPLICATE_TOKEN}"}, timeout=10)
            return {"ok": r.status_code == 200}
        if svc == "elevenlabs":
            r = rq.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": Config.ELEVEN_KEY}, timeout=10)
            return {"ok": r.status_code == 200}
        if svc == "airtable":
            r = rq.get(f"https://api.airtable.com/v0/{Config.AIRTABLE_BASE}/{Config.AIRTABLE_TABLE}?maxRecords=1",
                       headers={"Authorization": f"Bearer {Config.AIRTABLE_KEY}"}, timeout=10)
            return {"ok": r.status_code == 200}
        return {"ok": False, "error": "Unknown"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ─── DASHBOARD ────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard(): return HTML

HTML = r"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Knights Reactor</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;800&family=Rajdhani:wght@400;500;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
:root{--bg:#08080a;--bg2:#0c0c10;--bg3:#111118;--panel:#0d0d12;--bd:rgba(227,160,40,.12);--bd2:rgba(227,160,40,.06);--amb:#e3a028;--amb2:#c88a1a;--amblo:rgba(227,160,40,.05);--txt:#e3a028;--txtd:#7a5a18;--txtdd:#3a2a08;--grn:#28e060;--grn2:rgba(40,224,96,.08);--red:#e04028;--red2:rgba(224,64,40,.08);--blu:#28a0e0;--blu2:rgba(40,160,224,.08);--wht:#c8c0a8;--f1:'Orbitron',monospace;--f2:'Rajdhani',sans-serif;--f3:'Share Tech Mono',monospace}
html.light{--bg:#f0ece4;--bg2:#e8e2d8;--bg3:#ddd6c8;--panel:#f5f1ea;--bd:rgba(140,100,20,.18);--bd2:rgba(140,100,20,.1);--amb:#8a6010;--amb2:#6e4c0c;--amblo:rgba(140,100,20,.06);--txt:#8a6010;--txtd:#a0884a;--txtdd:#c4b898;--grn:#1a8a3a;--grn2:rgba(26,138,58,.08);--red:#c03020;--red2:rgba(192,48,32,.08);--blu:#1870b0;--blu2:rgba(24,112,176,.08);--wht:#3a3428}
html.light select.fin option{background:var(--panel);color:var(--amb)}
html.light .login-box{box-shadow:0 2px 20px rgba(0,0,0,.08)}
html.light .sb-exec{color:#fff}
*{margin:0;padding:0;box-sizing:border-box}
html{font-size:clamp(14px,1.25vw,22px)}
body{background:var(--bg);color:var(--txt);font-family:var(--f3);height:100vh;overflow:hidden}
#L{min-height:100vh;display:flex;align-items:center;justify-content:center;background:radial-gradient(ellipse at 50% 30%,rgba(227,160,40,.03),transparent 60%)}
.login-box{width:24em;padding:2.25em 1.7em;text-align:center;background:var(--panel);border:1px solid var(--bd);animation:glow 3s infinite}
::-webkit-scrollbar{width:3px}::-webkit-scrollbar-thumb{background:var(--amb2)}::-webkit-scrollbar-track{background:var(--bg)}
button{font-family:var(--f3);cursor:pointer}input,select{font-family:var(--f3)}.hd{display:none}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
@keyframes scan{0%{top:-100%}100%{top:100%}}
@keyframes glow{0%,100%{box-shadow:0 0 5px rgba(227,160,40,.15)}50%{box-shadow:0 0 15px rgba(227,160,40,.25)}}

/* BADGES */
.bg{font-size:.6em;padding:.15em .5em;display:inline-flex;align-items:center;gap:4px;letter-spacing:1px;text-transform:uppercase}
.bd2{width:.35em;height:.35em}
.bg-g{color:var(--grn);background:var(--grn2);border:1px solid rgba(40,224,96,.15)}.bg-g .bd2{background:var(--grn)}
.bg-r{color:var(--red);background:var(--red2);border:1px solid rgba(224,64,40,.15)}.bg-r .bd2{background:var(--red)}
.bg-b{color:var(--blu);background:var(--blu2);border:1px solid rgba(40,160,224,.15)}.bg-b .bd2{background:var(--blu);animation:pulse 1.2s infinite}
.bg-m{color:var(--txtdd);background:rgba(50,40,16,.08);border:1px solid rgba(50,40,16,.12)}.bg-m .bd2{background:var(--txtdd)}

/* PHASE */
.ph{background:var(--panel);border:1px solid var(--bd2);padding:.7em .85em;border-left:3px solid var(--txtdd);transition:all .3s;position:relative;overflow:hidden;margin-bottom:4px}
.ph.dn{border-left-color:var(--grn);background:rgba(40,224,96,.015)}.ph.rn{border-left-color:var(--blu);background:rgba(40,160,224,.02)}
.ph.rn::after{content:'';position:absolute;top:0;left:0;width:100%;height:2px;background:linear-gradient(90deg,transparent,var(--blu),transparent);animation:scan 2s linear infinite}
.ph.dm{opacity:.25}

/* SETTINGS */
.sec{background:var(--panel);border:1px solid var(--bd2);margin-bottom:.7em}
.sec-h{width:100%;display:flex;align-items:center;justify-content:space-between;padding:1em 1.2em;background:none;border:none;color:var(--txt);cursor:pointer}
.sec-t{font-family:var(--f1);font-size:.85em;font-weight:600;letter-spacing:.15em}.sec-a{font-size:1em;color:var(--txtd);transition:transform .15s}
.sec-b{padding:0 1.2em 1em}.sec-b.shut{display:none}
.fi{padding:.7em 0;border-bottom:1px solid var(--bd2)}
.fl{font-size:.7em;color:var(--txtd);text-transform:uppercase;letter-spacing:.15em;margin-bottom:.35em}
.fin{width:100%;padding:.65em .8em;background:var(--bg);border:1px solid var(--bd2);font-size:.9em;color:var(--amb);outline:none;font-family:var(--f3);border-radius:0}
.fin:focus{border-color:var(--amb);box-shadow:0 0 6px rgba(227,160,40,.1)}
select.fin{-webkit-appearance:none;-moz-appearance:none;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23e3a028'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center;background-color:var(--bg);padding-right:28px;cursor:pointer}
html.light select.fin{background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%238a6010'/%3E%3C/svg%3E")}
select.fin option{background:var(--bg2);color:var(--amb);padding:6px}
.fin-slider{-webkit-appearance:none;appearance:none;background:var(--bg3);border-radius:3px;outline:none;height:.5em;cursor:pointer;width:100%}
.fin-slider::-webkit-slider-thumb{-webkit-appearance:none;width:1.3em;height:1.3em;border-radius:50%;background:var(--amb);border:2px solid var(--bg);cursor:pointer}
.fin-slider::-moz-range-thumb{width:1.3em;height:1.3em;border-radius:50%;background:var(--amb);border:2px solid var(--bg)}
.tg{width:3em;height:1.5em;border-radius:1px;border:1px solid var(--bd);position:relative;transition:background .2s}
.tg.on{background:rgba(40,224,96,.15);border-color:var(--grn)}.tg.off{background:var(--bg);border-color:var(--bd2)}
.td{position:absolute;top:.15em;width:1.15em;height:1.15em;background:var(--amb);transition:left .2s;left:.15em}.tg.on .td{background:var(--grn);left:1.5em}.tg.off .td{left:.15em}
.sv{width:100%;padding:.9em;border:1px solid var(--amb);background:rgba(227,160,40,.06);font-size:.85em;font-weight:600;color:var(--amb);letter-spacing:.2em;font-family:var(--f1);margin-top:1em}
.sv:hover{background:rgba(227,160,40,.12)}
.sm{background:var(--grn2);border:1px solid rgba(40,224,96,.15);padding:.5em .85em;margin-bottom:.55em;font-size:.7em;color:var(--grn)}
.rw{padding:.7em 1em;border-bottom:1px solid var(--bd2)}
.panel{background:var(--panel);border:1px solid var(--bd2);padding:1em;position:relative;overflow:hidden}
.ptitle{font-family:var(--f1);font-size:.6em;font-weight:600;letter-spacing:.15em;color:var(--txtd);margin-bottom:.55em;display:flex;align-items:center;gap:.55em}
.ptitle::before{content:'';width:.2em;height:.7em;background:var(--amb)}
.stat{background:var(--panel);border:1px solid var(--bd2);padding:.7em;text-align:center}
.stat b{font-family:var(--f1);font-size:1.3em;font-weight:800;display:block}
.stat small{font-family:var(--f1);font-size:.5em;letter-spacing:.15em;opacity:.5}
.pgrid{display:grid;gap:6px;margin:8px 0}.pcard{background:var(--bg);border:1px solid var(--bd2);overflow:hidden;position:relative}
.pcard img,.pcard video{width:100%;height:auto;display:block}
.pcard .dl{position:absolute;bottom:3px;right:3px;background:rgba(8,8,10,.85);border:1px solid var(--bd);color:var(--amb);font-size:.55em;padding:.15em .4em;cursor:pointer}
.plbl{font-size:.5em;color:var(--txtd);padding:.2em .4em;letter-spacing:.08em;text-transform:uppercase}
.fvid{border:1px solid var(--amb);padding:2px;background:var(--bg);margin:8px 0}.fvid video{width:100%;display:block}

/* ═══ DESKTOP ═══ */
@media(min-width:769px){
.mob-wrap{display:none!important}
.desk-wrap{display:flex!important;height:100vh}
.sidebar{width:14em;background:var(--bg2);border-right:1px solid var(--bd2);display:flex;flex-direction:column;flex-shrink:0}
.sb-logo{padding:16px 14px;border-bottom:1px solid var(--bd2)}
.sb-logo h1{font-family:var(--f1);font-size:.75em;font-weight:800;color:var(--amb);letter-spacing:.15em;line-height:1.4}
.sb-logo p{font-size:.5em;color:var(--txtd);letter-spacing:.2em;margin-top:.2em}
.sb-nav{flex:1;padding:8px 0;overflow-y:auto}
.sb-i{width:100%;display:flex;align-items:center;gap:.65em;padding:.65em 1em;background:none;border:none;border-left:3px solid transparent;color:var(--txtd);font-size:.7em;letter-spacing:.08em;transition:all .12s;text-align:left}
.sb-i:hover{color:var(--amb);background:var(--amblo)}
.sb-i.on{color:var(--amb);border-left-color:var(--amb);background:var(--amblo)}
.sb-i span{font-size:.85em;width:1.15em;text-align:center}
.sb-ft{padding:.7em 1em;border-top:1px solid var(--bd2)}
.sb-exec{width:100%;padding:.65em;font-family:var(--f1);font-size:.6em;font-weight:600;letter-spacing:.15em;color:var(--bg);background:var(--amb);border:none;box-shadow:0 0 8px rgba(227,160,40,.2)}
.sb-exec:hover{box-shadow:0 0 16px rgba(227,160,40,.4)}
.sb-res{width:100%;padding:.5em;font-family:var(--f1);font-size:.5em;letter-spacing:.15em;color:var(--amb);background:none;border:1px solid var(--bd);margin-top:5px;display:none}
.dmain{flex:1;display:flex;flex-direction:column;overflow:hidden}
.topbar{height:3em;background:var(--bg2);border-bottom:1px solid var(--bd2);display:flex;align-items:center;justify-content:space-between;padding:0 1.25em;flex-shrink:0}
.topbar-t{font-family:var(--f1);font-size:.65em;letter-spacing:.15em;color:var(--txtd)}
.topbar-s{display:flex;align-items:center;gap:10px}
.topbar-ph{font-size:.65em;color:var(--blu);letter-spacing:.08em}
.topbar-pb{width:7em;height:.2em;background:var(--bg);border:1px solid var(--bd2);overflow:hidden}
.topbar-pb div{height:100%;background:var(--amb);transition:width .6s}
.dcontent{flex:1;overflow-y:auto;padding:1.15em}
.dpage{display:none}.dpage.on{display:block}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:.7em}
.g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:.7em}
.g4{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:.55em}
.phgrid{display:grid;grid-template-columns:1fr 1fr;gap:.35em}
.sec-b{display:grid;grid-template-columns:1fr 1fr;gap:.2em 1.5em}
.sec{margin-bottom:.7em}
.sec-h{padding:1.1em 1.4em}
.sec-t{font-size:1em}
.sec-a{font-size:1.2em}
.fi{padding:.8em 0}
.fl{font-size:.7em;margin-bottom:.35em}
.fin{font-size:.9em;padding:.6em .75em}
select.fin{padding-right:2em}
.fi.w{grid-column:1/-1}
.sv{font-size:.85em;padding:.9em;letter-spacing:.2em}
.sm{font-size:.8em;padding:.6em 1em}
.tg{width:2.8em;height:1.4em;border-radius:2px}
.td{width:1em;height:1em;top:.15em}
.tg.on .td{left:1.5em}
.tg.off .td{left:.2em}
.fi.w{grid-column:1/-1}
.pgrid{grid-template-columns:repeat(4,1fr)}
.logp{background:var(--panel);border:1px solid var(--bd2);padding:12px;max-height:calc(100vh - 8em);overflow-y:auto;font-size:.7em;line-height:1.8}
}

/* ═══ MOBILE ═══ */
@media(max-width:768px){
.desk-wrap{display:none!important}
.mob-wrap{display:block!important}
body{overflow:auto}
.mhdr{padding:12px;border-bottom:1px solid var(--bd);background:var(--bg2);display:flex;align-items:center;justify-content:space-between}
.mhdr h1{font-family:var(--f1);font-size:.8em;font-weight:800;color:var(--amb);letter-spacing:.15em}
.mexec{font-family:var(--f1);font-size:.6em;font-weight:600;color:var(--bg);background:var(--amb);border:none;padding:.7em 1em;letter-spacing:.15em}
.mres{font-family:var(--f1);font-size:.6em;color:var(--amb);background:none;border:1px solid var(--amb);padding:.7em;letter-spacing:.15em;display:none;margin-left:.35em}
.mprog{height:2px;background:var(--bd2);overflow:hidden}.mprog div{height:100%;background:var(--amb);transition:width .6s}
.mtabs{display:flex;border-bottom:1px solid var(--bd);background:var(--bg2);overflow-x:auto;-webkit-overflow-scrolling:touch}
.mt{font-family:var(--f1);font-size:.55em;color:var(--txtd);background:none;border:none;border-bottom:2px solid transparent;padding:.75em .65em;white-space:nowrap;letter-spacing:1.5px;min-height:3em}
.mt:hover{color:var(--amb)}.mt.on{color:var(--amb);font-weight:600;border-bottom-color:var(--amb)}
.mcont{padding:10px}
.mpage{display:none}.mpage.on{display:block}
.g4m{display:grid;grid-template-columns:1fr 1fr;gap:.3em;margin-bottom:.55em}
.sec-b{display:block}
.fin{font-size:1em;padding:.7em .85em;min-height:3em}
.tg{width:3.4em;height:1.85em}.td{top:.2em;width:1.4em;height:1.4em}
.tg.on .td{left:1.7em!important}.tg.off .td{left:.2em!important}
.sec-h{min-height:3.2em}
.pgrid{grid-template-columns:repeat(2,1fr)}
.logp{max-height:28em;overflow-y:auto;font-size:.7em;line-height:1.8;background:var(--panel);border:1px solid var(--bd2);padding:10px}
}
</style></head><body>

<div id="L"><div class="login-box">
<div style="font-family:var(--f1);font-size:.5em;color:var(--txtd);letter-spacing:5px;margin-bottom:6px">SYSTEM ACCESS</div>
<div style="font-family:var(--f1);font-size:1.15em;font-weight:800;color:var(--amb);letter-spacing:3px;margin-bottom:3px">KNIGHTS REACTOR</div>
<div style="font-size:.55em;color:var(--txtd);letter-spacing:.3em;margin-bottom:1.4em">/// CONTROL v6.0 ///</div>
<div style="width:2.8em;height:2px;background:var(--amb);margin:0 auto 1.15em"></div>
<input type="password" id="pw" style="width:100%;padding:.7em;background:var(--bg);border:1px solid var(--bd);font-size:.85em;color:var(--amb);outline:none;margin-bottom:.55em;text-align:center;letter-spacing:3px" placeholder="ACCESS CODE" onkeydown="event.key==='Enter'&&go()">
<div id="le" class="hd" style="font-size:.65em;color:var(--red);margin-bottom:.4em">ACCESS DENIED</div>
<button onclick="go()" style="width:100%;padding:10px;border:1px solid var(--amb);background:rgba(227,160,40,.06);font-family:var(--f1);font-size:.65em;font-weight:600;color:var(--amb);letter-spacing:.2em">AUTHENTICATE</button>
</div></div>

<div id="A" class="hd">
<div class="desk-wrap">
<div class="sidebar">
<div class="sb-logo"><h1>KNIGHTS<br>REACTOR</h1><p>CONTROL v6.0</p></div>
<div class="sb-nav">
<button class="sb-i on" onclick="dNav('pipeline',this)"><span>⚡</span>PIPELINE</button>
<button class="sb-i" onclick="dNav('runs',this)"><span>◈</span>RUNS</button>
<button class="sb-i" onclick="dNav('logs',this)"><span>▤</span>LOGS</button>
<button class="sb-i" onclick="dNav('preview',this)"><span>◉</span>PREVIEW</button>
<button class="sb-i" onclick="dNav('settings',this)"><span>⚙</span>CONFIG</button>
<button class="sb-i" onclick="dNav('health',this)"><span>◎</span>STATUS</button>
</div>
<div class="sb-ft">
<button class="sb-exec" id="d-rb" onclick="runNow()">▶ EXECUTE</button>
<button class="sb-res" id="d-rsb" onclick="resumeNow()">♻ RESUME</button>
<button id="d-thm" onclick="toggleTheme()" style="width:100%;padding:6px;margin-top:6px;font-size:.55em;letter-spacing:.15em;color:var(--txtd);background:none;border:1px solid var(--bd2);font-family:var(--f1)">☀ LIGHT MODE</button>
</div>
</div>
<div class="dmain">
<div class="topbar"><div class="topbar-t" id="d-title">⚡ PIPELINE MONITOR</div><div class="topbar-s"><span class="topbar-ph" id="d-ph"></span><div class="topbar-pb"><div id="d-pb"></div></div></div></div>
<div class="dcontent">

<div class="dpage on" id="dp-pipeline"><div class="g4" id="d-stats" style="margin-bottom:12px"></div><div class="phgrid" id="d-pl"></div></div>

<div class="dpage" id="dp-runs"><div class="g4" id="d-rs" style="margin-bottom:12px"></div><div class="panel" id="d-rl"></div></div>

<div class="dpage" id="dp-logs"><div style="display:flex;justify-content:space-between;margin-bottom:6px"><span class="ptitle" style="margin:0">SYSTEM LOGS</span><span id="d-lc" style="font-size:.65em;color:var(--txtd)"></span></div><div class="logp" id="d-la"></div></div>

<div class="dpage" id="dp-preview">
<div id="d-pve" class="panel" style="padding:30px;text-align:center"><div style="font-size:.7em;color:var(--txtd);letter-spacing:.15em">NO ASSETS YET</div><div style="font-size:.65em;color:var(--txtdd);margin-top:.3em">Execute pipeline to generate media</div></div>
<div id="d-pvi" class="hd"><div class="ptitle">IMAGES</div><div id="d-pig" class="pgrid"></div></div>
<div id="d-pvv" class="hd"><div class="ptitle" style="margin-top:12px">CLIPS</div><div id="d-pvg" class="pgrid"></div></div>
<div id="d-pvf" class="hd"><div class="ptitle" style="margin-top:12px;color:var(--grn)">FINAL RENDER</div><div class="fvid"><video id="d-fv" controls></video></div><a id="d-fd" href="#" download style="display:block;text-align:center;padding:8px;border:1px solid var(--amb);background:var(--amblo);color:var(--amb);font-family:var(--f1);font-size:.6em;letter-spacing:.15em;text-decoration:none;margin-top:.3em">⬇ DOWNLOAD</a></div>
<div id="d-pvs" class="hd" style="margin-top:12px"><div class="ptitle">SCRIPT</div><div id="d-pst" class="panel" style="font-size:.8em;color:var(--wht);line-height:1.7"></div></div>
</div>

<div class="dpage" id="dp-settings"><div id="d-ss" class="sm hd">✓ SAVED</div><div id="d-sf"></div><button class="sv" onclick="saveSett()">SAVE CONFIGURATION</button></div>

<div class="dpage" id="dp-health">
<div class="panel" id="d-hl" style="margin-bottom:10px"></div>
<div class="panel" style="padding:12px"><div class="ptitle">DIAGNOSTICS</div><button style="width:100%;padding:10px;background:var(--bg);border:1px solid var(--bd2);color:var(--amb);font-size:.8em" onclick="testAll()">TEST ALL CONNECTIONS →</button></div>
<button onclick="sessionStorage.removeItem('kt');$('L').style.display='flex';$('A').classList.add('hd')" style="width:100%;padding:9px;margin-top:10px;border:1px solid rgba(224,64,40,.2);background:var(--red2);font-family:var(--f1);font-size:.6em;color:var(--red);letter-spacing:.2em">⚠ DISCONNECT</button>
</div>

</div></div></div>

<div class="mob-wrap">
<div class="mhdr"><h1>KNIGHTS REACTOR</h1><div style="display:flex;align-items:center;gap:6px"><button id="m-thm" onclick="toggleTheme()" style="font-size:.85em;background:none;border:1px solid var(--bd2);color:var(--txtd);padding:.4em .55em;min-height:2.5em">☀</button><button class="mexec" id="m-rb" onclick="runNow()">▶ EXECUTE</button><button class="mres" id="m-rsb" onclick="resumeNow()">♻</button></div></div>
<div class="mprog" id="m-prog"><div id="m-pb"></div></div>
<div class="mtabs">
<button class="mt on" onclick="mNav('pipeline',this)">⚡ PIPELINE</button>
<button class="mt" onclick="mNav('runs',this)">◈ RUNS</button>
<button class="mt" onclick="mNav('logs',this)">▤ LOGS</button>
<button class="mt" onclick="mNav('preview',this)">◉ PREVIEW</button>
<button class="mt" onclick="mNav('settings',this)">⚙ CONFIG</button>
<button class="mt" onclick="mNav('health',this)">◎ STATUS</button>
</div>
<div class="mcont">

<div class="mpage on" id="mp-pipeline"><div id="m-pl"></div></div>

<div class="mpage" id="mp-runs"><div class="g4m" id="m-rs"></div><div class="panel" id="m-rl"></div></div>

<div class="mpage" id="mp-logs"><div class="logp" id="m-la"></div></div>

<div class="mpage" id="mp-preview">
<div id="m-pve" class="panel" style="padding:20px;text-align:center"><div style="font-size:.7em;color:var(--txtd)">NO ASSETS YET</div></div>
<div id="m-pvi" class="hd"><div style="font-family:var(--f1);font-size:.6em;color:var(--amb);letter-spacing:.15em;margin-bottom:.3em">IMAGES</div><div id="m-pig" class="pgrid"></div></div>
<div id="m-pvv" class="hd"><div style="font-family:var(--f1);font-size:.6em;color:var(--amb);letter-spacing:.15em;margin:.7em 0 .3em">CLIPS</div><div id="m-pvg" class="pgrid"></div></div>
<div id="m-pvf" class="hd"><div class="fvid"><video id="m-fv" controls></video></div><a id="m-fd" href="#" download style="display:block;text-align:center;padding:10px;border:1px solid var(--amb);background:var(--amblo);color:var(--amb);font-family:var(--f1);font-size:.65em;letter-spacing:.15em;text-decoration:none;margin-top:.3em">⬇ DOWNLOAD</a></div>
<div id="m-pvs" class="hd" style="margin-top:10px"><div id="m-pst" class="panel" style="font-size:.8em;color:var(--wht);line-height:1.7"></div></div>
</div>

<div class="mpage" id="mp-settings"><div id="m-ss" class="sm hd">✓ SAVED</div><div id="m-sf"></div><button class="sv" onclick="saveSett()">SAVE CONFIGURATION</button></div>

<div class="mpage" id="mp-health">
<div class="panel" id="m-hl" style="margin-bottom:8px"></div>
<button style="width:100%;padding:12px;background:var(--bg);border:1px solid var(--bd2);color:var(--amb);font-size:.8em;min-height:3.2em" onclick="testAll()">TEST ALL CONNECTIONS →</button>
<button onclick="sessionStorage.removeItem('kt');$('L').style.display='flex';$('A').classList.add('hd')" style="width:100%;padding:12px;margin-top:8px;border:1px solid rgba(224,64,40,.2);background:var(--red2);font-family:var(--f1);font-size:.65em;color:var(--red);letter-spacing:.2em;min-height:3.2em">⚠ DISCONNECT</button>
</div>

</div></div>
</div>

<script>
let RN=false,PH=0,PD=[],ST={},LAST_RESULT=null;
const $=id=>document.getElementById(id);
const B=(s,l)=>{const c={done:'g',running:'b',failed:'r',configured:'g',missing:'r',warning:'o',waiting:'m'}[s]||'m';return`<span class="bg bg-${c}"><span class="bd2"></span>${l||s}</span>`};
const PHS=[{n:"FETCH TOPIC",a:"AIRTABLE",i:"⬡",d:"~2s"},{n:"GENERATE SCRIPT",a:"GPT-4o",i:"⬢",d:"~3s"},{n:"SCENE ENGINE",a:"LOCAL",i:"◈",d:"<1s"},{n:"GENERATE IMAGES",a:"SWITCHABLE",i:"◉",d:"~30s"},{n:"GENERATE VIDEOS",a:"SWITCHABLE",i:"▶",d:"~120s"},{n:"VOICEOVER",a:"ELEVENLABS",i:"◎",d:"~4s"},{n:"TRANSCRIBE",a:"WHISPER",i:"▤",d:"~3s"},{n:"UPLOAD ASSETS",a:"R2",i:"⬆",d:"~8s"},{n:"FINAL RENDER",a:"SHOTSTACK",i:"⬡",d:"~90s"},{n:"CAPTIONS",a:"GPT-4o",i:"✎",d:"~4s"},{n:"PUBLISH",a:"BLOTATO",i:"◇",d:"~6s"}];

const STS=[
{t:"SCRIPT ENGINE",f:[{k:"script_model",l:"AI Model",tp:"select",o:["gpt-4o","gpt-4o-mini"],d:"gpt-4o"},{k:"script_temp",l:"Temperature",d:"0.85"},{k:"script_words",l:"Script Length",tp:"slider",min:30,max:180,step:5,d:90}]},
{t:"SCENE ENGINE",f:[{k:"scene_style",l:"Visual Style",tp:"select",o:["photorealistic","cinematic","painterly","anime","dark fantasy","oil painting"],d:"photorealistic"},{k:"scene_camera",l:"Camera Style",tp:"select",o:["steady","dynamic","handheld"],d:"steady"},{k:"scene_mood",l:"Mood Override",tp:"select",o:["auto","storm","fire","dawn","night","grey","battle"],d:"auto"}]},
{t:"VOICE SYNTH",f:[{k:"voice_id",l:"Voice ID",d:"bwCXcoVxWNYMlC6Esa8u"},{k:"voice_model",l:"Model",tp:"select",o:["eleven_turbo_v2","eleven_multilingual_v2","eleven_monolingual_v1"],d:"eleven_turbo_v2"},{k:"voice_stability",l:"Stability",d:"0.5"},{k:"voice_similarity",l:"Similarity",d:"0.75"},{k:"voice_speed",l:"Speed",d:"1.0"},{k:"voice_style",l:"Style",d:"0.0"}]},
{t:"IMAGE GENERATION",f:[{k:"image_provider",l:"Provider",tp:"select",o:["replicate"],d:"replicate"},{k:"image_model",l:"Model",tp:"select",o:[],d:"black-forest-labs/flux-1.1-pro",dep:"image_provider"},{k:"image_quality",l:"Quality",tp:"select",o:["low","medium","high"],d:"high"}]},
{t:"VIDEO GENERATION",f:[{k:"video_provider",l:"Provider",tp:"select",o:["replicate"],d:"replicate"},{k:"video_model",l:"Model",tp:"select",o:[],d:"bytedance/seedance-1-lite",dep:"video_provider"},{k:"clip_count",l:"Clips",tp:"select",o:["2","3","4","5"],d:"3"},{k:"clip_duration",l:"Clip Duration",tp:"select",o:["5","8","10","12","15"],d:"10"},{k:"_vid_total",l:"",tp:"computed"},{k:"video_timeout",l:"Timeout (sec)",d:"600"},{k:"cta_enabled",l:"CTA End Clip",tp:"toggle",d:true},{k:"cta_url",l:"CTA Video URL",d:"https://pub-8d4a1338211a44a7875ebe6ac8487129.r2.dev/_assets/ChristCTA.mp4"},{k:"cta_duration",l:"CTA Duration (sec)",tp:"select",o:["3","4","5","6","8","10"],d:"5"}]},
{t:"RENDER OUTPUT",f:[{k:"render_fps",l:"FPS",tp:"select",o:["24","30","60"],d:"30"},{k:"render_res",l:"Resolution",tp:"select",o:["720","1080"],d:"1080"},{k:"render_aspect",l:"Aspect Ratio",tp:"select",o:["9:16","16:9","1:1"],d:"9:16"},{k:"render_bg",l:"Background Color",d:"#000000"}]},
{t:"WATERMARK / LOGO",f:[{k:"logo_enabled",l:"Show Logo",tp:"toggle",d:true},{k:"logo_url",l:"Logo URL",d:"https://pub-8d4a1338211a44a7875ebe6ac8487129.r2.dev/gods_knights.png"},{k:"logo_position",l:"Position",tp:"select",o:["topRight","topLeft","bottomRight","bottomLeft","center"],d:"topRight"},{k:"logo_scale",l:"Scale",d:"0.12"},{k:"logo_opacity",l:"Opacity",d:"0.8"}]},
{t:"SCHEDULE",f:[{k:"sched_int",l:"Every (hours)",tp:"select",o:["4","6","8","12","24"],d:"8"},{k:"post_tt",l:"TikTok Time",d:"3:00 PM"},{k:"post_yt",l:"YouTube Time",d:"1:30 PM"},{k:"post_ig",l:"Instagram Time",d:"12:00 PM"},{k:"post_fb",l:"Facebook Time",d:"2:00 PM"}]},
{t:"PLATFORMS",f:[{k:"on_tt",l:"TikTok",tp:"toggle",d:true},{k:"on_yt",l:"YouTube",tp:"toggle",d:true},{k:"on_ig",l:"Instagram",tp:"toggle",d:true},{k:"on_fb",l:"Facebook",tp:"toggle",d:true},{k:"on_tw",l:"X/Twitter",tp:"toggle",d:true},{k:"on_th",l:"Threads",tp:"toggle",d:true},{k:"on_pn",l:"Pinterest",tp:"toggle",d:false}]}
];
let stOpen={};
const IMG_MODELS={replicate:[{v:"google/nano-banana-pro",l:"Nano Banana Pro ~$0.10"},{v:"google/nano-banana",l:"Nano Banana ~$0.02"},{v:"xai/grok-imagine-image",l:"Grok Aurora ~$0.07"},{v:"bytedance/seedream-4.5",l:"Seedream 4.5 ~$0.03"},{v:"black-forest-labs/flux-1.1-pro",l:"Flux 1.1 Pro ~$0.04"},{v:"black-forest-labs/flux-schnell",l:"Flux Schnell ~$0.003"},{v:"black-forest-labs/flux-dev",l:"Flux Dev ~$0.03"},{v:"ideogram-ai/ideogram-v3-quality",l:"Ideogram v3 Q ~$0.08"},{v:"ideogram-ai/ideogram-v3-turbo",l:"Ideogram v3 T ~$0.02"},{v:"recraft-ai/recraft-v3",l:"Recraft v3 ~$0.04"},{v:"stability-ai/stable-diffusion-3.5-large",l:"SD 3.5 L ~$0.035"},{v:"google-deepmind/imagen-4-preview",l:"Imagen 4 ~$0.04"}]};
const VID_MODELS={replicate:[{v:"bytedance/seedance-1-lite",l:"Seedance Lite ~$0.25"},{v:"bytedance/seedance-1",l:"Seedance Pro ~$0.50"},{v:"wavespeedai/wan-2.1-i2v-480p",l:"Wan 480p ~$0.10"},{v:"wavespeedai/wan-2.1-i2v-720p",l:"Wan 720p ~$0.20"},{v:"xai/grok-imagine-video",l:"Grok Video ~$0.30"},{v:"minimax/video-01-live",l:"Minimax Live ~$0.25"},{v:"minimax/video-01",l:"Minimax v01 ~$0.50"},{v:"kwaivgi/kling-v2.0-image-to-video",l:"Kling v2.0 ~$0.30"},{v:"luma/ray-2-flash",l:"Luma Flash ~$0.20"},{v:"luma/ray-2",l:"Luma Ray 2 ~$0.40"},{v:"google-deepmind/veo-3",l:"Veo 3 ~$0.50"}]};
const SVCS=[{n:"OPENAI",d:"GPT-4o + Whisper",k:"openai"},{n:"REPLICATE",d:"Image + Video",k:"replicate"},{n:"ELEVENLABS",d:"Voice Synthesis",k:"elevenlabs"},{n:"SHOTSTACK",d:"Video Render",k:"shotstack"},{n:"R2",d:"Asset Storage",k:"r2"},{n:"AIRTABLE",d:"Topic DB",k:"airtable"},{n:"BLOTATO",d:"Publishing",k:"blotato"}];

const titles={pipeline:'⚡ PIPELINE MONITOR',runs:'◈ RUN HISTORY',logs:'▤ SYSTEM LOGS',preview:'◉ ASSET PREVIEW',settings:'⚙ CONFIGURATION',health:'◎ SYSTEM STATUS'};

/* THEME */
function toggleTheme(){const on=document.documentElement.classList.toggle('light');localStorage.setItem('kr-theme',on?'light':'dark');updThemeBtn();}
function updThemeBtn(){const lt=document.documentElement.classList.contains('light');['d-thm','m-thm'].forEach(id=>{const el=$(id);if(el){if(id==='d-thm')el.textContent=lt?'◑ DARK MODE':'☀ LIGHT MODE';else el.textContent=lt?'◑':'☀';}});}
(function(){if(localStorage.getItem('kr-theme')==='light')document.documentElement.classList.add('light');})();

/* AUTH */
async function go(){const p=$('pw').value;if(!p){$('le').style.display='block';return;}try{const r=await(await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:p})})).json();if(r.ok){if(r.token)sessionStorage.setItem('kt',r.token);$('L').style.display='none';$('A').classList.remove('hd');init();}else{$('le').style.display='block';}}catch(e){$('le').style.display='block';}}
async function autoLogin(){const t=sessionStorage.getItem('kt');if(!t)return;try{const r=await(await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:t})})).json();if(r.ok){$('L').style.display='none';$('A').classList.remove('hd');init();}}catch(e){}}

/* NAV */
function dNav(p,btn){document.querySelectorAll('.dpage').forEach(e=>e.classList.remove('on'));document.querySelectorAll('.sb-i').forEach(b=>b.classList.remove('on'));$('dp-'+p).classList.add('on');if(btn)btn.classList.add('on');$('d-title').textContent=titles[p]||p;if(p==='runs')loadRuns();if(p==='logs')loadLogs();if(p==='preview')rPv();if(p==='health')rH();}
function mNav(p,btn){document.querySelectorAll('.mpage').forEach(e=>e.classList.remove('on'));document.querySelectorAll('.mt').forEach(b=>b.classList.remove('on'));$('mp-'+p).classList.add('on');if(btn)btn.classList.add('on');if(p==='runs')loadRuns();if(p==='logs')loadLogs();if(p==='preview')rPv();if(p==='health')rH();}

/* PIPELINE */
function rP(){
  let h='';const isDone=!RN&&PD.length>0;
  PHS.forEach((p,i)=>{let s='waiting',c='',sl='';if(PD.includes(i)){s='done';c='dn';sl='COMPLETE';}else if(RN&&i===PH){s='running';c='rn';sl='ACTIVE';}else if(RN&&i<PH){s='done';c='dn';sl='COMPLETE';}else if(RN){c='dm';}
    const nc=s==='done'?'var(--grn)':s==='running'?'var(--blu)':'var(--txtdd)';const nt=s==='done'?'var(--grn)':s==='running'?'var(--amb)':'var(--txtd)';
    h+=`<div class="ph ${c}"><div style="display:flex;align-items:center;gap:.55em"><span style="font-size:.8em;width:1.15em;text-align:center;color:${nc}">${p.i}</span><div style="flex:1"><div style="font-family:var(--f1);font-size:.6em;font-weight:600;letter-spacing:.15em;color:${nt}">${p.n}</div><div style="font-size:.5em;color:var(--txtdd);margin-top:.05em;letter-spacing:.08em">${p.a} · ${p.d}</div></div>${sl?`<span style="font-family:var(--f1);font-size:.5em;color:${nc};letter-spacing:1px">${sl}</span>`:''} ${B(s)}</div></div>`;
  });
  ['d-pl','m-pl'].forEach(id=>{if($(id))$(id).innerHTML=h;});
  const pct=(PD.length/PHS.length*100);
  ['d-pb','m-pb'].forEach(id=>{if($(id))$(id).style.width=pct+'%';});
  // Desktop stats on pipeline page
  if($('d-stats')){const t=PD.length,tot=PHS.length;$('d-stats').innerHTML=[{l:'PHASES',v:t+'/'+tot,c:'amb'},{l:'PROGRESS',v:Math.round(pct)+'%',c:pct>=100?'grn':'blu'},{l:'STATUS',v:RN?'RUNNING':'IDLE',c:RN?'blu':'txtd'},{l:'LAST',v:LAST_RESULT?LAST_RESULT.status:'—',c:LAST_RESULT&&LAST_RESULT.status==='failed'?'red':'grn'}].map(s=>`<div class="stat"><b style="color:var(--${s.c})">${s.v}</b><small style="color:var(--${s.c})">${s.l}</small></div>`).join('');}
  if(RN){
    if($('d-ph'))$('d-ph').textContent='PHASE '+(PH+1)+'/11';
    ['d-rb','m-rb'].forEach(id=>{if($(id)){$(id).textContent='⏳';$(id).style.background='var(--bg3)';$(id).style.color='var(--txtd)';}});
  }else{
    if($('d-ph'))$('d-ph').textContent='';
    if($('d-rb')){$('d-rb').textContent='▶ EXECUTE';$('d-rb').style.background='var(--amb)';$('d-rb').style.color='var(--bg)';}
    if($('m-rb')){$('m-rb').textContent='▶ EXECUTE';$('m-rb').style.background='var(--amb)';$('m-rb').style.color='var(--bg)';}
    const sr=LAST_RESULT&&LAST_RESULT.status==='failed';
    ['d-rsb','m-rsb'].forEach(id=>{if($(id))$(id).style.display=sr?'block':'none';});
  }
}

/* ACTIONS */
async function runNow(){if(RN)return;await fetch('/api/run',{method:'POST'});RN=true;PH=0;PD=[];rP();poll();}
async function resumeNow(){if(RN)return;const r=await fetch('/api/resume',{method:'POST'});const d=await r.json();if(r.ok){RN=true;PD=[];rP();poll();}else{alert(d.error||'Failed');}}
async function poll(){if(!RN)return;try{const r=await(await fetch('/api/status')).json();PH=r.phase;PD=r.phases_done||[];if(r.result)LAST_RESULT=r.result;if(!r.running){RN=false;rP();rPv();return;}RN=true;rP();setTimeout(poll,2000);}catch(e){setTimeout(poll,3000);}}

/* RUNS */
async function loadRuns(){try{const runs=await(await fetch('/api/runs')).json();const t=runs.length,ok=runs.filter(r=>r.status==='published'||r.status==='complete').length;
const sh=[{l:'TOTAL',v:t,c:'amb'},{l:'SUCCESS',v:ok,c:'grn'},{l:'RATE',v:t?Math.round(ok/t*100)+'%':'—',c:'blu'},{l:'FAILED',v:t-ok,c:'red'}].map(s=>`<div class="stat"><b style="color:var(--${s.c})">${s.v}</b><small style="color:var(--${s.c})">${s.l}</small></div>`).join('');
['d-rs','m-rs'].forEach(id=>{if($(id))$(id).innerHTML=sh;});
const rh=runs.length?runs.map(r=>`<div class="rw"><div style="display:flex;align-items:center;gap:.55em"><div style="flex:1"><div style="font-family:var(--f2);font-size:.85em;font-weight:600;color:var(--wht)">${r.topic||'?'}</div><div style="font-size:.55em;color:var(--txtd);margin-top:.05em;letter-spacing:.08em">${r.date} · ${r.category||''}</div></div>${B(r.status==='published'||r.status==='complete'?'done':'failed',r.status)}</div>${r.error?`<div style="font-size:.65em;color:var(--red);margin-top:.3em;background:var(--red2);padding:.2em .4em">${r.error}</div>`:''}</div>`).join(''):'<div class="rw" style="color:var(--txtd)">NO RUNS</div>';
['d-rl','m-rl'].forEach(id=>{if($(id))$(id).innerHTML=rh;});
}catch(e){}}

/* LOGS */
async function loadLogs(){try{const logs=await(await fetch('/api/logs')).json();
const h=logs.length?logs.map(l=>`<div><span style="color:var(--txtdd)">${l.t}</span> <span style="color:var(--amb);background:var(--amblo);padding:0 .2em;font-size:.55em;letter-spacing:.08em">${l.phase}</span> <span style="color:var(--${l.level==='ok'?'grn':l.level==='error'?'red':'txtd'})">${l.msg}</span></div>`).join(''):'<div style="color:var(--txtd)">No logs yet.</div>';
['d-la','m-la'].forEach(id=>{if($(id))$(id).innerHTML=h;});
if($('d-lc'))$('d-lc').textContent=logs.length+' entries';
}catch(e){}}

/* PREVIEW */
async function rPv(){try{const r=await(await fetch('/api/last-result')).json();if(!r||!r.topic)return;
['d-','m-'].forEach(px=>{
  if($(px+'pve'))$(px+'pve').style.display='none';
  if(r.images&&r.images.length){if($(px+'pvi'))$(px+'pvi').style.display='block';if($(px+'pig'))$(px+'pig').innerHTML=r.images.map(img=>`<div class="pcard"><img src="${img.url}" alt="S${img.index}" loading="lazy"><div class="plbl">SCENE ${img.index}</div><a class="dl" href="${img.url}" download target="_blank">⬇</a></div>`).join('');}
  if(r.videos&&r.videos.length){if($(px+'pvv'))$(px+'pvv').style.display='block';if($(px+'pvg'))$(px+'pvg').innerHTML=r.videos.map(v=>`<div class="pcard"><video src="${v.url}" muted loop playsinline onmouseenter="this.play()" onmouseleave="this.pause();this.currentTime=0"></video><div class="plbl">CLIP ${v.index}</div><a class="dl" href="${v.url}" download target="_blank">⬇</a></div>`).join('');}
  if(r.final_url){if($(px+'pvf'))$(px+'pvf').style.display='block';if($(px+'fv'))$(px+'fv').src=r.final_url;if($(px+'fd'))$(px+'fd').href=r.final_url;}
  if(r.script){if($(px+'pvs'))$(px+'pvs').style.display='block';if($(px+'pst'))$(px+'pst').textContent=r.script;}
});
}catch(e){}}

/* SETTINGS */
function getModels(fk){const prov=fk==='image_model'?(ST.image_provider||'replicate'):(ST.video_provider||'replicate');const cat=fk==='image_model'?IMG_MODELS:VID_MODELS;return cat[prov]||[];}

function rSt(){let h='';STS.forEach((sec,si)=>{let ff='';sec.f.forEach(f=>{try{const v=ST[f.k]!==undefined?ST[f.k]:f.d;const wide=f.tp==='slider'||f.tp==='toggle'||f.tp==='computed';
if(f.tp==='toggle'){const on=v===true||v==='true';ff+=`<div class="fi${wide?' w':''}" style="display:flex;align-items:center;justify-content:space-between"><div style="font-size:.9em;color:var(--wht)">${f.l}</div><button class="tg ${on?'on':'off'}" onclick="event.stopPropagation();ST['${f.k}']=!(ST['${f.k}']===true||ST['${f.k}']==='true');rSt()"><span class="td"></span></button></div>`;}
else if(f.tp==='select'){let opts=f.o;if(f.dep){opts=getModels(f.k);ff+=`<div class="fi"><div class="fl">${f.l}</div><select class="fin" onchange="ST['${f.k}']=this.value">${opts.map(o=>`<option value="${o.v}"${o.v==v?' selected':''}>${o.l}</option>`).join('')}</select></div>`;}
else if(f.k==='image_provider'||f.k==='video_provider'||f.k==='clip_count'||f.k==='clip_duration'){ff+=`<div class="fi"><div class="fl">${f.l}</div><select class="fin" onchange="ST['${f.k}']=this.value;rSt()">${opts.map(o=>`<option${o==v?' selected':''}>${o}</option>`).join('')}</select></div>`;}
else{ff+=`<div class="fi"><div class="fl">${f.l}</div><select class="fin" onchange="ST['${f.k}']=this.value">${opts.map(o=>`<option${o==v?' selected':''}>${o}</option>`).join('')}</select></div>`;}}
else if(f.tp==='computed'){const clips=parseInt(ST.clip_count)||3,dur=parseInt(ST.clip_duration)||10,tot=clips*dur,words=parseInt(ST.script_words)||90,vo=Math.round(words/3),diff=tot-vo;const warn=diff>10?'⚠ VO '+diff+'s short':'✓ Matched';const wc=diff>10?'var(--red)':'var(--grn)';
ff+=`<div class="fi w" style="border:1px solid var(--bd2);padding:8px;background:rgba(227,160,40,.03)"><div style="display:flex;justify-content:space-between"><div style="font-family:var(--f1);font-size:.6em;letter-spacing:.15em;color:var(--txtd)">TOTAL VIDEO</div><div style="font-family:var(--f1);font-size:1.15em;font-weight:800;color:var(--amb)">${tot}s</div></div><div style="display:flex;justify-content:space-between;margin-top:3px"><div style="font-size:.55em;color:var(--txtdd)">${clips}×${dur}s</div><div style="font-size:.55em;color:${wc}">${warn}</div></div></div>`;}
else if(f.tp==='slider'){const mn=f.min||30,mx=f.max||180,stp=f.step||5,cv=parseInt(v)||f.d,secs=Math.round(cv/3),pct=((cv-mn)/(mx-mn))*100,dl=secs>=60?Math.floor(secs/60)+'m'+(secs%60?' '+secs%60+'s':''):secs+'s';
ff+=`<div class="fi w"><div class="fl">${f.l}</div><div style="display:flex;align-items:center;gap:.55em"><input type="range" min="${mn}" max="${mx}" step="${stp}" value="${cv}" class="fin-slider" style="flex:1" oninput="ST['${f.k}']=parseInt(this.value);document.getElementById('sl_${f.k}').textContent=this.value+' words ≈ '+Math.round(this.value/3)+'s';document.getElementById('slb_${f.k}').style.width=((this.value-${mn})/(${mx}-${mn})*100)+'%'"><div id="sl_${f.k}" style="min-width:6em;font-family:var(--f1);font-size:.65em;letter-spacing:1px;color:var(--amb);text-align:right">${cv} words ≈ ${dl}</div></div><div style="position:relative;height:3px;background:var(--bg3);margin-top:3px;overflow:hidden"><div id="slb_${f.k}" style="position:absolute;top:0;left:0;height:100%;background:var(--amb);width:${pct}%;transition:width .1s"></div></div><div style="display:flex;justify-content:space-between;margin-top:2px"><span style="font-size:.5em;color:var(--txtdd)">${mn}w/${Math.round(mn/3)}s</span><span style="font-size:.5em;color:var(--txtdd)">${mx}w/${Math.round(mx/3)}s</span></div></div>`;}
else{ff+=`<div class="fi"><div class="fl">${f.l}</div><input class="fin" value="${v||''}" onchange="ST['${f.k}']=this.value"></div>`;}
}catch(e){console.error('CFG:',f.k,e);}});
h+=`<div class="sec"><button class="sec-h" onclick="stOpen[${si}]=!stOpen[${si}];rSt()"><span class="sec-t">${sec.t}</span><span class="sec-a" style="transform:${stOpen[si]?'rotate(90deg)':''}">›</span></button><div class="sec-b${stOpen[si]?'':' shut'}">${ff}</div></div>`;
});['d-sf','m-sf'].forEach(id=>{if($(id))$(id).innerHTML=h;});}

async function saveSett(){await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(ST)});['d-ss','m-ss'].forEach(id=>{if($(id)){$(id).style.display='block';setTimeout(()=>$(id).style.display='none',3000);}});}

/* HEALTH */
async function rH(){try{const cfg=await(await fetch('/api/config')).json();const h='<div class="rw"><span style="font-family:var(--f1);font-size:.6em;color:var(--txtd);letter-spacing:.2em">API CONNECTIONS</span></div>'+SVCS.map(s=>`<div class="rw" style="display:flex;justify-content:space-between;align-items:center"><div><div style="font-family:var(--f1);font-size:.7em;font-weight:600;letter-spacing:.15em;color:var(--wht)">${s.n}</div><div style="font-size:.55em;color:var(--txtd);margin-top:.05em">${s.d}</div></div>${B(cfg[s.k]?'configured':'missing')}</div>`).join('');['d-hl','m-hl'].forEach(id=>{if($(id))$(id).innerHTML=h;});}catch(e){}}
async function testAll(){alert('Testing...');for(const s of['openai','replicate','elevenlabs','airtable']){try{await(await fetch('/api/test-connection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service:s})})).json();}catch(e){}}rH();alert('Done!');}

/* INIT */
async function init(){rP();updThemeBtn();try{const r=await(await fetch('/api/settings')).json();STS.forEach(s=>s.f.forEach(f=>{if(r[f.k]!==undefined)ST[f.k]=r[f.k];else ST[f.k]=f.d;}));}catch(e){STS.forEach(s=>s.f.forEach(f=>ST[f.k]=f.d));}rSt();try{const r=await(await fetch('/api/status')).json();if(r.result){LAST_RESULT=r.result;PD=r.phases_done||[];}if(r.running){RN=true;PH=r.phase;PD=r.phases_done||[];rP();poll();}else{rP();}}catch(e){}}
autoLogin();
</script></body></html>
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
