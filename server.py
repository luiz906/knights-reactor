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
DATA_DIR = Path(__file__).parent / "data"
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
    # Platforms
    for pk in ["on_tt","on_yt","on_ig","on_fb","on_tw","on_th","on_pn"]:
        if pk in s: setattr(Config, pk.upper(), s[pk] in (True, "true", "True"))

apply_credentials()
apply_model_settings()

# ─── STATE ────────────────────────────────────────────────────
RUNS = load_json(RUNS_FILE, []) if RUNS_FILE.exists() else []
CURRENT_RUN = {"active": False, "result": None, "phase": 0, "phase_name": "", "phases_done": []}
LOGS = []

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
        "error": result.get("error"),
    }
    RUNS.insert(0, run_entry)
    save_json(RUNS_FILE, RUNS[:100])
    log_entry("System", "ok" if result.get("status") == "published" else "error", f"Pipeline finished: {result.get('status')}")

# ─── API ──────────────────────────────────────────────────────
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
    if not os.path.exists("/tmp/pipeline_checkpoint.json"):
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

HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Knights Reactor /// Control Terminal</title>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;500;600;700;800;900&family=Rajdhani:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#0a0a08;--panel:#0d0d0a;--grid:rgba(227,160,40,.04);--bd:rgba(227,160,40,.15);--bd2:rgba(227,160,40,.08);--amb:#e3a028;--amb2:#c88a1a;--amblo:rgba(227,160,40,.06);--ambmd:rgba(227,160,40,.12);--txt:#e3a028;--txtd:#8a6a1a;--txtdd:#4a3a10;--grn:#28e060;--grn2:rgba(40,224,96,.1);--red:#e04028;--red2:rgba(224,64,40,.1);--blu:#28a0e0;--blu2:rgba(40,160,224,.12);--wht:#d4cbb8;--f1:'Orbitron',monospace;--f2:'Rajdhani',sans-serif;--f3:'Share Tech Mono',monospace}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--txt);font-family:var(--f3);min-height:100vh;overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(227,160,40,.015) 2px,rgba(227,160,40,.015) 4px);pointer-events:none;z-index:9999}
body::after{content:'';position:fixed;inset:0;background:radial-gradient(ellipse at 50% 0%,rgba(227,160,40,.03) 0%,transparent 70%);pointer-events:none;z-index:9998}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:var(--amb2);border-radius:2px}::-webkit-scrollbar-track{background:var(--bg)}
button{font-family:var(--f3);cursor:pointer}input,select{font-family:var(--f3)}
.hd{display:none}
@keyframes scanline{0%{top:-100%}100%{top:100%}}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
@keyframes glow{0%,100%{box-shadow:0 0 5px rgba(227,160,40,.2),inset 0 0 5px rgba(227,160,40,.05)}50%{box-shadow:0 0 15px rgba(227,160,40,.3),inset 0 0 10px rgba(227,160,40,.08)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
@keyframes fi{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}

/* PANELS */
.pnl{background:var(--panel);border:1px solid var(--bd);position:relative;overflow:hidden}
.pnl::before{content:'';position:absolute;inset:0;background:repeating-linear-gradient(0deg,transparent 0px,transparent 30px,var(--grid) 30px,var(--grid) 31px),repeating-linear-gradient(90deg,transparent 0px,transparent 30px,var(--grid) 30px,var(--grid) 31px);pointer-events:none}
.pnl-glow{animation:glow 3s ease-in-out infinite}

/* BADGES */
.bg{font-family:var(--f3);font-size:9px;padding:2px 8px;border-radius:1px;display:inline-flex;align-items:center;gap:5px;letter-spacing:1px;text-transform:uppercase}
.bd2{width:5px;height:5px;border-radius:0}
.bg-g{color:var(--grn);background:var(--grn2);border:1px solid rgba(40,224,96,.2)}.bg-g .bd2{background:var(--grn)}
.bg-r{color:var(--red);background:var(--red2);border:1px solid rgba(224,64,40,.2)}.bg-r .bd2{background:var(--red)}
.bg-b{color:var(--blu);background:var(--blu2);border:1px solid rgba(40,160,224,.2)}.bg-b .bd2{background:var(--blu);animation:pulse 1.2s infinite}
.bg-m{color:var(--txtdd);background:rgba(74,58,16,.1);border:1px solid rgba(74,58,16,.2)}.bg-m .bd2{background:var(--txtdd)}
.bg-o{color:var(--amb);background:var(--amblo);border:1px solid var(--bd)}.bg-o .bd2{background:var(--amb)}

/* PHASE CARDS */
.ph{background:var(--panel);border:1px solid var(--bd2);padding:12px 14px;margin-bottom:4px;border-left:3px solid var(--txtdd);transition:all .3s;position:relative;overflow:hidden}
.ph.dn{border-left-color:var(--grn);background:rgba(40,224,96,.02)}.ph.rn{border-left-color:var(--blu);background:rgba(40,160,224,.03)}
.ph.rn::after{content:'';position:absolute;top:0;left:0;width:100%;height:2px;background:linear-gradient(90deg,transparent,var(--blu),transparent);animation:scanline 2s linear infinite}
.ph.dm{opacity:.3}

/* SETTINGS SECTIONS */
.sec{background:var(--panel);border:1px solid var(--bd2);margin-bottom:6px;overflow:hidden}
.sec-h{width:100%;display:flex;align-items:center;justify-content:space-between;padding:12px 14px;background:none;border:none;color:var(--txt)}
.sec-t{font-family:var(--f1);font-size:10px;font-weight:600;letter-spacing:2px;text-transform:uppercase}.sec-a{font-family:var(--f3);font-size:14px;color:var(--txtd);transition:transform .15s}
.sec-b{padding:0 14px 12px}.fi{padding:9px 0;border-bottom:1px solid var(--bd2)}
.fl{font-family:var(--f3);font-size:8px;color:var(--txtd);text-transform:uppercase;letter-spacing:2px;margin-bottom:4px}
.fin{width:100%;padding:8px 10px;background:var(--bg);border:1px solid var(--bd2);font-size:11px;color:var(--amb);outline:none;box-sizing:border-box;font-family:var(--f3)}
.fin-slider{-webkit-appearance:none;appearance:none;background:var(--bg3);border-radius:3px;outline:none;opacity:.8;transition:opacity .15s}
.fin-slider:hover{opacity:1}
.fin-slider::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:16px;height:16px;border-radius:50%;background:var(--amb);cursor:pointer;border:2px solid var(--bg)}
.fin-slider::-moz-range-thumb{width:16px;height:16px;border-radius:50%;background:var(--amb);cursor:pointer;border:2px solid var(--bg)}
.fin:focus{border-color:var(--amb);box-shadow:0 0 8px rgba(227,160,40,.15)}
.tg{width:38px;height:20px;border-radius:1px;border:1px solid var(--bd);position:relative;transition:background .2s}
.tg.on{background:rgba(40,224,96,.2);border-color:var(--grn)}.tg.off{background:var(--bg);border-color:var(--bd2)}.td{position:absolute;top:2px;width:16px;height:16px;border-radius:0;background:var(--amb);transition:left .2s;box-shadow:0 0 6px rgba(227,160,40,.4)}
.tg.on .td{background:var(--grn);box-shadow:0 0 6px rgba(40,224,96,.4)}
.sv{width:100%;padding:11px;border:1px solid var(--amb);background:rgba(227,160,40,.08);font-size:11px;font-weight:600;color:var(--amb);margin-top:10px;letter-spacing:3px;text-transform:uppercase;font-family:var(--f1);transition:all .2s}
.sv:hover{background:rgba(227,160,40,.15);box-shadow:0 0 15px rgba(227,160,40,.2)}
.sm{background:var(--grn2);border:1px solid rgba(40,224,96,.2);padding:8px 12px;margin-bottom:10px;font-size:10px;color:var(--grn)}
.rw{padding:11px 14px;border-bottom:1px solid var(--bd2)}

/* ASSET PREVIEW */
.preview-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}
.preview-card{background:var(--bg);border:1px solid var(--bd2);overflow:hidden;position:relative}
.preview-card img,.preview-card video{width:100%;height:auto;display:block}
.preview-card .dl-btn{position:absolute;bottom:6px;right:6px;background:rgba(10,10,8,.85);border:1px solid var(--bd);color:var(--amb);font-family:var(--f3);font-size:9px;padding:3px 8px;cursor:pointer;letter-spacing:1px}
.preview-card .dl-btn:hover{background:rgba(227,160,40,.15)}
.preview-label{font-family:var(--f3);font-size:8px;color:var(--txtd);padding:4px 6px;letter-spacing:1px;text-transform:uppercase}
.final-video{border:1px solid var(--amb);padding:2px;background:var(--bg);margin:12px 0}
.final-video video{width:100%;display:block}

