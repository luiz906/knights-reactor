"""
Knights Reactor — Web Server
Minimal dashboard to trigger, monitor, and schedule the pipeline.
"""

import asyncio, json, os, threading, time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pipeline import run_pipeline, Config

app = FastAPI(title="Knights Reactor")

# ─── STATE ────────────────────────────────────────────────────
RUNS = []  # In-memory run log (use SQLite for production)
CURRENT_RUN = {"active": False, "result": None}


def execute_pipeline():
    """Run pipeline in background thread."""
    CURRENT_RUN["active"] = True
    CURRENT_RUN["started"] = datetime.now().isoformat()
    CURRENT_RUN["result"] = None

    result = run_pipeline()

    CURRENT_RUN["active"] = False
    CURRENT_RUN["result"] = result
    RUNS.insert(0, {
        "id": len(RUNS) + 1,
        "date": datetime.now().strftime("%b %d, %I:%M %p"),
        "topic": result.get("topic", {}).get("idea", "Unknown"),
        "category": result.get("topic", {}).get("category", ""),
        "status": result.get("status", "failed"),
        "duration": result.get("duration", "?"),
        "error": result.get("error"),
        "video": result.get("final_video"),
        "phases": result.get("phases", []),
    })


# ─── API ENDPOINTS ────────────────────────────────────────────

@app.post("/api/run")
async def trigger_run(background_tasks: BackgroundTasks):
    if CURRENT_RUN["active"]:
        return JSONResponse({"error": "Pipeline already running"}, 409)
    background_tasks.add_task(execute_pipeline)
    return {"status": "started"}


@app.get("/api/status")
async def get_status():
    return {
        "running": CURRENT_RUN["active"],
        "started": CURRENT_RUN.get("started"),
        "result": CURRENT_RUN.get("result"),
    }


@app.get("/api/runs")
async def get_runs():
    return RUNS[:50]


@app.get("/api/config")
async def get_config():
    """Return which API keys are configured (not the actual keys)."""
    return {
        "openai": bool(Config.OPENAI_KEY),
        "replicate": bool(Config.REPLICATE_TOKEN),
        "elevenlabs": bool(Config.ELEVEN_KEY),
        "shotstack": bool(Config.SHOTSTACK_KEY),
        "r2": bool(Config.R2_ACCESS_KEY),
        "airtable": bool(Config.AIRTABLE_KEY),
        "blotato": bool(Config.BLOTATO_KEY),
    }


