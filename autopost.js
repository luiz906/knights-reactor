/* ══════════════════════════════════════════════════════════════
   AUTOPOST v2 — Brand-aware Kanban board
   API keys from Render env vars. Brand config from brand settings.
   ══════════════════════════════════════════════════════════════ */

let AP_DATA = {enabled:false, incoming:[], posted:[], failed:[], brand:''};
let AP_STATUS = {};
let AP_CREDS = {};

const _apB = (typeof B === 'function') ? B : function(s, l) {
  const c = {done:'g',running:'b',failed:'r',posted:'g',queued:'b',processing:'b',waiting:'m'}[s] || 'm';
  return '<span class="bg bg-'+c+'"><span class="bd2"></span>'+(l||s)+'</span>';
};

async function apRender() {
  await Promise.all([apLoadBoard(), apLoadStatus(), apLoadCreds()]);
  apRenderBoard();
  apRenderStatus();
  apRenderEnvStatus();
}

async function apLoadBoard() {
  try { AP_DATA = await (await fetch('/ap/board')).json(); } catch(e) { console.error('apBoard',e); }
}
async function apLoadStatus() {
  try { AP_STATUS = await (await fetch('/ap/status')).json(); } catch(e) {}
}
async function apLoadCreds() {
  try { AP_CREDS = await (await fetch('/ap/credentials')).json(); } catch(e) {}
}

function apRenderBoard() {
  ['d-','m-'].forEach(function(p) {
    var el = document.getElementById(p+'apboard');
    if (!el) return;
    if (!AP_DATA.enabled) {
      el.innerHTML = '<div style="text-align:center;padding:2em">'
        +'<div style="font-family:var(--f1);font-size:.8em;color:var(--txtd);letter-spacing:.15em;margin-bottom:.5em">AUTO-POST DISABLED</div>'
        +'<div style="font-size:.7em;color:var(--txtdd);margin-bottom:1em">Enable for this brand to create Dropbox folders</div>'
        +'<button onclick="apEnable()" style="padding:.7em 2em;border:1px solid var(--grn);background:rgba(40,224,96,.08);color:var(--grn);font-family:var(--f1);font-size:.65em;letter-spacing:.12em">ENABLE AUTO-POST</button></div>';
      return;
    }
    if (AP_DATA.error) {
      el.innerHTML = '<div style="padding:1em;color:var(--red);font-size:.7em">Error: '+AP_DATA.error+'</div>';
      return;
    }
    var mobile = p === 'm-';
    el.innerHTML = '<div style="display:flex;gap:12px;'+(mobile?'flex-direction:column':'')+'">'
      + apCol('INCOMING','blu', AP_DATA.incoming||[], 'incoming')
      + apCol('POSTED','grn', AP_DATA.posted||[], 'posted')
      + apCol('FAILED','red', AP_DATA.failed||[], 'failed')
      + '</div>';
  });
}