/* TABS */
.tb{font-family:var(--f1);font-size:8px;color:var(--txtd);background:none;border:none;border-bottom:2px solid transparent;padding:10px 12px;white-space:nowrap;display:flex;align-items:center;gap:5px;letter-spacing:2px;text-transform:uppercase;transition:all .15s}
.tb:hover{color:var(--amb)}.tb.ac{color:var(--amb);font-weight:600;border-bottom-color:var(--amb)}
</style></head><body>

<!-- LOGIN -->
<div id="L" style="min-height:100vh;display:flex;align-items:center;justify-content:center">
<div class="pnl pnl-glow" style="width:380px;padding:40px 30px;text-align:center">
<div style="font-family:var(--f1);font-size:8px;color:var(--txtd);letter-spacing:6px;margin-bottom:8px">SYSTEM ACCESS</div>
<div style="font-family:var(--f1);font-size:22px;font-weight:800;color:var(--amb);letter-spacing:3px;margin-bottom:4px">KNIGHTS REACTOR</div>
<div style="font-family:var(--f3);font-size:9px;color:var(--txtd);letter-spacing:4px;margin-bottom:30px">/// CONTROL TERMINAL v5.0 ///</div>
<div style="width:60px;height:2px;background:var(--amb);margin:0 auto 24px;box-shadow:0 0 10px rgba(227,160,40,.4)"></div>
<input type="password" id="pw" style="width:100%;padding:12px 14px;background:var(--bg);border:1px solid var(--bd);font-size:13px;color:var(--amb);outline:none;margin-bottom:12px;text-align:center;letter-spacing:4px;font-family:var(--f3)" placeholder="ENTER ACCESS CODE" onkeydown="event.key==='Enter'&&go()">
<div id="le" class="hd" style="font-size:9px;color:var(--red);margin-bottom:8px;letter-spacing:1px">⚠ ACCESS DENIED</div>
<button onclick="go()" style="width:100%;padding:12px;border:1px solid var(--amb);background:rgba(227,160,40,.08);font-family:var(--f1);font-size:10px;font-weight:600;color:var(--amb);letter-spacing:4px;transition:all .2s" onmouseover="this.style.background='rgba(227,160,40,.15)'" onmouseout="this.style.background='rgba(227,160,40,.08)'">AUTHENTICATE</button>
<div style="margin-top:20px;font-size:8px;color:var(--txtdd);letter-spacing:2px">04.52.3021 // CLASSIFIED</div>
</div></div>

