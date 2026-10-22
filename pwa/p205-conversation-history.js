/* Vishnu P2-05 Conversation History: canonical ContinuityService client; no parallel chat store. */
(()=>{
'use strict';
if(window.vishnuP205)return;
const el=id=>document.getElementById(id), b=()=>window.vishnuHistoryBridge,esc=x=>String(x??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])),sid=x=>encodeURIComponent(String(x)),fmt=s=>{try{return new Date(s).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})}catch{return ''}};
const types={personal:{label:'Personal',icon:'☏'},work:{label:'Work',icon:'▣'},project:{label:'Project',icon:'⬡'},workspace:{label:'Workspace',icon:'❖'}};
const nav=[['Home','home','⌂'],['Chat','chat','◯'],['Today','today','▣'],['Workspaces','labs','▦'],['Projects','projects','⬡'],['Agents','agents','♧'],['Create','products','✧'],['Library','knowledge','▤'],['Tools','tools','⌘'],['Devices','devices','▥'],['More','dashboard','⋯'],['Search','search','⌕'],['Notifications','attention','♧'],['Settings','settings','⚙']];
const S={open:false,filter:'all',query:'',date:'all',kind:'all',project:'',workspace:'',tag:'',rows:[],cursor:null,selected:null,thread:null,events:[],related:null,tab:'chat',mobileDetail:false,loading:false,busy:false,requestEpoch:0,detailEpoch:0,sourceEpoch:0,filterTimer:null,draft:'',pending:null,summary:'',menu:null,projects:[],workspaces:[],error:'',lastFocus:null,scroll:0};
function ctx(row){const c=row?.context||{},kind=c.conversation_kind||'personal';return types[kind]?kind:'personal'}
function active(){return S.open&&el('p205Root')&&!el('p205Root').classList.contains('hidden')}
function alert(text){if(el('p205Notice'))el('p205Notice').textContent=text||''}
function uiButton(act,txt,css='',props=''){return '<button type="button" data-h-action="'+act+'" class="'+css+'" '+props+'>'+txt+'</button>'}
function confirmAction(text){return b().confirm?.(text)??Promise.resolve(confirm(text))}
function showModal(title,subtitle,options){
 const d=el('p205Dialog');el('p205ModalTitle').textContent=title;el('p205ModalText').textContent=subtitle;const host=el('p205Choices');host.replaceChildren();
 for(const option of [...options,['Cancel',()=>{}]]){const btn=document.createElement('button');btn.type='button';btn.textContent=option[0];btn.onclick=()=>{d.close();Promise.resolve(option[1]()).catch(e=>alert(e.message))};host.append(btn)}
 d.showModal();
}
function setBusy(loading){S.loading=loading;el('p205Root')?.classList.toggle('loading',loading)}
function section(time){const d=new Date(time);if(Number.isNaN(+d))return 'Older';const today=new Date();const nowDate=new Date(today.getFullYear(),today.getMonth(),today.getDate());const dayDate=new Date(d.getFullYear(),d.getMonth(),d.getDate());const diff=Math.round((nowDate-dayDate)/86400000);return diff===0?'Today':diff===1?'Yesterday':diff>=0&&diff<7?'This Week':'Older'}
function badges(row){const c=row.context||{},labels=[ctx(row)==='personal'?'Personal':types[ctx(row)].label];
 const linked=ctx(row)==='project'?S.projects.find(p=>p.id===c.project_id):ctx(row)==='workspace'?S.workspaces.find(w=>w.id===c.workspace_id):null;
 if(linked)labels.push(linked.name);
 labels.push(...(Array.isArray(c.history_tags)?c.history_tags:[]).slice(0,3));
 return labels.map((t,i)=>'<span class="p205-chip '+(i===0?ctx(row):'')+'">'+esc(t)+'</span>').join('');
}
function listRow(row){
 const cat=ctx(row),selected=S.selected===row.id,c=row.context||{},pin=Boolean(c.history_pinned);
 return '<div class="p205-row '+(selected?'active ':'')+cat+'" data-h-row="'+esc(row.id)+'" role="listitem">'+
 '<button type="button" data-h-select="'+esc(row.id)+'" class="p205-row-open" aria-label="Open '+esc(row.title)+'">'+
 '<span class="p205-row-icon">'+types[cat].icon+'</span><span class="p205-row-copy"><strong>'+esc(row.title||'New conversation')+'</strong>'+
 '<small>'+esc((row.preview||'No messages yet').slice(0,105))+'</small><span class="p205-row-tags">'+badges(row)+'</span></span></button>'+
 '<span class="p205-row-time">'+fmt(row.updated_at)+'</span>'+
 '<button type="button" data-h-action="pin:'+esc(row.id)+'" aria-label="'+(pin?'Unpin':'Pin')+' conversation" class="p205-pin">'+(pin?'◆':'♧')+'</button>'+
 '<button type="button" data-h-action="menu:'+esc(row.id)+'" aria-label="Conversation actions" class="p205-dots">⋮</button></div>';
}
function drawList(){
 if(!active())return;
 const host=el('p205List'),prevScroll=host.scrollTop;host.replaceChildren();
 const groups=new Map();for(const row of S.rows){const title=section(row.updated_at);if(!groups.has(title))groups.set(title,[]);groups.get(title).push(row)}
 if(!S.rows.length){host.innerHTML='<div class="p205-empty"><strong>No matching conversations</strong><p>Try another filter or start a new conversation.</p>'+uiButton('new','New Chat','p205-primary')+'</div>'}
 else for(const [name,rows] of groups){const heading=document.createElement('h3');heading.className='p205-group-title';heading.textContent=name;host.append(heading);
 const group=document.createElement('section');group.setAttribute('aria-label',name);group.setAttribute('role','list');group.innerHTML=rows.map(listRow).join('');host.append(group)}
 if(S.cursor){const more=document.createElement('div');more.innerHTML=uiButton('load-more','Load more conversations','p205-more-load');host.append(more)}
 host.scrollTop=S.scroll||prevScroll;
 el('p205Count').textContent=String(S.rows.length)+(S.cursor?'+':'')+' conversations';
}
function filtersQuery(cursor=null){
 const p=new URLSearchParams({q:S.query,limit:'40',kind:S.filter==='personal'?'personal':S.filter==='work'?'work':S.filter==='project'?'project':S.filter==='workspace'?'workspace':S.kind,status:S.filter==='archived'?'archived':'active',pinned:String(S.filter==='pinned'),tag:S.tag,project_id:S.project,workspace_id:S.workspace});
 const now=new Date();const day=n=>{const d=new Date(now.getFullYear(),now.getMonth(),now.getDate()-n);return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-')};
 if(S.date==='today'){p.set('since',day(0));p.set('until',day(0))}
 else if(S.date==='yesterday'){p.set('since',day(1));p.set('until',day(1))}
 else if(S.date==='7'){p.set('since',day(6))}
 else if(S.date==='30'){p.set('since',day(29))}
 if(cursor){p.set('cursor_time',cursor.updated_at);p.set('cursor_id',cursor.id)}
 return p.toString();
}
async function list(append=false){
 if(!active())return;
 const token=++S.requestEpoch,cursor=append?S.cursor:null;
 if(!append){S.scroll=0;setBusy(true);el('p205List').innerHTML='<div class="p205-loading">Loading conversations…</div>'}
 try{
  const result=await b().api('/conversations/history/search?'+filtersQuery(cursor));
  if(token!==S.requestEpoch||!active())return;
  S.rows=append?S.rows.concat(result.conversations||[]):(result.conversations||[]);
  S.cursor=result.next_cursor||null;S.error='';
  if(S.selected&&!S.rows.some(r=>r.id===S.selected)&&!append){S.selected=null;S.thread=null;S.events=[];S.related=null}
  drawList();renderDetail();
 }catch(e){if(token!==S.requestEpoch)return;S.error=e.message;el('p205List').innerHTML='<div class="p205-empty">Could not load conversations. '+esc(e.message)+uiButton('retry','Retry')+'</div>';alert(e.message)}
 finally{if(token===S.requestEpoch)setBusy(false)}
}
async function loadSources(){
 const results=await Promise.allSettled([b().api('/projects?status=active'),b().api('/workspaces?status=active')]);
 if(!active())return;
 S.projects=results[0].status==='fulfilled'?results[0].value.projects||[]:[];
 S.workspaces=results[1].status==='fulfilled'?results[1].value.workspaces||[]:[];
 const select=(id,items,label)=>{const n=el(id);n.replaceChildren();n.add(new Option(label,''));for(const item of items)n.add(new Option(item.name,item.id))};
 select('p205Project',S.projects,'Project');select('p205Workspace',S.workspaces,'Workspace');
}
async function select(id){
 const row=S.rows.find(r=>r.id===id);if(!row)return;
 S.selected=id;S.mobileDetail=true;S.tab='chat';S.thread=row;S.related=null;S.events=[];S.summary=String(row.context?.history_summary||'');
 const token=++S.detailEpoch;drawList();renderDetail();
 try{const result=await b().api('/conversations/'+sid(id)+'/history-detail?limit=200');
 if(token!==S.detailEpoch||!active())return;
 S.thread=result.conversation;S.events=result.events||[];S.summary=String(S.thread.context?.history_summary||'');renderDetail();
 }catch(e){if(token!==S.detailEpoch)return;alert('Unable to open conversation: '+e.message)}
 try{const result=await b().api('/conversations/'+sid(id)+'/related');if(token===S.detailEpoch&&active()){S.related=result;renderDetail()}}catch{}
}
function headerOfDetail(){
 const row=S.thread||S.rows.find(x=>x.id===S.selected);if(!row)return '';
 const cat=ctx(row),pin=Boolean(row.context?.history_pinned);
 return '<div class="p205-detail-header">'+uiButton('back','‹','p205-back','aria-label="Back to history"')+
 '<span class="p205-detail-icon '+cat+'">'+types[cat].icon+'</span><div class="p205-detail-heading"><h2>'+esc(row.title)+'</h2><small>'+types[cat].label+' · '+fmt(row.updated_at)+'</small></div>'+
 uiButton('pin:'+esc(row.id),pin?'◆':'♧','','aria-label="'+(pin?'Unpin':'Pin')+' conversation"')+
 uiButton('menu:'+esc(row.id),'⋯','','aria-label="Manage conversation"')+'</div>';
}
function tabNav(){
 const titles=[['chat','Chat'],['summary','Summary'],['files','Files'],['related','Related'],['tasks','Tasks'],['details','Details']];
 return '<div class="p205-detail-tabs" role="tablist" aria-label="Conversation details">'+titles.map(([x,n])=>'<button type="button" role="tab" aria-selected="'+(S.tab===x)+'" data-h-tab="'+x+'" class="'+(S.tab===x?'selected':'')+'">'+n+'</button>').join('')+'</div>';
}
function messageCard(ev){
 const role=ev.kind==='user_message'?'mine':'vishnu',text=String(ev.payload?.text||'');
 if(!['user_message','assistant_message'].includes(ev.kind))return '';
 return '<article class="p205-msg '+role+'"><span class="p205-avatar">'+(role==='mine'?'●':'✺')+'</span><div><div class="p205-msg-by">'+(role==='mine'?'You':'Vishnu')+' <small>'+fmt(ev.created_at)+'</small></div><p>'+esc(text)+'</p></div></article>';
}
function content(){
 const thread=S.thread;
 if(!thread)return '<div class="p205-empty">Select a conversation to preview it.</div>';
 const c=thread.context||{};
 if(S.tab==='chat'){
  const messages=S.events.filter(e=>['user_message','assistant_message'].includes(e.kind));
  return '<div class="p205-messages">'+(messages.length?messages.map(messageCard).join(''):'<div class="p205-empty">This conversation has no saved messages.</div>')+'</div>';
 }
 if(S.tab==='summary'){
  return '<div class="p205-info-card"><h3>Conversation Summary</h3>'+(S.summary?'<p class="p205-summary">'+esc(S.summary)+'</p>':'<p>No generated summary has been saved for this conversation.</p>')+
   (thread.closed_at?'':uiButton('summary',S.summary?'Regenerate Summary':'Generate Summary','p205-primary'))+'</div>';
 }
 if(S.tab==='files'){
  return '<div class="p205-info-card"><h3>Conversation Files</h3><p>Direct attachment relationships are not exposed by this conversation ledger. Files saved in Knowledge or Projects remain in their authorized source.</p>'+uiButton('navigate:knowledge','Open Library')+'</div>';
 }
 if(S.tab==='related'){
  const r=S.related,pr=r?.projects||[],ws=r?.workspaces||[];
  return '<div class="p205-info-card"><h3>Related Resources</h3>'+
   (pr.map(p=>uiButton('navigate:projects','Project · '+esc(p.name),'p205-resource')).join('')||'')+
   (ws.map(w=>uiButton('navigate:labs','Workspace · '+esc(w.name),'p205-resource')).join('')||'')+
   ((!pr.length&&!ws.length)?'<p>No canonical Project or Workspace association is recorded.</p>':'')+
   '<small>Semantic similarity and attachment-linked resources are not indexed here.</small></div>';
 }
 if(S.tab==='tasks')return '<div class="p205-info-card"><h3>Linked Tasks</h3><p>No authoritative conversation-to-task index is available. Open Today or the linked Project for verified tasks.</p>'+uiButton('navigate:today','Open Today')+'</div>';
 return '<div class="p205-info-card"><h3>Conversation Details</h3><dl><dt>ID</dt><dd>'+esc(thread.id)+'</dd><dt>Context</dt><dd>'+esc(types[ctx(thread)].label)+'</dd><dt>Created</dt><dd>'+esc(fmt(thread.created_at))+'</dd><dt>Updated</dt><dd>'+esc(fmt(thread.updated_at))+'</dd><dt>Status</dt><dd>'+(thread.closed_at?'Archived':'Active')+'</dd><dt>Tags</dt><dd>'+esc((c.history_tags||[]).join(', ')||'None')+'</dd><dt>Message events</dt><dd>'+Number(thread.event_count||S.events.length)+'</dd></dl>'+uiButton('organize','Organize')+uiButton('tags','Edit Tags')+'</div>';
}
function renderDetail(){
 if(!active())return;const host=el('p205Detail');
 host.classList.toggle('mobile-open',S.mobileDetail&&Boolean(S.selected));el('p205Root').classList.toggle('detail-open',S.mobileDetail&&Boolean(S.selected));
 if(!S.selected){host.innerHTML='<div class="p205-detail-blank"><span>✺</span><h2>Choose a conversation</h2><p>View and continue saved conversations without creating copies.</p></div>';return}
 const thread=S.thread||S.rows.find(x=>x.id===S.selected);
 host.innerHTML=headerOfDetail()+tabNav()+'<section class="p205-detail-content" role="tabpanel" aria-label="'+esc(S.tab)+'">'+content()+'</section>'+
 '<form id="p205Form" class="p205-composer"><button type="button" data-h-action="attach" aria-label="Attach">＋</button><textarea id="p205Message" rows="1" placeholder="'+(thread?.closed_at?'Restore to continue…':'Message Vishnu…')+'" aria-label="Continue conversation" '+(thread?.closed_at?'disabled':'')+' maxlength="8000"></textarea>'+
 '<button type="button" data-h-action="voice" aria-label="Continue by voice" '+(thread?.closed_at?'disabled':'')+'>♩</button><button type="submit" aria-label="Send message" '+(thread?.closed_at?'disabled':'')+'>➤</button></form>'+
 '<div class="p205-quick">'+[['summary','Summarize'],['task','Create Task'],['organize','Add to Project'],['related','Find Related'],['menu:'+esc(S.selected),'More']].map(([key,name])=>uiButton(key,name)).join('')+'</div>';
 const field=el('p205Message');field.value=S.draft;
 el('p205Form').onsubmit=e=>{e.preventDefault();send()};
 field.oninput=()=>{S.draft=field.value};
 field.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send()}};
}
async function send(text=S.draft,mode='text'){
 if(S.busy||!S.selected)return;
 const row=S.thread;if(!row||row.closed_at){alert('Restore archived conversations before sending.');return}
 const clean=String(text||'').trim();if(!clean)return;
 S.busy=true;const nonce=S.selected;
 const request=S.pending?.text===clean&&S.pending?.conversation===nonce?S.pending.id:crypto.randomUUID();
 S.pending={id:request,text:clean,conversation:nonce};
 el('p205Form')?.classList.add('sending');alert('Vishnu is responding…');
 try{
  const data={request_id:request,conversation_id:nonce,transcript:clean};
  if(ctx(row)==='workspace')data.workspace_id=row.context.workspace_id;
  const reply=await b().api('/voice/turn',{method:'POST',headers:{'X-Personal-AI-Input-Modality':mode},body:JSON.stringify(data)});
  if(!active()||S.selected!==nonce)return;
  if(reply.status==='approval_required'){alert('Action requires approval; open the trusted Approval Center.')}
  else{S.pending=null;S.draft='';alert('Response saved.');}
  await select(nonce);await list();
 }catch(e){alert('Send was not confirmed: '+e.message+'. Draft and request ID retained for safe retry.')}
 finally{S.busy=false;el('p205Form')?.classList.remove('sending')}
}
async function summary(){
 if(S.busy||!S.selected)return;
 const conversation=S.selected;
 const prompt='Summarize this conversation based on its actual earlier messages. Include decisions, next steps and unknowns. If there are not enough messages, say so.';
 await send(prompt,'text');
 if(!active()||S.selected!==conversation||S.pending)return;
 const ev=[...S.events].reverse().find(x=>x.kind==='assistant_message');
 if(!ev?.payload?.text){alert('A verified summary response is unavailable.');return}
 const text=String(ev.payload.text).slice(0,6000);
 try{const result=await b().api('/conversations/'+sid(conversation)+'/metadata',{method:'PATCH',body:JSON.stringify({summary:text})});S.summary=String(result.conversation.context?.history_summary||'');S.thread=result.conversation;S.tab='summary';renderDetail()}
 catch(e){alert('Summary is in conversation history, but could not save its dedicated summary: '+e.message)}
}
async function mutate(url,method='POST',body){
 const result=await b().api('/conversations/'+sid(S.selected)+url,{method,body:body?JSON.stringify(body):undefined});
 const id=S.selected;await list();if(S.selected===id)await select(id);return result;
}
async function metadata(row,fields){
 if(S.busy)return;
 S.busy=true;
 try{await b().api('/conversations/'+sid(row.id)+'/metadata',{method:'PATCH',body:JSON.stringify(fields)});
  await list();if(S.selected===row.id)await select(row.id);alert('Conversation saved.')}
 catch(e){alert('Changes not saved: '+e.message)}
 finally{S.busy=false}
}
async function pin(id){const row=S.rows.find(x=>x.id===id)||S.thread;if(!row)return;await metadata(row,{pinned:!Boolean(row.context?.history_pinned)})}
async function rename(){
 if(!S.selected)return;const row=S.thread;const next=prompt('Rename conversation',row.title||'');
 if(next===null)return;await metadata(row,{title:next.trim()});
}
async function editTags(){
 if(!S.selected)return;const row=S.thread;const next=prompt('Comma-separated tags (up to 12)',(row.context?.history_tags||[]).join(', '));
 if(next===null)return;const tags=next.split(',').map(x=>x.trim()).filter(Boolean);await metadata(row,{tags});
}
async function archive(){
 if(!S.selected)return;const row=S.thread;
 if(row.closed_at){await mutate('/restore');alert('Conversation restored.');return}
 if(!await confirmAction('Archive this conversation? It remains available under Archived.'))return;
 await mutate('/archive');S.selected=null;S.thread=null;S.mobileDetail=false;await list();alert('Conversation archived.');
}
async function remove(){
 if(!S.selected)return;const id=S.selected;
 if(!await confirmAction('Permanently delete this conversation and its canonical event history? This cannot be undone.'))return;
 if(!await confirmAction('Confirm permanent deletion of '+S.thread.title+'?'))return;
 try{await b().api('/conversations/'+sid(id),{method:'DELETE'});S.selected=null;S.thread=null;S.events=[];S.mobileDetail=false;S.draft='';await list();alert('Conversation deleted.')}
 catch(e){alert('Deletion was not confirmed: '+e.message)}
}
async function exportConversation(){
 if(!S.selected)return;
 const bundle=await b().api('/conversations/'+sid(S.selected)+'/export');
 const blob=new Blob([JSON.stringify(bundle,null,2)],{type:'application/json'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='vishnu-conversation-'+S.selected+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 alert('Conversation export prepared for download.');
}
async function organize(){
 if(!S.selected)return;
 const opts=[['Keep Personal','personal',null],['Move to Work','work',null]];
 for(const p of S.projects.slice(0,40))opts.push(['Project · '+p.name,'project',p.id]);
 for(const w of S.workspaces.slice(0,40))opts.push(['Workspace · '+w.name,'workspace',w.id]);
 showModal('Organize Conversation','Preserve the original ID, messages, files and event order. Changing scope can affect which context Vishnu may use in future turns. No transcript is copied.',
 opts.map(([label,kind,target])=>[label,async()=>{if(!await confirmAction('Change this conversation context to '+label+'? Old private content remains in the thread; do not share it with unauthorized people.'))return;
 try{await mutate('/organize','POST',{kind,target_id:target,confirm:true});alert('Original conversation reorganized; no transcript duplication.')}
 catch(e){alert('Context not changed: '+e.message)}}]));
}
function menu(id){
 const row=S.rows.find(x=>x.id===id)||S.thread;if(!row)return;
 showModal(row.title,'Manage this canonical conversation.',[
 ['Open',()=>select(id)],['Rename',async()=>{await select(id);rename()}],
 [row.context?.history_pinned?'Unpin':'Pin',()=>pin(id)],
 ['Edit Tags',async()=>{await select(id);editTags()}],
 ['Organize',async()=>{await select(id);organize()}],
 [row.closed_at?'Restore':'Archive',async()=>{await select(id);archive()}],
 ['Export JSON',async()=>{await select(id);exportConversation()}],
 ['Delete permanently',async()=>{await select(id);remove()}]]);
}
function navigate(dest){
 close();if(dest==='voice'&&S.thread&&['personal','work'].includes(ctx(S.thread))){b().continueVoice?.(S.thread.id);return}
 b().navigate(dest);
}
async function newChat(){
 if(S.busy)return;
 if(S.filter==='project'||S.filter==='workspace'){
  showModal('Create scoped Chat','Select the existing Project or Workspace first.',
   (S.filter==='project'?S.projects:S.workspaces).map(p=>[p.name,async()=>{
    const path=S.filter==='project'?'/projects/'+sid(p.id)+'/conversations':'/workspaces/'+sid(p.id)+'/conversations';
    const obj=await b().api(path,{method:'POST',body:JSON.stringify({title:'New conversation',request_id:crypto.randomUUID()})});
    if(obj.conversation?.id){S.filter='all';setFilters();await list();await select(obj.conversation.id)}
   }]));
  return;
 }
 const result=await b().api('/conversations',{method:'POST',body:JSON.stringify({title:'New conversation',context_type:S.filter==='work'?'work':'personal'})});
 if(result.conversation?.id){close();b().openConversation(result.conversation.id)}
}
async function handle(action){
 if(action.startsWith('nav:'))return navigate(action.slice(4));
 if(action.startsWith('pin:'))return pin(action.slice(4));
 if(action.startsWith('menu:'))return menu(action.slice(5));
 if(action==='new')return newChat();
 if(action==='back'){S.mobileDetail=false;el('p205Root').classList.remove('detail-open');el('p205Detail').classList.remove('mobile-open');el('p205Search').focus();return}
 if(action==='load-more'){S.scroll=el('p205List').scrollTop;return list(true)}
 if(action==='retry')return list();
 if(action==='reset'){S.query='';S.date='all';S.kind='all';S.project='';S.workspace='';S.tag='';S.filter='all';setFilters();return list()}
 if(action==='summary')return summary();
 if(action==='task'){alert('Opening canonical Today task creation. Automatic conversation-task linking is not yet supported.');return b().createTask()}
 if(action==='organize')return organize();
 if(action==='tags')return editTags();
 if(action==='related'){S.tab='related';renderDetail();return}
 if(action==='rename')return rename();
 if(action==='archive')return archive();
 if(action==='delete')return remove();
 if(action==='export')return exportConversation();
 if(action==='attach'){showModal('Attach File','The existing file picker saves sources in Knowledge. It is not a conversation-local attachment; no upload starts automatically.',[['Open Library',()=>navigate('knowledge')]]);return}
 if(action==='voice'){if(!S.thread)return;if(['workspace','project'].includes(ctx(S.thread))){alert('Voice continuation of this scoped transcript is not yet supported. Open the Voice screen and choose the same Project/Workspace; this does not copy the existing transcript.');return}close();b().continueVoice(S.thread.id);return}
 if(action==='search-global')return navigate('search');
 if(action==='notifications')return navigate('attention');
 if(action==='account')return navigate('owner');
 if(action==='more')return showModal('History Actions','Choose an authorized action.',[['Archived conversations',()=>{S.filter='archived';setFilters();list()}],['History settings',()=>navigate('settings')],['Export selected',exportConversation]]);
}
function setFilters(){
 el('p205Search').value=S.query;el('p205Date').value=S.date;el('p205Type').value=S.kind;el('p205Project').value=S.project;el('p205Workspace').value=S.workspace;el('p205Tags').value=S.tag;
 document.querySelectorAll('#p205Root [data-h-filter]').forEach(item=>{const active=item.dataset.hFilter===S.filter;item.classList.toggle('selected',active);item.setAttribute('aria-selected',String(active))});
}
function build(){
 const tabs=[['all','All'],['personal','Personal'],['work','Work'],['project','Projects'],['workspace','Workspaces'],['pinned','Pinned'],['archived','Archived']];
 const topTabs=tabs.map(([id,name])=>'<button type="button" role="tab" data-h-filter="'+id+'" aria-selected="false">'+name+'</button>').join('');
 const sidebar=nav.map(([name,dest,ic])=>uiButton('nav:'+dest,'<span aria-hidden="true">'+ic+'</span>'+esc(name),'p205-side-nav '+(dest==='chat'?'':'') )).join('');
 const mb=[['Home','home','⌂'],['Chat','chat','◯'],['Today','today','▣'],['Voice','voice','♩'],['History','history','▤']];
 el('p205Root').innerHTML='<div class="p205-shell"><aside class="p205-sidebar"><div class="p205-brand">V I S H N U</div><nav aria-label="Vishnu modules">'+sidebar+'</nav><div class="p205-owner">'+esc(b().owner?.()||'Owner')+'</div></aside><div class="p205-main"><header class="p205-global-header">'+uiButton('menu-mobile','☰','p205-menu-toggle')+'<strong class="p205-mobile-logo">V I S H N U</strong>'+uiButton('search-global','⌕ Search conversations, messages, files, projects…','p205-global-search')+uiButton('notifications','♧','','aria-label="Notifications"')+uiButton('nav:chat','▢','','aria-label="Chat"')+uiButton('account','●','','aria-label="Owner Account"')+'</header><section class="p205-page"><header class="p205-heading"><span class="p205-head-icon">◯</span><div><h1>Conversation History</h1><p>Find, organize and continue your conversations with Vishnu.</p></div><div class="p205-heading-actions">'+uiButton('new','＋ New Chat','p205-primary')+uiButton('more','⋯','','aria-label="History options"')+'</div></header><nav class="p205-category-tabs" role="tablist" aria-label="Conversation categories">'+topTabs+'</nav><div class="p205-filters"><label class="p205-search-wrap"><span aria-hidden="true">⌕</span><input id="p205Search" type="search" aria-label="Search conversations" placeholder="Search conversations…"></label><select id="p205Date" aria-label="Filter by date"><option value="all">Date</option><option value="today">Today</option><option value="yesterday">Yesterday</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option></select><select id="p205Type" aria-label="Filter by type"><option value="all">Type</option><option value="personal">Personal</option><option value="work">Work</option><option value="project">Project</option><option value="workspace">Workspace</option></select><select id="p205Project" aria-label="Filter by Project"></select><select id="p205Workspace" aria-label="Filter by Workspace"></select><input id="p205Tags" maxlength="32" aria-label="Filter by tag" placeholder="Tags"><button type="button" data-h-action="reset">Reset</button></div><div class="p205-body"><section class="p205-list-panel"><header class="p205-list-title"><h2>Your Conversations</h2><small id="p205Count"></small></header><div id="p205List" class="p205-list"></div></section><section id="p205Detail" class="p205-detail-panel"></section></div><div class="p205-notice" id="p205Notice" role="status" aria-live="polite"></div></section><nav class="p205-mobile-nav" aria-label="Mobile destinations">'+mb.map(([name,dest,ic])=>uiButton('nav:'+dest,'<span>'+ic+'</span><small>'+name+'</small>',dest==='history'?'active':'')).join('')+'</nav></div></div>';
 const root=el('p205Root');
 root.addEventListener('click',e=>{const select=e.target.closest('[data-h-select]'),act=e.target.closest('[data-h-action]'),tab=e.target.closest('[data-h-tab]'),filter=e.target.closest('[data-h-filter]');
  if(select){S.draft='';S.pending=null;S.scroll=el('p205List').scrollTop;return void (selectConversation(select.dataset.hSelect))}
  if(act){if(act.dataset.hAction==='menu-mobile'){root.classList.toggle('menu-open');return}handle(act.dataset.hAction).catch(err=>alert(err.message));return}
  if(tab){S.tab=tab.dataset.hTab;renderDetail();return}
  if(filter){S.filter=filter.dataset.hFilter;S.selected=null;S.thread=null;S.mobileDetail=false;setFilters();list()}
 });
 el('p205Search').oninput=e=>{S.query=e.target.value;clearTimeout(S.filterTimer);S.filterTimer=setTimeout(()=>list(),250)};
 for(const [key,name] of [['p205Date','date'],['p205Type','kind'],['p205Project','project'],['p205Workspace','workspace']])el(key).onchange=e=>{S[name]=e.target.value;list()};
 el('p205Tags').oninput=e=>{S.tag=e.target.value;clearTimeout(S.filterTimer);S.filterTimer=setTimeout(()=>list(),300)};
 setFilters();renderDetail();
}
async function selectConversation(id){return select(id)}
async function open(){
 if(S.open)return;
 S.selected=null;S.thread=null;S.mobileDetail=false;S.events=[];S.draft='';S.pending=null;
 S.open=true;const root=el('p205Root');if(!root){S.open=false;throw Error('Conversation History is not mounted.')}
 S.lastFocus=document.activeElement;root.classList.remove('hidden');root.setAttribute('aria-hidden','false');build();
 await Promise.allSettled([loadSources(),list()]);setFilters();
}
function close(){if(!S.open)return;S.open=false;S.requestEpoch++;S.detailEpoch++;clearTimeout(S.filterTimer);el('p205Root')?.classList.add('hidden');el('p205Root')?.setAttribute('aria-hidden','true');el('p205Root')?.classList.remove('detail-open');S.lastFocus?.focus?.({preventScroll:true});b().onClose?.()}
window.vishnuP205={open,close,select:selectConversation,get state(){return {selected:S.selected,filter:S.filter,rows:S.rows.length,open:S.open}}};
})();