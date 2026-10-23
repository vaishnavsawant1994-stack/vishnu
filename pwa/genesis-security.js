/* P1-03 security presentation. Backend ownership remains with FirstRunCoordinator. */
import { mountNeuralSphere } from '/iphone/genesis-neural-sphere.js';

const icon=(body,cl='')=>'<svg class="'+cl+'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+body+'</svg>';
const lock=icon('<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>');
const eye=icon('<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>');
const eyeOff=icon('<path d="m3 3 18 18M10.6 5.1Q11.3 5 12 5c6 0 10 7 10 7a16 16 0 0 1-3 3.7M6.2 6.8C3.6 8.6 2 12 2 12s4 7 10 7c1.5 0 2.9-.5 4.2-1.2"/>');
const fingerprint=icon('<path d="M3 10a9 9 0 0 1 18 0M6 12v-2a6 6 0 0 1 12 0v3M9 11v-1a3 3 0 0 1 6 0v4M12 13v5M6 16c0 2-1 4-2 5m14-4c0 2 .5 3.5 1.5 4M9 17c0 2-.5 4-1.5 5m7-2c.2 1 .5 1.6 1 2"/>');
const laptop=icon('<rect x="4" y="5" width="16" height="12" rx="1"/><path d="M2 20h20"/>');
const phone=icon('<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>');
const globe=icon('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c-5 6-5 12 0 18m0-18c5 6 5 12 0 18"/>');
const info=icon('<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>');
const arrow=icon('<path d="M4 12h16m-6-6 6 6-6 6"/>');
const deviceGuess=()=>{
  const platform=(navigator.userAgentData?.platform||navigator.platform||'').toLowerCase();
  const ua=navigator.userAgent.toLowerCase();
  if(/iphone|ipad|ipod/.test(platform+' '+ua))return {name:'My iPhone',mobile:true};
  if(/android/.test(platform+' '+ua))return {name:'My Android Phone',mobile:true};
  if(/mac/.test(platform))return {name:'My MacBook',mobile:false};
  if(/win/.test(platform))return {name:'My Windows Laptop',mobile:false};
  if(/linux/.test(platform))return {name:'My Linux Computer',mobile:false};
  return {name:'My Device',mobile:false};
};
function strength(v){
  if(!v)return 0;
  let score=0;
  if(v.length>=12)score++;
  if(v.length>=16)score++;
  if(/[a-z]/.test(v)&&/[A-Z]/.test(v)&&/[0-9]/.test(v))score++;
  if(/[^a-zA-Z0-9]/.test(v)||v.length>=22)score++;
  if(/^(.)\1+$/.test(v)||/(password|123456|qwerty|vishnu)/i.test(v))score=Math.min(score,1);
  return score;
}
const field=(id,placeholder,autocomplete)=>'<div class="vs-field">'+lock+
  '<input id="'+id+'" type="password" autocomplete="'+autocomplete+'" placeholder="'+placeholder+'" minlength="12" maxlength="256" spellcheck="false" aria-label="'+placeholder+'">'+
  '<button type="button" class="vs-visibility" data-visibility="'+id+'" aria-label="Show '+placeholder.toLowerCase()+'">'+eyeOff+'</button></div>';
