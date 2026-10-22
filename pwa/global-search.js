/* P2-06 Global Search — extends the existing openModule('search') shell. */
(() => {
'use strict';
if (window.__vishnuP206Installed) return;
window.__vishnuP206Installed = true;
const $=id=>document.getElementById(id);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const enc=x=>encodeURIComponent(String(x)),types=[
 ['all','All','⌕'],['conversations','Chats','◉'],['workspaces','Workspaces','▦'],
 ['projects','Projects','⬡'],['files','Files','▤'],['work','Work','▣'],['agents','Agents','♧'],
 ['knowledge','Knowledge','▧'],['memory','Memory','✧']
];
const state={query:'',category:'all',sort:'relevance',time:'all',project:'',workspace:'',tag:'',
 results:[],counts:{},coverage:{},selected:null,detail:null,offset:0,next:null,
 loading:false,error:'',filtersOpen:false,mobileDetail:false,
 pending:0,detailPending:0,navPending:0,timer:0,recent:[],abort:null,initialized:false,live:false,actionBusy:false,summary:''};
const active=()=>state.live&&document.body.classList.contains('global-search-mode');
const message=text=>{if($('gsNotice'))$('gsNotice').textContent=text||''};
const format=t=>{if(!t)return '';const d=new Date(t);return Number.isNaN(d.valueOf())?'':new Intl.DateTimeFormat(undefined,{dateStyle:'medium'}).format(d)};
const icon=type=>Object.fromEntries(types.map(x=>[x[0],x[2]]))[type]||'⌕';
const label=type=>Object.fromEntries(types.map(x=>[x[0],x[1]]))[type]||type;
function setRecent(query){const q=String(query||'').trim();if(q.length<2||q.length>100)return;state.recent=[q,...state.recent.filter(x=>x!==q)].slice(0,7);renderRecent()}
function renderRecent(){const h=$('gsRecent');if(!h)return;h.innerHTML='<strong>Recent Searches <small>(this session)</small></strong>'+
 (state.recent.length?state.recent.map((q,i)=>'<button type="button" data-gs-recent="'+i+'">'+esc(q)+'</button>').join(''):'<small>No recent searches</small>')+
 '<button type="button" data-gs-action="clear-recent" class="gs-recent-clear" '+(state.recent.length?'':'disabled')+'>Clear all</button>'}
function updateFacets(){const h=$('gsScopes');if(!h)return;const lower=Object.values(state.coverage).some(x=>x==='partial');h.innerHTML=types.map(([key,text,ic])=>
 '<button type="button" class="'+(state.category===key?'active':'')+'" aria-pressed="'+(state.category===key)+'" data-gs-category="'+key+'"><span>'+ic+'</span>'+text+
 ((state.query&&state.counts[key]!=null)?' <small>'+(lower?'≥':'')+Number(state.counts[key])+'</small>':'')+'</button>').join('')}
function updateCoverage(){const h=$('gsCoverage');if(!h)return;
 const unavailable=Object.entries(state.coverage).filter(([,v])=>!['available','not_scoped'].includes(v));
 const good=Object.values(state.coverage).filter(v=>v==='available').length;
 h.textContent=state.query?good+' live sources · '+(unavailable.length?unavailable.map(([k,v])=>label(k)+': '+v).join(' · '):'All queried sources available')+'. Results and counts are limited to each source’s current search coverage.':'Search is private to this authenticated Vishnu runtime. Only permitted sources are queried.';
}
function resultItem(item){return '<button type="button" class="gs-result-main '+(state.selected?.type===item.type&&state.selected?.id===item.id?'selected':'')+
 '" data-gs-select="'+esc(item.type)+'" data-gs-id="'+esc(item.id)+'" data-gs-project="'+esc(item.project_id||'')+'">'+
 '<span class="gs-result-icon gs-icon-'+esc(item.type)+'">'+icon(item.type)+'</span><span class="gs-result-copy"><strong>'+esc(item.title)+'</strong><span class="gs-summary">'+esc(item.excerpt||'No preview recorded')+'</span>'+
 '<span class="gs-badges"><em>'+label(item.type)+'</em>'+(item.status?'<em>'+esc(item.status)+'</em>':'')+
 (item.project_id?'<em>Project linked</em>':'')+(item.workspace_id?'<em>Workspace linked</em>':'')+'</span></span>'+
 '<span class="gs-date">'+format(item.updated_at)+'</span><span class="gs-arrow">›</span></button>'}
function renderResults(append=false){const h=$('globalSearchResults');if(!h)return;
 const rows=state.results;
 if(!rows.length){h.innerHTML=state.query?
 '<div class="gs-empty"><strong>No matching results</strong><p>Try another phrase or category. Unavailable sources are listed above.</p></div>':
 '<div class="gs-empty"><strong>Search your Vishnu</strong><p>Find authorized conversations, projects, tasks, files and more.</p></div>';return}
 const count=state.counts[state.category]||0;
 h.innerHTML='<div class="gs-result-title"><strong>Search Results'+(state.query?' ('+(Object.values(state.coverage).some(x=>x==='partial')?'≥':'')+count+')':'')+'</strong><small>Showing matched authorized records</small></div>'+
 rows.map(resultItem).join('')+
 (state.next!==null?'<button type="button" class="gs-load-more" data-gs-action="more">Load more results</button>':'');
}
function detailMarkup(){
 const item=state.detail?.result||state.selected;
 if(!item)return '<div class="gs-no-selection"><span>⌕</span><h2>Choose a search result</h2><p>Inspect its source and open the real record.</p></div>';
 const related=state.detail?.related||[],preview=state.detail?.preview||[];
 return '<div class="gs-detail-head"><button type="button" class="gs-back" data-gs-action="back" aria-label="Back to search results">‹</button>'+
 '<span class="gs-result-icon gs-icon-'+esc(item.type)+'">'+icon(item.type)+'</span><div><h2>'+esc(item.title)+'</h2><p>'+label(item.type)+' · '+format(item.updated_at)+'</p></div></div>'+
 '<div class="gs-detail-actions"><button data-gs-action="open">Open '+(item.type==='conversations'?'in Chat':'Original')+'</button>'+
 '<button data-gs-action="copy">Copy Link</button>'+
 (item.type==='conversations'?'<button data-gs-action="summarize">Summarize</button><button data-gs-action="organize">Move to Project</button>':'')+
 (item.project_id?'<button data-gs-action="task">Create Task</button>':'')+'</div>'+
 '<div class="gs-preview-card"><header>Preview</header>'+
 (state.summary?'<div class="gs-preview-message"><strong>Verified AI Summary</strong><p>'+esc(state.summary)+'</p></div>':'')+
 (preview.length?preview.map(msg=>'<div class="gs-preview-message"><strong>'+ (msg.role==='user_message'?'You':'Vishnu')+'</strong><p>'+esc(msg.text)+'</p></div>').join(''):
 '<p>'+esc(item.excerpt||'A searchable preview is not available. Open the source for its full information.')+'</p>')+'</div>'+
 '<div class="gs-related-card"><header>Related Items</header>'+
 (related.length?related.map((r,i)=>'<button type="button" data-gs-related="'+i+'"><span>'+icon(r.type)+'</span>'+esc(r.title)+'</button>').join(''):
 '<p>No verified resource relationships are available for this result.</p>')+'</div>';
}
function renderDetail(){const h=$('gsDetail');if(!h)return;h.innerHTML=detailMarkup();h.classList.toggle('mobile-open',Boolean(state.mobileDetail&&state.selected));document.querySelector('.global-search-page')?.classList.toggle('detail-open',Boolean(state.mobileDetail&&state.selected))}
function renderMeta(){const h=$('gsMeta');if(!h)return;const item=state.detail?.result||state.selected;
 if(!item){h.innerHTML='<h3>Result Details</h3><p>Select a result to inspect its type, source and real associations.</p>';return}
 h.innerHTML='<h3>Result Details</h3><dl><dt>Type</dt><dd>'+label(item.type)+'</dd><dt>Source</dt><dd>'+esc(item.source||item.type)+'</dd>'+
 (item.project_id?'<dt>Project ID</dt><dd>'+esc(item.project_id)+'</dd>':'')+
 (item.workspace_id?'<dt>Workspace ID</dt><dd>'+esc(item.workspace_id)+'</dd>':'')+
 (item.status?'<dt>Status</dt><dd>'+esc(item.status)+'</dd>':'')+
 '<dt>Updated</dt><dd>'+esc(format(item.updated_at)||'Unavailable')+'</dd></dl><div class="gs-meta-actions">'+
 '<button data-gs-action="open">Open original</button><button data-gs-action="copy">Copy private app link</button></div>';
}
function queryParams(offset=0){
 const p=new URLSearchParams({q:state.query.trim(),category:state.category,sort:state.sort,limit:'25',offset:String(offset)});
 if(state.project)p.set('project_id',state.project);
 if(state.workspace)p.set('workspace_id',state.workspace);
 if(state.tag)p.set('tag',state.tag);
 const now=new Date(),day=n=>{const d=new Date(now);d.setDate(d.getDate()-n);return d.toISOString().slice(0,10)};
 if(state.time==='today'){p.set('date_from',day(0));p.set('date_to',day(0))}
 if(state.time==='7')p.set('date_from',day(6));
 if(state.time==='30')p.set('date_from',day(29));
 return p.toString();
}
async function search({append=false,remember=false}={}){
 const seq=++state.pending;
 if(!state.query.trim()){state.results=[];state.counts={};state.coverage={};state.next=null;state.selected=null;state.detail=null;renderResults();renderDetail();renderMeta();updateFacets();updateCoverage();return}
 if(remember)setRecent(state.query);
 const offset=append?state.next||0:0;
 state.loading=true;
 if(!append){$('globalSearchResults').innerHTML='<div class="gs-loading" role="status">Searching permitted Vishnu sources…</div>';message('Searching…')}
 try{
   const data=await window.api('/search?'+queryParams(offset));
   if(seq!==state.pending||!active())return;
   state.results=append?[...state.results,...(data.results||[])]:data.results||[];
   state.next=data.next_offset??null;state.counts=data.counts||{};state.coverage=data.coverage||{};
   if(!append){state.selected=null;state.detail=null;state.mobileDetail=false}
   renderResults();renderDetail();renderMeta();updateCoverage();updateFacets();
   message(state.results.length+' loaded results. '+(state.next===null?'No further page.':'More results available.'));
 }catch(e){if(seq!==state.pending)return;state.error=e.message;
  $('globalSearchResults').innerHTML='<div class="gs-error" role="alert"><strong>Search unavailable</strong><p>'+esc(e.message)+'</p><button type="button" data-gs-action="retry">Retry</button></div>';message('Search failed; no results were fabricated.')}
 finally{if(seq===state.pending)state.loading=false}
}
async function select(item){
 const id=++state.detailPending;state.selected=item;state.detail=null;state.summary='';state.mobileDetail=true;renderDetail();renderMeta();renderResults();
 try{const qp=item.project_id?'?project_id='+enc(item.project_id):'';
  const data=await window.api('/search/result/'+enc(item.type)+'/'+enc(item.id)+qp);
  if(id!==state.detailPending||!active())return;
  state.detail=data;renderDetail();renderMeta();
 }catch(e){if(id===state.detailPending){state.selected=null;state.detail=null;state.mobileDetail=false;message('Source preview unavailable or no longer authorized: '+e.message);renderDetail();renderMeta()}}
}
async function navigate(item){
 if(!item)return;
 const type=item.type,id=item.id,mod=type==='conversations'?'chat':type==='projects'||type==='work'||type==='files'&&item.project_id?'projects':type==='workspaces'?'labs':type==='agents'?'agents':type==='memory'?'memory':'knowledge';
 if(type==='conversations'&&typeof window.openConversation==='function'){
   window.openConversation(id).catch(e=>window.showToast?.(e.message));document.body.classList.remove('global-search-mode');return
 }
 await window.openModule(mod);
 if((type==='projects'||item.project_id)&&typeof window.openProject==='function'){
   await window.openProject(item.project_id||id);
 }
 if(type==='workspaces'&&typeof window.openWorkspace==='function')await window.openWorkspace(id);
 if(!['conversations','projects','workspaces'].includes(type))window.showToast?.('Opened source module. Select '+item.title+' to inspect the full record.');
}
async function action(kind){
 const item=state.detail?.result||state.selected;
 if(kind==='retry')return search({remember:false});
 if(kind==='clear'){state.query='';$('globalSearchQuery').value='';clearTimeout(state.timer);return search()}
 if(kind==='clear-recent'){state.recent=[];renderRecent();return}
 if(kind==='more')return search({append:true});
 if(kind==='reset'){state.category='all';state.sort='relevance';state.time='all';state.project='';state.workspace='';state.tag='';state.filtersOpen=false;renderFilters();return search()}
 if(kind==='back'){state.mobileDetail=false;renderDetail();$('globalSearchQuery').focus();return}
 if(kind==='filters'){state.filtersOpen=!state.filtersOpen;renderFilters();return}
 if(!item)return;
 if(kind==='open')return navigate(item);
 if(kind==='copy'){const url=location.origin+location.pathname+'#search/'+enc(item.type)+'/'+enc(item.id)+'/'+enc(item.project_id||'-');
  try{await navigator.clipboard.writeText(url);message('Private in-app reference copied. It does not grant anyone access.')}
  catch{message('Clipboard unavailable. No public sharing link was created.')}return}
 if(kind==='summarize'){
   if(item.type!=='conversations'||state.actionBusy)return;
   if(!window.confirm('Ask the configured Vishnu AI to summarize this existing conversation? This submits a new canonical conversation turn.'))return;
   state.actionBusy=true;message('Requesting real canonical conversation summary…');
   const id=item.id,ctx=state.detail?.result||item,request={request_id:crypto.randomUUID(),conversation_id:id,transcript:'Summarize this conversation, identify decisions and next steps, and clearly state uncertainties.'};
   if(ctx.workspace_id)request.workspace_id=ctx.workspace_id;
   try{
     const reply=await window.api('/voice/turn',{method:'POST',headers:{'X-Personal-AI-Input-Modality':'text'},body:JSON.stringify(request)});
     if(!active()||state.selected?.id!==id)return;
     if(reply.status!=='completed'||!reply.reply){message('Summary is not complete; open the conversation to inspect the actual turn.');return}
     state.summary=String(reply.reply).slice(0,4500);renderDetail();message('Canonical AI summary confirmed and saved as a conversation turn.');
   }catch(e){message('No summary confirmed: '+e.message)}
   finally{state.actionBusy=false}
   return;
 }
 if(kind==='organize'){
   if(item.type!=='conversations'||state.actionBusy)return;
   try{
     const list=await window.api('/projects?status=all&sort=recent');
     const projects=list.projects||[];
     if(!projects.length){message('No eligible Projects available.');return}
     const choices=projects.slice(0,30).map((p,i)=>i+1+'. '+p.name).join('\n');
     const answer=window.prompt('Move this existing conversation to a Project (enter its number):\n'+choices);
     if(answer===null)return;
     const project=projects[Number(answer)-1];
     if(!project){message('No Project selected.');return}
     if(!window.confirm('Move the full original conversation to '+project.name+'? Its context changes; no message or attachment is copied.'))return;
     state.actionBusy=true;
     const response=await window.api('/conversations/'+enc(item.id)+'/organize',{method:'POST',body:JSON.stringify({kind:'project',target_id:project.id,confirm:true})});
     if(!response.conversation?.id){message('Organization was not confirmed.');return}
     item.project_id=project.id;state.detail=null;
     if(active())await select(item);
     message('The original conversation is now linked to the selected Project.');
   }catch(e){message('Conversation was not moved: '+e.message)}
   finally{state.actionBusy=false}
   return;
 }
 if(kind==='task'){
   if(!item.project_id){message('Choose a Project in its owning module before creating a task.');return}
   const title=window.prompt?.('Task title for this Project',('Review '+item.title).slice(0,100));
   if(!title?.trim())return;
   if(!window.confirm('Create this Project task? No AI execution will start automatically.'))return;
   try{const result=await window.api('/projects/'+enc(item.project_id)+'/tasks',{method:'POST',body:JSON.stringify({title:title.trim().slice(0,140),description:'Created from Global Search result '+item.type+': '+item.id,priority:'medium'})});
    if(result){message('Project task created and confirmed.');}}
   catch(e){message('Task not saved: '+e.message)}
 }
}
function renderFilters(){
 const root=$('gsAdvanced');if(!root)return;root.classList.toggle('expanded',state.filtersOpen);
 root.innerHTML='<label>Sort <select data-gs-filter="sort"><option value="relevance">Relevance</option><option value="recent">Most recent</option><option value="oldest">Oldest</option><option value="title">Title</option></select></label>'+
 '<label>Date <select data-gs-filter="time"><option value="all">Any time</option><option value="today">Today</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option></select></label>'+
 '<label>Workspace <select data-gs-filter="workspace" id="gsWorkspace"><option value="">All workspaces</option></select></label>'+
 '<label>Project <select data-gs-filter="project" id="gsProject"><option value="">All projects</option></select></label>'+
 '<label>Tag <input data-gs-filter="tag" maxlength="32" placeholder="Tag" aria-label="Search tag"></label>'+
 '<button type="button" data-gs-action="reset">Reset</button>';
 for(const [k,v] of Object.entries({sort:state.sort,time:state.time,workspace:state.workspace,project:state.project,tag:state.tag})){
   const el=root.querySelector('[data-gs-filter="'+k+'"]');if(el)el.value=v;
 }
 loadFilters();
}
async function loadFilters(){
 const token=++state.navPending;
 try{const [w,p]=await Promise.allSettled([window.api('/workspaces?status=active'),window.api('/projects?status=all&sort=recent')]);
  if(token!==state.navPending||!active())return;
  const fill=(id,items,selected)=>{const el=$(id);if(!el)return;for(const x of items)el.add(new Option(x.name,x.id));el.value=selected};
  if(w.status==='fulfilled')fill('gsWorkspace',w.value.workspaces||[],state.workspace);
  if(p.status==='fulfilled')fill('gsProject',p.value.projects||[],state.project);
 }catch{}
}
function mount(focus=false){
 const root=$('moduleBody');if(!root)return;
 root.innerHTML='<div class="global-search-page"><header class="gs-heading"><span class="gs-heading-icon">⌕</span><div><h1>Global Search</h1><p>Find conversations, files, projects, workspaces, work items, agents, memory and more.</p></div></header>'+
 '<form id="gsForm" class="gs-search-form"><label class="gs-input-wrap"><span>⌕</span><input id="globalSearchQuery" type="search" aria-label="Search all Vishnu resources" placeholder="Search anything across Vishnu…" autocomplete="off" value="'+esc(state.query)+'"></label>'+
 '<button type="button" data-gs-action="clear" aria-label="Clear search">×</button><button class="gs-search-submit" type="submit" aria-label="Run search">⌕</button></form>'+
 '<div id="gsScopes" class="gs-scopes" role="group" aria-label="Search categories"></div>'+
 '<div class="gs-mobile-filters"><button type="button" data-gs-action="filters">☷ Filters</button></div><div id="gsAdvanced" class="gs-advanced"></div>'+
 '<div id="gsCoverage" class="gs-coverage" role="status"></div><div class="gs-main"><div class="gs-result-panel" id="globalSearchResults"></div><section class="gs-detail" id="gsDetail" aria-label="Selected result"></section><aside class="gs-meta" id="gsMeta" aria-label="Result metadata"></aside></div>'+
 '<div id="gsRecent" class="gs-recent"></div><div id="gsNotice" class="gs-notice" role="status" aria-live="polite"></div></div>';
 root.querySelector('#gsForm').onsubmit=e=>{e.preventDefault();clearTimeout(state.timer);search({remember:true})};
 const surface=root.querySelector('.global-search-page');
 surface.addEventListener('click',e=>{
  if(!active())return;
  const actionBtn=e.target.closest('[data-gs-action]'),category=e.target.closest('[data-gs-category]'),selected=e.target.closest('[data-gs-select]'),recent=e.target.closest('[data-gs-recent]'),related=e.target.closest('[data-gs-related]');
  if(actionBtn){action(actionBtn.dataset.gsAction).catch(err=>message(err.message));return}
  if(category){state.category=category.dataset.gsCategory;updateFacets();search();return}
  if(selected){const type=selected.dataset.gsSelect,id=selected.dataset.gsId,project_id=selected.dataset.gsProject;const item=state.results.find(x=>x.type===type&&x.id===id&&x.project_id===project_id);if(item)select(item);return}
  if(recent){state.query=state.recent[Number(recent.dataset.gsRecent)];$('globalSearchQuery').value=state.query;search({remember:true});return}
  if(related){const item=state.detail?.related?.[Number(related.dataset.gsRelated)];if(item)select({...item,project_id:item.project_id||''});return}
 });
 root.querySelector('#globalSearchQuery').oninput=e=>{state.query=e.target.value;clearTimeout(state.timer);state.timer=setTimeout(()=>search(),290)};
 root.querySelector('#globalSearchQuery').onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();action('clear')}};
 surface.addEventListener('change',e=>{const key=e.target.dataset.gsFilter;if(!key)return;state[key]=e.target.value;search()});
 renderFilters();updateFacets();updateCoverage();renderResults();renderDetail();renderMeta();renderRecent();
 if(focus)root.querySelector('#globalSearchQuery').focus();
}
const original=window.openModule;
if(typeof original!=='function')return;
let navigationEpoch=0;
window.openModule=function(name){
 const current=++navigationEpoch;
 if(name!=='search'){state.live=false;++state.pending;++state.detailPending;clearTimeout(state.timer);document.body.classList.remove('global-search-mode');return original.call(this,name)}
 return Promise.resolve(original.call(this,name)).then(()=>{
  if(current!==navigationEpoch)return;
  state.live=true;document.body.classList.add('global-search-mode');
  const title=$('moduleTitle'),subtitle=$('moduleText'),metric=$('moduleMetric');
  if(title)title.textContent='Global Search';
  if(subtitle)subtitle.textContent='Search authorized Vishnu resources';
  if(metric)metric.textContent='';
  mount(true);if(state.query.trim())search();
 });
};
document.addEventListener('click',e=>{const t=e.target.closest('[data-reference-search]');if(!t)return;e.preventDefault();e.stopImmediatePropagation();window.openModule('search')},true);
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){if(e.target.closest('[contenteditable="true"]'))return;e.preventDefault();window.openModule('search')}});
function followSearchReference(){
 const parts=location.hash.slice(1).split('/');
 if(parts[0]!=='search'||parts.length<3)return;
 const kind=decodeURIComponent(parts[1]||''),id=decodeURIComponent(parts[2]||'');
 if(!types.some(([v])=>v===kind&&v!=='all')||!id||id.length>160)return;
 const project_id=parts[3]&&parts[3]!=='-'?decodeURIComponent(parts[3]):'';
 window.openModule('search').then(()=>select({type:kind,id,project_id,title:'Loading authorized resource…'})).catch(e=>message('Unable to open reference: '+e.message));
}
window.addEventListener('hashchange',followSearchReference);
window.addEventListener('load',followSearchReference);
window.addEventListener('vishnu:new-chat',()=>{state.live=false;document.body.classList.remove('global-search-mode')});
})();
