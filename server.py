"""
Knights Reactor — Web Server v3
Full admin dashboard: Pipeline, Topics, Runs, Logs, Settings, Credentials, Health
Phase 2: Topic DB, Prompt Editing Gates, Video Approval Gates
"""

import json, os, threading, time, hashlib, hmac, base64, logging
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
import requests as _rq

ap_log = logging.getLogger("autopost")

app = FastAPI(title="Knights Reactor")

# ─── STATIC FILES & SUB-APPS ─────────────────────────────────
from fastapi.staticfiles import StaticFiles
import shutil as _shutil

_APP_DIR = Path(__file__).parent
_static_dir = _APP_DIR / "static"
_static_dir.mkdir(exist_ok=True)

# If CSS/JS files are at root level (flat repo), copy into static/
for _fname in ["style.css", "app.js", "graphics.css", "autopost.js"]:
    _root = _APP_DIR / _fname
    _dest = _static_dir / _fname
    if _root.exists() and (not _dest.exists() or _root.stat().st_mtime > _dest.stat().st_mtime):
        _shutil.copy2(str(_root), str(_dest))

app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

try:
    from graphics import router as graphics_router
    app.include_router(graphics_router)
except ImportError:
    pass

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

# One-time brand seeds (safe to re-run, won't overwrite existing data)
try:
    import seed_attic_magic
except Exception as e:
    print(f"Brand seed note: {e}")

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

# ══════════════════════════════════════════════════════════════
# AUTOPOST v2 — Brand-aware Dropbox → Blotato image publisher
# ══════════════════════════════════════════════════════════════
AP_RUNS_FILE = DATA_DIR / "ap_runs.json"
AP_RUNS = load_json(AP_RUNS_FILE, []) if AP_RUNS_FILE.exists() else []
AP_JOBS = {}
AP_TOKEN_CACHE = {"token": None, "expires": 0}
AP_CURSORS = {}  # {brand_name: cursor_string}

def _ap_env(key, fallback=""):
    return os.getenv(key, fallback)

def _ap_get_access_token():
    now = time.time()
    if AP_TOKEN_CACHE["token"] and AP_TOKEN_CACHE["expires"] > now + 60:
        return AP_TOKEN_CACHE["token"]
    app_key = _ap_env("DBX_APP_KEY")
    app_secret = _ap_env("DBX_APP_SECRET")
    refresh = _ap_env("DBX_REFRESH_TOKEN")
    if not all([app_key, app_secret, refresh]):
        raise ValueError("Dropbox env vars not set (DBX_APP_KEY, DBX_APP_SECRET, DBX_REFRESH_TOKEN)")
    r = _rq.post("https://api.dropbox.com/oauth2/token", data={
        "grant_type": "refresh_token", "refresh_token": refresh,
        "client_id": app_key, "client_secret": app_secret,
    }, timeout=15)
    r.raise_for_status()
    data = r.json()
    AP_TOKEN_CACHE["token"] = data["access_token"]
    AP_TOKEN_CACHE["expires"] = now + data.get("expires_in", 14400)
    return AP_TOKEN_CACHE["token"]

def _ap_dbx(method, endpoint, json_body=None, content=False):
    """Helper for Dropbox API calls."""
    token = _ap_get_access_token()
    base = "https://content.dropboxapi.com" if content else "https://api.dropboxapi.com"
    hdrs = {"Authorization": f"Bearer {token}"}
    if not content:
        hdrs["Content-Type"] = "application/json"
    return _rq.post(f"{base}{endpoint}", headers=hdrs, json=json_body if not content else None, timeout=30)

def _ap_ensure_folder(path):
    try:
        _ap_dbx("POST", "/2/files/create_folder_v2", {"path": path, "autorename": False})
    except: pass

def ap_brand_cfg(brand_name):
    """Get AutoPost config for a brand from its settings.json."""
    bd = BRANDS_DIR / brand_name
    s = load_json(bd / "settings.json", {})
    root = f"/AutoPost/{brand_name}"
    # Caption prompt: use brand persona or default
    persona = s.get("brand_persona", "")
    default_prompt = f"You are the voice of {s.get('brand_name', brand_name)}. {persona} Write an engaging social media caption for this image. Be concise, use 1-2 relevant emojis. Under 200 characters."
    if not persona:
        default_prompt = "Write an engaging social media caption for this image. Be concise, use 1-2 relevant emojis. Under 200 characters."
    return {
        "enabled": s.get("ap_enabled", False),
        "incoming": s.get("ap_watch_folder", f"{root}/Incoming"),
        "posted": s.get("ap_posted_folder", f"{root}/Posted"),
        "failed": s.get("ap_failed_folder", f"{root}/Failed"),
        "caption_prompt": s.get("ap_caption_prompt", default_prompt),
        "brand_name": s.get("brand_name", brand_name),
        "brand_id": brand_name,
    }

