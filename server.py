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

app = FastAPI(title="Knights Reactor")

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

apply_credentials()

# ─── STATE ────────────────────────────────────────────────────
RUNS = load_json(RUNS_FILE, []) if RUNS_FILE.exists() else []
CURRENT_RUN = {"active": False, "result": None, "phase": 0, "phase_name": "", "phases_done": []}
LOGS = []

def log_entry(phase, level, msg):
    LOGS.append({"t": datetime.now().strftime("%H:%M:%S"), "phase": phase, "level": level, "msg": msg})
    if len(LOGS) > 500: LOGS.pop(0)

def execute_pipeline():
    CURRENT_RUN.update({"active": True, "started": datetime.now().isoformat(), "result": None, "phase": 0, "phases_done": []})
    LOGS.clear()
    log_entry("System", "info", "Pipeline started")
    result = run_pipeline()
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
    bg.add_task(execute_pipeline)
    return {"status": "started"}

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
    creds = load_json(CREDS_FILE, {})
    masked = {}
    for k, v in creds.items():
        if v and len(v) > 8: masked[k] = v[:3] + "..." + v[-3:]
        elif v: masked[k] = "***"
        else: masked[k] = ""
    return masked

@app.post("/api/credentials")
async def save_credentials(req: Request):
    body = await req.json()
    existing = load_json(CREDS_FILE, {})
    for k, v in body.items():
        if v is not None: existing[k] = v
    save_json(CREDS_FILE, existing)
    apply_credentials()
    return {"status": "saved"}

@app.get("/api/settings")
async def get_settings(): return load_json(SETTINGS_FILE, {})

