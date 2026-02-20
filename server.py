"""
Knights Reactor — Web Server v3
Full admin dashboard: Pipeline, Topics, Runs, Logs, Settings, Credentials, Health
Phase 2: Topic DB, Prompt Editing Gates, Video Approval Gates
"""

import json, os, threading, time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse

from pipeline import (
    run_pipeline, Config, DATA_DIR as PIPELINE_DATA_DIR,
    load_topics, save_topics, add_topic, delete_topic,
    fetch_next_topic, generate_topics_ai, seed_default_topics,
    generate_video_single,
)
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

def execute_pipeline(resume_from: int = 0, topic_id: str = None):
    apply_model_settings()  # Reload model selections before each run
    CURRENT_RUN.update({"active": True, "started": datetime.now().isoformat(), "result": None, "phase": 0, "phase_name": "", "phases_done": []})
    if resume_from == 0:
        LOGS.clear()
    log_entry("System", "info", f"Pipeline {'resumed from phase ' + str(resume_from) if resume_from else 'started'}{' (topic: '+topic_id+')' if topic_id else ''}")

    def on_phase(phase_index, phase_name, status):
        if status == "running":
            CURRENT_RUN["phase"] = phase_index
            CURRENT_RUN["phase_name"] = phase_name
            log_entry(phase_name, "info", f"Starting...")
        elif status == "done":
            if phase_index not in CURRENT_RUN["phases_done"]:
                CURRENT_RUN["phases_done"].append(phase_index)
            log_entry(phase_name, "ok", f"Complete ✓")

    result = run_pipeline(progress_cb=on_phase, resume_from=resume_from, topic_id=topic_id)

    # Handle gate pauses (pipeline returned early, not finished)
    gate = result.get("gate")
    if gate:
        CURRENT_RUN.update({"active": False, "result": result})
        log_entry("System", "info", f"⏸️ Gate: {gate} — awaiting approval")
        return

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
    log_entry("System", "ok" if result.get("status") in ("published","complete") else "error", f"Pipeline finished: {result.get('status')}")

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
async def trigger_run(bg: BackgroundTasks, req: Request):
    if CURRENT_RUN["active"]: return JSONResponse({"error": "Already running"}, 409)
    body = {}
    try: body = await req.json()
    except: pass
    topic_id = body.get("topic_id")
    bg.add_task(execute_pipeline, 0, topic_id)
    return {"status": "started", "topic_id": topic_id}

@app.post("/api/resume")
async def trigger_resume(bg: BackgroundTasks):
    """Resume pipeline from the last failed/gated phase."""
    if CURRENT_RUN["active"]: return JSONResponse({"error": "Already running"}, 409)
    last_result = CURRENT_RUN.get("result", {}) or {}
    # Gate resume: use gate_phase if set, otherwise failed_phase
    resume_phase = last_result.get("gate_phase") or last_result.get("failed_phase", 0)
    ckpt_path = DATA_DIR / "pipeline_checkpoint.json"
    if not ckpt_path.exists():
        return JSONResponse({"error": "No checkpoint found — run fresh pipeline instead"}, 400)
    bg.add_task(execute_pipeline, resume_phase)
    return {"status": "resuming", "from_phase": resume_phase}

# ─── TOPIC DATABASE ──────────────────────────────────────────

@app.get("/api/topics")
async def get_topics():
    topics = load_topics()
    return {"topics": topics, "total": len(topics), "new": sum(1 for t in topics if t.get("status") == "new")}

@app.post("/api/topics")
async def create_topic(req: Request):
    body = await req.json()
    t = add_topic(body.get("idea",""), body.get("category","Shocking Revelations"), body.get("scripture",""))
    return {"status": "created", "topic": t}

@app.delete("/api/topics/{topic_id}")
async def remove_topic(topic_id: str):
    ok = delete_topic(topic_id)
    return {"status": "deleted" if ok else "not_found"}

@app.post("/api/topics/generate")
async def gen_topics(req: Request, bg: BackgroundTasks):
    body = {}
    try: body = await req.json()
    except: pass
    count = body.get("count", 10)
    try:
        new_topics = generate_topics_ai(count)
        return {"status": "generated", "count": len(new_topics), "topics": new_topics}
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)