<!-- APP -->
<div id="A" class="hd">
<!-- HEADER -->
<div style="padding:14px 20px 10px;border-bottom:1px solid var(--bd);background:var(--panel);display:flex;align-items:center;justify-content:space-between">
<div style="display:flex;align-items:center;gap:12px">
<div style="width:6px;height:28px;background:var(--amb);box-shadow:0 0 10px rgba(227,160,40,.4)"></div>
<div>
<div style="font-family:var(--f1);font-size:14px;font-weight:800;color:var(--amb);letter-spacing:3px;line-height:1">KNIGHTS REACTOR</div>
<div style="font-family:var(--f3);font-size:8px;color:var(--txtd);letter-spacing:3px;margin-top:3px">PIPELINE CONTROL /// V5.0</div>
</div></div>
<div style="display:flex;align-items:center;gap:10px">
<span id="pi" class="hd" style="font-family:var(--f3);font-size:9px;color:var(--blu);letter-spacing:1px"></span>
<button id="rb" onclick="runNow()" style="font-family:var(--f1);font-size:9px;font-weight:600;color:var(--bg);background:var(--amb);border:none;padding:9px 16px;letter-spacing:2px;transition:all .2s;box-shadow:0 0 10px rgba(227,160,40,.3)" onmouseover="this.style.boxShadow='0 0 20px rgba(227,160,40,.5)'" onmouseout="this.style.boxShadow='0 0 10px rgba(227,160,40,.3)'">▶ EXECUTE</button>
<button id="rsb" onclick="resumeNow()" style="font-family:var(--f1);font-size:9px;font-weight:600;color:var(--amb);background:transparent;border:1px solid var(--amb);padding:9px 16px;letter-spacing:2px;transition:all .2s;display:none;margin-left:8px" onmouseover="this.style.background='rgba(227,160,40,.15)'" onmouseout="this.style.background='transparent'">♻ RESUME</button>
</div></div>

<!-- TABS -->
<div style="display:flex;border-bottom:1px solid var(--bd);background:var(--panel);overflow-x:auto">
<button class="tb ac" onclick="sw('pipeline',this)">⚡ PIPELINE</button>
<button class="tb" onclick="sw('runs',this)">◈ RUNS</button>
<button class="tb" onclick="sw('logs',this)">▤ LOGS</button>
<button class="tb" onclick="sw('preview',this)">◉ PREVIEW</button>
<button class="tb" onclick="sw('settings',this)">⚙ CONFIG</button>
<button class="tb" onclick="sw('health',this)">◎ STATUS</button>
</div>

<div style="padding:16px 20px;max-width:680px;margin:0 auto">

<!-- PIPELINE -->
<div id="t-pipeline">
<div id="pg" class="hd" style="height:2px;background:var(--bd2);overflow:hidden;margin-bottom:14px"><div id="pb" style="height:100%;background:var(--amb);transition:width .6s ease;width:0%;box-shadow:0 0 10px rgba(227,160,40,.5)"></div></div>
<div id="pl"></div>
</div>

<!-- RUNS -->
<div id="t-runs" class="hd">
<div id="rs" style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:14px"></div>
<div class="pnl" id="rl"></div>
</div>

<!-- LOGS -->
<div id="t-logs" class="hd">
<div style="display:flex;justify-content:space-between;margin-bottom:10px">
<span style="font-family:var(--f1);font-size:8px;color:var(--txtd);letter-spacing:3px">SYSTEM LOG OUTPUT</span>
<span id="lc" style="font-size:9px;color:var(--txtd)"></span>
</div>
<div id="la" class="pnl" style="padding:12px 14px;max-height:500px;overflow-y:auto;font-size:10.5px;line-height:1.9"></div>
</div>

<!-- PREVIEW -->
<div id="t-preview" class="hd">
<div style="font-family:var(--f1);font-size:8px;color:var(--txtd);letter-spacing:3px;margin-bottom:12px">ASSET PREVIEW /// GENERATED MEDIA</div>

<div id="pv-empty" class="pnl" style="padding:30px;text-align:center">
<div style="font-size:10px;color:var(--txtd);letter-spacing:2px">NO ASSETS GENERATED YET</div>
<div style="font-size:9px;color:var(--txtdd);margin-top:6px">Run the pipeline to generate images and videos</div>
</div>

<div id="pv-images" class="hd">
<div style="font-family:var(--f1);font-size:9px;color:var(--amb);letter-spacing:2px;margin-bottom:8px;display:flex;align-items:center;gap:8px"><span style="width:3px;height:12px;background:var(--amb);display:inline-block"></span>GENERATED IMAGES</div>
<div id="pv-img-grid" class="preview-grid"></div>
</div>

<div id="pv-videos" class="hd">
<div style="font-family:var(--f1);font-size:9px;color:var(--amb);letter-spacing:2px;margin:16px 0 8px;display:flex;align-items:center;gap:8px"><span style="width:3px;height:12px;background:var(--amb);display:inline-block"></span>ANIMATED CLIPS</div>
<div id="pv-vid-grid" class="preview-grid"></div>
</div>

