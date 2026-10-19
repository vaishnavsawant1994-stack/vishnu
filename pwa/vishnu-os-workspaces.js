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
  const newRequestId = () => {
    if(globalThis.crypto?.randomUUID)return globalThis.crypto.randomUUID();
    const random = new Uint8Array(16);
    if(!globalThis.crypto?.getRandomValues)throw new Error('Secure randomness is required for Workspace creation');
    globalThis.crypto.getRandomValues(random);
    return Array.from(random, byte=>byte.toString(16).padStart(2,'0')).join('');
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
    layoutMode:'grid', createBusy:false, workOrders:[], attentionItems:[], attentionCount:0, attentionOpen:false, workError:'',people:[],peopleError:'',peopleQuery:'',selectedAgent:null,spatialAngle:0,settingsSection:0,settingsDraft:null,settingsMessage:'',savingSettings:false,todayData:null,todayAttention:null
  };
  const root=document.createElement('div');
  root.id='vishnuOs1620';
  root.className='vos-hidden';
  root.setAttribute('aria-label','Vishnu OS workspace interface');
  document.body.appendChild(root);
  const shellTitle=()=>({workspaces:'Workspaces',create:'Create a Workspace',overview:'Workspace Overview',studio:'Workspace Studio',spatial:'3D Space',agents:'Team & Agents',assets:'Files & Assets',settings:'Workspace Settings',today:'Today'})[state.page]||'Vishnu OS';
  const btn=(act,label,cls='',extra='')=>'<button type="button" class="vos-btn '+cls+'" data-vos="'+esc(act)+'" '+extra+'>'+label+'</button>';
  const count=(num)=>Number.isFinite(+num)?Number(num):0;
  const tpl=(id)=>templates.find(t=>t[0]===id)||templates[0];
  const formattedDate=(x)=>x?new Date(x).toLocaleDateString(undefined,{month:'short',day:'numeric'}):'';
  const initials=(s)=>String(s||'').trim().slice(0,1).toUpperCase()||'◇';
  function attention(){
    return state.attentionCount ? String(state.attentionCount)+' need attention' : 'Attention';
  }
  function icon(symbol){return '<span class="vos-object-icon" aria-hidden="true">'+symbol+'</span>';}
  function nav(){
    const links=[['home','⌂','Home'],['workspaces','▦','Workspaces'],['work','▷','Work'],['projects','▱','Projects'],['agents','♧','Agents'],['create','✧','Create'],['memory','◫','Memory & Knowledge'],['tools','☷','Apps & Capabilities'],['devices','▣','Devices'],['activities','⌁','Activity']];
    return '<aside class="vos-sidebar"><div class="vos-wordmark">V I S H N U</div><nav aria-label="Main navigation">'+links.map(([id,i,name])=>btn('nav:'+id,'<span aria-hidden="true">'+i+'</span> '+name,id===state.page||['create','overview','studio','spatial','agents','assets','settings'].includes(state.page)&&id==='workspaces'?'is-active':'')).join('')+'</nav><div class="vos-secondary">'+btn('nav:settings','⚙ Settings')+'</div></aside>';
  }
  function header(){
    return '<header class="vos-globalbar">'+btn('back','←','vos-icon-btn')+
      '<button class="vos-context" type="button" data-vos="workspaces">'+esc(state.workspace?.name||'Personal')+' ▾</button>'+
      btn('command','⌕ &nbsp;Search or command <kbd>Ctrl K</kbd>','vos-global-search')+
      btn('attention','♢ &nbsp; '+esc(attention()),'vos-icon-btn')+
      '</header>';
  }
  function mobileNav(){
    return '<nav class="vos-mobile-nav" aria-label="Mobile navigation">'+
      [['home','⌂','Home'],['workspaces','▦','Spaces'],['create','✧','Create'],['work','▷','Work'],['more','•••','More']]
      .map(([id,i,label])=>btn('nav:'+id,'<span aria-hidden="true">'+i+'</span><small>'+label+'</small>',
        state.page===id||['overview','studio','spatial','agents','assets','settings','create'].includes(state.page)&&id==='workspaces'?'is-active':'')).join('')+'</nav>';
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
    return '<div class="vos-tabs">'+[['overview','Overview'],['studio','Studio'],['spatial','3D Space'],['projects','Projects'],['work','Work'],['agents','Agents'],['assets','Assets'],['knowledge','Knowledge'],['activity','Activity'],['settings','Settings']].map(([id,label])=>
      btn(['overview','studio','spatial','agents','assets','settings'].includes(id)?id:'external:'+id,esc(label),state.page===id?'is-active':'')).join('')+'</div>';
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
      btn('studio','◈ Open Workspace Studio')+btn('today','◷ Today')+btn('external:projects','＋ Create Project')+
      btn('link-project','↗ Link Existing Project')+'</div>'+
      '<div class="vos-overview-top">'+section('Workspace resources','<div class="vos-metrics">'+
      '<span>'+count(counts.project)+' Projects</span><span>'+count(counts.work)+' Work links</span><span>'+count(counts.agent)+' Agents linked</span>'+
      '<span>'+count(counts.file)+' Files linked</span></div>')+'</div>'+
      '<div class="vos-overview-grid">'+section('Projects',list.length?list.map(p=>
      '<button class="vos-list-row" data-vos="project:'+esc(p.id)+'" type="button"><strong>'+esc(p.name)+'</strong>'+
      '<span>'+esc(p.description||p.status)+'</span>'+badge(p.status)+'</button>').join(''):
      '<p class="vos-muted">No Projects linked yet. Add an existing Project to this Workspace.</p>')+
      section('Current Work',state.workOrders.length ? state.workOrders.slice(0,5).map(w=>
      '<button class="vos-list-row" type="button" data-vos="work-project:'+esc(w.project_id)+'"><strong>'+
      esc(w.title||'Work item')+'</strong><span>'+esc(w.status||'Unknown')+'</span></button>').join(''):
      '<p class="vos-muted">'+esc(state.workError||'No canonical Work orders for linked Projects.')+'</p>'+

      btn('external:work','Open Work'))+
      section('Agents working','<p class="vos-muted">Agent work details are available from the canonical Agents view. This Workspace does not create simulated agent identities.</p>'+btn('external:agents','Open Agents'))+
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

  // Screens 21–25: deliberately use verified Workspace/Project, Agent, Work and Attention records.
  // Full mesh assets, Agent workspace grants and resource indexing are NOT inferred from screenshots.
  const infoCard=(title,text,action)=>'<section class="vos-detail-card"><h2>'+esc(title)+'</h2><p class="vos-muted">'+esc(text)+'</p>'+(action||'')+'</section>';
  const relatedProjects=()=>state.summary?.projects||[];
  const roomObjects=()=>relatedProjects().map((p,i)=>'<button type="button" class="vos-spatial-object" style="--x:'+((i%3)-1)+';--y:'+Math.floor(i/3)+'" data-vos="project:'+esc(p.id)+'"><span class="vos-spatial-mark" aria-hidden="true">⬡</span><strong>'+esc(p.name)+'</strong><small>'+esc(p.status||'Project')+'</small></button>').join('');
  function spatialPage(){
    const projects=relatedProjects();
    return workspaceHeader()+'<div class="vos-spatial-layout"><div class="vos-spatial-main">'+
      '<div class="vos-spatial-toolbar">'+btn('spatial-orbit','↻ Orbit')+btn('spatial-focus','◎ Focus')+
      btn('spatial-reset','↶ Reset View')+btn('external:projects','Open Projects')+'</div>'+
      '<div class="vos-spatial-viewport" role="region" aria-label="Spatial preview of linked Workspace Projects">'+
      '<div class="vos-spatial-horizon" aria-hidden="true"></div>'+
      '<div class="vos-spatial-scene" style="--angle:'+state.spatialAngle+'deg">'+
      '<div class="vos-spatial-platform" aria-hidden="true">VISHNU</div>'+
      roomObjects()+'</div>'+
      (!projects.length?'<div class="vos-spatial-note">No linked Projects. Link an existing Project to populate this view.</div>':'')+
      '</div><div class="vos-spatial-footer">'+btn('link-project','＋ Link Project','vos-primary')+
      '<span class="vos-muted">Spatial Project preview; production 3D character mesh and asset adapters are not connected.</span></div></div>'+
      '<aside class="vos-inspector vos-new-inspector"><h2>Spatial objects</h2>'+
      '<p class="vos-muted">These are existing, authorized Project references—not copies of Project data.</p>'+
      (projects.map(p=>'<button class="vos-list-row" type="button" data-vos="project:'+esc(p.id)+'"><strong>'+esc(p.name)+'</strong><span>Open →</span></button>').join('')||
      '<p class="vos-muted">No Project objects yet.</p>')+
      '<div class="vos-divider"></div><h3>3D model availability</h3><p class="vos-muted">No canonical 3D character source has been linked. A rendered screenshot is not a mesh.</p></aside></div>';
  }
  function agentPage(){
    const q=state.peopleQuery.trim().toLowerCase();
    const people=state.people.filter(a=>[a.name,a.role,a.description,a.id].join(' ').toLowerCase().includes(q));
    const selected=state.people.find(a=>String(a.id)===String(state.selectedAgent))||people[0];
    return workspaceHeader()+'<div class="vos-new-page"><div class="vos-new-page-main">'+
      '<label class="vos-search">⌕ <input data-vos-input="people-search" aria-label="Search available Agents" placeholder="Search team members, agents, roles, or tools…" value="'+esc(state.peopleQuery)+'"></label>'+
      '<div class="vos-new-summary"><strong>Available canonical Agents ('+state.people.length+')</strong>'+
      btn('external:agents','Manage Agents →')+'</div>'+
      '<p class="vos-muted">Global Agent catalogue. Workspace membership and grants are not yet implemented in the Workspace API; these records are not presented as assigned collaborators.</p>'+
      (state.peopleError?'<div class="vos-error" role="alert">'+esc(state.peopleError)+'</div>':'')+
      (people.length?people.map(a=>'<button class="vos-agent-row '+(selected?.id===a.id?'selected':'')+'" type="button" data-vos="choose-agent:'+esc(a.id)+'">'+
      '<span class="vos-object-icon" aria-hidden="true">✦</span><span><strong>'+esc(a.name||a.id)+'</strong>'+
      '<small>AI Agent · '+esc(a.role||'Unspecified role')+'</small>'+
      '<small>'+esc(a.description||'No description provided')+'</small></span><span class="vos-badge">Inspect →</span></button>').join(''):
      '<div class="vos-empty">No available Agent records matched. No simulated Agents have been created.</div>')+'</div>'+
      '<aside class="vos-inspector vos-new-inspector"><h2>Selected Agent</h2>'+
      (selected?'<div class="vos-detail-heading">'+icon('✦')+'<div><h3>'+esc(selected.name||selected.id)+'</h3><span class="vos-badge">AI Agent</span></div></div>'+
      '<div class="vos-detail-rows"><div><span>Role</span><strong>'+esc(selected.role||'—')+'</strong></div>'+
      '<div><span>Workspace access</span><strong>Not qualified</strong></div></div>'+
      '<p>'+esc(selected.description||'No description provided.')+'</p>'+
      '<p class="vos-muted">Actual capability grants, Work assignments and access changes must be managed through their canonical authority.</p>'+
      btn('external:agents','Open Agent Manager →','vos-primary vos-full'):
      '<p class="vos-muted">Select an available Agent to inspect it.</p>')+'</aside></div>';
  }
  function assetsPage(){
    const links=(state.workspace?.links||[]).filter(l=>['file','artifact'].includes(l.kind));
    return workspaceHeader()+'<div class="vos-new-page"><div class="vos-new-page-main">'+
      '<div class="vos-new-summary"><h2>Files & Assets</h2>'+btn('external:knowledge','Open Knowledge →')+'</div>'+
      infoCard('Linked resource references', 'The Workspace registry currently authorizes Project links only. File and Artifact linking needs a permission-checked canonical Resource API before an asset library can display real data.')+
      (links.length?section('Existing references',links.map(l=>'<div class="vos-list-row"><strong>'+esc(l.kind)+'</strong><span>'+esc(l.resource_id)+'</span></div>').join('')):
      '<div class="vos-empty">No verified Workspace file or artifact links are available. Assets are not fabricated from the design reference.</div>')+
      '<div class="vos-quick">'+btn('external:projects','Open Projects')+btn('external:knowledge','Open Knowledge')+'</div></div>'+
      '<aside class="vos-inspector vos-new-inspector"><h2>Storage & provenance</h2><p class="vos-muted">Resource availability, source device, version, size, and data placement must come from authoritative records. No live storage assertions are made here.</p></aside></div>';
  }
  function settingsPage(){
    const ws=state.workspace||{};
    const draft=state.settingsDraft||{name:ws.name||'',description:ws.description||''};
    const options=['General','Workspace Modules','Intelligence & Context','Team & Agents','Data & Storage',
      'Apps & Capabilities','Notifications & Attention','Sharing & Access','Defaults','Advanced','Danger Zone'];
    return workspaceHeader()+'<div class="vos-settings-title"><h2>Workspace Settings</h2>'+
      '<p class="vos-muted">Configure how this Workspace works, what it can access, and how Vishnu and your agents use it.</p></div>'+
      '<div class="vos-settings-grid"><nav class="vos-settings-menu" aria-label="Workspace settings sections">'+
      options.map((option,i)=>btn('settings-section:'+i,esc(option),i===state.settingsSection?'is-active':i===10?'vos-danger-link':'')).join('')+'</nav>'+
      '<div class="vos-settings-body">'+
      (state.settingsSection===0?
      '<form id="vosWorkspaceSettingsForm" class="vos-settings-form"><h2>General</h2><p class="vos-muted">Basic information about this Workspace.</p>'+
      '<label>Workspace name<input name="name" maxlength="120" required value="'+esc(draft.name)+'"></label>'+
      '<label>Description<textarea name="description" maxlength="2000" rows="4">'+esc(draft.description)+'</textarea></label>'+
      '<label>Workspace type / template<input disabled value="'+esc(tpl(ws.template_id)[1])+'"></label>'+
      '<div class="vos-settings-favorite"><span>☆ Favorite<br><small class="vos-muted">Show this Workspace in favorites.</small></span>'+
      btn('toggle-favorite',ws.pinned?'On ✓':'Off',ws.pinned?'is-active':'')+'</div>'+
      '<p class="vos-muted">Workspace ID: '+esc(ws.id)+'</p>'+
      (state.settingsMessage?'<p role="status" class="vos-save-message">'+esc(state.settingsMessage)+'</p>':'')+
      '<button class="vos-btn vos-primary" type="submit" '+(state.savingSettings?'disabled':'')+'>'+
      (state.savingSettings?'Saving…':'Save Changes')+'</button></form>':
      state.settingsSection===10?
      infoCard('Danger Zone','Archive removes a Workspace from active navigation without deleting associated canonical resources.',
      btn('archive-current',ws.status==='archived'?'Restore Workspace':'Archive Workspace','vos-danger-link'))+
      '<p class="vos-muted">Workspace deletion is unavailable until relationship-impact analysis and durable recovery are implemented.</p>':
      infoCard(options[state.settingsSection], 'This settings category is not yet backed by qualified Workspace configuration APIs. No fake preference values or save actions are exposed.',
      state.settingsSection===3?btn('agents','Inspect available Agents →'):state.settingsSection===5?btn('external:tools','Open Capabilities →'):'')+
      (state.settingsSection===4?'<div class="vos-detail-card"><strong>Required data policies</strong><p class="vos-muted">Device Only · Progress Only · Sync Everywhere · On Demand. Current policy is not exposed by this Workspace API, so it cannot be changed here.</p></div>':''))+
      '</div><aside class="vos-inspector vos-new-inspector"><h2>Workspace Preview</h2>'+icon(esc(ws.icon||initials(ws.name)))+
      '<h3>'+esc(ws.name)+'</h3><p>'+esc(ws.description||'No description')+'</p>'+badge(ws.status||'active')+
      btn('overview','View Workspace →','vos-primary vos-full')+
      '<div class="vos-divider"></div><h3>Quick Actions</h3>'+
      btn('agents','Agents','vos-full')+btn('assets','Files & Assets','vos-full')+
      '<p class="vos-muted">Current Workspace values are provided by the owner-authorized API.</p></aside></div>';
  }
  function todayPage(){
    const data=state.todayData||{work_orders:[],counts:{}};
    const rows=Array.isArray(data.work_orders)?data.work_orders:[];
    const att=state.todayAttention||{items:[],counts:{}};
    const items=Array.isArray(att.items)?att.items:[];
    const present=rows.filter(w=>!['COMPLETED','CANCELLED'].includes(String(w.status||'').toUpperCase()));
    const complete=rows.filter(w=>String(w.status||'').toUpperCase()==='COMPLETED');
    const day=new Intl.DateTimeFormat(undefined,{weekday:'long',month:'long',day:'numeric'}).format(new Date());
    const hour=new Date().getHours(),greeting=hour<12?'Good morning':hour<17?'Good afternoon':'Good evening';
    const attentionRows=items.slice(0,4).map((a,i)=>'<button class="vos-list-row" data-vos="today-attention:'+i+'"><strong>'+esc(a.title||a.reason||a.type||'Action required')+'</strong><span>'+esc(a.priority||a.kind||'Attention')+'</span></button>').join('');
    const workRows=present.slice(0,6).map(w=>'<button class="vos-list-row" data-vos="work-project:'+esc(w.project_id||'')+'"><strong>'+esc(w.title||'Work')+'</strong><span>'+esc(w.project_name||w.status||'Work')+'</span>'+badge(w.status||'unknown')+'</button>').join('');
    return '<div class="vos-today"><div class="vos-today-hero"><small>'+esc(day)+'</small>'+
      '<h1>'+esc(greeting)+'.</h1><p>Here is what matters today.</p>'+
      '<div class="vos-context-composer"><span aria-hidden="true">⌕</span><input data-vos-input="ask" placeholder="Ask Vishnu about my day, my work, or anything…" aria-label="Ask Vishnu about my day">'+btn('ask','➤','vos-primary')+'</div>'+
      '<div class="vos-quick">'+btn('attention','What needs my attention?')+btn('nav:work','Show active Work')+'</div></div>'+
      '<div class="vos-new-page"><div class="vos-new-page-main">'+
      section('Needs Your Attention ('+Number(att.counts?.total||items.length)+')',attentionRows||'<div class="vos-empty">Nothing currently needs your action.</div>')+
      section('Active Work ('+present.length+')',workRows||'<div class="vos-empty">No current canonical Work is available.</div>')+
      section('Recently Completed',complete.slice(0,5).map(w=>'<div class="vos-list-row"><strong>'+esc(w.title||'Completed Work')+'</strong>'+badge('completed')+'</div>').join('')||'<p class="vos-muted">No completed Work in this response.</p>')+
      '</div><aside class="vos-inspector vos-new-inspector"><h2>Today Summary</h2>'+
      '<div class="vos-detail-rows"><div><span>Active Work</span><strong>'+present.length+'</strong></div>'+
      '<div><span>Needs Attention</span><strong>'+Number(att.counts?.total||items.length)+'</strong></div></div>'+
      '<h3>Source transparency</h3><p class="vos-muted">Today reads canonical Work and Attention projections. Calendar events, continuation history, and recommendation data are omitted until an authorized source is connected.</p>'+
      btn('reload-today','Refresh Today','vos-primary vos-full')+'</aside></div></div>';
  }
  async function openToday(){
    state.page='today';state.error='';state.loading=true;show('today');
    const [work,attentionResult]=await Promise.allSettled([bridge().api('/work/summary'),bridge().api('/work/attention')]);
    state.todayData=work.status==='fulfilled'?work.value:{work_orders:[],counts:{}};
    state.todayAttention=attentionResult.status==='fulfilled'?attentionResult.value:{items:[],counts:{}};
    state.loading=false;state.error=work.status==='rejected'||attentionResult.status==='rejected'?
      'One or more Today sources could not be loaded; unavailable sections show no simulated data.':'';
    render();
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
  function attentionDialog(){
    if(!state.attentionOpen)return '';
    return '<div class="vos-command-backdrop" data-vos="close-attention"><div class="vos-command-panel" role="dialog" aria-modal="true" aria-labelledby="vosAttentionTitle">'+
      '<div class="vos-command-title"><h2 id="vosAttentionTitle">Needs your attention</h2>'+btn('close-attention','×','vos-icon-btn')+
      '<p>Verified pending items from Vishnu Work authority.</p></div>'+
      (state.attentionItems.length?state.attentionItems.map((item,index)=>
        '<button type="button" class="vos-list-row" data-vos="attention-item:'+index+'"><strong>'+
        esc(item.title||item.summary||item.label||'Attention item')+'</strong>'+
        '<span>'+esc(item.status||item.type||'Review')+'</span><span>→</span></button>').join(''):
        '<p class="vos-muted">There are no pending attention items.</p>')+
      '</div></div>';
  }
  function render(){
    if(root.classList.contains('vos-hidden'))return;
    const content=state.page==='workspaces'?workspacesPage():state.page==='create'?createPage():
      state.page==='overview'?summaryPage():state.page==='studio'?studioPage():state.page==='spatial'?spatialPage():state.page==='agents'?agentPage():state.page==='assets'?assetsPage():state.page==='settings'?settingsPage():todayPage();
    root.innerHTML=nav()+'<div class="vos-main">'+
      '<div class="vos-mobile-header">'+btn('menu','☰','vos-icon-btn')+'<strong>V I S H N U</strong>'+
      btn('command','⌕','vos-icon-btn')+'</div>'+
      header()+'<main class="vos-page">'+loading()+error()+content+'</main></div>'+mobileNav()+commandPalette()+attentionDialog();
    const focused=root.querySelector('[data-vos-input="command"]');
    if(state.command&&focused)focused.focus();
  }
  function show(page){
    state.page=page;
    root.classList.remove('vos-hidden','vos-command-only');
    document.body.classList.add('vos-active');
    render();
  }
  function hide(){
    root.classList.add('vos-hidden');
    root.classList.remove('vos-command-only');
    document.body.classList.remove('vos-active');
    state.command=false;
  }
  function openCommand(){
    const hidden=root.classList.contains('vos-hidden');
    if(hidden){root.classList.remove('vos-hidden');root.classList.add('vos-command-only');}
    state.command=true;state.commandText='';state.commandFilter='all';render();
  }
  function closeCommand(){
    state.command=false;
    if(root.classList.contains('vos-command-only'))hide();else render();
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
    state.page=page;root.classList.remove('vos-command-only','vos-hidden');
    document.body.classList.add('vos-active');render();
    try{
      const result=await api('/'+encodeURIComponent(id)+'/summary');
      state.workspace=result.workspace;state.summary=result;
      const related=new Set((state.workspace.links||[]).filter(l=>l.kind==='project').map(l=>l.resource_id));
      state.workError='';
      const [workResponse,attentionResponse]=await Promise.allSettled([
        bridge().api('/work/summary'),bridge().api('/work/attention')
      ]);
      if(workResponse.status==='fulfilled'){
        state.workOrders=(workResponse.value.work_orders||[]).filter(w=>related.has(w.project_id)&&
          !['COMPLETED','CANCELLED'].includes(String(w.status||'').toUpperCase()));
      }else{state.workOrders=[];state.workError='Live Work is currently unavailable.';}
      if(attentionResponse.status==='fulfilled'){
        const snapshot=attentionResponse.value;
        state.attentionItems=Array.isArray(snapshot.items)?snapshot.items:[];
        state.attentionCount=Number(snapshot.counts?.total||state.attentionItems.length);
      }else{state.attentionItems=[];state.attentionCount=0;}

      if(page==='agents'){
         try{const results=await bridge().api('/agents');state.people=Array.isArray(results.agents)?results.agents:[];state.peopleError='';}
         catch(e){state.people=[];state.peopleError=e.message||'Agent directory unavailable';}
       }
       if(page==='settings'){
         state.settingsDraft={name:state.workspace.name,description:state.workspace.description||''};
         state.settingsMessage='';
       }
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
    if(action==='reload'){if(state.page==='today')return openToday();if(['studio','overview','spatial','agents','assets','settings'].includes(state.page)&&state.workspace)return openWorkspace(state.workspace.id,state.page);return refresh();}
    if(action==='command'){openCommand();return;}
    if(action==='close-command'){closeCommand();return;}
    if(action==='back'||action==='workspace-list'||action==='workspaces'){state.command=false;show('workspaces');return refresh();}
    if(action==='create'){state.command=false;state.template='blank';state.draft={name:'',description:''};state.createRequestId=null;show('create');return;}
    if(['overview','studio','spatial','agents','assets','settings'].includes(action)){return openWorkspace(state.workspace.id,action);}
    if(action==='today'||action==='reload-today')return openToday();
    if(action==='spatial-orbit'){state.spatialAngle=(state.spatialAngle+35)%360;render();return;}
    if(action==='spatial-reset'||action==='spatial-focus'){state.spatialAngle=0;render();return;}
    if(action.startsWith('choose-agent:')){state.selectedAgent=action.slice(13);render();return;}
    if(action.startsWith('settings-section:')){state.settingsSection=Number(action.slice(17));render();return;}
    if(action==='toggle-favorite'){
      try{const updated=await api('/'+encodeURIComponent(state.workspace.id),{method:'PATCH',body:JSON.stringify({pinned:!state.workspace.pinned})});state.workspace=updated.workspace;state.settingsMessage='Favorite preference saved.';render();}
      catch(e){state.error=e.message;render();}return;
    }
    if(action==='archive-current'){
      if(!confirm('Archive this Workspace? Project and resource records will be preserved.'))return;
      try{const updated=await api('/'+encodeURIComponent(state.workspace.id),{method:'PATCH',body:JSON.stringify({status:state.workspace.status==='archived'?'active':'archived'})});state.workspace=updated.workspace;render();}catch(e){state.error=e.message;render();}return;
    }
    if(action.startsWith('today-attention:')){
      const item=state.todayAttention?.items?.[Number(action.slice(16))];
      if(item){hide();await window.__vishnuGlobalWorkAwareness?.openAttention?.(item);}return;
    }
    if(action==='attention'){
      state.command=false;state.attentionOpen=true;render();return;
    }
    if(action==='close-attention'){state.attentionOpen=false;render();return;}
    if(action.startsWith('attention-item:')){
      const selected=state.attentionItems[Number(action.slice(15))];
      state.attentionOpen=false;hide();
      const opened=await window.__vishnuGlobalWorkAwareness?.openAttention?.(selected);
      if(!opened)bridge()?.openModule?.('projects');
      return;
    }
    if(action.startsWith('work-project:')){
      hide();const projectId=action.slice(13);
      if(typeof window.openProject==='function')window.openProject(projectId,'live');
      else bridge()?.openModule?.('projects');
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
      hide();bridge()?.openModule?.(name==='work'?'projects':name==='more'?'home':name);
      return;
    }
    if(action.startsWith('external:')){
      hide();bridge()?.openModule?.(action.slice(9)==='work'?'projects':action.slice(9));return;
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
    if(button.classList.contains('vos-command-backdrop')&&event.target.closest('.vos-command-panel'))return;
    event.preventDefault();event.stopPropagation();
    perform(button.dataset.vos);
  },true);
  root.addEventListener('submit',async event=>{
    if(event.target.id==='vosWorkspaceSettingsForm'){
      event.preventDefault();const form=event.target;
      state.settingsDraft={name:form.elements.name.value,description:form.elements.description.value};
      state.savingSettings=true;state.settingsMessage='';render();
      try{const response=await api('/'+encodeURIComponent(state.workspace.id),{method:'PATCH',body:JSON.stringify(state.settingsDraft)});
        state.workspace=response.workspace;state.settingsDraft={name:response.workspace.name,description:response.workspace.description};state.settingsMessage='Changes saved.';
      }catch(error){state.settingsMessage='Save failed: '+(error.message||'Unknown error');}
      finally{state.savingSettings=false;render();}return;
    }
    if(event.target.id!=='vosWorkspaceForm')return;
    event.preventDefault();
    const fd=new FormData(event.target);
    state.draft={name:String(fd.get('name')||''),description:String(fd.get('description')||'')};
    if(!state.createRequestId)state.createRequestId=newRequestId();
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
    if(event.target.dataset.vosInput==='people-search'){
      state.peopleQuery=event.target.value;const pos=event.target.selectionStart;render();
      const field=root.querySelector('[data-vos-input="people-search"]');field?.focus();field?.setSelectionRange(pos,pos);return;
    }
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
      if(state.command){closeCommand();}else openCommand();return;
    }
    if(event.key==='Escape'&&!root.classList.contains('vos-hidden')){
      event.preventDefault();event.stopImmediatePropagation();
      if(state.command){closeCommand();}else if(state.attentionOpen){state.attentionOpen=false;render();}else hide();
    }
  },true);
  window.vishnuOsWorkspaces={open:()=>{show('workspaces');return refresh(true);},openWorkspace,
    command:()=>openCommand(),today:()=>openToday()};
})();