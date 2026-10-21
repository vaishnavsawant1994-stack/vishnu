/* P1-08 — screenshot-led recovery verification.
 * Two genuine, mutually exclusive authorities:
 *  - owner one-use 4-4-4 code, displayed as six 2-character boxes
 *  - authenticated portable .vdr archive + separate .vrk key + passphrase
 * Never store credentials; never infer success from a clicked button.
 */
import {mountNeuralSphere} from '/iphone/genesis-neural-sphere.js';
const svg=p=>'<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">'+p+'</svg>';
const globe=svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c-5 6-5 12 0 18m0-18c5 6 5 12 0 18"/>');
const key=svg('<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9m-3 3 3 3m-6 0 3 3"/>');
const database=svg('<ellipse cx="12" cy="5.5" rx="8" ry="3.5"/><path d="M4 5.5v7c0 2 3.6 3.5 8 3.5s8-1.5 8-3.5v-7M4 12.5v6c0 2 3.6 3.5 8 3.5s8-1.5 8-3.5v-6"/>');
const shield=svg('<path d="M12 2 4 5v6c0 5 3.4 9.7 8 11 4.6-1.3 8-6 8-11V5z"/><path d="m9 12 2 2 4-5"/>');
const arrow=svg('<path d="M4 12h16m-6-6 6 6-6 6"/>');
const folder=svg('<path d="M3 19V5a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v11z"/><path d="M3 19 7 11h14"/>');
const file=svg('<path d="M6 2h8l5 5v15H6z"/><path d="M14 2v6h5"/>');
const eye=svg('<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>');
const eyeOff=svg('<path d="m2 2 20 20M10.5 6.1c.5-.1 1-.1 1.5-.1 6.5 0 10 6 10 6a17 17 0 0 1-4 4.1M6.1 7.5A17 17 0 0 0 2 12s3.5 6 10 6c.7 0 1.4-.1 2-.2"/>');
const codeAlphabet='ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const sanitize=value=>String(value||'').toUpperCase().replace(/[^A-Z2-9]/g,'').split('').filter(x=>codeAlphabet.includes(x)).join('').slice(0,12);
export const formatRecoveryCode=raw=>{
 const value=sanitize(raw);
 return value.length===12?value.slice(0,4)+'-'+value.slice(4,8)+'-'+value.slice(8):null;
};
const formatName=name=>String(name||'').slice(0,120);
function markup(mode,options){
 const backupAvailable=Boolean(options?.restore_available&&!options?.restore_setup_in_progress);
 const codeAvailable=Boolean(options?.recovery_available);
 const selected=mode==='restore_data'?'backup':'code';
 return `<div class="vo-window-dots" aria-hidden="true"><i></i><i></i><i></i></div>
 <header class="vs-header vo-header"><div class="vs-brand"><span class="vs-logo" aria-hidden="true"><span></span></span>
  <div><strong>Vishnu 2.0</strong><small>Your Personal AI Companion</small></div></div>
 <div class="vo-header-actions"><button type="button" class="vs-language" data-v8-language aria-haspopup="dialog">${globe} English ⌄</button>
  <span class="vo-badge">P1-08</span></div></header>
 <div class="vs-body vo-body"><div class="vs-hero vo-hero" aria-hidden="true">
  <div class="vw-sphere vs-sphere vo-sphere"><canvas data-v8-sphere data-neural-emphasis="login"></canvas></div>
  <div class="vs-ground vo-ground"><span></span></div></div>
 <div class="vo-right"><section class="vo-panel v8-panel" aria-label="Recovery verification">
   <p class="vs-eyebrow vo-eyebrow" aria-label="Recovery verification, screen P1-08">STEP 8 OF 9</p>
   <h1>Recovery <span>Verification</span></h1>
   <p class="vo-description">Verify your recovery information to regain access to your Vishnu. Choose a method below.</p>
   <div class="v8-methods" aria-label="Recovery verification methods">
    <section class="v8-method ${selected==='code'?'selected':''}" data-v8-method="code" aria-label="Use a Recovery Code">
      <button type="button" class="v8-method-heading" data-v8-select="code" aria-pressed="${selected==='code'}">
       <span class="v8-method-icon">${key}</span><span class="v8-method-title"><strong>Use a Recovery Code</strong>
       <small>Enter one of your recovery codes to verify your identity.</small></span><span class="v8-info" aria-hidden="true">ⓘ</span>
      </button>
      <div class="v8-code-groups" role="group" aria-label="Recovery code, six two-character groups">
       ${Array.from({length:6},(_,i)=>`<input data-v8-group="${i}" type="text" inputmode="text" maxlength="32"
        autocapitalize="characters" autocorrect="off" spellcheck="false" autocomplete="off"
        aria-label="Recovery code group ${i+1} of 6" placeholder="••" />`).join('')}
      </div>
    </section>
    <div class="v8-or" aria-hidden="true"><span></span><b>OR</b><span></span></div>
    <section class="v8-method ${selected==='backup'?'selected':''}" data-v8-method="backup" aria-label="Use an Encrypted Backup">
     <button type="button" class="v8-method-heading" data-v8-select="backup" aria-pressed="${selected==='backup'}">
      <span class="v8-method-icon">${database}</span><span class="v8-method-title"><strong>Use an Encrypted Backup</strong>
      <small>Select your backup file and enter the required password or recovery key.</small></span><span class="v8-info" aria-hidden="true">ⓘ</span>
     </button>
     <div class="v8-backup-fields">
      <div class="v8-file-line"><span>${file}<span data-v8-archive-name>Select Backup File (.vdr)</span></span>
       <label class="v8-browse">${folder}<span>Browse</span>
        <input type="file" accept=".vdr,application/octet-stream" id="v8Archive" aria-label="Choose encrypted backup archive"/></label>
      </div>
      <div class="v8-file-line v8-key-file"><span>${key}<span data-v8-key-name>Select Separate Recovery Key (.vrk)</span></span>
       <label class="v8-browse">${folder}<span>Browse</span>
        <input type="file" accept=".vrk,application/octet-stream" id="v8KeyFile" aria-label="Choose separate encrypted recovery key"/></label>
      </div>
      <div class="v8-password-line">${key}<input id="v8Passphrase" type="password" placeholder="Recovery key passphrase" autocomplete="off"
         aria-label="Recovery key passphrase" /><button type="button" data-v8-visible aria-label="Show passphrase">${eyeOff}</button></div>
      ${options?.local_setup_available?'':`<div class="v8-password-line v8-bootstrap">${shield}
       <input id="v8Bootstrap" type="password" placeholder="Local runtime setup code" autocomplete="off" aria-label="Local runtime setup code"/></div>`}
      <p class="v8-method-limit" data-v8-backup-limit>${backupAvailable?
        'The archive, separate recovery key and passphrase are all required. Vishnu verifies them before scheduling restoration.':
        'Encrypted restoration is available only on an eligible uninitialized Vishnu runtime. No files will be sent here.'}</p>
      <p class="v8-method-limit">Trusted-device data transfer is not supported in this PWA.</p>
     </div>
    </section>
   </div>
   <div class="v8-safety">${shield}<span><strong>Your recovery information is secure</strong>
    <small>Vishnu verifies credentials using your configured runtime and does not send them to third-party AI providers or analytics.</small></span></div>
   <p id="v8Status" role="status" aria-live="polite" class="v8-status"></p>
  </section></div></div>
 <footer class="vo-footer v8-footer"><button type="button" class="vo-back" data-v8-back>← <span>Back</span></button>
  <button class="vo-continue" type="button" data-v8-submit>Verify &amp; Continue ${arrow}</button></footer>
 <dialog class="vs-dialog" id="v8LanguageDialog"><h2>Language</h2><p>English is currently supported for secure recovery.</p>
  <button type="button" data-v8-language-close>Close</button></dialog>`;
}
export function mountRecoveryVerificationScreen(root,mode,options,{onBack,onVerifyCode,onRestore}){
 if(!root)return()=>{};
 const backupAvailable=Boolean(options?.restore_available&&!options?.restore_setup_in_progress);
 const codeAvailable=Boolean(options?.recovery_available);
 let selected=mode==='restore_data'?'backup':'code';
 root.innerHTML=markup(mode,options);
 const $=query=>root.querySelector(query);
 const groups=[...root.querySelectorAll('[data-v8-group]')];
 let disposed=false,busy=false;
 const say=(value,error=false)=>{if(disposed)return;const s=$('#v8Status');s.textContent=value;s.dataset.error=String(error);};
 const clearSecrets=()=>{
  groups.forEach(i=>{i.value='';});$('#v8Passphrase').value='';
  if($('#v8Bootstrap'))$('#v8Bootstrap').value='';
 };
 const update=()=>{
  for(const method of root.querySelectorAll('[data-v8-method]')){
   const active=method.dataset.v8Method===selected;
   method.classList.toggle('selected',active);method.querySelector('[data-v8-select]').setAttribute('aria-pressed',String(active));
  }
 };
 const select=method=>{
  if(busy||method===selected)return;
  clearSecrets();selected=method;update();say('');
  if(method==='code')groups[0].focus();else $('#v8Archive').focus();
 };
 const pasteValue=(value)=>{
  const v=sanitize(value);groups.forEach((input,i)=>{input.value=v.slice(i*2,i*2+2);});
  groups[Math.min(Math.floor(v.length/2),5)].focus();
 };
 for(const input of groups){
  const idx=Number(input.dataset.v8Group);
  input.addEventListener('input',()=>{
   let v=sanitize(input.value);if(v.length>2){pasteValue(v);return;}
   input.value=v.slice(0,2);
   if(v.length===2&&idx<groups.length-1)groups[idx+1].focus();
   say('');
  });
  input.addEventListener('paste',event=>{
   const raw=event.clipboardData?.getData('text')||'';
   if(raw){event.preventDefault();pasteValue(raw);}
  });
  input.addEventListener('keydown',event=>{
   if(event.key==='Backspace'&&!input.value&&idx>0){groups[idx-1].focus();groups[idx-1].value='';}
   if(event.key==='ArrowLeft'&&idx>0){event.preventDefault();groups[idx-1].focus();}
   if(event.key==='ArrowRight'&&idx<5){event.preventDefault();groups[idx+1].focus();}
   if(event.key==='Enter'){event.preventDefault();void submit();}
  });
  input.addEventListener('focus',()=>select('code'));
 }
 const archive=$('#v8Archive'),keyFile=$('#v8KeyFile'),passphrase=$('#v8Passphrase');
 const changeFile=(input,textSelector,ext)=>{
  input.addEventListener('change',()=>{
   select('backup');
   const chosen=input.files?.[0];
   $(textSelector).textContent=chosen?formatName(chosen.name):'Select '+(ext==='vdr'?'Backup File (.vdr)':'Separate Recovery Key (.vrk)');
   if(chosen&&!chosen.name.toLowerCase().endsWith('.'+ext))say('Select a valid .'+ext+' file.',true);
   else say('');
  });
 };
 changeFile(archive,'[data-v8-archive-name]','vdr');
 changeFile(keyFile,'[data-v8-key-name]','vrk');
 passphrase.addEventListener('focus',()=>select('backup'));
 $('#v8Bootstrap')?.addEventListener('focus',()=>select('backup'));
 $('[data-v8-visible]').addEventListener('click',()=>{
  const isVisible=passphrase.type==='text';passphrase.type=isVisible?'password':'text';
  $('[data-v8-visible]').innerHTML=isVisible?eyeOff:eye;
  $('[data-v8-visible]').setAttribute('aria-label',isVisible?'Show passphrase':'Hide passphrase');
 });
 root.querySelectorAll('[data-v8-select]').forEach(button=>button.addEventListener('click',()=>select(button.dataset.v8Select)));
 const lock=value=>{busy=value;for(const b of root.querySelectorAll('button'))b.disabled=value;};
 async function submit(){
  if(busy)return;
  if(selected==='code'){
   if(!codeAvailable){say('No unused owner recovery codes are available on this runtime.',true);return;}
   const compact=groups.map(input=>sanitize(input.value)).join('');
   const code=formatRecoveryCode(compact);
   if(!code){say('Enter one complete 12-character recovery code.',true);groups.find(g=>g.value.length<2)?.focus();return;}
   clearSecrets();lock(true);say('Verifying your one-time recovery code…');
   try{await onVerifyCode({code,mode});}
   catch(error){say(error?.message||'The recovery code could not be verified.',true);}
   finally{if(!disposed)lock(false);}
  }else{
   if(!backupAvailable){say('Encrypted restore requires a new, eligible Vishnu runtime. No backup has been uploaded.',true);return;}
   const f=archive.files?.[0],k=keyFile.files?.[0];
   if(!f||!k||!f.name.toLowerCase().endsWith('.vdr')||!k.name.toLowerCase().endsWith('.vrk')){
    say('Choose a .vdr backup and its matching .vrk recovery key.',true);return;
   }
   const secret=passphrase.value,bootstrap=$('#v8Bootstrap')?.value||'';
   if(secret.length<12){say('Enter the recovery-key passphrase (at least 12 characters).',true);return;}
   if(!options?.local_setup_available&&bootstrap.length<32){say('Enter the setup code provided for this Vishnu runtime.',true);return;}
   clearSecrets();lock(true);say('Uploading and verifying recovery materials…');
   try{
    const result=await onRestore({archive:f,keyFile:k,passphrase:secret,bootstrap});
    if(result?.status!=='restart_required')throw new Error('The runtime has not confirmed a scheduled restore.');
    say('Encrypted package authenticated. Restart the local Vishnu runtime to restore data, then secure the replacement device.');
   }catch(error){say(error?.message||'Encrypted restoration could not be verified. No success was recorded.',true);}
   finally{if(!disposed)lock(false);}
  }
 }
 $('[data-v8-submit]').addEventListener('click',()=>void submit());
 $('[data-v8-back]').addEventListener('click',()=>{if(!busy){clearSecrets();onBack();}});
 $('[data-v8-language]').addEventListener('click',()=>$('#v8LanguageDialog').showModal());
 $('[data-v8-language-close]').addEventListener('click',()=>$('#v8LanguageDialog').close());
 let dispose=()=>{};
 try{dispose=mountNeuralSphere($('[data-v8-sphere]'));}
 catch{$('[data-v8-sphere]')?.parentElement?.classList.add('vw-static-fallback');}
 update();
 return()=>{
  disposed=true;clearSecrets();
  if($('#v8LanguageDialog')?.open)$('#v8LanguageDialog').close();
  dispose?.();
 };
}
