/* P1-04 — one-time owner recovery ceremony.
   The backend generates and hashes codes; this module never invents codes.
   Plaintext lives in an in-memory, authorized one-time reveal only. */
import { mountNeuralSphere } from '/iphone/genesis-neural-sphere.js';
const svg=(path)=>'<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+path+'</svg>';
const key=svg('<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9m-3 3 3 3m-6 0 3 3"/>');
const copy=svg('<rect x="8" y="7" width="12" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h2"/>');
const download=svg('<path d="M12 2v13m-5-5 5 5 5-5M4 17v4h16v-4"/>');
const shield=svg('<path d="M12 2 3 6v6c0 5.2 3 8.8 9 10 6-1.2 9-4.8 9-10V6L12 2Z"/><path d="m8 12 3 3 5-6"/>');
const globe=svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c-5 6-5 12 0 18m0-18c5 6 5 12 0 18"/>');
const rotate=svg('<path d="M20 11a8 8 0 0 0-14-5L4 8m0-6v6h6m-6 5a8 8 0 0 0 14 5l2-2m0 6v-6h-6"/>');
const arrow=svg('<path d="M4 12h16m-6-6 6 6-6 6"/>');
function template(){
 return `<header class="vs-header">
 <div class="vs-brand"><span class="vs-logo" aria-hidden="true"><span></span></span><div><strong>Vishnu 2.0</strong><small>Your Personal AI Companion</small></div></div>
 <ol class="vs-progress" aria-label="Onboarding steps">
  <li class="complete"><span class="vs-step">✓</span><span>Welcome</span></li>
  <li class="complete"><span class="vs-step">✓</span><span>Your Name</span></li>
  <li class="complete"><span class="vs-step">✓</span><span>Security</span></li>
  <li aria-current="step"><span class="vs-step">4</span><span>Recovery</span></li>
 </ol>
 <button type="button" class="vs-language" data-vr-language aria-haspopup="dialog">${globe} English <span aria-hidden="true">⌄</span></button></header>
 <div class="vs-body">
  <div class="vs-hero" aria-hidden="true"><div class="vw-sphere vs-sphere"><canvas data-vr-sphere data-neural-emphasis="security"></canvas></div><div class="vs-ground"><span></span></div></div>
  <section class="vs-main vr-main" aria-label="Recovery codes and quick review">
   <p class="vs-eyebrow">STEP 4 OF 4</p>
   <h1>Save Your <span>Recovery Codes</span></h1>
   <p class="vs-description">These codes help you restore Vishnu if you lose your device<br class="vr-desktop-break"> or can’t access your sign-in method. Keep them safe and private.</p>
   <div class="vr-panel">
    <div class="vr-card-head"><div class="vr-card-title">${key}<strong>Your Recovery Codes</strong></div>
      <button type="button" class="vr-new" data-vr-regenerate>${rotate}<span>Generate New Codes</span></button></div>
    <div id="firstRunCodes" class="vr-code-grid" role="group" aria-label="One-time recovery codes"></div>
    <div class="vr-code-actions"><button type="button" class="vr-download" data-vr-download>${download}<span><strong>Download as a File</strong><small>Save recovery codes, not a data backup</small></span></button>
      <button type="button" class="vr-copy-all" data-vr-copy-all>${copy}<span><strong>Copy All Codes</strong><small>Copy to clipboard</small></span></button></div>
    <section class="vr-warning" aria-label="Important recovery code safety guidance">${shield}<div><strong>Important</strong>
      <ul><li>Keep these codes private and safe.</li>
          <li>Anyone with an unused code may be able to recover your account.</li>
          <li>Store codes separately from this device, if possible.</li>
          <li>Recovery codes restore access, not lost encrypted data.</li></ul></div></section>
    <label class="vr-ack"><input type="checkbox" id="firstRunRecoverySaved"><span>I have saved my recovery codes and understand their importance.</span></label>
    <button type="button" class="vr-review-trigger" data-vr-review>Review setup <span aria-hidden="true">⌄</span></button>
   </div>
   <div class="vs-navigation vr-nav"><button type="button" class="vs-back" data-vr-back>← <span>Back</span></button>
    <button type="button" class="vs-continue" data-genesis-next><span>Continue to Vishnu</span>${arrow}</button></div>
   <p id="genesisStatus" class="vs-status vr-status" role="status" aria-live="polite"></p>
  </section>
 </div>
 <dialog class="vs-dialog vr-dialog" id="vrRegenerateDialog" aria-labelledby="vrRegenerateTitle">
  <h2 id="vrRegenerateTitle">Replace your recovery codes?</h2>
  <p>Your existing recovery codes will immediately stop working. Save the new set before completing Vishnu setup.</p>
  <div class="vr-dialog-actions"><button type="button" data-vr-cancel>Cancel</button><button type="button" data-vr-confirm class="vr-danger">Replace Codes</button></div>
 </dialog>
 <dialog class="vs-dialog vr-dialog" id="vrReviewDialog" aria-labelledby="vrReviewTitle">
  <h2 id="vrReviewTitle">Review your Vishnu setup</h2><dl id="vrReviewRows"></dl>
  <p class="vr-review-help">Your password, passkey secrets and recovery codes are not shown here. You can update your profile and device label after setup.</p>
  <button type="button" data-vr-review-close>Close Review</button>
 </dialog>
 <dialog class="vs-dialog vr-dialog" id="vrLanguageDialog"><h2>Language</h2>
  <p>English is currently available for secure setup. Additional languages will appear when supported.</p>
  <button type="button" data-vr-language-close>Close</button></dialog>`;
}
const validCodes=state=>Array.isArray(state.recoveryCodes)?
  state.recoveryCodes.filter(c=>typeof c==='string'&&/^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$/.test(c)):[];
