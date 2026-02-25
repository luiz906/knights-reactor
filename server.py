"""
Knights Reactor — Web Server v3
Full admin dashboard: Pipeline, Topics, Runs, Logs, Settings, Credentials, Health
Phase 2: Topic DB, Prompt Editing Gates, Video Approval Gates
"""

import json, os, threading, time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, Request, UploadFile, File
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
BRANDS_DIR = DATA_DIR / "brands"
BRANDS_DIR.mkdir(exist_ok=True)

# ─── BRAND SYSTEM ─────────────────────────────────────────────
ACTIVE_BRAND_FILE = DATA_DIR / "active_brand.txt"

def get_active_brand() -> str:
    if ACTIVE_BRAND_FILE.exists():
        return ACTIVE_BRAND_FILE.read_text().strip() or "knights"
    return "knights"

def set_active_brand(name: str):
    ACTIVE_BRAND_FILE.write_text(name)

def brand_dir(name: str = None) -> Path:
    name = name or get_active_brand()
    d = BRANDS_DIR / name
    d.mkdir(exist_ok=True)
    return d

def migrate_legacy_data():
    """Move existing flat files into default 'knights' brand folder."""
    bd = brand_dir("knights")
    for fname in ["credentials.json", "settings.json", "runs.json", "topics.json", "pipeline_checkpoint.json"]:
        src = DATA_DIR / fname
        dst = bd / fname
        if src.exists() and not dst.exists():
            import shutil
            shutil.move(str(src), str(dst))

migrate_legacy_data()

def CREDS_FILE():  return brand_dir() / "credentials.json"
def SETTINGS_FILE(): return brand_dir() / "settings.json"
def RUNS_FILE():   return brand_dir() / "runs.json"
def TOPICS_FILE(): return brand_dir() / "topics.json"

def load_json(path, default=None):
    p = path() if callable(path) else path
    if p.exists():
        try: return json.loads(p.read_text())
        except: pass
    return default if default is not None else {}

def save_json(path, data):
    p = path() if callable(path) else path
    p.write_text(json.dumps(data, indent=2))

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
    if s.get("scene_intensity"): Config.SCENE_INTENSITY = s["scene_intensity"]
    if s.get("scene_camera"):   Config.SCENE_CAMERA = s["scene_camera"]
    if s.get("scene_mood"):     Config.SCENE_MOOD_BIAS = s["scene_mood"]
    if s.get("scene_story"):    Config.SCENE_STORY = s["scene_story"]
    if s.get("scene_theme"):    Config.SCENE_THEME = s["scene_theme"]
    if s.get("scene_figure"):   Config.SCENE_FIGURE = s["scene_figure"]
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
    if "logo_enabled" in s:    Config.LOGO_ENABLED = s["logo_enabled"] in (True, "true", "True")
    if "captions_enabled" in s: Config.CAPTIONS_ENABLED = s["captions_enabled"] in (True, "true", "True")
    if s.get("logo_position"):  Config.LOGO_POSITION = s["logo_position"]
    if s.get("logo_scale"):     Config.LOGO_SCALE = float(s["logo_scale"])
    if s.get("logo_opacity"):   Config.LOGO_OPACITY = float(s["logo_opacity"])
    # Video timeout
    if s.get("video_timeout"):  Config.VIDEO_TIMEOUT = int(s["video_timeout"])
    if s.get("shotstack_env"):  Config.SHOTSTACK_ENV = s["shotstack_env"]
    # Platforms
    for pk in ["on_tt","on_yt","on_ig","on_fb","on_tw","on_th","on_pn"]:
        if pk in s: setattr(Config, pk.upper(), s[pk] in (True, "true", "True"))
    # Brand / Persona
    if s.get("brand_name"):    Config.BRAND_NAME = s["brand_name"]
    if s.get("brand_persona"): Config.BRAND_PERSONA = s["brand_persona"]
    if s.get("brand_voice"):   Config.BRAND_VOICE = s["brand_voice"]
    if s.get("brand_themes"):  Config.BRAND_THEMES = s["brand_themes"]
    if s.get("brand_avoid"):   Config.BRAND_AVOID = s["brand_avoid"]