# ─── DASHBOARD ────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Knights Reactor</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600;700&family=Outfit:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0a10; --surface: #111118; --raised: #17171f;
    --border: #222233; --gold: #c9a84c; --gold-dim: #8a7234;
    --gold-glow: rgba(201,168,76,0.08);
    --red: #c44; --green: #3a8; --blue: #48a;
    --text: #ddd8cc; --dim: #777266; --muted: #444038;
    --font-d: 'Cormorant Garamond', Georgia, serif;
    --font-b: 'Outfit', system-ui, sans-serif;
    --font-m: 'IBM Plex Mono', monospace;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:var(--bg); color:var(--text); font-family:var(--font-b); min-height:100vh; }

  .container { max-width:640px; margin:0 auto; padding:0 16px; }

  /* Header */
  header {
    padding:20px 0 14px; border-bottom:1px solid var(--border);
    display:flex; align-items:center; justify-content:space-between;
  }
  .logo { display:flex; align-items:center; gap:10px; }
  .logo-icon {
    width:30px; height:30px; border-radius:7px; display:flex;
    align-items:center; justify-content:center; font-size:14px;
    background:linear-gradient(135deg, var(--gold), var(--gold-dim));
  }
  .logo-text { font-family:var(--font-d); font-size:17px; font-weight:700; color:var(--gold); line-height:1; }
  .logo-sub { font-family:var(--font-m); font-size:8px; color:var(--muted); letter-spacing:1.5px; margin-top:2px; }

  #run-btn {
    font-family:var(--font-b); font-size:12px; font-weight:600;
    color:#05050a; background:linear-gradient(135deg, var(--gold), var(--gold-dim));
    border:none; border-radius:7px; padding:8px 16px; cursor:pointer;
    transition: opacity 0.15s;
  }
  #run-btn:hover { opacity:0.9; }
  #run-btn:disabled { opacity:0.4; cursor:wait; background:var(--raised); color:var(--dim); border:1px solid var(--border); }

  /* Tabs */
  .tabs { display:flex; border-bottom:1px solid var(--border); margin-bottom:16px; }
  .tab {
    font-family:var(--font-m); font-size:11px; color:var(--muted);
    background:none; border:none; border-bottom:2px solid transparent;
    padding:11px 14px; cursor:pointer; letter-spacing:0.3px;
  }
  .tab.active { color:var(--gold); border-bottom-color:var(--gold); font-weight:600; }

  /* Cards */
  .card {
    background:var(--surface); border:1px solid var(--border);
    border-radius:9px; padding:13px 15px; margin-bottom:8px;
  }
  .card-header { display:flex; align-items:center; gap:10px; }
  .phase-num {
    font-family:var(--font-m); font-size:10px; font-weight:700; color:var(--gold);
    background:var(--gold-glow); width:24px; height:24px; border-radius:5px;
    display:flex; align-items:center; justify-content:center;
  }
  .phase-name { font-family:var(--font-b); font-size:13px; font-weight:500; }
  .phase-api { font-family:var(--font-m); font-size:9px; color:var(--dim); margin-top:1px; }

  /* Status dots */
  .status {
    font-family:var(--font-m); font-size:9px; padding:2px 7px;
    border-radius:8px; display:inline-flex; align-items:center; gap:4px;
  }
  .status .dot { width:4px; height:4px; border-radius:50%; }
  .status.done { color:var(--green); background:rgba(51,170,136,0.1); }
  .status.done .dot { background:var(--green); }
  .status.running { color:var(--blue); background:rgba(68,136,170,0.1); }
  .status.running .dot { background:var(--blue); animation:pulse 1.2s infinite; }
  .status.failed { color:var(--red); background:rgba(204,68,68,0.1); }
  .status.failed .dot { background:var(--red); }
  .status.idle { color:var(--muted); background:rgba(68,64,56,0.15); }
  .status.idle .dot { background:var(--muted); }

  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }

  /* Progress bar */
  .progress-bar { height:3px; background:var(--border); border-radius:2px; margin:14px 0 6px; overflow:hidden; }
  .progress-fill { height:100%; background:var(--blue); border-radius:2px; transition:width 0.5s ease; }

  /* Run rows */
  .run-row { padding:11px 14px; border-bottom:1px solid var(--border); cursor:pointer; }
  .run-row:hover { background:var(--raised); }
  .run-topic { font-family:var(--font-b); font-size:13px; font-weight:500; }
  .run-meta { font-family:var(--font-m); font-size:9px; color:var(--muted); margin-top:2px; }
  .run-error { font-family:var(--font-m); font-size:10px; color:var(--red); margin-top:6px; }

  /* Stats */
  .stats { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:14px; }
  .stat { background:var(--surface); border:1px solid var(--border); border-radius:9px; padding:12px; text-align:center; }
  .stat-val { font-family:var(--font-d); font-size:20px; font-weight:700; }
  .stat-label { font-family:var(--font-m); font-size:8px; color:var(--gold); letter-spacing:0.5px; margin-top:3px; }

  /* Config */
  .config-row {
    display:flex; align-items:center; justify-content:space-between;
    padding:9px 0; border-bottom:1px solid var(--border);
    font-family:var(--font-m); font-size:11px;
  }
  .config-row:last-child { border-bottom:none; }

  .hidden { display:none; }

  /* Alert bar */
  .alert {
    background:rgba(68,136,170,0.08); border:1px solid rgba(68,136,170,0.2);
    border-radius:9px; padding:10px 14px; margin-bottom:12px;
    font-family:var(--font-m); font-size:11px; color:var(--blue);
    display:flex; align-items:center; gap:8px;
  }
  .alert.error { background:rgba(204,68,68,0.08); border-color:rgba(204,68,68,0.2); color:var(--red); }
  .alert.success { background:rgba(51,170,136,0.08); border-color:rgba(51,170,136,0.2); color:var(--green); }
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="logo">
      <div class="logo-icon">⚔️</div>
      <div>
        <div class="logo-text">Knights Reactor</div>
        <div class="logo-sub">BIBLICAL KNIGHTS · V5 · AUTOMATED</div>
      </div>
    </div>
    <button id="run-btn" onclick="triggerRun()">▶ Run Now</button>
  </header>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('pipeline')">Pipeline</button>
    <button class="tab" onclick="switchTab('runs')">Runs</button>
    <button class="tab" onclick="switchTab('config')">Config</button>
  </div>

  <!-- PIPELINE TAB -->
  <div id="tab-pipeline">
    <div id="alert-area"></div>
    <div id="phases"></div>
  </div>

  <!-- RUNS TAB -->
  <div id="tab-runs" class="hidden">
    <div class="stats" id="stats">
      <div class="stat"><div class="stat-val" id="s-today">0</div><div class="stat-label">Today</div></div>
      <div class="stat"><div class="stat-val" id="s-total">0</div><div class="stat-label">Total Runs</div></div>
      <div class="stat"><div class="stat-val" id="s-success">0%</div><div class="stat-label">Success Rate</div></div>
    </div>
    <div class="card" style="padding:0;overflow:hidden">
      <div style="padding:9px 14px;border-bottom:1px solid var(--border)">
        <span style="font-family:var(--font-m);font-size:8px;color:var(--muted);text-transform:uppercase;letter-spacing:1.5px">Recent Runs</span>
      </div>
      <div id="run-list"></div>
    </div>
  </div>

  <!-- CONFIG TAB -->
  <div id="tab-config" class="hidden">
    <div class="card">
      <div style="font-family:var(--font-d);font-size:15px;font-weight:600;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border)">API Keys Status</div>
      <div id="config-list"></div>
    </div>
    <div class="card" style="margin-top:8px">
      <div style="font-family:var(--font-d);font-size:15px;font-weight:600;margin-bottom:8px">Setup</div>
      <p style="font-family:var(--font-m);font-size:10px;color:var(--dim);line-height:1.5">
        Set API keys as environment variables before starting the server.
        Create a <code style="color:var(--gold)">.env</code> file or export them in your shell.
        Required: OPENAI_API_KEY, REPLICATE_API_TOKEN, ELEVENLABS_API_KEY,
        SHOTSTACK_API_KEY, R2_ACCESS_KEY, R2_SECRET_KEY, R2_ENDPOINT,
        AIRTABLE_API_KEY, BLOTATO_API_KEY
      </p>
    </div>
  </div>
