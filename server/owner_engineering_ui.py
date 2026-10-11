from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware


JS = r'''(()=>{
'use strict';
const PANEL_ID='ocEngineeringAutonomy';
let snapshot=null;
let loading=false;
let timer=null;
const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const call=(path,options)=>window.api(path,options);
const toast=message=>typeof window.showToast==='function'?window.showToast(String(message)):console.info(message);
function permissionsPage(){const body=document.getElementById('moduleBody');if(!body)return null;const text=body.textContent||'';return text.includes('Read & understand')&&text.includes('Edit / organize')?body:null}
function installStyle(){if(document.getElementById('oc-engineering-style'))return;const style=document.createElement('style');style.id='oc-engineering-style';style.textContent=`
#${PANEL_ID}{margin-top:18px}.oc-eng-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap}.oc-eng-head p{max-width:780px;margin:6px 0 0;opacity:.72}.oc-eng-badges{display:flex;gap:7px;flex-wrap:wrap}.oc-eng-badge{padding:6px 9px;border-radius:999px;background:var(--surface-2,rgba(255,255,255,.06));font-size:11px}.oc-eng-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:14px}.oc-eng-control{display:grid;gap:7px;padding:12px;border:1px solid var(--border,rgba(255,255,255,.1));border-radius:13px}.oc-eng-control span{font-size:12px;opacity:.7}.oc-eng-control select,.oc-eng-control input[type=number],.oc-eng-run input{width:100%;min-height:38px;border-radius:9px;padding:7px 9px;background:var(--surface-2,rgba(255,255,255,.05));color:inherit;border:1px solid var(--border,rgba(255,255,255,.14))}.oc-eng-check{display:flex;align-items:center;justify-content:space-between;gap:10px}.oc-eng-check input{width:20px;height:20px}.oc-eng-run{display:grid;grid-template-columns:1fr auto;gap:9px;margin-top:14px}.oc-eng-work{margin-top:16px;display:grid;gap:8px}.oc-eng-work-row{display:grid;grid-template-columns:minmax(0,1.6fr) repeat(3,minmax(90px,.6fr));gap:10px;align-items:center;padding:11px;border:1px solid var(--border,rgba(255,255,255,.09));border-radius:12px}.oc-eng-work-row small{display:block;opacity:.65;margin-top:3px;word-break:break-word}.oc-eng-empty{padding:16px;text-align:center;opacity:.7}.oc-eng-note{margin-top:12px;font-size:12px;opacity:.66}.oc-eng-warning{margin-top:12px;padding:10px 12px;border-radius:10px;background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.25);font-size:12px}.oc-eng-loading{opacity:.65}@media(max-width:900px){.oc-eng-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.oc-eng-work-row{grid-template-columns:1fr 1fr}}@media(max-width:600px){.oc-eng-grid{grid-template-columns:1fr}.oc-eng-run{grid-template-columns:1fr}.oc-eng-work-row{grid-template-columns:1fr}.oc-eng-head{display:grid}}
`;document.head.appendChild(style)}
function option(value,label,current){return `<option value="${esc(value)}" ${String(current)===String(value)?'selected':''}>${esc(label)}</option>`}
function control(label,key,html,help=''){return `<label class="oc-eng-control"><strong>${esc(label)}</strong>${html}${help?`<span>${esc(help)}</span>`:''}</label>`}
function check(label,key,value,help=''){return `<label class="oc-eng-control oc-eng-check"><span><strong style="display:block;color:inherit;opacity:1">${esc(label)}</strong>${help?`<span>${esc(help)}</span>`:''}</span><input type="checkbox" data-eng-key="${esc(key)}" ${value?'checked':''}></label>`}
function workRows(items){if(!Array.isArray(items)||!items.length)return '<div class="oc-eng-empty">No engineering workspace has been created yet.</div>';return items.slice(0,12).map(item=>`<article class="oc-eng-work-row"><div><strong>${esc(item.title||item.work_order_id)}</strong><small>${esc(item.work_order_id)}</small><small>${esc(item.candidate_revision?`Candidate ${String(item.candidate_revision).slice(0,12)}…`:'No candidate commit yet')}</small></div><div><strong>${esc(item.work_status||'unknown')}</strong><small>Work</small></div><div><strong>${esc(item.attempt_status||item.workspace_state||'unknown')}</strong><small>Attempt</small></div><div><strong>${esc(item.qualification_status||'pending')}</strong><small>${esc(item.review_decision?`Review ${item.review_decision}`:`Repairs ${item.repair_cycles??0}`)}</small></div></article>`).join('')}
function panel(data){const p=data.policy||{};return `<section class="oc-panel" id="${PANEL_ID}">
<div class="oc-eng-head"><div><strong>Engineering Autonomy</strong><p>Control how far Vishnu may go when doing software-engineering Work. Repository scope still comes only from Canonical Work, and push, merge, deploy and Body activation remain separate authorities.</p></div><div class="oc-eng-badges"><span class="oc-eng-badge">No auto merge</span><span class="oc-eng-badge">No auto deploy</span><span class="oc-eng-badge">Canonical Work scoped</span></div></div>
<div class="oc-eng-grid">
${control('Operating mode','mode',`<select data-eng-key="mode">${option('off','Off',p.mode)}${option('analyze','Analyze',p.mode)}${option('workspace','Workspace',p.mode)}${option('auto_fix','Auto-Fix',p.mode)}${option('review_candidate','Review Candidate',p.mode)}</select>`,'Analyze is read-only. Workspace permits isolated edits. Auto-Fix can run bounded repair. Review Candidate adds candidate review.')}
${control('Security ceiling','security_level',`<select data-eng-key="security_level">${option('ordinary','Ordinary',p.security_level)}${option('sensitive','Sensitive',p.security_level)}${option('authority','Authority',p.security_level)}</select>`,'Authority code still requires explicit Canonical Work approval.')}
${control('Browser depth','browser_depth',`<select data-eng-key="browser_depth">${option('critical','Critical',p.browser_depth)}${option('full','Full',p.browser_depth)}${option('release','Release',p.browser_depth)}</select>`)}
${control('Visual qualification','visual_level',`<select data-eng-key="visual_level">${option('off','Off',p.visual_level)}${option('diff','Approved baseline diff',p.visual_level)}${option('semantic','Diff + semantic vision review',p.visual_level)}</select>`)}
${control('Maximum files','max_files',`<input type="number" min="1" max="200" value="${esc(p.max_files??24)}" data-eng-key="max_files">`)}
${control('Maximum repair cycles','max_repair_cycles',`<input type="number" min="0" max="10" value="${esc(p.max_repair_cycles??3)}" data-eng-key="max_repair_cycles">`)}
${control('File byte ceiling','max_file_bytes',`<input type="number" min="1000" max="5000000" step="1000" value="${esc(p.max_file_bytes??500000)}" data-eng-key="max_file_bytes">`)}
${control('Total change bytes','max_total_bytes',`<input type="number" min="1000" max="20000000" step="1000" value="${esc(p.max_total_bytes??2000000)}" data-eng-key="max_total_bytes">`)}
${control('Evidence retention days','evidence_retention_days',`<input type="number" min="1" max="3650" value="${esc(p.evidence_retention_days??30)}" data-eng-key="evidence_retention_days">`)}
${control('Model cost / Work','max_model_cost_per_work',`<input type="number" min="0.01" max="100000" step="0.01" value="${esc(p.max_model_cost_per_work??'')}" placeholder="Existing model policy" data-eng-key="max_model_cost_per_work">`)}
${check('Allow preview qualification','preview_enabled',!!p.preview_enabled,'Observes an already-created preview; does not grant deploy authority.')}
${check('Require physical-device evidence','physical_device_required',!!p.physical_device_required)}
${check('Require performance gate','performance_required',p.performance_required!==false)}
${check('Require localization stress','localization_required',p.localization_required!==false)}
${check('Require 3D / WebGL gate','three_d_required',p.three_d_required!==false)}
</div>
<div class="oc-eng-run"><input id="ocEngineeringWorkId" maxlength="200" placeholder="Canonical WorkOrder ID"><button type="button" class="oc-button primary" data-eng-run>Run governed engineering Work</button></div>
<div class="oc-eng-warning">Changing Engineering Autonomy or starting work requires fresh owner verification. Auto-Fix and Review Candidate still stop before remote push, merge, deployment or Body activation.</div>
<div class="oc-eng-work"><div class="oc-eng-head"><strong>Live engineering work</strong><button type="button" class="oc-button" data-eng-refresh>Refresh</button></div>${workRows(data.recent_work)}</div>
<div class="oc-eng-note">Repository paths, candidate branches, tests, repair attempts and review state are projected from Canonical Work and its isolated engineering workspaces.</div>
</section>`}
async function load(force=false){if(loading&&!force)return;loading=true;try{snapshot=await call('/owner/engineering/summary');mount()}catch(error){console.warn('Engineering Autonomy unavailable',error);const old=document.getElementById(PANEL_ID);if(old)old.innerHTML='<strong>Engineering Autonomy</strong><p class="oc-eng-loading">Engineering runtime is unavailable on this host.</p>'}finally{loading=false}}
async function save(target){const key=target.dataset.engKey;if(!key)return;let value;if(target.type==='checkbox')value=target.checked;else if(target.type==='number')value=target.value.trim()===''?null:Number(target.value);else value=target.value;target.disabled=true;try{const result=await call('/owner/engineering/policy',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:value})});snapshot={...(snapshot||{}),policy:result.policy};toast('Engineering Autonomy setting saved.');mount()}catch(error){toast(error.message||'Fresh owner verification may be required.');await load(true)}finally{target.disabled=false}}
async function runWork(){const input=document.getElementById('ocEngineeringWorkId');const id=String(input?.value||'').trim();if(!id){toast('Enter a Canonical WorkOrder ID.');return}try{const result=await call(`/owner/engineering/work/${encodeURIComponent(id)}/execute`,{method:'POST'});toast(result.scheduled?'Engineering work scheduled.':'Engineering work was not scheduled.');setTimeout(()=>load(true),800)}catch(error){toast(error.message||'Could not start engineering work.')}}
function bind(panel){panel.querySelectorAll('[data-eng-key]').forEach(el=>el.addEventListener('change',()=>save(el)));panel.querySelector('[data-eng-refresh]')?.addEventListener('click',()=>load(true));panel.querySelector('[data-eng-run]')?.addEventListener('click',runWork)}
function mount(){installStyle();const body=permissionsPage();if(!body)return;let current=document.getElementById(PANEL_ID);if(!snapshot){if(!current){current=document.createElement('section');current.id=PANEL_ID;current.className='oc-panel';current.innerHTML='<strong>Engineering Autonomy</strong><p class="oc-eng-loading">Loading governed engineering controls…</p>';body.appendChild(current)}load();return}const holder=document.createElement('div');holder.innerHTML=panel(snapshot);const fresh=holder.firstElementChild;if(current)current.replaceWith(fresh);else body.appendChild(fresh);bind(fresh);if(!timer)timer=setInterval(()=>{if(permissionsPage())load(true)},8000)}
const observer=new MutationObserver(()=>{if(permissionsPage()&&!document.getElementById(PANEL_ID))mount()});observer.observe(document.documentElement,{childList:true,subtree:true});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();'''


class OwnerEngineeringUiMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path not in {"/iphone", "/iphone/"} or response.status_code != 200:
            return response
        if "text/html" not in response.headers.get("content-type", ""):
            return response
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        text = body.decode("utf-8")
        marker = "</body>"
        script = '<script src="/iphone/owner-engineering-ui.js"></script>'
        if marker in text and script not in text:
            text = text.replace(marker, script + marker, 1)
        headers = {
            key: value for key, value in response.headers.items()
            if key.lower() not in {"content-length", "content-encoding"}
        }
        return Response(text, status_code=response.status_code, headers=headers, media_type="text/html")


def owner_engineering_ui_router() -> APIRouter:
    router = APIRouter()

    @router.get("/iphone/owner-engineering-ui.js", include_in_schema=False)
    def owner_engineering_js():
        return Response(JS, media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    return router