apply_credentials()
apply_model_settings()

# ─── STATE ────────────────────────────────────────────────────
RUNS = load_json(RUNS_FILE, []) if RUNS_FILE().exists() else []
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

def execute_pipeline(resume_from: int = 0, topic_id: str = None, manual_clips: list = None, manual_voiceover: str = None):
    apply_model_settings()  # Reload model selections before each run
    mode = "full-manual" if (manual_clips and manual_voiceover) else ("manual" if manual_clips else ("resume" if resume_from > 0 else "normal"))
    CURRENT_RUN.update({"active": True, "started": datetime.now().isoformat(), "result": None, "phase": 0, "phase_name": "", "phases_done": []})
    if resume_from == 0:
        LOGS.clear()
    log_entry("System", "info", f"Pipeline {mode} mode{' (topic: '+topic_id+')' if topic_id else ''}{' — '+str(len(manual_clips))+' clips' if manual_clips else ''}{' + voiceover' if manual_voiceover else ''}")

    def on_phase(phase_index, phase_name, status):
        if status == "running":
            CURRENT_RUN["phase"] = phase_index
            CURRENT_RUN["phase_name"] = phase_name
            log_entry(phase_name, "info", f"Starting...")
        elif status == "done":
            if phase_index not in CURRENT_RUN["phases_done"]:
                CURRENT_RUN["phases_done"].append(phase_index)
            log_entry(phase_name, "ok", f"Complete ✓")

    result = run_pipeline(progress_cb=on_phase, resume_from=resume_from, topic_id=topic_id, manual_clips=manual_clips, manual_voiceover=manual_voiceover)

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
# ─── BRAND API ────────────────────────────────────────────────
@app.get("/api/brands")
async def list_brands():
    """List all brands and active brand."""
    brands = []
    for d in sorted(BRANDS_DIR.iterdir()):
        if d.is_dir():
            s = load_json(d / "settings.json", {})
            brands.append({
                "id": d.name,
                "display_name": s.get("brand_name", d.name.replace("_"," ").title()),
                "topics": len(load_json(d / "topics.json", [])),
                "runs": len(load_json(d / "runs.json", [])),
            })
    if not brands:
        # Create default brand
        brand_dir("knights")
        brands = [{"id": "knights", "display_name": "Knights Reactor", "topics": 0, "runs": 0}]
    return {"brands": brands, "active": get_active_brand()}

@app.post("/api/brands/switch")
async def switch_brand(req: Request):
    """Switch active brand. Reloads all config."""
    global RUNS, CURRENT_RUN
    body = await req.json()
    name = body.get("brand", "").strip().lower().replace(" ", "_")
    if not name:
        return JSONResponse({"error": "Brand name required"}, 400)
    bd = brand_dir(name)
    set_active_brand(name)
    # Reload everything for new brand
    apply_credentials()
    apply_model_settings()
    RUNS = load_json(RUNS_FILE, []) if RUNS_FILE().exists() else []
    CURRENT_RUN = {"active": False, "result": None, "phase": 0, "phase_name": "", "phases_done": []}
    return {"status": "switched", "brand": name}

@app.post("/api/brands/create")
async def create_brand(req: Request):
    """Create a new brand."""
    body = await req.json()
    name = body.get("name", "").strip().lower().replace(" ", "_")
    display = body.get("display_name", name.replace("_"," ").title())
    if not name or not name.replace("_","").isalnum():
        return JSONResponse({"error": "Invalid brand name (letters, numbers, underscores only)"}, 400)
    bd = brand_dir(name)
    # Save initial settings with brand name
    s = load_json(bd / "settings.json", {})
    s["brand_name"] = display
    save_json(bd / "settings.json", s)
    return {"status": "created", "brand": name, "display_name": display}

@app.post("/api/brands/delete")
async def delete_brand(req: Request):
    """Delete a brand (cannot delete active brand)."""
    body = await req.json()
    name = body.get("brand", "").strip()
    if name == get_active_brand():
        return JSONResponse({"error": "Cannot delete active brand. Switch first."}, 400)
    bd = BRANDS_DIR / name
    if bd.exists() and bd.is_dir():
        import shutil
        shutil.rmtree(bd)
    return {"status": "deleted", "brand": name}

