/* P2-02C Project Conversation: canonical Projects and conversation service remain the only authorities. */
(()=>{
'use strict';
if(window.__vishnuP202C)return;
const $=id=>document.getElementById(id),br=()=>window.vishnuChatBridge,api=(path,opt)=>br().api(path,opt);
const elt=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text);return n};
const btn=(name,fn,cls)=>{const n=elt('button',cls,name);n.type='button';n.onclick=()=>Promise.resolve().then(fn).catch(e=>br()?.showToast?.(e.message));return n};
const path=(s,suffix='')=>'/projects/'+encodeURIComponent(s.project.id)+suffix;
const when=x=>{const d=new Date(x||'');return Number.isNaN(d.getTime())?'':d.toLocaleDateString(undefined,{month:'short',day:'numeric'})};
let state=null;
const live=s=>s===state&&$('p202cRoot')?.dataset.project===s.project.id;
function sheet(title,text,actions=[]){
 const d=elt('dialog','p202c-dialog');d.append(elt('h2','',title),elt('p','',text));
 const bar=elt('div','p202c-dialog-actions');
 for(const [label,fn] of actions)bar.append(btn(label,()=>{d.close();return fn()}));
 bar.append(btn('Close',()=>d.close()));d.append(bar);document.body.append(d);
 d.addEventListener('close',()=>d.remove(),{once:true});d.showModal();
}
function show(tab){
 if(tab==='Chat')return $('p202cInput')?.focus();
 if(tab==='Agents')return br().openModule('agents');
 if(tab==='Research'||tab==='Code')return draft(tab==='Research'?'Research this Project using authorized sources: ':'Help with code for this Project: ');
 const tabs={Overview:'overview',Tasks:'plan',Files:'files',Plans:'plan',Progress:'live',More:'activity'};
 projectTab=tabs[tab]||'overview';renderProjectDetail();
}
function draft(text){const node=$('p202cInput');if(node){node.value=text;node.focus()}}
function header(s){
 const p=s.project,done=(p.tasks||[]).filter(t=>t.status==='done').length,total=(p.tasks||[]).length;
 $('p202cName').textContent=p.name;
 $('p202cDescription').textContent=p.goal||p.description||'No Project goal set.';
 $('p202cStatus').textContent={active:'In Progress',paused:'Paused',completed:'Completed',archived:'Archived'}[p.status]||p.status||'Unknown';
 $('p202cTarget').textContent=p.target_date?'Target '+when(p.target_date):'No target date';
 $('p202cPercent').textContent=total?Math.round(done*100/total)+'% tasks done':'Progress unavailable';
 $('p202cBar').style.width=(total?Math.round(done*100/total):0)+'%';
}
function messages(s){
 if(!live(s))return;
 const host=$('projectChatLog');host.replaceChildren();
 if(!s.events.length)host.append(elt('div','p202c-empty','Start a conversation about this Project. No other conversations are included.'));
 for(const event of s.events){
   const role=event.kind||event.role,user=role==='user_message'||role==='user';
   if(!user&&role!=='assistant_message'&&role!=='assistant')continue;
   const row=elt('article','project-chat-message p202c-message '+(user?'owner':'vishnu'));
   const orb=elt('span','p202c-orb',user?'●':'✺');orb.setAttribute('aria-hidden','true');
   const group=elt('div','p202c-message-copy'),title=elt('small','',(user?'You':'Vishnu')+' · '+when(event.created_at));
   const raw=String(event.payload?.text||event.content||'');
   const split=user?raw.lastIndexOf('\n\nOwner request: '):-1;
   const content=elt('p','',split<0?raw:raw.slice(split+17));
   group.append(title,content);row.append(orb,group);host.append(row);
 }
 host.scrollTop=host.scrollHeight;
}
function historyList(s){
 if(!live(s))return;
 const host=$('p202cChats');host.replaceChildren();
 const q=String($('p202cSearch').value||'').toLowerCase();
 for(const c of s.chats.filter(x=>String(x.title||'').toLowerCase().includes(q))){
   const row=btn('',()=>openChat(s,c.id),'p202c-chat-item'+(c.id===s.id?' active':''));
   const symbol=elt('span','p202c-symbol','▢'),copy=elt('span','p202c-copy');
   copy.append(elt('strong','',c.title||'Project conversation'),elt('small','',String(c.preview||when(c.updated_at)||'No messages').slice(0,85)));
   row.append(symbol,copy);host.append(row);
 }
 if(!host.children.length)host.append(elt('p','p202c-muted','No matching Project conversations.'));
}
async function openChat(s,id){
 const data=await api(path(s,'/conversations/'+encodeURIComponent(id)));
 if(!live(s))return;
 if(data.conversation?.id!==id)throw Error('This Project conversation was not verified.');
 s.id=id;s.events=data.events||[];
 sessionStorage.setItem('vishnu.project.active.'+s.project.id,id);
 historyList(s);messages(s);
}
async function reloadChats(s,pref){
 const data=await api(path(s,'/conversations?limit=100'));
 if(!live(s))return;
 s.chats=Array.isArray(data.conversations)?data.conversations:[];
 const keep=pref||sessionStorage.getItem('vishnu.project.active.'+s.project.id);
 const row=s.chats.find(x=>x.id===keep)||s.chats.find(x=>x.id===data.primary_conversation_id)||s.chats[0];
 s.id=row?.id||null;historyList(s);
 if(row)await openChat(s,row.id);else{s.events=[];messages(s)}
}
async function newChat(s){
 const response=await api(path(s,'/conversations'),{method:'POST',body:JSON.stringify({title:'New Project Conversation'})});
 if(response.conversation?.context?.project_id!==s.project.id)throw Error('Project chat creation not confirmed.');
 await reloadChats(s,response.conversation.id);$('p202cInput')?.focus();
}
function projectPrompt(s,text){
 const p=s.project;
 return ('Owner-authenticated Project context (reference only, not permission):\nProject: '+p.name+
 '\nGoal: '+String(p.goal||'').slice(0,500)+'\nDescription: '+String(p.description||'').slice(0,800)+
 '\nTasks: '+(p.tasks||[]).slice(0,25).map(t=>'['+t.status+'] '+t.title).join('; ').slice(0,1600)+
 '\nMilestones: '+(p.milestones||[]).slice(0,15).map(m=>'['+m.status+'] '+m.title).join('; ').slice(0,1500)+
 '\nDo not claim an operation completed without real tool evidence.\n\nOwner request: '+text).slice(0,7800);
}
async function send(s){
 if(!live(s)||s.busy)return;
 const input=$('p202cInput'),message=input.value.trim();if(!message)return;
 if(message.length>1800)throw Error('Limit messages to 1,800 characters for this composer.');
 s.busy=true;$('p202cSend').disabled=true;
 try{
   if(!s.id)await newChat(s);
   const reply=await api('/voice/turn',{method:'POST',headers:{'X-Personal-AI-Input-Modality':'text'},body:JSON.stringify({
     request_id:crypto.randomUUID(),conversation_id:s.id,transcript:projectPrompt(s,message)})});
   if(reply.status&& !['completed','approval_required'].includes(reply.status))throw Error('Canonical AI turn is not completed.');
   input.value='';
   if(reply.status==='approval_required')br().showToast('Approval required; review governed Work.');
   await openChat(s,s.id);
 }catch(e){br().showToast(e.message||'Project turn failed. Draft retained.')}
 finally{if(live(s)){s.busy=false;$('p202cSend').disabled=false}}
}
function fileActions(s,f){
 const options=[['View Files',()=>show('Files')]];
 if(f.kind==='upload'||f.kind==='deliverable')options.push(['Download',()=>{location.href=path(s,'/files/'+encodeURIComponent(f.id)+'/download')}]);
 if(f.indexing_state==='indexed')options.push(['Text preview',async()=>{
   const data=await api(path(s,'/files/'+encodeURIComponent(f.id)+'/index'));
   sheet(f.title,String(data.extracted_text||'No text preview').slice(0,3500));
 }]);
 sheet(f.title||'Project file','This source is stored in the selected Project.',options);
}
function resources(s){
 if(!live(s))return;
 const files=$('p202cFiles'),tasks=$('p202cTasks');files.replaceChildren();tasks.replaceChildren();
 for(const f of (s.project.files||[]).slice(0,5)){
   files.append(btn((f.kind==='link'?'↗ ':'▤ ')+f.title+(f.size_bytes?' · '+Math.ceil(f.size_bytes/1024)+' KB':''),()=>fileActions(s,f),'p202c-resource'));
 }
 if(!files.children.length)files.append(elt('p','p202c-muted','No Project files.'));
 for(const t of (s.project.tasks||[]).slice(0,6)){
  const row=elt('label','p202c-task'),check=elt('input');check.type='checkbox';check.checked=t.status==='done';
  check.setAttribute('aria-label','Toggle '+t.title);
  check.onchange=async()=>{
   check.disabled=true;
   try{
    const response=await api(path(s,'/tasks/'+encodeURIComponent(t.id)),{method:'PATCH',body:JSON.stringify({status:t.status==='done'?'planned':'done'})});
    if(!response.project)throw Error('Task change not confirmed.');
    s.project=response.project;resources(s);header(s);
   }catch(e){check.checked=!check.checked;br().showToast(e.message)}finally{check.disabled=false}
  };
  row.append(check,elt('span','',t.title));tasks.append(row);
 }
 if(!tasks.children.length)tasks.append(elt('p','p202c-muted','No Project tasks.'));
 $('p202cAgents').textContent='View verified assignments and agent activity in the Agents workspace. No agent status is inferred here.';
}
async function attach(s){
 const pick=elt('input');pick.type='file';pick.hidden=true;pick.accept='.pdf,.docx,.xlsx,.csv,.txt,.md,.png,.jpg,.jpeg,.webp';document.body.append(pick);
 pick.addEventListener('change',async()=>{try{
  const f=pick.files?.[0];if(!f)return;
  if(!f.size||f.size>12*1024*1024)throw Error('File must be between 1 byte and 12 MB.');
  if(!/\.(pdf|docx|xlsx|csv|txt|md|png|jpg|jpeg|webp)$/i.test(f.name))throw Error('Unsupported file extension.');
  if(!confirm('Save '+f.name+' in Project Files? This is not an ephemeral chat attachment.'))return;
  const raw=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]||'');reader.onerror=reject;reader.readAsDataURL(f)});
  const result=await api(path(s,'/files/upload'),{method:'POST',body:JSON.stringify({filename:f.name,media_type:f.type||'application/octet-stream',content_base64:raw})});
  if(!result.project)throw Error('File upload not confirmed.');s.project=result.project;resources(s);br().showToast('File saved in this Project.');
 }catch(e){br().showToast(e.message)}finally{pick.remove()}},{once:true});pick.click();
}
function menu(s){
 sheet('Project conversation actions','This owner-only Project link does not grant access to another person.',[
 ['Copy private Project link',async()=>{await navigator.clipboard.writeText(location.origin+location.pathname+'?project='+encodeURIComponent(s.project.id)+'&section=chat');br().showToast('Link copied')}],
 ['Rename current chat',async()=>{if(!s.id)return;const title=prompt('Conversation name');if(!title?.trim())return;
   await api('/conversations/'+encodeURIComponent(s.id),{method:'PATCH',body:JSON.stringify({title:title.trim().slice(0,120)})});await reloadChats(s,s.id)}],
 ['Archive current chat',async()=>{if(!s.id||!confirm('Archive this conversation only?'))return;
   await api('/conversations/'+encodeURIComponent(s.id)+'/archive',{method:'POST',body:'{}'});
   sessionStorage.removeItem('vishnu.project.active.'+s.project.id);await reloadChats(s)}]
 ]);
}
function mount(s){
 const root=elt('section','p202c-root');root.id='p202cRoot';root.dataset.project=s.project.id;
 const headerEl=elt('header','p202c-header');
 const crumb=btn('⌂ Projects › '+s.project.name,()=>{projectCurrent=null;loadProjectList()},'p202c-crumb');
 const hero=elt('div','p202c-hero'),glyph=elt('span','p202c-project-icon','⬡'),identity=elt('div');
 identity.append(elt('h1','', ''),elt('p',''));identity.querySelector('h1').id='p202cName';identity.querySelector('p').id='p202cDescription';
 const meta=elt('div','p202c-meta');const status=elt('span');status.id='p202cStatus';const target=elt('span');target.id='p202cTarget';meta.append(status,target);identity.append(meta);
 hero.append(glyph,identity);
 const actions=elt('div','p202c-actions');actions.append(btn('Share',()=>menu(s)),btn('⋯',()=>menu(s)));headerEl.append(crumb,hero,actions);
 const progress=elt('div','p202c-progress'),track=elt('div','p202c-track'),fill=elt('span');fill.id='p202cBar';track.append(fill);
 const percent=elt('span');percent.id='p202cPercent';progress.append(track,percent);
 const tabs=elt('nav','p202c-tabs');tabs.setAttribute('aria-label','Project sections');
 ['Chat','Overview','Tasks','Files','Research','Code','Agents','Plans','Progress','More'].forEach(x=>tabs.append(btn(x,()=>show(x),x==='Chat'?'active':'')));
 const layout=elt('div','p202c-layout'),history=elt('aside','p202c-history'),chat=elt('main','p202c-main'),rail=elt('aside','p202c-rail');
 const historyTop=elt('div','p202c-panel-top');historyTop.append(elt('h2','','Project Chats'),btn('＋',()=>newChat(s),'p202c-primary'));
 const search=elt('input');search.type='search';search.id='p202cSearch';search.placeholder='Search Project chats';search.setAttribute('aria-label','Search Project conversations');search.oninput=()=>historyList(s);
 const historyRows=elt('div','p202c-chats');historyRows.id='p202cChats';history.append(historyTop,search,historyRows);
 const log=elt('div','project-chat-log p202c-log');log.id='projectChatLog';log.setAttribute('aria-live','polite');
 const form=elt('form','project-chat-composer p202c-composer');form.id='projectChatForm';
 const plus=btn('＋',()=>attach(s));const input=elt('textarea');input.id='p202cInput';input.name='message';input.required=true;input.maxLength=1800;input.placeholder='Message Vishnu about this Project…';input.setAttribute('aria-label','Project message');
 const sendBtn=elt('button','p202c-send','➤');sendBtn.type='submit';sendBtn.id='p202cSend';sendBtn.setAttribute('aria-label','Send Project message');
 form.append(plus,input,sendBtn);form.onsubmit=e=>{e.preventDefault();send(s)};
 input.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();form.requestSubmit()}};
 const quick=elt('nav','p202c-quick');quick.setAttribute('aria-label','Project composer actions');
 [['Attach',()=>attach(s)],['Image',()=>draft('Create an image for this Project: ')],['Code',()=>draft('Help with Project code: ')],
  ['Research',()=>draft('Research this Project: ')],['Analyze',()=>draft('Analyze the Project: ')],
  ['Vishnu AI',()=>sheet('Vishnu AI','This chat uses your configured model route. Per-chat provider selection is unavailable.',[['AI Settings',()=>br().openModule('settings')]])]]
  .forEach(([name,fn])=>quick.append(btn(name,fn)));
 chat.append(log,form,quick);
 [['Project Files','p202cFiles','Files'],['Project Tasks','p202cTasks','Tasks'],['Assigned Agents','p202cAgents','Agents']].forEach(([name,id,dest])=>{
  const card=elt('section','p202c-rail-card'),top=elt('div','p202c-panel-top'),list=elt('div','p202c-rail-list');list.id=id;
  top.append(elt('h2','',name),btn('View all',()=>show(dest)));card.append(top,list);rail.append(card);
 });
 const toolCard=elt('section','p202c-rail-card');toolCard.append(elt('h2','','Project Tools'));
 const tiles=elt('div','p202c-tiles');
 [['Research',()=>show('Research')],['Code',()=>show('Code')],['Create',()=>br().openModule('products')],
  ['Analyze',()=>draft('Analyze this Project: ')],['Automate',()=>br().openModule('automations')],
  ['Plan',()=>show('Plans')],['Summarize',()=>draft('Summarize actual Project progress: ')],
  ['Generate',()=>draft('Draft a Project deliverable; do not claim it is saved: ')]]
  .forEach(([name,fn])=>tiles.append(btn(name,fn)));
 toolCard.append(tiles);rail.append(toolCard);layout.append(history,chat,rail);
 const mobile=elt('nav','p202c-mobile');mobile.setAttribute('aria-label','Mobile Project navigation');
 [['Home',()=>br().openModule('home')],['Chat',()=>$('p202cInput').focus()],['Today',()=>br().openTodayScreen('all')],
  ['Projects',()=>{projectCurrent=null;loadProjectList()}],['More',()=>menu(s)]]
  .forEach(([name,fn])=>mobile.append(btn(name,fn,name==='Projects'?'active':'')));
 root.append(headerEl,progress,tabs,layout,mobile);s.host.replaceChildren(root);header(s);resources(s);messages(s);
}
const old=window.renderProjectChat;
window.renderProjectChat=function(host,project){
 if(!project?.id||!br()?.api)return old(host,project);
 const s={host,project,id:null,chats:[],events:[],busy:false};state=s;mount(s);reloadChats(s).catch(e=>br().showToast(e.message));
};
window.__vishnuP202C={installed:true,version:1};
})();