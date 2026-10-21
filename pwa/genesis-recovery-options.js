/* Vishnu 2.0 P1-07/P1-08 recovery choice and verification presentation.
   Distinct authorities: one-use owner recovery codes vs. authenticated .vdr/.vrk data restore.
   Browser selection carries only a non-secret mode and never issues device trust. */
import {mountNeuralSphere} from '/iphone/genesis-neural-sphere.js';
const svg=p=>'<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">'+p+'</svg>';
const globe=svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c-5 6-5 12 0 18m0-18c5 6 5 12 0 18"/>');
const key=svg('<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9m-3 3 3 3m-6 0 3 3"/>');
const database=svg('<ellipse cx="12" cy="5.5" rx="8" ry="3.5"/><path d="M4 5.5v7c0 1.9 3.6 3.5 8 3.5s8-1.6 8-3.5v-7M4 12.5v6c0 2 3.6 3.5 8 3.5s8-1.5 8-3.5v-6"/>');
const phone=svg('<rect x="6" y="2" width="12" height="20" rx="2"/><path d="M10 19h4"/>');
const shield=svg('<path d="M12 2 4 5v6c0 5 3.4 9.7 8 11 4.6-1.3 8-6 8-11V5z"/><path d="m9 12 2 2 4-5"/>');
const arrow=svg('<path d="M4 12h16m-6-6 6 6-6 6"/>');
const chevron=svg('<path d="m9 5 7 7-7 7"/>');
const modes=[
 {id:'recover_login',title:'Recover My Login',description:'Use your recovery codes to regain access to your Vishnu account.',icon:key},
 {id:'restore_data',title:'Restore My Data',description:'Restore your data from an encrypted backup file or another trusted device.',icon:database},
 {id:'replacement_device',title:'Set Up on a New Device',description:"I've lost or replaced a device and want to recover Vishnu on this new device.",icon:phone},
];
function markup(mode,verify,options){
 const option=modes.find(item=>item.id===mode)||modes[0];
 const backupAvailable=Boolean(options?.restore_available&&!options?.restore_setup_in_progress);
 const optionsMarkup=modes.map(m=>`<button type="button" class="vo-choice ${m.id===mode?'selected':''}" role="radio" data-vo-mode="${m.id}" aria-checked="${m.id===mode}" tabindex="${m.id===mode?0:-1}">
  <span class="vo-icon">${m.icon}</span><span class="vo-choice-text"><strong>${m.title}</strong><small>${m.description}</small></span>
  <span class="vo-chevron">${arrow}</span></button>`).join('');
 const verifyDescription=mode==='restore_data'?
   'Verify your encrypted recovery package and its separate recovery key. Recovery codes cannot restore lost data.':
   mode==='replacement_device'?
   'Verify a valid, unused owner recovery code to authorize this replacement browser. Revoke lost devices separately after signing in.':
   'Enter one unused recovery code. Vishnu verifies and consumes the code before restoring account access.';
 return `<div class="vo-window-dots" aria-hidden="true"><i></i><i></i><i></i></div>
 <header class="vs-header vo-header"><div class="vs-brand"><span class="vs-logo" aria-hidden="true"><span></span></span>
   <div><strong>Vishnu 2.0</strong><small>Your Personal AI Companion</small></div></div>
  <div class="vo-header-actions"><button class="vs-language" data-vo-language type="button" aria-haspopup="dialog">${globe} English ⌄</button>
   <span class="vo-badge">P1-${verify?'08':'07'}</span></div></header>
 <div class="vs-body vo-body"><div class="vs-hero vo-hero" aria-hidden="true">
  <div class="vw-sphere vs-sphere vo-sphere"><canvas data-vo-sphere data-neural-emphasis="login"></canvas></div>
  <div class="vs-ground vo-ground"><span></span></div></div>
 <div class="vo-right"><section class="vo-panel" aria-label="${verify?'Recovery verification':'Recovery options'}">
  <p class="vs-eyebrow vo-eyebrow">${verify?'RECOVERY VERIFICATION · P1-08':'RECOVERY · P1-07'}</p>
  <h1>${verify?'<span>Verify</span> Your Recovery':'Recovery <span>Options</span>'}</h1>
  <p class="vo-description">${verify?verifyDescription:'Choose what you want to recover. You can regain access to your Vishnu, restore your data or set up a new device.'}</p>
  ${verify?
  `<div class="vo-verify-card"><span class="vo-icon">${option.icon}</span><span><strong>${option.title}</strong><small>${mode==='restore_data'?'Encrypted backup verification':'One-time recovery code verification'}</small></span></div>
    ${mode==='restore_data'?`
    <div class="vo-verify-info"><strong>${backupAvailable?'Encrypted restore is available':'Encrypted restore requires an eligible new runtime'}</strong>
      <p>${backupAvailable?'Choose the secure restore process to supply your .vdr archive, separate .vrk key and recovery passphrase. Vishnu verifies materials before any data changes.':'This runtime does not currently permit encrypted data restoration. Open Vishnu on an eligible uninitialized runtime or use the supported recovery flow there. No data will be overwritten here.'}</p>
      <p>Transfer from another trusted device is not implemented in this PWA.</p></div>
    ${backupAvailable?'<button class="vo-backup-action" type="button" data-vo-backup>Open Secure Backup Verification →</button>':''}`
    :`<form id="voVerifyForm" novalidate><label for="voRecoveryCode">One-time recovery code</label>
     <div class="vo-input-line">${key}<input id="voRecoveryCode" name="recoveryCode" type="text" autocapitalize="characters" autocomplete="one-time-code" autocorrect="off" spellcheck="false" maxlength="64" placeholder="Enter your saved recovery code" required></div>
     <p class="vo-form-help">Each code can be used once. This restores sign-in access, not lost encrypted files.</p>
     ${mode==='replacement_device'?'<p class="vo-form-help">Vishnu does not automatically revoke your old device. Review trusted devices after authentication.</p>':''}
     <button class="vo-backup-action" type="submit" data-vo-submit>Verify and Continue ${arrow}</button></form>`}
   </div>`
  :`<div class="vo-choices" role="radiogroup" aria-label="Choose recovery option">${optionsMarkup}</div>
   <div class="vo-info">${shield}<span><strong>Your data stays secure</strong><small>One-time codes recover access; encrypted backups restore available data. Vishnu verifies each method before granting access or changing data.</small></span></div>`}
  <p class="vo-status" id="voStatus" role="status" aria-live="polite"></p>
 </section></div></div>
 <footer class="vo-footer"><button type="button" class="vo-back" data-vo-back>← <span>Back</span></button>
   <button type="button" class="vo-continue" data-vo-continue>${verify?'Change Method':'Continue'} ${arrow}</button></footer>
 <dialog class="vs-dialog" id="voLanguageDialog"><h2>Language</h2><p>English is currently supported for secure recovery.</p><button type="button" data-vo-language-close>Close</button></dialog>`;
}
function mount(root,{mode='recover_login',verify=false,options={},onBack,onContinue,onVerifyCode,onRestore}){
 if(!root)return()=>{};
 root.innerHTML=markup(mode,verify,options);
 const $=s=>root.querySelector(s);
 let busy=false,disposed=false;
 const status=$('#voStatus');
 const say=(value,error=false)=>{if(disposed)return;status.textContent=value;status.dataset.error=String(error);};
 function choose(next){
  mode=next;
  root.querySelectorAll('[data-vo-mode]').forEach(btn=>{
   const yes=btn.dataset.voMode===mode;btn.classList.toggle('selected',yes);btn.setAttribute('aria-checked',String(yes));btn.tabIndex=yes?0:-1;
  });
  say('');
 }
 if(!verify){
  for(const btn of root.querySelectorAll('[data-vo-mode]')){
   btn.addEventListener('click',()=>choose(btn.dataset.voMode));
   btn.addEventListener('keydown',event=>{
    if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();
    const ids=modes.map(item=>item.id);
    const current=ids.indexOf(btn.dataset.voMode);
    const next=event.key==='Home'?0:event.key==='End'?ids.length-1:
      (current+(event.key==='ArrowDown'||event.key==='ArrowRight'?1:-1)+ids.length)%ids.length;
    choose(ids[next]);$('[data-vo-mode="'+ids[next]+'"]').focus();
   });
  }
 }
 const disable=(val)=>{busy=val;for(const btn of root.querySelectorAll('button:not([data-vo-language-close])'))btn.disabled=val;};
 $('[data-vo-back]').addEventListener('click',()=>{if(!busy)onBack();});
 $('[data-vo-continue]').addEventListener('click',()=>{if(!busy)onContinue(verify?mode:mode);});
 const verifyCode=async(event)=>{
  event.preventDefault();if(busy)return;
  const input=$('#voRecoveryCode');
  const code=input.value.trim().toUpperCase();
  if(!code){say('Enter one unused recovery code.',true);input.focus();return;}
  if(!/^[A-Z0-9-]{8,64}$/.test(code)){say('Check the recovery code format and try again.',true);input.focus();return;}
  input.value='';disable(true);say('Verifying your recovery code securely…');
  try{await onVerifyCode({code,mode});}
  catch(err){say(err?.message||'Verification failed. No account access was granted.',true);}
  finally{if(!disposed)disable(false);}
 };
 $('#voVerifyForm')?.addEventListener('submit',verifyCode);
 $('[data-vo-backup]')?.addEventListener('click',async()=>{
  if(busy)return;disable(true);say('Opening verified encrypted recovery…');
  try{await onRestore();}
  catch(err){say(err?.message||'Secure restore is not available on this runtime.',true);if(!disposed)disable(false);}
 });
 $('[data-vo-language]').addEventListener('click',()=>$('#voLanguageDialog').showModal());
 $('[data-vo-language-close]').addEventListener('click',()=>$('#voLanguageDialog').close());
 let unmount=()=>{};
 try{unmount=mountNeuralSphere($('[data-vo-sphere]'));}
 catch{$('[data-vo-sphere]')?.parentElement?.classList.add('vw-static-fallback');}
 return()=>{disposed=true;if($('#voLanguageDialog')?.open)$('#voLanguageDialog').close();unmount?.();};
}
export function mountRecoveryOptionsScreen(root,options,callbacks){return mount(root,{...callbacks,options,verify:false});}
export function mountRecoveryVerificationScreen(root,mode,options,callbacks){return mount(root,{...callbacks,options,verify:true,mode});}