<div id="pv-final" class="hd">
<div style="font-family:var(--f1);font-size:9px;color:var(--grn);letter-spacing:2px;margin:16px 0 8px;display:flex;align-items:center;gap:8px"><span style="width:3px;height:12px;background:var(--grn);display:inline-block"></span>FINAL RENDER</div>
<div class="final-video"><video id="pv-final-vid" controls></video></div>
<a id="pv-final-dl" href="#" download style="display:block;text-align:center;padding:10px;border:1px solid var(--amb);background:var(--amblo);color:var(--amb);font-family:var(--f1);font-size:9px;letter-spacing:3px;text-decoration:none;margin-top:8px;transition:all .2s" onmouseover="this.style.background='rgba(227,160,40,.15)'" onmouseout="this.style.background='var(--amblo)'">⬇ DOWNLOAD FINAL VIDEO</a>
</div>

<div id="pv-script" class="hd" style="margin-top:16px">
<div style="font-family:var(--f1);font-size:9px;color:var(--amb);letter-spacing:2px;margin-bottom:8px;display:flex;align-items:center;gap:8px"><span style="width:3px;height:12px;background:var(--amb);display:inline-block"></span>SCRIPT</div>
<div id="pv-script-text" class="pnl" style="padding:14px;font-size:11px;color:var(--wht);line-height:1.7"></div>
</div>
</div>

<!-- SETTINGS -->
<div id="t-settings" class="hd"><div id="ss" class="sm hd">✓ CONFIGURATION SAVED</div><div id="sf"></div><button class="sv" onclick="saveSett()">SAVE CONFIGURATION</button></div>

<!-- HEALTH -->
<div id="t-health" class="hd">
<div class="pnl" id="hl" style="margin-bottom:12px"></div>
<div class="pnl" style="padding:14px">
<div style="font-family:var(--f1);font-size:9px;font-weight:600;letter-spacing:3px;margin-bottom:10px">DIAGNOSTICS</div>
<button style="width:100%;display:flex;justify-content:space-between;align-items:center;padding:10px 12px;margin-bottom:6px;background:var(--bg);border:1px solid var(--bd2)" onclick="testAll()">
<div style="text-align:left"><div style="font-size:11px;font-weight:500;color:var(--amb)">TEST ALL CONNECTIONS</div><div style="font-size:8px;color:var(--txtd);margin-top:2px;letter-spacing:1px">PING EACH API ENDPOINT</div></div>
<span style="font-size:12px;color:var(--amb)">→</span></button>
</div>
<button onclick="sessionStorage.removeItem('kt');document.getElementById('L').style.display='flex';document.getElementById('A').style.display='none'" style="width:100%;padding:10px;margin-top:12px;border:1px solid rgba(224,64,40,.3);background:var(--red2);font-family:var(--f1);font-size:9px;color:var(--red);letter-spacing:3px">⚠ DISCONNECT</button>
</div>

</div></div>

<script>
let RN=false,PH=0,PD=[],ST={},LAST_RESULT=null;
const $=id=>document.getElementById(id);
const B=(s,l)=>{const c={done:'g',running:'b',failed:'r',configured:'g',missing:'r',warning:'o',waiting:'m'}[s]||'m';return`<span class="bg bg-${c}"><span class="bd2"></span>${l||s}</span>`};

const PHS=[{n:"FETCH TOPIC",a:"AIRTABLE",i:"⬡",d:"~2s"},{n:"GENERATE SCRIPT",a:"GPT-4o",i:"⬢",d:"~3s"},{n:"SCENE ENGINE",a:"LOCAL",i:"◈",d:"<1s"},{n:"GENERATE IMAGES",a:"SWITCHABLE",i:"◉",d:"~30s"},{n:"GENERATE VIDEOS",a:"SWITCHABLE",i:"▶",d:"~120s"},{n:"VOICEOVER",a:"ELEVENLABS",i:"◎",d:"~4s"},{n:"TRANSCRIBE",a:"WHISPER",i:"▤",d:"~3s"},{n:"UPLOAD ASSETS",a:"R2",i:"⬆",d:"~8s"},{n:"FINAL RENDER",a:"SHOTSTACK",i:"⬡",d:"~90s"},{n:"CAPTIONS",a:"GPT-4o",i:"✎",d:"~4s"},{n:"PUBLISH",a:"BLOTATO",i:"◇",d:"~6s"}];

