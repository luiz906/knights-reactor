let RN=false,PH=0,PD=[],ST={},LAST_RESULT=null,GATE=null,SCENE_DATA=null;
const $=id=>document.getElementById(id);
const TB=(s)=>{const m={new:'m',processing:'b',executed:'g',published:'g',failed:'r'};const l={new:'NEW',processing:'ACTIVE',executed:'DONE',published:'DONE',failed:'FAIL'};const c=m[(s||'new').toLowerCase()]||'m';return '<span class="bg bg-'+c+'"><span class="bd2"></span>'+(l[(s||'new').toLowerCase()]||s)+'</span>';};
const B=(s,l)=>{const c={done:'g',running:'b',failed:'r',configured:'g',missing:'r',waiting:'m',gated:'o'}[s]||'m';return`<span class="bg bg-${c}"><span class="bd2"></span>${l||s}</span>`};
const PHS=[{n:"FETCH TOPIC",a:"LOCAL DB",i:"⬡",d:"~1s"},{n:"GENERATE SCRIPT",a:"GPT-4o",i:"⬢",d:"~3s"},{n:"SCENE ENGINE",a:"LOCAL",i:"◈",d:"<1s"},{n:"GENERATE IMAGES",a:"REPLICATE",i:"◉",d:"~30s"},{n:"GENERATE VIDEOS",a:"REPLICATE",i:"▶",d:"~120s"},{n:"VOICEOVER",a:"ELEVENLABS",i:"◎",d:"~4s"},{n:"TRANSCRIBE",a:"WHISPER",i:"▤",d:"~3s"},{n:"UPLOAD ASSETS",a:"R2",i:"⬆",d:"~8s"},{n:"FINAL RENDER",a:"SHOTSTACK",i:"⬡",d:"~90s"},{n:"CAPTIONS",a:"GPT-4o",i:"✎",d:"~4s"},{n:"PUBLISH",a:"BLOTATO",i:"◇",d:"~6s"}];

const STS=[
{t:"BRAND",f:[{k:"brand_name",l:"Brand Name",d:"Knights Reactor",b:1},{k:"brand_tagline",l:"Tagline",d:"Biblical content for men of faith",b:1},{k:"brand_persona",l:"Character Persona",tp:"textarea",d:"A battle-hardened Christian knight: Strong, disciplined, capable, calm. Not cruel, not cold—firm and compassionate. Protector of faith, family, duty, truth. Lives in peace but ready for war. Wears the Armor of God (Ephesians 6) symbolically. Unwavering allegiance: Christ is King.",b:1},{k:"brand_voice",l:"Voice Description",tp:"textarea",d:"Low, controlled, resonant. Calm intensity; authoritative without shouting. Short, declarative sentences. Measured pacing. Dark, mysterious presence—disciplined resolve. Masculine and grounded. NO hype. NO motivational fluff.",b:1},{k:"brand_themes",l:"Core Themes",tp:"textarea",d:"Address real daily battles: Finances, family leadership, temptation, fatigue, doubt, lust, anger, responsibility, endurance, obedience. Discipline over comfort. Duty over desire. Endurance over escape. Faith over fear. Action over emotion.",b:1},{k:"brand_avoid",l:"What to Avoid",d:"Warmth or sentimentality, soft encouragement, modern slang, politics, long scripture quotations, hashtags",b:1}]},
{t:"SCRIPT ENGINE",f:[{k:"script_model",l:"AI Model",tp:"select",o:["gpt-4o","gpt-4o-mini"],d:"gpt-4o"},{k:"script_temp",l:"Temperature",d:"0.85"},{k:"script_words",l:"Script Length",tp:"slider",min:30,max:180,step:5,d:90}]},
{t:"SCENE ENGINE",f:[{k:"scene_story",l:"Story Seed",tp:"select",o:["auto"],d:"auto",dynamic:"stories"},{k:"scene_theme",l:"Theme Force",tp:"select",o:["auto"],d:"auto",dynamic:"themes"},{k:"scene_figure",l:"Figure",tp:"select",o:["auto"],d:"auto",dynamic:"figures"},{k:"scene_intensity",l:"Intensity",tp:"select",o:["still","measured","dynamic"],d:"measured"},{k:"scene_camera",l:"Camera Style",tp:"select",o:["steady","dynamic","handheld"],d:"steady"},{k:"scene_mood",l:"Mood Lighting",tp:"select",o:["auto"],d:"auto",dynamic:"moods"},{k:"_scene_pack",l:"",tp:"scene_pack"}]},
{t:"VOICE SYNTH",f:[{k:"voice_id",l:"Voice ID",d:"bwCXcoVxWNYMlC6Esa8u",b:1},{k:"voice_model",l:"Model",tp:"select",o:["eleven_turbo_v2","eleven_multilingual_v2","eleven_monolingual_v1"],d:"eleven_turbo_v2"},{k:"voice_stability",l:"Stability",d:"0.5"},{k:"voice_similarity",l:"Similarity",d:"0.75"},{k:"voice_speed",l:"Speed",d:"1.0"},{k:"voice_style",l:"Style",d:"0.0"}]},
{t:"IMAGE GENERATION",f:[{k:"image_provider",l:"Provider",tp:"select",o:["replicate"],d:"replicate"},{k:"image_model",l:"Model",tp:"select",o:[],d:"black-forest-labs/flux-1.1-pro",dep:"image_provider"},{k:"image_quality",l:"Quality",tp:"select",o:["low","medium","high"],d:"high"}]},
{t:"VIDEO GENERATION",f:[{k:"video_provider",l:"Provider",tp:"select",o:["replicate"],d:"replicate"},{k:"video_model",l:"Model",tp:"select",o:[],d:"bytedance/seedance-1-lite",dep:"video_provider"},{k:"clip_count",l:"Clips",tp:"select",o:["2","3","4","5"],d:"3"},{k:"clip_duration",l:"Clip Duration",tp:"select",o:["5","8","10","12","15"],d:"10"},{k:"cta_enabled",l:"CTA End Card",tp:"toggle",d:true},{k:"cta_duration",l:"CTA Duration (sec)",tp:"select",o:["3","4","5","6","8"],d:"5"},{k:"_vid_total",l:"",tp:"computed"},{k:"video_timeout",l:"Timeout (sec)",d:"600"}]},
{t:"RENDER OUTPUT",f:[{k:"shotstack_env",l:"Shotstack Mode",tp:"select",o:["stage","v1"],d:"stage"},{k:"render_fps",l:"FPS",tp:"select",o:["24","30","60"],d:"30"},{k:"render_res",l:"Resolution",tp:"select",o:["720","1080"],d:"1080"},{k:"render_aspect",l:"Aspect Ratio",tp:"select",o:["9:16","16:9","1:1"],d:"9:16"},{k:"render_bg",l:"Background Color",d:"#000000"}]},
{t:"WATERMARK / LOGO",f:[{k:"logo_enabled",l:"Show Logo",tp:"toggle",d:true},{k:"captions_enabled",l:"Show Captions",tp:"toggle",d:true},{k:"logo_url",l:"Logo URL",d:""},{k:"logo_position",l:"Position",tp:"select",o:["topRight","topLeft","bottomRight","bottomLeft","center"],d:"topRight"},{k:"logo_scale",l:"Scale",d:"0.12"},{k:"logo_opacity",l:"Opacity",d:"0.8"}]},
{t:"PLATFORMS",f:[{k:"on_tt",l:"TikTok",tp:"toggle",d:true},{k:"on_yt",l:"YouTube",tp:"toggle",d:true},{k:"on_ig",l:"Instagram",tp:"toggle",d:true},{k:"on_fb",l:"Facebook",tp:"toggle",d:true},{k:"on_tw",l:"X/Twitter",tp:"toggle",d:true},{k:"on_th",l:"Threads",tp:"toggle",d:true},{k:"on_pn",l:"Pinterest",tp:"toggle",d:false}]}
];
let stOpen={};
const IMG_MODELS={replicate:[{v:"google/nano-banana-pro",l:"Nano Banana Pro"},{v:"google/nano-banana",l:"Nano Banana"},{v:"xai/grok-imagine-image",l:"Grok Aurora"},{v:"bytedance/seedream-4.5",l:"Seedream 4.5"},{v:"black-forest-labs/flux-1.1-pro",l:"Flux 1.1 Pro"},{v:"black-forest-labs/flux-schnell",l:"Flux Schnell"},{v:"black-forest-labs/flux-dev",l:"Flux Dev"},{v:"ideogram-ai/ideogram-v3-quality",l:"Ideogram v3 Q"},{v:"ideogram-ai/ideogram-v3-turbo",l:"Ideogram v3 T"},{v:"recraft-ai/recraft-v3",l:"Recraft v3"},{v:"stability-ai/stable-diffusion-3.5-large",l:"SD 3.5 L"},{v:"google-deepmind/imagen-4-preview",l:"Imagen 4"}]};
const VID_MODELS={replicate:[{v:"bytedance/seedance-1-lite",l:"Seedance Lite"},{v:"bytedance/seedance-1",l:"Seedance Pro"},{v:"wavespeedai/wan-2.1-i2v-480p",l:"Wan 480p"},{v:"wavespeedai/wan-2.1-i2v-720p",l:"Wan 720p"},{v:"xai/grok-imagine-video",l:"Grok Video"},{v:"minimax/video-01-live",l:"Minimax Live"},{v:"minimax/video-01",l:"Minimax v01"},{v:"kwaivgi/kling-v2.0-image-to-video",l:"Kling v2.0"},{v:"luma/ray-2-flash",l:"Luma Flash"},{v:"luma/ray-2",l:"Luma Ray 2"},{v:"google-deepmind/veo-3",l:"Veo 3"}]};
const SVCS=[{n:"OPENAI",d:"GPT-4o + Whisper",k:"openai"},{n:"REPLICATE",d:"Image + Video",k:"replicate"},{n:"ELEVENLABS",d:"Voice Synthesis",k:"elevenlabs"},{n:"SHOTSTACK",d:"Video Render",k:"shotstack"},{n:"R2",d:"Asset Storage",k:"r2"},{n:"BLOTATO",d:"Publishing",k:"blotato"}];
const titles={pipeline:'⚡ PIPELINE MONITOR',manual:'◈ MANUAL PIPELINE',topics:'✦ TOPIC DATABASE',runs:'◈ RUN HISTORY',logs:'▤ SYSTEM LOGS',preview:'◉ ASSET PREVIEW',settings:'⚙ CONFIGURATION',health:'◎ SYSTEM STATUS',channels:'📡 PUBLISHING CHANNELS'};

