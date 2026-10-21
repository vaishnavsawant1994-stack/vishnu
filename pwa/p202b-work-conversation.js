/* P2-02B Work Conversation: opt-in presentation over canonical conversation APIs.
 * Work mode is currently a device-local view marker, NOT an authorization boundary.
 * Project task execution and resources remain server-controlled and unlinked unless
 * a canonical, owner-approved association exists. Never synthesize WorkPlan progress.
 */
(() => {
 'use strict';
 if(window.__vishnuP202B)return;
 const $=id=>document.getElementById(id);
 const bridge=()=>window.vishnuChatBridge;
 const make=(tag,cls,value)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(value!==undefined)n.textContent=String(value);return n};
 const btn=(text,cls,fn)=>{const n=make('button',cls,text);n.type='button';n.addEventListener('click',fn);return n};
 const ready=()=>Boolean(bridge()?.api)&&!$('voicePanel')?.classList.contains('hidden');
 const inChat=()=>ready()&&document.body.classList.contains('chat-experience')&&!document.body.classList.contains('home-landing');
 const projectScoped=()=>/^\s*Project\s*[·:]/i.test($('vContextChip')?.querySelector('span')?.textContent||'');
 let selected=false, lastId=null, syncing=false, refreshController=null, refreshTimer=null, status={};
 const ref={}, drafts=new Map();
 const statusNotice=txt=>{if(ref.notice)ref.notice.textContent=txt;};
 const inform=msg=>bridge()?.showToast?.(msg);
 const guarded=async job=>{try{return await job()}catch(e){inform(e?.message||'This action is not available right now.')}};
 const nav=dest=>bridge()?.openModule?.(dest);
 const toggle=enable=>{
   selected=Boolean(enable);
   try{if(selected)sessionStorage.setItem('vishnu.work.chat.view','on');else sessionStorage.removeItem('vishnu.work.chat.view')}catch{}
   if(!selected)document.body.classList.remove('p202-work-chat');
   queue();
 };
 const isActive=()=>selected&&inChat()&&!projectScoped();
 const currentId=()=>bridge()?.current?.id||null;
 const ask=draft=>{
   if(!isActive())return;
   bridge()?.setDraft?.(draft);
   $('message')?.focus();
 };
 function newWork(){
   return guarded(async()=>{
     if(bridge()?.turnInFlight)return inform('Finish or cancel the current response first.');
     const original=$('message')?.value||'';
     if(original.trim())return inform('Send or clear your unsent message before starting another conversation.');
     await bridge().createConversation();
     toggle(true);queue();
   });
 }
 function startWorkView(){
   selected=true;
   try{sessionStorage.setItem('vishnu.work.chat.view','on')}catch{}
   if(!inChat()){
     const id=currentId();
     if(id)return guarded(()=>bridge().openConversation(id));
     return newWork();
   }
   queue();
 }
 function chooseContext(){
   const dialog=make('dialog','p202b-modal');dialog.setAttribute('aria-label','Conversation context');
   dialog.append(make('h2','','Choose a conversation context'));
   dialog.append(make('p','','Work is currently an organizational view on this device. It does not create a new security or sharing boundary. Project and Workspace contexts have separate canonical controls.'));
   const actions=make('div','p202b-modal-actions');
   actions.append(btn('Personal Chat','',()=>{dialog.close();toggle(false)}));
   actions.append(btn('Project context…','',()=>{dialog.close();$('vContextChip')?.click()}));
   actions.append(btn('Keep Work view','p202b-primary',()=>dialog.close()));
   dialog.append(actions);document.body.append(dialog);
   dialog.addEventListener('close',()=>dialog.remove(),{once:true});
   dialog.showModal();
 }
 function openMenu(){
   if($('chatMenuButton')&&!$('chatMenuButton').classList.contains('hidden'))$('chatMenuButton').click();
   else $('chatDetailsTop')?.click();
 }
 function section(title,cls){
   const el=make('section','p202b-card '+(cls||''));el.append(make('h3','',title));return el;
 }
 function setLoading(el,msg){el.replaceChildren(make('p','p202b-empty',msg));}
 function renderRows(el,rows,empty,display){
   el.replaceChildren();
   if(!rows.length){el.append(make('p','p202b-empty',empty));return}
   rows.forEach((item,i)=>el.append(display(item,i)));
 }
 function itemRow(icon,title,caption,onClick){
   const row=btn('','p202b-resource',onClick);
   const glyph=make('span','p202b-resource-icon',icon);
   const label=make('span','p202b-resource-copy');
   label.append(make('strong','',title),make('small','',caption));
   row.append(glyph,label,make('span','p202b-chevron','›'));
   return row;
 }
 function mount(){
   if($('p202bShell')||!$('voicePanel'))return;
   const shell=make('div','p202b-shell');shell.id='p202bShell';shell.hidden=true;
   const tabs=make('header','p202b-tabs');
   const scope=btn('▣  Work  ▾','p202b-scope',chooseContext);scope.setAttribute('aria-label','Work conversation context');
   tabs.append(scope);
   const tabList=make('nav','p202b-tablist');tabList.setAttribute('aria-label','Work conversation sections');
   ['Chat','Files','Tasks','Research','Code','Plans','More'].forEach((name,i)=>{
     const t=btn(name,'p202b-tab'+(i?'':' active'),()=>switchTab(name));
     t.dataset.tab=name;t.setAttribute('aria-pressed',String(!i));tabList.append(t);
   });
   tabs.append(tabList);
   tabs.append(btn('＋ New Chat','p202b-new',newWork));
   tabs.append(btn('•••','p202b-more',openMenu));
   shell.append(tabs);
   const layout=make('div','p202b-layout');
   const history=section('Work Conversations','p202b-history');
   history.querySelector('h3').textContent='Chats';
   const historyActions=make('div','p202b-history-actions');
   historyActions.append(btn('＋ New Chat','p202b-primary',newWork));
   historyActions.append(btn('⌕ History','',()=>{$('historyButton')?.click();document.getElementById('appConversations')?.click()}));
   history.append(historyActions);
   ref.history=make('div','p202b-history-list');
   ref.history.setAttribute('aria-label','Saved conversations; Work context is not server-classified');
   history.append(make('p','p202b-note','All saved conversations. Vishnu does not yet distinguish standalone Work chats in canonical history.'),ref.history);
   layout.append(history);
   const main=make('div','p202b-main');
   ref.surface=make('div','p202b-surface');
   const summary=make('div','p202b-current');
   ref.title=make('strong','','Work Conversation');
   summary.append(make('span','p202b-core','◉'),ref.title);
   summary.append(make('span','p202b-context-label','Work view · owner-only conversation'));
   ref.surface.append(summary);
   ref.notice=make('p','p202b-notice','Messages are stored through Vishnu’s existing conversation engine.');
   ref.surface.append(ref.notice);
   ref.search=make('div','p202b-search hidden');
   const query=make('input');query.type='search';query.placeholder='Search messages in this conversation…';query.setAttribute('aria-label','Search this conversation');
   const results=make('div','p202b-search-results');
   query.addEventListener('input',()=>renderSearch(query.value,results));
   ref.search.append(query,results);
   main.append(ref.surface,ref.search);
   const actions=make('div','p202b-search-actions');
   actions.append(btn('⌕ Search conversation','',()=>{ref.search.classList.toggle('hidden');if(!ref.search.classList.contains('hidden'))query.focus()}));
   actions.append(btn('◈ System status','',()=>nav('system')));
   main.append(actions);
   layout.append(main);
   const context=make('aside','p202b-context');
   context.setAttribute('aria-label','Work conversation details and resources');
   const about=section('Conversation Context');
   ref.context=make('div','p202b-context-body');
   about.append(ref.context);context.append(about);
   const files=section('Files & Resources');files.querySelector('h3').append(btn('＋ Add','p202b-small-link',()=>openFiles()));
   ref.files=make('div');setLoading(ref.files,'No files are linked to this conversation.');files.append(ref.files);context.append(files);
   const tasks=section('Tasks');
   tasks.querySelector('h3').append(btn('＋ Add','p202b-small-link',()=>addTask()));
   ref.tasks=make('div');setLoading(ref.tasks,'No conversation-linked tasks.');tasks.append(ref.tasks);context.append(tasks);
   const plans=section('Active Work');
   plans.querySelector('h3').append(btn('View all ›','p202b-small-link',()=>nav('workflows')));
   ref.work=make('div');setLoading(ref.work,'Loading current Work state…');plans.append(ref.work);context.append(plans);
   const quick=section('Quick Actions');
   const grid=make('div','p202b-quick');
   [
     ['Summarize','▤','Summarize the current work conversation and identify decisions and next steps.'],
     ['Analyze','▥','Analyze the current work discussion, listing assumptions, risks, and opportunities.'],
     ['Create Image','▧','Create an image for '],['Write','✎','Help me draft a professional '],
     ['Improve','⌁','Improve the previous draft while preserving its intended meaning.'],
     ['Translate','◇','Translate the following into ']
   ].forEach(([label,icon,draft])=>{
     const b=btn('','p202b-quick-button',()=>ask(draft));b.append(make('span','',icon),make('small','',label));grid.append(b);
   });
   quick.append(grid);context.append(quick);
   layout.append(context);shell.append(layout);
   const composerTools=make('div','p202b-composer-tools');
   composerTools.id='p202bComposerTools';
   [
     ['Attach',()=>openFiles()],['Image',()=>ask('Create an image of ')],
     ['Code',()=>ask('Help me create or review code for ')],
     ['Research',()=>ask('Research this work question using permitted sources: ')],
     ['Analyze',()=>ask('Analyze ')],
     ['Vishnu AI',()=>modelDialog()]
   ].forEach(([name,action])=>composerTools.append(btn(name,'',action)));
   shell.append(composerTools);
   const existing=$('voicePanel');
   // The original message stream and composer remain in their canonical DOM;
   // this shell is layout/navigation only and must not duplicate either.
   document.body.append(shell);
   const entry=btn('▣ Work Chat','p202b-entry',()=>{
     if(inChat())toggle(true);else startWorkView();
   });
   entry.id='p202bEntry';entry.setAttribute('aria-label','Open Work Conversation');
   const navHost=document.querySelector('.reference-desktop-sidebar nav');
   const chat=navHost?.querySelector('.p2-sidebar-added');
   (chat||navHost?.querySelector('[data-app-module="home"]'))?.after(entry);
   const shortcut=btn('Work Chat','p202b-drawer-entry',()=>{document.getElementById('closeAppDrawer')?.click();startWorkView()});
   shortcut.id='p202bDrawerEntry';
   const navDrawer=$('appDrawer')?.querySelector('.sidebar-main-nav');
   navDrawer?.append(shortcut);
   document.querySelector('.reference-desktop-tools [data-reference-search]')?.addEventListener('click',e=>{
     if(!isActive())return;e.stopImmediatePropagation();e.preventDefault();ref.search.classList.remove('hidden');query.focus();
   },true);
   refsAttach();
   refreshHistory();
 }
 function refsAttach(){
   $('message')?.addEventListener('input',()=>{
     if(isActive())drafts.set(currentId()||'new',$('message').value);
   });
   $('messageStream')?.addEventListener('click',e=>{
     const button=e.target.closest?.('[data-p202b-draft]');
     if(button&&isActive())ask(button.dataset.p202bDraft);
   });
   const observer=new MutationObserver(queue);
   observer.observe(document.body,{attributes:true,attributeFilter:['class']});
   if($('vContextChip'))observer.observe($('vContextChip'),{subtree:true,childList:true});
   if($('messageStream'))observer.observe($('messageStream'),{childList:true});
   window.addEventListener('vishnu:new-chat',()=>{selected&&queue();refreshHistory()});
   document.addEventListener('visibilitychange',()=>{if(!document.hidden&&isActive()){reload();refreshHistory()}});
   window.addEventListener('focus',()=>isActive()&&reload());
 }
 function modelDialog(){
   const state=status.model?.state||'unavailable';
   alertDialog('Vishnu AI',state==='ready'||state==='available'
     ?'This conversation uses your existing configured model route; per-chat model overrides are not enabled.'
     :'AI status: '+state+'. Configure an authorized model in Settings.',[
     ['AI Settings',()=>nav('settings')]
   ]);
 }
 function alertDialog(title,detail,extra=[]){
   const modal=make('dialog','p202b-modal');modal.append(make('h2','',title),make('p','',detail));
   const actions=make('div','p202b-modal-actions');
   extra.forEach(([label,cb])=>actions.append(btn(label,'',()=>{modal.close();cb()})));
   actions.append(btn('Close','p202b-primary',()=>modal.close()));modal.append(actions);
   document.body.append(modal);modal.addEventListener('close',()=>modal.remove(),{once:true});modal.showModal();
 }
 function openFiles(){
   alertDialog('Files & Resources','This Work chat currently has no canonical conversation-attachment association. Adding a file to Knowledge is a separate, persistent action and requires explicit owner choice.',[
     ['Open Library',()=>nav('knowledge')],['Add to Knowledge',()=>$('attachmentInput')?.click()]
   ]);
 }
 function addTask(){
   if(typeof bridge()?.openTodayExistingCreate==='function')bridge().openTodayExistingCreate('task');
   else bridge()?.openTodayScreen?.('all');
 }
 function switchTab(name){
   ref.activeTab=name;
   document.querySelectorAll('.p202b-tab').forEach(t=>{
     const on=t.dataset.tab===name;
     t.classList.toggle('active',on);t.setAttribute('aria-pressed',String(on));
   });
   if(name==='Chat'){ref.search.classList.add('hidden');return}
   if(name==='More')return openMenu();
   const map={
     Files:['Files & Resources','No file is linked to this conversation. Knowledge sources live separately until explicitly attached.'],
     Tasks:['Tasks','Standalone conversation tasks are not yet linked. You can open the existing Today task creator.'],
     Research:['Research','Research citations are shown in actual Vishnu responses. A separate conversation research ledger is not configured.'],
     Code:['Code','Code output is available in the canonical chat transcript. Repository edits require governed tools.'],
     Plans:['Plans','WorkPlans require an authorized Project/Work association. The global Work list is available without linking unrelated work.']
   };
   const [title,msg]=map[name]||[name,'Not configured'];
   alertDialog(title,msg,name==='Files'?[['Open Library',()=>nav('knowledge')]]:name==='Tasks'?[['Add Task',addTask]]:name==='Plans'?[['View Work',()=>nav('workflows')]]:[]);
 }
 async function refreshHistory(){
   if(!isActive())return;
   try{
     const data=await bridge().api('/conversations?limit=50');
     if(!isActive())return;
     const rows=Array.isArray(data?.conversations)?data.conversations:[];
     renderRows(ref.history,rows,'No saved conversations yet. Start a Work Conversation.',row=>{
       const t=row.updated_at||row.created_at;
       const date=t?new Date(t):null;
       const stamp=date&&!Number.isNaN(date.getTime())?new Intl.DateTimeFormat(navigator.language,{month:'short',day:'numeric'}).format(date):'';
       const el=itemRow('◉',row.title||'Conversation',stamp,()=>guarded(async()=>{
         const old=currentId();
         if(old)drafts.set(old,$('message')?.value||'');
         await bridge().openConversation(row.id);toggle(true);
         const draft=drafts.get(row.id);
         if(draft&&!bridge().turnInFlight)bridge().setDraft(draft);
       }));
       if(row.id===currentId()){el.classList.add('active');el.setAttribute('aria-current','page')}
       return el;
     });
   }catch(e){if(isActive())setLoading(ref.history,'Unable to load saved conversations. Open History to retry.')}
 }
 function renderSearch(q,host){
   const term=String(q||'').trim().toLocaleLowerCase();
   host.replaceChildren();
   if(!term)return;
   const rows=(bridge()?.current?.events||[])
    .filter(e=>['assistant_message','user_message'].includes(e.kind))
    .map((e,i)=>({index:i,text:String(e.payload?.text||'')}))
    .filter(row=>row.text.toLocaleLowerCase().includes(term));
   if(!rows.length){host.append(make('p','p202b-empty','No matching messages in this loaded conversation.'));return}
   rows.slice(0,30).forEach(row=>{
     host.append(btn(row.text.slice(0,95),'p202b-search-hit',()=>{
       // The canonical message renderer owns ordering. Search only scrolls;
       // it never sends message text or alters its persistence.
       const messages=[...document.querySelectorAll('#messageStream .message-entry')];
       messages[row.index]?.scrollIntoView({block:'center',behavior:'smooth'});
       messages[row.index]?.classList.add('p202b-found');
       setTimeout(()=>messages[row.index]?.classList.remove('p202b-found'),1800);
     }));
   });
 }
 function renderOverview(){
   const id=currentId(),title=bridge()?.current?.title||'New Work Conversation';
   ref.title.textContent=title==='New conversation'?'New Work Conversation':title;
   ref.context.replaceChildren(make('strong','',ref.title.textContent),make('p','p202b-empty','Work view · local organization only'));
   if(id)ref.context.append(btn('Conversation options ›','p202b-link',openMenu));
   statusNotice('Messages use the canonical Vishnu conversation. Unlinked files and tasks are not shown as attached.');
 }
 function showWork(data){
   const work=ref.work;work.replaceChildren();
   if(data?.authority!=='read_only_projection'||!Array.isArray(data?.work_orders)){
     setLoading(work,'Work summary is unavailable.');return;
   }
   const active=new Set(['RUNNING','VERIFYING','RECOVERING','RETRYING','WAITING_APPROVAL']);
   const orders=data.work_orders.filter(w=>active.has(String(w.status||'').toUpperCase()));
   if(!orders.length){setLoading(work,'No active Project WorkOrders.');return}
   work.append(make('p','p202b-note','Global WorkOrders — not attached to this conversation'));
   orders.slice(0,4).forEach(o=>{
     work.append(itemRow('◈',o.title||'WorkOrder',String(o.status||'')+' · '+(o.project_name||'Project'),()=>nav('workflows')));
   });
 }
 function renderResources(){
   setLoading(ref.files,'No files are linked to this conversation. Open Library to browse authorized resources.');
   setLoading(ref.tasks,'No linked conversation tasks. Use Add to create a task in Today.');
 }
 async function reload(){
   if(!isActive())return;
   refreshController?.abort();const ctl=new AbortController();refreshController=ctl;
   const timeout=setTimeout(()=>ctl.abort(),8500);
   try{
     const req=async p=>bridge().api(p,{signal:ctl.signal});
     const settled=await Promise.allSettled([req('/work/summary'),req('/status')]);
     if(!isActive()||ctl.signal.aborted)return;
     if(settled[0].status==='fulfilled')showWork(settled[0].value);
     else setLoading(ref.work,'Work status temporarily unavailable.');
     if(settled[1].status==='fulfilled')status=settled[1].value;
   }finally{clearTimeout(timeout);if(refreshController===ctl)refreshController=null}
 }
 function sync(){
   syncing=false;
   const show=isActive();
   document.body.classList.toggle('p202-work-chat',show);
   if(ref.shell)ref.shell.hidden=!show;
   const shell=$('p202bShell');if(shell)shell.hidden=!show;
   const mobile=document.querySelector('.p202b-mobile-header');
   if(mobile)mobile.hidden=!show;
   if(!show){clearInterval(refreshTimer);refreshTimer=null;refreshController?.abort();return}
   if(lastId!==currentId()){
     const old=lastId;lastId=currentId();
     if(old)drafts.set(old,$('message')?.value||'');
     renderOverview();refreshHistory();
     renderResources();
   }
   if(!refreshTimer){reload();refreshTimer=setInterval(()=>{if(isActive()&&!document.hidden)reload()},60000)}
   const tab=ref.activeTab||'Chat';
   document.querySelectorAll('.p202b-tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===tab));
 }
 function queue(){if(syncing)return;syncing=true;queueMicrotask(sync)}
 function start(){
   try{selected=sessionStorage.getItem('vishnu.work.chat.view')==='on'}catch{}
   mount();
   const shell=$('p202bShell');ref.shell=shell;
   queue();
 }
 window.__vishnuP202B={version:1,authority:'presentation_only',open:startWorkView,newChat:newWork,isActive};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});
 else start();
})();