const STS=[
{t:"SCRIPT ENGINE",f:[
  {k:"script_model",l:"AI Model",tp:"select",o:["gpt-4o","gpt-4o-mini"],d:"gpt-4o"},
  {k:"script_temp",l:"Temperature (creativity)",d:"0.85"},
  {k:"script_words",l:"Script Length",tp:"slider",min:30,max:180,step:5,d:90}
]},
{t:"SCENE ENGINE",f:[
  {k:"scene_style",l:"Visual Style",tp:"select",o:["photorealistic","cinematic","painterly","anime","dark fantasy","oil painting"],d:"photorealistic"},
  {k:"scene_camera",l:"Camera Style",tp:"select",o:["steady","dynamic","handheld"],d:"steady"},
  {k:"scene_mood",l:"Mood Override",tp:"select",o:["auto","storm","fire","dawn","night","grey","battle"],d:"auto"}
]},
{t:"VOICE SYNTH",f:[
  {k:"voice_id",l:"Voice ID (ElevenLabs)",d:"bwCXcoVxWNYMlC6Esa8u"},
  {k:"voice_model",l:"Model",tp:"select",o:["eleven_turbo_v2","eleven_multilingual_v2","eleven_monolingual_v1"],d:"eleven_turbo_v2"},
  {k:"voice_stability",l:"Stability (0-1)",d:"0.5"},
  {k:"voice_similarity",l:"Similarity Boost (0-1)",d:"0.75"},
  {k:"voice_speed",l:"Speed (0.5-2.0)",d:"1.0"},
  {k:"voice_style",l:"Style Exaggeration (0-1)",d:"0.0"}
]},
{t:"IMAGE GENERATION",f:[
  {k:"image_provider",l:"Provider",tp:"select",o:["replicate"],d:"replicate"},
  {k:"image_model",l:"Model",tp:"select",o:[],d:"black-forest-labs/flux-1.1-pro",dep:"image_provider"},
  {k:"image_quality",l:"Quality",tp:"select",o:["low","medium","high"],d:"high"}
]},
{t:"VIDEO GENERATION",f:[
  {k:"video_provider",l:"Provider",tp:"select",o:["replicate"],d:"replicate"},
  {k:"video_model",l:"Model",tp:"select",o:[],d:"bytedance/seedance-1-lite",dep:"video_provider"},
  {k:"clip_count",l:"Clips per Video",tp:"select",o:["2","3","4","5"],d:"3"},
  {k:"clip_duration",l:"Clip Duration (sec)",tp:"select",o:["5","8","10","12","15"],d:"10"},
  {k:"_vid_total",l:"",tp:"computed"},
  {k:"video_timeout",l:"Timeout (sec)",d:"600"}
]},
{t:"RENDER OUTPUT",f:[
  {k:"render_fps",l:"FPS",tp:"select",o:["24","30","60"],d:"30"},
  {k:"render_res",l:"Resolution",tp:"select",o:["720","1080"],d:"1080"},
  {k:"render_aspect",l:"Aspect Ratio",tp:"select",o:["9:16","16:9","1:1"],d:"9:16"},
  {k:"render_bg",l:"Background Color",d:"#000000"}
]},
{t:"WATERMARK / LOGO",f:[
  {k:"logo_enabled",l:"Show Logo",tp:"toggle",d:true},
  {k:"logo_url",l:"Logo Image URL",d:"https://pub-b96dc727407242919393b2bef35ade2f.r2.dev/gods_knights.png"},
  {k:"logo_position",l:"Position",tp:"select",o:["topRight","topLeft","bottomRight","bottomLeft","center"],d:"topRight"},
  {k:"logo_scale",l:"Scale (0.01-1.0)",d:"0.12"},
  {k:"logo_opacity",l:"Opacity (0-1)",d:"0.8"}
]},
{t:"SCHEDULE",f:[
  {k:"sched_int",l:"Every (hours)",tp:"select",o:["4","6","8","12","24"],d:"8"},
  {k:"post_tt",l:"TikTok Time",d:"3:00 PM"},
  {k:"post_yt",l:"YouTube Time",d:"1:30 PM"},
  {k:"post_ig",l:"Instagram Time",d:"12:00 PM"},
  {k:"post_fb",l:"Facebook Time",d:"2:00 PM"}
]},
{t:"PLATFORMS",f:[
  {k:"on_tt",l:"TikTok",tp:"toggle",d:true},
  {k:"on_yt",l:"YouTube",tp:"toggle",d:true},
  {k:"on_ig",l:"Instagram",tp:"toggle",d:true},
  {k:"on_fb",l:"Facebook",tp:"toggle",d:true},
  {k:"on_tw",l:"X/Twitter",tp:"toggle",d:true},
  {k:"on_th",l:"Threads",tp:"toggle",d:true},
  {k:"on_pn",l:"Pinterest",tp:"toggle",d:false}
]}
];

async function go(){const p=$('pw').value;if(!p){$('le').style.display='block';return;}try{const r=await(await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:p})})).json();if(r.ok){if(r.token)sessionStorage.setItem('kt',r.token);$('L').style.display='none';$('A').style.display='block';init();}else{$('le').style.display='block';}}catch(e){$('le').style.display='block';}}
async function autoLogin(){const t=sessionStorage.getItem('kt');if(!t)return false;try{const r=await(await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:t})})).json();if(r.ok){$('L').style.display='none';$('A').style.display='block';init();return true;}}catch(e){}return false;}
autoLogin();

function sw(id,btn){document.querySelectorAll('[id^="t-"]').forEach(e=>e.style.display='none');$('t-'+id).style.display='block';document.querySelectorAll('.tb').forEach(t=>t.classList.remove('ac'));btn.classList.add('ac');if(id==='runs')loadRuns();if(id==='logs')loadLogs();if(id==='health')rH();if(id==='preview')rPv();}

function rP(){
  let h='';const isDone=!RN&&PD.length>0;PHS.forEach((p,i)=>{let s='waiting',c='',sl='';if(PD.includes(i)){s='done';c='dn';sl='COMPLETE';}else if(RN&&i===PH){s='running';c='rn';sl='ACTIVE';}else if(RN&&i<PH){s='done';c='dn';sl='COMPLETE';}else if(RN){c='dm';sl='';}else if(isDone){c='';sl='';}
    const nc=s==='done'?'var(--grn)':s==='running'?'var(--blu)':'var(--txtdd)';
    const nt=s==='done'?'var(--grn)':s==='running'?'var(--amb)':'var(--txtd)';
    h+=`<div class="ph ${c}"><div style="display:flex;align-items:center;gap:10px"><span style="font-size:12px;width:18px;text-align:center;color:${nc}">${p.i}</span><div style="flex:1"><div style="font-family:var(--f1);font-size:9px;font-weight:600;letter-spacing:2px;color:${nt}">${p.n}</div><div style="font-size:8px;color:var(--txtdd);margin-top:2px;letter-spacing:1px">${p.a} · ${p.d}</div></div><div style="display:flex;align-items:center;gap:6px">${sl?`<span style="font-family:var(--f1);font-size:7px;color:${nc};letter-spacing:2px">${sl}</span>`:''}${B(s)}</div></div></div>`;
  });$('pl').innerHTML=h;
  if(RN){$('pg').style.display='block';$('pb').style.width=(PD.length/PHS.length*100)+'%';$('pi').textContent='PHASE '+(PH+1)+'/11';$('pi').style.display='inline';$('rb').textContent='⏳ PROCESSING';$('rb').style.background='var(--bg)';$('rb').style.color='var(--txtd)';$('rb').style.border='1px solid var(--bd)';$('rb').style.boxShadow='none';}
  else{$('pg').style.display='none';$('pi').style.display='none';$('rb').textContent='▶ EXECUTE';$('rb').style.background='var(--amb)';$('rb').style.color='var(--bg)';$('rb').style.border='none';$('rb').style.boxShadow='0 0 10px rgba(227,160,40,.3)';
  if(d.result&&d.result.status==='failed'){$('rsb').style.display='inline-block';}else{$('rsb').style.display='none';}}
}

