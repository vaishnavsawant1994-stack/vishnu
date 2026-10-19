/* Reference Home and system-wide chat. Reuses the existing sphere, chat, and navigation. */
(function(){
  const $ = window.$ || (id => document.getElementById(id));
  const folder = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h6l2 2h10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>';
  function keepMobileHomeClearOfDock(){
    if(document.getElementById('vMobileHomeViewportFix')) return;
    const style=document.createElement('style');
    style.id='vMobileHomeViewportFix';
    style.textContent=`@media(max-width:760px){
      body.v-ref.home-landing .home{height:100dvh!important;max-height:100dvh!important;min-height:0!important;padding-top:calc(var(--home-fixed-top,0px) + var(--home-fixed-header-h,66px) + 4px)!important;padding-bottom:8px!important;overflow:hidden!important;background:transparent!important;background-image:none!important}
      body.v-ref.home-landing .presence{height:calc(100dvh - var(--home-fixed-top,0px) - var(--home-fixed-header-h,66px) - 142px)!important;max-height:calc(100dvh - var(--home-fixed-top,0px) - var(--home-fixed-header-h,66px) - 142px)!important;background:transparent!important;background-image:none!important}
      body.v-ref.home-landing #homeIntro{background:transparent!important;background-image:none!important}
      body.v-ref.home-landing .home-intro{max-height:100%;min-height:0;padding-top:8px!important;padding-bottom:12px}
      body.v-ref.home-landing .home-intro{scrollbar-width:none!important;-ms-overflow-style:none!important}
      body.v-ref.home-landing .home-intro::-webkit-scrollbar{display:none!important;width:0!important;height:0!important}
      body.v-ref.home-landing .home-greeting{margin:8px 0 9px}
      body.v-ref.home-landing .home-sphere-stage{order:-1}
      body.v-ref.home-landing .home-sphere-stage{height:195px;margin:0 0 11px}
      body.v-ref.home-landing .home-sphere-stage .core-stage{width:156px!important;height:156px!important;min-width:156px!important;max-width:156px!important}
      body.v-ref.home-landing .v-shortcuts{grid-template-rows:repeat(2,92px);grid-auto-rows:92px;gap:10px;margin:6px 0 28px}
      body.v-ref.home-landing .v-card{height:92px;min-height:92px;padding:9px;grid-template-columns:32px minmax(0,1fr) 8px;gap:6px}
      body.v-ref.home-landing .v-card .v-icon{width:32px;height:32px}
      body.v-ref.home-landing .v-recent-head{margin-bottom:6px}
      body.v-ref.home-landing #vChatDock{background:transparent!important;background-image:none!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important;box-shadow:none!important}
      body.v-ref.home-landing #composer{background:transparent!important;background-image:none!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important;box-shadow:none!important;border-color:rgba(146,157,175,.3)!important}
      body.v-ref.home-landing .topbar-actions{display:flex!important}
      body.v-ref.home-landing .topbar-actions .chat-menu-button{display:none!important}
      body.v-ref.home-landing .topbar-actions .owner-status{display:grid!important;grid-column:3;grid-row:1;justify-self:end;width:44px;height:44px;min-width:44px;min-height:44px;padding:0;place-items:center}
      body.v-ref.home-landing .topbar-actions .owner-status .trust{display:none!important}
    }
    @media(max-width:350px){
      body.v-ref.home-landing .v-shortcuts{grid-template-rows:repeat(2,108px);grid-auto-rows:108px}
      body.v-ref.home-landing .v-card{height:108px;min-height:108px;grid-template-columns:30px minmax(0,1fr) 8px;gap:5px;padding:9px 7px}
      body.v-ref.home-landing .v-card .v-icon{width:30px;height:30px}
    }
    @media(max-width:760px) and (max-height:650px){
      body.v-ref.home-landing .home-intro{padding-top:8px!important}
      body.v-ref.home-landing .home-sphere-stage{height:148px;margin:0 0 5px}
    }
    body.v-ref.home-landing .home-sphere-stage{order:-1}`;
    document.head.append(style);
  }
  function placeSphere(){
    const stage = document.querySelector('.core-stage');
    const homeStage = $('homeSphereStage');
    const headerBrand = document.querySelector('.header-core');
    if(!stage || !homeStage || !headerBrand) return;
    if(document.body.classList.contains('home-landing')) homeStage.appendChild(stage);
    else headerBrand.appendChild(stage);
    if(typeof resizeCanvas === 'function') requestAnimationFrame(resizeCanvas);
  }

  function personalizeGreeting(){
    const node = $('homeGreeting');
    if(!node || typeof greeting !== 'function') return;
    const base = greeting().replace(/\.$/, '');
    const name = typeof ownerDisplayName === 'function' ? ownerDisplayName() : '';
    node.textContent = name ? base + ', ' + name : base;
  }

  function syncAttachIcon(){
    const button = $('attachmentButton');
    if(!button) return;
    const home = document.body.classList.contains('home-landing');
    button.setAttribute('aria-label', home ? 'Attach a file' : 'Add to message');
    button.innerHTML = home
      ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 12.5 14.8 5.7a3 3 0 0 1 4.2 4.2l-8.2 8.2a4.2 4.2 0 0 1-6-6l7.4-7.4"/></svg>'
      : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>';
  }

  async function loadRecentProjects(){
    const host = $('homeProjectList');
    if(!host) return;
    host.replaceChildren();
    const loading = document.createElement('p');
    loading.className = 'v-empty';
    loading.textContent = 'Loading your projects…';
    host.append(loading);
    try{
      const data = await api('/projects');
      const rows = (Array.isArray(data.projects) ? data.projects : []).slice(0, 4);
      host.replaceChildren();
      if(!rows.length){
        const empty = document.createElement('div');
        empty.className = 'v-empty';
        empty.innerHTML = '<p>No projects yet. Create a workspace to keep files, tasks, and chat scoped to that project.</p>';
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'v-action';
        button.textContent = 'Create a project';
        button.onclick = () => openProjects();
        empty.append(button);
        host.append(empty);
        return;
      }
      const details = await Promise.all(rows.map(async project => {
        try { return (await api('/projects/'+encodeURIComponent(project.id))).project || project; }
        catch { return project; }
      }));
      details.forEach(project => {
        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'v-project';
        const activity = Array.isArray(project.activity) ? project.activity[0] : null;
        const nextTask = (project.tasks || []).find(task => task.status !== 'done');
        const status = nextTask ? 'Next: '+nextTask.title
          : activity && activity.action !== 'created project' && (activity.detail || activity.action)
            ? (activity.detail || activity.action)
          : project.updated_at ? 'Updated '+new Date(project.updated_at).toLocaleDateString(undefined,{month:'short',day:'numeric'})
          : 'No recent update yet';
        row.innerHTML = '<span class="v-icon">'+folder+'</span><span><strong></strong><small></small></span><span class="v-chev" aria-hidden="true">›</span>';
        row.querySelector('strong').textContent = project.name || 'Untitled project';
        row.querySelector('small').textContent = status;
        row.onclick = () => openProjectWorkspace(project.id);
        host.append(row);
      });
    }catch(error){
      host.replaceChildren();
      const box = document.createElement('div');
      box.className = 'v-error';
      box.innerHTML = '<p></p>';
      box.querySelector('p').textContent = error && error.status === 404
        ? 'Projects are not available on this runtime yet.'
        : (error.message || 'Could not load projects.');
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'v-action';
      retry.textContent = 'Retry';
      retry.onclick = () => loadRecentProjects();
      box.append(retry);
      host.append(box);
    }
  }

  function openProjects(){
    closeAllDrawers();
    if(typeof openModule === 'function') openModule('projects');
    else showToast('Projects are not available in this build.');
  }
  async function openProjectWorkspace(id, tab='overview'){
    closeAllDrawers();
    if(typeof openProject === 'function' && typeof openModule === 'function'){
      await openModule('projects');
      await openProject(id, tab);
    }
    else if(typeof openModule === 'function') await openModule('projects');
    else showToast('That project workspace is not available.');
  }
  async function assignWork(){
    closeAllDrawers();
    let rows = [];
    try{ rows = (await api('/projects')).projects || []; }
    catch(error){ showToast(error.message||'Could not load your projects to assign this task.'); return; }
    if(!rows.length){
      if(typeof openModule === 'function') await openModule('projects');
      else showToast('Task assignment is not available yet.');
      return;
    }
    if(typeof projectDialog !== 'function') return openProjects();
    const choice = await projectDialog('Choose a project for this task',[{
      name:'project_id',label:'Project',type:'select',required:true,
      options:rows.map(project=>[project.id,project.name||'Untitled project'])
    }]);
    if(!choice || !choice.project_id) return;
    await openProjectWorkspace(choice.project_id,'plan');
    requestAnimationFrame(()=>document.querySelector('[data-project-action="new-task"]')?.click());
  }

  function wireHome(){
    const timelineButton = $('ownerButton');
    if(timelineButton){timelineButton.setAttribute('aria-label','Open right sidebar timeline');timelineButton.title='Open timeline';}
    const cards = {
      vProjects: openProjects,
      vAssign: () => assignWork().catch(error => showToast(error.message)),
      vToday: () => { closeAllDrawers(); if(typeof openTodayScreen === 'function') openTodayScreen(); else showToast('Today is not available in this build.'); },
      vMemory: () => { closeAllDrawers(); openModule('memory'); },
      vViewAllProjects: openProjects
    };
    Object.entries(cards).forEach(([id, action]) => { const node = $(id); if(node) node.onclick = action; });
    const fresh = $('vNewChat');
    if(fresh) fresh.onclick = () => createConversation().catch(error => showToast(error.message||'Could not start a new chat. Your previous conversations are unchanged.'));
    const chip = $('vContextChip');
    if(chip) chip.onclick = () => openContextChooser().catch(error => showToast(error.message));
    const scope = $('vScopeButton');
    if(scope) scope.onclick = () => openContextChooser().catch(error => showToast(error.message));
  }

  async function openContextChooser(){
    let rows = [];
    try{ rows = (await api('/projects')).projects || []; }
    catch(error){ showToast(error.message||'Could not load projects. General chat remains unchanged.'); return; }
    if(typeof projectDialog !== 'function') return showToast('Project context selection is unavailable. General chat remains unchanged.');
    const choice = await projectDialog('Choose conversation context',[{
      name:'project_id',label:'Context',type:'select',required:false,
      value:'',options:[['','General chat · No project context'],...rows.map(project=>[project.id,project.name||'Untitled project'])]
    }]);
    if(!choice || !choice.project_id) return;
    const id=choice.project_id;
    await api('/projects/'+encodeURIComponent(id)+'/conversation',{method:'POST',body:'{}'});
    await openProjectWorkspace(id,'chat');
  }

  async function renderWorkCards(){
    const stream = $('messageStream');
    if(!stream || document.body.classList.contains('home-landing')) return;
    stream.querySelectorAll('.v-work').forEach(node => {
      const actions=node.querySelector('.message-actions');
      const assistant=[...stream.querySelectorAll('.message-entry.assistant')].at(-1);
      if(actions && assistant && !assistant.contains(actions)) assistant.querySelector('.message-footer')?.append(actions);
      node.remove();
    });
    const lastUser = [...conversationEvents].reverse().find(event => event.kind === 'user_message');
    const asked = lastUser && /update|attention|continue|task|work/i.test(String(lastUser.payload && lastUser.payload.text || ''));
    if(!asked) return;
    let details = [];
    try{
      const projects=(await api('/projects')).projects||[];
      details=await Promise.all(projects.slice(0, 4).map(async project=>{
        const result=await api('/projects/'+encodeURIComponent(project.id));
        return result.project||project;
      }));
    }catch(error){
      const block=document.createElement('section');
      block.className='v-work';
      block.setAttribute('aria-label','Project work status');
      const failure=document.createElement('div');
      failure.className='v-work-empty';
      failure.setAttribute('role','alert');
      const text=document.createElement('span');
      text.textContent='Could not load current project tasks. '+(error.message||'');
      const retry=document.createElement('button');
      retry.type='button';
      retry.className='v-action';
      retry.textContent='Retry';
      retry.onclick=()=>renderWorkCards();
      failure.append(text,retry);
      block.append(failure);
      stream.append(block);
      return;
    }
    const attention = [];
    const next = [];
    details.forEach(project => {
      (project.tasks || []).forEach(task => {
        const item = {project, task};
        if(task.owner === 'vishnu' && task.status === 'planned') next.push(item);
        else if(task.status === 'blocked') attention.push(item);
      });
    });
    const block = document.createElement('section');
    block.className = 'v-work';
    block.setAttribute('aria-label', 'Project work from your saved project data');
    const attentionTitle=document.createElement('h3');
    attentionTitle.textContent='Items that need your attention';
    block.append(attentionTitle);
    if(attention.length) attention.slice(0,3).forEach(item=>block.append(workCard(item,'review')));
    else block.append(emptyWork('No blocked project tasks need your attention.'));
    const nextTitle=document.createElement('h3');
    nextTitle.textContent='Next action for Vishnu';
    block.append(nextTitle);
    if(next.length) next.slice(0,2).forEach(item=>block.append(workCard(item,'start')));
    else block.append(emptyWork('There is no planned Vishnu task ready to start.'));
    stream.append(block);
    const assistant=[...stream.querySelectorAll('.message-entry.assistant')].at(-1);
    const actionBar=assistant?.querySelector('.message-actions');
    if(actionBar) block.append(actionBar);
    if(conversationPinnedToBottom) stream.scrollTop = stream.scrollHeight;
  }

  function emptyWork(message){
    const empty=document.createElement('p');
    empty.className='v-work-empty';
    empty.textContent=message;
    return empty;
  }

  function workCard(item, actionKind){
    const card = document.createElement('article');
    card.className = 'v-work-card';
    const isNext=actionKind==='start';
    const status=isNext?'Ready to start':'Blocked · Needs your input';
    const open=document.createElement('button');
    open.type='button';
    open.className='v-work-open';
    open.innerHTML='<span class="v-icon">'+folder+'</span><span><strong></strong><small></small><span class="v-pill"></span></span>';
    open.querySelector('strong').textContent=isNext?item.task.title:item.project.name;
    open.querySelector('small').textContent=isNext?'From: '+(item.project.name||'Project'):'Project · '+(item.project.goal||item.project.description||'Workspace');
    const statusPill=open.querySelector('.v-pill');
    statusPill.classList.add(isNext?'ok':'warn');
    statusPill.textContent=status;
    open.setAttribute('aria-label',(isNext?'Open task ':'Open project ')+(isNext?item.task.title:item.project.name));
    open.onclick=()=>openProjectWorkspace(item.project.id,'plan').then(()=>{
      if(!isNext && typeof editProjectTask==='function') editProjectTask(item.task.id);
    });
    const action = document.createElement('button');
    action.type = 'button';
    action.className = 'v-action';
    action.textContent=isNext?'Start work':'Review';
    action.onclick=()=>runWorkAction(item,actionKind);
    card.append(open,action);
    return card;
  }

  async function runWorkAction(item, actionKind){
    if(actionKind === 'start'){
      try{
        await openProjectWorkspace(item.project.id,'chat');
        if(typeof sendProjectMessage!=='function')throw new Error('Project task chat is unavailable in this build.');
        const prompt=`Start work on the project task “${item.task.title}”${item.task.description?': '+item.task.description:''}. Take the next concrete step that the existing project workflow supports. Use approvals for consequential actions, ask me if you need missing information, and report what actually happened. Do not claim a task or background operation has started unless the corresponding operation succeeds.`;
        await sendProjectMessage(prompt);
      }catch(error){ showToast(error.message || 'Could not start that task.'); }
      return;
    }
    await openProjectWorkspace(item.project.id,'plan');
    if(typeof editProjectTask==='function') editProjectTask(item.task.id);
  }

  function boot(){
    keepMobileHomeClearOfDock();
    document.body.classList.add('v-ref');
    const originalHome = enterHomeLanding;
    enterHomeLanding = function(){
      const activeId=currentConversationId||(appStatus?.conversation?.thread?.id||appStatus?.conversation?.conversation?.id||appStatus?.conversation?.id||null);
      originalHome();
      // Home clears the visible transcript while keeping the saved system chat active.
      currentConversationId=activeId;
      personalizeGreeting(); placeSphere(); syncAttachIcon(); loadRecentProjects();
      const homeIntro=$('homeIntro'),composer=$('composer'),composerSlot=$('referenceComposerSlot');
      if(composer&&composerSlot&&composer.parentNode!==composerSlot)composerSlot.appendChild(composer);
      if(homeIntro){homeIntro.scrollTop=0;requestAnimationFrame(()=>{homeIntro.scrollTop=0;});}
    };
    const originalConversation = enterConversationView;
    enterConversationView = function(){ originalConversation(); placeSphere(); syncAttachIcon(); };
    const originalRender = renderMessages;
    renderMessages = function(){ originalRender(); renderWorkCards(); };
    wireHome();
    personalizeGreeting();
    placeSphere();
    syncAttachIcon();
    if(document.body.classList.contains('home-landing')) loadRecentProjects();
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();

// Projects Work adapter is intentionally loaded after projects-workspace-views.js so
// it overrides only Work Plan and Live Work while preserving every other Project view.
(()=>{
  if(document.querySelector('script[data-canonical-project-work]'))return;
  const script=document.createElement('script');
  script.src='/iphone/projects-work-runtime.js';
  script.async=false;
  script.dataset.canonicalProjectWork='true';
  script.onerror=()=>console.warn('Canonical Projects Work UI could not be loaded.');
  document.body.append(script);
})();