def ap_get_enabled_brands():
    """List all brands with ap_enabled=True."""
    brands = []
    for d in sorted(BRANDS_DIR.iterdir()):
        if d.is_dir():
            cfg = ap_brand_cfg(d.name)
            if cfg["enabled"]:
                brands.append(cfg)
    return brands

def ap_init_brand(brand_name):
    """Create Dropbox folders for a brand and init cursor."""
    cfg = ap_brand_cfg(brand_name)
    try:
        token = _ap_get_access_token()
        for folder in [cfg["incoming"], cfg["posted"], cfg["failed"]]:
            _ap_ensure_folder(folder)
        # Init cursor
        r = _ap_dbx("POST", "/2/files/list_folder", {"path": cfg["incoming"], "recursive": False})
        if r.status_code == 200:
            AP_CURSORS[brand_name] = r.json().get("cursor")
            ap_log.info(f"AutoPost: {brand_name} cursor ready — {cfg['incoming']}")
    except Exception as e:
        ap_log.warning(f"AutoPost init {brand_name}: {e}")

def ap_list_folder(folder_path):
    """List image files in a Dropbox folder. Returns [{name, path, modified, size}]."""
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
    try:
        r = _ap_dbx("POST", "/2/files/list_folder", {"path": folder_path, "recursive": False})
        if r.status_code != 200:
            return []
        files = []
        data = r.json()
        for entry in data.get("entries", []):
            if entry.get(".tag") == "file":
                ext = os.path.splitext(entry["name"])[1].lower()
                if ext in IMAGE_EXTS:
                    files.append({
                        "name": entry["name"],
                        "path": entry["path_lower"],
                        "modified": entry.get("client_modified", ""),
                        "size": entry.get("size", 0),
                    })
        # Handle pagination
        while data.get("has_more"):
            r = _ap_dbx("POST", "/2/files/list_folder/continue", {"cursor": data["cursor"]})
            if r.status_code != 200: break
            data = r.json()
            for entry in data.get("entries", []):
                if entry.get(".tag") == "file":
                    ext = os.path.splitext(entry["name"])[1].lower()
                    if ext in IMAGE_EXTS:
                        files.append({"name": entry["name"], "path": entry["path_lower"],
                                      "modified": entry.get("client_modified", ""), "size": entry.get("size", 0)})
        return files
    except Exception as e:
        ap_log.warning(f"List folder {folder_path}: {e}")
        return []

def ap_get_thumbnail_url(path):
    """Get a temporary thumbnail link from Dropbox."""
    try:
        r = _rq.post("https://api.dropboxapi.com/2/files/get_temporary_link",
            headers={"Authorization": f"Bearer {_ap_get_access_token()}", "Content-Type": "application/json"},
            json={"path": path}, timeout=10)
        if r.status_code == 200:
            return r.json().get("link", "")
    except: pass
    return ""

def ap_poll_brand(brand_name):
    """Poll one brand's incoming folder for new files."""
    cfg = ap_brand_cfg(brand_name)
    if not cfg["enabled"]: return 0
    token = _ap_get_access_token()
    hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    cursor = AP_CURSORS.get(brand_name)
    if cursor:
        r = _rq.post("https://api.dropboxapi.com/2/files/list_folder/continue", headers=hdrs, json={"cursor": cursor}, timeout=15)
    else:
        r = _rq.post("https://api.dropboxapi.com/2/files/list_folder", headers=hdrs, json={"path": cfg["incoming"], "recursive": False}, timeout=15)
    if r.status_code != 200: return 0
    data = r.json()
    AP_CURSORS[brand_name] = data.get("cursor", cursor)
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
    new_files = []
    for entry in data.get("entries", []):
        if entry.get(".tag") == "file":
            if os.path.splitext(entry["name"])[1].lower() in IMAGE_EXTS:
                new_files.append({"path": entry["path_lower"], "name": entry["name"]})
    for f in new_files:
        jid = f"ap_{int(time.time()*1000)}_{brand_name}_{f['name']}"
        AP_JOBS[jid] = {"id": jid, "status": "queued", "brand": brand_name, "filename": f["name"],
                        "path": f["path"], "started": datetime.now().isoformat(), "error": None}
        threading.Thread(target=_ap_process_wrapper, args=(jid, brand_name, f["path"], f["name"]), daemon=True).start()
    return len(new_files)