async function runNow(){if(RN)return;await fetch('/api/run',{method:'POST'});RN=true;PH=0;PD=[];$('rsb').style.display='none';rP();poll();}
async function resumeNow(){if(RN)return;const r=await fetch('/api/resume',{method:'POST'});const d=await r.json();if(r.ok){RN=true;PD=[];$('rsb').style.display='none';rP();poll();}else{alert(d.error||'Resume failed');}}
async function poll(){if(!RN)return;try{const r=await(await fetch('/api/status')).json();PH=r.phase;PD=r.phases_done||[];if(r.result)LAST_RESULT=r.result;if(!r.running){RN=false;rP();rPv();return;}RN=true;rP();setTimeout(poll,2000);}catch(e){setTimeout(poll,3000);}}

async function loadRuns(){try{const runs=await(await fetch('/api/runs')).json();const t=runs.length,ok=runs.filter(r=>r.status==='published'||r.status==='complete').length;
$('rs').innerHTML=[{l:'TOTAL',v:t,c:'amb'},{l:'SUCCESS',v:ok,c:'grn'},{l:'RATE',v:t?Math.round(ok/t*100)+'%':'0%',c:'blu'},{l:'FAILED',v:t-ok,c:'red'}].map(s=>`<div class="pnl" style="padding:12px 10px;text-align:center"><div style="font-family:var(--f1);font-size:18px;font-weight:800;color:var(--${s.c})">${s.v}</div><div style="font-family:var(--f1);font-size:7px;color:var(--${s.c});margin-top:3px;letter-spacing:2px;opacity:.6">${s.l}</div></div>`).join('');
$('rl').innerHTML=runs.length?runs.map(r=>`<div class="rw"><div style="display:flex;align-items:center;gap:10px"><div style="flex:1"><div style="font-family:var(--f2);font-size:13px;font-weight:600;color:var(--wht)">${r.topic||'?'}</div><div style="font-size:8px;color:var(--txtd);margin-top:2px;letter-spacing:1px">${r.date} · ${r.category||''} · ${r.duration||''}</div></div>${B(r.status==='published'||r.status==='complete'?'done':'failed',r.status)}</div>${r.error?`<div style="font-size:9px;color:var(--red);margin-top:6px;background:var(--red2);padding:4px 8px;border:1px solid rgba(224,64,40,.2)">${r.error}</div>`:''}</div>`).join(''):'<div class="rw" style="color:var(--txtd)">NO RUNS RECORDED</div>';}catch(e){}}

async function loadLogs(){try{const logs=await(await fetch('/api/logs')).json();$('lc').textContent=logs.length+' entries';
$('la').innerHTML=logs.length?logs.map(l=>`<div><span style="color:var(--txtdd)">${l.t}</span> <span style="color:var(--amb);background:var(--amblo);padding:0 4px;font-size:8px;letter-spacing:1px">${l.phase}</span> <span style="color:var(--${l.level==='ok'?'grn':l.level==='error'?'red':'txtd'})">${l.msg}</span></div>`).join(''):'<div style="color:var(--txtd)">No log output. Execute pipeline to begin.</div>';
$('la').scrollTop=$('la').scrollHeight;}catch(e){}}

// PREVIEW
async function rPv(){
  if(!LAST_RESULT){try{const lr=await(await fetch('/api/last-result')).json();if(lr&&lr.status)LAST_RESULT=lr;}catch(e){}}
  const r=LAST_RESULT;
  if(!r){$('pv-empty').style.display='block';$('pv-images').style.display='none';$('pv-videos').style.display='none';$('pv-final').style.display='none';$('pv-script').style.display='none';return;}
  $('pv-empty').style.display='none';

  if(r.images&&r.images.length){
    $('pv-images').style.display='block';
    $('pv-img-grid').innerHTML=r.images.map(img=>`<div class="preview-card"><img src="${img.url}" alt="Scene ${img.index}" loading="lazy"><div class="preview-label">SCENE ${img.index}</div><a class="dl-btn" href="${img.url}" download target="_blank">⬇ DL</a></div>`).join('');
  }else{$('pv-images').style.display='none';}

  if(r.videos&&r.videos.length){
    $('pv-videos').style.display='block';
    $('pv-vid-grid').innerHTML=r.videos.map(v=>`<div class="preview-card"><video src="${v.url}" muted loop playsinline onmouseenter="this.play()" onmouseleave="this.pause();this.currentTime=0"></video><div class="preview-label">CLIP ${v.index}</div><a class="dl-btn" href="${v.url}" download target="_blank">⬇ DL</a></div>`).join('');
  }else{$('pv-videos').style.display='none';}

  if(r.final_video){
    $('pv-final').style.display='block';
    $('pv-final-vid').src=r.final_video;
    $('pv-final-dl').href=r.final_video;
  }else{$('pv-final').style.display='none';}

  if(r.script&&r.script.script_full){
    $('pv-script').style.display='block';
    $('pv-script-text').textContent=r.script.script_full;
  }else{$('pv-script').style.display='none';}
}

