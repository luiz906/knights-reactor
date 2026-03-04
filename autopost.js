/* ══════════════════════════════════════════════════════════════
   AUTOPOST MODULE — Dropbox → Blotato image auto-publisher
   Add <script src="/static/autopost.js"></script> after app.js in dashboard.html
   ══════════════════════════════════════════════════════════════ */

const AP_CFG_FIELDS = [
  {t:"DROPBOX", f:[
    {k:"DBX_APP_KEY", l:"App Key"},
    {k:"DBX_APP_SECRET", l:"App Secret"},
    {k:"DBX_REFRESH_TOKEN", l:"Refresh Token"}
  ]},
  {t:"BLOTATO", f:[
    {k:"AP_BLOTATO_KEY", l:"API Key"},
    {k:"AP_BLOTATO_ACCOUNTS", l:"Accounts JSON", ph:'[{"id":"12345","platform":"instagram"},{"id":"67890","platform":"facebook","pageId":"pg123"}]'}
  ]},
  {t:"AI CAPTION", f:[
    {k:"AP_OPENAI_KEY", l:"OpenAI Key"},
    {k:"AP_CAPTION_PROMPT", l:"Caption Prompt"}
  ]},
  {t:"FOLDERS", f:[
    {k:"AP_WATCH_FOLDER", l:"Watch Folder", d:"/AutoPost/Incoming"},
    {k:"AP_POSTED_FOLDER", l:"Posted Folder", d:"/AutoPost/Posted"},
    {k:"AP_FAILED_FOLDER", l:"Failed Folder", d:"/AutoPost/Failed"},
    {k:"AP_MAX_RETRIES", l:"Max Retries", d:"3"}
  ]}
];

let AP_ST = {}, AP_CREDS_SET = {};

/* Badge helper — reuse from app.js if available */
const _apB = (typeof B === 'function') ? B : function(s, l) {
  const c = {done:'g',running:'b',failed:'r',configured:'g',missing:'r',waiting:'m'}[s] || 'm';
  return `<span class="bg bg-${c}"><span class="bd2"></span>${l||s}</span>`;
};

async function apPoll() {
  try {
    const r = await (await fetch('/ap/status')).json();
    const stats = [
      {l:'TOTAL', v:r.total, c:'amb'},
      {l:'POSTED', v:r.posted, c:'grn'},
      {l:'FAILED', v:r.failed, c:'red'},
      {l:'ACTIVE', v:r.active_count, c:r.active_count ? 'blu' : 'txtd'}
    ];
    const sh = stats.map(s =>
      `<div class="stat"><b style="color:var(--${s.c})">${s.v}</b><small style="color:var(--${s.c})">${s.l}</small></div>`
    ).join('');
    ['d-apst','m-apst'].forEach(id => { const el = document.getElementById(id); if(el) el.innerHTML = sh; });

    // Active jobs
    const activeJobs = (r.jobs || []).filter(j => j.status !== 'posted' && j.status !== 'failed');
    const jh = activeJobs.length ? activeJobs.map(j =>
      `<div class="rw"><div style="display:flex;align-items:center;gap:.5em">`
      + (j.status.includes('process') || j.status === 'queued' ? '<span class="ap-spin"></span>' : '')
      + `<div style="flex:1"><div style="font-size:.8em;color:var(--wht)">${j.filename||'?'}</div>`
      + `<div style="font-size:.55em;color:var(--txtd)">${j.started||''}</div></div>`
      + _apB(j.status.includes('fail') ? 'failed' : j.status.includes('post') ? 'done' : 'running', j.status)
      + `</div>${j.error ? `<div style="font-size:.6em;color:var(--red);margin-top:3px">${j.error}</div>` : ''}</div>`
    ).join('') : '<div style="font-size:.7em;color:var(--txtd);padding:.5em">No active jobs</div>';
    ['d-apjobs','m-apjobs'].forEach(id => { const el = document.getElementById(id); if(el) el.innerHTML = jh; });

    // Recent runs
    const runs = (r.runs || []).slice(0, 20);
    const rh = runs.length ? runs.map(run =>
      `<div class="rw"><div style="display:flex;align-items:center;gap:.5em">`
      + `<div style="flex:1"><div style="font-size:.8em;color:var(--wht)">${run.filename||'?'}</div>`
      + `<div style="font-size:.55em;color:var(--txtd)">${run.date} · ${(run.platforms||[]).join(', ')}</div></div>`
      + _apB(run.status === 'posted' ? 'done' : 'failed', run.status)
      + `</div>${run.caption ? `<div style="font-size:.6em;color:var(--txtdd);margin-top:2px">${run.caption}</div>` : ''}</div>`
    ).join('') : '<div style="font-size:.7em;color:var(--txtd);padding:.5em">No posts yet</div>';
    ['d-apruns','m-apruns'].forEach(id => { const el = document.getElementById(id); if(el) el.innerHTML = rh; });

    // Cursor status
    ['d-apcur','m-apcur'].forEach(id => {
      const el = document.getElementById(id);
      if(el) el.textContent = r.cursor_ok ? '✓ Cursor active' : '⚠ Cursor not initialized';
    });
  } catch(e) { console.error('apPoll', e); }
}