@app.post("/api/settings")
async def save_settings(req: Request):
    save_json(SETTINGS_FILE, await req.json())
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
<title>Knights Reactor</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600;700&family=Outfit:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#08080f;--sf:#0f0f18;--ra:#161620;--bd:#1e1e2e;--gold:#c9a84c;--gd:#8a7234;--gg:rgba(201,168,76,.07);--red:#c55;--rd:rgba(204,85,85,.1);--grn:#3b9;--gd2:rgba(51,187,153,.1);--blu:#58b;--bd2:rgba(85,136,187,.1);--org:#c93;--od:rgba(204,153,51,.1);--tx:#ddd8cc;--dm:#777266;--mt:#444038;--ft:#2a2720;--fd:'Cormorant Garamond',Georgia,serif;--fb:'Outfit',system-ui,sans-serif;--fm:'IBM Plex Mono',monospace}
*{margin:0;padding:0;box-sizing:border-box}body{background:var(--bg);color:var(--tx);font-family:var(--fb);min-height:100vh}button{font-family:var(--fb);cursor:pointer}input,select{font-family:var(--fm)}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:var(--bd);border-radius:2px}
@keyframes fi{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}@keyframes pu{0%,100%{opacity:1}50%{opacity:.3}}
.hd{display:none}.card{background:var(--sf);border:1px solid var(--bd);border-radius:10px}.rw{padding:11px 14px;border-bottom:1px solid var(--bd)}
.bg{font-family:var(--fm);font-size:9px;padding:2px 8px;border-radius:9px;display:inline-flex;align-items:center;gap:4px}.bd2{width:5px;height:5px;border-radius:50%}
.bg-g{color:var(--grn);background:var(--gd2)}.bg-g .bd2{background:var(--grn)}.bg-r{color:var(--red);background:var(--rd)}.bg-r .bd2{background:var(--red)}
.bg-b{color:var(--blu);background:var(--bd2)}.bg-b .bd2{background:var(--blu);animation:pu 1.2s infinite}.bg-o{color:var(--org);background:var(--od)}.bg-o .bd2{background:var(--org)}
.bg-m{color:var(--mt);background:rgba(68,64,56,.12)}.bg-m .bd2{background:var(--mt)}
.sec{background:var(--sf);border:1px solid var(--bd);border-radius:10px;margin-bottom:8px;overflow:hidden}
.sec-h{width:100%;display:flex;align-items:center;justify-content:space-between;padding:13px 16px;background:none;border:none}
.sec-t{font-family:var(--fd);font-size:15px;font-weight:600;color:var(--tx)}.sec-a{font-family:var(--fm);font-size:14px;color:var(--mt);transition:transform .15s}
.sec-b{padding:0 16px 14px}.fi{padding:10px 0;border-bottom:1px solid var(--bd)}
.fl{font-family:var(--fm);font-size:9px;color:var(--mt);text-transform:uppercase;letter-spacing:1px;margin-bottom:5px}
.fin{width:100%;padding:9px 10px;background:var(--ra);border:1px solid var(--bd);border-radius:6px;font-size:11px;color:var(--tx);outline:none;box-sizing:border-box}
.fin.ok{border-color:rgba(51,187,153,.27)}.fh{font-family:var(--fm);font-size:8px;color:var(--ft);margin-top:3px}
.fr{display:flex;gap:6px}.eb{width:36px;background:var(--ra);border:1px solid var(--bd);border-radius:6px;font-size:12px;color:var(--dm);display:flex;align-items:center;justify-content:center}
.lb{font-family:var(--fm);font-size:10px;color:var(--blu);background:var(--bd2);padding:6px 10px;border-radius:6px;cursor:pointer;margin-bottom:8px;display:block;text-decoration:none;border:none;text-align:left;width:100%}
.ds{font-family:var(--fm);font-size:10px;color:var(--dm);margin-bottom:8px;line-height:1.5}
.tg{width:40px;height:22px;border-radius:11px;border:none;position:relative;transition:background .2s}
.tg.on{background:var(--grn)}.tg.off{background:var(--ft)}.td{position:absolute;top:2px;width:18px;height:18px;border-radius:9px;background:#fff;transition:left .2s;box-shadow:0 1px 3px rgba(0,0,0,.3)}
.sv{width:100%;padding:12px;border:none;border-radius:8px;font-size:13px;font-weight:600;color:#04040a;background:linear-gradient(135deg,var(--gold),var(--gd));margin-top:10px}
.sm{background:var(--gd2);border:1px solid rgba(51,187,153,.2);border-radius:8px;padding:8px 12px;margin-bottom:10px;font-family:var(--fm);font-size:10px;color:var(--grn)}
.ph{background:var(--sf);border:1px solid var(--bd);border-radius:9px;padding:11px 14px;margin-bottom:6px;border-left:3px solid var(--bd);transition:opacity .3s}
.ph.dn{border-left-color:var(--grn)}.ph.rn{border-left-color:var(--blu)}.ph.dm{opacity:.4}
</style></head><body>

<!-- LOGIN -->
<div id="L" style="min-height:100vh;display:flex;align-items:center;justify-content:center">
<div style="width:340px;background:var(--sf);border:1px solid var(--bd);border-radius:14px;padding:36px 28px;text-align:center">
<div style="width:50px;height:50px;border-radius:12px;margin:0 auto 16px;background:linear-gradient(135deg,var(--gold),var(--gd));display:flex;align-items:center;justify-content:center;font-size:22px">⚔️</div>
<div style="font-family:var(--fd);font-size:24px;font-weight:700;color:var(--gold);margin-bottom:4px">Knights Reactor</div>
<div style="font-family:var(--fm);font-size:9px;color:var(--mt);letter-spacing:2px;margin-bottom:28px">ADMIN DASHBOARD</div>
<input type="password" id="pw" style="width:100%;padding:11px 14px;background:var(--ra);border:1px solid var(--bd);border-radius:8px;font-size:13px;color:var(--tx);outline:none;margin-bottom:12px;text-align:center" placeholder="Enter password" onkeydown="event.key==='Enter'&&go()">
<div id="le" class="hd" style="font-family:var(--fm);font-size:10px;color:var(--red);margin-bottom:8px">Invalid password</div>
<button onclick="go()" style="width:100%;padding:11px;border:none;border-radius:8px;font-size:13px;font-weight:600;color:#04040a;background:linear-gradient(135deg,var(--gold),var(--gd))">Enter</button>
</div></div>

<!-- APP -->
<div id="A" class="hd">
<div style="padding:16px 20px 12px;border-bottom:1px solid var(--bd);display:flex;align-items:center;justify-content:space-between;background:var(--sf)">
<div style="display:flex;align-items:center;gap:10px"><div style="width:30px;height:30px;border-radius:8px;background:linear-gradient(135deg,var(--gold),var(--gd));display:flex;align-items:center;justify-content:center;font-size:14px">⚔️</div><div><div style="font-family:var(--fd);font-size:17px;font-weight:700;color:var(--gold);line-height:1">Knights Reactor</div><div style="font-family:var(--fm);font-size:8px;color:var(--mt);letter-spacing:2px;margin-top:2px">V5 · ADMIN</div></div></div>
<div style="display:flex;align-items:center;gap:10px"><span id="pi" class="hd" style="font-family:var(--fm);font-size:10px;color:var(--blu)"></span>
<button id="rb" onclick="runNow()" style="font-size:11px;font-weight:600;color:#04040a;background:linear-gradient(135deg,var(--gold),var(--gd));border:none;border-radius:7px;padding:8px 14px">▶ Run Now</button></div></div>

<div style="display:flex;border-bottom:1px solid var(--bd);background:var(--sf);overflow-x:auto">
<button class="tb ac" onclick="sw('pipeline',this)">⚡Pipeline</button>
<button class="tb" onclick="sw('runs',this)">📊Runs</button>
<button class="tb" onclick="sw('logs',this)">📄Logs</button>
<button class="tb" onclick="sw('settings',this)">⚙️Settings</button>
<button class="tb" onclick="sw('credentials',this)" style="position:relative">🔑Credentials<span id="ca" style="width:6px;height:6px;border-radius:3px;background:var(--org);position:absolute;top:6px;right:2px"></span></button>
<button class="tb" onclick="sw('health',this)">🩺Health</button>
</div>
<style>.tb{font-family:var(--fm);font-size:10px;color:var(--mt);background:none;border:none;border-bottom:2px solid transparent;padding:10px 11px;white-space:nowrap;display:flex;align-items:center;gap:4px}.tb.ac{color:var(--gold);font-weight:600;border-bottom-color:var(--gold)}</style>

<div style="padding:16px 20px;max-width:660px;margin:0 auto">

<!-- PIPELINE -->
<div id="t-pipeline"><div id="pg" class="hd" style="height:3px;background:var(--bd);border-radius:2px;overflow:hidden;margin-bottom:14px"><div id="pb" style="height:100%;background:var(--blu);border-radius:2px;transition:width .6s ease;width:0%"></div></div><div id="pl"></div></div>

<!-- RUNS -->
<div id="t-runs" class="hd"><div id="rs" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px"></div><div id="rl" class="card"></div></div>

<!-- LOGS -->
<div id="t-logs" class="hd"><div style="display:flex;justify-content:space-between;margin-bottom:10px"><span style="font-family:var(--fm);font-size:9px;color:var(--mt);text-transform:uppercase;letter-spacing:1.5px">Live Pipeline Log</span><span id="lc" style="font-family:var(--fm);font-size:9px;color:var(--dm)"></span></div><div id="la" style="background:#04040a;border:1px solid var(--bd);border-radius:10px;padding:12px 14px;max-height:500px;overflow-y:auto;font-family:var(--fm);font-size:10.5px;line-height:1.8"></div></div>

<!-- SETTINGS -->
<div id="t-settings" class="hd"><div id="ss" class="sm hd">✓ Settings saved</div><div id="sf"></div><button class="sv" onclick="saveSett()">Save Settings</button></div>

<!-- CREDENTIALS -->
<div id="t-credentials" class="hd"><div id="cs" class="sm hd">✓ Credentials saved securely</div><div id="cx" class="card" style="padding:12px 14px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center"></div><div id="cf"></div><button class="sv" onclick="saveCreds()">Save All Credentials</button></div>

<!-- HEALTH -->
<div id="t-health" class="hd"><div id="hl" class="card" style="margin-bottom:12px"></div>
<div class="card" style="padding:14px 16px"><div style="font-family:var(--fd);font-size:15px;font-weight:600;margin-bottom:10px">Quick Actions</div>
<button style="width:100%;display:flex;justify-content:space-between;align-items:center;padding:10px 12px;margin-bottom:6px;background:var(--ra);border:1px solid var(--bd);border-radius:7px" onclick="testAll()"><div style="text-align:left"><div style="font-size:12px;font-weight:500">Test All Connections</div><div style="font-family:var(--fm);font-size:9px;color:var(--dm);margin-top:1px">Ping each API to verify keys</div></div><span style="font-family:var(--fm);font-size:12px;color:var(--gold)">→</span></button>
</div>
<button onclick="document.getElementById('L').style.display='flex';document.getElementById('A').style.display='none'" style="width:100%;padding:10px;margin-top:12px;border:1px solid var(--bd);border-radius:7px;background:none;font-family:var(--fm);font-size:11px;color:var(--red)">🔒 Logout</button>
</div>

</div></div>

<script>
let RN=false,PH=0,PD=[],CR={},ST={};
const $=id=>document.getElementById(id);
const B=(s,l)=>{const c={done:'g',running:'b',failed:'r',configured:'g',missing:'r',warning:'o',waiting:'m'}[s]||'m';return`<span class="bg bg-${c}"><span class="bd2"></span>${l||s}</span>`};

const PHS=[{n:"Fetch Topic",a:"Airtable",i:"📋",d:"~2s"},{n:"Generate Script",a:"OpenAI GPT-4o",i:"📝",d:"~3s"},{n:"Scene Engine v6",a:"Local",i:"🎬",d:"<1s"},{n:"Generate Images",a:"Replicate",i:"🖼️",d:"~60s"},{n:"Generate Videos",a:"Seedance-1-Lite",i:"🎥",d:"~120s"},{n:"Voiceover",a:"ElevenLabs",i:"🔊",d:"~4s"},{n:"Transcribe",a:"Whisper",i:"💬",d:"~3s"},{n:"Upload Assets",a:"R2",i:"☁️",d:"~8s"},{n:"Final Render",a:"Shotstack",i:"🎞️",d:"~90s"},{n:"Captions",a:"GPT-4o",i:"✍️",d:"~4s"},{n:"Publish",a:"Blotato",i:"📡",d:"~6s"}];

const CRS=[
{t:"🤖 OpenAI",d:"Powers script generation and transcription",l:"https://platform.openai.com/api-keys",ll:"Get key → platform.openai.com",f:[{k:"OPENAI_API_KEY",l:"API Key",p:"sk-...",s:1}]},
{t:"🎨 Replicate",d:"Image generation + video animation",l:"https://replicate.com/account/api-tokens",ll:"Get token → replicate.com",f:[{k:"REPLICATE_API_TOKEN",l:"API Token",p:"r8_...",s:1}]},
{t:"🔊 ElevenLabs",d:"Knight voiceover narration",l:"https://elevenlabs.io",ll:"Get key → elevenlabs.io",f:[{k:"ELEVENLABS_API_KEY",l:"API Key",p:"xi-...",s:1},{k:"ELEVENLABS_VOICE_ID",l:"Voice ID",p:"bwCXcoVxWNYMlC6Esa8u",s:0}]},
{t:"🎞️ Shotstack",d:"Final video rendering",l:"https://dashboard.shotstack.io",ll:"Get key → dashboard.shotstack.io",f:[{k:"SHOTSTACK_API_KEY",l:"API Key",p:"your-key",s:1}]},
{t:"☁️ Cloudflare R2",d:"Video asset storage",l:"https://dash.cloudflare.com",ll:"Cloudflare → R2 → API Tokens",f:[{k:"R2_ACCESS_KEY",l:"Access Key",p:"key",s:1},{k:"R2_SECRET_KEY",l:"Secret Key",p:"secret",s:1},{k:"R2_ENDPOINT",l:"Endpoint",p:"https://ID.r2.cloudflarestorage.com",s:0},{k:"R2_BUCKET",l:"Bucket",p:"knights-videos",s:0},{k:"R2_PUBLIC_URL",l:"Public URL",p:"https://pub-xxx.r2.dev",s:0}]},
{t:"📋 Airtable",d:"Topic database",l:"https://airtable.com/create/tokens",ll:"Get token → airtable.com",f:[{k:"AIRTABLE_API_KEY",l:"Access Token",p:"pat...",s:1},{k:"AIRTABLE_BASE_ID",l:"Base ID",p:"appNDCADOHinuotY1",s:0},{k:"AIRTABLE_TABLE",l:"Table Name",p:"Scripture Topics",s:0}]},
{t:"📡 Blotato",d:"Social media publishing",l:"https://blotato.com",ll:"Blotato → Settings → API",f:[{k:"BLOTATO_API_KEY",l:"API Key",p:"your-key",s:1}]},
{t:"📱 Social Account IDs",d:"Find in Blotato → Accounts",f:[{k:"BLOTATO_TIKTOK_ID",l:"TikTok",p:"acct_",s:0},{k:"BLOTATO_YOUTUBE_ID",l:"YouTube",p:"acct_",s:0},{k:"BLOTATO_INSTAGRAM_ID",l:"Instagram",p:"31177",s:0},{k:"BLOTATO_FACEBOOK_ID",l:"Facebook",p:"acct_",s:0},{k:"BLOTATO_FACEBOOK_PAGE_ID",l:"FB Page",p:"page_",s:0},{k:"BLOTATO_TWITTER_ID",l:"X/Twitter",p:"acct_",s:0},{k:"BLOTATO_THREADS_ID",l:"Threads",p:"acct_",s:0},{k:"BLOTATO_PINTEREST_ID",l:"Pinterest",p:"acct_",s:0}]}
];

const STS=[
{t:"📝 Script",f:[{k:"script_model",l:"AI Model",tp:"select",o:["gpt-4o","gpt-4o-mini"],d:"gpt-4o"},{k:"script_temp",l:"Temperature",d:"0.85"},{k:"script_max_words",l:"Max Words",d:"50"}]},
{t:"🔊 Voice",f:[{k:"voice_model",l:"Model",tp:"select",o:["eleven_turbo_v2","eleven_multilingual_v2"],d:"eleven_turbo_v2"},{k:"voice_stability",l:"Stability",d:"0.5"},{k:"voice_similarity",l:"Similarity",d:"0.75"}]},
{t:"🖼️ Image & Video",f:[{k:"image_size",l:"Size",tp:"select",o:["1024x1792","1024x1024"],d:"1024x1792"},{k:"image_quality",l:"Quality",tp:"select",o:["high","standard"],d:"high"},{k:"video_timeout",l:"Timeout (sec)",d:"600"}]},
{t:"🎞️ Render",f:[{k:"render_fps",l:"FPS",tp:"select",o:["24","30","60"],d:"30"},{k:"render_res",l:"Resolution",tp:"select",o:["720","1080"],d:"1080"},{k:"render_aspect",l:"Aspect",tp:"select",o:["9:16","16:9","1:1"],d:"9:16"}]},
{t:"⏰ Schedule",f:[{k:"sched_int",l:"Every (hours)",tp:"select",o:["4","6","8","12","24"],d:"8"},{k:"post_tt",l:"TikTok Time",d:"3:00 PM"},{k:"post_yt",l:"YouTube Time",d:"1:30 PM"},{k:"post_ig",l:"Instagram Time",d:"12:00 PM"},{k:"post_fb",l:"Facebook Time",d:"2:00 PM"}]},
{t:"📡 Platforms",f:[{k:"on_tt",l:"TikTok",tp:"toggle",d:true},{k:"on_yt",l:"YouTube",tp:"toggle",d:true},{k:"on_ig",l:"Instagram",tp:"toggle",d:true},{k:"on_fb",l:"Facebook",tp:"toggle",d:true},{k:"on_tw",l:"X/Twitter",tp:"toggle",d:true},{k:"on_th",l:"Threads",tp:"toggle",d:true},{k:"on_pn",l:"Pinterest",tp:"toggle",d:false}]}
];

function go(){if($('pw').value.length>0){$('L').style.display='none';$('A').style.display='block';init();}else $('le').style.display='block'}
function sw(id,btn){document.querySelectorAll('[id^="t-"]').forEach(e=>e.style.display='none');$('t-'+id).style.display='block';document.querySelectorAll('.tb').forEach(t=>t.classList.remove('ac'));btn.classList.add('ac');if(id==='runs')loadRuns();if(id==='logs')loadLogs();if(id==='health')rH();}

function rP(){
  let h='';PHS.forEach((p,i)=>{let s='waiting',c='';if(PD.includes(i)){s='done';c='dn';}else if(RN&&i===PH){s='running';c='rn';}else if(RN){c='dm';}
    h+=`<div class="ph ${c}"><div style="display:flex;align-items:center;gap:10px"><span style="font-size:14px;width:20px;text-align:center">${p.i}</span><div style="flex:1"><div style="font-family:var(--fb);font-size:12.5px;font-weight:500">${p.n}</div><div style="font-family:var(--fm);font-size:9px;color:var(--dm);margin-top:1px">${p.a} · ${p.d}</div></div>${B(s)}</div></div>`;
  });$('pl').innerHTML=h;
  if(RN){$('pg').style.display='block';$('pb').style.width=(PD.length/PHS.length*100)+'%';$('pi').textContent='Phase '+(PH+1)+'/11';$('pi').style.display='inline';$('rb').textContent='⏳ Running...';$('rb').style.background='var(--ra)';$('rb').style.color='var(--dm)';$('rb').style.border='1px solid var(--bd)';}
  else{$('pg').style.display='none';$('pi').style.display='none';$('rb').textContent='▶ Run Now';$('rb').style.background='linear-gradient(135deg,var(--gold),var(--gd))';$('rb').style.color='#04040a';$('rb').style.border='none';}
}

async function runNow(){if(RN)return;await fetch('/api/run',{method:'POST'});RN=true;PH=0;PD=[];rP();poll();}
async function poll(){if(!RN)return;try{const r=await(await fetch('/api/status')).json();RN=r.running;PH=r.phase;PD=r.phases_done||[];rP();if(r.running)setTimeout(poll,2000);}catch(e){setTimeout(poll,3000);}}

async function loadRuns(){try{const runs=await(await fetch('/api/runs')).json();const t=runs.length,ok=runs.filter(r=>r.status==='published'||r.status==='complete').length;
$('rs').innerHTML=[{l:'Total',v:t,c:'gold'},{l:'Success',v:ok,c:'grn'},{l:'Rate',v:t?Math.round(ok/t*100)+'%':'0%',c:'blu'},{l:'Failed',v:t-ok,c:'red'}].map(s=>`<div style="background:var(--sf);border:1px solid var(--bd);border-radius:9px;padding:12px 10px;text-align:center"><div style="font-family:var(--fd);font-size:20px;font-weight:700">${s.v}</div><div style="font-family:var(--fm);font-size:8px;color:var(--${s.c});margin-top:2px">${s.l}</div></div>`).join('');
$('rl').innerHTML=runs.length?runs.map(r=>`<div class="rw"><div style="display:flex;align-items:center;gap:10px"><div style="flex:1"><div style="font-size:12.5px;font-weight:500">${r.topic||'?'}</div><div style="font-family:var(--fm);font-size:9px;color:var(--mt);margin-top:2px">${r.date} · ${r.category||''} · ${r.duration||''}</div></div>${B(r.status==='published'||r.status==='complete'?'done':'failed',r.status)}</div>${r.error?`<div style="font-family:var(--fm);font-size:10px;color:var(--red);margin-top:6px;background:var(--rd);padding:4px 8px;border-radius:4px">${r.error}</div>`:''}</div>`).join(''):'<div class="rw" style="color:var(--dm)">No runs yet</div>';}catch(e){}}

async function loadLogs(){try{const logs=await(await fetch('/api/logs')).json();$('lc').textContent=logs.length+' entries';
$('la').innerHTML=logs.length?logs.map(l=>`<div><span style="color:var(--mt)">${l.t}</span> <span style="color:var(--gold);background:var(--gg);padding:0 4px;border-radius:3px;font-size:9px">${l.phase}</span> <span style="color:var(--${l.level==='ok'?'grn':l.level==='error'?'red':'dm'})">${l.msg}</span></div>`).join(''):'<div style="color:var(--dm)">No logs yet. Run the pipeline to see output.</div>';
$('la').scrollTop=$('la').scrollHeight;}catch(e){}}

function rSt(){let h='';STS.forEach(sec=>{let ff='';sec.f.forEach(f=>{const v=ST[f.k]!==undefined?ST[f.k]:f.d;
if(f.tp==='toggle'){const on=v===true||v==='true';ff+=`<div class="fi" style="display:flex;align-items:center;justify-content:space-between"><div style="font-size:12px">${f.l}</div><button class="tg ${on?'on':'off'}" onclick="ST['${f.k}']=!ST['${f.k}'];rSt()"><span class="td" style="left:${on?'20px':'2px'}"></span></button></div>`;}
else if(f.tp==='select'){ff+=`<div class="fi"><div class="fl">${f.l}</div><select class="fin" onchange="ST['${f.k}']=this.value">${f.o.map(o=>`<option${o==v?' selected':''}>${o}</option>`).join('')}</select></div>`;}
else{ff+=`<div class="fi"><div class="fl">${f.l}</div><input class="fin" value="${v||''}" onchange="ST['${f.k}']=this.value"></div>`;}
});h+=`<div class="sec"><button class="sec-h" onclick="this.nextElementSibling.classList.toggle('hd');this.querySelector('.sec-a').style.transform=this.nextElementSibling.classList.contains('hd')?'':'rotate(90deg)'"><span class="sec-t">${sec.t}</span><span class="sec-a">›</span></button><div class="sec-b hd">${ff}</div></div>`;});
$('sf').innerHTML=h;}

async function saveSett(){await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(ST)});$('ss').style.display='block';setTimeout(()=>$('ss').style.display='none',3000);}