@app.post("/api/topics/seed")
async def seed_topics():
    seed_default_topics()
    return {"status": "seeded", "total": len(load_topics())}

# ─── PROMPT EDITING GATE ─────────────────────────────────────

@app.get("/api/prompts")
async def get_prompts():
    """Return current clips from checkpoint for editing."""
    ckpt_path = DATA_DIR / "pipeline_checkpoint.json"
    if not ckpt_path.exists():
        return {"clips": [], "error": "No checkpoint"}
    ckpt = json.loads(ckpt_path.read_text())
    clips = ckpt.get("clips", [])
    script = ckpt.get("script", {})
    topic = ckpt.get("topic", {})
    return {"clips": clips, "script": script, "topic": topic}

@app.post("/api/prompts/save")
async def save_prompts(req: Request):
    """Save edited prompts to checkpoint as clips_edited."""
    body = await req.json()
    edited_clips = body.get("clips", [])
    ckpt_path = DATA_DIR / "pipeline_checkpoint.json"
    if not ckpt_path.exists():
        return JSONResponse({"error": "No checkpoint"}, 400)
    ckpt = json.loads(ckpt_path.read_text())
    ckpt["clips_edited"] = edited_clips
    ckpt_path.write_text(json.dumps(ckpt))
    return {"status": "saved", "clips": len(edited_clips)}

# ─── VIDEO APPROVAL GATE ─────────────────────────────────────

@app.get("/api/videos/review")
async def get_videos_for_review():
    """Return current clips with videos from checkpoint for approval."""
    ckpt_path = DATA_DIR / "pipeline_checkpoint.json"
    if not ckpt_path.exists():
        return {"clips": [], "error": "No checkpoint"}
    ckpt = json.loads(ckpt_path.read_text())
    clips = ckpt.get("clips_with_videos", [])
    return {"clips": clips}

@app.post("/api/videos/approve")
async def approve_videos(req: Request):
    """Mark videos as approved and save to checkpoint."""
    body = await req.json()
    approved_clips = body.get("clips", [])
    ckpt_path = DATA_DIR / "pipeline_checkpoint.json"
    if not ckpt_path.exists():
        return JSONResponse({"error": "No checkpoint"}, 400)
    ckpt = json.loads(ckpt_path.read_text())
    ckpt["clips_approved"] = approved_clips
    ckpt_path.write_text(json.dumps(ckpt))
    return {"status": "approved", "clips": len(approved_clips)}

@app.post("/api/videos/regen")
async def regen_video(req: Request):
    """Regenerate a single video clip by index."""
    body = await req.json()
    clip_index = body.get("index")
    ckpt_path = DATA_DIR / "pipeline_checkpoint.json"
    if not ckpt_path.exists():
        return JSONResponse({"error": "No checkpoint"}, 400)
    ckpt = json.loads(ckpt_path.read_text())
    clips = ckpt.get("clips_with_videos", [])
    target = None
    for c in clips:
        if c.get("index") == clip_index:
            target = c
            break
    if not target:
        return JSONResponse({"error": f"Clip {clip_index} not found"}, 404)
    try:
        target = generate_video_single(target)
        # Update in clips list
        for i, c in enumerate(clips):
            if c.get("index") == clip_index:
                clips[i] = target
                break
        ckpt["clips_with_videos"] = clips
        ckpt_path.write_text(json.dumps(ckpt))
        return {"status": "regenerated", "clip": target}
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)

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
            "r2": bool(Config.R2_ACCESS_KEY), "blotato": bool(Config.BLOTATO_KEY)}

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
        return {"ok": False, "error": "Unknown"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ─── DASHBOARD ────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard(): return HTML


# Load HTML from external file
_html_path = Path(__file__).parent / "dashboard.html"
if _html_path.exists():
    HTML = _html_path.read_text()
else:
    HTML = "<h1>Dashboard not found</h1><p>Place dashboard.html next to server.py</p>"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
