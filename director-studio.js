/* Knights Reactor — Director Studio (review build)
   Uses existing FastAPI endpoints; never calls paid generation on page load.
   The classic dashboard remains the source of technical configuration. */
"use strict";
const $=id=>document.getElementById(id);
const state={settings:{},topics:[],scenePack:{},story:null,runs:[],plan:null,status:null,
  gate:null,clips:[],runTopic:null,activeTab:"story",mode:"standalone",busy:false,initialized:false};
const saveKeys=["creative_direction","video_length_target","scene_pacing","target_clips","scene_figure",
  "music_enabled","music_style","music_volume","sfx_enabled"];
const esc=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const asBool=x=>x===true||x==="true"||x==="True";
function toast(message,error=false){const el=$("toast");el.textContent=message;el.style.display="block";el.style.background=error?"#c6827b":"#e0c28a";clearTimeout(toast.t);toast.t=setTimeout(()=>el.style.display="none",4800);}
async function api(path,options={}){
  const res=await fetch(path,{credentials:"same-origin",...options});
  const data=await res.json().catch(()=>({}));
  if(!res.ok)throw new Error(data.error||data.detail||"Request failed ("+res.status+")");
  return data;
}
function post(path,body={}){return api(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});}
function confirmAction(title,description){
  return new Promise(resolve=>{
    const dialog=$("confirm-dialog");$("confirm-title").textContent=title;$("confirm-text").textContent=description;
    const yes=$("confirm-yes"),no=$("confirm-no");
    const finish=value=>{dialog.close();yes.removeEventListener("click",accepted);no.removeEventListener("click",declined);dialog.removeEventListener("cancel",cancelled);resolve(value);};
    const accepted=()=>finish(true),declined=()=>finish(false),cancelled=e=>{e.preventDefault();finish(false);};
    yes.addEventListener("click",accepted);no.addEventListener("click",declined);dialog.addEventListener("cancel",cancelled);dialog.showModal();
  });
}
function showView(view){
  for(const name of ["create","library","productions","setup"]) $("view-"+name).classList.toggle("hidden",name!==view);
  document.querySelectorAll(".nav-btn[data-view]").forEach(b=>b.classList.toggle("on",b.dataset.view===view));
  $("header-caption").textContent=({create:"CREATE / DIRECTOR STUDIO",library:"LIBRARY / CAST & SERIES",productions:"PRODUCTIONS / RUN HISTORY",setup:"SYSTEM / SETUP"})[view];
  if(view==="productions")loadRuns().catch(e=>toast(e.message,true));
}
function showTab(tab){
  state.activeTab=tab;
  for(const name of ["story","continuity","timeline"])$(name+"-panel").classList.toggle("hidden",name!==tab);
  document.querySelectorAll(".step").forEach(b=>b.classList.toggle("active",b.dataset.tab===tab));
}
function figures(){
  return (state.scenePack.figures||[]).map((f,i)=>typeof f==="string"?{name:"Knight "+(i+1),desc:f,ref_image:""}:{name:f.name||"Knight "+(i+1),desc:f.desc||f.description||"",ref_image:f.ref_image||""});
}
function selectedFigure(){
  const name=$("knight-select").value;
  return figures().find(f=>f.name===name)||figures()[0]||null;
}
function selectedTopic(){
  const id=$("topic-select").value;
  return state.topics.find(t=>t.id===id)||null;
}
function formatName(f){return f?f.name||"Unnamed knight":"No cast configured";}
function isSeries(t){return !!(t.episode&&t.episode.code);}
function renderCast(){
  const fs=figures(),current=state.settings.scene_figure||"auto";
  $("knight-select").innerHTML='<option value="auto">Auto-select character</option>'+fs.map(f=>'<option value="'+esc(f.name)+'">'+esc(f.name)+'</option>').join("");
  $("knight-select").value=fs.some(f=>f.name===current)?current:"auto";
  let f=selectedFigure();$("knight-name").textContent=$("knight-select").value==="auto"?"AI chooses the knight":formatName(f);
  $("knight-desc").textContent=f?f.desc:"Add cast members in Classic Visual Director.";
  const frame=$("reference-picture");frame.querySelector("img")?.remove();
  frame.querySelector(".no-image")?.remove();
  if(f&&f.ref_image){
    const img=new Image();img.alt="Reference portrait for "+f.name;img.src=f.ref_image;img.onerror=()=>{img.remove();};frame.prepend(img);
    $("reference-stamp").textContent="REFERENCE UPLOADED";
  }else{
    const placeholder=document.createElement("span");placeholder.className="no-image";placeholder.textContent="♜";frame.prepend(placeholder);
    $("reference-stamp").textContent="REFERENCE NOT UPLOADED";
  }
  $("cast-list").innerHTML=fs.length?fs.map(f=>'<div class="field"><div class="inline">'+
    (f.ref_image?'<img alt="" src="'+esc(f.ref_image)+'" style="width:52px;height:65px;object-fit:cover;border-radius:6px">':'<span class="no-image" style="font-size:31px">♜</span>')+
    '<div><strong>'+esc(f.name)+'</strong><p>'+esc(f.desc)+'</p></div></div></div>').join(""):'<div class="status warn">No knight cast is configured.</div>';
}
function renderTopics(){
  const old=$("topic-select").value;
  const eligible=state.topics.filter(t=>t.status==="new"&&(state.mode==="series"?isSeries(t):!isSeries(t)));
  $("topic-select").innerHTML='<option value="">Next available '+(state.mode==="series"?"episode":"topic")+'</option>'+
    eligible.map(t=>'<option value="'+esc(t.id)+'">'+esc(t.idea)+'</option>').join("");
  if(eligible.some(t=>t.id===old))$("topic-select").value=old;
  if(!eligible.length)$("topic-select").innerHTML='<option value="">No new '+(state.mode==="series"?"episodes — queue them in Library":"topics — add in Classic Topics")+'</option>';
  const series=state.story||{};
  const episodes=series.episodes||[];
  $("series-library").innerHTML='<div class="status">'+esc(series.title||"The Last Watch")+' · '+episodes.length+' episode'+(episodes.length!==1?"s":"")+'</div>'+
    '<div class="stack">'+episodes.slice(0,12).map(ep=>'<div class="field"><strong>'+esc(ep.code||"Episode")+' — '+esc(ep.title||"Untitled")+'</strong><p>'+esc(ep.knight||ep.summary||"")+'</p></div>').join("")+'</div>';
}
function syncFields(){
  $("creative-brief").value=state.settings.creative_direction||"";
  $("duration-target").value=String(state.settings.video_length_target??"0");
  $("scene-pacing").value=state.settings.scene_pacing||"auto";
  $("target-clips").value=String(state.settings.target_clips||6);
  $("target-clips-label").textContent=$("target-clips").value;
  $("manual-clips-row").classList.toggle("hidden",$("scene-pacing").value!=="manual");
  $("music-enabled").checked=asBool(state.settings.music_enabled);
  $("music-style").value=state.settings.music_style||"";
  $("sfx-enabled").checked=asBool(state.settings.sfx_enabled);
  $("music-volume").value=Math.round(Number(state.settings.music_volume??.18)*100);
  $("music-value").textContent=$("music-volume").value+"%";
}
function collectFields(){
  const s=state.settings;
  s.creative_direction=$("creative-brief").value.slice(0,3000);
  s.video_length_target=$("duration-target").value;
  s.scene_pacing=$("scene-pacing").value;
  s.target_clips=Number($("target-clips").value);
  s.scene_figure=$("knight-select").value;
  s.music_enabled=$("music-enabled").checked;
  s.music_style=$("music-style").value.slice(0,1000);
  s.sfx_enabled=$("sfx-enabled").checked;
  s.music_volume=(Number($("music-volume").value)/100).toFixed(2);
  return s;
}
async function saveDirection(silent=false){
  collectFields();
  await post("/api/settings",state.settings);
  if(!silent)toast("Creative direction saved");
  await refreshEstimate();
}
async function refreshEstimate(){
  try{
    const plan=await api("/api/plan-estimate");state.plan=plan;
    if(!state.status?.running&&!state.gate)renderPlan(plan);
  }catch(e){$("plan-status").textContent="Estimate unavailable: "+e.message;}
}
function renderPlan(p){
  if(!p)return;
  const cost=p.cost||{},missing=(cost.missing||[]).length;
  $("metric-shots").textContent=p.clips||"—";
  $("metric-secs").textContent=Math.round(p.video_seconds||0)+"s";
  $("metric-cost").textContent=cost.total==null?"—":"≈$"+Number(cost.total).toFixed(2)+(missing?"+":"");
  const lengths=(p.scene_seconds||[]).map(x=>Number(x).toFixed(1)+"s").join(" · ");
  const details=(p.target_clips!=null?"Manual target "+p.target_clips+" → "+p.clips+" feasible clips. ":"")+
    "Narration ≈"+Math.round(p.narration_seconds||0)+"s"+(p.cta_seconds?" + "+p.cta_seconds+"s end card":"")+
    ". Shot lengths: "+lengths+". Cost includes known images, video footage and estimated writing; excludes voice, music and Shotstack.";
  $("plan-status").textContent=details;
  $("plan-status").className="status warn";
}
function renderState(){
  const status=state.status||{};
  const result=status.result||{};
  const gate=result.gate||null;
  state.gate=gate;
  const label=gate==="prompts"?"Review scene prompts":gate==="images"?"Review starting images":gate==="videos"?"Review generated video clips":status.running?"Generating — "+(status.phase_name||"processing"):result.final_video?"Final video ready":result.error?"Failed — "+result.error:"Ready to direct";
  $("production-state").className="status"+(result.error?" bad":status.running?" warn":"");
  $("production-state").textContent=label;
  $("system-dot").style.background=result.error?"var(--red)":status.running?"var(--gold)":"var(--green)";
  $("system-label").textContent=label.toUpperCase().slice(0,58);
  if(result.plan)renderPlan(result.plan);
  if(gate)$("gate-message").textContent=label+" · Edit or approve before proceeding.";
  if(result.final_video){
    $("final-media").classList.remove("hidden");
    $("final-media video").src=result.final_video;$("final-download").href=result.final_video;
  }else $("final-media").classList.add("hidden");
  const btn=$("start-run");
  btn.disabled=!!status.running||!!gate||state.busy;
  btn.textContent=status.running?"⏳ GENERATING":gate?"REVIEW IN PROGRESS":"▶ START PRODUCTION";
}
async function refreshStatus(){
  state.status=await api("/api/status");renderState();
  if(state.gate){
    const endpoint=({prompts:"/api/prompts",images:"/api/images/review",videos:"/api/videos/review"})[state.gate];
    if(endpoint){
      const data=await api(endpoint);
      state.clips=data.clips||[];
      renderShots();
      if(state.gate==="prompts"||state.gate==="images")showTab("continuity");
      else showTab("timeline");
    }
  }else if(state.status.result?.clips){state.clips=state.status.result.clips;renderShots();}
}
function shotMedia(c){
  if(state.gate==="videos"&&(c.video_url||c.r2_url))return '<video controls preload="metadata" style="width:100%;height:100%;object-fit:cover" src="'+esc(c.video_url||c.r2_url)+'"></video>';
  if(c.image_url)return '<img loading="lazy" src="'+esc(c.image_url)+'" alt="Generated shot '+esc(c.index)+'">';
  return '<span style="font-size:48px;color:#9b8462">♜</span>';
}
function renderShots(){
  const gate=state.gate;
  $("gate-message").textContent=gate?({
    prompts:"Read the scene direction. Save edits and approve to start image generation.",
    images:"Check character identity and composition in every still before starting paid video generation.",
    videos:"Review each generated clip. Final approval will resume render AND may publish to your social channels."
  })[gate]:"Shot previews become available after the Scene Engine runs.";
  $("approve-stage").disabled=!gate||!state.clips.length||state.busy;
  $("approve-stage").textContent=gate==="prompts"?"APPROVE PROMPTS → IMAGES":gate==="images"?"APPROVE IMAGES → VIDEO":gate==="videos"?"APPROVE VIDEO → RENDER / PUBLISH":"AWAITING SHOTS";
  $("shot-grid").innerHTML=state.clips.length?state.clips.map((c,i)=>'<article class="shot">'+
    '<div class="shot-image">'+shotMedia(c)+'</div><div class="shot-bd"><div class="sectionbar"><h3>SHOT '+esc(c.index||i+1)+'</h3><span class="tag">'+esc(c.length?Number(c.length).toFixed(1)+"s":"PLANNED")+'</span></div>'+
    '<div class="small">'+esc(c.scene_source||c.scene_concept||"Narration-aligned shot")+'</div>'+
    '<label class="small" for="shot-image-'+i+'">IMAGE PROMPT</label><textarea class="inputarea" id="shot-image-'+i+'" data-field="image_prompt" data-index="'+i+'" '+(gate==="videos"?"readonly":"")+'>'+esc(c.image_prompt||"")+'</textarea>'+
    '<label class="small" for="shot-motion-'+i+'">MOTION PROMPT</label><textarea class="inputarea" id="shot-motion-'+i+'" data-field="motion_prompt" data-index="'+i+'" '+(gate!=="prompts"?"readonly":"")+'>'+esc(c.motion_prompt||"")+'</textarea>'+
    '<div class="shot-tools">'+(gate==="images"?'<button class="btn tiny" data-regen-image="'+i+'">↻ REGENERATE IMAGE (PAID)</button>':"")+
    (gate==="videos"?'<button class="btn tiny" data-regen-video="'+i+'">↻ REGENERATE CLIP (PAID)</button>':"")+
    '</div></div></article>').join(""):'<div class="note">No generated shots yet. The AI director creates them after voiceover timing is available.</div>';
  $("video-track").innerHTML=(state.clips||[]).map((c,i)=>'<div class="segment video">SHOT '+(i+1)+'</div>').join("")||'<div class="segment video">AWAITING SHOTS</div>';
}
function updateLocalClipInputs(){
  document.querySelectorAll("[data-field][data-index]").forEach(el=>{
    const c=state.clips[Number(el.dataset.index)];
    if(c)c[el.dataset.field]=el.value;
  });
}
async function startProduction(){
  if(state.status?.running||state.gate)return toast("Finish or cancel the current run in Classic Editor first",true);
  collectFields();
  const topic=selectedTopic();
  if(!state.topics.some(t=>t.status==="new"&&(state.mode==="series"?isSeries(t):!isSeries(t))))return toast("No new topics in this mode. Add or queue one first.",true);
  if(!await confirmAction("Start paid production?",
    "This will generate a script, narration, scene prompts and then pause for approval. Later approval gates trigger paid images/videos. The existing final phase may auto-publish when approved."))return;
  state.busy=true;renderState();
  try{
    await saveDirection(true);
    const data=await post("/api/run",{production_mode:state.mode,...(topic?{topic_id:topic.id}:{})});
    toast("Production started. Waiting for the storyboard gate.");
    state.status={running:true,phase_name:"Starting",result:null};renderState();
    poll();
  }catch(e){toast("Could not start production: "+e.message,true);}
  finally{state.busy=false;renderState();}
}
let polling=false;
async function poll(){
  if(polling)return;
  polling=true;
  try{
    for(let i=0;i<75;i++){
      await refreshStatus();
      if(!state.status.running)break;
      await new Promise(r=>setTimeout(r,3500));
    }
  }catch(e){toast("Status check failed: "+e.message,true);}
  finally{polling=false;}
}
async function advanceGate(){
  const gate=state.gate;
  if(!gate||!state.clips.length)return;
  updateLocalClipInputs();
  const next={prompts:"generate AI starting images",images:"generate paid video clips",videos:"render the final video and possibly AUTOMATICALLY PUBLISH to configured platforms"}[gate];
  if(!await confirmAction("Approve this production stage?","Continue to "+next+". Review every shot carefully; provider generation can incur charges."))return;
  state.busy=true;renderState();
  try{
    if(gate==="prompts")await post("/api/prompts/save",{clips:state.clips.map(c=>({index:c.index,image_prompt:c.image_prompt,motion_prompt:c.motion_prompt}))});
    if(gate==="images")await post("/api/images/approve",{clips:state.clips});
    if(gate==="videos")await post("/api/videos/approve",{clips:state.clips});
    await post("/api/resume");
    toast("Approved. Continuing production.");
    state.gate=null;state.clips=[];state.status={running:true,phase_name:"Resuming",result:null};
    renderShots();renderState();poll();
  }catch(e){toast("Approval failed: "+e.message,true);}
  finally{state.busy=false;renderState();}
}
async function regen(kind,i){
  const c=state.clips[i];
  if(!c)return;
  updateLocalClipInputs();
  if(!await confirmAction("Regenerate this "+kind+"?","Recreating shot "+c.index+" costs provider credits and replaces the currently selected "+kind+"."))return;
  state.busy=true;renderState();
  try{
    const data=await post("/api/"+kind+"s/regen",{index:c.index,...(kind==="image"?{image_prompt:c.image_prompt}:{})});
    if(data.clip)state.clips[i]=data.clip;
    renderShots();toast("Shot "+c.index+" regenerated.");
  }catch(e){toast("Regeneration failed: "+e.message,true);}
  finally{state.busy=false;renderState();}
}
async function previewScript(){
  try{
    await saveDirection(true);
    const t=selectedTopic();
    if(!state.topics.some(x=>x.status==="new"&&(state.mode==="series"?isSeries(x):!isSeries(x))))throw Error("No available topic");
    if(!await confirmAction("Generate AI script preview?","This makes a paid AI script/scene call but will not generate image or video media, publish, or consume the topic."))return;
    const out=await post("/api/script-only",{production_mode:state.mode,...(t?{topic_id:t.id}:{})});
    if(!out.script)throw Error(out.error||"No script returned");
    $("script-preview-text").textContent=out.script.script_full||"No text";
    $("script-preview").classList.remove("hidden");
    toast("Script preview generated.");
  }catch(e){toast("Script preview failed: "+e.message,true);}
}
async function loadRuns(){
  const runs=await api("/api/runs");state.runs=Array.isArray(runs)?runs:runs.runs||[];
  $("runs-list").innerHTML=state.runs.length?state.runs.slice(0,25).map(r=>'<article class="run-row"><strong>'+esc(r.topic||"Untitled")+'</strong><small>'+esc(r.date||"")+' · '+esc(r.status||"")+(r.plan?.clips?" · "+esc(r.plan.clips)+" clips":"")+'</small>'+
    (r.error?'<p class="small">'+esc(r.error)+'</p>':"")+
    (r.final_video?'<p><a target="_blank" rel="noopener" href="'+esc(r.final_video)+'">Watch final film ↗</a></p>':"")+'</article>').join(""):'<p class="small">No production history yet.</p>';
}
async function loadConnections(){
  const keys=await api("/api/config");
  $("connections").innerHTML=Object.entries(keys).map(([name,active])=>'<div class="card panel"><div class="eyebrow">'+esc(name.toUpperCase())+'</div><h2 style="color:'+(active?"var(--green)":"var(--gold)")+'">'+(active?"CONNECTED":"NOT CONFIGURED")+'</h2></div>').join("");
}
async function loadAll(){
  const [settings,topics,scenes,story]=await Promise.all([
    api("/api/settings"),api("/api/topics"),api("/api/scenes"),api("/api/story")
  ]);
  state.settings=settings||{};
  state.topics=topics.topics||topics||[];
  state.scenePack=scenes.data||{};
  state.story=story.story||{};
  syncFields();renderCast();renderTopics();
  await Promise.all([refreshEstimate(),refreshStatus(),loadConnections(),loadRuns()]);
  state.initialized=true;
}
function bindEvents(){
  document.querySelectorAll("[data-view]").forEach(b=>b.addEventListener("click",()=>showView(b.dataset.view)));
  document.querySelectorAll("[data-tab]").forEach(b=>b.addEventListener("click",()=>showTab(b.dataset.tab)));
  document.querySelectorAll("[data-next]").forEach(b=>b.addEventListener("click",()=>showTab(b.dataset.next)));
  $("production-mode").addEventListener("change",e=>{state.mode=e.target.value;renderTopics();});
  $("knight-select").addEventListener("change",()=>{collectFields();renderCast();});
  $("scene-pacing").addEventListener("change",()=>{$("manual-clips-row").classList.toggle("hidden",$("scene-pacing").value!=="manual");});
  $("target-clips").addEventListener("input",()=>{$("target-clips-label").textContent=$("target-clips").value;});
  $("music-volume").addEventListener("input",()=>{$("music-value").textContent=$("music-volume").value+"%";});
  $("refresh-all").addEventListener("click",()=>loadAll().then(()=>toast("Studio refreshed")).catch(e=>toast(e.message,true)));
  $("refresh-productions").addEventListener("click",()=>loadRuns().catch(e=>toast(e.message,true)));
  $("save-brief").addEventListener("click",()=>saveDirection().catch(e=>toast(e.message,true)));
  $("save-audio").addEventListener("click",()=>saveDirection().catch(e=>toast(e.message,true)));
  $("start-run").addEventListener("click",startProduction);
  $("preview-script").addEventListener("click",previewScript);
  $("approve-stage").addEventListener("click",advanceGate);
  $("shot-grid").addEventListener("click",e=>{
    const image=e.target.closest("[data-regen-image]");
    const video=e.target.closest("[data-regen-video]");
    if(image)regen("image",Number(image.dataset.regenImage));
    if(video)regen("video",Number(video.dataset.regenVideo));
  });
  $("queue-episodes").addEventListener("click",async()=>{
    if(!await confirmAction("Queue series episodes?","Add unqueued episodes from The Last Watch to Topics. No paid generation starts."))return;
    try{const r=await post("/api/topics/episodes");toast("Queued "+(r.added||0)+" episodes");const topics=await api("/api/topics");state.topics=topics.topics||[];renderTopics();}catch(e){toast(e.message,true);}
  });
  $("login-form").addEventListener("submit",async e=>{
    e.preventDefault();
    try{
      const result=await post("/api/login",{password:$("password").value});
      if(!result.ok)throw Error("Incorrect password");
      sessionStorage.setItem("kt",result.token||"");
      $("login-screen").classList.add("hidden");$("studio").classList.remove("hidden");
      await loadAll();$("password").value="";
    }catch(e){$("login-error").classList.remove("hidden");$("login-error").textContent=e.message;}
  });
}
async function boot(){
  bindEvents();
  const token=sessionStorage.getItem("kt");
  if(token){
    try{
      const r=await post("/api/login",{token});
      if(r.ok){$("login-screen").classList.add("hidden");$("studio").classList.remove("hidden");await loadAll();}
    }catch(e){sessionStorage.removeItem("kt");}
  }
}
boot();