def _ap_process_wrapper(jid, brand_name, path, name):
    for attempt in range(3):
        try:
            AP_JOBS[jid]["status"] = "processing"
            _ap_process_file(jid, brand_name, path, name)
            return
        except Exception as e:
            AP_JOBS[jid]["error"] = str(e)
            if attempt < 2:
                AP_JOBS[jid]["status"] = f"retry {attempt+2}/3"
                time.sleep(5 * (2 ** attempt))
            else:
                AP_JOBS[jid]["status"] = "failed"
                cfg = ap_brand_cfg(brand_name)
                try: _ap_move_file(path, cfg["failed"], name)
                except: pass
                _ap_save_run(jid, brand_name, "failed", str(e))

def _ap_process_file(jid, brand_name, path, name):
    cfg = ap_brand_cfg(brand_name)
    token = _ap_get_access_token()
    # Download image
    r = _rq.post("https://content.dropboxapi.com/2/files/download",
        headers={"Authorization": f"Bearer {token}", "Dropbox-API-Arg": json.dumps({"path": path})}, timeout=60)
    r.raise_for_status()
    img_bytes = r.content
    # Sidecar caption
    caption = None
    txt_path = os.path.splitext(path)[0] + ".txt"
    try:
        tr = _rq.post("https://content.dropboxapi.com/2/files/download",
            headers={"Authorization": f"Bearer {token}", "Dropbox-API-Arg": json.dumps({"path": txt_path})}, timeout=10)
        if tr.status_code == 200: caption = tr.text.strip()
    except: pass
    # OpenAI Vision fallback with brand persona
    openai_key = _ap_env("OPENAI_API_KEY")
    if not caption and openai_key:
        try:
            img_b64 = base64.b64encode(img_bytes).decode()
            mt = "image/png" if name.lower().endswith(".png") else "image/jpeg"
            vr = _rq.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini", "max_tokens": 300,
                      "messages": [{"role": "user", "content": [
                          {"type": "text", "text": cfg["caption_prompt"]},
                          {"type": "image_url", "image_url": {"url": f"data:{mt};base64,{img_b64}"}}
                      ]}]}, timeout=30)
            vr.raise_for_status()
            caption = vr.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            ap_log.warning(f"Vision caption failed for {brand_name}: {e}")
    if not caption:
        caption = name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
    AP_JOBS[jid]["caption"] = caption[:200]
    # Upload to Blotato
    blotato_key = _ap_env("BLOTATO_API_KEY")
    img_b64_str = base64.b64encode(img_bytes).decode()
    ext = os.path.splitext(name)[1].lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
    mr = _rq.post("https://backend.blotato.com/v2/media",
        headers={"Authorization": f"Bearer {blotato_key}", "Content-Type": "application/json"},
        json={"base64": f"data:{mime};base64,{img_b64_str}"}, timeout=30)
    mr.raise_for_status()
    media_url = mr.json().get("url", "")
    # Post to platforms using pipeline's Blotato accounts + brand's platform toggles
    bd = BRANDS_DIR / brand_name
    brand_settings = load_json(bd / "settings.json", {})
    # Account IDs from env vars (same as pipeline)
    acct_map = {
        "tiktok":    {"id": _ap_env("BLOTATO_TIKTOK_ID"), "platform": "tiktok"},
        "youtube":   {"id": _ap_env("BLOTATO_YOUTUBE_ID"), "platform": "youtube"},
        "instagram": {"id": _ap_env("BLOTATO_INSTAGRAM_ID", "31177"), "platform": "instagram"},
        "facebook":  {"id": _ap_env("BLOTATO_FACEBOOK_ID"), "platform": "facebook", "pageId": _ap_env("BLOTATO_FACEBOOK_PAGE_ID")},
        "twitter":   {"id": _ap_env("BLOTATO_TWITTER_ID"), "platform": "twitter"},
        "threads":   {"id": _ap_env("BLOTATO_THREADS_ID"), "platform": "threads"},
        "pinterest": {"id": _ap_env("BLOTATO_PINTEREST_ID"), "platform": "pinterest"},
    }
    # Platform toggles from brand settings (on_ig, on_tt, etc.)
    toggle_map = {"tiktok": "on_tt", "youtube": "on_yt", "instagram": "on_ig",
                  "facebook": "on_fb", "twitter": "on_tw", "threads": "on_th", "pinterest": "on_pn"}
    posted = []
    for platform, toggle_key in toggle_map.items():
        enabled = brand_settings.get(toggle_key, False)
        if enabled in (True, "true", "True") and acct_map[platform]["id"]:
            acct = acct_map[platform]
            payload = {"post": {"accountId": str(acct["id"]), "content": {"text": caption, "mediaUrls": [media_url], "platform": platform}, "target": {"targetType": platform}}}
            if acct.get("pageId"): payload["post"]["target"]["pageId"] = acct["pageId"]
            try:
                pr = _rq.post("https://backend.blotato.com/v2/posts",
                    headers={"Authorization": f"Bearer {blotato_key}", "Content-Type": "application/json"}, json=payload, timeout=20)
                posted.append({"platform": platform, "ok": pr.ok, "status": pr.status_code})
            except Exception as e:
                posted.append({"platform": platform, "ok": False, "error": str(e)})
    AP_JOBS[jid]["posted"] = posted
    AP_JOBS[jid]["media_url"] = media_url
    # Move to Posted
    _ap_move_file(path, cfg["posted"], name)
    try: _ap_move_file(txt_path, cfg["posted"], os.path.splitext(name)[0] + ".txt")
    except: pass
    AP_JOBS[jid]["status"] = "posted"
    _ap_save_run(jid, brand_name, "posted", None)

