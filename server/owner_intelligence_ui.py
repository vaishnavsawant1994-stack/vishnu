from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware


JS = r'''(()=>{
'use strict';
const PANEL_ID='ocAdvancedIntelligence';
const DIALOG_ID='ocTrainingReview';
let summary=null;
let loading=false;
const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const apiCall=(path,options)=>window.api(path,options);
const toast=message=>typeof window.showToast==='function'?window.showToast(String(message)):console.info(message);
function installStyle(){if(document.getElementById('oc-intelligence-style'))return;const style=document.createElement('style');style.id='oc-intelligence-style';style.textContent=`
#${PANEL_ID}{margin-top:18px}.oc-ai-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px}.oc-ai-control{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px;border:1px solid var(--border,rgba(255,255,255,.1));border-radius:14px}.oc-ai-control>span{display:grid;gap:4px}.oc-ai-control small{opacity:.68}.oc-ai-control select,.oc-ai-control input[type=number]{max-width:180px;min-height:38px;border-radius:10px;padding:6px 9px;background:var(--surface-2,rgba(255,255,255,.05));color:inherit;border:1px solid var(--border,rgba(255,255,255,.14))}.oc-ai-toggle{width:42px;height:24px;accent-color:currentColor}.oc-ai-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}.oc-ai-metrics{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.oc-ai-metric{padding:7px 10px;border-radius:999px;background:var(--surface-2,rgba(255,255,255,.06));font-size:12px}.oc-training-dialog{width:min(920px,calc(100vw - 28px));max-height:82vh;border:1px solid rgba(255,255,255,.14);border-radius:20px;padding:0;background:var(--surface,#101521);color:inherit;box-shadow:0 24px 80px rgba(0,0,0,.45)}.oc-training-dialog::backdrop{background:rgba(3,6,12,.68);backdrop-filter:blur(7px)}.oc-training-head{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;align-items:center;gap:14px;padding:18px 20px;background:var(--surface,#101521);border-bottom:1px solid rgba(255,255,255,.1)}.oc-training-body{padding:16px 20px 22px;display:grid;gap:12px;overflow:auto}.oc-training-row{display:grid;gap:9px;padding:14px;border:1px solid rgba(255,255,255,.1);border-radius:14px}.oc-training-row pre{white-space:pre-wrap;word-break:break-word;max-height:150px;overflow:auto;margin:0;padding:10px;border-radius:10px;background:rgba(0,0,0,.18);font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace}.oc-training-row .actions{display:flex;gap:8px;flex-wrap:wrap}.oc-training-empty{padding:24px;text-align:center;opacity:.72}@media(max-width:720px){.oc-ai-grid{grid-template-columns:1fr}.oc-ai-control{align-items:flex-start}.oc-ai-control select,.oc-ai-control input[type=number]{max-width:45vw}.oc-training-dialog{max-height:90vh}}
`;document.head.appendChild(style)}
function providerPage(){const body=document.getElementById('moduleBody');if(!body)return null;const text=body.textContent||'';if(!text.includes('Your AI providers')&&!text.includes('Choose and configure AI providers'))return null;return body}
function metric(label,value){return `<span class="oc-ai-metric"><strong>${esc(value)}</strong> ${esc(label)}</span>`}
function toggle(label,key,checked,help){return `<label class="oc-ai-control"><span><strong>${esc(label)}</strong><small>${esc(help)}</small></span><input class="oc-ai-toggle" type="checkbox" data-ai-setting="${esc(key)}" ${checked?'checked':''}></label>`}
function panelHtml(data){const s=data.settings||{},t=data.training||{},runtime=data.runtime||{};const statuses=t.by_status||{};return `<section class="oc-panel" id="${PANEL_ID}">
<div><strong>Advanced Intelligence</strong><p>Keep normal Vishnu as the default, or enable bounded multi-model reasoning only when you need it. Security, permissions, privacy and approvals always remain authoritative.</p></div>
<div class="oc-ai-grid">
${toggle('Advanced Intelligence','enabled',!!s.enabled,'Master switch. Off always uses Standard behavior.')}
<label class="oc-ai-control"><span><strong>Mode</strong><small>Standard, Smart, Deep or Research.</small></span><select data-ai-setting="mode">${['standard','smart','deep','research'].map(v=>`<option value="${v}" ${s.mode===v?'selected':''}>${v[0].toUpperCase()+v.slice(1)}</option>`).join('')}</select></label>
${toggle('Automatic escalation','auto_escalation',!!s.auto_escalation,'Escalate only when task complexity warrants it.')}
${toggle('Response verification','verification_enabled',s.verification_enabled!==false,'Check evidence and constraints without granting authority.')}
${toggle('Performance learning','performance_learning',s.performance_learning!==false,'Learn provider/model reliability by task; separate from Memory.')}
${toggle('Training candidate capture','training_capture',s.training_capture!==false,'Create governed candidates only when source policy allows it.')}
<label class="oc-ai-control"><span><strong>Maximum models</strong><small>Hard cap per deliberation request.</small></span><select data-ai-setting="max_models">${[1,2,3,4,5].map(v=>`<option value="${v}" ${Number(s.max_models||5)===v?'selected':''}>${v}</option>`).join('')}</select></label>
<label class="oc-ai-control"><span><strong>Latency preference</strong><small>Fast caps deliberation more aggressively.</small></span><select data-ai-setting="latency_preference">${['fast','balanced','quality'].map(v=>`<option value="${v}" ${s.latency_preference===v?'selected':''}>${v[0].toUpperCase()+v.slice(1)}</option>`).join('')}</select></label>
<label class="oc-ai-control"><span><strong>Per-request cost ceiling</strong><small>Optional owner ceiling; leave blank for existing budget policy.</small></span><input type="number" min="0.01" max="10000" step="0.01" value="${s.max_cost_per_request??''}" placeholder="Existing policy" data-ai-setting="max_cost_per_request"></label>
</div>
<div class="oc-ai-metrics">${metric('current mode',runtime.mode||s.mode||'standard')}${metric('training candidates',t.total||0)}${metric('eligible',t.eligible||0)}${metric('approved',statuses.approved||0)}${metric('performance profiles',(data.performance||[]).length)}</div>
<div class="oc-ai-actions"><button type="button" class="oc-button" data-ai-review>Review training candidates</button><button type="button" class="oc-button" data-ai-export>Export approved dataset</button></div>
<div class="oc-note">Training exports are owner-local JSONL + manifest files. Vishnu does not automatically publish them, and model output never gains tool or execution authority.</div>
</section>`}
async function loadSummary(){if(loading)return;loading=true;try{summary=await apiCall('/owner/intelligence/summary');mount()}catch(error){console.warn('Advanced Intelligence unavailable',error)}finally{loading=false}}
function mount(){installStyle();const body=providerPage();if(!body)return;let panel=document.getElementById(PANEL_ID);if(!summary){if(!panel){panel=document.createElement('section');panel.id=PANEL_ID;panel.className='oc-panel';panel.innerHTML='<strong>Advanced Intelligence</strong><p>Loading intelligence controls…</p>';const list=body.querySelector('.oc-list');(list?.parentNode||body).insertBefore(panel,list?.nextSibling||null)};loadSummary();return}const holder=document.createElement('div');holder.innerHTML=panelHtml(summary);const fresh=holder.firstElementChild;if(panel)panel.replaceWith(fresh);else{const list=body.querySelector('.oc-list');(list?.parentNode||body).insertBefore(fresh,list?.nextSibling||null)}bindPanel(fresh)}
async function saveSetting(target){const key=target.dataset.aiSetting;if(!key)return;let value;if(target.type==='checkbox')value=target.checked;else if(key==='max_models')value=Number(target.value);else if(key==='max_cost_per_request')value=target.value.trim()===''?null:Number(target.value);else value=target.value;target.disabled=true;try{const result=await apiCall('/owner/intelligence/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:value})});summary={...(summary||{}),settings:result.settings||summary?.settings};toast('Advanced Intelligence setting saved.')}catch(error){toast(error.message||'Could not save intelligence setting.');summary=null}finally{target.disabled=false;loadSummary()}}
function bindPanel(panel){panel.querySelectorAll('[data-ai-setting]').forEach(el=>el.addEventListener('change',()=>saveSetting(el)));panel.querySelector('[data-ai-review]')?.addEventListener('click',openTrainingReview);panel.querySelector('[data-ai-export]')?.addEventListener('click',exportDataset)}
function ensureDialog(){let dialog=document.getElementById(DIALOG_ID);if(dialog)return dialog;dialog=document.createElement('dialog');dialog.id=DIALOG_ID;dialog.className='oc-training-dialog';dialog.innerHTML=`<div class="oc-training-head"><div><strong>Training candidates</strong><small style="display:block;opacity:.65">Sanitized candidates only</small></div><button type="button" class="oc-button" data-training-close>Close</button></div><div class="oc-training-body"><div class="oc-training-empty">Loading…</div></div>`;document.body.appendChild(dialog);dialog.querySelector('[data-training-close]').addEventListener('click',()=>dialog.close());return dialog}
function candidateRow(c){const eligible=c.training_eligible===true;const reasons=(c.reason_codes||[]).join(', ')||'No blocking reason';return `<article class="oc-training-row" data-candidate-id="${esc(c.candidate_id)}"><div><strong>${esc(c.source_type||'candidate')}</strong> · ${esc(c.status||'pending')} · ${eligible?'eligible':'not eligible'}</div><small>Privacy: ${esc(c.privacy_level||'unknown')} · Provider: ${esc(c.provider_id||'unknown')} · Verification: ${esc(c.verifier_score??'not scored')}</small><small>${esc(reasons)}</small>${c.prompt!==undefined?`<pre><strong>Instruction</strong>\n${esc(c.prompt)}\n\n<strong>Response</strong>\n${esc(c.response)}</pre>`:''}<div class="actions">${eligible&&c.status==='pending'?`<button class="oc-button primary" data-candidate-approve="${esc(c.candidate_id)}">Approve</button>`:''}${c.status==='pending'?`<button class="oc-button" data-candidate-reject="${esc(c.candidate_id)}">Reject</button>`:''}${c.status!=='tombstoned'?`<button class="oc-button" data-candidate-delete="${esc(c.candidate_id)}">Remove</button>`:''}</div></article>`}
async function openTrainingReview(){const dialog=ensureDialog(),body=dialog.querySelector('.oc-training-body');body.innerHTML='<div class="oc-training-empty">Loading governed candidates…</div>';if(!dialog.open)dialog.showModal();try{const data=await apiCall('/owner/intelligence/training/candidates?limit=100&include_content=true');const rows=data.candidates||[];body.innerHTML=rows.length?rows.map(candidateRow).join(''):'<div class="oc-training-empty">No training candidates have been captured.</div>';bindCandidateActions(body)}catch(error){body.innerHTML=`<div class="oc-training-empty">${esc(error.message||'Candidates unavailable.')}</div>`}}
function bindCandidateActions(root){root.querySelectorAll('[data-candidate-approve]').forEach(btn=>btn.addEventListener('click',()=>candidateAction(btn,'approve')));root.querySelectorAll('[data-candidate-reject]').forEach(btn=>btn.addEventListener('click',()=>candidateAction(btn,'reject')));root.querySelectorAll('[data-candidate-delete]').forEach(btn=>btn.addEventListener('click',()=>candidateAction(btn,'delete')))}
async function candidateAction(button,action){const id=button.dataset.candidateApprove||button.dataset.candidateReject||button.dataset.candidateDelete;if(!id)return;button.disabled=true;try{let path='/owner/intelligence/training/candidates/'+encodeURIComponent(id),options={method:'DELETE'};if(action==='approve'){path+='/approve';options={method:'POST',body:'{}'}}else if(action==='reject'){path+='/reject';options={method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:'owner_rejected'})}}await apiCall(path,options);toast(`Training candidate ${action==='delete'?'removed':action+'d'}.`);summary=null;await openTrainingReview();loadSummary()}catch(error){toast(error.message||'Training candidate action failed.');button.disabled=false}}
async function exportDataset(){try{const result=await apiCall('/owner/intelligence/training/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset_name:'vishnu-general',limit:10000})});const exp=result.export||{};toast(`Exported ${exp.records||0} approved training records locally.`);summary=null;loadSummary()}catch(error){toast(error.message||'Dataset export failed.')}}
const observer=new MutationObserver(()=>{if(providerPage()&&!document.getElementById(PANEL_ID))mount()});observer.observe(document.documentElement,{childList:true,subtree:true});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();'''


class OwnerIntelligenceUiMiddleware(BaseHTTPMiddleware):
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
        script = '<script src="/iphone/owner-intelligence-ui.js"></script>'
        if marker in text and script not in text:
            text = text.replace(marker, script + marker, 1)
        headers = {
            key: value for key, value in response.headers.items()
            if key.lower() not in {'content-length', 'content-encoding'}
        }
        return Response(text, status_code=response.status_code, headers=headers, media_type='text/html')


def owner_intelligence_ui_router() -> APIRouter:
    router = APIRouter()

    @router.get('/iphone/owner-intelligence-ui.js', include_in_schema=False)
    def owner_intelligence_js():
        return Response(JS, media_type='application/javascript', headers={'Cache-Control': 'no-cache'})

    return router
