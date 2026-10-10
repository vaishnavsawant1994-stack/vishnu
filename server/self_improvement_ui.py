from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware


JS = r'''(()=>{
'use strict';
const ROOT='ocSelfImprovement';
let busy=false;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const api=(path,options)=>window.api(path,options);
const toast=m=>typeof window.showToast==='function'?window.showToast(String(m)):console.info(m);
function installStyle(){if(document.getElementById('oc-self-improvement-style'))return;const s=document.createElement('style');s.id='oc-self-improvement-style';s.textContent=`
#${ROOT}{margin-top:16px;padding-top:16px;border-top:1px solid var(--border,rgba(255,255,255,.1))}.si-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap}.si-section{margin-top:16px}.si-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}.si-control{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px;border:1px solid var(--border,rgba(255,255,255,.1));border-radius:13px}.si-control span{display:grid;gap:3px}.si-control small,.si-note{opacity:.68}.si-control input,.si-control select{max-width:190px;min-height:36px;border-radius:9px;padding:6px 8px;background:var(--surface-2,rgba(255,255,255,.05));color:inherit;border:1px solid var(--border,rgba(255,255,255,.14))}.si-actions,.si-pills{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.si-pill{padding:6px 9px;border-radius:999px;background:var(--surface-2,rgba(255,255,255,.06));font-size:12px}.si-list{display:grid;gap:8px;margin-top:12px}.si-row{padding:10px 12px;border:1px solid var(--border,rgba(255,255,255,.1));border-radius:12px;display:flex;justify-content:space-between;gap:12px;align-items:center}.si-row>span{display:grid;gap:3px}.si-row small{opacity:.68}.si-warning{padding:10px 12px;border:1px solid var(--border,rgba(255,255,255,.14));border-radius:12px;margin-top:10px}@media(max-width:720px){.si-grid{grid-template-columns:1fr}.si-control{align-items:flex-start}.si-control input,.si-control select{max-width:45vw}.si-row{align-items:flex-start;flex-direction:column}}
`;document.head.appendChild(s)}
function metric(label,value){return `<span class="si-pill"><strong>${esc(value)}</strong> ${esc(label)}</span>`}
function control(label,key,value,type='text',help='',surface='training'){const attr=surface==='intelligence'?'data-si-intelligence-setting':'data-si-setting';if(type==='checkbox')return `<label class="si-control"><span><strong>${esc(label)}</strong><small>${esc(help)}</small></span><input type="checkbox" ${attr}="${esc(key)}" ${value?'checked':''}></label>`;const step=['minimum_quality_score','minimum_improvement','max_training_cost','shadow_min_pass_rate','shadow_min_quality_delta'].includes(key)?' step="0.01"':'';return `<label class="si-control"><span><strong>${esc(label)}</strong><small>${esc(help)}</small></span><input type="${type}"${step} ${attr}="${esc(key)}" value="${esc(value??'')}"></label>`}
function select(label,key,value,values,help=''){return `<label class="si-control"><span><strong>${esc(label)}</strong><small>${esc(help)}</small></span><select data-si-setting="${esc(key)}">${values.map(v=>`<option value="${esc(v)}" ${String(value)===String(v)?'selected':''}>${esc(v)}</option>`).join('')}</select></label>`}
function renderPerformance(rows){if(!rows.length)return '<div class="si-note">No routing-learning observations yet.</div>';return `<div class="si-list">${rows.slice(0,8).map(p=>`<div class="si-row"><span><strong>${esc(p.task_domain)} · ${esc(p.task_complexity||'medium')} · ${esc(p.specialist_role||'general')}</strong><small>${esc(p.provider_id)}/${esc(p.model_id)} · quality ${Number(p.quality_score||0).toFixed(2)} · samples ${esc(p.samples)} · confidence ${Number(p.sample_confidence||0).toFixed(2)} · recency ${Number(p.recency_weight||0).toFixed(2)}</small></span></div>`).join('')}</div>`}
function renderModels(models){if(!models.length)return '<div class="si-note">No trained model versions yet.</div>';return `<div class="si-list">${models.slice(0,8).map(m=>{const life=m.lifecycle||{},shadow=m.shadow||{};const eligible=life.status==='candidate'&&life.promotion_state==='eligible';return `<div class="si-row"><span><strong>${esc(m.model_id)}</strong><small>${esc(life.status||m.status)} · ${esc(m.method)} · ${esc(m.base_model)} · dataset ${esc(life.snapshot_id||m.dataset_snapshot_id||'—')} · shadow ${esc(shadow.samples||0)} samples / ${Number(shadow.pass_rate||0).toFixed(2)} pass</small></span>${eligible?`<button type="button" class="oc-button primary" data-si-promote="${esc(m.model_id)}">Approve promotion</button>`:''}</div>`}).join('')}</div>`}
function html(data){const training=data.auto_training||{},s=training.settings||{},intel=data.settings||{},rt=data.auto_training_runtime||{},shadow=data.shadow_qualification||{},code=data.code_evolution||{},jobs=training.jobs||[],models=training.models||[],backends=training.backends||{},stats=data.training||{},performance=data.performance||{};const backend=backends[s.backend_id]||{};return `<div id="${ROOT}">
<div class="si-head"><div><strong>Self-Improvement Engine</strong><p class="si-note">Routing learning, governed Training Capture, real adapter/fine-tuning jobs, evaluation, live shadow qualification and safe code preparation. Model output, consensus or verifier scores never grant authority.</p></div></div>
<div class="si-section"><strong>Routing Learning & Training Capture</strong><div class="si-grid">
${control('Training Capture','training_capture',intel.training_capture!==false,'checkbox','ON by default. Turning it OFF stops new candidate creation; existing approved data remains separately governed.','intelligence')}
${control('Performance learning','performance_learning',intel.performance_learning!==false,'checkbox','Uses bounded task/model outcomes, confidence and recency only after canonical eligibility gates.','intelligence')}
</div><div class="si-pills">${metric('captured',stats.total||0)}${metric('eligible',stats.eligible||0)}${metric('approved',stats.approved_for_export||0)}${metric('routing profiles',Array.isArray(performance)?performance.length:0)}</div>
<div class="si-warning si-note">Capture is not approval. Secrets/credentials, prohibited connected-service sources, sensitive privacy classes, missing provenance/consent where required, low-quality/unverified data and duplicates remain governed before dataset inclusion. No automatic public or Hugging Face publishing.</div>${renderPerformance(Array.isArray(performance)?performance:[])}</div>
<div class="si-section"><strong>Auto Training</strong><div class="si-grid">
${control('Auto Training','enabled',!!s.enabled,'checkbox','Runs only when owner thresholds and configured compute requirements are satisfied.')}
${control('Training backend','backend_id',s.backend_id||'local_peft','text','Built-in governed backend: local_peft. Remote/cloud backends must be explicitly configured.')}
${control('Base model','base_model',s.base_model||'','text','Owner-selected open-weight/local model identifier or path.')}
${select('Training method','method',s.method||'lora',['lora','qlora','full'],'LoRA/QLoRA are supported; full means full fine-tuning, not foundation-model pretraining.')}
${control('Minimum approved records','min_approved_records',s.min_approved_records||100,'number','No training before this governed threshold.')}
${control('Minimum new examples','min_new_examples_since_last_training',s.min_new_examples_since_last_training??25,'number','Prevents retraining after every interaction.')}
${control('Maximum training records','max_training_records',s.max_training_records||10000,'number','Hard cap on one immutable training snapshot.')}
${control('Training interval (seconds)','interval_seconds',s.interval_seconds||86400,'number','Automatic cadence; minimum one hour.')}
${control('Maximum training cost','max_training_cost',s.max_training_cost??'','number','If set, backends that cannot prove cost fail closed.')}
${control('Maximum runtime (seconds)','max_runtime_seconds',s.max_runtime_seconds||21600,'number','Owner ceiling for one training run.')}
${control('Minimum quality','minimum_quality_score',s.minimum_quality_score??0.8,'number','Candidate must pass absolute quality and safety evaluation.')}
${control('Minimum improvement','minimum_improvement',s.minimum_improvement??0,'number','Required measured improvement over the current base/baseline suite.')}
${control('Require safety evaluation','require_safety_evaluation',s.require_safety_evaluation!==false,'checkbox','Policy/action-boundary and adversarial checks must pass.')}
${control('Require held-out evaluation','require_shadow_evaluation',s.require_shadow_evaluation!==false,'checkbox','Source-isolated test split is required before live shadow.')}
${control('Live shadow minimum samples','shadow_min_samples',s.shadow_min_samples||20,'number','Candidate answers remain non-authoritative until enough real-request evidence exists.')}
${control('Live shadow pass rate','shadow_min_pass_rate',s.shadow_min_pass_rate??0.9,'number','Minimum real shadow reliability before promotion eligibility.')}
${control('Automatic rollback','automatic_rollback',s.automatic_rollback!==false,'checkbox','Enables rollback policy only where a release controller and serving backend are configured; it never grants model self-activation.')}
</div>
<div class="si-pills">${metric('trainer',backend.available?'ready':(backend.reason||'unavailable'))}${metric('auto-training',rt.running?'running':(s.enabled?'enabled':'off'))}${metric('shadow backends',Object.values(shadow.backends||{}).filter(v=>v&&v.available).length)}${metric('jobs',jobs.length)}${metric('models',models.length)}${metric('code evolution',code.running?'running':(code.available?'ready':'unavailable'))}</div>
<div class="si-actions"><button type="button" class="oc-button primary" data-si-train>Run training now</button><button type="button" class="oc-button" data-si-evolve>Run approved code upgrades</button></div>
<div class="si-note" style="margin-top:10px">Training completion, offline evaluation, live shadow qualification, promotion approval, deployment and activation are separate states. No control here can self-approve, auto-merge, silently deploy, modify protected authority/security code, or adopt a new Vishnu Body revision.</div>
${jobs.length?`<div class="si-list"><div><strong>Recent training jobs</strong></div>${jobs.slice(0,8).map(j=>{const g=j.governance||{};return `<div class="si-row"><span><strong>${esc(j.job_id)}</strong><small>${esc(g.status||j.status)} · ${esc(j.method)} · ${esc(j.base_model)} · dataset ${esc(g.snapshot_id||j.dataset_snapshot_id||'—')} · cost ${esc(g.estimated_cost??'—')}</small></span></div>`}).join('')}</div>`:''}
<div style="margin-top:12px"><strong>Model Versions & Lineage</strong>${renderModels(models)}</div></div>
</div>`}
async function load(){if(busy)return;const parent=document.getElementById('ocAdvancedIntelligence');if(!parent)return;busy=true;try{const data=await api('/owner/intelligence/summary');installStyle();const old=document.getElementById(ROOT);const holder=document.createElement('div');holder.innerHTML=html(data);const fresh=holder.firstElementChild;if(old)old.replaceWith(fresh);else parent.appendChild(fresh);bind(fresh)}catch(e){console.warn('Self-Improvement Engine unavailable',e)}finally{busy=false}}
function valueOf(el){if(el.type==='checkbox')return el.checked;if(el.type==='number')return el.value===''?null:Number(el.value);return el.value}
async function saveTraining(el){const key=el.dataset.siSetting;el.disabled=true;try{await api('/owner/intelligence/training/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:valueOf(el)})});toast('Training setting saved.');await load()}catch(e){toast(e.message||'Could not save training setting.')}finally{el.disabled=false}}
async function saveIntelligence(el){const key=el.dataset.siIntelligenceSetting;el.disabled=true;try{await api('/owner/intelligence/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:valueOf(el)})});toast(key==='training_capture'?(el.checked?'Training Capture is ON.':'Training Capture is OFF; no new candidates will be created.'):'Routing-learning setting saved.');await load()}catch(e){toast(e.message||'Could not save intelligence setting.')}finally{el.disabled=false}}
function bind(root){root.querySelectorAll('[data-si-setting]').forEach(el=>el.addEventListener('change',()=>saveTraining(el)));root.querySelectorAll('[data-si-intelligence-setting]').forEach(el=>el.addEventListener('change',()=>saveIntelligence(el)));root.querySelector('[data-si-train]')?.addEventListener('click',async()=>{try{await api('/owner/intelligence/training/run',{method:'POST'});toast('Training run scheduled from governed approved data.');setTimeout(load,800)}catch(e){toast(e.message||'Training could not be started.')}});root.querySelector('[data-si-evolve]')?.addEventListener('click',async()=>{try{await api('/owner/intelligence/evolution/run-approved',{method:'POST'});toast('Approved evolution handoffs scheduled for isolated implementation.');setTimeout(load,800)}catch(e){toast(e.message||'Evolution cycle could not be started.')}});root.querySelectorAll('[data-si-promote]').forEach(btn=>btn.addEventListener('click',async()=>{try{await api('/owner/intelligence/training/models/'+encodeURIComponent(btn.dataset.siPromote)+'/approve-promotion',{method:'POST'});toast('Model promotion approved; release activation is still separate.');await load()}catch(e){toast(e.message||'Promotion could not be approved.')}}))}
const observer=new MutationObserver(()=>{if(document.getElementById('ocAdvancedIntelligence')&&!document.getElementById(ROOT))load()});observer.observe(document.documentElement,{childList:true,subtree:true});if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(load,100));else setTimeout(load,100);
})();'''


class SelfImprovementUiMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path not in {'/iphone', '/iphone/'} or response.status_code != 200:
            return response
        if 'text/html' not in response.headers.get('content-type', ''):
            return response
        body = b''
        async for chunk in response.body_iterator:
            body += chunk
        text = body.decode('utf-8')
        marker = '</body>'
        script = '<script src="/iphone/self-improvement-ui.js"></script>'
        if marker in text and script not in text:
            text = text.replace(marker, script + marker, 1)
        headers = {key: value for key, value in response.headers.items() if key.lower() not in {'content-length','content-encoding'}}
        return Response(text, status_code=response.status_code, headers=headers, media_type='text/html')


def self_improvement_ui_router() -> APIRouter:
    router = APIRouter()

    @router.get('/iphone/self-improvement-ui.js', include_in_schema=False)
    def self_improvement_js():
        return Response(JS, media_type='application/javascript', headers={'Cache-Control': 'no-cache'})

    return router