def _ap_move_file(from_path, to_folder, name):
    token = _ap_get_access_token()
    _ap_ensure_folder(to_folder)
    _rq.post("https://api.dropboxapi.com/2/files/move_v2",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"from_path": from_path, "to_path": f"{to_folder}/{name}", "autorename": True}, timeout=15)

def _ap_save_run(jid, brand_name, status, error):
    job = AP_JOBS.get(jid, {})
    entry = {"id": jid, "brand": brand_name, "date": datetime.now().strftime("%b %d, %I:%M %p"),
             "filename": job.get("filename", "?"), "status": status,
             "caption": job.get("caption", "")[:100], "error": error,
             "platforms": [p.get("platform") for p in job.get("posted", []) if p.get("ok")]}
    AP_RUNS.insert(0, entry)
    AP_RUNS[:] = AP_RUNS[:200]
    try: save_json(AP_RUNS_FILE, AP_RUNS)
    except: pass

def _ap_bg_poller():
    time.sleep(20)
    while True:
        try:
            if _ap_env("DBX_APP_KEY"):
                for bcfg in ap_get_enabled_brands():
                    bn = bcfg["brand_id"]
                    if bn not in AP_CURSORS:
                        ap_init_brand(bn)
                    n = ap_poll_brand(bn)
                    if n: ap_log.info(f"AutoPost {bn}: {n} new files")
        except Exception as e:
            ap_log.warning(f"AutoPost poll error: {e}")
        time.sleep(300)

threading.Thread(target=_ap_bg_poller, daemon=True).start()
# Init all enabled brands on boot
try:
    if _ap_env("DBX_APP_KEY"):
        for _bcfg in ap_get_enabled_brands():
            ap_init_brand(_bcfg["brand_id"])
except: pass

# ─── AUTOPOST API ─────────────────────────────────────────────
@app.get("/ap/webhook/dropbox")
async def ap_webhook_verify(req: Request):
    challenge = req.query_params.get("challenge", "")
    return HTMLResponse(content=challenge, headers={"Content-Type": "text/plain", "X-Content-Type-Options": "nosniff"})

@app.post("/ap/webhook/dropbox")
async def ap_webhook_notify(req: Request, bg: BackgroundTasks):
    body = await req.body()
    sig = req.headers.get("X-Dropbox-Signature", "")
    secret = _ap_env("DBX_APP_SECRET")
    if secret:
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return JSONResponse({"error": "Invalid signature"}, 403)
    for bcfg in ap_get_enabled_brands():
        bg.add_task(ap_poll_brand, bcfg["brand_id"])
    return {"ok": True}

@app.post("/ap/trigger")
async def ap_manual_trigger(bg: BackgroundTasks):
    brand = get_active_brand()
    bg.add_task(ap_poll_brand, brand)
    return {"ok": True, "brand": brand}

@app.post("/ap/enable")
async def ap_enable_brand(req: Request):
    """Toggle ap_enabled for active brand and create Dropbox folders."""
    body = await req.json()
    brand = get_active_brand()
    bd = brand_dir(brand)
    s = load_json(bd / "settings.json", {})
    enabled = body.get("enabled", True)
    s["ap_enabled"] = enabled
    save_json(bd / "settings.json", s)
    if enabled:
        try: ap_init_brand(brand)
        except Exception as e:
            return {"status": "enabled_no_dbx", "error": str(e), "brand": brand}
    return {"status": "enabled" if enabled else "disabled", "brand": brand}

