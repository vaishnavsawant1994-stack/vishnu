/* Vishnu 2.0 P1-06 - device joining: never creates trust in the browser.
   The canonical owner/password/WebAuthn + DeviceRegistry join endpoints decide.
   QR/code/link methods are explicitly unavailable until a governed protocol exists. */
import {mountNeuralSphere} from '/iphone/genesis-neural-sphere.js';
const svg=p=>'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+p+'</svg>';
const globe=svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c-5 6-5 12 0 18m0-18c5 6 5 12 0 18"/>');
const laptop=svg('<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M1 20h22"/>');
const shield=svg('<path d="M12 2 4 5v6c0 5 3.4 9.7 8 11 4.6-1.3 8-6 8-11V5z"/><path d="m9 12 2 2 4-5"/>');
const key=svg('<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9m-3 3 3 3m-6 0 3 3"/>');
const chain=svg('<path d="m10 13 4-4M8 17H7a5 5 0 0 1 0-10h3m4 0h3a5 5 0 0 1 0 10h-3"/>');
const person=svg('<circle cx="12" cy="7" r="4"/><path d="M4 22v-3a8 8 0 0 1 16 0v3"/>');
const arrow=svg('<path d="M5 12h14m-6-6 6 6-6 6"/>');
const chevron=svg('<path d="m9 5 7 7-7 7"/>');
const qr=svg('<rect x="2" y="2" width="8" height="8"/><path d="M4 4h4v4H4zM14 2h8v8h-8zM16 4h4v4h-4zM2 14h8v8H2zM4 16h4v4H4zM14 14h2v2m4-2h2v2m-8 4h3v2m3-3h2v3m-5-6v3"/>');
const escapeHTML=v=>String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const methods=[
 {id:'qr',title:'Use a QR Code',desc:'Open Vishnu on one of your trusted devices and scan a securely issued pairing code.',icon:qr},
 {id:'approval',title:'Request Approval',desc:'Verify your account, then approve the new device from an existing trusted device.',icon:laptop},
 {id:'code',title:'Use a Pairing Code',desc:'Enter a short-lived one-time code supplied through a supported trusted-device pairing service.',icon:key},
 {id:'link',title:'Use a Secure Link',desc:'Open an authorized, single-use device pairing link on a trusted device.',icon:chain},
 {id:'account',title:'Sign in with Your Account',desc:'Use your existing Vishnu password or passkey; new devices still require approval.',icon:person},
];
const notReady={
 qr:'QR pairing is not supported by this runtime yet. No QR or pairing token was issued. Use verified account sign-in and trusted-device approval instead.',
 code:'This runtime does not yet issue or redeem one-time pairing codes. Do not enter an unrelated recovery code here. Use account sign-in.',
 link:'This runtime has no approved single-use pairing-link protocol yet. Use account sign-in and trusted-device approval.',
};
function shell(join){
 const pending=Boolean(join?.request_id);
 const label=pending?'Approval':'Choose Method';
 const methodMarkup=methods.map(m=>{
 const unavailable=Boolean(notReady[m.id]);
 return `<button class="vc-method ${m.id==='qr'?'selected':''}" type="button" role="radio" aria-checked="${m.id==='qr'}" data-vc-method="${m.id}">
   <span class="vc-symbol ${m.id==='qr'?'vc-qr-symbol':''}">${m.icon}
    ${m.id==='qr'?'<small>QR pairing<br>not issued</small>':''}</span>
   <span class="vc-method-copy"><span class="vc-method-title">${m.title}
     ${m.id==='qr'?'<small class="vc-pill">Reference option</small>':''}</span>
    <span class="vc-method-desc">${m.desc}</span>
    ${unavailable?'<small class="vc-unsupported">Requires a supported pairing service</small>':''}</span>
    <span class="vc-method-chevron">${chevron}</span>
 </button>`}).join('');
 return `<header class="vs-header vc-header">
  <div class="vs-brand"><span class="vs-logo" aria-hidden="true"><span></span></span><div><strong>Vishnu 2.0</strong><small>Your Personal AI Companion</small></div></div>
  <ol class="vs-progress vc-progress" aria-label="Device joining journey">
    <li class="${pending?'complete':''}"><span class="vs-step">${pending?'✓':'1'}</span><span>Choose</span></li>
    <li class="${pending?'complete':''}"><span class="vs-step">${pending?'✓':'2'}</span><span>Verify Owner</span></li>
    <li ${pending?'aria-current="step"':''}><span class="vs-step">3</span><span>Approval</span></li>
    <li><span class="vs-step">4</span><span>Connected</span></li>
  </ol>
  <button type="button" class="vs-language" data-vc-language aria-haspopup="dialog">${globe} English <span aria-hidden="true">⌄</span></button>
 </header>
 <div class="vs-body vc-body">
 <div class="vs-hero vc-hero" aria-hidden="true"><div class="vw-sphere vs-sphere vc-sphere">
  <canvas data-vc-sphere data-neural-emphasis="login"></canvas></div><div class="vs-ground vc-ground"><span></span></div>
  <button type="button" class="vc-back vc-desktop-back" data-vc-back>← <span>Back</span></button></div>
 <section class="vc-panel" aria-label="Connect this device">
  <p class="vs-eyebrow vc-eyebrow">${pending?'AWAITING APPROVAL':'DEVICE JOIN · P1-06'}</p>
  <h1>Connect This <span>Device</span></h1>
  <p class="vc-description">Join your existing Vishnu and get approval from a trusted device.</p>
  <div class="vc-methods" role="radiogroup" aria-label="Connection method">${methodMarkup}</div>
  <section class="vc-request ${pending?'':'hidden'}" aria-live="off" aria-label="Authorized join request">
   <strong>Your verified join request</strong>
   <p>On an existing trusted device, open Settings → Devices, compare the code, and approve or deny this exact request. Approval also requires owner-password verification.</p>
   <div class="vc-code-row"><span>Verification code</span><strong id="vcVerificationCode">${escapeHTML(pending?join.verification_code:'')}</strong></div>
   <p id="vcExpiry" class="vc-expiry" role="status">Checking expiry…</p>
   <p class="vc-join-name">${escapeHTML(join?.name||'New web browser')}</p>
   <p class="vc-join-help">Requests appear in the trusted-device queue. No push notification or QR code is claimed.</p>
  </section>
  <div class="vc-trust">${shield}<span><strong>This device will be added as a trusted device only after approval</strong><small>It receives separate revocable credentials and permissions once Vishnu verifies the approved request.</small></span></div>
  <p class="vc-status" id="vcStatus" role="status" aria-live="polite"></p>
  <div class="vc-nav"><button type="button" class="vc-back vc-mobile-back" data-vc-back>← Back</button>
   <button type="button" class="vc-continue" data-vc-continue>${pending?'Check Approval':'Continue'} ${arrow}</button></div>
 </section></div>
 <dialog class="vs-dialog" id="vcLanguageDialog" aria-labelledby="vcLanguageTitle"><h2 id="vcLanguageTitle">Language</h2><p>English is available for secure device joining on this runtime.</p><button type="button" data-vc-language-close>Close</button></dialog>`;
}
export function mountConnectScreen(root,join,{onBack,onAuthenticate,onCheck,onComplete}){
 if(!root)return()=>{};
 root.innerHTML=shell(join);
 const $=selector=>root.querySelector(selector);
 let selected='qr',disposed=false,checking=false,timer=0,clock=0;
 const status=$('#vcStatus');const pending=Boolean(join?.request_id);
 const say=(message,error=false)=>{if(disposed)return;status.textContent=message;status.dataset.error=String(error);};
 function choose(id){
  selected=id;
  root.querySelectorAll('[data-vc-method]').forEach(el=>{
   const active=el.dataset.vcMethod===id;el.classList.toggle('selected',active);el.setAttribute('aria-checked',String(active));el.tabIndex=active?0:-1;
  });
  if(notReady[id])say(notReady[id],true);
  else if(id==='approval')say(pending?'Your request is waiting for trusted-device approval.':'First verify your Vishnu credentials to create a real device approval request.');
  else say(pending?'Awaiting verified approval from a trusted device.':'Your Vishnu credentials will be verified first. A new device cannot become trusted automatically.');
 }
 root.querySelectorAll('[data-vc-method]').forEach(el=>{
  el.addEventListener('click',()=>choose(el.dataset.vcMethod));
  el.addEventListener('keydown',event=>{
   if(!['ArrowRight','ArrowLeft','Home','End'].includes(event.key))return;
   event.preventDefault();
   const all=methods.map(m=>m.id);
   const next=event.key==='Home'?0:event.key==='End'?all.length-1:
     (all.indexOf(el.dataset.vcMethod)+(event.key==='ArrowRight'?1:-1)+all.length)%all.length;
   choose(all[next]);root.querySelector('[data-vc-method="'+all[next]+'"]').focus();
  });
 });
 if(pending)choose('approval');else choose('qr');
 function expiry(){
  if(disposed||!pending)return;
  const remaining=Math.ceil(Number(join.expires_at)-Date.now()/1000);
  if(!Number.isFinite(remaining)){ $('#vcExpiry').textContent='Expiration unknown; reauthentication may be needed.';return;}
  if(remaining<=0){$('#vcExpiry').textContent='Join request expired. Start a new verified sign-in.';say('This request expired. No device was connected.',true);clearTimeout(timer);return;}
  $('#vcExpiry').textContent='Expires in '+Math.floor(remaining/60)+':'+String(remaining%60).padStart(2,'0');
 }
 if(pending){expiry();clock=setInterval(expiry,1000);}
 async function poll(){
  if(disposed||!pending||checking)return;
  checking=true;
  try{
   const result=await onCheck(join.request_id);
   if(disposed)return;
   if(result?.status==='complete'){
    clearTimeout(timer);clearInterval(clock);
    say('Vishnu confirmed the approval. Verifying this device session…');
    await onComplete();
    return;
   }
   if(result?.status==='denied'||result?.status==='expired'||result?.status==='completed'){
    clearTimeout(timer);clearInterval(clock);
    say(result.status==='denied'?'The trusted owner denied this request. No device was added.':'This join request is no longer active. Sign in again.',true);
    $('#vcExpiry').textContent='Request '+result.status;return;
   }
   if(result?.status==='pending'||result?.status==='approved'){
    say('Waiting for an existing trusted device to verify and approve this request.');
   }else say('The device approval status could not be confirmed.',true);
  }catch(err){
   if(!disposed)say(err?.message||'Cannot check approval. You can retry.',true);
  }finally{checking=false;}
 }
 async function checkAndSchedule(){
  if(disposed||!pending)return;
  await poll();
  if(!disposed && !status.textContent.match(/denied|expired|no longer active/i) && Number(join.expires_at)>Date.now()/1000)
   timer=setTimeout(checkAndSchedule,3000);
 }
 if(pending)timer=setTimeout(checkAndSchedule,1200);
 $('[data-vc-continue]').addEventListener('click',()=>{
  if(pending){void poll();return;}
  if(notReady[selected]){say(notReady[selected]+' Select Request Approval or Sign in with Your Account to continue.',true);return;}
  onAuthenticate();
 });
 root.querySelectorAll('[data-vc-back]').forEach(btn=>btn.addEventListener('click',()=>onBack()));
 $('[data-vc-language]').addEventListener('click',()=>$('#vcLanguageDialog').showModal());
 $('[data-vc-language-close]').addEventListener('click',()=>$('#vcLanguageDialog').close());
 let unmount=()=>{};
 try{unmount=mountNeuralSphere($('[data-vc-sphere]'));}
 catch{$('[data-vc-sphere]')?.parentElement?.classList.add('vw-static-fallback');}
 return()=>{disposed=true;clearTimeout(timer);clearInterval(clock);if($('#vcLanguageDialog')?.open)$('#vcLanguageDialog').close();unmount?.();};
}
