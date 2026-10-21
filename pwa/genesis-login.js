/* P1-05 returning owner authentication — presentation only.
   Every credential and trust decision is made by Vishnu's canonical API. */
import {mountNeuralSphere} from '/iphone/genesis-neural-sphere.js';
const svg=path=>'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+path+'</svg>';
const lock=svg('<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>');
const fingerprint=svg('<path d="M8 18c1-3 0-7 4-7s3 4 4 7M5 15v-2a7 7 0 0 1 14 0v3M12 3a10 10 0 0 0-10 10m20 0A10 10 0 0 0 12 3M9 21c2-4 0-7 3-7s1 4 3 7M6 20c1-3 0-6 0-7a6 6 0 0 1 12 0c0 3 0 5 1 7"/>');
const user=svg('<circle cx="9" cy="8" r="4"/><path d="M1 21v-3a8 8 0 0 1 16 0v3M19 9v8m-4-4h8"/>');
const face=svg('<path d="M8 3H5a2 2 0 0 0-2 2v3m13-5h3a2 2 0 0 1 2 2v3M3 16v3a2 2 0 0 0 2 2h3m13-5v3a2 2 0 0 1-2 2h-3M8 14c2 3 6 3 8 0M8 9h.01M16 9h.01"/>');
const laptop=svg('<rect x="4" y="3" width="16" height="14" rx="1"/><path d="M2 20h20"/>');
const globe=svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c-5 6-5 12 0 18m0-18c5 6 5 12 0 18"/>');
const arrow=svg('<path d="M4 12h16m-6-6 6 6-6 6"/>');
const eye=svg('<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>');
const eyeOff=svg('<path d="m3 3 18 18M9.9 5.2a11 11 0 0 1 2.1-.2c6 0 10 7 10 7a16 16 0 0 1-3.1 3.8M6 6.5C3.7 8.2 2 12 2 12s4 7 10 7c1.3 0 2.6-.3 3.7-.8"/>');
function markup(){
return `<header class="vs-header vl-header">
  <div class="vs-brand"><span class="vs-logo" aria-hidden="true"><span></span></span><div><strong>Vishnu 2.0</strong><small>Your Personal AI Companion</small></div></div>
  <ol class="vs-progress vl-progress" aria-label="Vishnu creation and returning-owner entry">
    <li class="complete"><span class="vs-step">✓</span><span>Welcome</span></li>
    <li class="complete"><span class="vs-step">✓</span><span>Your Name</span></li>
    <li class="complete"><span class="vs-step">✓</span><span>Security</span></li>
    <li class="complete"><span class="vs-step">✓</span><span>Recovery</span></li>
    <li aria-current="step"><span class="vs-step">5</span><span>Login</span></li>
  </ol>
  <button type="button" class="vs-language" data-vl-language aria-haspopup="dialog">${globe} English <span aria-hidden="true">⌄</span></button>
 </header>
 <div class="vs-body vl-body">
  <div class="vs-hero vl-hero" aria-hidden="true">
   <div class="vw-sphere vs-sphere vl-sphere"><canvas data-vl-sphere data-neural-emphasis="security"></canvas></div>
   <div class="vs-ground vl-ground"><span></span></div>
   <button type="button" class="vl-back" data-vl-back>← <span>Back</span></button>
  </div>
  <section class="vl-panel" aria-label="Returning owner login">
   <p class="vs-eyebrow vl-eyebrow">RETURNING OWNER · P1-05</p>
   <h1>Unlock <span>Vishnu</span></h1>
   <p class="vl-description">Sign in to your Vishnu using your preferred method.</p>
   <div class="vl-tabs" role="tablist" aria-label="Sign-in methods">
    <button type="button" role="tab" aria-selected="true" id="vlPasswordTab" aria-controls="vlPasswordPanel" data-vl-tab="password">${lock}<span>Password</span></button>
    <button type="button" role="tab" aria-selected="false" id="vlPasskeyTab" aria-controls="vlPasskeyPanel" data-vl-tab="passkey">${user}<span>Passkey</span></button>
    <button type="button" role="tab" aria-selected="false" id="vlBiometricTab" aria-controls="vlBiometricPanel" data-vl-tab="biometric">${fingerprint}<span>Biometric</span></button>
   </div>
   <div role="tabpanel" id="vlPasswordPanel" aria-labelledby="vlPasswordTab">
    <form id="vlPasswordForm" novalidate>
     <label class="vl-field-label" for="vlPassword">Enter your password</label>
     <div class="vs-field vl-field">${lock}<input type="password" id="vlPassword" name="password" required autocomplete="current-password" placeholder="Enter your password" maxlength="256" aria-describedby="vlPasswordError">
      <button type="button" class="vs-visibility" data-vl-visibility aria-label="Show password">${eyeOff}</button></div>
     <p id="vlPasswordError" class="vl-field-error" role="alert"></p>
     <button type="button" class="vl-forgot" data-vl-recovery>Forgot password?</button>
     <label class="vl-remember"><input type="checkbox" id="vlRemember"><span>Remember this device</span><span class="vl-info" title="Your runtime controls session duration and device trust. This choice cannot approve an untrusted device.">ⓘ</span></label>
     <button type="submit" class="vl-primary" data-vl-submit><span>Sign In</span>${arrow}</button>
    </form>
   </div>
   <div role="tabpanel" id="vlPasskeyPanel" aria-labelledby="vlPasskeyTab" hidden>
    <p class="vl-method-help">Use a passkey already registered with Vishnu. Your authenticator confirms your identity.</p>
    <button type="button" class="vl-primary" data-vl-passkey-tab-action>Sign in with Passkey ${arrow}</button>
   </div>
   <div role="tabpanel" id="vlBiometricPanel" aria-labelledby="vlBiometricTab" hidden>
    <p class="vl-method-help">Use your device's configured biometric-backed passkey, when supported. Vishnu never collects biometric data.</p>
    <button type="button" class="vl-primary" data-vl-bio-tab-action>Use Device Authenticator ${arrow}</button>
   </div>
   <div class="vl-or"><span></span><b>OR</b><span></span></div>
   <button type="button" class="vl-alternative" data-vl-passkey>${fingerprint}<strong>Sign in with Passkey</strong>${arrow}</button>
   <button type="button" class="vl-alternative" data-vl-biometric>${face}<strong data-vl-bio-label>Use Device Authenticator</strong>${arrow}</button>
   <div class="vl-trust">${laptop}<span><strong data-vl-trust-title>Device trust is checked on sign-in</strong><small data-vl-trust-desc>New devices require approval from an existing trusted device.</small></span><button type="button" data-vl-devices>Manage Devices</button></div>
   <p id="returningStatus" class="vl-status" role="status" aria-live="polite"></p>
   <button type="button" class="vl-mobile-back" data-vl-back>← Back</button>
  </section>
 </div>
 <dialog class="vs-dialog" id="vlLanguageDialog" aria-labelledby="vlLanguageTitle"><h2 id="vlLanguageTitle">Language</h2><p>English is currently available for secure sign-in. More languages will appear when supported.</p><button type="button" data-vl-language-close>Close</button></dialog>`;
}
const encodeBuffer=buffer=>{
 if(!buffer)return null;
 const bytes=new Uint8Array(buffer);
 let ascii='';
 for(const byte of bytes)ascii+=String.fromCharCode(byte);
 return btoa(ascii).split('+').join('-').split('/').join('_').replace(/=+$/,'');
};
const decodeText=str=>{
 const text=String(str||'').replace(/-/g,'+').replace(/_/g,'/');
 const padded=text+'='.repeat((4-text.length%4)%4);
 const bytes=atob(padded);
 return Uint8Array.from(bytes,chr=>chr.charCodeAt(0));
};
export function publicKeyRequestOptions(options){
 if(!options?.challenge)throw new Error('The authenticator challenge was missing.');
 return {...options,challenge:decodeText(options.challenge),
  allowCredentials:(options.allowCredentials||[]).map(item=>({...item,id:decodeText(item.id)}))};
}
export function serializeAuthentication(credential){
 if(!credential?.response?.signature||!credential.response.authenticatorData||!credential.response.clientDataJSON)
   throw new Error('Authenticator did not return valid authentication evidence.');
 return {id:credential.id,rawId:encodeBuffer(credential.rawId),type:credential.type,
  response:{authenticatorData:encodeBuffer(credential.response.authenticatorData),
   clientDataJSON:encodeBuffer(credential.response.clientDataJSON),
   signature:encodeBuffer(credential.response.signature),
   userHandle:encodeBuffer(credential.response.userHandle)},
  clientExtensionResults:credential.getClientExtensionResults?.()||{},
  authenticatorAttachment:credential.authenticatorAttachment||null};
}
function platformName(){
 const platform=String(navigator.userAgentData?.platform||navigator.platform||'').toLowerCase();
 if(/iphone|ipad|mac/.test(platform))return 'Use Face ID / Touch ID';
 if(/win/.test(platform))return 'Use Windows Hello';
 if(/android/.test(platform))return 'Use Device Biometrics';
 return 'Use Device Authenticator';
}
export function mountLoginScreen(root,options,{onPassword,onPasskey,onRecover,onManage,onBack}){
 if(!root)return()=>{};
 root.innerHTML=markup();
 const $=selector=>root.querySelector(selector);
 let pending=false,disposed=false;
 const available=Boolean(options.passkey_available && window.PublicKeyCredential && navigator.credentials?.get);
 const status=$('#returningStatus');
 const password=$('#vlPassword'),submit=$('[data-vl-submit]');
 const tabs=Array.from(root.querySelectorAll('[data-vl-tab]'));
 const panels={password:$('#vlPasswordPanel'),passkey:$('#vlPasskeyPanel'),biometric:$('#vlBiometricPanel')};
 function say(text,isError=false){if(disposed)return;status.textContent=text;status.dataset.error=String(isError);}
 function lockUI(active){
  pending=active;
  for(const button of root.querySelectorAll('button'))if(!button.hasAttribute('data-vl-language-close'))button.disabled=active;
  password.disabled=active;$('#vlRemember').disabled=active;
  if(active)submit.setAttribute('aria-busy','true');else submit.removeAttribute('aria-busy');
 }
 function tab(method){
  if(pending)return;
  tabs.forEach(el=>{const active=el.dataset.vlTab===method;el.setAttribute('aria-selected',String(active));el.tabIndex=active?0:-1;});
  for(const [key,panel] of Object.entries(panels))panel.hidden=key!==method;
  if(method==='password')password.focus({preventScroll:true});
  else say(available?'': 'No configured passkey is available in this browser. Use your owner password.',!available);
 }
 tabs.forEach(el=>{
  el.addEventListener('click',()=>tab(el.dataset.vlTab));
  el.addEventListener('keydown',event=>{
   if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
   event.preventDefault();
   const current=tabs.indexOf(el);
   const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:
     (current+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
   tab(tabs[next].dataset.vlTab);tabs[next].focus();
  });
 });
 $('[data-vl-visibility]').addEventListener('click',()=>{
  const revealing=password.type==='password';password.type=revealing?'text':'password';
  $('[data-vl-visibility]').innerHTML=revealing?eye:eyeOff;
  $('[data-vl-visibility]').setAttribute('aria-label',(revealing?'Hide':'Show')+' password');
 });
 $('[data-vl-bio-label]').textContent=platformName();
 $('#vlRemember').addEventListener('change',()=>{
   say('Vishnu controls session lifetime and device trust. Remembering this browser cannot bypass approval.');
 });
 async function run(task,message){
  if(pending)return;
  lockUI(true);say(message||'Verifying your identity…');
  try{await task();}catch(error){
   if(error?.name==='NotAllowedError'||error?.name==='AbortError')say('Authentication was cancelled or unavailable.',true);
   else say(error?.message||'Could not sign in. Check your connection or use another method.',true);
  }finally{if(!disposed)lockUI(false);}
 }
 $('#vlPasswordForm').addEventListener('submit',event=>{
   event.preventDefault();
   if(pending)return;
   if(!password.value){$('#vlPasswordError').textContent='Enter your owner password.';password.focus();return;}
   $('#vlPasswordError').textContent='';
   // Plaintext is used only for the one canonical authentication request.
   const candidate=password.value;password.value='';
   void run(()=>onPassword(candidate),'Checking your password…');
 });
 password.addEventListener('input',()=>{$('#vlPasswordError').textContent='';});
 const passkey=()=>{if(!available){say('A configured passkey is unavailable here. Try the owner password.',true);return;}
  void run(()=>onPasskey(), 'Waiting for your system authenticator…');
 };
 $('[data-vl-passkey]').addEventListener('click',passkey);
 $('[data-vl-passkey-tab-action]').addEventListener('click',passkey);
 $('[data-vl-biometric]').addEventListener('click',passkey);
 $('[data-vl-bio-tab-action]').addEventListener('click',passkey);
 $('[data-vl-recovery]').addEventListener('click',()=>{if(!pending)onRecover();});
 root.querySelectorAll('[data-vl-back]').forEach(button=>button.addEventListener('click',()=>{if(!pending)onBack();}));
 $('[data-vl-devices]').addEventListener('click',()=>{
   if(pending)return;
   const outcome=onManage();
   if(typeof outcome==='string')say(outcome);
 });
 $('[data-vl-language]').addEventListener('click',()=>$('#vlLanguageDialog').showModal());
 $('[data-vl-language-close]').addEventListener('click',()=>$('#vlLanguageDialog').close());
 let dispose=()=>{};
 try{dispose=mountNeuralSphere($('[data-vl-sphere]'));}
 catch{$('[data-vl-sphere]')?.parentElement?.classList.add('vw-static-fallback');}
 return()=>{disposed=true;password.value='';if($('#vlLanguageDialog').open)$('#vlLanguageDialog').close();dispose?.();};
}
