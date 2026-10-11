from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware


JS = r'''(()=>{
'use strict';
const ID='ocReleaseProduction';let data=null,busy=false,timer=null;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const call=(path,opt)=>window.api(path,opt);const toast=m=>typeof window.showToast==='function'?window.showToast(String(m)):console.info(m);
function page(){const body=document.getElementById('moduleBody');if(!body)return null;const t=body.textContent||'';return t.includes('Read & understand')&&t.includes('Edit / organize')?body:null}
function styles(){if(document.getElementById('oc-release-style'))return;const s=document.createElement('style');s.id='oc-release-style';s.textContent=`
#${ID}{margin-top:18px}.oc-rel-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap}.oc-rel-head p{margin:6px 0 0;max-width:800px;opacity:.72}.oc-rel-badges{display:flex;gap:7px;flex-wrap:wrap}.oc-rel-badge{padding:6px 9px;border-radius:999px;background:var(--surface-2,rgba(255,255,255,.06));font-size:11px}.oc-rel-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:14px}.oc-rel-control{display:grid;gap:7px;padding:12px;border:1px solid var(--border,rgba(255,255,255,.1));border-radius:13px}.oc-rel-control small{opacity:.68}.oc-rel-control select,.oc-rel-control input[type=number]{width:100%;min-height:38px;border-radius:9px;padding:7px 9px;background:var(--surface-2,rgba(255,255,255,.05));color:inherit;border:1px solid var(--border,rgba(255,255,255,.14))}.oc-rel-check{display:flex;align-items:center;justify-content:space-between;gap:10px}.oc-rel-check input{width:20px;height:20px}.oc-rel-warning{margin-top:12px;padding:10px 12px;border-radius:10px;background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.25);font-size:12px}.oc-rel-list{margin-top:16px;display:grid;gap:9px}.oc-rel-row{padding:12px;border:1px solid var(--border,rgba(255,255,255,.1));border-radius:13px;display:grid;grid-template-columns:minmax(0,1.5fr) minmax(110px,.6fr) minmax(0,1fr);gap:10px;align-items:center}.oc-rel-row small{display:block;opacity:.65;margin-top:3px;word-break:break-word}.oc-rel-actions{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.oc-rel-actions button{min-height:34px}.oc-rel-empty{padding:16px;text-align:center;opacity:.7}.oc-rel-provider{margin-top:10px;font-size:12px;opacity:.7}@media(max-width:900px){.oc-rel-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.oc-rel-row{grid-template-columns:1fr 1fr}.oc-rel-actions{grid-column:1/-1;justify-content:flex-start}}@media(max-width:600px){.oc-rel-grid,.oc-rel-row{grid-template-columns:1fr}.oc-rel-actions{grid-column:auto}.oc-rel-head{display:grid}}
`;document.head.appendChild(s)}
function opt(v,l,c){return `<option value="${esc(v)}" ${String(c)===String(v)?'selected':''}>${esc(l)}</option>`}
function ctl(label,key,inner,help=''){return `<label class="oc-rel-control"><strong>${esc(label)}</strong>${inner}${help?`<small>${esc(help)}</small>`:''}</label>`}
function chk(label,key,v,help=''){return `<label class="oc-rel-control oc-rel-check"><span><strong style="display:block">${esc(label)}</strong>${help?`<small>${esc(help)}</small>`:''}</span><input type="checkbox" data-rel-key="${esc(key)}" ${v?'checked':''}></label>`}
function action(id,name,label,danger=false){return `<button type="button" class="oc-button ${danger?'danger':''}" data-rel-action="${esc(name)}" data-rel-id="${esc(id)}">${esc(label)}</button>`}
function rows(items){if(!Array.isArray(items)||!items.length)return '<div class="oc-rel-empty">No qualified engineering candidate has entered release control yet.</div>';return items.slice(0,20).map(r=>{let buttons='';if(r.approval_required&&!r.approved_by&&!['succeeded','failed','cancelled','rolled_back'].includes(r.status))buttons+=action(r.id,'approve','Approve');if(['planned','awaiting_approval'].includes(r.status))buttons+=action(r.id,'preview','Preview');if(r.status==='preview_qualified')buttons+=action(r.id,'promote','Promote');if(r.status==='rollback_recommended')buttons+=action(r.id,'rollback','Rollback',true);if(!['succeeded','failed','cancelled','rolled_back','promoting','rolling_back'].includes(r.status))buttons+=action(r.id,'cancel','Cancel');return `<article class="oc-rel-row"><div><strong>${esc(r.id)}</strong><small>Candidate ${esc(String(r.candidate_revision||'').slice(0,12))}… · ${esc(r.provider)} · ${esc(r.target)}</small><small>${esc(r.preview_url||r.production_url||'No deployment URL yet')}</small></div><div><strong>${esc(r.status)}</strong><small>${esc(r.risk_class)} risk${r.approval_required?' · approval governed':''}</small></div><div class="oc-rel-actions">${buttons||'<small>No owner action required.</small>'}</div></article>`}).join('')}
function panel(x){const p=x.policy||{};const providers=Array.isArray(x.providers)?x.providers:[];return `<section class="oc-panel" id="${ID}"><div class="oc-rel-head"><div><strong>Release & Production Autonomy</strong><p>Govern how an exact, independently qualified engineering candidate may move through preview, production smoke checks, canary monitoring and rollback. Release authority is separate from Engineering Autonomy.</p></div><div class="oc-rel-badges"><span class="oc-rel-badge">Exact SHA bound</span><span class="oc-rel-badge">No model shell</span><span class="oc-rel-badge">No Body activation</span><span class="oc-rel-badge">Rollback separately governed</span></div></div><div class="oc-rel-grid">
${ctl('Release mode','mode',`<select data-rel-key="mode">${opt('off','Off',p.mode)}${opt('preview_only','Preview only',p.mode)}${opt('approval_required','Approval required',p.mode)}${opt('auto_low_risk','Auto low-risk',p.mode)}</select>`,'Auto low-risk still requires approval for sensitive/auth/security/database/billing/provider/runtime changes.')}
${ctl('Automatic risk ceiling','automatic_risk_ceiling',`<select data-rel-key="automatic_risk_ceiling">${opt('low','Low',p.automatic_risk_ceiling)}${opt('medium','Medium',p.automatic_risk_ceiling)}${opt('high','High',p.automatic_risk_ceiling)}${opt('critical','Critical',p.automatic_risk_ceiling)}</select>`,'Sensitive-surface approval rules remain independent of this ceiling.')}
${ctl('Canary minimum requests','canary_min_requests',`<input type="number" min="1" max="100000" value="${esc(p.canary_min_requests??20)}" data-rel-key="canary_min_requests">`)}
${ctl('Max error-rate regression','canary_max_error_rate_regression',`<input type="number" min="0" max="1" step="0.01" value="${esc(p.canary_max_error_rate_regression??0.05)}" data-rel-key="canary_max_error_rate_regression">`)}
${ctl('Max p95 latency ratio','canary_max_latency_ratio',`<input type="number" min="1" max="100" step="0.05" value="${esc(p.canary_max_latency_ratio??1.35)}" data-rel-key="canary_max_latency_ratio">`)}
${chk('Allow production','allow_production',p.allow_production!==false)}
${chk('Require preview','require_preview',p.require_preview!==false)}
${chk('Require exact-revision evidence','require_exact_revision_evidence',p.require_exact_revision_evidence!==false)}
${chk('Require production smoke','require_production_smoke',p.require_production_smoke!==false)}
${chk('Require canary','require_canary',p.require_canary!==false)}
${chk('Sensitive surfaces require approval','owner_approval_for_sensitive_surfaces',p.owner_approval_for_sensitive_surfaces!==false)}
${chk('Permit explicitly confirmed rollback','allow_automatic_rollback',!!p.allow_automatic_rollback,'This does not create automatic rollback. An explicit confirmed owner action is still required.')}
</div><div class="oc-rel-warning">Production promotion and rollback require a trusted admin device and fresh owner verification. A canary failure can recommend rollback and open Canonical Work, but it cannot silently roll production back.</div><div class="oc-rel-provider">Configured release providers: ${providers.length?providers.map(esc).join(', '):'none — qualified candidates remain engineering-qualified but are not deployable from this host.'}</div><div class="oc-rel-list"><div class="oc-rel-head"><strong>Release ledger</strong><button type="button" class="oc-button" data-rel-refresh>Refresh</button></div>${rows(x.releases)}</div></section>`}
async function load(force=false){if(busy&&!force)return;busy=true;try{data=await call('/owner/release/summary');mount()}catch(e){console.warn('Release control unavailable',e);const old=document.getElementById(ID);if(old)old.innerHTML='<strong>Release & Production Autonomy</strong><p>Release control is unavailable on this host.</p>'}finally{busy=false}}
async function save(el){const key=el.dataset.relKey;if(!key)return;let value=el.type==='checkbox'?el.checked:el.type==='number'?Number(el.value):el.value;el.disabled=true;try{const r=await call('/owner/release/policy',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:value})});data={...(data||{}),policy:r.policy};toast('Release policy saved.');mount()}catch(e){toast(e.message||'Fresh owner verification may be required.');await load(true)}finally{el.disabled=false}}
async function act(button){const id=button.dataset.relId,name=button.dataset.relAction;if(!id||!name)return;let body;let suffix=name;if(name==='rollback'){if(!window.confirm('Rollback production to the bound base revision?'))return;body={confirm:true}}if(name==='cancel'){const reason=window.prompt('Reason for cancelling this release:','Owner cancelled release');if(!reason)return;body={reason}}button.disabled=true;try{await call(`/owner/release/${encodeURIComponent(id)}/${suffix}`,{method:'POST',headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});toast(`Release action ${name} completed.`);await load(true)}catch(e){toast(e.message||`Release action ${name} failed.`)}finally{button.disabled=false}}
function bind(root){root.querySelectorAll('[data-rel-key]').forEach(el=>el.addEventListener('change',()=>save(el)));root.querySelector('[data-rel-refresh]')?.addEventListener('click',()=>load(true));root.querySelectorAll('[data-rel-action]').forEach(el=>el.addEventListener('click',()=>act(el)))}
function mount(){styles();const body=page();if(!body)return;let cur=document.getElementById(ID);if(!data){if(!cur){cur=document.createElement('section');cur.id=ID;cur.className='oc-panel';cur.innerHTML='<strong>Release & Production Autonomy</strong><p>Loading governed release controls…</p>';body.appendChild(cur)}load();return}const h=document.createElement('div');h.innerHTML=panel(data);const fresh=h.firstElementChild;if(cur)cur.replaceWith(fresh);else body.appendChild(fresh);bind(fresh);if(!timer)timer=setInterval(()=>{if(page())load(true)},10000)}
const observer=new MutationObserver(()=>{if(page()&&!document.getElementById(ID))mount()});observer.observe(document.documentElement,{childList:true,subtree:true});if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();'''


class OwnerReleaseUiMiddleware(BaseHTTPMiddleware):
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
        script = '<script src="/iphone/owner-release-ui.js"></script>'
        if marker in text and script not in text:
            text = text.replace(marker, script + marker, 1)
        headers = {key: value for key, value in response.headers.items() if key.lower() not in {"content-length", "content-encoding"}}
        return Response(text, status_code=response.status_code, headers=headers, media_type="text/html")


def owner_release_ui_router() -> APIRouter:
    router = APIRouter()

    @router.get("/iphone/owner-release-ui.js", include_in_schema=False)
    def owner_release_js():
        return Response(JS, media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    return router