/* THEME */
function toggleTheme(){const on=document.documentElement.classList.toggle('light');localStorage.setItem('kr-theme',on?'light':'dark');updThemeBtn();}
function updThemeBtn(){const lt=document.documentElement.classList.contains('light');['d-thm','m-thm'].forEach(id=>{const el=$(id);if(el)el.textContent=lt?'◑ DARK MODE':'☀ LIGHT MODE';});}
(function(){if(localStorage.getItem('kr-theme')==='light')document.documentElement.classList.add('light');})();

/* AUTH */
async function go(){const p=$('pw').value;if(!p){$('le').style.display='block';return;}try{const r=await(await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:p})})).json();if(r.ok){if(r.token)sessionStorage.setItem('kt',r.token);$('L').style.display='none';$('A').classList.remove('hd');init();}else{$('le').style.display='block';}}catch(e){$('le').style.display='block';}}
async function autoLogin(){const t=sessionStorage.getItem('kt');if(!t)return;try{const r=await(await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:t})})).json();if(r.ok){$('L').style.display='none';$('A').classList.remove('hd');init();}}catch(e){}}

/* NAV */
function dNav(p,btn){document.querySelectorAll('.dpage').forEach(e=>e.classList.remove('on'));document.querySelectorAll('.sb-i').forEach(b=>b.classList.remove('on'));$('dp-'+p).classList.add('on');if(btn)btn.classList.add('on');$('d-title').textContent=titles[p]||p;if(p==='topics')loadTopics();if(p==='runs')loadRuns();if(p==='logs')loadLogs();if(p==='preview')rPv();if(p==='health')rH();if(p==='channels')loadChannels();}
function mNav(p,btn){document.querySelectorAll('.mpage').forEach(e=>e.classList.remove('on'));document.querySelectorAll('.mt').forEach(b=>b.classList.remove('on'));$('mp-'+p).classList.add('on');if(btn)btn.classList.add('on');if(p==='topics')loadTopics();if(p==='runs')loadRuns();if(p==='logs')loadLogs();if(p==='preview')rPv();if(p==='health')rH();if(p==='channels')loadChannels();}

/* ═══ GATE BANNERS ═══ */
function rGate(){
  let h='';
  if(GATE==='prompts'){
    h=`<div class="gate-banner"><div class="g-icon">✎</div><div class="g-text"><div class="g-title">PROMPT EDITING GATE</div><div class="g-sub">Scene Engine complete — review and edit image/motion prompts before generating</div></div><div style="display:flex;gap:6px"><button class="btn-sm btn-blu" onclick="openPromptEditor()">EDIT PROMPTS</button><button class="btn-sm btn-grn" onclick="resumeNow()">APPROVE & CONTINUE ▶</button></div></div>`;
  }else if(GATE==='videos'){
    h=`<div class="gate-banner"><div class="g-icon">▶</div><div class="g-text"><div class="g-title">VIDEO APPROVAL GATE</div><div class="g-sub">Videos generated — review clips, regenerate if needed, then approve</div></div><div style="display:flex;gap:6px"><button class="btn-sm btn-blu" onclick="openVideoReview()">REVIEW CLIPS</button><button class="btn-sm btn-grn" onclick="approveAllVideos()">APPROVE ALL ▶</button></div></div>`;
  }
  ['d-gate','m-gate'].forEach(id=>{if($(id))$(id).innerHTML=h;});
  if(GATE==='prompts')setTimeout(openPromptEditor,100);
  if(GATE==='videos')setTimeout(openVideoReview,100);
}

/* ═══ PROMPT EDITOR ═══ */
async function openPromptEditor(){
  try{
    const r=await(await fetch('/api/prompts')).json();
    if(!r.clips||!r.clips.length){alert('No prompts found');return;}
    let h='<div style="font-family:var(--f1);font-size:.7em;letter-spacing:.15em;color:var(--amb);margin-bottom:.5em">EDIT SCENE PROMPTS</div>';
    if(r.script)h+=`<div class="panel" style="font-size:.75em;color:var(--wht);line-height:1.6;margin-bottom:.7em"><b style="color:var(--amb)">Script:</b> ${r.script.script_full||''}</div>`;
    r.clips.forEach(c=>{
      h+=`<div class="clip-edit" id="ce-${c.index}"><div class="ce-head">SCENE ${c.index}</div><div class="fl">IMAGE PROMPT</div><textarea id="ip-${c.index}" rows="3">${c.image_prompt||''}</textarea><div class="fl" style="margin-top:.4em">MOTION PROMPT</div><textarea id="mp-${c.index}" rows="2">${c.motion_prompt||''}</textarea></div>`;
    });
    h+=`<div style="display:flex;gap:8px;margin-top:.7em"><button class="btn-sm btn-grn" onclick="savePrompts(${r.clips.length})">SAVE & CONTINUE ▶</button><button class="btn-sm" onclick="rP()">CANCEL</button></div>`;
    // Show in pipeline area
    ['d-pl','m-pl'].forEach(id=>{if($(id))$(id).innerHTML=h;});
    ['d-stats'].forEach(id=>{if($(id))$(id).innerHTML='';});
  }catch(e){alert('Error loading prompts: '+e);}
}