function apCol(title, color, items, type) {
  var cards = '';
  if (items.length) {
    for (var i = 0; i < items.length; i++) {
      var f = items[i];
      var thumb = f.thumb
        ? '<img src="'+f.thumb+'" style="width:100%;aspect-ratio:1;object-fit:cover;display:block;border-bottom:1px solid var(--bd2)" loading="lazy">'
        : '<div style="width:100%;aspect-ratio:1;background:var(--bg3);display:flex;align-items:center;justify-content:center;font-size:.6em;color:var(--txtdd)">NO PREVIEW</div>';
      var kb = f.size ? Math.round(f.size/1024)+'KB' : '';
      var btn = '';
      var epath = f.path.replace(/'/g,"\\'");
      var ename = f.name.replace(/'/g,"\\'");
      if (type === 'incoming') btn = '<button onclick="apPostNow(\''+epath+'\',\''+ename+'\')" style="width:100%;margin-top:4px;padding:3px;border:1px solid var(--grn);background:rgba(40,224,96,.06);color:var(--grn);font-size:.5em;font-family:var(--f3);letter-spacing:.05em">▶ POST NOW</button>';
      if (type === 'failed') btn = '<button onclick="apRetry(\''+epath+'\',\''+ename+'\')" style="width:100%;margin-top:4px;padding:3px;border:1px solid var(--amb);background:var(--amblo);color:var(--amb);font-size:.5em;font-family:var(--f3);letter-spacing:.05em">♻ RETRY</button>';
      if (type === 'posted') btn = '<div style="margin-top:3px;font-size:.45em;color:var(--grn);letter-spacing:.05em">✓ PUBLISHED</div>';
      cards += '<div style="background:var(--bg);border:1px solid var(--bd2);overflow:hidden;border-radius:2px">'
        + thumb
        + '<div style="padding:4px 6px">'
        + '<div style="font-size:.6em;color:var(--wht);white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="'+f.name+'">'+f.name+'</div>'
        + '<div style="font-size:.45em;color:var(--txtdd);margin-top:1px">'+kb+(f.modified?' · '+f.modified.slice(0,10):'')+'</div>'
        + btn + '</div></div>';
    }
  } else {
    cards = '<div style="padding:1.5em;text-align:center;font-size:.6em;color:var(--txtdd);border:1px dashed var(--bd2)">Empty</div>';
  }
  return '<div style="flex:1;min-width:0">'
    + '<div style="font-family:var(--f1);font-size:.55em;font-weight:600;letter-spacing:.15em;color:var(--'+color+');margin-bottom:6px;display:flex;align-items:center;gap:6px">'
    + '<span style="width:6px;height:6px;background:var(--'+color+');display:inline-block"></span>'
    + title+' <span style="color:var(--txtdd);font-weight:400">('+items.length+')</span></div>'
    + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(7em,1fr));gap:6px">'+cards+'</div></div>';
}

function apRenderStatus() {
  var s = AP_STATUS;
  var stats = [{l:'TOTAL',v:s.total||0,c:'amb'},{l:'POSTED',v:s.posted||0,c:'grn'},{l:'FAILED',v:s.failed||0,c:'red'},{l:'ACTIVE',v:s.active_count||0,c:s.active_count?'blu':'txtd'}];
  var sh = stats.map(function(x){return '<div class="stat"><b style="color:var(--'+x.c+')">'+x.v+'</b><small style="color:var(--'+x.c+')">'+x.l+'</small></div>';}).join('');
  ['d-apst','m-apst'].forEach(function(id){var el=document.getElementById(id);if(el)el.innerHTML=sh;});
  var active=(s.jobs||[]).filter(function(j){return j.status!=='posted'&&j.status!=='failed';});
  var jh=active.length?active.map(function(j){return '<div class="rw" style="display:flex;align-items:center;gap:.5em">'+(j.status.indexOf('process')>=0||j.status==='queued'?'<span class="ap-spin"></span>':'')+'<div style="flex:1"><span style="font-size:.8em;color:var(--wht)">'+j.filename+'</span></div>'+_apB(j.status.indexOf('fail')>=0?'failed':'running',j.status)+'</div>';}).join(''):'<div style="font-size:.65em;color:var(--txtdd);padding:4px">No active jobs</div>';
  ['d-apactive','m-apactive'].forEach(function(id){var el=document.getElementById(id);if(el)el.innerHTML=jh;});
  ['d-apwh','m-apwh'].forEach(function(id){var el=document.getElementById(id);if(el)el.textContent=location.origin+'/ap/webhook/dropbox';});
  ['d-apcur','m-apcur'].forEach(function(id){var el=document.getElementById(id);if(el)el.textContent=s.cursor_ok?'✓ Cursor active':'⚠ No cursor';});
  ['d-apfolders','m-apfolders'].forEach(function(id){var el=document.getElementById(id);if(el&&s.folders)el.textContent=s.folders.incoming;});
}

function apRenderEnvStatus() {
  var keys=['DBX_APP_KEY','DBX_APP_SECRET','DBX_REFRESH_TOKEN','OPENAI_API_KEY','BLOTATO_API_KEY'];
  var h=keys.map(function(k){var set=AP_CREDS[k];return '<span style="font-size:.55em;color:var(--'+(set?'grn':'red')+');margin-right:8px">'+(set?'✓':'✗')+' '+k.replace(/_/g,' ')+'</span>';}).join('');
  ['d-apenv','m-apenv'].forEach(function(id){var el=document.getElementById(id);if(el)el.innerHTML=h;});
}

async function apEnable(){await fetch('/ap/enable',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:true})});setTimeout(apRender,1500);}
async function apTrigger(){await fetch('/ap/trigger',{method:'POST'});setTimeout(apRender,3000);}
async function apPostNow(path,name){await fetch('/ap/post-now',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:path,name:name})});setTimeout(apRender,2000);}
async function apRetry(path,name){await fetch('/ap/retry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:path,name:name})});setTimeout(apRender,2000);}

/* Nav patch */
(function(){
  if(typeof window.dNav==='function'){var _o=window.dNav;window.dNav=function(p,b){_o(p,b);if(p==='autopost')apRender();};}
  if(typeof window.mNav==='function'){var _o=window.mNav;window.mNav=function(p,b){_o(p,b);if(p==='autopost')apRender();};}
  if(typeof window.titles==='object')window.titles['autopost']='◈ AUTO-POST';
})();