# ─── SCENE PACK API ──────────────────────────────────────────

@app.get("/api/scenes")
async def get_scenes():
    """Get scene pack for the active brand. Returns JSON structure or empty if using defaults."""
    from phases.scenes import load_brand_scenes, export_default_scenes
    data = load_brand_scenes()
    if data:
        return {"source": "brand", "data": data}
    return {"source": "default", "data": export_default_scenes()}

@app.post("/api/scenes")
async def save_scenes(req: Request):
    """Save scene pack for the active brand."""
    from phases.scenes import save_brand_scenes
    body = await req.json()
    save_brand_scenes(body)
    return {"status": "saved", "stories": len(body.get("stories", [])), "figures": len(body.get("figures", []))}

@app.post("/api/scenes/seed-defaults")
async def seed_default_scenes():
    """Copy the hardcoded knight defaults into the active brand's scenes.json (for editing)."""
    from phases.scenes import export_default_scenes, save_brand_scenes
    data = export_default_scenes()
    save_brand_scenes(data)
    return {"status": "seeded", "stories": len(data["stories"]), "figures": len(data["figures"])}

@app.get("/api/scenes/summary")
async def scenes_summary():
    """Quick summary of the active brand's scene pack."""
    from phases.scenes import load_brand_scenes, STORY_SEEDS, FIGURES
    data = load_brand_scenes()
    if data:
        stories = data.get("stories", [])
        return {
            "source": "brand",
            "stories": len(stories),
            "figures": len(data.get("figures", [])),
            "moods": list(data.get("moods", {}).keys()),
            "themes": list(data.get("themes", {}).keys()),
            "story_names": [s["name"] for s in stories],
        }
    return {
        "source": "default (knights)",
        "stories": len(STORY_SEEDS),
        "figures": len(FIGURES),
        "moods": ["storm", "fire", "dawn", "night", "grey", "battle"],
        "themes": ["temptation", "endurance", "doubt", "discipline", "courage", "duty", "loss", "patience", "anger", "identity"],
        "story_names": [s["name"] for s in STORY_SEEDS],
    }

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
    ckpt_path = brand_dir() / "pipeline_checkpoint.json"
    if not ckpt_path.exists():
        return JSONResponse({"error": "No checkpoint found — run fresh pipeline instead"}, 400)
    bg.add_task(execute_pipeline, resume_phase)
    return {"status": "resuming", "from_phase": resume_phase}

@app.post("/api/manual-run")
async def trigger_manual_run(bg: BackgroundTasks, req: Request):
    """Run pipeline with user-provided video clips and optional voiceover."""
    if CURRENT_RUN["active"]: return JSONResponse({"error": "Already running"}, 409)
    body = await req.json()
    clip_urls = body.get("clips", [])
    voiceover_url = body.get("voiceover", "").strip()
    cta_url = body.get("cta_url", "").strip()
    topic_id = body.get("topic_id")
    if not clip_urls or len(clip_urls) < 1:
        return JSONResponse({"error": "Provide at least 1 clip URL"}, 400)
    # Validate clip URLs
    valid = [u.strip() for u in clip_urls if u and u.strip().startswith("http")]
    if not valid:
        return JSONResponse({"error": "No valid clip URLs provided"}, 400)
    # Validate voiceover URL if provided
    vo = voiceover_url if voiceover_url.startswith("http") else None
    # Override CTA if provided
    if cta_url and cta_url.startswith("http"):
        Config.CTA_URL = cta_url
        Config.CTA_ENABLED = True
    # Full manual = clips + voiceover (skip all AI gen)
    # Partial manual = clips only (still generates script + voiceover via AI)
    mode = "full-manual" if vo else "manual"
    if vo:
        topic_id = None  # Full manual doesn't need a topic
    bg.add_task(execute_pipeline, 0, topic_id, valid, vo)
    return {"status": "started", "mode": mode, "clips": len(valid), "voiceover": bool(vo), "cta": bool(cta_url)}