@app.get("/ap/status")
async def ap_status():
    brand = get_active_brand()
    cfg = ap_brand_cfg(brand)
    brand_runs = [r for r in AP_RUNS if r.get("brand") == brand]
    total = len(brand_runs)
    posted = sum(1 for r in brand_runs if r.get("status") == "posted")
    failed = sum(1 for r in brand_runs if r.get("status") == "failed")
    active = [j for j in AP_JOBS.values() if j.get("brand") == brand and j.get("status") not in ("posted", "failed")]
    return {"brand": brand, "enabled": cfg["enabled"], "total": total, "posted": posted, "failed": failed,
            "active_count": len(active), "jobs": [j for j in AP_JOBS.values() if j.get("brand") == brand][-20:],
            "runs": brand_runs[:30], "cursor_ok": brand in AP_CURSORS,
            "folders": {"incoming": cfg["incoming"], "posted": cfg["posted"], "failed": cfg["failed"]}}

@app.get("/ap/board")
async def ap_board():
    """Kanban board data — list files in Incoming/Posted/Failed for active brand."""
    brand = get_active_brand()
    cfg = ap_brand_cfg(brand)
    if not cfg["enabled"]:
        return {"brand": brand, "enabled": False, "incoming": [], "posted": [], "failed": []}
    try:
        incoming = ap_list_folder(cfg["incoming"])
        posted_files = ap_list_folder(cfg["posted"])
        failed_files = ap_list_folder(cfg["failed"])
        # Get thumbnail links for incoming (most useful for preview)
        for f in incoming[:12]:  # limit to avoid rate limits
            f["thumb"] = ap_get_thumbnail_url(f["path"])
        for f in posted_files[:12]:
            f["thumb"] = ap_get_thumbnail_url(f["path"])
        for f in failed_files[:6]:
            f["thumb"] = ap_get_thumbnail_url(f["path"])
        return {"brand": brand, "enabled": True,
                "incoming": incoming[:20], "posted": posted_files[:20], "failed": failed_files[:10]}
    except Exception as e:
        return {"brand": brand, "enabled": True, "error": str(e), "incoming": [], "posted": [], "failed": []}

@app.post("/ap/post-now")
async def ap_post_now(req: Request, bg: BackgroundTasks):
    """Manually post a specific file from Incoming."""
    body = await req.json()
    path = body.get("path", "")
    name = body.get("name", "")
    brand = get_active_brand()
    if not path or not name:
        return JSONResponse({"error": "path and name required"}, 400)
    jid = f"ap_{int(time.time()*1000)}_{brand}_{name}"
    AP_JOBS[jid] = {"id": jid, "status": "queued", "brand": brand, "filename": name,
                    "path": path, "started": datetime.now().isoformat(), "error": None}
    bg.add_task(_ap_process_wrapper, jid, brand, path, name)
    return {"ok": True, "job_id": jid}

@app.post("/ap/retry")
async def ap_retry_file(req: Request, bg: BackgroundTasks):
    """Move a file from Failed back to Incoming and process it."""
    body = await req.json()
    path = body.get("path", "")
    name = body.get("name", "")
    brand = get_active_brand()
    cfg = ap_brand_cfg(brand)
    if not path or not name:
        return JSONResponse({"error": "path and name required"}, 400)
    # Move from Failed to Incoming
    try:
        _ap_move_file(path, cfg["incoming"], name)
    except: pass
    new_path = f"{cfg['incoming']}/{name}"
    jid = f"ap_{int(time.time()*1000)}_{brand}_{name}"
    AP_JOBS[jid] = {"id": jid, "status": "queued", "brand": brand, "filename": name,
                    "path": new_path, "started": datetime.now().isoformat(), "error": None}
    bg.add_task(_ap_process_wrapper, jid, brand, new_path, name)
    return {"ok": True, "job_id": jid}

@app.get("/ap/credentials")
async def ap_get_creds():
    return {"DBX_APP_KEY": bool(_ap_env("DBX_APP_KEY")), "DBX_APP_SECRET": bool(_ap_env("DBX_APP_SECRET")),
            "DBX_REFRESH_TOKEN": bool(_ap_env("DBX_REFRESH_TOKEN")),
            "OPENAI_API_KEY": bool(_ap_env("OPENAI_API_KEY")), "BLOTATO_API_KEY": bool(_ap_env("BLOTATO_API_KEY"))}

@app.get("/ap/runs")
async def ap_get_runs():
    brand = get_active_brand()
    return [r for r in AP_RUNS if r.get("brand") == brand][:50]

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
