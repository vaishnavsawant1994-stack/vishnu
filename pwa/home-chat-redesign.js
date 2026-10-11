/* Sequential loader for Home/Chat plus canonical Projects Work surfaces. */
(()=>{
  // Preserve the canonical active conversation while Home clears its visible
  // transcript. This wrapper installs before the async status check resolves,
  // so refresh cannot race the later Home/core adapter. Deliberate clears such
  // as delete/new-session enter Home with no active id and remain cleared.
  if(typeof window.enterHomeLanding==='function'&&!window.__vishnuHomeBindingGuard){
    window.__vishnuHomeBindingGuard=true;
    const canonicalHome=window.enterHomeLanding;
    window.enterHomeLanding=function(...args){
      const activeId=typeof currentConversationId==='undefined'?null:currentConversationId;
      const result=canonicalHome.apply(this,args);
      if(activeId&&typeof currentConversationId!=='undefined')currentConversationId=activeId;
      return result;
    };
  }

  // Owner-frozen shared mobile chrome contract. Chat Experience changes the
  // conversation layout, so preserve the shared fixed SMS composer, context
  // dock, and conversation-details control after every Home/Chat transition.
  // Inline !important properties deliberately outrank screen-specific CSS.
  const enforceSharedMobileComposerChrome=()=>{
    if(!document.getElementById('vishnuSharedMobileComposerGuard')){
      const style=document.createElement('style');
      style.id='vishnuSharedMobileComposerGuard';
      style.textContent=`@media(max-width:760px){
        body.chat-experience:not(.home-landing) .message-stream{
          scroll-padding-bottom:calc(var(--shared-composer-bottom,24px) + var(--shared-composer-h,54px) + 58px)!important;
        }
      }
      @media(max-width:760px) and (max-height:560px){
        body.v-ref.home-landing .home-greeting{margin:2px 0 4px!important}
        body.v-ref.home-landing .home-greeting h1{font-size:22px!important}
        body.v-ref.home-landing .home-greeting p{font-size:13px!important;margin-top:3px!important}
        body.v-ref.home-landing .home-sphere-stage{height:92px!important;margin:0 0 4px!important}
        body.v-ref.home-landing .home-sphere-stage .core-stage{width:92px!important;height:92px!important;min-width:92px!important;max-width:92px!important}
        body.v-ref.home-landing .v-shortcuts{grid-template-rows:repeat(2,58px)!important;grid-auto-rows:58px!important;gap:6px!important;margin:4px 0 10px!important}
        body.v-ref.home-landing .v-card{height:58px!important;min-height:58px!important;padding:5px 7px!important;grid-template-columns:28px minmax(0,1fr) 8px!important;gap:5px!important}
        body.v-ref.home-landing .v-card .v-icon{width:28px!important;height:28px!important}
        body.v-ref.home-landing .v-card strong{font-size:12.5px!important}
        body.v-ref.home-landing .v-card small{font-size:10.5px!important;line-height:1.15!important;margin-top:1px!important}
        body.v-ref.home-landing .home-intro{scroll-padding-bottom:calc(var(--shared-composer-bottom,24px) + var(--shared-composer-h,54px) + 12px)!important}
      }`;
      document.head.append(style);
    }
    // Normal Home and the dedicated New Chat empty state are different screens.
    // Once an existing conversation returns Home, release Chat Experience so
    // the canonical four Home cards and Home composer rules are restored.
    const normalHome=document.body.classList.contains('home-landing')&&!document.body.classList.contains('chat-new-empty');
    if(normalHome&&document.body.classList.contains('chat-experience')){
      document.body.classList.remove('chat-experience','chat-empty-state','chat-response-clean','chat-details-open','chat-shell-collapsed');
    }
    if(normalHome){
      const stage=document.querySelector('.core-stage'),homeStage=document.getElementById('homeSphereStage');
      if(stage&&homeStage&&!homeStage.contains(stage))homeStage.appendChild(stage);
      if(stage&&homeStage&&typeof resizeCanvas==='function')requestAnimationFrame(resizeCanvas);
    }
    const composer=document.getElementById('composer'),dock=document.getElementById('vChatDock'),details=document.getElementById('chatDetailsTop');
    if(!composer)return;
    const mobile=matchMedia('(max-width:760px)').matches;
    const chat=mobile&&document.body.classList.contains('chat-experience')&&!document.body.classList.contains('home-landing');
    const composerProps=['position','z-index','left','right','bottom','width','max-width','margin'];
    const dockProps=['position','z-index','left','right','transform','bottom','width','margin'];
    const detailProps=['display','visibility','opacity','pointer-events','width','height','position','right','top','z-index'];
    if(!chat){
      composerProps.forEach(name=>composer.style.removeProperty(name));
      if(dock)dockProps.forEach(name=>dock.style.removeProperty(name));
      if(details)detailProps.forEach(name=>details.style.removeProperty(name));
      return;
    }
    const keyboard=document.body.classList.contains('keyboard-open');
    const composerBottom=keyboard
      ? 'max(var(--shared-composer-bottom,24px),calc(100dvh - var(--keyboard-visible-height,100dvh) + var(--shared-composer-bottom,24px)))'
      : 'var(--shared-composer-bottom,24px)';
    composer.style.setProperty('position','fixed','important');
    composer.style.setProperty('z-index','45','important');
    composer.style.setProperty('left','max(var(--shared-chrome-x,18px),env(safe-area-inset-left))','important');
    composer.style.setProperty('right','max(var(--shared-chrome-x,18px),env(safe-area-inset-right))','important');
    composer.style.setProperty('bottom',composerBottom,'important');
    composer.style.setProperty('width','auto','important');
    composer.style.setProperty('max-width','var(--shared-chrome-max,720px)','important');
    composer.style.setProperty('margin','0 auto','important');
    if(dock){
      const dockBottom=keyboard
        ? 'max(calc(var(--shared-composer-bottom,24px) + var(--shared-composer-h,54px) + 10px),calc(100dvh - var(--keyboard-visible-height,100dvh) + var(--shared-composer-bottom,24px) + var(--shared-composer-h,54px) + 10px))'
        : 'calc(var(--shared-composer-bottom,24px) + var(--shared-composer-h,54px) + 10px)';
      dock.style.setProperty('position','fixed','important');
      dock.style.setProperty('z-index','46','important');
      dock.style.setProperty('left','50%','important');
      dock.style.setProperty('right','auto','important');
      dock.style.setProperty('transform','translateX(-50%)','important');
      dock.style.setProperty('bottom',dockBottom,'important');
      dock.style.setProperty('width','min(820px,calc(100% - 28px))','important');
      dock.style.setProperty('margin','0','important');
    }
    if(details){
      details.style.setProperty('display','grid','important');
      details.style.setProperty('visibility','visible','important');
      details.style.setProperty('opacity','1','important');
      details.style.setProperty('pointer-events','auto','important');
      details.style.setProperty('width','44px','important');
      details.style.setProperty('height','44px','important');
      details.style.setProperty('position','absolute','important');
      details.style.setProperty('right','max(104px,calc(env(safe-area-inset-right) + 104px))','important');
      details.style.setProperty('top','5px','important');
      details.style.setProperty('z-index','60','important');
    }
  };
  const scheduleSharedMobileComposerChrome=()=>requestAnimationFrame(enforceSharedMobileComposerChrome);
  enforceSharedMobileComposerChrome();
  new MutationObserver(scheduleSharedMobileComposerChrome).observe(document.body,{attributes:true,attributeFilter:['class']});
  window.addEventListener('resize',scheduleSharedMobileComposerChrome);
  window.visualViewport?.addEventListener('resize',scheduleSharedMobileComposerChrome);
  window.visualViewport?.addEventListener('scroll',scheduleSharedMobileComposerChrome);
  document.addEventListener('focusin',event=>{if(event.target?.id==='message')scheduleSharedMobileComposerChrome()});

  const loadChatContextOwner=()=>{
    if(window.__vishnuChatContextOwner||document.querySelector('script[data-chat-context-owner]'))return;
    const context=document.createElement('script');
    context.src='/iphone/chat-context-owner.js';
    context.async=false;
    context.dataset.chatContextOwner='true';
    context.onerror=()=>console.warn('Chat project-context controller could not be loaded.');
    document.body.append(context);
  };

  // Chat owns shared composer/context/menu behavior and must not wait for the
  // much larger Projects/Work enhancement chain. Loading it first removes a
  // first-render race where legacy Home CSS/handlers temporarily win.
  loadChatContextOwner();

  const loadAttentionCenter=()=>{
    if(window.__vishnuWorkAttentionCenter){loadChatContextOwner();return}
    const existing=document.querySelector('script[data-work-attention-center]');
    if(existing){existing.addEventListener('load',loadChatContextOwner,{once:true});existing.addEventListener('error',loadChatContextOwner,{once:true});return}
    const attention=document.createElement('script');
    attention.src='/iphone/work-attention-center.js';
    attention.async=false;
    attention.dataset.workAttentionCenter='true';
    attention.onload=loadChatContextOwner;
    attention.onerror=()=>{console.warn('Work Attention Center could not be loaded.');loadChatContextOwner()};
    document.body.append(attention);
  };
  const loadGlobalAwareness=()=>{
    const loadGlobal=()=>{
      let global=document.querySelector('script[data-global-work-awareness]');
      if(window.__vishnuGlobalWorkAwareness){loadAttentionCenter();return}
      if(global){global.addEventListener('load',loadAttentionCenter,{once:true});return}
      global=document.createElement('script');
      global.src='/iphone/global-work-awareness.js';
      global.async=false;
      global.dataset.globalWorkAwareness='true';
      global.onload=loadAttentionCenter;
      global.onerror=()=>console.warn('Global canonical Work awareness could not be loaded.');
      document.body.append(global);
    };
    let detail=document.querySelector('script[data-workorder-detail]');
    if(window.__vishnuWorkOrderDetail){loadGlobal();return}
    if(detail){detail.addEventListener('load',loadGlobal,{once:true});return}
    detail=document.createElement('script');
    detail.src='/iphone/workorder-detail.js';
    detail.async=false;
    detail.dataset.workorderDetail='true';
    detail.onload=loadGlobal;
    detail.onerror=()=>console.warn('WorkOrder detail surface could not be loaded.');
    document.body.append(detail);
  };
  const loadVisualizations=()=>{
    let visual=document.querySelector('script[data-canonical-project-visualizations]');
    if(window.__vishnuCanonicalProjectVisualizations){loadGlobalAwareness();return}
    if(visual){visual.addEventListener('load',loadGlobalAwareness,{once:true});return}
    visual=document.createElement('script');
    visual.src='/iphone/projects-work-visualization-runtime.js';
    visual.async=false;
    visual.dataset.canonicalProjectVisualizations='true';
    visual.onload=loadGlobalAwareness;
    visual.onerror=()=>console.warn('Canonical Projects visualizations could not be loaded.');
    document.body.append(visual);
  };
  const loadProjectAutonomy=()=>{
    let controls=document.querySelector('script[data-project-autonomy-controls]');
    if(window.__vishnuProjectAutonomyUI){loadVisualizations();return}
    if(controls){controls.addEventListener('load',loadVisualizations,{once:true});return}
    controls=document.createElement('script');
    controls.src='/iphone/project-autonomy-controls.js';
    controls.async=false;
    controls.dataset.projectAutonomyControls='true';
    controls.onload=loadVisualizations;
    controls.onerror=()=>console.warn('Project autonomy controls could not be loaded.');
    document.body.append(controls);
  };
  const ensureCanonicalWork=()=>{
    let script=document.querySelector('script[data-canonical-project-work]');
    if(window.__vishnuCanonicalProjectWork){loadProjectAutonomy();return}
    if(script){script.addEventListener('load',loadProjectAutonomy,{once:true});return}
    script=document.createElement('script');
    script.src='/iphone/projects-work-runtime.js';
    script.async=false;
    script.dataset.canonicalProjectWork='true';
    script.onload=loadProjectAutonomy;
    script.onerror=()=>console.warn('Canonical Projects Work UI could not be loaded.');
    document.body.append(script);
  };
  const existingCore=document.querySelector('script[data-home-chat-core]');
  if(existingCore){
    if(window.__vishnuHomeChatCoreLoaded)ensureCanonicalWork();
    else existingCore.addEventListener('load',ensureCanonicalWork,{once:true});
    return;
  }
  const core=document.createElement('script');
  core.src='/iphone/home-chat-redesign-core.js';
  core.async=false;
  core.dataset.homeChatCore='true';
  core.onload=()=>{window.__vishnuHomeChatCoreLoaded=true;ensureCanonicalWork()};
  core.onerror=()=>console.warn('Home and Chat enhancements could not be loaded.');
  document.body.append(core);
})();
