from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware


JS = r'''(()=>{
'use strict';
const PANEL='ocPortableIntelligence';
let summary=null,loading=false;
const esc=v=>String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const api=(path,options)=>window.api(path,options);
const toast=message=>typeof window.showToast==='function'?window.showToast(String(message)):console.info(message);
function page(){const body=document.getElementById('moduleBody');if(!body)return null;const text=body.textContent||'';return text.includes('Your data stays owner-controlled')||text.includes('Data & Backups')?body:null}
function style(){if(document.getElementById('portable-intelligence-style'))return;const node=document.createElement('style');node.id='portable-intelligence-style';node.textContent=`
#${PANEL}{margin-top:18px}.pi-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px}.pi-card{padding:14px;border:1px solid var(--border,rgba(255,255,255,.1));border-radius:14px;display:grid;gap:7px}.pi-card small,.pi-note{opacity:.68;line-height:1.45}.pi-value{font-size:1.02rem;font-weight:650;word-break:break-word}.pi-actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:14px}.pi-settings{display:grid;gap:9px;margin-top:14px}.pi-setting{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:11px 12px;border:1px solid var(--border,rgba(255,255,255,.1));border-radius:12px}.pi-setting select{min-height:36px;max-width:220px;background:var(--surface-2,rgba(255,255,255,.05));color:inherit;border:1px solid var(--border,rgba(255,255,255,.14));border-radius:9px;padding:5px 8px}.pi-setting input[type=checkbox]{width:20px;height:20px}.pi-specialists{display:grid;gap:8px;margin-top:12px}.pi-specialist{padding:10px 12px;border-radius:11px;background:var(--surface-2,rgba(255,255,255,.05));font-size:13px}.pi-form{display:grid;grid-template-columns:1fr 1fr 1.2fr auto;gap:8px;margin-top:10px}.pi-form input,.pi-form select{min-width:0;min-height:38px;border-radius:10px;padding:6px 8px;background:var(--surface-2,rgba(255,255,255,.05));color:inherit;border:1px solid var(--border,rgba(255,255,255,.14))}@media(max-width:720px){.pi-grid{grid-template-columns:1fr}.pi-form{grid-template-columns:1fr}.pi-setting{align-items:flex-start}.pi-setting select{max-width:48vw}}
`;document.head.appendChild(node)}
function card(label,value,help){return `<div class="pi-card"><small>${esc(label)}</small><div class="pi-value">${esc(value)}</div><small>${esc(help||'')}</small></div>`}
function statusHtml(data){const manifest=data.manifest||{},hw=data.hardware||{},off=data.offline_readiness||{},act=data.activation||{},vault=data.vault||{},con=data.contributions||{};const specialists=data.specialist_bindings||[];return `<section class="oc-panel" id="${PANEL}">
<div><strong>Portable Vishnu Intelligence</strong><p>Restore the same approved Vishnu state on another machine, verify hardware and offline readiness, and control what may contribute to shared learning.</p></div>
<div class="pi-grid">
${card('Intelligence Manifest',manifest.manifest_id||'Not published',manifest.core_version?`Core ${manifest.core_version}`:'Publish the current qualified state first.')}
${card('This device',`${hw.platform||'unknown'} · ${hw.ram_gb??'?'} GB RAM`,`${hw.accelerator||'none'} · ${hw.gpu_vram_gb??0} GB dedicated VRAM`)}
${card('Offline readiness',off.ready?'Ready':'Not ready',off.ready?`Runtime ${off.selected_runtime||'selected'}`:(off.blocked||[]).join(', ')||'No local runtime catalog')}
${card('Activation',act.activated?'Verified active':'Not activated',act.receipt?.runtime_id?`${act.receipt.runtime_id} · ${act.receipt.model_ref}`:'No verified activation receipt')}
${card('Intelligence Vault',vault.production_durable?'Durable':'Local / durability not asserted',vault.integrity?`Integrity ${vault.integrity}`:'Content-addressed storage')}
${card('Remote GPU training',data.remote_gpu_backend_configured?'Configured':'Provider not configured',data.remote_gpu_backend_configured?'Available through governed training ceilings':'Connect an approved provider adapter; credentials are never exposed here.')}
</div>
<div class="pi-actions"><button class="oc-button primary" type="button" data-pi-publish>Publish current Vishnu</button><button class="oc-button" type="button" data-pi-offline>Prepare offline pack</button><button class="oc-button" type="button" data-pi-preflight>Check restore activation</button><button class="oc-button" type="button" data-pi-activate>Activate restored Vishnu</button></div>
<div class="pi-note" data-pi-result></div>
<div class="pi-settings"><strong>Help improve Vishnu</strong>
<label class="pi-setting"><span><b>Contribution mode</b><small style="display:block">Private is the default. Aggregate shares structured outcomes only.</small></span><select data-pi-setting="mode"><option value="private" ${con.mode==='private'?'selected':''}>Private</option><option value="aggregate" ${con.mode==='aggregate'?'selected':''}>Anonymous aggregate</option><option value="training_contributor" ${con.mode==='training_contributor'?'selected':''}>Training contributor</option></select></label>
${['agent_outcomes','tool_metrics','corrections','conversations','documents'].map(key=>`<label class="pi-setting"><span>${esc(key.replaceAll('_',' '))}</span><input type="checkbox" data-pi-setting="${key}" ${con[key]?'checked':''}></label>`).join('')}
</div>
<div class="pi-specialists"><strong>Specialist model bindings</strong>${specialists.length?specialists.map(item=>`<div class="pi-specialist"><b>${esc(item.specialist_role)}</b> · ${esc(item.task_domain)} → ${esc(item.model_id)}</div>`).join(''):'<div class="pi-note">No production-active specialist adapters are bound yet.</div>'}<div class="pi-form"><input data-pi-role placeholder="Role, e.g. coding"><input data-pi-domain placeholder="Domain, e.g. general"><select data-pi-model><option value="">Select active model…</option></select><button class="oc-button" type="button" data-pi-bind>Bind</button></div></div>
<div class="oc-note">Backup/restore mutation stays owned by Vishnu's encrypted recovery system. Model execution stays owned by the governed model router. Model promotion stays owned by the training registry.</div>
</section>`}
async function loadModels(panel){try{const data=await api('/owner/intelligence/training/models?limit=100');const select=panel.querySelector('[data-pi-model]');if(!select)return;const active=(data.models||[]).filter(item=>String(item.status||'').toLowerCase()==='active');select.innerHTML='<option value="">Select active model…</option>'+active.map(item=>`<option value="${esc(item.model_id)}">${esc(item.model_id)}</option>`).join('')}catch(error){console.warn('Portable specialist models unavailable',error)}}
function bind(panel){panel.querySelector('[data-pi-publish]')?.addEventListener('click',()=>action('/owner/portable-intelligence/publish',{},'Published current Vishnu identity.'));panel.querySelector('[data-pi-offline]')?.addEventListener('click',()=>action('/owner/portable-intelligence/offline-pack',{},'Offline pack prepared and verified.'));panel.querySelector('[data-pi-preflight]')?.addEventListener('click',()=>action('/owner/portable-intelligence/activation/preflight',{online:navigator.onLine},'Activation preflight completed.'));panel.querySelector('[data-pi-activate]')?.addEventListener('click',()=>action('/owner/portable-intelligence/activation',{online:navigator.onLine},'Restored Vishnu activated and verified.'));panel.querySelectorAll('[data-pi-setting]').forEach(el=>el.addEventListener('change',()=>saveSetting(el)));panel.querySelector('[data-pi-bind]')?.addEventListener('click',()=>bindSpecialist(panel));loadModels(panel)}
async function action(path,body,message){try{const result=await api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const note=document.querySelector('[data-pi-result]');if(note)note.textContent=path.endsWith('/preflight')?JSON.stringify(result.preflight||result):message;toast(message);summary=null;await load()}catch(error){toast(error.message||'Portable intelligence action failed.')}}
async function saveSetting(el){const key=el.dataset.piSetting,value=el.type==='checkbox'?el.checked:el.value;el.disabled=true;try{await api('/owner/portable-intelligence/contributions',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:value})});toast('Shared-learning preference saved.');summary=null;await load()}catch(error){toast(error.message||'Could not save shared-learning preference.')}finally{el.disabled=false}}
async function bindSpecialist(panel){const role=panel.querySelector('[data-pi-role]')?.value.trim(),domain=panel.querySelector('[data-pi-domain]')?.value.trim()||'general',model_id=panel.querySelector('[data-pi-model]')?.value;if(!role||!model_id){toast('Choose a specialist role and an active model.');return}try{await api('/owner/portable-intelligence/specialists',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({specialist_role:role,task_domain:domain,model_id})});toast('Specialist model bound.');summary=null;await load()}catch(error){toast(error.message||'Could not bind specialist model.')}}
async function load(){if(loading)return;loading=true;try{summary=await api('/owner/portable-intelligence/summary');mount()}catch(error){console.warn('Portable intelligence unavailable',error)}finally{loading=false}}
function mount(){style();const body=page();if(!body)return;let existing=document.getElementById(PANEL);if(!summary){if(!existing){existing=document.createElement('section');existing.id=PANEL;existing.className='oc-panel';existing.innerHTML='<strong>Portable Vishnu Intelligence</strong><p>Loading portable intelligence status…</p>';body.appendChild(existing)}load();return}const holder=document.createElement('div');holder.innerHTML=statusHtml(summary);const fresh=holder.firstElementChild;if(existing)existing.replaceWith(fresh);else body.appendChild(fresh);bind(fresh)}
const observer=new MutationObserver(()=>{if(page()&&!document.getElementById(PANEL))mount()});observer.observe(document.documentElement,{childList:true,subtree:true});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();'''


class PortableIntelligenceUiMiddleware(BaseHTTPMiddleware):
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
        script = '<script src="/iphone/portable-intelligence-ui.js"></script>'
        if marker in text and script not in text:
            text = text.replace(marker, script + marker, 1)
        headers = {key: value for key, value in response.headers.items() if key.lower() not in {'content-length', 'content-encoding'}}
        return Response(text, status_code=response.status_code, headers=headers, media_type='text/html')


def portable_intelligence_ui_router() -> APIRouter:
    router = APIRouter()

    @router.get('/iphone/portable-intelligence-ui.js', include_in_schema=False)
    def portable_intelligence_js():
        return Response(JS, media_type='application/javascript', headers={'Cache-Control': 'no-cache'})

    return router