function rC(){
  const ak=CRS.flatMap(s=>s.f.map(f=>f.k)),fl=ak.filter(k=>CR[k]&&CR[k].length>0).length;
  $('cx').innerHTML=`<div><div style="font-family:var(--fm);font-size:9px;color:var(--mt);text-transform:uppercase;letter-spacing:1px">Credentials</div><div style="font-family:var(--fm);font-size:12px;color:var(--${fl>=8?'grn':'org'});margin-top:3px;font-weight:500">${fl} of ${ak.length} configured</div></div>${B(fl>=8?'configured':fl>=4?'warning':'missing',fl>=8?'ready':'needs keys')}`;
  $('ca').style.display=fl<8?'block':'none';
  let h='';CRS.forEach((sec,si)=>{
    const af=sec.f.every(f=>CR[f.k]&&CR[f.k].length>0),pf=sec.f.some(f=>CR[f.k]&&CR[f.k].length>0);
    let ff='';if(sec.d)ff+=`<div class="ds">${sec.d}</div>`;if(sec.l)ff+=`<a class="lb" href="${sec.l}" target="_blank">↗ ${sec.ll}</a>`;
    sec.f.forEach(f=>{const v=CR[f.k]||'';const ok=v.length>0;
      ff+=`<div class="fi"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px"><span class="fl">${f.l}</span>${B(ok?'configured':'missing',ok?'set':'empty')}</div><div class="fr"><input type="${f.s?'password':'text'}" class="fin${ok?' ok':''}" value="${v}" placeholder="${f.p||''}" id="c_${f.k}" onchange="CR['${f.k}']=this.value;rC()">${f.s?`<button class="eb" onclick="var i=$('c_${f.k}');i.type=i.type==='password'?'text':'password';this.textContent=i.type==='password'?'👁️':'🙈'">👁️</button>`:''}</div><div class="fh">${f.k}</div></div>`;
    });
    h+=`<div class="sec"><button class="sec-h" onclick="this.nextElementSibling.classList.toggle('hd');this.querySelector('.sec-a').style.transform=this.nextElementSibling.classList.contains('hd')?'':'rotate(90deg)'"><div style="display:flex;align-items:center;gap:10px"><span class="sec-t">${sec.t}</span>${B(af?'configured':pf?'warning':'missing',af?'all set':pf?'partial':'needs keys')}</div><span class="sec-a">›</span></button><div class="sec-b hd">${ff}</div></div>`;
  });$('cf').innerHTML=h;
}

