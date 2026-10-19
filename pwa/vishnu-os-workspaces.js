/* Vishnu OS screens 16–20: progressive UI on top of the existing PWA.
 * No copy of the canonical Project/Work/Agent authorities.
 * All mutations use owner-authorized /iphone/api/os/workspaces endpoints.
 */
(() => {
  'use strict';
  const bridge = () => window.vishnuChatBridge;
  const api = (path, options) => {
    if (!bridge()?.api) return Promise.reject(new Error('Vishnu session is not ready'));
    return bridge().api('/os/workspaces' + path, options);
  };
  const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c =>
    ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const templates = [
    ['blank','Blank Workspace','Start with a clean workspace and set it up your way.','◇'],
    ['software','Software Development','Code, repositories, testing and releases.','</>'],
    ['product','Product Development','Plan, design, build and launch products.','⬡'],
    ['business','Business','Operations, customers, workflows and documents.','▥'],
    ['research','Research','Sources, papers, evidence and notes.','▣'],
    ['creative','Creative','Design, media, content and assets.','✧'],
    ['3d','3D / Character','3D models, references, renders and animation.','⬢'],
    ['personal','Personal','Your notes, planning and personal projects.','♙'],
    ['learning','Learning','Courses, notes, exercises and progress.','▤']
  ];
  const state = {
    page:'workspaces', previous:'workspaces', workspaces:[], selected:null,
    workspace:null, summary:null, views:[], view:null, template:'blank',
    query:'', filter:'all', draft:{name:'',description:''}, createRequestId:null, loading:false, error:'', command:false,
    commandText:'', commandFilter:'all', focusPanel:null,
    layoutMode:'grid', createBusy:false
  };
  const root=document.createElement('div');
  root.id='vishnuOs1620';
  root.className='vos-hidden';
  root.setAttribute('aria-label','Vishnu OS workspace interface');
  document.body.appendChild(root);
  const shellTitle=()=>state.page==='workspaces'?'Workspaces':state.page==='create'?'Create a Workspace':state.page==='overview'?'Workspace Overview':'Workspace Studio';
  const btn=(act,label,cls='',extra='')=>'<button type="button" class="vos-btn '+cls+'" data-vos="'+esc(act)+'" '+extra+'>'+label+'</button>';
  const count=(num)=>Number.isFinite(+num)?Number(num):0;
  const tpl=(id)=>templates.find(t=>t[0]===id)||templates[0];
  const formattedDate=(x)=>x?new Date(x).toLocaleDateString(undefined,{month:'short',day:'numeric'}):'';
  const initials=(s)=>String(s||'').trim().slice(0,1).toUpperCase()||'◇';
  function attention(){return '';/* owner Attention counts are not inferred from workspace membership */}
  function icon(symbol){return '<span class="vos-object-icon" aria-hidden="true">'+symbol+'</span>';}
  function nav(){
    const links=[['home','⌂','Home'],['workspaces','▦','Workspaces'],['work','▷','Work'],['projects','▱','Projects'],['agents','♧','Agents'],['create','✧','Create'],['memory','◫','Memory & Knowledge'],['tools','☷','Apps & Capabilities'],['devices','▣','Devices'],['activities','⌁','Activity']];
    return '<aside class="vos-sidebar"><div class="vos-wordmark">V I S H N U</div><nav aria-label="Main navigation">'+links.map(([id,i,name])=>btn('nav:'+id,'<span aria-hidden="true">'+i+'</span> '+name,id===state.page||['create','overview','studio'].includes(state.page)&&id==='workspaces'?'is-active':'')).join('')+'</nav><div class="vos-secondary">'+btn('nav:settings','⚙ Settings')+'</div></aside>';
  }
  function header(){
    return '<header class="vos-globalbar">'+btn('back','←','vos-icon-btn')+
      '<button class="vos-context" type="button" data-vos="workspaces">'+esc(state.workspace?.name||'Personal')+' ▾</button>'+
      btn('command','⌕ &nbsp;Search or command <kbd>Ctrl K</kbd>','vos-global-search')+
      btn('attention','♢ &nbsp; Attention','vos-icon-btn')+
      '</header>';
  }
  function mobileNav(){
    return '<nav class="vos-mobile-nav" aria-label="Mobile navigation">'+
      [['home','⌂','Home'],['workspaces','▦','Spaces'],['create','✧','Create'],['work','▷','Work'],['more','•••','More']]
      .map(([id,i,label])=>btn('nav:'+id,'<span aria-hidden="true">'+i+'</span><small>'+label+'</small>',
        state.page===id||['overview','studio','create'].includes(state.page)&&id==='workspaces'?'is-active':'')).join('')+'</nav>';
  }
  function loading(){return state.loading?'<p class="vos-muted" role="status">Loading Workspace information…</p>':''}
  function error(){return state.error?'<div class="vos-error" role="alert">'+esc(state.error)+' '+btn('reload','Retry')+'</div>':''}
  function section(label,inner,action=''){
    return '<section class="vos-section"><div class="vos-section-head"><h2>'+esc(label)+'</h2>'+action+'</div>'+inner+'</section>';
  }
  function badge(status){return '<span class="vos-badge" data-status="'+esc(status||'')+'">'+esc(status||'Active')+'</span>'}
  function metrics(ws){
    return '<div class="vos-metrics"><span>◫ '+count(ws.linked_counts?.project)+' Projects</span><span>◎ '+count(ws.linked_counts?.work)+' Work</span><span>♧ '+count(ws.linked_counts?.agent)+' Agents</span><span>▤ '+count(ws.linked_counts?.file)+' Files</span></div>';
  }
  function workspaceCard(ws){
    const selected=state.selected===ws.id;
    return '<article class="vos-workspace-card '+(selected?'selected':'')+'">'+
      '<button type="button" data-vos="select:'+esc(ws.id)+'" class="vos-card-select" aria-pressed="'+selected+'">'+
      icon(esc(ws.icon||initials(ws.name)))+badge(ws.status)+
      '<strong>'+esc(ws.name)+'</strong><span class="vos-muted">'+esc(tpl(ws.template_id)[1])+'</span>'+
      '<p>'+esc(ws.description||'Your workspace for everything you are building.')+'</p>'+metrics(ws)+
      '</button><div class="vos-card-actions">'+btn('open:'+ws.id,'Open Workspace →','vos-link')+
      btn('pin:'+ws.id,ws.pinned?'Unpin':'Pin','vos-link')+'</div></article>';
  }
  function inspector(){
    const ws=state.workspaces.find(w=>w.id===state.selected);
    if(!ws)return '<aside class="vos-inspector">'+section('Workspace Details','<p class="vos-muted">Select a Workspace to inspect it.</p>')+'</aside>';
    return '<aside class="vos-inspector"><h2>Workspace Details</h2>'+
      '<div class="vos-detail-heading">'+icon(esc(ws.icon||initials(ws.name)))+'<div><h3>'+esc(ws.name)+'</h3>'+badge(ws.status)+'</div></div>'+
      '<p class="vos-muted">'+esc(ws.description||tpl(ws.template_id)[2])+'</p>'+
      '<div class="vos-detail-rows">'+Object.entries(ws.linked_counts||{}).filter(([k,v])=>v).map(([k,v])=>
        '<div><span>'+esc(k)+'</span><strong>'+count(v)+'</strong></div>').join('')+'</div>'+
      btn('open:'+ws.id,'Open Workspace →','vos-primary vos-full')+
      '<div class="vos-divider"></div>'+
      btn('pin:'+ws.id,ws.pinned?'Unpin workspace':'Pin workspace','vos-full')+
      btn('archive:'+ws.id,ws.status==='archived'?'Restore Workspace':'Archive Workspace','vos-full')+'</aside>';
  }
  function workspacesPage(){
    const query=state.query.toLowerCase().trim();
    const rows=state.workspaces.filter(w=>(state.filter==='all'||state.filter==='pinned'&&w.pinned||
      state.filter==='active'&&w.status==='active'||state.filter==='archived'&&w.status==='archived'||
      state.filter===w.template_id)&&(!query||[w.name,w.description,tpl(w.template_id)[1]].join(' ').toLowerCase().includes(query)));
    const visibleFilters=[['all','All'],['pinned','Pinned'],['active','Active'],['business','Business'],['software','Development'],['research','Research'],['archived','Archived']];
    const filters='<div class="vos-filters">'+visibleFilters.map(([k,l])=>btn('filter:'+k,
      esc(l),state.filter===k?'is-active':'')).join('')+'</div>';
    const cards=rows.length?'<div class="vos-workspace-grid">'+rows.map(workspaceCard).join('')+'</div>':
      '<div class="vos-empty">No matching Workspaces. '+btn('create','Create Workspace')+'</div>';
    return '<div class="vos-header"><div>'+icon('⬡')+'<h1>Workspaces</h1><p>Your organized worlds for everything you’re building.</p></div>'+
      btn('create','＋ New Workspace','vos-primary')+'</div>'+
      '<div class="vos-library"><div class="vos-library-main">'+
      '<label class="vos-search">⌕ <input aria-label="Search workspaces" data-vos-input="workspace-search" placeholder="Search workspaces…" value="'+esc(state.query)+'"></label>'+
      filters+section('Pinned', state.workspaces.filter(w=>w.pinned&&w.status!=='archived').length?'<div class="vos-pinned">'+state.workspaces.filter(w=>w.pinned&&w.status!=='archived').map(workspaceCard).join('')+'</div>':'<p class="vos-muted">No pinned Workspaces.</p>')+
      section('All Workspaces',cards)+
      '</div>'+inspector()+'</div>';
  }
  function createPage(){
    return '<div class="vos-header"><div>'+icon('◇')+'<h1>Create a Workspace</h1><p>Give your work a dedicated place for conversations, projects, agents, files, knowledge and execution.</p></div></div>'+
      '<div class="vos-create-grid"><div><h2>1. Choose a template</h2><p class="vos-muted">Start with a template or a blank Workspace. Customize everything later.</p>'+
      '<div class="vos-template-grid">'+templates.map(([id,name,description,symbol])=>
      '<button class="vos-template '+(state.template===id?'selected':'')+'" data-vos="template:'+id+'" type="button" aria-pressed="'+(state.template===id)+'">'+
      icon(symbol)+'<strong>'+esc(name)+'</strong><small>'+esc(description)+'</small></button>').join('')+'</div>'+
      '<div class="vos-describe"><h2>Or describe what you’re building</h2>'+
      '<p>Ask Vishnu to help propose a Workspace structure.</p><textarea data-vos-input="description-ai" placeholder="Describe your Workspace…"></textarea>'+
      btn('ask-template','Ask Vishnu to suggest a template →')+'</div>'+
      '<form id="vosWorkspaceForm" class="vos-create-form"><h2>2. Workspace details</h2>'+
      '<label>Workspace name *<input name="name" value="'+esc(state.draft?.name||'')+'" maxlength="120" required placeholder="My new Workspace"></label>'+
      '<label>Description (optional)<textarea name="description" maxlength="2000" placeholder="What will you build here?">'+esc(state.draft?.description||'')+'</textarea></label>'+
      '<p class="vos-muted">Template: '+esc(tpl(state.template)[1])+'</p>'+
      '<button class="vos-btn vos-primary" type="submit" '+(state.createBusy?'disabled':'')+'>'+
      (state.createBusy?'Creating…':'Create Workspace →')+'</button></form></div>'+
      '<aside class="vos-inspector"><h2>Template Preview</h2>'+icon(tpl(state.template)[3])+
      '<h3>'+esc(tpl(state.template)[1])+'</h3><p>'+esc(tpl(state.template)[2])+'</p>'+
      '<div class="vos-divider"></div><h3>You can always add</h3>'+
      '<p>Projects<br>Work items<br>Agents<br>Files & Assets<br>Knowledge<br>Conversations<br>Studio panels</p>'+
      '<p class="vos-muted">Templates suggest organization; they never create fabricated Projects or Agents.</p></aside></div>';
  }
  function workspaceTabs(){
    return '<div class="vos-tabs">'+[['overview','Overview'],['studio','Studio'],['projects','Projects'],['work','Work'],['agents','Agents'],['files','Files & Assets'],['knowledge','Knowledge'],['activity','Activity'],['settings','Settings']].map(([id,label])=>
      btn(['overview','studio'].includes(id)?id:'external:'+id,esc(label),state.page===id?'is-active':'')).join('')+'</div>';
  }
  function workspaceHeader(){
    const ws=state.workspace;
    if(!ws)return '';
    return '<div class="vos-ws-heading">'+icon(esc(ws.icon||initials(ws.name)))+
      '<div><h1>'+esc(ws.name)+'</h1><p>'+esc(tpl(ws.template_id)[1])+' · '+esc(ws.status)+'</p>'+
      '<p>'+esc(ws.description)+'</p></div>'+
      btn('workspace-list','All Workspaces','vos-link')+'</div>'+workspaceTabs()+
      '<div class="vos-context-composer"><span aria-hidden="true">›_</span><input data-vos-input="ask" aria-label="Ask Vishnu in this workspace" placeholder="Ask Vishnu anything in this workspace…">'+
      btn('ask','➤','vos-primary')+'</div>';
  }
  function summaryPage(){
    const list=(state.summary?.projects||[]);
    const counts=state.workspace?.linked_counts||{};
    return workspaceHeader()+'<div class="vos-quick">'+
      btn('studio','◈ Open Workspace Studio')+btn('external:projects','＋ Create Project')+
      btn('link-project','↗ Link Existing Project')+'</div>'+
      '<div class="vos-overview-top">'+section('Workspace resources','<div class="vos-metrics">'+
      '<span>'+count(counts.project)+' Projects</span><span>'+count(counts.work)+' Work links</span><span>'+count(counts.agent)+' Agents linked</span>'+
      '<span>'+count(counts.file)+' Files linked</span></div>')+'</div>'+
      '<div class="vos-overview-grid">'+section('Projects',list.length?list.map(p=>
      '<button class="vos-list-row" data-vos="project:'+esc(p.id)+'" type="button"><strong>'+esc(p.name)+'</strong>'+
      '<span>'+esc(p.description||p.status)+'</span>'+badge(p.status)+'</button>').join(''):
      '<p class="vos-muted">No Projects linked yet. Add an existing Project to this Workspace.</p>')+
      section('Current Work','<p class="vos-muted">Work status is available in the canonical Work view. Workspace-local Work aggregation is not yet connected.</p>'+
      btn('external:work','Open Work'))+
      section('Agents working','<p class="vos-muted">Open the canonical Agents view for verified live activity.</p>'+btn('external:agents','Open Agents'))+
      section('Files & Knowledge','<p class="vos-muted">Files and Knowledge remain with their canonical authorities.</p>'+
      btn('external:knowledge','Open Knowledge'))+
      section('Activity','<p class="vos-muted">View verified system activity in the Activity section.</p>'+
      btn('external:activities','Open Activity'))+'</div>';
  }
  function studioPanel(panel,i){
    const match=(state.summary?.projects||[]).find(p=>p.id===panel.resource_id);
    const title=match?.name||panel.label||'Unavailable resource';
    return '<article class="vos-studio-panel" data-panel="'+i+'"><header><strong>'+esc(title)+'</strong>'+
      btn('focus:'+i,'⤢','vos-link','aria-label="Focus panel"')+
      btn('move:'+i,'↔','vos-link','aria-label="Move panel to next position"')+
      btn('remove:'+i,'×','vos-link','aria-label="Remove panel"')+'</header>'+
      '<p class="vos-muted">'+esc(panel.kind)+' · '+(match?'Linked canonical Project':'Resource not available')+'</p>'+
      (match?'<p>'+esc(match.description)+'</p>'+badge(match.status)+btn('project:'+match.id,'Open Project →'):
      '<p class="vos-muted">This item is not currently reachable. No data has been copied.</p>')+'</article>';
  }
  function studioPage(){
    const panels=state.view?.layout?.panels||[];
    const narrowed=state.focusPanel===null?panels:panels.filter((_,i)=>i===state.focusPanel);
    return workspaceHeader()+
      '<div class="vos-studio-toolbar">'+btn('add-panel','＋ Add','vos-primary')+
      btn('layout','Layout: '+esc(state.layoutMode))+
      btn('views','Views ▾')+btn('save-view','Save View')+
      (state.focusPanel!==null?btn('unfocus','Exit Focus'):'')+'</div>'+
      section('Open panels ('+panels.length+')',
      narrowed.length?'<div class="vos-studio-grid '+(state.focusPanel!==null?'focused':state.layoutMode==='list'?'vos-list':'')+'">'+
      narrowed.map((panel,index)=>studioPanel(panel,state.focusPanel===null?index:state.focusPanel)).join('')+'</div>':
      '<div class="vos-empty">Your Studio is ready. Add an existing Project to the workbench.</div>')+
      '<p class="vos-muted">Layouts save references to Projects, not copies of their content. Full document/code editors are not yet integrated in this slice.</p>';
  }
  function commandPalette(){
    if(!state.command)return '';
    const commands=[
      ['workspaces','Open Workspaces','Navigation','nav:workspaces'],
      ['create','Create Workspace','Create','create'],
      ['projects','Open Projects','Navigation','external:projects'],
      ['agents','Show active Agents','Agents','external:agents'],
      ['attention','Review pending approvals','Work','attention'],
      ['home','Go Home','Navigation','nav:home'],
      ['work','Open Work','Work','external:work'],
      ['knowledge','Open Knowledge','Navigation','external:knowledge'],
      ['settings','Open Settings','Settings','external:settings']
    ];
    state.workspaces.forEach(ws=>commands.push(['w'+ws.id,'Open '+ws.name,'Workspaces','open:'+ws.id]));
    const q=state.commandText.trim().toLowerCase();
    const visible=commands.filter(([id,label,category])=>
      (!q||[label,category].join(' ').toLowerCase().includes(q))&&
      (state.commandFilter==='all'||category.toLowerCase()===state.commandFilter));
    return '<div class="vos-command-backdrop" data-vos="close-command"><div class="vos-command-panel" role="dialog" aria-modal="true" aria-labelledby="vosCommandTitle" tabindex="-1">'+
      '<div class="vos-command-title"><h2 id="vosCommandTitle">Command Center</h2>'+btn('close-command','×','vos-icon-btn')+
      '<p>What do you want Vishnu to do?</p></div>'+
      '<label class="vos-search vos-command-input">&gt;_ <input data-vos-input="command" aria-label="Command" placeholder="What do you want Vishnu to do?" value="'+esc(state.commandText)+'" autocomplete="off"></label>'+
      '<p class="vos-muted">Find a safe action, destination or resource. Sensitive actions remain governed.</p>'+
      '<div class="vos-filters">'+['all','navigation','create','work','agents','workspaces'].map(x=>
        btn('command-filter:'+x,x[0].toUpperCase()+x.slice(1),state.commandFilter===x?'is-active':'')).join('')+'</div>'+
      section('Commands',visible.length?visible.map(([id,label,category,action])=>
      '<button class="vos-list-row" data-vos="'+esc(action)+'" type="button"><strong>'+esc(label)+'</strong><span>'+esc(category)+'</span><span>→</span></button>').join(''):
      '<p class="vos-muted">No matching command. Use Global Search or Ask Vishnu for an open-ended request.</p>')+
      '</div></div>';
  }
  function render(){
    if(root.classList.contains('vos-hidden'))return;
    const content=state.page==='workspaces'?workspacesPage():state.page==='create'?createPage():
      state.page==='overview'?summaryPage():studioPage();
    root.innerHTML=nav()+'<div class="vos-main">'+
      '<div class="vos-mobile-header">'+btn('menu','☰','vos-icon-btn')+'<strong>V I S H N U</strong>'+
      btn('command','⌕','vos-icon-btn')+'</div>'+
      header()+'<main class="vos-page">'+loading()+error()+content+'</main></div>'+mobileNav()+commandPalette();
    const focused=root.querySelector('[data-vos-input="command"]');
    if(state.command&&focused)focused.focus();
  }
  function show(page){
    state.page=page;
    root.classList.remove('vos-hidden');
    document.body.classList.add('vos-active');
    render();
  }
  function hide(){
    root.classList.add('vos-hidden');
    document.body.classList.remove('vos-active');
    state.command=false;
  }
  async function refresh(selectFirst=false){
    state.loading=true;state.error='';render();
    try{
      const result=await api('');
      state.workspaces=result.workspaces||[];
      if(selectFirst&&!state.selected)state.selected=state.workspaces[0]?.id||null;
    }catch(error){state.error=error.message||'Workspaces could not be loaded';}
    finally{state.loading=false;render();}
  }
  async function openWorkspace(id, page='overview'){
    state.error='';state.loading=true;state.selected=id;
    state.page=page;render();
    try{
      const result=await api('/'+encodeURIComponent(id)+'/summary');
      state.workspace=result.workspace;state.summary=result;
      if(page==='studio'){
        const loaded=await api('/'+encodeURIComponent(id)+'/studio/views');
        state.views=loaded.views||[];
        state.view=state.views[0]||null;
        state.focusPanel=null;
      }
    }catch(error){state.error=error.message||'Workspace unavailable';}
    finally{state.loading=false;render();}
  }
  async function perform(action){
    if(action==='reload'){if(['studio','overview'].includes(state.page)&&state.workspace)return openWorkspace(state.workspace.id,state.page);return refresh();}
    if(action==='command'){state.command=true;state.commandText='';state.commandFilter='all';render();return;}
    if(action==='close-command'){state.command=false;render();return;}
    if(action==='back'||action==='workspace-list'||action==='workspaces'){state.command=false;show('workspaces');return refresh();}
    if(action==='create'){state.command=false;state.page='create';state.template='blank';state.draft={name:'',description:''};state.createRequestId=null;render();return;}
    if(action==='overview'||action==='studio'){return openWorkspace(state.workspace.id,action);}
    if(action==='attention'){
      hide();bridge()?.openModule?.('activities');
      bridge()?.showToast?.('Review approvals in the canonical Attention Center / Work view.');
      return;
    }
    if(action==='menu'){hide();document.getElementById('historyButton')?.click();return;}
    if(action==='ask'){
      const text=root.querySelector('[data-vos-input="ask"]')?.value?.trim();
      if(text){hide();bridge()?.openModule?.('home');bridge()?.setDraft?.(text);}
      return;
    }
    if(action==='ask-template'){
      const text=root.querySelector('[data-vos-input="description-ai"]')?.value?.trim();
      if(!text){state.error='Describe what you want to build first.';render();return;}
      hide();bridge()?.openModule?.('home');
      bridge()?.setDraft?.('Help me choose a Vishnu Workspace template and structure for: '+text);
      return;
    }
    if(action==='add-panel'){
      const projects=state.summary?.projects||[];
      if(!projects.length){state.error='Link a Project to this Workspace before adding a Project panel.';render();return;}
      const remaining=projects.find(p=>!state.view?.layout?.panels?.some(q=>q.resource_id===p.id));
      if(!remaining){state.error='All linked Projects are already open in this view.';render();return;}
      if(!state.view)state.view={name:'Default',layout:{panels:[]}};
      state.view.layout.panels.push({kind:'project',resource_id:remaining.id});
      state.error='';render();return;
    }
    if(action==='save-view'){
      if(!state.workspace)return;
      const body={name:state.view?.name||'Default',layout:state.view?.layout||{panels:[]}};
      try{
        const path='/'+encodeURIComponent(state.workspace.id)+'/studio/views';
        const edit=Boolean(state.view?.id);
        const result=await api(path+(edit?'/'+encodeURIComponent(state.view.id):''),{
          method:edit?'PUT':'POST',body:JSON.stringify(body)});
        state.view=result.view;state.views=state.views.filter(v=>v.id!==result.view.id);state.views.unshift(result.view);state.error='';render();
      }catch(error){state.error=error.message;render();}
      return;
    }
    if(action==='views'){
      if(!state.views.length){state.error='No saved views yet. Add panels and select Save View.';render();return;}
      const index=state.views.findIndex(x=>x.id===state.view?.id);
      state.view=state.views[(index+1)%state.views.length];state.focusPanel=null;render();return;
    }
    if(action==='layout'){state.layoutMode=state.layoutMode==='grid'?'list':'grid';render();return;}
    if(action==='unfocus'){state.focusPanel=null;render();return;}
    if(action==='link-project'){
      try{
        const result=await bridge().api('/projects');
        const rows=result.projects||result.items||[];
        const candidate=rows.find(p=>!(state.workspace.links||[]).some(l=>l.kind==='project'&&l.resource_id===p.id));
        if(!candidate){state.error='No unlinked Projects found. Create one in the Projects section first.';render();return;}
        await api('/'+state.workspace.id+'/links',{method:'POST',body:JSON.stringify({kind:'project',resource_id:candidate.id})});
        await openWorkspace(state.workspace.id,state.page);
      }catch(error){state.error=error.message||'Could not link Project';render();}
      return;
    }
    if(action.startsWith('focus:')){state.focusPanel=Number(action.split(':')[1]);render();return;}
    if(action.startsWith('remove:')){
      const n=Number(action.split(':')[1]);state.view?.layout?.panels?.splice(n,1);state.focusPanel=null;render();return;
    }
    if(action.startsWith('move:')){
      const n=Number(action.split(':')[1]),p=state.view?.layout?.panels||[];
      if(p.length>1){const target=(n+1)%p.length;[p[n],p[target]]=[p[target],p[n]];}render();return;
    }
    if(action.startsWith('nav:')){
      state.command=false;const name=action.slice(4);
      if(name==='workspaces')return show('workspaces'),refresh();
      if(name==='create')return show('create');
      hide();bridge()?.openModule?.(name==='more'?'home':name);
      return;
    }
    if(action.startsWith('external:')){
      hide();bridge()?.openModule?.(action.slice(9)==='projects'?'projects':action.slice(9));return;
    }
    if(action.startsWith('open:')){state.command=false;return openWorkspace(action.slice(5));}
    if(action.startsWith('project:')){
      hide();const id=action.slice(8);if(window.openProject)window.openProject(id);
      else bridge()?.openModule?.('projects');
      return;
    }
    if(action.startsWith('select:')){state.selected=action.slice(7);render();return;}
    if(action.startsWith('filter:')){state.filter=action.slice(7);render();return;}
    if(action.startsWith('template:')){state.template=action.slice(9);render();return;}
    if(action.startsWith('command-filter:')){state.commandFilter=action.slice(15);render();return;}
    if(action.startsWith('pin:')||action.startsWith('archive:')){
      const pin=action.startsWith('pin:'),id=action.slice(pin?4:8);
      const ws=state.workspaces.find(w=>w.id===id);if(!ws)return;
      try{
        await api('/'+encodeURIComponent(id),{method:'PATCH',body:JSON.stringify(pin?{pinned:!ws.pinned}:
          {status:ws.status==='archived'?'active':'archived'})});
        await refresh();
      }catch(error){state.error=error.message;render();}
    }
  }
  document.addEventListener('click',event=>{
    const navTarget=event.target.closest('[data-app-module="labs"]');
    if(navTarget&&!root.contains(navTarget)){
      event.preventDefault();event.stopImmediatePropagation();
      show('workspaces');refresh(true);return;
    }
    if(root.classList.contains('vos-hidden'))return;
    const button=event.target.closest('[data-vos]');
    if(!button||!root.contains(button))return;
    if(button.dataset.vos==='close-command'&&event.target.closest('.vos-command-panel'))return;
    event.preventDefault();event.stopPropagation();
    perform(button.dataset.vos);
  },true);
  root.addEventListener('submit',async event=>{
    if(event.target.id!=='vosWorkspaceForm')return;
    event.preventDefault();
    const fd=new FormData(event.target);
    state.draft={name:String(fd.get('name')||''),description:String(fd.get('description')||'')};
    if(!state.createRequestId)state.createRequestId=crypto.randomUUID();
    state.createBusy=true;state.error='';render();
    try{
      const created=await api('',{method:'POST',body:JSON.stringify({
        name:state.draft.name,description:state.draft.description,
        template_id:state.template,request_id:state.createRequestId
      })});
      state.createRequestId=null;await refresh();await openWorkspace(created.workspace.id);
    }catch(error){state.error=error.message||'Workspace could not be created';state.createBusy=false;render();}
    finally{state.createBusy=false;}
  });
  root.addEventListener('input',event=>{
    if(event.target.dataset.vosInput==='workspace-search'){
      state.query=event.target.value;
      const position=event.target.selectionStart;render();
      const field=root.querySelector('[data-vos-input="workspace-search"]');field?.focus();field?.setSelectionRange(position,position);
    }
    if(event.target.closest('#vosWorkspaceForm')){
      const f=event.target.closest('form');
      state.draft={name:f.elements.name?.value||'', description:f.elements.description?.value||''};
    }
    if(event.target.dataset.vosInput==='command'){
      state.commandText=event.target.value;
      const position=event.target.selectionStart;render();
      const field=root.querySelector('[data-vos-input="command"]');field?.setSelectionRange(position,position);
    }
  });
  document.addEventListener('keydown',event=>{
    if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'){
      if(document.querySelector('.enroll:not(.hidden)'))return;
      event.preventDefault();event.stopImmediatePropagation();
      if(root.classList.contains('vos-hidden'))show('workspaces');
      state.command=!state.command;render();return;
    }
    if(event.key==='Escape'&&!root.classList.contains('vos-hidden')){
      event.preventDefault();event.stopImmediatePropagation();
      if(state.command){state.command=false;render();}else hide();
    }
  },true);
  window.vishnuOsWorkspaces={open:()=>{show('workspaces');return refresh(true);},openWorkspace,
    command:()=>{if(root.classList.contains('vos-hidden'))show('workspaces');state.command=true;render();}};
})();