function setApWebhookUrl() {
  const u = location.origin + '/ap/webhook/dropbox';
  ['d-apwh','m-apwh'].forEach(id => { const el = document.getElementById(id); if(el) el.textContent = u; });
}

async function apTrigger() {
  try {
    await fetch('/ap/trigger', {method: 'POST'});
    setTimeout(apPoll, 2000);
  } catch(e) { alert('Error: ' + e); }
}

function rApCfg() {
  let h = '';
  AP_CFG_FIELDS.forEach((sec) => {
    let ff = '';
    sec.f.forEach(f => {
      const set = AP_CREDS_SET[f.k];
      const v = AP_ST[f.k] || f.d || '';
      ff += `<div class="fi"><div class="fl">${f.l} ${set ? '<span style="color:var(--grn)">✓ SET</span>' : ''}</div>`
          + `<input class="fin" value="${v}" placeholder="${f.ph||''}" onchange="AP_ST['${f.k}']=this.value"></div>`;
    });
    h += `<div class="sec"><button class="sec-h" onclick="this.nextElementSibling.classList.toggle('shut')">`
       + `<span class="sec-t">${sec.t}</span><span class="sec-a">›</span></button>`
       + `<div class="sec-b shut">${ff}</div></div>`;
  });
  ['d-apcfg','m-apcfg'].forEach(id => { const el = document.getElementById(id); if(el) el.innerHTML = h; });
}

async function apSaveCfg() {
  const body = {};
  AP_CFG_FIELDS.forEach(s => s.f.forEach(f => { if(AP_ST[f.k]) body[f.k] = AP_ST[f.k]; }));
  await fetch('/ap/credentials', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  ['d-apss','m-apss'].forEach(id => {
    const el = document.getElementById(id);
    if(el) { el.style.display = 'block'; setTimeout(() => el.style.display = 'none', 3000); }
  });
  apLoadCreds();
}

async function apLoadCreds() {
  try { AP_CREDS_SET = await (await fetch('/ap/credentials')).json(); } catch(e) {}
}

/* ─── PATCH nav functions if they exist ─── */
(function() {
  // Patch dNav
  if (typeof window.dNav === 'function') {
    const _origDNav = window.dNav;
    window.dNav = function(p, btn) {
      _origDNav(p, btn);
      if (p === 'autopost') { apPoll(); setApWebhookUrl(); rApCfg(); }
    };
  }
  // Patch mNav
  if (typeof window.mNav === 'function') {
    const _origMNav = window.mNav;
    window.mNav = function(p, btn) {
      _origMNav(p, btn);
      if (p === 'autopost') { apPoll(); setApWebhookUrl(); rApCfg(); }
    };
  }
  // Patch titles
  if (typeof window.titles === 'object') {
    window.titles['autopost'] = '◈ AUTO-POST';
  }
  // Load AP creds on boot
  apLoadCreds();
})();
