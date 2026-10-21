/* Vishnu Phase 1 P1-02: owner identity UI; canonical create authority remains P1-03. */
import { mountNeuralSphere } from '/iphone/genesis-neural-sphere.js';

const svg = path => '<svg viewBox="0 0 24 24" aria-hidden="true">'+path+'</svg>';
const globe = svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c-5 6-5 12 0 18m0-18c5 6 5 12 0 18"/>');
const user = svg('<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>');
const message = svg('<path d="M4 5h16v12H9l-5 3V5Z"/><path d="M8 10h8m-8 4h5"/>');
const presets = ['blue', 'mountain', 'forest', 'horizon'];
const presetNames = ['Blue abstract sphere', 'Mountain landscape', 'Forest landscape', 'Sea sunset'];
const svgBrand = '<svg class="vi-brand-icon" viewBox="0 0 32 34" aria-hidden="true"><defs><linearGradient id="viBrandGrad"><stop stop-color="#21dcfa"/><stop offset="1" stop-color="#047cc3"/></linearGradient></defs><path d="M16 2 27 23c2 4 0 6-4 6l-7-4-7 4c-4 0-6-2-4-6Z" fill="url(#viBrandGrad)"/><path d="M16 10 22 24h-12Z" fill="#021523"/></svg>';

function step(label, number, active = false) {
  return '<li'+(active?' aria-current="step"':'')+'><span class="vi-step-number">'+number+'</span><span>'+label+'</span></li>';
}
function avatarMarkup(id, index) {
  return '<button type="button" class="vi-avatar-choice" data-vi-avatar="'+id+'" data-selected="false" aria-pressed="false" aria-label="Choose '+presetNames[index]+'"><span class="vi-avatar-ring"><img src="/iphone/assets/genesis/avatar-'+id+'.svg" alt="" loading="eager"></span></button>';
}
function markup() {
  return '<header class="vi-header"><div class="vi-brand">'+svgBrand+'<span>VISHNU 2.0</span></div>'+
    '<ol class="vi-progress" aria-label="Creation progress">'+step('Welcome','1')+step('Your Identity','2',true)+step('Secure Vishnu','3')+step('Recovery','4')+'</ol>'+
    '<div class="vi-header-tools"><button type="button" class="vi-language" data-vi-language aria-haspopup="dialog">'+globe+' English <span aria-hidden="true">⌄</span></button><span class="vi-screen-id">P1-02</span></div></header>'+
    '<div class="vi-body"><div class="vi-hero"><div class="vw-sphere vi-sphere" aria-hidden="true"><canvas data-vi-sphere></canvas></div></div>'+
    '<section class="vi-form" aria-labelledby="viNameHeading"><h1 id="viNameHeading">What should <span>Vishnu</span> call you?</h1>'+
    '<p class="vi-subtitle">This helps Vishnu personalize your experience and how it talks to you.</p>'+
    '<div class="vi-form-fields"><div><label class="vi-label" for="firstRunFirstName">Your Name</label>'+
    '<div class="vi-field">'+user+'<input class="vi-input" id="firstRunFirstName" name="name" autocomplete="name" maxlength="80" placeholder="Enter your name" required aria-describedby="viNameError"></div>'+
    '<p class="vi-field-error" id="viNameError" aria-live="polite"></p></div>'+
    '<div><label class="vi-label" for="firstRunDisplayName">Display Name <small>(Optional)</small></label>'+
    '<div class="vi-field">'+message+'<input class="vi-input" id="firstRunDisplayName" autocomplete="nickname" maxlength="120" placeholder="How should Vishnu address you?"></div></div>'+
    '<div><p class="vi-label vi-avatars-heading" id="viAvatarLabel">Profile Picture <small>(Optional)</small></p>'+
    '<div class="vi-avatar-row" role="group" aria-labelledby="viAvatarLabel">'+
    '<button type="button" class="vi-avatar-choice vi-avatar-add" data-vi-add aria-label="Add photo"><span class="vi-avatar-ring">+</span><span>Add Photo</span></button>'+
    presets.map(avatarMarkup).join('')+'</div><input type="file" id="viAvatarFile" class="vi-avatar-file" tabindex="-1" accept="image/png,image/jpeg,image/webp" aria-label="Choose profile photo">'+
    '<p class="vi-field-error" id="viAvatarError" aria-live="polite"></p><button type="button" class="vi-avatar-choice" data-vi-remove hidden>Remove selected photo</button></div></div>'+
    '<div class="vi-preview"><div class="vw-sphere vi-mini-sphere" aria-hidden="true"><canvas data-vi-mini-sphere></canvas></div>'+
    '<div class="vi-greeting" aria-live="polite" aria-atomic="true"><strong id="viGreetingTitle">Hello there!</strong><span id="viGreetingDetail">I’m Vishnu. What should I call you?</span><small>I’ll be with you on your journey.</small></div><img id="viSelectedAvatarPreview" class="vi-selected-avatar" alt="Selected profile photo preview" hidden></div>'+ 
    '<p class="vi-draft-note" id="viAvatarNote" hidden>Your picture is a preview until secure setup finishes. It will be saved privately on your Vishnu runtime, not sent to an external image service.</p>'+ 
    '<div class="vi-actions"><button class="vi-back" data-vi-back type="button">← &nbsp; Back</button><button class="vi-continue" data-genesis-next type="button">Continue &nbsp; →</button></div>'+
    '<p id="genesisStatus" class="vi-field-error" role="status" aria-live="polite"></p></section></div>'+
    '<dialog class="vi-dialog" id="viLanguageDialog" aria-labelledby="viLangHeading"><h2 id="viLangHeading">Language</h2>'+
    '<p>English is supported during this setup. Additional languages will be available after they are translated and tested.</p>'+
    '<button type="button" data-vi-dialog-close>Close</button></dialog>';
}