@app.post("/api/script-only")
async def generate_script_only(req: Request):
    """Generate script + scene prompts for a topic — no media, no render."""
    from phases.topics import fetch_topic
    from phases.script import generate_script
    from phases.scenes import scene_engine
    apply_model_settings()
    body = await req.json()
    topic_id = body.get("topic_id")
    try:
        topic = fetch_topic(topic_id)
        script = generate_script(topic)
        clips = scene_engine(script, topic)
        return {"status": "ok", "topic": topic, "script": script, "clips": clips}
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)

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
    ckpt_path = brand_dir() / "pipeline_checkpoint.json"
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
    ckpt_path = brand_dir() / "pipeline_checkpoint.json"
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
    ckpt_path = brand_dir() / "pipeline_checkpoint.json"
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
    ckpt_path = brand_dir() / "pipeline_checkpoint.json"
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
    ckpt_path = brand_dir() / "pipeline_checkpoint.json"
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

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a video/audio file to R2, return public URL."""
    from phases.render import get_s3_client
    import uuid

    data = await file.read()
    if len(data) > 200 * 1024 * 1024:  # 200MB limit
        return JSONResponse({"error": "File too large (max 200MB)"}, 413)

    # Detect content type from magic bytes
    ct = file.content_type or "application/octet-stream"
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"

    # Video detection
    if data[:4] == b'\x1a\x45\xdf\xa3':
        ct = "video/webm"; ext = "webm"
    elif data[4:8] == b'ftyp':
        ct = "video/mp4"; ext = "mp4"
    # Audio detection
    elif data[:3] == b'ID3' or data[:2] in (b'\xff\xfb', b'\xff\xf3'):
        ct = "audio/mpeg"; ext = "mp3"
    elif data[:4] == b'RIFF' and data[8:12] == b'WAVE':
        ct = "audio/wav"; ext = "wav"
    elif data[:4] == b'fLaC':
        ct = "audio/flac"; ext = "flac"
    elif data[4:8] == b'ftyp' and b'M4A' in data[8:16]:
        ct = "audio/mp4"; ext = "m4a"

    # Upload to R2
    short_id = uuid.uuid4().hex[:8]
    safe_name = file.filename.rsplit(".", 1)[0][:30].replace(" ", "_")
    key = f"_uploads/{safe_name}_{short_id}.{ext}"

    s3 = get_s3_client()
    s3.put_object(
        Bucket=Config.R2_BUCKET,
        Key=key,
        Body=data,
        ContentType=ct,
    )

    url = f"{Config.R2_PUBLIC_URL}/{key}"
    log_entry("Upload", "ok", f"Uploaded {file.filename} → {key} ({len(data)//1024}KB)")
    return {"url": url, "filename": file.filename, "size": len(data), "content_type": ct}

@app.post("/api/probe")
async def probe_media(req: Request):
    """Probe a video/audio URL via Shotstack to get duration."""
    body = await req.json()
    url = body.get("url", "").strip()
    if not url:
        return JSONResponse({"error": "No URL"}, 400)
    import requests as rq
    from urllib.parse import quote
    try:
        ss_env = getattr(Config, 'SHOTSTACK_ENV', 'stage')
        encoded = quote(url, safe='')
        probe_url = f"https://api.shotstack.io/{ss_env}/probe/{encoded}"
        r = rq.get(probe_url, headers={"x-api-key": Config.SHOTSTACK_KEY}, timeout=15)
        if r.status_code == 200:
            data = r.json().get("response", {}).get("metadata", {})
            duration = float(data.get("format", {}).get("duration", 0))
            streams = data.get("streams", [])
            # Get resolution from first video stream
            width = height = 0
            for s in streams:
                if s.get("codec_type") == "video":
                    width = s.get("width", 0)
                    height = s.get("height", 0)
                    break
            return {"duration": round(duration, 2), "width": width, "height": height}
        return JSONResponse({"error": f"Probe failed ({r.status_code})"}, 400)
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
