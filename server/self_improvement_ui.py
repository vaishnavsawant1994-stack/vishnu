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
#${ROOT}{margin-top:16px;padding-top:16px;border-top:1px solid var(--border,rgba(255,255,255,.1))}.si-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap}.si-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}.si-control{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px;border:1px solid var(--border,rgba(255,255,255,.1));border-radius:13px}.si-control span{display:grid;gap:3px}.si-control small,.si-note{opacity:.68}.si-control input,.si-control select{max-width:190px;min-height:36px;border-radius:9px;padding:6px 8px;background:var(--surface-2,rgba(255,255,255,.05));color:inherit;border:1px solid var(--border,rgba(255,255,255,.14))}.si-actions,.si-pills{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.si-pill{padding:6px 9px;border-radius:999px;background:var(--surface-2,rgba(255,255,255,.06));font-size:12px}.si-list{display:grid;gap:8px;margin-top:12px}.si-row{padding:10px 12px;border:1px solid var(--border,rgba(255,255,255,.1));border-radius:12px;display:flex;justify-content:space-between;gap:12px;align-items:center}.si-row>span{display:grid;gap:3px}.si-row small{opacity:.68}@media(max-width:720px){.si-grid{grid-template-columns:1fr}.si-control{align-items:flex-start}.si-control input,.si-control select{max-width:45vw}.si-row{align-items:flex-start;flex-direction:column}}
`;document.head.appendChild(s)}
function metric(label,value){return `<span class="si-pill"><strong>${esc(value)}</strong> ${esc(label)}</span>`}
function control(label,key,value,type='text',help=''){if(type==='checkbox')return `<label class="si-control"><span><strong>${esc(label)}</strong><small>${esc(help)}</small></span><input type="checkbox" data-si-setting="${esc(key)}" ${value?'checked':''}></label>`;const step=(key==='minimum_quality_score'||key==='minimum_improvement')?' step="0.01"':'';return `<label class="si-control"><span><strong>${esc(label)}</strong><small>${esc(help)}</small></span><input type="${type}"${step} data-si-setting="${esc(key)}" value="${esc(value??'')}"></label>`}
function select(label,key,value,values,help=''){return `<label class="si-control"><span><strong>${esc(label)}</strong><small>${esc(help)}</small></span><select data-si-setting="${esc(key)}">${values.map(v=>`<option value="${esc(v)}" ${String(value)===String(v)?'selected':''}>${esc(v)}</option>`).join('')}</select></label>`}
function renderModels(models){if(!models.length)return '<div class="si-note">No trained model versions yet.</div>';return `<div class="si-list">${models.slice(0,5).map(m=>`<div class="si-row"><span><strong>${esc(m.model_id)}</strong><small>${esc(m.status)} · ${esc(m.method)} · ${esc(m.base_model)}</small></span>${m.status==='promotion_ready'?`<button type="button" class="oc-button primary" data-si-promote="${esc(m.model_id)}">Approve promotion</button>`:''}</div>`).join('')}</div>`}
function html(data){const training=data.auto_training||{},s=training.settings||{},rt=data.auto_training_runtime||{},code=data.code_evolution||{},jobs=training.jobs||[],models=training.models||[],backends=training.backends||{};const backend=backends[s.backend_id]||{};return `<div id="${ROOT}">
<div class="si-head"><div><strong>Self-Improvement Engine</strong><p class="si-note">Performance learning improves eligible model ranking. Auto Training can create and evaluate new checkpoints against their base model. Safe code evolution can implement already owner-approved handoffs in isolation. Production activation and Body adoption remain separate owner/release gates.</p></div></div>
<div class="si-grid">
${control('Auto Training','enabled',!!s.enabled,'checkbox','Runs only on approved eligible datasets and configured training compute.')}
${control('Training backend','backend_id',s.backend_id||'local_peft','text','Built-in governed local backend: local_peft.')}
${control('Base model','base_model',s.base_model||'','text','Owner-selected local/open-weight model identifier or path.')}
${select('Training method','method',s.method||'lora',['lora','qlora','full'],'LoRA is the default; QLoRA needs compatible GPU dependencies.')}
${control('Minimum approved records','min_approved_records',s.min_approved_records||100,'number','Training does not start before this governed threshold.')}
${control('Maximum training records','max_training_records',s.max_training_records||10000,'number','Hard cap on one governed training snapshot.')}
${control('Training interval (seconds)','interval_seconds',s.interval_seconds||86400,'number','Automatic cadence; minimum one hour.')}
${control('Minimum quality','minimum_quality_score',s.minimum_quality_score??0.8,'number','Candidate must pass absolute safety/correctness and held-out evaluation.')}
${control('Minimum improvement','minimum_improvement',s.minimum_improvement??0,'number','Required quality gain over the base model on the same evaluation suite.')}
${control('Require safety evaluation','require_safety_evaluation',s.require_safety_evaluation!==false,'checkbox','Critical action-boundary and injection tests must pass.')}
${control('Require held-out shadow','require_shadow_evaluation',s.require_shadow_evaluation!==false,'checkbox','Uses a source-isolated held-out test split before promotion.')}
</div>
<div class="si-pills">${metric('trainer',backend.available?'ready':(backend.reason||'unavailable'))}${metric('auto-training',rt.running?'running':(s.enabled?'enabled':'off'))}${metric('jobs',jobs.length)}${metric('models',models.length)}${metric('code evolution',code.running?'running':(code.available?'ready':'unavailable'))}</div>
<div class="si-actions"><button type="button" class="oc-button primary" data-si-train>Run training now</button><button type="button" class="oc-button" data-si-evolve>Run approved code upgrades</button></div>
<div class="si-note" style="margin-top:10px">No control here can self-approve training promotion, activate a model, merge/deploy code, change protected security/evolution files, or adopt a new Vishnu Body revision.</div>
${jobs.length?`<div class="si-list"><div><strong>Recent training jobs</strong></div>${jobs.slice(0,5).map(j=>`<div class="si-row"><span><strong>${esc(j.job_id)}</strong><small>${esc(j.status)} · ${esc(j.method)} · ${esc(j.base_model)}</small></span></div>`).join('')}</div>`:''}
<div style="margin-top:12px"><strong>Trained models</strong>${renderModels(models)}</div>
</div>`}
async function load(){if(busy)return;const parent=document.getElementById('ocAdvancedIntelligence');if(!parent)return;busy=true;try{const data=await api('/owner/intelligence/summary');installStyle();const old=document.getElementById(ROOT);const holder=document.createElement('div');holder.innerHTML=html(data);const fresh=holder.firstElementChild;if(old)old.replaceWith(fresh);else parent.appendChild(fresh);bind(fresh)}catch(e){console.warn('Self-Improvement Engine unavailable',e)}finally{busy=false}}
async function save(el){const key=el.dataset.siSetting;let value;if(el.type==='checkbox')value=el.checked;else if(el.type==='number')value=Number(el.value);else value=el.value;el.disabled=true;try{await api('/owner/intelligence/training/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:value})});toast('Self-improvement setting saved.');await load()}catch(e){toast(e.message||'Could not save training setting.')}finally{el.disabled=false}}
function bind(root){root.querySelectorAll('[data-si-setting]').forEach(el=>el.addEventListener('change',()=>save(el)));root.querySelector('[data-si-train]')?.addEventListener('click',async()=>{try{await api('/owner/intelligence/training/run',{method:'POST'});toast('Training run scheduled from governed approved data.');setTimeout(load,800)}catch(e){toast(e.message||'Training could not be started.')}});root.querySelector('[data-si-evolve]')?.addEventListener('click',async()=>{try{await api('/owner/intelligence/evolution/run-approved',{method:'POST'});toast('Approved evolution handoffs scheduled for isolated implementation.');setTimeout(load,800)}catch(e){toast(e.message||'Evolution cycle could not be started.')}});root.querySelectorAll('[data-si-promote]').forEach(btn=>btn.addEventListener('click',async()=>{try{await api('/owner/intelligence/training/models/'+encodeURIComponent(btn.dataset.siPromote)+'/approve-promotion',{method:'POST'});toast('Model promotion approved; release activation is still separate.');await load()}catch(e){toast(e.message||'Promotion could not be approved.')}}))}
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