async function savePrompts(count){
  const clips=[];
  for(let i=1;i<=count;i++){
    const ip=$('ip-'+i),mp=$('mp-'+i);
    if(ip&&mp)clips.push({index:i,image_prompt:ip.value,motion_prompt:mp.value});
  }
  try{
    await fetch('/api/prompts/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clips})});
    GATE=null;rGate();
    resumeNow();
  }catch(e){alert('Save failed: '+e);}
}

/* ═══ VIDEO REVIEW ═══ */
async function openVideoReview(){
  try{
    const r=await(await fetch('/api/videos/review')).json();
    if(!r.clips||!r.clips.length){alert('No videos found');return;}
    let h='<div style="font-family:var(--f1);font-size:.7em;letter-spacing:.15em;color:var(--amb);margin-bottom:.5em">REVIEW VIDEO CLIPS</div>';
    r.clips.forEach(c=>{
      h+=`<div class="clip-review" id="vr-${c.index}"><video src="${c.video_url}" controls muted playsinline></video><div style="font-size:.65em;color:var(--txtd);margin-bottom:.3em">Clip ${c.index}</div><div class="cr-acts"><button class="btn-sm btn-red" onclick="regenClip(${c.index})">♻ REGENERATE</button><span id="vrs-${c.index}" style="font-size:.6em;color:var(--txtd)"></span></div></div>`;
    });
    h+=`<div style="display:flex;gap:8px;margin-top:.7em"><button class="btn-sm btn-grn" onclick="approveAllVideos()">APPROVE ALL & CONTINUE ▶</button><button class="btn-sm" onclick="rP()">CANCEL</button></div>`;
    ['d-pl','m-pl'].forEach(id=>{if($(id))$(id).innerHTML=h;});
    ['d-stats'].forEach(id=>{if($(id))$(id).innerHTML='';});
  }catch(e){alert('Error loading videos: '+e);}
}

async function regenClip(idx){
  const st=$('vrs-'+idx);
  if(st)st.textContent='Regenerating...';
  try{
    const r=await(await fetch('/api/videos/regen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({index:idx})})).json();
    if(r.clip){
      const vr=$('vr-'+idx);
      if(vr){const vid=vr.querySelector('video');if(vid)vid.src=r.clip.video_url;}
      if(st)st.textContent='Regenerated ✓';
    }else{if(st)st.textContent='Failed: '+(r.error||'unknown');}
  }catch(e){if(st)st.textContent='Error: '+e;}
}

async function approveAllVideos(){
  try{
    const r=await(await fetch('/api/videos/review')).json();
    await fetch('/api/videos/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clips:r.clips||[]})});
    GATE=null;rGate();
    resumeNow();
  }catch(e){alert('Approval failed: '+e);}
}

/* ═══ PIPELINE RENDER ═══ */
function rP(){
  let h='';
  PHS.forEach((p,i)=>{
    let s='waiting',c='',sl='';
    if(PD.includes(i)){s='done';c='dn';sl='COMPLETE';}
    else if(RN&&i===PH){s='running';c='rn';sl='ACTIVE';}
    else if(RN&&i<PH){s='done';c='dn';sl='COMPLETE';}
    else if(RN){c='dm';}
    // Gate markers
    if(!RN&&GATE==='prompts'&&i===2){s='gated';c='gt';sl='GATE';}
    if(!RN&&GATE==='videos'&&i===4){s='gated';c='gt';sl='GATE';}
    const nc=s==='done'?'var(--grn)':s==='running'?'var(--blu)':s==='gated'?'var(--amb)':'var(--txtdd)';
    const nt=s==='done'?'var(--grn)':s==='running'?'var(--amb)':s==='gated'?'var(--amb)':'var(--txtd)';
    h+=`<div class="ph ${c}"><div style="display:flex;align-items:center;gap:.55em"><span style="font-size:.8em;width:1.15em;text-align:center;color:${nc}">${p.i}</span><div style="flex:1"><div style="font-family:var(--f1);font-size:.6em;font-weight:600;letter-spacing:.15em;color:${nt}">${p.n}</div><div style="font-size:.5em;color:var(--txtdd);margin-top:.05em;letter-spacing:.08em">${p.a} · ${p.d}</div></div>${sl?`<span style="font-family:var(--f1);font-size:.5em;color:${nc};letter-spacing:1px">${sl}</span>`:''} ${B(s)}</div></div>`;
  });
  ['d-pl','m-pl'].forEach(id=>{if($(id))$(id).innerHTML=h;});
  const pct=(PD.length/PHS.length*100);
  ['d-pb','m-pb'].forEach(id=>{if($(id))$(id).style.width=pct+'%';});
  rGate();
  // Stats
  if($('d-stats')){const t=PD.length,tot=PHS.length;$('d-stats').innerHTML=[{l:'PHASES',v:t+'/'+tot,c:'amb'},{l:'PROGRESS',v:Math.round(pct)+'%',c:pct>=100?'grn':'blu'},{l:'STATUS',v:RN?'RUNNING':GATE?'GATED':'IDLE',c:RN?'blu':GATE?'amb':'txtd'},{l:'LAST',v:LAST_RESULT?LAST_RESULT.status:'—',c:LAST_RESULT&&LAST_RESULT.status==='failed'?'red':'grn'}].map(s=>`<div class="stat"><b style="color:var(--${s.c})">${s.v}</b><small style="color:var(--${s.c})">${s.l}</small></div>`).join('');}
  // Phase indicator
  if(RN){
    if($('d-ph'))$('d-ph').textContent='PHASE '+(PH+1)+'/11';
    ['d-rb','m-rb','d-rb2','m-rb2'].forEach(id=>{if($(id)){$(id).textContent='⏳';$(id).style.background='var(--bg3)';$(id).style.color='var(--txtd)';}});
  }else{
    if($('d-ph'))$('d-ph').textContent='';
    if($('d-rb')){$('d-rb').textContent='▶ EXECUTE';$('d-rb').style.background='var(--amb)';$('d-rb').style.color='var(--bg)';}
    if($('m-rb')){$('m-rb').textContent='▶ EXECUTE';$('m-rb').style.background='var(--amb)';$('m-rb').style.color='var(--bg)';}
    if($('d-rb2')){$('d-rb2').textContent='▶ EXECUTE';$('d-rb2').style.background='var(--amb)';$('d-rb2').style.color='var(--bg)';}
    if($('m-rb2')){$('m-rb2').textContent='▶ EXECUTE';$('m-rb2').style.background='var(--amb)';$('m-rb2').style.color='var(--bg)';}
  }
  // Resume button — show for gates and failures
  const showRes=(!RN&&(GATE||LAST_RESULT&&LAST_RESULT.status==='failed'));
  ['d-rsb','m-rsb','d-rsb2'].forEach(id=>{if($(id))$(id).style.display=showRes?'block':'none';});
}

/* ═══ ACTIONS ═══ */
async function runNow(topicId){
  if(RN)return;
  const body=topicId?{topic_id:topicId}:{};
  await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  RN=true;PH=0;PD=[];GATE=null;rP();poll();
}
async function resumeNow(){
  if(RN)return;
  const r=await fetch('/api/resume',{method:'POST'});
  const d=await r.json();
  if(r.ok){RN=true;GATE=null;PD=[];rP();poll();}
  else{alert(d.error||'Resume failed');}
}
/* Manual clip card system */
let manClips=[{url:''},{url:''},{url:''}]; // Start with 3 empty slots

function renderManualCards(px){
  const grid=$(px+'-mclips');
  if(!grid)return;
  grid.innerHTML='';
  manClips.forEach((clip,i)=>{
    const card=document.createElement('div');
    card.className='man-card';
    card.dataset.idx=i;
    const url=clip.url||'';
    const hasUrl=url&&url.startsWith('http');
    let previewHtml='';
    if(hasUrl){
      previewHtml=`<video src="${url}" muted loop playsinline onmouseenter="this.play()" onmouseleave="this.pause();this.currentTime=0" ontouchstart="this.paused?this.play():this.pause()"></video>`;
      if(clip.dur) previewHtml+=`<div class="man-card-badge">${fmtDur(clip.dur)}</div>`;
      previewHtml+=`<div class="man-card-num">CLIP ${i+1}</div>`;
      if(manClips.length>1) previewHtml+=`<div class="man-card-rm" onclick="removeClip(${i})">✕</div>`;
    }else{
      previewHtml=`<div class="man-card-empty" onclick="this.closest('.man-card').querySelector('.man-url').focus()"><span style="font-size:1.5em">▶</span><span>CLIP ${i+1}</span></div>`;
      if(manClips.length>1) previewHtml+=`<div class="man-card-rm" style="opacity:1" onclick="event.stopPropagation();removeClip(${i})">✕</div>`;
    }
    card.innerHTML=`<div class="man-card-preview">${previewHtml}</div><div class="man-card-bar"><input class="fin man-url mc-url" value="${url}" placeholder="Clip ${i+1} URL" style="flex:1" data-idx="${i}" onchange="onClipUrl(this)" onpaste="setTimeout(()=>onClipUrl(this),100)"><button class="btn-upload" onclick="uploadFile(this,'video')">▤</button></div>`;
    grid.appendChild(card);
  });
}
function fmtDur(s){return s>=60?Math.floor(s/60)+'m'+Math.round(s%60)+'s':Math.round(s*10)/10+'s';}
async function onClipUrl(inp){
  const idx=parseInt(inp.dataset.idx);
  const url=inp.value.trim();
  manClips[idx].url=url;
  manClips[idx].dur=0;
  // Re-render both grids
  ['d','m'].forEach(px=>renderManualCards(px));
  // Probe duration
  if(url&&url.startsWith('http')){
    try{
      const r=await fetch('/api/probe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
      const d=await r.json();
      if(d.duration){manClips[idx].dur=d.duration;}
    }catch(e){}
    ['d','m'].forEach(px=>renderManualCards(px));
  }
  updateTotals();
}
function removeClip(idx){
  if(manClips.length<=1)return;
  manClips.splice(idx,1);
  ['d','m'].forEach(px=>renderManualCards(px));
  updateTotals();
}
function addClipCard(px){
  if(manClips.length>=6)return;
  manClips.push({url:''});
  ['d','m'].forEach(p=>renderManualCards(p));
}
function renderVoCard(px){
  const inp=document.querySelector('#'+px+'-vo-card .man-url');
  const prev=$(px+'-vo-preview');
  if(!inp||!prev)return;
  const url=inp.value.trim();
  if(url&&url.startsWith('http')){
    prev.innerHTML=`<audio src="${url}" controls style="width:100%;margin-top:.5em"></audio>`;
  }else{
    prev.innerHTML=`<div class="man-card-empty" onclick="document.querySelector('#${px}-vo-card .man-url').focus()"><span style="font-size:1.5em">◎</span><span>Paste URL or upload audio</span></div>`;
  }
}
function renderCtaCard(px){
  const inp=document.querySelector('#'+px+'-cta-card .man-url');
  const prev=$(px+'-cta-preview');
  if(!inp||!prev)return;
  const url=inp.value.trim();
  if(url&&url.startsWith('http')){
    prev.innerHTML=`<video src="${url}" muted loop playsinline onmouseenter="this.play()" onmouseleave="this.pause();this.currentTime=0" ontouchstart="this.paused?this.play():this.pause()" style="width:100%;height:100%;object-fit:cover"></video>`;
  }else{
    prev.innerHTML=`<div class="man-card-empty" onclick="document.querySelector('#${px}-cta-card .man-url').focus()"><span style="font-size:1.5em">▶</span><span>End card</span></div>`;
  }
}
// Keep old name for uploadFile compat
function addClipSlot(prefix){addClipCard(prefix);}
async function probeUrl(inp){onClipUrl(inp);}
async function probeVo(inp){
  const url=inp.value.trim();
  const durSpan=inp.parentElement.querySelector('.vo-dur');
  if(!durSpan)return;
  if(!url||!url.startsWith('http')){durSpan.textContent='';updateTotals();return;}
  durSpan.textContent='⏳';durSpan.style.color='var(--blu)';
  try{
    const r=await fetch('/api/probe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    const d=await r.json();
    if(d.duration){
      const s=d.duration;
      durSpan.textContent=s>=60?Math.floor(s/60)+'m'+Math.round(s%60)+'s':Math.round(s*10)/10+'s';
      durSpan.style.color='var(--grn)';durSpan.dataset.dur=s;
    }else{durSpan.textContent='?';durSpan.style.color='var(--red)';durSpan.dataset.dur='';}
  }catch(e){durSpan.textContent='✗';durSpan.style.color='var(--red)';durSpan.dataset.dur='';}
  updateTotals();
}
function updateTotals(){
  let clipTotal=0,clipCount=0;
  manClips.forEach(c=>{if(c.dur>0){clipTotal+=c.dur;clipCount++;}});
  let voTotal=0;
  document.querySelectorAll('.vo-dur').forEach(el=>{
    const d=parseFloat(el.dataset.dur);if(d>0&&voTotal===0)voTotal=d;
  });
  ['d','m'].forEach(px=>{
    const bar=$(px+'-mtotals');
    if(!bar)return;
    if(clipCount===0&&voTotal===0){bar.style.display='none';return;}
    bar.style.display='flex';
    const fmt=s=>s>=60?Math.floor(s/60)+'m'+Math.round(s%60)+'s':Math.round(s*10)/10+'s';
    $(px+'-mt-clips').textContent='CLIPS: '+fmt(clipTotal);
    $(px+'-mt-vo').textContent=voTotal>0?'VOICE: '+fmt(voTotal):'';
    const final=voTotal>0?voTotal:clipTotal;
    $(px+'-mt-total').textContent='VIDEO: '+fmt(final);
  });
}
async function uploadFile(btn, type){
  const accept = type==='audio' ? 'audio/*,.mp3,.wav,.m4a,.flac,.ogg' : 'video/*,.mp4,.mov,.webm,.avi';
  const input = document.createElement('input');
  input.type='file';
  input.accept=accept;
  input.onchange=async function(){
    const file=input.files[0];
    if(!file)return;
    const row=btn.parentElement;
    const textInput=row.querySelector('.man-url,.mc-url,.mc-vo,.mc-cta');
    if(!textInput)return;
    const origText=btn.textContent;
    btn.textContent='⏳';
    btn.classList.add('uploading');
    try{
      const form=new FormData();
      form.append('file',file);
      const r=await fetch('/api/upload',{method:'POST',body:form});
      const d=await r.json();
      if(d.url){
        textInput.value=d.url;
        btn.textContent='✓';
        setTimeout(()=>btn.textContent=origText,2000);
        // Trigger the appropriate handler
        if(textInput.classList.contains('mc-url')){
          onClipUrl(textInput);
        }else if(textInput.classList.contains('mc-vo')){
          probeVo(textInput);
          ['d','m'].forEach(px=>renderVoCard(px));
        }else if(textInput.classList.contains('mc-cta')){
          ['d','m'].forEach(px=>renderCtaCard(px));
        }
      }else{
        textInput.value='';
        btn.textContent='✗';
        alert(d.error||'Upload failed');
        setTimeout(()=>btn.textContent=origText,2000);
      }
    }catch(e){
      textInput.value='';
      btn.textContent='✗';
      alert('Upload error: '+e.message);
      setTimeout(()=>btn.textContent=origText,2000);
    }
    btn.classList.remove('uploading');
  };
  input.click();
}
async function manualRun(){
  if(RN)return;
  // Gather clip URLs from manClips array
  const urls=manClips.filter(c=>c.url&&c.url.startsWith('http')).map(c=>c.url);
  if(!urls.length){alert('Paste at least 1 video URL');return;}
  // Gather voiceover URL (check both d and m inputs)
  let vo='';
  document.querySelectorAll('.mc-vo').forEach(inp=>{
    const v=inp.value.trim();
    if(v&&v.startsWith('http'))vo=v;
  });
  // Gather CTA clip URL
  let cta='';
  document.querySelectorAll('.mc-cta').forEach(inp=>{
    const v=inp.value.trim();
    if(v&&v.startsWith('http'))cta=v;
  });
  const body={clips:urls};
  if(vo)body.voiceover=vo;
  if(cta)body.cta_url=cta;
  const mode=vo?'FULL MANUAL (clips + voiceover)':'MANUAL (clips only)';
  if(!confirm(`Start ${mode} run?\n\n${urls.length} clip(s)${vo?'\n+ voiceover':''}${cta?'\n+ custom CTA':''}${vo?'\n\nSkips ALL AI generation (~$0.02)':''}`))return;
  const r=await fetch('/api/manual-run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  if(r.ok){RN=true;PH=0;PD=[];GATE=null;rP();poll();}
  else{alert(d.error||'Manual run failed');}
}
async function scriptOnly(){
  const btn=event.target;btn.textContent='⏳ GENERATING...';btn.disabled=true;
  try{
    const r=await fetch('/api/script-only',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});
    const d=await r.json();
    if(r.ok&&d.script){
      ['d-','m-'].forEach(px=>{
        const el=$(px+'script-result');if(el)el.classList.remove('hd');
        const t=$(px+'scr-title');if(t)t.textContent=d.topic.idea||'Script';
        const txt=$(px+'scr-text');if(txt)txt.textContent=d.script.script_full||'';
        const meta=$(px+'scr-meta');if(meta)meta.textContent=`${d.topic.category||''} · ${(d.script.script_full||'').split(' ').length} words · Tone: ${d.script.tone||'?'}`;
        // Render prompts
        const pr=$(px+'scr-prompts');
        if(pr&&d.clips&&d.clips.length){
          let ph='<div style="font-family:var(--f1);font-size:.55em;color:var(--amb);letter-spacing:.15em;margin-bottom:.4em">SCENE PROMPTS</div>';
          d.clips.forEach(c=>{
            ph+=`<div style="background:var(--bg);border:1px solid var(--bd2);padding:.6em;margin-bottom:5px">
              <div style="font-family:var(--f1);font-size:.5em;color:var(--blu);letter-spacing:.12em;margin-bottom:.3em">CLIP ${c.index}</div>
              <div style="font-size:.6em;color:var(--txtd);margin-bottom:.2em">◉️ IMAGE</div>
              <div style="font-size:.7em;color:var(--wht);line-height:1.5;margin-bottom:.4em;cursor:pointer;user-select:all" title="Click to select">${c.image_prompt}</div>
              <div style="font-size:.6em;color:var(--txtd);margin-bottom:.2em">▶ MOTION</div>
              <div style="font-size:.7em;color:var(--wht);line-height:1.5;cursor:pointer;user-select:all" title="Click to select">${c.motion_prompt}</div>
            </div>`;
          });
          pr.innerHTML=ph;
        }
      });
    }else{alert(d.error||'Script generation failed');}
  }catch(e){alert('Error: '+e);}
  btn.textContent='✎ SCRIPT ONLY';btn.disabled=false;
}
async function poll(){
  if(!RN)return;
  try{
    const r=await(await fetch('/api/status')).json();
    PH=r.phase;PD=r.phases_done||[];
    if(r.result){
      LAST_RESULT=r.result;
      GATE=r.result.gate||null;
    }
    if(!r.running){RN=false;rP();rPv();return;}
    RN=true;rP();setTimeout(poll,2000);
  }catch(e){setTimeout(poll,3000);}
}

/* ═══ TOPICS ═══ */
async function loadTopics(){
  try{
    const _tr=await(await fetch('/api/topics')).json();const topics=_tr.topics||_tr;
    const h=topics.length?topics.map(t=>`<div class="topic-row"><div style="flex:1"><div style="font-family:var(--f2);font-size:.85em;font-weight:600;color:var(--wht)">${t.idea}</div><div style="font-size:.55em;color:var(--txtd);margin-top:.05em">${t.category}${t.scripture?' · '+t.scripture:''}</div></div><div style="flex-shrink:0;margin-right:.5em">${TB(t.status||'new')}</div><div style="display:flex;gap:4px"><button class="btn-sm btn-grn" onclick="runNow('${t.id}')" title="Run pipeline with this topic">▶</button><button class="btn-sm btn-red" onclick="deleteTopic('${t.id}')" title="Delete">✕</button></div></div>`).join(''):'<div class="topic-row" style="color:var(--txtd)">No topics — seed defaults or add manually</div>';
    ['d-tl','m-tl'].forEach(id=>{if($(id))$(id).innerHTML=h;});
  }catch(e){console.error('loadTopics:',e);}
}

async function addNewTopic(){
  const idea=($('d-ti')||$('m-ti')).value.trim();
  const cat=($('d-tc')||$('m-tc')).value;
  const scr=($('d-ts')||$('m-ts')).value.trim();
  if(!idea){alert('Enter a topic idea');return;}
  await fetch('/api/topics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idea,category:cat,scripture:scr})});
  ['d-ti','m-ti','d-ts','m-ts'].forEach(id=>{if($(id))$(id).value='';});
  loadTopics();
}

async function deleteTopic(id){
  if(!confirm('Delete this topic?'))return;
  await fetch('/api/topics/'+id,{method:'DELETE'});
  loadTopics();
}

async function seedTopics(){
  if(!confirm('Seed 100 default topics?'))return;
  await fetch('/api/topics/seed',{method:'POST'});
  loadTopics();
}

async function generateTopicsAI(){
  const btn=event.target;btn.textContent='Generating...';btn.disabled=true;
  try{
    const r=await(await fetch('/api/topics/generate',{method:'POST'})).json();
    alert('Generated '+(r.count||0)+' topics');
    loadTopics();
  }catch(e){alert('Failed: '+e);}
  btn.textContent='✦ AI GENERATE';btn.disabled=false;
}

/* ═══ RUNS ═══ */
async function loadRuns(){
  try{
    const runs=await(await fetch('/api/runs')).json();
    const t=runs.length,ok=runs.filter(r=>r.status==='published'||r.status==='complete').length;
    const sh=[{l:'TOTAL',v:t,c:'amb'},{l:'SUCCESS',v:ok,c:'grn'},{l:'RATE',v:t?Math.round(ok/t*100)+'%':'—',c:'blu'},{l:'FAILED',v:t-ok,c:'red'}].map(s=>`<div class="stat"><b style="color:var(--${s.c})">${s.v}</b><small style="color:var(--${s.c})">${s.l}</small></div>`).join('');
    ['d-rs','m-rs'].forEach(id=>{if($(id))$(id).innerHTML=sh;});
    const rh=runs.length?runs.map(r=>`<div class="rw"><div style="display:flex;align-items:center;gap:.55em"><div style="flex:1"><div style="font-family:var(--f2);font-size:.85em;font-weight:600;color:var(--wht)">${r.topic||'?'}</div><div style="font-size:.55em;color:var(--txtd);margin-top:.05em;letter-spacing:.08em">${r.date} · ${r.category||''}</div></div>${B(r.status==='published'||r.status==='complete'?'done':'failed',r.status)}</div>${r.error?`<div style="font-size:.65em;color:var(--red);margin-top:.3em;background:var(--red2);padding:.2em .4em">${r.error}</div>`:''}</div>`).join(''):'<div class="rw" style="color:var(--txtd)">NO RUNS</div>';
    ['d-rl','m-rl'].forEach(id=>{if($(id))$(id).innerHTML=rh;});
  }catch(e){}
}

/* ═══ LOGS ═══ */
async function loadLogs(){
  try{
    const logs=await(await fetch('/api/logs')).json();
    const lvl={ok:'ok',error:'error',info:'info'};
    const lbl={ok:'OK',error:'ERR',info:'INFO'};
    const h=logs.length?logs.map(l=>{const lv=lvl[l.level]||'info';return `<div class="log-row lv-${l.level}"><span class="log-ts">${l.t}</span><span class="log-lv ${lv}">${lbl[lv]||'INFO'}</span><span class="log-ph">${l.phase}</span><span class="log-msg${l.level==='error'?' lv-error':''}">${l.msg}</span></div>`;}).join('')+'<div class="log-row" style="border-top:1px solid var(--bd2);margin-top:6px"><span class="log-ts" style="color:var(--txtdd)">[--:--]</span><span style="color:var(--amb);font-weight:700;letter-spacing:2px;font-size:.85em;display:flex;align-items:center;gap:6px"><span style="display:inline-block;width:5px;height:5px;background:var(--amb);border-radius:50%;animation:pulse 1.5s infinite"></span>LISTENING...</span></div>':'<div class="log-row"><span class="log-msg" style="color:var(--txtd)">No events captured.</span></div>';
    ['d-la','m-la'].forEach(id=>{if($(id))$(id).innerHTML=h;});
    if($('d-lc'))$('d-lc').textContent=logs.length+' entries';
  }catch(e){}
}

/* ═══ PREVIEW ═══ */
async function rPv(){
  try{
    const r=await(await fetch('/api/last-result')).json();
    if(!r||!r.topic)return;
    ['d-','m-'].forEach(px=>{
      if($(px+'pve'))$(px+'pve').style.display='none';
      if(r.images&&r.images.length){if($(px+'pvi'))$(px+'pvi').style.display='block';if($(px+'pig'))$(px+'pig').innerHTML=r.images.map(img=>`<div class="pcard"><img src="${img.url}" alt="S${img.index}" loading="lazy"><div class="plbl">SCENE ${img.index}</div><a class="dl" href="${img.url}" download target="_blank">⬇</a></div>`).join('');}
      if(r.videos&&r.videos.length){if($(px+'pvv'))$(px+'pvv').style.display='block';if($(px+'pvg'))$(px+'pvg').innerHTML=r.videos.map(v=>`<div class="pcard"><video src="${v.url}" muted loop playsinline onmouseenter="this.play()" onmouseleave="this.pause();this.currentTime=0"></video><div class="plbl">CLIP ${v.index}</div><a class="dl" href="${v.url}" download target="_blank">⬇</a></div>`).join('');}
      if(r.final_video){if($(px+'pvf'))$(px+'pvf').style.display='block';if($(px+'fv'))$(px+'fv').src=r.final_video;if($(px+'fd'))$(px+'fd').href=r.final_video;}
      if(r.script){if($(px+'pvs'))$(px+'pvs').style.display='block';if($(px+'pst'))$(px+'pst').textContent=typeof r.script==='string'?r.script:(r.script.script_full||'');}
    });
  }catch(e){}
}

/* ═══ SETTINGS ═══ */
function getModels(fk){const prov=fk==='image_model'?(ST.image_provider||'replicate'):(ST.video_provider||'replicate');const cat=fk==='image_model'?IMG_MODELS:VID_MODELS;return cat[prov]||[];}

function rSt(){
  let h='';
  STS.forEach((sec,si)=>{
    let ff='';
    sec.f.forEach(f=>{try{
      const v=ST[f.k]!==undefined?ST[f.k]:f.d;
      if(f.tp==='toggle'){
        const on=v===true||v==='true';
        ff+=`<div class="fi w" style="display:flex;align-items:center;justify-content:space-between"><div style="font-size:.9em;color:var(--wht)">${f.l}</div><button class="tg ${on?'on':'off'}" onclick="event.stopPropagation();ST['${f.k}']=!(ST['${f.k}']===true||ST['${f.k}']==='true');rSt()"><span class="td"></span></button></div>`;
      }else if(f.tp==='select'){
        let opts=f.o;
        if(f.dynamic&&SCENE_DATA){
          // Build options from brand scene data
          opts=["auto"];
          if(f.dynamic==='stories'&&SCENE_DATA.stories){
            SCENE_DATA.stories.forEach(s=>opts.push(s.name+' — '+s.mood));
          }else if(f.dynamic==='themes'&&SCENE_DATA.themes){
            Object.keys(SCENE_DATA.themes).forEach(t=>opts.push(t));
          }else if(f.dynamic==='figures'&&SCENE_DATA.figures){
            SCENE_DATA.figures.forEach((fig,i)=>opts.push(fig.substring(0,60)));
          }else if(f.dynamic==='moods'&&SCENE_DATA.moods){
            Object.keys(SCENE_DATA.moods).forEach(m=>opts.push(m));
          }
          ff+=`<div class="fi"><div class="fl">${f.l}</div><select class="fin" onchange="ST['${f.k}']=this.value">${opts.map(o=>`<option${o==v?' selected':''}>${o}</option>`).join('')}</select></div>`;
        }else if(f.dep){
          opts=getModels(f.k);
          ff+=`<div class="fi"><div class="fl">${f.l}</div><select class="fin" onchange="ST['${f.k}']=this.value">${opts.map(o=>`<option value="${o.v}"${o.v==v?' selected':''}>${o.l}</option>`).join('')}</select></div>`;
        }else if(f.k==='image_provider'||f.k==='video_provider'||f.k==='clip_count'||f.k==='clip_duration'){
          ff+=`<div class="fi"><div class="fl">${f.l}</div><select class="fin" onchange="ST['${f.k}']=this.value;rSt()">${opts.map(o=>`<option${o==v?' selected':''}>${o}</option>`).join('')}</select></div>`;
        }else{
          ff+=`<div class="fi"><div class="fl">${f.l}</div><select class="fin" onchange="ST['${f.k}']=this.value">${opts.map(o=>`<option${o==v?' selected':''}>${o}</option>`).join('')}</select></div>`;
        }
      }else if(f.tp==='computed'){
        const clips=parseInt(ST.clip_count)||3,dur=parseInt(ST.clip_duration)||10,clipTot=clips*dur;
        const words=parseInt(ST.script_words)||90,voEst=Math.round(words/3);
        const ctaOn=ST.cta_enabled===true||ST.cta_enabled==='true';
        const ctaDur=ctaOn?parseFloat(ST.cta_duration||4):0;
        const finalDur=Math.max(voEst,clipTot)+ctaDur+1;
        const overflow=voEst-clipTot;
        let status,sc;
        if(overflow>dur){status='⚠ Voice overflows clips by '+overflow+'s — consider adding a clip';sc='var(--red)';}
        else if(overflow>3){status='⚠ CTA will stretch ~'+overflow+'s to cover voice';sc='var(--amb)';}
        else if(overflow<-10){status='ℹ Clips extend '+Math.abs(overflow)+'s past voice — last frame holds';sc='var(--amb)';}
        else{status='✓ Well matched';sc='var(--grn)';}
        ff+=`<div class="fi w" style="border:1px solid var(--bd2);padding:10px;background:var(--amblo)">
<div style="font-family:var(--f1);font-size:.6em;letter-spacing:.15em;color:var(--txtd);margin-bottom:6px">TIMING BREAKDOWN</div>
<div style="display:flex;gap:8px;margin-bottom:6px">
<div style="flex:1;padding:5px;background:var(--bg);border:1px solid var(--bd2);text-align:center"><div style="font-family:var(--f1);font-size:.9em;font-weight:800;color:var(--amb)">${clipTot}s</div><div style="font-size:.5em;color:var(--txtdd);letter-spacing:.1em">CLIPS ${clips}×${dur}s</div></div>
<div style="flex:1;padding:5px;background:var(--bg);border:1px solid var(--bd2);text-align:center"><div style="font-family:var(--f1);font-size:.9em;font-weight:800;color:var(--blu)">${voEst}s</div><div style="font-size:.5em;color:var(--txtdd);letter-spacing:.1em">VOICE ~${words}w</div></div>
${ctaDur>0?`<div style="flex:1;padding:5px;background:var(--bg);border:1px solid var(--bd2);text-align:center"><div style="font-family:var(--f1);font-size:.9em;font-weight:800;color:var(--txtd)">${ctaDur}s</div><div style="font-size:.5em;color:var(--txtdd);letter-spacing:.1em">CTA</div></div>`:''}
<div style="flex:1;padding:5px;background:var(--bg);border:1px solid var(--grn);text-align:center"><div style="font-family:var(--f1);font-size:.9em;font-weight:800;color:var(--grn)">~${Math.round(finalDur)}s</div><div style="font-size:.5em;color:var(--txtdd);letter-spacing:.1em">FINAL</div></div>
</div>
<div style="font-size:.55em;color:${sc}">${status}</div>
<div style="font-size:.45em;color:var(--txtdd);margin-top:3px">Voice dictates length. Clips play naturally, CTA stretches if needed.</div>
</div>`;
      }else if(f.tp==='slider'){
        const mn=f.min||30,mx=f.max||180,stp=f.step||5,cv=parseInt(v)||f.d,secs=Math.round(cv/3),pct=((cv-mn)/(mx-mn))*100;
        ff+=`<div class="fi w"><div class="fl">${f.l}</div><div style="display:flex;align-items:center;gap:.55em"><input type="range" min="${mn}" max="${mx}" step="${stp}" value="${cv}" class="fin-slider" style="flex:1" oninput="ST['${f.k}']=parseInt(this.value);document.getElementById('sl_${f.k}').textContent=this.value+' words ≈ '+Math.round(this.value/3)+'s'" onchange="ST['${f.k}']=parseInt(this.value);document.getElementById('sl_${f.k}').textContent=this.value+' words ≈ '+Math.round(this.value/3)+'s'" ontouchmove="ST['${f.k}']=parseInt(this.value);document.getElementById('sl_${f.k}').textContent=this.value+' words ≈ '+Math.round(this.value/3)+'s'"><div id="sl_${f.k}" style="min-width:6em;font-family:var(--f1);font-size:.65em;letter-spacing:1px;color:var(--amb);text-align:right">${cv} words ≈ ${secs}s</div></div></div>`;
      }else if(f.tp==='scene_pack'){
        const src=SCENE_DATA?'Brand':'Default (Knights)';
        const sc=SCENE_DATA&&SCENE_DATA._source==='brand'?'var(--grn)':'var(--txtd)';
        const nStories=SCENE_DATA?SCENE_DATA.stories.length:0;
        const nFigs=SCENE_DATA?SCENE_DATA.figures.length:0;
        const nMoods=SCENE_DATA?Object.keys(SCENE_DATA.moods).length:0;
        ff+=`<div class="fi w" style="border:1px solid var(--bd2);padding:10px;background:var(--amblo)">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
<div style="font-family:var(--f1);font-size:.6em;letter-spacing:.15em;color:var(--txtd)">SCENE PACK</div>
<span style="font-size:.55em;color:${sc};letter-spacing:.08em">${src.toUpperCase()}</span>
</div>
<div style="display:flex;gap:6px;margin-bottom:8px">
<div style="flex:1;padding:4px;background:var(--bg);border:1px solid var(--bd2);text-align:center"><div style="font-family:var(--f1);font-size:.85em;font-weight:800;color:var(--amb)">${nStories}</div><div style="font-size:.45em;color:var(--txtdd);letter-spacing:.08em">STORIES</div></div>
<div style="flex:1;padding:4px;background:var(--bg);border:1px solid var(--bd2);text-align:center"><div style="font-family:var(--f1);font-size:.85em;font-weight:800;color:var(--amb)">${nFigs}</div><div style="font-size:.45em;color:var(--txtdd);letter-spacing:.08em">FIGURES</div></div>
<div style="flex:1;padding:4px;background:var(--bg);border:1px solid var(--bd2);text-align:center"><div style="font-family:var(--f1);font-size:.85em;font-weight:800;color:var(--amb)">${nMoods}</div><div style="font-size:.45em;color:var(--txtdd);letter-spacing:.08em">MOODS</div></div>
</div>
<div style="display:flex;gap:6px">
<button style="flex:1;padding:6px;background:var(--bg);border:1px solid var(--bd2);color:var(--amb);font-size:.6em;font-family:var(--f1);letter-spacing:.1em;cursor:pointer" onclick="editScenePack()">✎ EDIT JSON</button>
<button style="flex:1;padding:6px;background:var(--bg);border:1px solid var(--bd2);color:var(--txtd);font-size:.6em;font-family:var(--f1);letter-spacing:.1em;cursor:pointer" onclick="seedDefaults()">⬇ SEED DEFAULTS</button>
</div>
</div>`;
      }else if(f.tp==='textarea'){
        ff+=`<div class="fi w"><div class="fl">${f.l}</div><textarea class="fin" rows="3" style="resize:vertical;min-height:3em" onchange="ST['${f.k}']=this.value">${v||''}</textarea></div>`;
      }else{
        ff+=`<div class="fi"><div class="fl">${f.l}</div><input class="fin" value="${v||''}" onchange="ST['${f.k}']=this.value"></div>`;
      }
    }catch(e){console.error('CFG:',f.k,e);}});
    h+=`<div class="sec"><button class="sec-h" onclick="stOpen[${si}]=!stOpen[${si}];rSt()"><span class="sec-t">${sec.t}</span><span class="sec-a" style="transform:${stOpen[si]?'rotate(90deg)':''}">›</span></button><div class="sec-b${stOpen[si]?'':' shut'}">${ff}</div></div>`;
  });
  ['d-sf','m-sf'].forEach(id=>{if($(id))$(id).innerHTML=h;});
}

async function saveSett(){
  await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(ST)});
  ['d-ss','m-ss'].forEach(id=>{if($(id)){$(id).style.display='block';setTimeout(()=>$(id).style.display='none',3000);}});
}

/* ═══ HEALTH ═══ */
async function rH(){
  try{
    const cfg=await(await fetch('/api/config')).json();
    const h='<div class="rw"><span style="font-family:var(--f1);font-size:.6em;color:var(--txtd);letter-spacing:.2em">API CONNECTIONS</span></div>'+SVCS.map(s=>`<div class="rw" style="display:flex;justify-content:space-between;align-items:center"><div><div style="font-family:var(--f1);font-size:.7em;font-weight:600;letter-spacing:.15em;color:var(--wht)">${s.n}</div><div style="font-size:.55em;color:var(--txtd);margin-top:.05em">${s.d}</div></div>${B(cfg[s.k]?'configured':'missing')}</div>`).join('');
    ['d-hl','m-hl'].forEach(id=>{if($(id))$(id).innerHTML=h;});
  }catch(e){}
}
async function testAll(){
  alert('Testing connections...');
  for(const s of['openai','replicate','elevenlabs']){
    try{await(await fetch('/api/test-connection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service:s})})).json();}catch(e){}
  }
  rH();alert('Done!');
}

/* ═══ SCENE PACK ═══ */
async function loadSceneData(){
  try{
    const r=await(await fetch('/api/scenes')).json();
    SCENE_DATA=r.data||null;
    if(SCENE_DATA)SCENE_DATA._source=r.source;
  }catch(e){SCENE_DATA=null;}
}

async function seedDefaults(){
  if(!confirm('Copy knight default scenes into this brand? This will overwrite any existing brand scenes.'))return;
  try{
    await fetch('/api/scenes/seed-defaults',{method:'POST'});
    await loadSceneData();
    rSt();
    alert('Knight defaults seeded into this brand. You can now edit them.');
  }catch(e){alert('Failed: '+e);}
}

function editScenePack(){
  // Open scene JSON editor in a modal-style overlay
  const json=JSON.stringify(SCENE_DATA||{},null,2);
  const el=document.createElement('div');
  el.id='scene-editor-overlay';
  el.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.85);z-index:9999;display:flex;flex-direction:column;padding:12px';
  el.innerHTML=`
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
<span style="font-family:var(--f1);font-size:.7em;color:var(--amb);letter-spacing:.15em">SCENE PACK EDITOR</span>
<div style="display:flex;gap:6px">
<button onclick="saveScenePack()" style="padding:6px 14px;background:var(--amb);color:var(--bg);border:none;font-family:var(--f1);font-size:.6em;letter-spacing:.15em;cursor:pointer">SAVE</button>
<button onclick="document.getElementById('scene-editor-overlay').remove()" style="padding:6px 14px;background:var(--bg3);color:var(--red);border:1px solid rgba(255,0,60,.2);font-family:var(--f1);font-size:.6em;letter-spacing:.15em;cursor:pointer">CLOSE</button>
</div>
</div>
<div style="font-size:.55em;color:var(--txtd);margin-bottom:8px">Edit figures, stories, themes, moods. Each story needs: name, themes[], mood, clips[] with 8 fields each.</div>
<textarea id="scene-json-editor" style="flex:1;width:100%;background:var(--bg);color:var(--amb);border:1px solid var(--bd);font-family:var(--f3);font-size:.75em;padding:10px;resize:none;outline:none;tab-size:2">${escHtml(json)}</textarea>
<div id="scene-editor-status" style="font-size:.6em;color:var(--txtd);margin-top:6px"></div>`;
  document.body.appendChild(el);
  // Tab key support in textarea
  const ta=document.getElementById('scene-json-editor');
  ta.addEventListener('keydown',function(e){
    if(e.key==='Tab'){e.preventDefault();const s=this.selectionStart,end=this.selectionEnd;this.value=this.value.substring(0,s)+'  '+this.value.substring(end);this.selectionStart=this.selectionEnd=s+2;}
  });
}

function escHtml(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

async function saveScenePack(){
  const ta=document.getElementById('scene-json-editor');
  const st=document.getElementById('scene-editor-status');
  let data;
  try{data=JSON.parse(ta.value);}catch(e){st.style.color='var(--red)';st.textContent='Invalid JSON: '+e.message;return;}
  // Validate structure
  if(!data.stories||!Array.isArray(data.stories)){st.style.color='var(--red)';st.textContent='Missing "stories" array';return;}
  if(!data.figures||!Array.isArray(data.figures)){st.style.color='var(--red)';st.textContent='Missing "figures" array';return;}
  try{
    await fetch('/api/scenes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    st.style.color='var(--grn)';st.textContent='✓ Saved — '+data.stories.length+' stories, '+data.figures.length+' figures';
    await loadSceneData();
    rSt();
  }catch(e){st.style.color='var(--red)';st.textContent='Save failed: '+e;}
}

/* ═══ INIT ═══ */
/* BRANDS */
let BRANDS=[],ACTIVE_BRAND='knights';
async function loadBrands(){
  try{
    const r=await(await fetch('/api/brands')).json();
    BRANDS=r.brands||[];ACTIVE_BRAND=r.active||'knights';
    ['d-brand-sel','m-brand-sel'].forEach(id=>{
      const sel=$(id);if(!sel)return;
      sel.innerHTML=BRANDS.map(b=>`<option value="${b.id}"${b.id===ACTIVE_BRAND?' selected':''}>${b.display_name}</option>`).join('')
        +`<option value="__new__">+ New Brand...</option>`;
    });
    const ab=BRANDS.find(b=>b.id===ACTIVE_BRAND);
    const dn=ab?ab.display_name:'CONTENT REACTOR';
    const parts=dn.toUpperCase().split(' ');
    if($('d-brand-title'))$('d-brand-title').innerHTML=parts.length>1?parts.slice(0,-1).join(' ')+'<br>'+parts[parts.length-1]:dn;
    if($('m-brand-title'))$('m-brand-title').textContent=dn.toUpperCase();
    // Show delete button only for non-default brands
    const canDel=ACTIVE_BRAND!=='knights';
    ['d-brand-del','m-brand-del'].forEach(id=>{if($(id))$(id).style.display=canDel?'block':'none';});
  }catch(e){console.error('loadBrands:',e);}
}
async function deleteBrand(){
  if(ACTIVE_BRAND==='knights'){alert('Cannot delete the default brand.');return;}
  const ab=BRANDS.find(b=>b.id===ACTIVE_BRAND);
  const name=ab?ab.display_name:ACTIVE_BRAND;
  const toDelete=ACTIVE_BRAND;
  if(!confirm(`Delete brand "${name}"?\n\nThis removes all settings, runs, and scene data for this brand. This cannot be undone.`))return;
  // Switch to knights first (backend won't delete active brand)
  await fetch('/api/brands/switch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({brand:'knights'})});
  // Now delete
  const r=await fetch('/api/brands/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({brand:toDelete})});
  const d=await r.json();
  if(!r.ok){alert(d.error||'Delete failed');return;}
  await loadBrands();await init();loadTopics();loadRuns();
}
async function switchBrand(val){
  let isNew=false;
  if(val==='__new__'){
    const name=prompt('New brand name:');
    if(!name){loadBrands();return;}
    const r=await fetch('/api/brands/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,display_name:name})});
    const d=await r.json();
    if(!r.ok){alert(d.error||'Failed');loadBrands();return;}
    val=d.brand;isNew=true;
  }
  await fetch('/api/brands/switch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({brand:val})});
  await loadBrands();
  await init();
  // Blank brand-specific fields for NEW brands so user knows what to fill in
  if(isNew){STS.forEach(s=>s.f.forEach(f=>{if(f.b)ST[f.k]=f.k==='brand_name'?val.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase()):''}));rSt();}
  loadTopics();
  loadRuns();
}

// ─── CHANNELS ────────────────────────────────────────────────
const CH_FIELDS=['instagram','facebook','facebook-page','twitter','threads','tiktok','youtube','pinterest','pinterest-board'];
async function loadChannels(){
  try{
    const r=await(await fetch('/api/channels')).json();
    CH_FIELDS.forEach(k=>{
      const val=r[k.replace(/-/g,'_')]||'';
      const d=$('ch-'+k);if(d)d.value=val;
      const m=$('mch-'+k);if(m)m.value=val;
    });
    ['ch-status','mch-status'].forEach(id=>{if($(id))$(id).innerHTML='<span style="color:var(--grn)">✓ Loaded</span>';});
  }catch(e){['ch-status','mch-status'].forEach(id=>{if($(id))$(id).innerHTML=`<span style="color:var(--red)">Error: ${e}</span>`;});}
}
async function saveChannels(){
  const body={};
  CH_FIELDS.forEach(k=>{
    const d=$('ch-'+k);const m=$('mch-'+k);
    body[k.replace(/-/g,'_')]=(d&&d.value?d.value:m&&m.value?m.value:'').trim();
  });
  try{
    await fetch('/api/channels',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    ['ch-status','mch-status'].forEach(id=>{if($(id))$(id).innerHTML='<span style="color:var(--grn)">✓ Channels saved!</span>';});
  }catch(e){['ch-status','mch-status'].forEach(id=>{if($(id))$(id).innerHTML=`<span style="color:var(--red)">Error: ${e}</span>`;});}
}

async function init(){
  rP();updThemeBtn();
  await loadBrands();
  ['d','m'].forEach(px=>renderManualCards(px)); // Init manual clip cards
  try{
    const r=await(await fetch('/api/settings')).json();
    STS.forEach(s=>s.f.forEach(f=>{if(r[f.k]!==undefined)ST[f.k]=r[f.k];else ST[f.k]=f.d;}));
  }catch(e){STS.forEach(s=>s.f.forEach(f=>ST[f.k]=f.d));}
  await loadSceneData();
  rSt();
  try{
    const r=await(await fetch('/api/status')).json();
    if(r.result){
      LAST_RESULT=r.result;
      GATE=r.result.gate||null;
      PD=r.phases_done||[];
    }
    if(r.running){RN=true;PH=r.phase;PD=r.phases_done||[];rP();poll();}
    else{rP();}
  }catch(e){}
}
autoLogin();