export function mountIdentityScreen(root, state, { onBack, onContinue }) {
  if (!root) return () => {};
  root.innerHTML = markup();
  const $ = q => root.querySelector(q);
  const first = $('#firstRunFirstName');
  const display = $('#firstRunDisplayName');
  first.value = state.firstName || '';
  display.value = state.displayName || '';
  const error = $('#viNameError'), avatarError=$('#viAvatarError'), remove=$('[data-vi-remove]');
  const sources = presets.reduce((o,n)=>{o[n]='/iphone/assets/genesis/avatar-'+n+'.svg';return o;},{});
  const greeting = () => {
    const preferred = (display.value || '').trim() || first.value.trim();
    $('#viGreetingTitle').textContent = preferred ? 'Hello, '+preferred+'!' : 'Hello there!';
    $('#viGreetingDetail').textContent = preferred ? 'I’m Vishnu. I’ll call you '+preferred+'.' : 'I’m Vishnu. What should I call you?';
    if (first.value.trim()) {error.textContent='';first.removeAttribute('aria-invalid');}
  };
  const clearSelection = () => {
    root.querySelectorAll('[data-vi-avatar]').forEach(btn=>{btn.dataset.selected='false';btn.setAttribute('aria-pressed','false');});
    remove.hidden = true;
    $('[data-vi-add]').dataset.selected='false';
    $('[data-vi-add]').setAttribute('aria-pressed','false');
  };
  const select = (source,id=null) => {
    if (state.avatarSource !== source || state.avatarId !== id) state.avatarSaved = false;
    clearSelection();
    state.avatarSource=source;state.avatarId=id;
    if(source==='preset') {
      const btn=$('[data-vi-avatar="'+id+'"]');
      if(btn){btn.dataset.selected='true';btn.setAttribute('aria-pressed','true');}
    }else if(source==='upload'){
      const add=$('[data-vi-add]');
      add.dataset.selected='true';add.setAttribute('aria-pressed','true');
    }
    remove.hidden=source==='none';
    const selected=$('#viSelectedAvatarPreview');
    const previewUrl=source==='upload' ? state.avatarPreviewUrl : source==='preset' ? sources[id] : '';
    selected.hidden=!previewUrl;
    if(previewUrl)selected.src=previewUrl;else selected.removeAttribute('src');
    $('#viAvatarNote').hidden=source==='none';
    avatarError.textContent='';
    // Untrusted image bytes remain ephemeral until owner security permits an authenticated save.
  };
  const cleanupUpload = () => {
    if(state.avatarPreviewUrl){URL.revokeObjectURL(state.avatarPreviewUrl);state.avatarPreviewUrl=null;}
    state.avatarFile=null;
  };
  root.querySelectorAll('[data-vi-avatar]').forEach(btn=>btn.addEventListener('click',()=>{
    cleanupUpload();select('preset',btn.dataset.viAvatar);
  }));
  $('[data-vi-add]').addEventListener('click',()=>$('#viAvatarFile').click());
  $('#viAvatarFile').addEventListener('change',async event=>{
    const file=event.currentTarget.files?.[0];
    if(!file)return;
    if(!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size>2*1024*1024 || file.size===0){
      avatarError.textContent='Choose a PNG, JPEG or WebP image smaller than 2 MB.';
      event.currentTarget.value='';return;
    }
    const previewUrl=URL.createObjectURL(file);
    try {
      const img = new Image();
      img.decoding='async';
      img.src=previewUrl;
      await img.decode();
      if(img.naturalWidth>4096 || img.naturalHeight>4096 || !img.naturalWidth || !img.naturalHeight)
        throw new Error('Image dimensions are too large');
    }catch{
      URL.revokeObjectURL(previewUrl);
      avatarError.textContent='That image cannot be opened. Choose another photo.';
      event.currentTarget.value='';return;
    }
    cleanupUpload();
    state.avatarFile=file;
    state.avatarPreviewUrl=previewUrl;
    select('upload');
    const add=$('[data-vi-add] .vi-avatar-ring');
    add.textContent='';
    const img=document.createElement('img');
    img.src=previewUrl;img.alt='';
    add.append(img);
  });
  remove.addEventListener('click',()=>{
    cleanupUpload();select('none');$('#viAvatarFile').value='';
    $('[data-vi-add] .vi-avatar-ring').textContent='+';
  });
  if(state.avatarSource==='upload' && state.avatarFile && state.avatarPreviewUrl){
    select('upload');
    const img=document.createElement('img');img.src=state.avatarPreviewUrl;img.alt='';
    $('[data-vi-add] .vi-avatar-ring').replaceChildren(img);
  } else if(state.avatarSource==='preset' && sources[state.avatarId]){
    select('preset',state.avatarId);
  }else select('none');
  const saveEdits=()=>{state.firstName=first.value;state.displayName=display.value;greeting();};
  first.addEventListener('input',saveEdits);
  display.addEventListener('input',saveEdits);
  greeting();
  let pending=false;
  $('[data-genesis-next]').addEventListener('click',()=>{
    if(pending)return;
    const normalized=first.value.trim().replace(/\s+/g,' ');
    const nickname=display.value.trim().replace(/\s+/g,' ');
    if(!normalized || normalized.length>80 || nickname.length>120){
      error.textContent=!normalized?'Please enter your name to continue.':'Name or display name is too long.';
      first.setAttribute('aria-invalid','true');
      first.focus();return;
    }
    first.value=normalized;display.value=nickname;
    saveEdits();
    pending=true;
    $('[data-genesis-next]').disabled=true;
    // The existing first-run actions layer validates and advances to security.
    onContinue();
    queueMicrotask(()=>{pending=false;const button=$('[data-genesis-next]');if(button)button.disabled=false;});
  });
  $('[data-vi-back]').addEventListener('click',()=>{saveEdits();onBack();});
  $('[data-vi-language]').addEventListener('click',()=>$('#viLanguageDialog').showModal());
  $('[data-vi-dialog-close]').addEventListener('click',()=>$('#viLanguageDialog').close());
  // Same WebGL geometry/rendering lifecycle as P1-01, with no new 3D implementation.
  const cleanups = [$('[data-vi-sphere]'),$('[data-vi-mini-sphere]')].map(mountNeuralSphere);
  return () => {cleanups.forEach(fn=>fn?.());};
}