let stOpen={};
// MODEL CATALOGS — only models that support 9:16 natively
// Price = approx cost per image on Replicate
const IMG_MODELS={
  replicate:[
    {v:"google/nano-banana-pro",l:"Nano Banana Pro — BEST ~$0.10"},
    {v:"google/nano-banana",l:"Nano Banana — Fast ~$0.02"},
    {v:"xai/grok-imagine-image",l:"Grok Aurora — Cinematic ~$0.07"},
    {v:"bytedance/seedream-4.5",l:"Seedream 4.5 — Great ~$0.03"},
    {v:"black-forest-labs/flux-1.1-pro",l:"Flux 1.1 Pro — Top ~$0.04"},
    {v:"black-forest-labs/flux-schnell",l:"Flux Schnell — Cheap ~$0.003"},
    {v:"black-forest-labs/flux-dev",l:"Flux Dev — Open ~$0.03"},
    {v:"ideogram-ai/ideogram-v3-quality",l:"Ideogram v3 Quality ~$0.08"},
    {v:"ideogram-ai/ideogram-v3-turbo",l:"Ideogram v3 Turbo ~$0.02"},
    {v:"recraft-ai/recraft-v3",l:"Recraft v3 — Design ~$0.04"},
    {v:"stability-ai/stable-diffusion-3.5-large",l:"SD 3.5 Large ~$0.035"},
    {v:"google-deepmind/imagen-4-preview",l:"Imagen 4 Preview ~$0.04"},
  ]
};
const VID_MODELS={
  replicate:[
    {v:"bytedance/seedance-1-lite",l:"Seedance Lite — Fast ~$0.25/5s"},
    {v:"bytedance/seedance-1",l:"Seedance Pro — Best ~$0.50/5s"},
    {v:"wavespeedai/wan-2.1-i2v-480p",l:"Wan 2.1 480p — Cheap ~$0.10"},
    {v:"wavespeedai/wan-2.1-i2v-720p",l:"Wan 2.1 720p ~$0.20"},
    {v:"xai/grok-imagine-video",l:"Grok Imagine — +Audio ~$0.30"},
    {v:"minimax/video-01-live",l:"Minimax Live ~$0.25"},
    {v:"minimax/video-01",l:"Minimax v01 ~$0.50"},
    {v:"kwaivgi/kling-v2.0-image-to-video",l:"Kling v2.0 ~$0.30"},
    {v:"luma/ray-2-flash",l:"Luma Ray 2 Flash ~$0.20"},
    {v:"luma/ray-2",l:"Luma Ray 2 — Premium ~$0.40"},
    {v:"google-deepmind/veo-3",l:"Veo 3 — Premium ~$0.50"},
  ]
};
function getModels(fieldKey){
  const prov=fieldKey==='image_model'?(ST.image_provider||'replicate'):(ST.video_provider||'replicate');
  const cat=fieldKey==='image_model'?IMG_MODELS:VID_MODELS;
  return cat[prov]||[];
}

