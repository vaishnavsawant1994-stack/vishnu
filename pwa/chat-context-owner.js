/* Final owner for Chat project-context controls. Loaded after the Home/core adapters so
   older Home wiring cannot replace the current conversation-context behavior. */
(()=>{
  if(window.__vishnuChatContextOwner)return;
  window.__vishnuChatContextOwner=true;
  const $=id=>document.getElementById(id);
  const bridge=()=>window.vishnuChatBridge;
  let selectedProjectId='';

  // Chat Details remains reachable through the canonical three-dot conversation menu.
  // The responsive Chat stylesheet introduced a second top-details button and hid the
  // canonical menu; override that presentation-only rule after all Chat CSS is loaded.
  // Empty Chat is its own state, not Home landing, so restore its intro container without
  // reviving Home quick actions. Mobile/tablet Chat keeps the shared fixed bottom composer,
  // with the project-context dock fixed directly above it instead of overlapping the editor.
  // Short landscape Home is height-constrained even when its width is tablet-like, so keep
  // the sphere compact and render the four canonical actions in one row above the composer.
  const menuStyle=document.createElement('style');
  menuStyle.dataset.chatCanonicalMenu='true';
  menuStyle.textContent='body.chat-experience .topbar-actions .chat-menu-button:not(.hidden){display:grid!important}body.chat-experience .chat-top-details{display:none!important}body.chat-experience.chat-new-empty .home-intro{display:flex!important}body.chat-experience.chat-new-empty .v-shortcuts{display:none!important}@media(max-width:1279px){body.chat-experience:not(.home-landing) #composer{position:fixed!important;z-index:30;left:max(14px,env(safe-area-inset-left))!important;right:max(14px,env(safe-area-inset-right))!important;bottom:calc(env(safe-area-inset-bottom) + 12px)!important;width:auto!important;margin:0!important}body.chat-experience:not(.home-landing) .message-stream{padding-bottom:calc(var(--shared-composer-h,60px) + 118px)!important;scroll-padding-bottom:calc(var(--shared-composer-h,60px) + 118px)!important}}@media(max-width:760px){body.chat-experience:not(.home-landing) #vChatDock{position:fixed!important;z-index:31;left:max(14px,env(safe-area-inset-left))!important;right:max(14px,env(safe-area-inset-right))!important;bottom:calc(env(safe-area-inset-bottom) + 12px + var(--shared-composer-h,60px) + 10px)!important;width:auto!important;margin:0!important;justify-content:center!important;pointer-events:none}body.chat-experience:not(.home-landing) #vContextChip{position:relative!important;z-index:1!important;pointer-events:auto!important;max-width:min(100%,320px)}}@media(min-width:761px) and (max-height:500px){body.v-ref.home-landing .home-intro{overflow-y:auto!important;padding-top:2px!important;padding-bottom:calc(var(--shared-composer-h,54px) + 74px)!important}body.v-ref.home-landing .home-sphere-stage{height:68px!important;min-height:68px!important;margin:0 0 2px!important}body.v-ref.home-landing .home-sphere-stage .core-stage{width:64px!important;height:64px!important;min-width:64px!important;max-width:64px!important}body.v-ref.home-landing .home-greeting{margin:2px 0 5px!important}body.v-ref.home-landing .home-greeting h1{margin:0!important}body.v-ref.home-landing .home-greeting p{margin-top:3px!important}body.v-ref.home-landing .v-shortcuts{grid-template-columns:repeat(4,minmax(0,1fr))!important;grid-template-rows:98px!important;grid-auto-rows:98px!important;gap:10px!important;margin:3px 0 10px!important}body.v-ref.home-landing .v-card{height:98px!important;min-height:98px!important;padding:9px!important}}';
  menuStyle.textContent+='@media(orientation:landscape) and (max-height:520px) and (max-width:900px){body.v-ref.home-landing .home-sphere-stage{height:48px!important;min-height:48px!important;flex:0 0 48px!important;margin:0!important}body.v-ref.home-landing .home-sphere-stage .core-stage{width:46px!important;height:46px!important;min-width:46px!important;max-width:46px!important}body.v-ref.home-landing .home-greeting{margin:4px 0 6px!important}body.v-ref.home-landing .home-greeting h1{font-size:20px!important;line-height:1.15!important;margin:0!important}body.v-ref.home-landing .home-greeting p{font-size:11px!important;line-height:1.2!important;margin:2px 0 0!important}body.v-ref.home-landing .v-shortcuts{grid-template-columns:repeat(4,minmax(0,1fr))!important;grid-template-rows:50px!important;grid-auto-rows:50px!important;gap:8px!important;margin:6px 0 10px!important}body.v-ref.home-landing .v-card{height:50px!important;min-height:50px!important;padding:6px 8px!important;grid-template-columns:30px minmax(0,1fr)!important;grid-template-rows:1fr!important;gap:7px!important}body.v-ref.home-landing .v-card .v-icon{width:28px;height:28px}body.v-ref.home-landing .v-card strong{font-size:11px!important;line-height:1.2}body.v-ref.home-landing .v-card small,body.v-ref.home-landing .v-card .v-chev{display:none!important}}';
  document.head.append(menuStyle);

  function setLabel(name=''){
    const label=name?'Project · '+name:'General chat · No project context';
    const chip=$('vContextChip');
    if(chip){
      const span=chip.querySelector('span');
      if(span)span.textContent=label;
      chip.setAttribute('aria-label','Conversation context: '+label+'. Choose context');
    }
    const scope=$('vScopeButton');
    if(scope){
      const strong=scope.querySelector('strong'),small=scope.querySelector('span');
      if(strong)strong.textContent=name?'Project · '+name:'Vishnu · System-wide';
      if(small)small.textContent=name?'Project-scoped conversation':'Ask anything · Updates · Give Vishnu work';
      scope.setAttribute('aria-label',name?'Project-scoped chat for '+name+'. Choose context':'Vishnu system-wide chat. Choose a project context');
    }
  }

  async function projects(){
    const b=bridge();
    if(!b)throw new Error('Conversation controls are unavailable.');
    const data=await b.api('/projects?status=active');
    return Array.isArray(data.projects)?data.projects:[];
  }

  async function chooseContext(){
    const b=bridge();
    if(!b||typeof window.projectDialog!=='function')throw new Error('Project context selection is unavailable.');
    const rows=await projects();
    if(!rows.length){b.showToast('No active projects are available. Create a project first.');return}
    const current=b.current,draft=b.getDraft();
    const inferred=rows.find(project=>project.conversation_id===current?.id);
    if(inferred)selectedProjectId=inferred.id;
    const choice=await window.projectDialog('Choose conversation context',[
      {name:'project_id',label:'Conversation context',type:'select',required:false,value:selectedProjectId,options:[['','General chat · No project context'],...rows.map(project=>[project.id,project.name||'Untitled project'])]},
      {name:'note',label:'',type:'note',value:'Project conversations use the selected project’s own conversation and remain scoped to that project.'}
    ]);
    if(!choice)return;
    if(!choice.project_id){
      if(selectedProjectId||inferred){
        if(draft.trim()){
          const input=$('message');if(input)input.value='';
          await b.createConversation();
          b.setDraft(draft);
        }else await b.createConversation();
      }
      selectedProjectId='';
      setLabel('');
      return;
    }
    const project=rows.find(row=>row.id===choice.project_id);
    if(!project)throw new Error('That project is no longer available.');
    let conversationId=project.conversation_id;
    if(!conversationId){
      const result=await b.api('/projects/'+encodeURIComponent(project.id)+'/conversation',{method:'POST',body:'{}'});
      conversationId=result?.conversation_id;
    }
    if(!conversationId)throw new Error('The project conversation could not be opened.');
    await b.openConversation(conversationId);
    if(draft)b.setDraft(draft);
    selectedProjectId=project.id;
    setLabel(project.name||'Project');
  }

  function intercept(event){
    const target=event.target?.closest?.('#vContextChip,#vScopeButton');
    if(!target)return;
    event.preventDefault();
    event.stopImmediatePropagation();
    chooseContext().catch(error=>bridge()?.showToast(error?.message||'Could not change conversation context.'));
  }

  document.addEventListener('click',intercept,true);
  window.addEventListener('vishnu:new-chat',()=>{
    selectedProjectId='';
    document.body.classList.remove('home-landing','chat-response-clean');
    document.body.classList.add('chat-new-empty','chat-experience','chat-empty-state');
    setLabel('');
  });
  // Synchronize an already-active project conversation without blocking first paint.
  queueMicrotask(async()=>{
    try{
      const b=bridge(),current=b?.current;if(!b||!current?.id)return;
      const rows=await projects(),project=rows.find(row=>row.conversation_id===current.id);
      selectedProjectId=project?.id||'';setLabel(project?.name||'');
    }catch{}
  });
})();

// Keep intent adaptation separate from canonical Chat state. The adaptive layer
// only previews/routs the draft; Chat, server planning, permissions and approvals
// remain the execution authorities.
(()=>{
  if(window.__vishnuAdaptiveComposer||document.querySelector('script[data-adaptive-composer]'))return;
  const script=document.createElement('script');
  script.src='/iphone/adaptive-composer.js';
  script.async=false;
  script.dataset.adaptiveComposer='true';
  script.onerror=()=>console.warn('Adaptive universal composer could not be loaded; normal chat remains available.');
  document.body.append(script);
})();