</div>

<script>
const PHASES = [
  {n:"01",name:"Fetch Topic",api:"Airtable"},
  {n:"02",name:"Generate Script",api:"OpenAI GPT-4o"},
  {n:"03",name:"Scene Engine v6",api:"Local"},
  {n:"04",name:"Generate Images",api:"Replicate → GPT-Image-1.5"},
  {n:"05",name:"Generate Videos",api:"Replicate → Seedance-1-Lite"},
  {n:"06",name:"Voiceover",api:"ElevenLabs"},
  {n:"07",name:"Transcribe",api:"OpenAI Whisper"},
  {n:"08",name:"Upload to R2",api:"Cloudflare R2"},
  {n:"09",name:"Final Render",api:"Shotstack"},
  {n:"10",name:"Generate Captions",api:"OpenAI GPT-4o"},
  {n:"11",name:"Publish",api:"Blotato → 7 platforms"},
];

const PHASE_NAMES_MAP = {
  "Fetch Topic":0,"Generate Script":1,"Scene Engine":2,
  "Generate Images":3,"Generate Videos":4,"Voiceover":5,
  "Transcribe":6,"Upload to R2":7,"Final Render":8,
  "Generate Captions":9,"Publish":10,
};

let polling = false;

function renderPhases(activePhases=[]) {
  const done = new Set();
  activePhases.forEach(p => { if(p.status==="done") done.add(PHASE_NAMES_MAP[p.name]); });
  const runningIdx = done.size;
  const isRunning = document.getElementById("run-btn").disabled;

  let html = '';
  if(isRunning) {
    const pct = Math.round(((runningIdx)/PHASES.length)*100);
    html += `<div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>`;
    html += `<div style="font-family:var(--font-m);font-size:9px;color:var(--blue);text-align:right;margin-bottom:10px">${runningIdx}/${PHASES.length}</div>`;
  }

  PHASES.forEach((p,i) => {
    let st = 'idle', stLabel = 'waiting';
    if(done.has(i)) { st='done'; stLabel='done'; }
    else if(isRunning && i===runningIdx) { st='running'; stLabel='running'; }

    html += `<div class="card" style="border-left:3px solid ${st==='done'?'var(--green)':st==='running'?'var(--blue)':'var(--border)'}">
      <div class="card-header">
        <div class="phase-num">${p.n}</div>
        <div style="flex:1">
          <div class="phase-name">${p.name}</div>
          <div class="phase-api">${p.api}</div>
        </div>
        <span class="status ${st}"><span class="dot"></span>${stLabel}</span>
      </div>
    </div>`;
  });
  document.getElementById("phases").innerHTML = html;
}

