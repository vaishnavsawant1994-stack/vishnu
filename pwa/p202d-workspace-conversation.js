/* P2-02D Workspace Conversation: screen adapter over the existing WorkspaceStore and ContinuityService. */
(()=>{
'use strict';
if(window.vishnuP202D)return;
const E=x=>encodeURIComponent(String(x));
const e=(tag,cls,text)=>{const x=document.createElement(tag);if(cls)x.className=cls;if(text!==undefined)x.textContent=String(text);return x};
const b=(label,action,cls)=>{const x=e('button',cls,label);x.type='button';x.addEventListener('click',()=>Promise.resolve().then(action).catch(fail));return x};
const fmtDate=t=>{const d=new Date(t||'');return Number.isNaN(d.getTime())?'':d.toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})};
const fail=err=>window.vishnuChatBridge?.showToast?.(err?.message||'This action is currently unavailable.');
const drafts=new Map();
let view=null;
const alive=s=>view===s&&s.host?.isConnected;
const path=(s,part='')=>'/workspaces/'+E(s.workspace.id)+part;
const api=(s,part='',opts)=>s.bridge.api(path(s,part),opts);
function confirmSheet(s,title,description,entries=[]){
 const origin=document.activeElement;
 const dialog=e('dialog','p202d-dialog'),heading=e('h2','',title),desc=e('p','',description),actions=e('div','p202d-dialog-actions');
 entries.forEach(([label,fn])=>{
  const action=b(label,()=>{dialog.close();return fn()});
  if(label.startsWith('＋ New Workspace Chat'))action.setAttribute('aria-label','Create new Workspace chat');
  actions.append(action);
 });
 actions.append(b('Close',()=>dialog.close()));
 dialog.append(heading,desc,actions);document.body.append(dialog);
 dialog.addEventListener('close',()=>{dialog.remove();origin?.focus?.()},{once:true});
 dialog.showModal();
}
function status(s,msg){const t=s.host.querySelector('[data-p202d-status]');if(t)t.textContent=msg||''}
function projectProgress(p){if(!Number.isFinite(p.task_count)||!p.task_count)return null;return Math.round(100*(p.done_count||0)/p.task_count)}
function openProject(id,section='overview'){
 if(typeof window.openProject==='function')return window.openProject(id,section);
 return window.vishnuChatBridge?.openModule?.('projects');
}
function showConversationPicker(s){
 const all=(s.chats||[]).map(item=>[item.title||'Workspace conversation',()=>select(s,item.id)]);
 all.unshift(['＋ New Workspace Chat',()=>create(s)]);
 confirmSheet(s,'Workspace Chats','Switch between real saved conversations in this Workspace.',all);
}
function navigate(s,tab){
 if(tab==='Chat')return s.host.querySelector('[data-p202d-input]')?.focus();
 if(tab==='More')return confirmSheet(s,'Workspace sections','Open a supported Workspace section.',[
   ['Workspace Overview',()=>s.actions.overview()],
   ['Workspace Studio',()=>s.actions.studio()],
   ['Settings',()=>s.actions.settings()],
   ['Search',()=>search(s)],
   ['Context',()=>contextSheet(s)],
 ]);
 if(tab==='Projects')return projectsSheet(s);
 if(tab==='Files')return s.actions.assets();
 if(tab==='Agents')return s.actions.agents();
 if(tab==='Tasks')return tasksSheet(s);
 if(tab==='Plans')return planSheet(s);
 if(tab==='Knowledge')return confirmSheet(s,'Workspace Knowledge','Standalone Workspace Knowledge linking is not yet available. You can open the canonical Knowledge module.',[['Open Knowledge',()=>s.bridge.openModule('knowledge')]]);
 if(tab==='Research'||tab==='Code'){
  const text=tab==='Research'?'Research a question about these linked Workspace Projects: ':'Help with code for an authorized Project in this Workspace: ';
  return setDraft(s,text);
 }
}
function setDraft(s,text){
 const box=s.host.querySelector('[data-p202d-input]');if(!box)return;
 box.value=text;drafts.set(s.workspace.id+'|'+(s.id||''),text);box.focus();
}
function projectRows(s){return s.summary?.projects||[]}
function projectsSheet(s){
 const rows=projectRows(s);
 confirmSheet(s,'Projects in this Workspace',rows.length+' verified linked Project(s). Removing a Workspace link will not delete its Project.',[
   ...rows.slice(0,15).map(p=>[p.name+' · '+(p.status||'Status unknown'),()=>openProject(p.id)]),
   ['Link an existing Project',()=>s.actions.linkProject()],
 ]);
}
function tasksSheet(s){
 const rows=projectRows(s);
 const tasks=rows.reduce((total,p)=>total+(p.task_count||0),0);
 confirmSheet(s,'Workspace Tasks',rows.length?String(tasks)+' task(s) recorded across linked Projects. Open the Project to edit or run its tasks.':'No Projects are linked yet.',[
   ...rows.slice(0,15).map(p=>[p.name+' · '+p.task_count+' task(s)',()=>openProject(p.id)]),
 ]);
}
function planSheet(s){
 const rows=projectRows(s);
 confirmSheet(s,'Plans and Work','Planning and execution are governed in the existing Project Work runtime. No Work is started by opening this menu.',[
   ...rows.slice(0,15).map(p=>['Open '+p.name+' Work',()=>openProject(p.id,'live')]),
 ]);
}
function contextSheet(s){
 const counts=s.summary?.counts||{};
 const lines=['Workspace: '+s.workspace.name,
 'Linked Projects: '+(counts.projects??'Unavailable'),
 'Active Project tasks: '+(counts.active_tasks??'Unavailable'),
 'Linked Project files: '+(counts.files??'Unavailable'),
 'Members: not supported in this single-owner Workspace',
 'Workspace-only Agent assignments: not yet linked',
 'Project links are references, not permission to execute tools.'];
 confirmSheet(s,'Workspace Context',lines.join('\n'),[
   ['Workspace Settings',()=>s.actions.settings()],
   ['Linked Projects',()=>projectsSheet(s)],
   ['File & asset sources',()=>s.actions.assets()],
 ]);
}
function search(s){
 const term=prompt('Search saved Workspace conversations by title or message:');
 if(term===null)return;
 if(term.length>120)return fail(new Error('Search is limited to 120 characters.'));
 return refreshChats(s,term);
}
function menu(s){
 confirmSheet(s,'Workspace conversation actions','Workspace conversations are private to the authenticated owner. Copying a link does not share access.',[
 ['Workspace Settings',()=>s.actions.settings()],
 ['Switch Workspace',()=>s.actions.library()],
 ['Rename chat',()=>rename(s)],
 ['Archive chat',()=>archive(s)],
 ['Export chat',()=>exportChat(s)],
 ]);
}
async function rename(s){
 if(!s.id)return;const title=prompt('Rename Workspace chat:');
 if(!title?.trim())return;
 await s.bridge.api('/conversations/'+E(s.id),{method:'PATCH',body:JSON.stringify({title:title.trim().slice(0,120)})});
 await refreshChats(s,'',s.id);
}
async function archive(s){
 if(!s.id||!confirm('Archive only this Workspace conversation?'))return;
 await s.bridge.api('/conversations/'+E(s.id)+'/archive',{method:'POST',body:'{}'});
 s.id=null;await refreshChats(s);
}
async function exportChat(s){
 if(!s.id)return;
 const payload=await s.bridge.api('/conversations/'+E(s.id)+'/export');
 const file=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'});
 const ref=URL.createObjectURL(file),link=e('a');
 link.href=ref;link.download='workspace-conversation.json';link.click();
 setTimeout(()=>URL.revokeObjectURL(ref),1000);
}
function renderChats(s){
 if(!alive(s))return;
 const left=s.host.querySelector('[data-p202d-chats]');left.replaceChildren();
 for(const item of s.chats){
  const row=b('',()=>select(s,item.id),'p202d-chat-item'+(s.id===item.id?' active':''));
  const icon=e('span','p202d-chat-icon','▦'),copy=e('span','p202d-chat-label');
  const title=e('strong','',item.title||'New Workspace Conversation'),preview=e('small','',String(item.preview||fmtDate(item.updated_at)||'No messages yet').slice(0,72));
  copy.append(title,preview);row.append(icon,copy);left.append(row);
 }
 if(!s.chats.length)left.append(e('p','p202d-muted','No conversations yet. Create one to start.'));
}
async function refreshChats(s,query='',selected=null){
 const r=await api(s,'/conversations?limit=100&q='+E(query));
 if(!alive(s))return;
 s.chats=Array.isArray(r.conversations)?r.conversations:[];
 let next=selected||s.id;
 if(!s.chats.some(x=>x.id===next))next=s.chats[0]?.id||null;
 s.id=next;renderChats(s);
 if(next)await select(s,next);else{s.events=[];renderMessages(s)}
}
async function select(s,id){
 const result=await api(s,'/conversations/'+E(id));
 if(!alive(s))return;
 if(result.conversation?.context?.workspace_id!==s.workspace.id)throw Error('Server did not verify this Workspace conversation.');
 s.id=id;s.events=result.events||[];
 renderChats(s);renderMessages(s);
 const box=s.host.querySelector('[data-p202d-input]');
 if(box)box.value=drafts.get(s.workspace.id+'|'+s.id)||'';
}
async function create(s){
 // The user can submit a draft while the explicit New Chat request is still
 // in flight. Share that request so both actions use one persisted thread.
 if(s.creating)return s.creating;
 s.creating=(async()=>{
  const result=await api(s,'/conversations',{method:'POST',body:JSON.stringify({title:'New Workspace Conversation',request_id:crypto.randomUUID()})});
  if(result.conversation?.context?.workspace_id!==s.workspace.id)throw Error('Conversation was not persisted in the selected Workspace.');
  s.id=result.conversation.id;await refreshChats(s,'',s.id);
  s.host.querySelector('[data-p202d-input]')?.focus();
  return s.id;
 })();
 try{return await s.creating}finally{s.creating=null}
}
function ownerText(text){
 const k=text.lastIndexOf('\nOwner request: ');
 return k<0?text:text.slice(k+16);
}
function renderMessages(s){
 if(!alive(s))return;
 const container=s.host.querySelector('[data-p202d-messages]');container.replaceChildren();
 if(!s.events.length){
  const hint=e('section','p202d-welcome'),orb=e('span','p202d-orb','✺');
  const info=e('div');info.append(e('h3','','Welcome to '+s.workspace.name),e('p','','Ask Vishnu about authorized linked Projects and Workspace work. No unrelated conversations are included.'));
  hint.append(orb,info);container.append(hint);
  if(s.summary)container.append(buildOverview(s));
 }
 for(const evt of s.events){
  const kind=evt.kind||evt.role,owner=kind==='user_message'||kind==='user';
  if(!owner&&kind!=='assistant_message'&&kind!=='assistant')continue;
  const row=e('article','p202d-message '+(owner?'mine':'assistant'));
  const avatar=e('span','p202d-orb',owner?'●':'✺');
  const body=e('div','p202d-message-body'),by=e('small','',(owner?'You':'Vishnu')+' · '+fmtDate(evt.created_at));
  const text=e('p','',owner?ownerText(String(evt.payload?.text||evt.content||'')):String(evt.payload?.text||evt.content||''));
  body.append(by,text);row.append(avatar,body);container.append(row);
 }
 container.scrollTop=container.scrollHeight;
}
function buildOverview(s){
 const box=e('section','p202d-overview'),head=e('h3','','Workspace Overview'),cols=e('div','p202d-stats');
 const counts=s.summary?.counts||{};
 [['Projects',counts.projects,()=>projectsSheet(s)],['Active Tasks',counts.active_tasks,()=>tasksSheet(s)],
  ['Members',counts.members,null],['AI Agents',counts.agents,()=>navigate(s,'Agents')]]
  .forEach(([name,count,click])=>{
   const tile=b('',click||(()=>contextSheet(s)),'p202d-stat');
   tile.append(e('span','p202d-stat-icon',({Projects:'▣','Active Tasks':'☷',Members:'♙','AI Agents':'⚙'})[name]),
     e('strong','',count===null||count===undefined?'—':count),e('small','',name));
   if(count==null)tile.title=name+' is not available from a verified Workspace-specific source.';
   cols.append(tile);
  });
 box.append(head,cols);return box;
}
function resources(s){
 if(!alive(s))return;
 const host=s.host,summary=s.summary||{},counts=summary.counts||{},projects=projectRows(s);
 const set=(selector,val)=>{const n=host.querySelector(selector);if(n)n.textContent=val};
 set('[data-p202d-header-name]',s.workspace.name);
 set('[data-p202d-header-description]',s.workspace.description||'Organize related projects and work with Vishnu.');
 set('[data-p202d-workspace-name]',s.workspace.name);
 set('[data-p202d-description]',s.workspace.description||'No description has been saved.');
 set('[data-p202d-project-count]',counts.projects??'Unavailable');
 set('[data-p202d-task-count]',counts.active_tasks??'Unavailable');
 set('[data-p202d-file-count]',counts.files??'Unavailable');
 set('[data-p202d-member-count]','Not available');
 set('[data-p202d-agent-count]','Not linked');
 const projectList=host.querySelector('[data-p202d-projects]'),activeList=host.querySelector('[data-p202d-active]');
 projectList.replaceChildren();activeList.replaceChildren();
 projects.slice(0,8).forEach(p=>{
   const label=(p.status||'Status unavailable'),percent=projectProgress(p);
   const left=b('',()=>openProject(p.id),'p202d-project-link');
   left.append(e('span','p202d-project-icon','⬡'),e('span','',p.name),e('small','',label));projectList.append(left);
   const row=b('',()=>openProject(p.id),'p202d-active-row');
   const title=e('span');title.append(e('strong','',p.name),e('small','',label+(percent!==null?' · '+percent+'% of tasks':'')));
   row.append(e('span','p202d-project-icon','⬡'),title);activeList.append(row);
 });
 if(!projects.length){projectList.append(e('p','p202d-muted','No linked Projects.'));activeList.append(e('p','p202d-muted','No linked Projects.'))}
 if(!s.events.length)renderMessages(s);
}
async function summary(s){
 try{const data=await api(s,'/summary');if(!alive(s))return;s.summary=data;resources(s)}
 catch(error){if(alive(s))status(s,'Project summary unavailable: '+error.message)}
}
async function send(s){
 if(!alive(s)||s.sending)return;
 const input=s.host.querySelector('[data-p202d-input]'),text=input.value.trim();
 if(!text)return;if(text.length>1800)throw Error('Workspace chat is limited to 1,800 characters per message.');
 s.sending=true;
 const button=s.host.querySelector('[data-p202d-send]');button.disabled=true;status(s,'Vishnu is responding…');
 try{
  if(!s.id)await create(s);
  // Creating an initial conversation must not consume its unsent prompt.
  drafts.set(s.workspace.id+'|'+s.id,text);
  input.value=text;
  const res=await s.bridge.api('/voice/turn',{method:'POST',headers:{'X-Personal-AI-Input-Modality':'text'},body:JSON.stringify({
   request_id:crypto.randomUUID(),conversation_id:s.id,workspace_id:s.workspace.id,transcript:text})});
  if(res.status!=='completed'&&res.status!=='approval_required')throw Error('AI turn has not completed.');
  drafts.delete(s.workspace.id+'|'+s.id);input.value='';
  if(res.status==='approval_required')status(s,'A consequential operation requires owner approval.');else status(s,'');
  await select(s,s.id);
  await summary(s);
 }catch(error){if(alive(s)){input.value=text;drafts.set(s.workspace.id+'|'+(s.id||''),text)}status(s,'Not sent: '+error.message)}
 finally{if(alive(s)){s.sending=false;button.disabled=false}}
}
function recordVoice(s){
 const Speech=window.SpeechRecognition||window.webkitSpeechRecognition;
 if(!Speech)return confirmSheet(s,'Voice not available','Speech recognition is not supported in this browser. Try a supported Vishnu voice surface.');
 if(!confirm('Allow microphone input for this Workspace conversation?'))return;
 const recognition=new Speech();recognition.lang=navigator.language||'en-US';recognition.interimResults=false;
 recognition.onresult=event=>{const text=event.results?.[0]?.[0]?.transcript||'';setDraft(s,text)};
 recognition.onerror=event=>status(s,'Microphone: '+(event.error||'Unavailable'));
 recognition.start();status(s,'Listening. Speech will be placed in your draft for review.');
}
function attach(s){
 const projects=projectRows(s);
 confirmSheet(s,'Workspace files','Files are managed in linked Projects. Uploading directly to a Workspace is not supported; no file will be silently added to global Knowledge.',[
 ...projects.slice(0,12).map(p=>['Open '+p.name+' files',()=>openProject(p.id)]),
 ['Linked Project Assets',()=>s.actions.assets()]
 ]);
}
function quick(s,name){
 if(name==='Attach'||name==='Image')return attach(s);
 if(name==='Code')return setDraft(s,'Review code for an authorized Project in this Workspace: ');
 if(name==='Research')return setDraft(s,'Research this Workspace question with allowed sources: ');
 if(name==='Analyze')return setDraft(s,'Analyze status, risks and attention across linked Projects: ');
 if(name==='Vishnu AI')return confirmSheet(s,'Configured AI','Vishnu uses the currently available canonical AI route. Per-Workspace model switching is not connected.',[
 ['AI Settings',()=>s.bridge.openModule('settings')]
 ]);
 if(name==='Plan')return planSheet(s);
 if(name==='Summarize')return setDraft(s,'Summarize actual linked Workspace Project progress: ');
 if(name==='Automate')return s.bridge.openModule('workflows');
 if(name==='Search')return search(s);
 if(name==='Create')return s.bridge.openModule('products');
}
function build(s){
 const host=s.host;host.replaceChildren();
 const root=e('section','p202d-root');root.dataset.workspace=s.workspace.id;
 const hero=e('header','p202d-hero'),identity=e('div','p202d-identity');
 identity.append(e('span','p202d-workspace-icon','▦'));
 const names=e('div');names.append(b(s.workspace.name+' ⌄',()=>s.actions.library(),'p202d-workspace-select'));
 const description=e('p');description.dataset.p202dHeaderDescription='';names.append(description);
 const stats=e('div','p202d-badges');[
 ['Projects','p202d-project-count'],['Active tasks','p202d-task-count']]
 .forEach(([label,attr])=>{const chip=b('',()=>label==='Projects'?projectsSheet(s):tasksSheet(s));
   const value=e('strong','');value.setAttribute('data-'+attr,'');chip.append(value,e('span','',label));stats.append(chip)});
 const absent=e('span','p202d-notice','Members and agents: not linked');stats.append(absent);
 names.append(stats);identity.append(names);
 const actions=e('div','p202d-hero-actions');
 const pick=b('Chats ▾',()=>showConversationPicker(s),'p202d-mobile-picker');
 pick.setAttribute('aria-label','Open workspace conversations');
 actions.append(b('＋ New Chat',()=>create(s),'p202d-primary'),pick,b('⋯',()=>menu(s)));
 hero.append(identity,actions);
 const topNav=e('nav','p202d-tabs');topNav.setAttribute('aria-label','Workspace sections');
 ['Chat','Projects','Files','Tasks','Agents','Plans','Research','Code','Knowledge','More'].forEach(name=>topNav.append(b(name,()=>navigate(s,name),name==='Chat'?'active':'')));
 const layout=e('div','p202d-layout'),left=e('aside','p202d-left'),main=e('main','p202d-center'),right=e('aside','p202d-right');
 const chatBox=e('section','p202d-panel p202d-chat-panel'),chatHead=e('div','p202d-panel-head');
 chatHead.append(e('h2','','Workspace Chats'),b('＋',()=>create(s),'p202d-primary'));
 const chatList=e('div','p202d-chat-list');chatList.dataset.p202dChats='';
 chatBox.append(chatHead,chatList);
 const projectsBox=e('section','p202d-panel'),projectsHead=e('div','p202d-panel-head');projectsHead.append(e('h2','','Projects in this Workspace'),b('＋',()=>s.actions.linkProject()));
 const projectsList=e('div','p202d-project-list');projectsList.dataset.p202dProjects='';
 projectsBox.append(projectsHead,projectsList,b('View all projects ›',()=>projectsSheet(s),'p202d-link'));left.append(chatBox,projectsBox);
 const stream=e('div','p202d-stream');stream.dataset.p202dMessages='';stream.setAttribute('aria-live','polite');
 const composer=e('form','p202d-composer'),plus=b('＋',()=>attach(s)),input=e('textarea');
 input.dataset.p202dInput='';input.maxLength=1800;input.placeholder='Message Vishnu about this workspace…';input.setAttribute('aria-label','Workspace message');
 input.addEventListener('input',()=>drafts.set(s.workspace.id+'|'+(s.id||''),input.value));
 input.addEventListener('keydown',evt=>{if(evt.key==='Enter'&&!evt.shiftKey&&!evt.isComposing){evt.preventDefault();composer.requestSubmit()}});
 const mic=b('♩',()=>recordVoice(s));mic.setAttribute('aria-label','Voice input');
 const sendBtn=e('button','p202d-send','➤');sendBtn.type='submit';sendBtn.dataset.p202dSend='';sendBtn.setAttribute('aria-label','Send Workspace message');
 composer.append(plus,input,mic,sendBtn);composer.onsubmit=evt=>{evt.preventDefault();send(s)};
 const quickbar=e('nav','p202d-quick');quickbar.setAttribute('aria-label','Workspace composer shortcuts');
 ['Attach','Image','Code','Research','Analyze','Vishnu AI'].forEach(name=>quickbar.append(b(name,()=>quick(s,name))));
 const sendStatus=e('p','p202d-message-status');sendStatus.dataset.p202dStatus='';sendStatus.setAttribute('role','status');
 main.append(stream,sendStatus,composer,quickbar);
 const context=e('section','p202d-panel'),contextHead=e('div','p202d-panel-head');
 contextHead.append(e('h2','','Workspace Context'),b('Edit',()=>contextSheet(s),'p202d-link'));
 const ctx=e('div','p202d-context-title');ctx.append(e('span','p202d-workspace-icon','▦'));
 const ctxName=e('strong');ctxName.dataset.p202dWorkspaceName='';ctx.append(ctxName);
 const ctxDesc=e('p');ctxDesc.dataset.p202dDescription='';
 const ctxItems=e('div','p202d-context-items');
 [['Projects','p202d-project-count'],['Active tasks','p202d-task-count'],['Files','p202d-file-count'],
  ['Members','p202d-member-count'],['AI agents','p202d-agent-count']].forEach(([label,key])=>{
   const row=e('div');row.append(e('span','',label));const value=e('strong');value.setAttribute('data-'+key,'');row.append(value);ctxItems.append(row)
 });
 context.append(contextHead,ctx,ctxDesc,ctxItems);
 const active=e('section','p202d-panel'),activeHead=e('div','p202d-panel-head');activeHead.append(e('h2','','Active Projects'),b('View all',()=>projectsSheet(s),'p202d-link'));
 const activeRows=e('div','p202d-active-projects');activeRows.dataset.p202dActive='';
 active.append(activeHead,activeRows);
 const agents=e('section','p202d-panel'),agentsHead=e('div','p202d-panel-head');agentsHead.append(e('h2','','Assigned Agents'),b('Manage',()=>s.actions.agents(),'p202d-link'));
 agents.append(agentsHead,e('p','p202d-muted','No Workspace Agent assignments verified. Open Agents for canonical workforce status.'));
 const toolPanel=e('section','p202d-panel'),toolsHead=e('div','p202d-panel-head');toolsHead.append(e('h2','','Workspace Tools'));
 const tools=e('div','p202d-tool-grid');['Research','Code','Create','Analyze','Plan','Summarize','Automate','Search'].forEach(name=>tools.append(b(name,()=>quick(s,name))));
 toolPanel.append(toolsHead,tools);right.append(context,active,agents,toolPanel);
 const mobile=e('nav','p202d-mobile-nav');mobile.setAttribute('aria-label','Workspace mobile navigation');
 [['Home',()=>s.bridge.openModule('home')],['Chat',()=>s.host.querySelector('[data-p202d-input]')?.focus()],['Today',()=>s.bridge.openTodayScreen('all')],
 ['Workspaces',()=>s.actions.library()],['More',()=>navigate(s,'More')]].forEach(([name,fn])=>mobile.append(b(name,fn,name==='Workspaces'?'active':'')));
 layout.append(left,main,right);root.append(hero,topNav,layout,mobile);host.append(root);
 // one shared selector is enough; duplicate stats data attributes are all updated below.
}
function updateNumbers(s){
 const c=s.summary?.counts||{};
 s.host.querySelectorAll('[data-p202d-project-count]').forEach(node=>node.textContent=c.projects??'—');
 s.host.querySelectorAll('[data-p202d-task-count]').forEach(node=>node.textContent=c.active_tasks??'—');
 s.host.querySelectorAll('[data-p202d-file-count]').forEach(node=>node.textContent=c.files??'—');
 s.host.querySelectorAll('[data-p202d-member-count]').forEach(node=>node.textContent='Unavailable');
 s.host.querySelectorAll('[data-p202d-agent-count]').forEach(node=>node.textContent='Not linked');
 const name=s.host.querySelector('[data-p202d-workspace-name]');if(name)name.textContent=s.workspace.name;
 const desc=s.host.querySelector('[data-p202d-description]');if(desc)desc.textContent=s.workspace.description||'No saved description.';
 const top=s.host.querySelector('[data-p202d-header-description]');if(top)top.textContent=s.workspace.description||'Workspace conversations and linked Project work.';
}
async function start(element,workspace,bridge,actions){
 const s={host:element,workspace,bridge,actions,summary:null,chats:[],events:[],id:null,sending:false};
 view=s;build(s);updateNumbers(s);
 // Failure in one panel never replaces an already-rendered conversation.
 await Promise.allSettled([summary(s),refreshChats(s)]);
 if(alive(s))updateNumbers(s);
}
window.vishnuP202D={mount:start,get currentWorkspaceId(){return view?.workspace.id||null}};
})();