const numbered=(codes)=>codes.map((c,i)=>String(i+1).padStart(2,'0')+'  '+c).join('\n');
function fillReview(root,state){
 const rows=root.querySelector('#vrReviewRows');rows.replaceChildren();
 const items=[
  ['Owner name',[state.firstName,state.lastName].filter(Boolean).join(' ')||'Not available'],
  ['Display name',state.displayName||'Use owner name'],
  ['First trusted device',state.deviceName||'Registered first device'],
  ['Sign-in methods',state.passkeyCreated?'Password and passkey':'Password'],
  ['Recovery readiness',root.querySelector('#firstRunRecoverySaved').checked?'Codes saved (confirmed)':'Waiting for your confirmation'],
  ['Privacy and data', 'Device only · no automatic cloud sync'],
  ['AI provider','Not configured (you can add one later)'],
 ];
 for(const [name,value] of items){
  const dt=document.createElement('dt'),dd=document.createElement('dd');
  dt.textContent=name;dd.textContent=value;rows.append(dt,dd);
 }
}
function downloadText(content){
 const blob=new Blob([content],{type:'text/plain;charset=utf-8'});
 const url=URL.createObjectURL(blob);
 try{
  const anchor=document.createElement('a');
  anchor.href=url;anchor.download='Vishnu-Recovery-Codes.txt';
  document.body.appendChild(anchor);anchor.click();anchor.remove();
 }finally{
  // Let the browser download begin before revoking the one-use blob URL.
  setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
}
export function mountRecoveryScreen(root,state,{onBack,onFinish,onRegenerate}){
 if(!root)return()=>{};
 root.innerHTML=template();
 const $=s=>root.querySelector(s);
 const messages=$('#genesisStatus'), checkbox=$('#firstRunRecoverySaved');
 const finishButton=$('[data-genesis-next]'), back=$('[data-vr-back]');
 const controls=['[data-vr-regenerate]','[data-vr-download]','[data-vr-copy-all]'];
 let pending=false,disposed=false;
 const say=(message,isError=false)=>{
   if(disposed)return;
   messages.textContent=message;
   messages.dataset.error=isError?'true':'false';
 };
 const codes=()=>validCodes(state);
 const allowed=()=>codes().length>0&&!pending;
 const grid=$('#firstRunCodes');
 function renderCodes(){
   grid.replaceChildren();
   const values=codes();
   if(!values.length){
     const notice=document.createElement('p');
     notice.className='vr-missing';
     notice.textContent='Recovery codes are not available for display. They were shown only once. If you did not save them, explicitly generate a new set before finishing setup.';
     grid.append(notice);
   } else {
     values.forEach((code,i)=>{
       const container=document.createElement('div');
       container.className='vr-code';
       const number=document.createElement('span');number.className='vr-number';number.textContent=String(i+1).padStart(2,'0');
       const text=document.createElement('code');text.textContent=code;
       const btn=document.createElement('button');btn.type='button';btn.className='vr-copy';
       btn.setAttribute('aria-label','Copy recovery code '+(i+1));
       btn.innerHTML=copy;
       btn.addEventListener('click',()=>{void copyText(code,'Recovery code '+(i+1)+' copied.');});
       container.append(number,text,btn);grid.append(container);
     });
   }
   for(const selector of controls) {
     const el=$(selector);
     if(el && selector!=='[data-vr-regenerate]')el.disabled=!values.length;
   }
 }
 const lock=(isBusy)=>{
   pending=isBusy;
   for(const selector of [...controls,'[data-vr-back]','[data-genesis-next]','[data-vr-review]']){
     const element=$(selector);
     if(element)element.disabled=isBusy;
   }
   for(const btn of grid.querySelectorAll('button'))btn.disabled=isBusy;
   checkbox.disabled=isBusy;
 };
 async function copyText(value,success){
   if(pending)return;
   try{
     if(!navigator.clipboard?.writeText)throw new Error('Clipboard permission unavailable');
     await navigator.clipboard.writeText(value);say(success);
   }catch{say('Clipboard access was blocked. You can use Download as a File instead.',true);}
 }
 renderCodes();
 checkbox.checked=false; // Never pre-confirm a newly revealed or regenerated set.
 checkbox.addEventListener('change',()=>{state.recoverySaved=checkbox.checked;say('');});
 for(const button of grid.querySelectorAll('.vr-copy'))button.disabled=false;
 $('[data-vr-copy-all]').addEventListener('click',()=>{
   if(allowed())void copyText(numbered(codes()),'All recovery codes copied. Keep your clipboard private.');
 });
 $('[data-vr-download]').addEventListener('click',()=>{
   if(!allowed())return;
   try{
     const body=['Vishnu Recovery Codes','Generated: '+new Date().toISOString(),'',
       'Each code can be used once. Store privately, preferably separate from your device.',
       'Recovery codes help restore account access; they are NOT an encrypted data backup.','',
       numbered(codes()),''].join('\n');
     downloadText(body);say('Recovery-code file prepared. Confirm that you saved it securely.');
   }catch{say('Your browser could not save the file. Copy the codes to a secure location instead.',true);}
 });
 const regen=$('#vrRegenerateDialog');
 $('[data-vr-regenerate]').addEventListener('click',()=>{if(!pending)regen.showModal();});
 $('[data-vr-cancel]').addEventListener('click',()=>regen.close());
 $('[data-vr-confirm]').addEventListener('click',async()=>{
   if(pending)return;
   regen.close();lock(true);say('Requesting new recovery codes…');
   try{
     const next=await onRegenerate();
     if(!Array.isArray(next)||next.length===0)throw new Error('The new recovery codes were not returned.');
     state.recoveryCodes=next;
     state.recoverySaved=false;checkbox.checked=false;renderCodes();
     say('Previous codes were invalidated. Save these replacement codes and acknowledge them again.');
   }catch(e){
     // If the network dropped after the server rotated codes, the old set
     // cannot safely be presented as current. Require explicit regeneration.
     state.recoveryCodes=[];state.recoverySaved=false;checkbox.checked=false;renderCodes();
     const needsOwner = Boolean(root.querySelector('[data-setup-device-reauth]'));
     say(needsOwner
       ? 'Verify your owner password in “Restore this browser’s setup access” below, then generate new recovery codes once. Earlier codes may be invalid.'
       : 'Could not verify the replacement codes. Older codes may be invalid. Retry Generate New Codes.',true);
   }finally{lock(false);}
 });
 const review=$('#vrReviewDialog');
 $('[data-vr-review]').addEventListener('click',()=>{
   fillReview(root,state);review.showModal();
 });
 $('[data-vr-review-close]').addEventListener('click',()=>review.close());
 $('[data-vr-back]').addEventListener('click',()=>{if(!pending)onBack();});
 finishButton.addEventListener('click',async()=>{
   if(pending)return;
   if(!codes().length){say('A new one-time recovery-code set must be saved before continuing.',true);return;}
   if(!checkbox.checked){say('Save your codes in a secure location, then check the acknowledgement box.',true);checkbox.focus();return;}
   lock(true);say('Finishing your secure Vishnu setup…');
   try{
     await onFinish();
     state.recoveryCodes=[];state.recoverySaved=false;
     checkbox.checked=false;renderCodes();
     say('Vishnu setup confirmed. Opening your home.');
   }catch(e){say(e?.message||'Vishnu could not finish setup. Your recovery codes have not been regenerated.',true);}
   finally{lock(false);}
 });
 $('[data-vr-language]').addEventListener('click',()=>$('#vrLanguageDialog').showModal());
 $('[data-vr-language-close]').addEventListener('click',()=>$('#vrLanguageDialog').close());
 let dispose=()=>{};
 try{dispose=mountNeuralSphere($('[data-vr-sphere]'));}
 catch{$('[data-vr-sphere]')?.parentElement?.classList.add('vw-static-fallback');}
 return ()=>{
   disposed=true;
   // Close dialogs if routing away; renderCodes is never reused on a new screen.
   for(const dialog of root.querySelectorAll('dialog'))if(dialog.open)dialog.close();
   dispose?.();
   grid.replaceChildren();
 };
}