function rSt(){let h='';STS.forEach((sec,si)=>{let ff='';sec.f.forEach(f=>{const v=ST[f.k]!==undefined?ST[f.k]:f.d;
if(f.tp==='toggle'){const on=v===true||v==='true';ff+=`<div class="fi" style="display:flex;align-items:center;justify-content:space-between"><div style="font-size:11px;color:var(--wht)">${f.l}</div><button class="tg ${on?'on':'off'}" onclick="event.stopPropagation();ST['${f.k}']=!(ST['${f.k}']===true||ST['${f.k}']==='true');rSt()"><span class="td" style="left:${on?'20px':'2px'}"></span></button></div>`;}
else if(f.tp==='select'){
  let opts=f.o;
  if(f.dep){opts=getModels(f.k);ff+=`<div class="fi"><div class="fl">${f.l}</div><select class="fin" onchange="ST['${f.k}']=this.value">${opts.map(o=>`<option value="${o.v}"${o.v==v?' selected':''}>${o.l}</option>`).join('')}</select></div>`;}
  else if(f.k==='image_provider'||f.k==='video_provider'||f.k==='clip_count'||f.k==='clip_duration'){ff+=`<div class="fi"><div class="fl">${f.l}</div><select class="fin" onchange="ST['${f.k}']=this.value;rSt()">${opts.map(o=>`<option${o==v?' selected':''}>${o}</option>`).join('')}</select></div>`;}
  else{ff+=`<div class="fi"><div class="fl">${f.l}</div><select class="fin" onchange="ST['${f.k}']=this.value">${opts.map(o=>`<option${o==v?' selected':''}>${o}</option>`).join('')}</select></div>`;}
}
else if(f.tp==='computed'){
  const clips=parseInt(ST['clip_count'])||3;const dur=parseInt(ST['clip_duration'])||10;const total=clips*dur;
  const words=parseInt(ST['script_words'])||90;const voSec=Math.round(words/3);
  const diff=total-voSec;const warn=diff>10?'⚠ Voiceover '+diff+'s shorter than video':'✓ Well matched';
  const wc=diff>10?'var(--red)':'var(--grn)';
  ff+=`<div class="fi" style="border:1px solid var(--bd2);padding:8px 10px;background:rgba(224,175,56,.04)"><div style="display:flex;justify-content:space-between;align-items:center"><div style="font-family:var(--f1);font-size:9px;letter-spacing:2px;color:var(--txtd)">TOTAL VIDEO</div><div style="font-family:var(--f1);font-size:16px;font-weight:800;color:var(--amb)">${total}s</div></div><div style="display:flex;justify-content:space-between;margin-top:4px"><div style="font-size:8px;color:var(--txtdd)">${clips} clips × ${dur}s each</div><div style="font-size:8px;color:${wc}">${warn}</div></div></div>`;
}
else if(f.tp==='slider'){
  const mn=f.min||30,mx=f.max||180,stp=f.step||5;const cv=parseInt(v)||f.d;const secs=Math.round(cv/3);
  const pct=((cv-mn)/(mx-mn))*100;
  const durLabel=secs>=60?Math.floor(secs/60)+'m '+(secs%60?secs%60+'s':''):secs+'s';
  ff+=`<div class="fi"><div class="fl">${f.l}</div><div style="display:flex;align-items:center;gap:10px;width:100%"><input type="range" min="${mn}" max="${mx}" step="${stp}" value="${cv}" class="fin-slider" style="flex:1;accent-color:var(--amb);height:6px;cursor:pointer" oninput="ST['${f.k}']=parseInt(this.value);document.getElementById('sl_${f.k}').innerHTML=this.value+' words ≈ '+Math.round(this.value/3)+'s'+(Math.round(this.value/3)>=60?' ('+Math.floor(Math.round(this.value/3)/60)+'m '+(Math.round(this.value/3)%60?Math.round(this.value/3)%60+'s':'')+')'    :'');document.getElementById('sl_${f.k}_bar').style.width=((this.value-${mn})/(${mx}-${mn})*100)+'%'"><div id="sl_${f.k}" style="min-width:120px;font-family:var(--f1);font-size:10px;letter-spacing:1px;color:var(--amb);text-align:right">${cv} words ≈ ${durLabel}</div></div><div style="position:relative;height:3px;background:var(--bg3);border-radius:2px;margin-top:4px;overflow:hidden"><div id="sl_${f.k}_bar" style="position:absolute;top:0;left:0;height:100%;background:var(--amb);border-radius:2px;width:${pct}%;transition:width .1s"></div></div><div style="display:flex;justify-content:space-between;margin-top:3px"><span style="font-size:7px;color:var(--txtdd);letter-spacing:1px">${mn}w / ${Math.round(mn/3)}s</span><span style="font-size:7px;color:var(--txtdd);letter-spacing:1px">${mx}w / ${Math.round(mx/3)}s (1min)</span></div></div>`;
}
else{ff+=`<div class="fi"><div class="fl">${f.l}</div><input class="fin" value="${v||''}" onchange="ST['${f.k}']=this.value"></div>`;}
});h+=`<div class="sec"><button class="sec-h" onclick="stOpen[${si}]=!stOpen[${si}];rSt()"><span class="sec-t">${sec.t}</span><span class="sec-a" style="transform:${stOpen[si]?'rotate(90deg)':''}">›</span></button><div class="sec-b${stOpen[si]?'':' hd'}">${ff}</div></div>`;});
$('sf').innerHTML=h;}

async function saveSett(){await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(ST)});$('ss').style.display='block';setTimeout(()=>$('ss').style.display='none',3000);}

async function rH(){try{const cfg=await(await fetch('/api/config')).json();
const svcs=[{n:"OPENAI",d:"GPT-4o + Whisper",k:"openai"},{n:"REPLICATE",d:"Image + Video Models",k:"replicate"},{n:"ELEVENLABS",d:"Voice Synthesis",k:"elevenlabs"},{n:"SHOTSTACK",d:"Video Rendering",k:"shotstack"},{n:"R2",d:"Asset Storage",k:"r2"},{n:"AIRTABLE",d:"Topic Database",k:"airtable"},{n:"BLOTATO",d:"Publishing",k:"blotato"}];
$('hl').innerHTML='<div class="rw"><span style="font-family:var(--f1);font-size:8px;color:var(--txtd);letter-spacing:3px">API CONNECTIONS</span></div>'+svcs.map(s=>`<div class="rw" style="display:flex;justify-content:space-between;align-items:center"><div><div style="font-family:var(--f1);font-size:10px;font-weight:600;letter-spacing:2px;color:var(--wht)">${s.n}</div><div style="font-size:8px;color:var(--txtd);margin-top:2px;letter-spacing:1px">${s.d}</div></div>${B(cfg[s.k]?'configured':'missing')}</div>`).join('');}catch(e){}}

async function testAll(){alert('Testing connections...');for(const s of['openai','replicate','elevenlabs','airtable']){try{const r=await(await fetch('/api/test-connection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service:s})})).json();console.log(s,r);}catch(e){}}rH();alert('Done! Check Status tab.');}

async function init(){
  rP();
  try{const r=await(await fetch('/api/settings')).json();STS.forEach(s=>s.f.forEach(f=>{if(r[f.k]!==undefined)ST[f.k]=r[f.k];else ST[f.k]=f.d;}));}catch(e){STS.forEach(s=>s.f.forEach(f=>ST[f.k]=f.d));}
  rSt();
  try{const r=await(await fetch('/api/status')).json();if(r.result){LAST_RESULT=r.result;PD=r.phases_done||[];}if(r.running){RN=true;PH=r.phase;PD=r.phases_done||[];rP();poll();}else{rP();}}catch(e){}
}
</script></body></html>
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