function switchTab(id) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('[id^=tab-]').forEach(t => t.classList.add('hidden'));
  document.getElementById('tab-'+id).classList.remove('hidden');
  event.target.classList.add('active');
  if(id==='runs') loadRuns();
  if(id==='config') loadConfig();
}

async function triggerRun() {
  const btn = document.getElementById("run-btn");
  btn.disabled = true; btn.textContent = "⏳ Starting...";
  document.getElementById("alert-area").innerHTML = `<div class="alert">Pipeline starting...</div>`;

  try {
    await fetch("/api/run", {method:"POST"});
    startPolling();
  } catch(e) {
    btn.disabled = false; btn.textContent = "▶ Run Now";
    document.getElementById("alert-area").innerHTML = `<div class="alert error">Failed to start: ${e.message}</div>`;
  }
}

function startPolling() {
  if(polling) return;
  polling = true;
  const btn = document.getElementById("run-btn");

  const interval = setInterval(async () => {
    try {
      const r = await fetch("/api/status");
      const data = await r.json();

      if(data.running) {
        btn.disabled = true;
        const phases = data.result?.phases || [];
        const cur = phases.length;
        btn.textContent = `⏳ Phase ${cur+1}/11...`;
        renderPhases(phases);
      } else {
        clearInterval(interval);
        polling = false;
        btn.disabled = false; btn.textContent = "▶ Run Now";

        const result = data.result;
        if(result?.status === "complete") {
          document.getElementById("alert-area").innerHTML = `<div class="alert success">✓ Complete — ${result.duration}</div>`;
          renderPhases(result.phases);
        } else if(result?.status === "failed") {
          document.getElementById("alert-area").innerHTML = `<div class="alert error">✗ Failed: ${result.error}</div>`;
          renderPhases(result.phases || []);
        }
      }
    } catch(e) {
      // Keep polling
    }
  }, 3000);
}

async function loadRuns() {
  try {
    const r = await fetch("/api/runs");
    const runs = await r.json();

    const today = new Date().toLocaleDateString();
    const todayRuns = runs.filter(r => new Date(r.date).toLocaleDateString() === today).length;
    const success = runs.filter(r => r.status === "complete").length;
    const rate = runs.length ? Math.round((success/runs.length)*100) : 0;

    document.getElementById("s-today").textContent = todayRuns || runs.length;
    document.getElementById("s-total").textContent = runs.length;
    document.getElementById("s-success").textContent = rate + "%";

    let html = '';
    if(!runs.length) {
      html = '<div style="padding:20px;text-align:center;font-family:var(--font-m);font-size:11px;color:var(--muted)">No runs yet. Hit ▶ Run Now.</div>';
    }
    runs.forEach(run => {
      html += `<div class="run-row">
        <div style="display:flex;align-items:center;gap:10px">
          <div style="flex:1">
            <div class="run-topic">${run.topic}</div>
            <div class="run-meta">${run.date} · ${run.category} · ${run.duration}</div>
          </div>
          <span class="status ${run.status}"><span class="dot"></span>${run.status}</span>
        </div>
        ${run.error ? `<div class="run-error">${run.error}</div>` : ''}
      </div>`;
    });
    document.getElementById("run-list").innerHTML = html;
  } catch(e) {}
}

async function loadConfig() {
  try {
    const r = await fetch("/api/config");
    const cfg = await r.json();
    const labels = {
      openai:"OpenAI (GPT-4o + Whisper)", replicate:"Replicate (Images + Video)",
      elevenlabs:"ElevenLabs (Voiceover)", shotstack:"Shotstack (Render)",
      r2:"Cloudflare R2 (Storage)", airtable:"Airtable (Topics)",
      blotato:"Blotato (Publishing)"
    };
    let html = '';
    Object.entries(cfg).forEach(([key, ok]) => {
      html += `<div class="config-row">
        <span>${labels[key]||key}</span>
        <span class="status ${ok?'done':'failed'}"><span class="dot"></span>${ok?'configured':'missing'}</span>
      </div>`;
    });
    document.getElementById("config-list").innerHTML = html;
  } catch(e) {}
}

// Init
renderPhases();

// Check if a run is active on page load
(async () => {
  try {
    const r = await fetch("/api/status");
    const data = await r.json();
    if(data.running) {
      document.getElementById("run-btn").disabled = true;
      startPolling();
    }
  } catch(e) {}
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