function markup(s){
 const saved=!!s.identityCreated;
 const device=deviceGuess();
 const name=s.deviceName===undefined?device.name:s.deviceName;
 return `<header class="vs-header">
   <div class="vs-brand"><span class="vs-logo" aria-hidden="true"><span></span></span><div><strong>Vishnu 2.0</strong><small>Your Personal AI Companion</small></div></div>
   <ol class="vs-progress" aria-label="Onboarding steps">
     <li class="complete"><span class="vs-step">✓</span><span>Welcome</span></li>
     <li class="complete"><span class="vs-step">✓</span><span>Your Name</span></li>
     <li aria-current="step"><span class="vs-step">3</span><span>Security</span></li>
     <li><span class="vs-step">4</span><span>Recovery</span></li>
   </ol>
   <button type="button" class="vs-language" data-vs-language aria-haspopup="dialog">${globe} English <span aria-hidden="true">⌄</span></button>
 </header>
 <div class="vs-body">
   <div class="vs-hero" aria-hidden="true"><div class="vw-sphere vs-sphere"><canvas data-vs-sphere data-neural-emphasis="security"></canvas></div><div class="vs-ground"><span></span></div></div>
   <div class="vs-main">
     <p class="vs-eyebrow">STEP 3 OF 4</p>
     <h1>Secure Your <span>Vishnu</span></h1>
     <p class="vs-description">Set up a secure sign-in method and name this device.<br>This keeps your Vishnu safe and only accessible to you.</p>
     <section class="vs-panel vs-security-panel" aria-label="Create a password and add a passkey">
       <div class="vs-section-heading"><span>${lock}<strong>1. Create a Password</strong></span><small>${info} Use a strong password</small></div>
       <div class="vs-passwords">${field('firstRunPassword','Enter a strong password','new-password')}
         ${field('firstRunPasswordAgain','Confirm your password','new-password')}</div>
       <div class="vs-strength" aria-label="Password strength"><div class="vs-bars" aria-hidden="true"><i></i><i></i><i></i><i></i></div><span id="vsStrength" role="status">Password strength</span></div>
       <p id="vsPasswordError" class="vs-field-error" role="alert" aria-live="polite"></p>
       <div class="vs-divider"></div>
       <div class="vs-section-heading vs-passkey-heading"><span>${fingerprint}<strong>2. Add a Passkey <em>(Recommended)</em></strong></span></div>
       <p class="vs-detail">Use Face ID, Touch ID or Windows Hello for a faster and more secure sign-in.</p>
       <button type="button" class="vs-passkey-button" data-vs-passkey>${fingerprint}<strong>Set up a Passkey</strong>${arrow}</button>
       <p class="vs-passkey-status" id="vsPasskeyStatus" role="status" aria-live="polite"></p>
     </section>
     <section class="vs-panel vs-device-panel" aria-label="Name this device">
       <div class="vs-section-heading"><span>${device.mobile?phone:laptop}<strong>3. Name This Device</strong></span></div>
       <p class="vs-detail">Give a name to this device so you can recognize it later.</p>
       <div class="vs-device-field">${device.mobile?phone:laptop}<input id="vsDeviceName" type="text" maxlength="120" autocomplete="off" value="" placeholder="Name this device" aria-label="Name this device"><button type="button" data-vs-clear-name aria-label="Clear device name">×</button></div>
       <p class="vs-field-error" id="vsDeviceError" role="alert" aria-live="polite"></p>
     </section>
     ${s.options?.local_setup_available?'<p class="vs-local-note">Local-only runtime verified. No setup code is needed.</p>':'<div class="vs-runtime-code"><label for="firstRunBootstrap">Secure runtime setup code (required)</label><input type="password" id="firstRunBootstrap" autocomplete="one-time-code" aria-describedby="vsBootstrapHelp" placeholder="Paste the setup code from your Vishnu runtime"><p class="vs-detail" id="vsBootstrapHelp">Remote or shared runtimes require the owner setup code configured on the Vishnu server. This is not your login password. For code-free local setup, launch Vishnu in loopback-only development mode.</p></div>'}
     <div class="vs-navigation"><button type="button" class="vs-back" data-vs-back>← <span>Back</span></button><button type="button" class="vs-continue" data-genesis-next><span>Continue</span> ${arrow}</button></div>
     <p id="genesisStatus" class="vs-status" role="status" aria-live="polite"></p>
   </div>
 </div>
 <dialog id="vsLanguageDialog" class="vs-dialog"><h2>Language</h2><p>English is the supported setup language. Other languages will appear when localization is available.</p><button type="button" data-vs-close>Close</button></dialog>`;
}
export function mountSecurityScreen(root,state,{onBack,onContinue,onPasskey}){
 if(!root)return()=>{};
 root.innerHTML=markup(state);
 const $=query=>root.querySelector(query);
 const pw=$('#firstRunPassword'), confirmation=$('#firstRunPasswordAgain');
 const error=$('#vsPasswordError'), devError=$('#vsDeviceError');
 const device=$('#vsDeviceName');
 device.value=state.deviceName===undefined?deviceGuess().name:state.deviceName;
 state.deviceName=device.value;
 const lockRegisteredName=()=>{
   if(!state.identityCreated)return;
   device.readOnly=true;
   $('[data-vs-clear-name]').disabled=true;
   $('[data-vs-clear-name]').title='Change this name later in Trusted Devices';
   device.title='This device name was securely registered; change it later in Trusted Devices';
 };
 lockRegisteredName();
 const validate=()=>{
   if(state.identityCreated)return true;
   const value=pw.value;
   if(!value||value.length<12||value.length>256){error.textContent='Use an owner password of at least 12 characters.';return false;}
   if(value!==confirmation.value){error.textContent='Your passwords do not match.';return false;}
   error.textContent='';
   return true;
 };
 const setStrength=()=>{
   const levels=['','Weak','Fair','Good','Strong'];
   const n=strength(pw.value);
   root.querySelector('.vs-bars').dataset.level=String(n);
   $('#vsStrength').textContent=n?levels[n]+' password':'Password strength';
   if(error.textContent)error.textContent='';
 };
 pw.addEventListener('input',setStrength);
 confirmation.addEventListener('input',()=>{if(error.textContent)error.textContent='';});
 root.querySelectorAll('[data-visibility]').forEach(button=>{
   button.addEventListener('click',()=>{
     const input=$('#'+button.dataset.visibility);
     const revealing=input.type==='password';
     input.type=revealing?'text':'password';
     button.innerHTML=revealing?eye:eyeOff;
     button.setAttribute('aria-label',(revealing?'Hide ':'Show ')+input.placeholder.toLowerCase());
   });
 });
 device.addEventListener('input',()=>{state.deviceName=device.value;devError.textContent='';});
 $('[data-vs-clear-name]').addEventListener('click',()=>{device.value='';state.deviceName='';device.focus();});
 const deviceValid=()=>{
   const name=device.value.trim().replace(/\s+/g,' ');
   if(!name){devError.textContent='Name this device before continuing.';device.focus();return false;}
   if(name.length>120){devError.textContent='Device names must be at most 120 characters.';return false;}
   state.deviceName=name;device.value=name;devError.textContent='';return true;
 };
 const button=$('[data-genesis-next]');
 let pending=false;
 const progress=async(fn,label)=>{
   if(pending)return;
   if(!deviceValid())return;
   if(!validate()){pw.focus();return;}
   const bootstrap=$('#firstRunBootstrap');
   if(!state.identityCreated && bootstrap && bootstrap.value.trim().length<32){
     const message=$('#genesisStatus');
     if(message)message.textContent='Secure runtime setup code required. Enter the code configured on your Vishnu server, or use the local-only runtime launcher. Do not enter your owner password here.';
     bootstrap.focus();
     return;
   }
   $('#genesisStatus').textContent='';
   pending=true;button.disabled=true;
   const back=$('[data-vs-back]');
   back.disabled=true;
   const passkeyButton=$('[data-vs-passkey]');
   passkeyButton.disabled=true;
   try{await fn();}
   catch(error){
     const message=$('#genesisStatus');
     if(message)message.textContent=error?.message||'Vishnu security setup could not continue. Try again.';
   }
   finally{
     pending=false;
     lockRegisteredName();
     if(button.isConnected)button.disabled=false;
     if(back.isConnected)back.disabled=false;
     if(passkeyButton.isConnected)passkeyButton.disabled=!hasWebAuthn && !state.passkeyCreated;
   }
 };
 button.addEventListener('click',()=>{void progress(onContinue,'Continue');});
 const status=$('#vsPasskeyStatus');
 const hasWebAuthn=Boolean(window.PublicKeyCredential&&navigator.credentials&&navigator.credentials.create);
 const passkey=$('[data-vs-passkey]');
 if(state.passkeyCreated){
   passkey.querySelector('strong').textContent='Passkey Added ✓';
   status.textContent='Your passkey has been verified and registered.';
 }else if(!hasWebAuthn){
   passkey.disabled=true;
   passkey.setAttribute('aria-disabled','true');
   status.textContent='Passkeys are unavailable in this browser. You can continue using a password.';
 }
 passkey.addEventListener('click',()=>{void progress(async()=>{
   status.textContent='Waiting for your device authenticator…';
   try{
     const result=await onPasskey({password:pw.value,confirmation:confirmation.value,
       bootstrap:$('#firstRunBootstrap')?.value||'',deviceName:state.deviceName});
     if(result){
       passkey.querySelector('strong').textContent='Passkey Added ✓';
       status.textContent='Your passkey was verified and registered.';
     }else status.textContent='Passkey setup was cancelled or unavailable. Your password still works.';
   }catch(e){status.textContent=e?.message||'Passkey setup failed. Try again or use your password.';}
 },'passkey');});
 $('[data-vs-back]').addEventListener('click',()=>{if(!pending)onBack();});
 $('[data-vs-language]').addEventListener('click',()=>$('#vsLanguageDialog').showModal());
 $('[data-vs-close]').addEventListener('click',()=>$('#vsLanguageDialog').close());
 const sphere=$('[data-vs-sphere]');
 let dispose=()=>{};
 try{
   dispose=mountNeuralSphere(sphere);
 }catch{
   // GPU/WebGL shader failure must not block owner setup or account recovery.
   sphere.parentElement?.classList.add('vw-static-fallback');
 }
 // A security draft must not retain the actual plaintext password in state.
 return()=>{pw.value='';confirmation.value='';dispose?.();};
}