async function saveCreds(){
  CRS.forEach(s=>s.f.forEach(f=>{const i=$('c_'+f.k);if(i)CR[f.k]=i.value;}));
  await fetch('/api/credentials',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(CR)});
  $('cs').style.display='block';setTimeout(()=>$('cs').style.display='none',3000);rC();rH();
}

async function rH(){try{const cfg=await(await fetch('/api/config')).json();
const svcs=[{n:"OpenAI",d:"GPT-4o + Whisper",k:"openai"},{n:"Replicate",d:"Image + Video",k:"replicate"},{n:"ElevenLabs",d:"Voiceover",k:"elevenlabs"},{n:"Shotstack",d:"Rendering",k:"shotstack"},{n:"R2",d:"Storage",k:"r2"},{n:"Airtable",d:"Topics",k:"airtable"},{n:"Blotato",d:"Publishing",k:"blotato"}];
$('hl').innerHTML='<div class="rw"><span style="font-family:var(--fm);font-size:9px;color:var(--mt);text-transform:uppercase;letter-spacing:1.5px">API Status</span></div>'+svcs.map(s=>`<div class="rw" style="display:flex;justify-content:space-between;align-items:center"><div><div style="font-size:12.5px;font-weight:500">${s.n}</div><div style="font-family:var(--fm);font-size:9px;color:var(--dm);margin-top:1px">${s.d}</div></div>${B(cfg[s.k]?'configured':'missing')}</div>`).join('');}catch(e){}}

async function testAll(){alert('Testing connections...');for(const s of['openai','replicate','elevenlabs','airtable']){try{const r=await(await fetch('/api/test-connection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service:s})})).json();console.log(s,r);}catch(e){}}rH();alert('Done! Check Health tab.');}

async function init(){
  rP();
  try{const r=await(await fetch('/api/credentials')).json();CR=r;}catch(e){CR={};}
  try{const r=await(await fetch('/api/settings')).json();STS.forEach(s=>s.f.forEach(f=>{if(r[f.k]!==undefined)ST[f.k]=r[f.k];else ST[f.k]=f.d;}));}catch(e){STS.forEach(s=>s.f.forEach(f=>ST[f.k]=f.d));}
  rSt();rC();
  try{const r=await(await fetch('/api/status')).json();if(r.running){RN=true;PH=r.phase;PD=r.phases_done||[];rP();poll();}}catch(e){}
}
</script></body></html>"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
