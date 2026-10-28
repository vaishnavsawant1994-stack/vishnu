/* P2-02B Work Conversation: opt-in presentation over canonical conversation APIs.
 * Work UI preference is device-local; conversation type and optional Project association
 * persist in canonical continuity. Neither confers new authorization or execution scope. Never synthesize WorkPlan progress.
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
 let resumePending=false, resumeBusy=false, checkedConversationId=null, checkingId=null;
 const ref={}, drafts=new Map();
 let linkedProjectId=null, linkedProject=null, linkedWork=null, linkedApprovals=[];
 const statusNotice=txt=>{if(ref.notice)ref.notice.textContent=txt;};
 const inform=msg=>bridge()?.showToast?.(msg);
 const guarded=async job=>{try{return await job()}catch(e){inform(e?.message||'This action is not available right now.')}};
 const nav=dest=>bridge()?.openModule?.(dest);
 const toggle=enable=>{
   selected=Boolean(enable);resumePending=false;
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
 async function createWork(){
   if(bridge()?.turnInFlight)throw new Error('Finish or cancel the current response first.');
   if(($('message')?.value||'').trim())throw new Error('Send or clear your unsent message first.');
   const response=await bridge().api('/conversations',{method:'POST',body:JSON.stringify({
     title:'New Work Conversation',context_type:'work'
   })});
   const item=response?.conversation;
   if(!item?.id || item?.context?.conversation_kind!=='work')
     throw new Error('Server did not confirm a Work-scoped conversation.');
   await bridge().openConversation(item.id);
   toggle(true);queue();
 }
 function newWork(){return guarded(createWork)}
 function startWorkView(){
   return guarded(async()=>{
     if(bridge()?.turnInFlight)throw new Error('Finish the current response first.');
     if(($('message')?.value||'').trim())throw new Error('Send or clear the current draft before switching contexts.');
     const listing=await bridge().api('/conversations?kind=work&limit=1');
     const row=listing?.conversations?.[0];
     if(row?.id){
       await bridge().openConversation(row.id);
       toggle(true);
     }else await createWork();
     queue();
   });
 }
 function startPersonalView(){
   return guarded(async()=>{
     if(bridge()?.turnInFlight)throw new Error('Finish the current response first.');
     if(($('message')?.value||'').trim())throw new Error('Send or clear the current draft before switching contexts.');
     const listing=await bridge().api('/conversations?kind=personal&limit=1');
     const row=listing?.conversations?.[0];
     if(row?.id)await bridge().openConversation(row.id);
     else await bridge().createConversation();
     toggle(false);
   });
 }
 function chooseContext(){
   const dialog=make('dialog','p202b-modal');dialog.setAttribute('aria-label','Conversation context');
   dialog.append(make('h2','','Choose a conversation context'));
   dialog.append(make('p','','Work and Personal chats retain distinct canonical conversation types. Changing the view switches to a different saved conversation; it does not move or share the current transcript. This remains a single-owner security domain.'));
   const actions=make('div','p202b-modal-actions');
   actions.append(btn('Personal Chat','',()=>{dialog.close();startPersonalView()}));
   actions.append(btn('Project context…','',()=>{dialog.close();$('vContextChip')?.click()}));
   actions.append(btn('Keep Work view','p202b-primary',()=>dialog.close()));
   dialog.append(actions);document.body.append(dialog);
   dialog.addEventListener('close',()=>dialog.remove(),{once:true});
   dialog.showModal();
 }
 function openCanonicalMenu(){
   if($('chatMenuButton')&&!$('chatMenuButton').classList.contains('hidden'))$('chatMenuButton').click();
   else $('chatDetailsTop')?.click();
 }
 function openMobileSearch(){
   const dialog=make('dialog','p202b-modal p202b-search-modal');
   dialog.append(make('h2','','Search this Work conversation'));
   const input=make('input');
   input.type='search';input.placeholder='Search loaded messages…';
   input.setAttribute('aria-label','Search messages in this conversation');
   const list=make('div','p202b-search-results');
   input.addEventListener('input',()=>renderSearch(input.value,list));
   list.addEventListener('click',event=>{
     if(event.target.closest?.('.p202b-search-hit'))dialog.close();
   },true);
   const close=btn('Close','p202b-primary',()=>dialog.close());
   dialog.append(input,list,close);
   document.body.append(dialog);
   dialog.addEventListener('close',()=>dialog.remove(),{once:true});
   dialog.showModal();input.focus();
 }
 function openMenu(){
   if(window.matchMedia('(max-width:900px)').matches){
     return alertDialog('Work conversation sections','Choose a section or open the conversation options.',[
       ['Search messages',openMobileSearch],
       ['Files',()=>switchTab('Files')],['Tasks',()=>switchTab('Tasks')],
       ['Research',()=>switchTab('Research')],['Code',()=>switchTab('Code')],
       ['Plans',()=>switchTab('Plans')],['Link Project',()=>guarded(linkProjectPicker)],
       ['Conversation options',openCanonicalMenu]
     ]);
   }
   openCanonicalMenu();
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
   ref.history.setAttribute('aria-label','Saved Work conversations in the owner continuity ledger');
   history.append(make('p','p202b-note','Only Work conversations from the existing owner-authorized continuity ledger.'),ref.history);
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
 ref.link=btn('Link Project','p202b-small-link',()=>guarded(linkProjectPicker));about.querySelector('h3').append(ref.link);
   ref.context=make('div','p202b-context-body');
   about.append(ref.context);context.append(about);
   const files=section('Files & Resources');files.querySelector('h3').append(btn('＋ Add','p202b-small-link',()=>linkedProject?guarded(uploadProjectFile):openFiles()));
   ref.files=make('div');setLoading(ref.files,'No files are linked to this conversation.');files.append(ref.files);context.append(files);
   const tasks=section('Tasks');
   tasks.querySelector('h3').append(btn('＋ Add','p202b-small-link',()=>linkedProject?guarded(addLinkedTask):addTask()));
   ref.tasks=make('div');setLoading(ref.tasks,'No conversation-linked tasks.');tasks.append(ref.tasks);context.append(tasks);
   const approvals=section('Approvals');ref.approvals=make('div');setLoading(ref.approvals,'No Project linked.');approvals.append(ref.approvals);context.append(approvals);
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
   const mobileNav=make('nav','p202b-mobile-nav');mobileNav.id='p202bMobileNav';
   mobileNav.setAttribute('aria-label','Work conversation mobile navigation');
   [['Home','⌂',()=>nav('home')],['Chat','▢',()=>{$('message')?.focus()}],
    ['Today','▣',()=>bridge()?.openTodayScreen?.('all')],['Work','▦',()=>nav('workflows')],
    ['More','•••',()=>$('historyButton')?.click()]].forEach(([label,glyph,act])=>{
     const el=btn('',label==='Chat'?'active':'',act);
     el.append(make('span','',glyph),make('small','',label));
     if(label==='Chat')el.setAttribute('aria-current','page');
     mobileNav.append(el);
   });
   shell.append(mobileNav);
   const existing=$('voicePanel');
   // The original message stream and composer remain in their canonical DOM;
   // this shell is layout/navigation only and must not duplicate either.
   document.body.append(shell);
   const entry=btn('▣ Work Chat','p202b-entry',startWorkView);
   entry.textContent='';entry.append(make('span','p202b-nav-icon','▦'),make('span','p202b-nav-label','Work Chat'));
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
 
 async function setProjectLink(projectId){
   const id=currentId();
   if(!isActive()||!id)throw new Error('Open a Work conversation first.');
   const next=projectId||null;
   const result=await bridge().api('/conversations/'+encodeURIComponent(id)+'/work-project',{
     method:'PUT',body:JSON.stringify({project_id:next,confirm:true})
   });
   if(result?.conversation?.context?.work_project_id!==next)
     throw new Error('Canonical Project association was not confirmed.');
   linkedProjectId=next;renderResources();
   await bridge().openConversation(id);await reload();refreshHistory();
   inform(next?'Project linked to this Work conversation.':'Project unlinked.');
 }
 async function linkProjectPicker(){
   const payload=await bridge().api('/projects');
   const projects=(Array.isArray(payload?.projects)?payload.projects:[]).filter(p=>p.id&&p.status!=='archived');
   const dialog=make('dialog','p202b-modal p202b-resources-modal');
   dialog.append(make('h2','','Choose an existing Project'),make('p','',
     'Only existing, authorized Project resources will be shown. No work starts automatically.'));
   const search=make('input');search.type='search';search.placeholder='Search Projects';
   search.setAttribute('aria-label','Search Projects');
   const list=make('div','p202b-project-choices');
   const draw=()=>{
     list.replaceChildren();
     projects.filter(p=>String(p.name||'').toLowerCase().includes(search.value.toLowerCase()))
       .slice(0,75).forEach(p=>list.append(btn(String(p.name||'Project')+(p.id===linkedProjectId?' · Linked':''),
       'p202b-project-choice',()=>{dialog.close();guarded(()=>setProjectLink(p.id))})));
     if(!list.childElementCount)list.append(make('p','p202b-empty','No available Projects.'));
   };
   search.addEventListener('input',draw);draw();
   const footer=make('div','p202b-modal-actions');
   if(linkedProjectId)footer.append(btn('Unlink Project','',()=>{dialog.close();guarded(()=>setProjectLink(null))}));
   footer.append(btn('Cancel','p202b-primary',()=>dialog.close()));
   dialog.append(search,list,footer);document.body.append(dialog);
   dialog.addEventListener('close',()=>dialog.remove(),{once:true});dialog.showModal();
 }
 function resourceDialog(title,items,mapper,actions=[]){
   const dialog=make('dialog','p202b-modal p202b-resources-modal');
   dialog.append(make('h2','',title),make('p','','Resources remain in the existing authorized Project.'));
   const list=make('div','p202b-project-choices');
   items.slice(0,75).forEach(item=>{
     const [label,action]=mapper(item);
     list.append(btn(label,'p202b-project-choice',()=>{dialog.close();action()}));
   });
   if(!items.length)list.append(make('p','p202b-empty','No Project resources found.'));
   const footer=make('div','p202b-modal-actions');
   actions.forEach(([label,act])=>footer.append(btn(label,'',()=>{dialog.close();act()})));
   footer.append(btn('Close','p202b-primary',()=>dialog.close()));
   dialog.append(list,footer);
   document.body.append(dialog);dialog.addEventListener('close',()=>dialog.remove(),{once:true});dialog.showModal();
 }
 function openProjectFile(file){
   if(!file?.id||!linkedProjectId)return;
   const actions=[];
   if(['upload','deliverable'].includes(file.kind)){
     actions.push(['Download file',()=>{
       const a=make('a');a.href='/iphone/api/projects/'+encodeURIComponent(linkedProjectId)+'/files/'+encodeURIComponent(file.id)+'/download';
       document.body.append(a);a.click();a.remove();
     }]);
     actions.push(['Preview text',()=>guarded(async()=>{
       const p='/projects/'+encodeURIComponent(linkedProjectId)+'/files/'+encodeURIComponent(file.id)+'/index';
       const result=await bridge().api(p);
       alertDialog(file.title||'Preview',String(result?.extracted_text||'No text preview is available.').slice(0,12000));
     })]);
   }
   alertDialog(file.title||'File','Canonical Project resource · '+String(file.kind||'file'),actions);
 }
 function openProjectTask(task){
   if(!task?.id||!linkedProjectId)return;
   const done=task.status==='done';
   alertDialog(task.title||'Task','Project task · '+String(task.status||'planned'),[
     [done?'Reopen':'Mark done',()=>guarded(async()=>{
       const url='/projects/'+encodeURIComponent(linkedProjectId)+'/tasks/'+encodeURIComponent(task.id);
       await bridge().api(url,{method:'PATCH',body:JSON.stringify({status:done?'planned':'done'})});
       await reload();inform('Project task updated.');
     })]
   ]);
 }
 function showLinkedResources(project,plan,approvals){
   linkedProject=project;linkedWork=plan;linkedApprovals=approvals;
   if(ref.link)ref.link.textContent='Change Project';
   ref.context.replaceChildren(make('strong','',bridge()?.current?.title||'Work Conversation'),
     make('p','p202b-note','Linked Project · '+String(project.name||'Project')));
   renderRows(ref.files,project.files||[],'No Project files.',f=>
     itemRow(f.kind==='deliverable'?'▧':'▤',f.title||'File',String(f.kind||'file'),()=>openProjectFile(f)));
   renderRows(ref.tasks,(project.tasks||[]).slice(0,8),'No Project tasks.',t=>
     itemRow(t.status==='done'?'✓':'□',t.title||'Task',String(t.status||'planned'),()=>openProjectTask(t)));
   renderRows(ref.approvals,approvals.slice(0,5),'No pending Project approvals.',a=>
     itemRow('◈',a.title||a.description||'Approval',String(a.status||'Pending'),()=>nav('workflows')));
   ref.work.replaceChildren(make('p','p202b-note','Linked Project · '+String(project.name||'Project')));
   if(plan?.p10_plan)ref.work.append(itemRow('▣','WorkPlan · '+String(plan.p10_plan.state||'available'),
     (plan.p10_plan.tasks||[]).length+' steps',()=>nav('workflows')));
   else ref.work.append(make('p','p202b-empty','No active canonical Project WorkPlan.'));
 }
 async function loadLinkedProject(signal){
   const id=currentId();if(!id)return;
   const bundle=await bridge().api('/conversations/'+encodeURIComponent(id),{signal});
   if(signal.aborted||!isActive()||id!==currentId())return;
   const ctx=bundle?.conversation?.context||{};
   if(ctx.conversation_kind!=='work')return;
   const pid=ctx.work_project_id||null;
   if(pid!==linkedProjectId){linkedProjectId=pid;renderResources();renderOverview();}
   if(!pid)return;
   const root='/projects/'+encodeURIComponent(pid);
   const results=await Promise.allSettled([
     bridge().api(root,{signal}),bridge().api(root+'/work',{signal}),
     bridge().api('/approvals-center?limit=100',{signal})
   ]);
   if(signal.aborted||!isActive()||id!==currentId()||pid!==linkedProjectId)return;
   const project=results[0].status==='fulfilled'?results[0].value?.project:null;
   if(!project){
     setLoading(ref.files,'Linked Project is unavailable or archived.');
     setLoading(ref.tasks,'Linked Project tasks unavailable.');
     setLoading(ref.approvals,'Linked Project approvals unavailable.');
     setLoading(ref.work,'Linked WorkPlan unavailable.');
     return;
   }
   const plan=results[1].status==='fulfilled'?results[1].value:null;
   const all=results[2].status==='fulfilled'?results[2].value?.approvals:[];
   showLinkedResources(project,plan,(Array.isArray(all)?all:[]).filter(a=>a.project_id===pid));
 }
 async function addLinkedTask(){
   const title=window.prompt('New Project task title');
   if(!title?.trim()||!linkedProjectId)return;
   await bridge().api('/projects/'+encodeURIComponent(linkedProjectId)+'/tasks',{
     method:'POST',body:JSON.stringify({title:title.trim().slice(0,180)})
   });
   await reload();inform('Task created in linked Project.');
 }
 async function uploadProjectFile(){
   if(!linkedProjectId)return linkProjectPicker();
   const projectId=linkedProjectId;
   const picker=make('input');picker.type='file';picker.hidden=true;
   picker.accept='.pdf,.docx,.xlsx,.csv,.txt,.md,.png,.jpg,.jpeg,.webp';
   document.body.append(picker);
   picker.addEventListener('change',()=>guarded(async()=>{
     const file=picker.files?.[0];if(!file)return;
     if(!file.size||file.size>12*1024*1024)throw new Error('File must be between 1 byte and 12 MB.');
     if(!/[.](pdf|docx|xlsx|csv|txt|md|png|jpg|jpeg|webp)$/i.test(file.name))
       throw new Error('Unsupported Project file type.');
     const raw=await new Promise((resolve,reject)=>{
       const reader=new FileReader();
       reader.onload=()=>resolve(String(reader.result||'').split(',')[1]||'');
       reader.onerror=()=>reject(new Error('Unable to read the selected file.'));
       reader.readAsDataURL(file);
     });
     if(linkedProjectId!==projectId)throw new Error('Linked Project changed during upload.');
     await bridge().api('/projects/'+encodeURIComponent(projectId)+'/files/upload',{
       method:'POST',body:JSON.stringify({filename:file.name,media_type:file.type||'application/octet-stream',content_base64:raw})
     });
     await reload();inform('File uploaded to the linked Project.');
   }).finally(()=>picker.remove()),{once:true});
   picker.click();
 }
 async function createLinkedPlan(){
   if(!linkedProjectId)throw new Error('Link a Project before creating a plan.');
   const pid=linkedProjectId;
   const query=window.prompt('Describe the desired Project outcome to plan');
   if(!query?.trim())return;
   if(!window.confirm('Create a new plan in the existing Project? No execution will start automatically.'))return;
   await bridge().api('/projects/'+encodeURIComponent(pid)+'/work/plan',{
     method:'POST',body:JSON.stringify({query:query.trim().slice(0,2000)})
   });
   await reload();inform('Canonical Project WorkPlan created.');
 }
 async function linkedPlanAction(planId,action){
   if(!linkedProjectId||!planId||!['pause','resume'].includes(action))
     throw new Error('A linked canonical plan is required.');
   if(!window.confirm((action==='pause'?'Pause':'Resume')+' this existing Project WorkPlan?'))return;
   await bridge().api('/projects/'+encodeURIComponent(linkedProjectId)+'/work/'+encodeURIComponent(planId)+'/'+action,{
     method:'POST',body:'{}'
   });
   await reload();inform('Project WorkPlan '+action+' confirmed.');
 }
 async function createLinkedArtifact(){
   if(!linkedProjectId)throw new Error('Link a Project before creating an artifact.');
   const title=window.prompt('Title for a Project text artifact');
   if(!title?.trim())return;
   const content=window.prompt('Artifact text (a saved Project deliverable)');
   if(!content?.trim())return;
   if(!window.confirm('Save this text as a persistent Project deliverable?'))return;
   const pid=linkedProjectId;
   await bridge().api('/projects/'+encodeURIComponent(pid)+'/deliverables',{
     method:'POST',body:JSON.stringify({title:title.trim().slice(0,180),content:content.trim().slice(0,12000)})
   });
   await reload();inform('Artifact saved to canonical Project deliverables.');
 }
 function showLinkedPlan(){
   const plan=linkedWork?.p10_plan;
   if(!plan)return alertDialog('Project WorkPlan','No canonical WorkPlan exists for the linked Project.',[
     ['Open Project planner',()=>nav('projects')],['Create Project plan',()=>guarded(createLinkedPlan)]
   ]);
   resourceDialog('Canonical Project WorkPlan',plan.tasks||[],t=>[
     String(t.objective||t.id||'Step')+' · '+String(t.status||'WAITING'),
     ()=>alertDialog('WorkPlan step',String(t.objective||'')+' · '+String(t.status||''),[
       ['Open governed Work',()=>nav('workflows')]
     ])
   ],[
     ['Pause',()=>guarded(()=>linkedPlanAction(plan.id,'pause'))],
     ['Resume',()=>guarded(()=>linkedPlanAction(plan.id,'resume'))],
     ['Open governed Work',()=>nav('workflows')]
   ]);
 }
 function openFiles(){
   if(linkedProject) return resourceDialog('Files & Deliverables',linkedProject.files||[],f=>[String(f.title||'File')+' · '+String(f.kind||'file'),()=>openProjectFile(f)],[[ 'Upload File',()=>guarded(uploadProjectFile)],['Create Text Artifact',()=>guarded(createLinkedArtifact)]]);
   alertDialog('Files & Resources','This Work chat currently has no canonical conversation-attachment association. Adding a file to Knowledge is a separate, persistent action and requires explicit owner choice.',[
     ['Open Library',()=>nav('knowledge')],['Add to Knowledge',()=>$('attachmentInput')?.click()]
   ]);
 }
 function addTask(){
   if(linkedProject)return resourceDialog('Project Tasks',linkedProject.tasks||[],t=>[String(t.title||'Task')+' · '+String(t.status||'planned'),()=>openProjectTask(t)],[['Add Project Task',()=>guarded(addLinkedTask)]]);
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
   if(name==='Files')return openFiles();
   if(name==='Tasks'&&linkedProject)return addTask();
   if(name==='Plans'&&linkedProject)return showLinkedPlan();
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
     const data=await bridge().api('/conversations?kind=work&limit=50');
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
   if(ref.link)ref.link.textContent=linkedProjectId?'Change Project':'Link Project';
   const id=currentId(),title=bridge()?.current?.title||'New Work Conversation';
   ref.title.textContent=title==='New conversation'?'New Work Conversation':title;
   ref.context.replaceChildren(make('strong','',ref.title.textContent),make('p','p202b-empty','Work · saved conversation context'));
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
   linkedProject=null;linkedWork=null;linkedApprovals=[];
   if(ref.approvals)setLoading(ref.approvals,'No linked Project approvals.');
   setLoading(ref.files,'No files are linked to this conversation. Open Library to browse authorized resources.');
   setLoading(ref.tasks,'No linked conversation tasks. Use Add to create a task in Today.');
 }
 async function reload(){
   if(!isActive())return;
   refreshController?.abort();const ctl=new AbortController();refreshController=ctl;
   const timeout=setTimeout(()=>ctl.abort(),8500);
   try{
     const req=async p=>bridge().api(p,{signal:ctl.signal});
     const settled=await Promise.allSettled([req('/work/summary'),req('/status'),loadLinkedProject(ctl.signal)]);
     if(!isActive()||ctl.signal.aborted)return;
     if(!linkedProjectId&&settled[0].status==='fulfilled')showWork(settled[0].value);
     else if(!linkedProjectId)setLoading(ref.work,'Work status temporarily unavailable.');
     if(settled[1].status==='fulfilled')status=settled[1].value;
   }finally{clearTimeout(timeout);if(refreshController===ctl)refreshController=null}
 }
 async function resumeExistingWorkView(){
   if(!resumePending||resumeBusy||!selected||!ready()||!document.body.classList.contains('home-landing'))return;
   resumePending=false;resumeBusy=true;
   try{
     const result=await bridge().api('/conversations?kind=work&limit=50');
     const rows=result?.conversations||[];
     const id=rows.some(row=>row.id===result?.active_conversation_id)?result.active_conversation_id:rows[0]?.id;
     if(id && selected && ready())await bridge().openConversation(id);
   }catch{
     inform('Work conversation could not be resumed. Open a saved conversation from History.');
   }finally{resumeBusy=false;queue()}
 }
 async function detectWorkContext(id){
   if(!id||checkingId===id)return;
   checkingId=id;
   try{
     const data=await bridge().api('/conversations/'+encodeURIComponent(id));
     if(currentId()!==id)return;
     const work=data?.conversation?.context?.conversation_kind==='work';
   if(work&&id===currentId())linkedProjectId=data.conversation.context.work_project_id||null;
     if(work && !projectScoped()){
       if(!selected)toggle(true);
     }else if(selected)toggle(false);
   }catch{
     // Do not claim a conversation's classification without a verified read.
     if(selected&&currentId()===id)toggle(false);
   }finally{if(checkingId===id)checkingId=null}
 }
 function sync(){
   syncing=false;
   const id=currentId();
   if(id && id!==checkedConversationId){
     checkedConversationId=id;
     void detectWorkContext(id);
   }
   if(resumePending && selected && ready() && document.body.classList.contains('home-landing'))
     void resumeExistingWorkView();
   const show=isActive();
   if(show && document.body.classList.contains('chat-details-open')){
     document.body.classList.remove('chat-details-open');
     $('chatDetailDesktop')?.classList.add('hidden');
     $('chatDetailDesktop')?.setAttribute('aria-hidden','true');
   }
   const searchButton=document.querySelector('.reference-desktop-tools [data-reference-search]');
   if(searchButton){
     const node=[...searchButton.childNodes].find(child=>child.nodeType===3);
     if(node){
       if(!searchButton.dataset.p202bOriginal)searchButton.dataset.p202bOriginal=node.textContent||' Search anything… ';
       node.textContent=show?' Search in this conversation… ':searchButton.dataset.p202bOriginal;
     }
   }
   document.body.classList.toggle('p202-work-chat',show);
   if(ref.shell)ref.shell.hidden=!show;
   const shell=$('p202bShell');if(shell)shell.hidden=!show;
   const mobile=document.querySelector('.p202b-mobile-header');
   if(mobile)mobile.hidden=!show;
   if(!show){clearInterval(refreshTimer);refreshTimer=null;refreshController?.abort();return}
   if(lastId!==currentId()){
     const old=lastId;lastId=currentId();
     if(old)drafts.set(old,$('message')?.value||'');
     linkedProjectId=bridge()?.current?.context?.work_project_id||null;
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
   resumePending=selected;
   mount();
   const shell=$('p202bShell');ref.shell=shell;
   queue();
 }
 window.__vishnuP202B={version:2,authority:'canonical_conversation_context',open:startWorkView,newChat:newWork,isActive};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});
 else start();
})();
