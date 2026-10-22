/* Vishnu 2.0 P2-08: one command registry, existing canonical destinations. */
(()=>{
'use strict';
if(window.vishnuCommandCenterInitialized)return;
window.vishnuCommandCenterInitialized=true;
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const registry=[
['home','Go to Home','Open Vishnu Home','Navigate','⌂','home','start overview'],
['chat','Open Chat','Start or continue a conversation','Navigate','☏','chat','conversation messages'],
['today','Open Today','View your daily plan','Navigate','▣','today','schedule my day'],
['workspaces','Open Workspaces','Manage your workspaces','Navigate','⬡','labs','spaces library'],
['projects','Open Projects','View all projects','Navigate','▧','projects','project work'],
['agents','Open Agents','Manage available agents','Navigate','♧','agents','agent workforce'],
['library','Open Library','Access knowledge and files','Navigate','▤','knowledge','files notes memory'],
['tools','Open Tools','Connected apps and capabilities','Tools','✧','tools','apps mcp tools'],
['devices','Open Devices','Trusted device management','Devices','▣','devices','security paired'],
['settings','Open Settings','Owner controls and preferences','Settings','⚙','settings','preferences'],
['search','Global Search','Find conversations and records','Navigate','⌕','search','search anything'],
['notifications','Open Notifications','Review notifications and alerts','Navigate','♧','notifications','approvals alert inbox'],
['new-chat','New Chat','Start a conversation','Create','☏','conversation','new chat create conversation'],
['new-project','New Project','Create a canonical Project','Create','⬡','create-project','create make start project'],
['new-workspace','New Workspace','Create a canonical Workspace','Create','✿','create-workspace','create space research workspace'],
['new-task','New Task','Add to your tasks','Create','☑','create-task','todo create task'],
['new-automation','New Automation','Open workflow creation','Create','⚙','workflows','automate workflow schedule automation'],
['new-note','New Note','Create in Knowledge / Notes','Create','▤','note','knowledge write note'],
['upload-file','Upload File','Use the secure Knowledge uploader','Files','▢','upload','attach file upload'],
['summarize-day','Summarize my day','Use permitted schedule and task context','Work','▣','prompt','daily summary what happened today'],
['summarize-this','Summarize This','Summarize permitted active context','Work','▤','prompt','summary current conversation page'],
['analyze-file','Analyze File','Review selected authorized file','Files','◈','file','analyze document report'],
['extract-actions','Extract Action Items','Prepare tasks from this conversation','Work','☑','prompt','tasks conversation extract'],
['research-agent','Research with Agent','Start a governed research request','Agents','✿','prompt','agent research'],
['custom-agent','Run Custom Agent','View registered agents first','Agents','⚡','agents','agent execute'],
['schedule-meeting','Schedule a Meeting','Use connected calendar when available','Work','▣','prompt','meeting calendar invite'],
['draft-email','Draft an Email','Create a draft without sending','Work','✉','prompt','email draft'],
['recent-work','Open Work','Inspect canonical Work and automations','Work','ϟ','workflows','work orders'],
['needs-approval','Pending Approvals','Review governed decisions','Work','⚠','notifications','approval queue']
].map(([id,title,description,category,icon,route,keywords])=>({id,title,description,category,icon,route,keywords}));
const byId=new Map(registry.map(x=>[x.id,x]));
const filters=['All','Navigate','Create','Work','Agents','Tools','Files','Devices','Settings'];
const primary=['new-chat','new-project','new-workspace','new-task','new-automation','tools'];
const groups=[['Navigate',['home','chat','today','workspaces','projects','agents','library']],
 ['Create',['new-chat','new-project','new-workspace','new-task','new-automation','new-note','upload-file']],
 ['Work & Agents',['summarize-this','analyze-file','extract-actions','research-agent','custom-agent','schedule-meeting','draft-email']]];
const examples=[['Create a project','new-project'],['Summarize my day','summarize-day'],['Open workspace','workspaces'],['Set a reminder','new-task'],['Find my last meeting','schedule-meeting'],['Analyze this file','analyze-file'],['Create a task from this chat','extract-actions']];
const state={active:false,q:'',category:'All',recent:[],status:'',busy:false,context:null,selected:0,revision:0,lastFocus:null,core:'idle'};
let root=null,prior=null,ready=false;
const api=(path,opts)=>{const f=window.vishnuChatBridge?.api;if(typeof f!=='function')throw Error('Authenticated Vishnu session unavailable');return f('/command-center'+path,opts)};
const commandAPI=(path,opts)=>{const f=window.vishnuChatBridge?.api;if(typeof f!=='function')throw Error('Authenticated Vishnu session unavailable');return f(path,opts)};
function status(message,type='info'){state.status=message;const el=$('ccStatus');if(el){el.textContent=message;el.dataset.type=type}}
function context(){const bridge=window.vishnuChatBridge;const project=window.projectCurrent||null;const ws=window.vishnuWorkspaces?.current||null;const projectId=project?.id||new URLSearchParams(location.search).get('project')||null;return {page:'Command Center',project:project?.name||null,projectId,workspace:ws?.name||null,workspaceId:ws?.id||null,conversation:bridge?.currentConversationId||null};}
function selectMatches(){const q=state.q.trim().toLowerCase(),filtered=registry.filter(x=>(state.category==='All'||x.category===state.category)&&(!q||[x.title,x.description,x.keywords,x.id].join(' ').toLowerCase().includes(q)));
return filtered.sort((a,b)=>q?((a.title.toLowerCase()===q?-10:0)-(b.title.toLowerCase()===q?-10:0)):0)}
function renderRow(x){return '<button type="button" class="cc-command" data-cc-id="'+x.id+'"><span class="cc-tile">'+esc(x.icon)+'</span><span class="cc-cmd-copy"><strong>'+esc(x.title)+'</strong><small>'+esc(x.description)+'</small></span><span class="cc-out">↗</span></button>'}
function panel(name,ids){return '<section class="cc-panel-list"><header><h3>'+esc(name)+'</h3><button data-cc-view="'+esc(name)+'">View all</button></header><div>'+ids.map(id=>byId.get(id)).filter(Boolean).map(renderRow).join('')+'</div></section>'}
function recentPanel(){const ids=state.recent.filter(x=>byId.has(x.id));return '<section class="cc-panel-list"><header><h3>Recently Used</h3><button data-cc-action="history">View all</button></header><div>'+(ids.length?ids.slice(0,7).map(row=>renderRow(byId.get(row.id))).join(''):'<p class="cc-placeholder">Your successfully opened commands will appear here.</p>')+'</div></section>'}
function drawLists(){const host=$('ccLists');if(!host)return;const matches=selectMatches();
if(state.q||state.category!=='All'){host.innerHTML='<section class="cc-panel-list cc-results"><header><h3>'+esc(state.q?'Matching commands':state.category+' commands')+'</h3><span>'+matches.length+' available</span></header><div>'+(matches.length?matches.map(renderRow).join(''):'<p class="cc-placeholder">No matching commands found. Clear the search or choose another category.</p>')+'</div></section>'+recentPanel()}
else host.innerHTML=groups.map(([g,ids])=>panel(g,ids)).join('')+recentPanel();
const tabs=$('ccFilters');if(tabs)tabs.innerHTML=filters.map(k=>'<button type="button" class="'+(state.category===k?'active':'')+'" data-cc-filter="'+k+'" aria-pressed="'+(state.category===k)+'">'+esc(k)+'</button>').join('');
}
function paintRecent(){drawLists()}
function mount(){
const h=$('moduleBody');if(!h)return;
state.context=context();state.q='';state.category='All';
h.innerHTML='<div class="cc-page"><header class="cc-top"><span class="cc-mark">ϟ</span><div><h1>Command Center</h1><p>Tell Vishnu what you want to do. Take action, create, navigate and automate.</p></div><div class="cc-top-actions"><button data-cc-action="help">ⓘ How to use</button><button data-cc-action="menu" aria-label="Command options">···</button></div></header><section class="cc-hero"><div class="cc-orb-stage" aria-hidden="true"><div class="cc-wave left"></div><img class="cc-neural" src="/iphone/assets/genesis/vishnu-core.png" alt="" loading="eager"><div class="cc-wave right"></div></div><div class="cc-hero-content"><h2>What would you like to do?</h2><p>Type a command or choose from quick actions below.</p><form id="ccCommandForm"><label class="cc-main-input"><span>✧</span><input id="ccCommandInput" aria-label="Ask Vishnu to do anything" placeholder="Ask Vishnu to do anything…" autocomplete="off" enterkeyhint="go" maxlength="500"><button class="cc-submit" type="submit" aria-label="Run entered command">↑</button></label></form><div class="cc-examples"><small>Examples:</small>'+examples.map(([l,id])=>'<button data-cc-example="'+id+'">'+esc(l)+'</button>').join('')+'</div></div></section><div class="cc-primary">'+primary.map(id=>{const c=byId.get(id);return '<button type="button" class="cc-primary-card" data-cc-id="'+c.id+'"><span class="cc-primary-icon">'+esc(c.icon)+'</span><strong>'+esc(c.title==='Open Tools'?'Open App':c.title)+'</strong><small>'+esc(c.description)+'</small></button>'}).join('')+'</div><nav class="cc-categories" aria-label="Command categories" id="ccFilters"></nav><div id="ccLists" class="cc-panels"></div><div class="cc-footer"><section><header><h3>✦ Quick Context</h3><p>Get relevant actions for your current context.</p></header><div class="cc-context"><span>Current Workspace<strong>'+esc(state.context.workspace||'None selected')+'</strong></span><span>Current Project<strong id="ccCurrentProject">'+esc(state.context.project||'None selected')+'</strong></span><span>Current Page<strong>Command Center</strong></span></div></section><section><header><h3>Keyboard Shortcuts</h3><p>Use verified shortcuts to work faster.</p></header><div class="cc-shortcuts"><span><kbd>Ctrl/Cmd</kbd> <kbd>K</kbd> Global Search</span><span><kbd>Ctrl/Cmd</kbd> <kbd>⇧ P</kbd> Command Center</span><span><kbd>↑</kbd><kbd>↓</kbd> Choose command</span><span><kbd>Esc</kbd> Exit results</span></div></section></div><p class="cc-status" id="ccStatus" role="status" aria-live="polite"></p></div>';
root=h.querySelector('.cc-page');root.dataset.state=state.core;
root.addEventListener('click',event=>{
const b=event.target.closest('button');if(!b)return;
if(b.dataset.ccFilter){state.category=b.dataset.ccFilter;drawLists();return}
if(b.dataset.ccId){executeId(b.dataset.ccId).catch(error=>status(error.message,'error'));return}
if(b.dataset.ccExample){executeId(b.dataset.ccExample).catch(error=>status(error.message,'error'));return}
if(b.dataset.ccView){state.category=b.dataset.ccView==='Navigate'?'Navigate':b.dataset.ccView==='Create'?'Create':'Work';drawLists();$('ccCommandInput')?.focus();return}
if(b.dataset.ccAction==='menu'){showOptions();return}
if(b.dataset.ccAction==='help'){showHelp();return}
if(b.dataset.ccAction==='history'){showHistory();return}
if(b.dataset.ccAction==='clear'){clearHistory().catch(e=>status(e.message,'error'))}
});
$('ccCommandForm').addEventListener('submit',event=>{event.preventDefault();if(event.isComposing)return;submit().catch(error=>status(error.message,'error'))});
$('ccCommandInput').addEventListener('input',event=>{state.q=event.target.value;state.core=state.q?'typing':'idle';root.dataset.state=state.core;drawLists()});
$('ccCommandInput').addEventListener('keydown',event=>{
if(event.isComposing)return;
if(event.key==='Escape'){event.preventDefault();state.q='';event.target.value='';state.category='All';drawLists()}
if(event.key==='ArrowDown'){let first=root.querySelector('.cc-command');if(first){event.preventDefault();first.focus()}}
});
root.addEventListener('keydown',event=>{const b=event.target.closest?.('.cc-command');if(!b)return;if(event.key==='ArrowDown'||event.key==='ArrowUp'){const list=[...root.querySelectorAll('.cc-command')];const n=list.indexOf(b);event.preventDefault();list[(n+(event.key==='ArrowDown'?1:-1)+list.length)%list.length]?.focus()}});
drawLists();status('Choose an action or type a command. Sensitive operations still require confirmation.');
loadHistory();
if(state.context.projectId&&!state.context.project){commandAPI('/projects/'+encodeURIComponent(state.context.projectId)).then(response=>{if(!state.active)return;const name=response.project?.name;if(!name)return;state.context.project=name;const cell=$('ccCurrentProject');if(cell)cell.textContent=name}).catch(()=>{})}
}
function showHelp(){status('Choose a command, or type a request. Creation opens the canonical editor. Work may require approval. Ctrl/Cmd+Shift+P opens this page; Ctrl/Cmd+K opens Global Search.');$('ccCommandInput')?.focus()}
function showOptions(){status('Command settings: use Vishnu Settings. Recent history is device-scoped and can be cleared here.');const host=$('ccStatus');host?.insertAdjacentHTML('beforeend',' <button type="button" data-cc-action="clear">Clear recent history</button> <button type="button" data-cc-id="settings">Open Settings</button>')}
function showHistory(){state.category='All';state.q='';$('ccCommandInput').value='';drawLists();$('ccLists')?.lastElementChild?.scrollIntoView({block:'nearest'})}
async function loadHistory(){try{const v=await api('/recent');if(!state.active)return;state.recent=Array.isArray(v.recent)?v.recent.filter(x=>byId.has(x.id)):[];paintRecent()}catch(e){status('Recent history unavailable: '+e.message)}}
async function remember(id){if(!byId.has(id))return;try{const d=await api('/recent',{method:'POST',body:JSON.stringify({command_id:id})});state.recent=d.recent||[];paintRecent()}catch(e){status('Command opened, but history could not be saved: '+e.message)}}
async function clearHistory(){await api('/recent',{method:'DELETE'});state.recent=[];paintRecent();status('Recent command history cleared on this trusted device.')}
async function go(mod){if(mod==='agents'){location.assign('/iphone/agents.html');return}if(mod==='chat'){await window.openModule('home');document.querySelector('#message')?.focus();return}if(mod==='today'){if(typeof window.vishnuChatBridge?.openTodayScreen!=='function')throw Error('Today assistant unavailable');await window.openModule('home');window.vishnuChatBridge.openTodayScreen();return}await window.openModule(mod)}
async function runPrompt(text){const bridge=window.vishnuTodayP203Bridge;if(typeof bridge?.runPrompt!=='function')throw Error('The canonical conversation executor is unavailable');await go('home');await bridge.runPrompt(text)}
async function toWizard(kind,name){
if(kind==='project'){await go('projects');const button=document.querySelector('[data-project-action="new-project"]');if(!button)throw Error('Canonical Project creation is not available in this workspace');button.click();if(name){const field=document.querySelector('input[name="name"]');if(field){field.value=name;field.dispatchEvent(new Event('input',{bubbles:true}))}}return}
if(kind==='workspace'){await go('labs');const button=document.querySelector('[data-workspace-new]');if(!button)throw Error('Canonical Workspace creation is not available');button.click();if(name){const field=document.querySelector('[data-workspace-form] [name="name"]');if(field){field.value=name;field.dispatchEvent(new Event('input',{bubbles:true}))}}return}
if(kind==='task'){const bridge=window.vishnuTodayP203Bridge;if(typeof bridge?.create!=='function')throw Error('Canonical task creation is unavailable');await window.openModule('home');bridge.create('task');return}
}
async function openNamedWorkspace(name){const d=await commandAPI('/workspaces?q='+encodeURIComponent(name)+'&status=active');const rows=d.workspaces||[];const exact=rows.filter(x=>x.name.toLowerCase()===name.toLowerCase());if(exact.length===1){await go('labs');document.querySelector('[data-workspace-open="'+CSS.escape(exact[0].id)+'"]')?.click();return}await go('labs');window.vishnuChatBridge?.showToast?.(rows.length?'Multiple Workspaces matched. Choose one in the Workspace library.':'No authorized Workspace matches that name.');}
async function executeId(id,options={}){const c=byId.get(id);if(!c||state.busy)return;state.busy=true;state.core='processing';if(root)root.dataset.state='processing';status('Opening '+c.title+'…');
try{
switch(c.route){
case 'home':case 'chat':case 'today':case 'labs':case 'projects':case 'knowledge':case 'tools':case 'devices':case 'settings':case 'search':case 'notifications':case 'workflows':await go(c.route);break;
case 'agents':await go('agents');break;
case 'conversation':if(window.personalAiDemoMode)throw Error('Preview mode cannot create conversations');await go('home');await window.vishnuChatBridge.createConversation();break;
case 'create-project':await toWizard('project',options.name);break;
case 'create-workspace':await toWizard('workspace',options.name);break;
case 'create-task':await toWizard('task');break;
case 'note':await go('memory');if(!document.querySelector('#memoryAdd'))throw Error('Canonical note editor unavailable');document.querySelector('#memoryAdd').click();break;
case 'upload':{await go('knowledge');const picker=document.querySelector('#knowledgeFile,#knowledgeFileInput,[data-knowledge-upload],#attachmentButton');if(picker&&picker.type==='file')picker.click();else if(picker)picker.click();else window.vishnuChatBridge?.showToast?.('Open the existing Knowledge upload picker. No file has been uploaded.');break}
case 'file':await go('knowledge');window.vishnuChatBridge?.showToast?.('Select an authorized file before requesting analysis.');break;
case 'prompt':{
const prompts={
'summarize-day':'Summarize my day using only the schedule, tasks and activity data you are authorized to access. Clearly identify missing sources.',
'summarize-this':'Summarize the current authorized conversation, and ask me to select a source if no context is available.',
'extract-actions':'Extract proposed action items from the current authorized conversation. Show an editable preview; do not create tasks without confirmation.',
'research-agent':'Research the topic I specify using authorized tools and sources. Ask me for the topic before initiating governed work.',
'schedule-meeting':'Help me schedule a meeting. First ask for attendees, date, time and timezone and confirm before creating invitations.',
'draft-email':'Help draft an email. Ask for missing recipient and purpose; do not send it.'
};await runPrompt(prompts[id]||c.description);break;
}
default:throw Error('This command is not configured')
}
await remember(id);
}catch(error){status(error?.message||'Unable to open command.','error');throw error}finally{state.busy=false;state.core='idle';if(root?.isConnected)root.dataset.state='idle'}}
async function submit(){if(state.busy)return;const raw=($('ccCommandInput')?.value||'').trim();if(!raw)return;const text=raw.toLowerCase().replace(/[.!?]+$/,'').trim();
const namedProject=raw.match(/^(?:create|make|start)\s+(?:a\s+)?(?:new\s+)?project\s+(?:called|named)\s+(.+)$/i);
if(namedProject){await executeId('new-project',{name:namedProject[1].slice(0,120)});return}
const namedWorkspace=raw.match(/^(?:create|make|start)\s+(?:a\s+)?(?:new\s+)?workspace\s+(?:called|named|for)\s+(.+)$/i);
if(namedWorkspace){await executeId('new-workspace',{name:namedWorkspace[1].slice(0,120)});return}
const openWs=raw.match(/^open\s+(.+?)\s+workspace$/i);if(openWs){await openNamedWorkspace(openWs[1]);return}
const aliases=[
[/^(?:new|create|start)\s+(?:a\s+)?(?:new\s+)?(?:chat|conversation)$/,'new-chat'],
[/^(?:create|make|start)\s+(?:a\s+)?(?:new\s+)?project$/,'new-project'],
[/^(?:create|make|start)\s+(?:a\s+)?(?:new\s+)?workspace$/,'new-workspace'],
[/^(?:create|make|add)\s+(?:a\s+)?(?:new\s+)?task$/,'new-task'],
[/^summari[sz]e my day$/,'summarize-day'],
[/^show (?:my )?(?:active )?agents$/,'agents'],
[/^show pending approvals$/,'needs-approval'],
[/^open (?:my )?(?:vishnu )?home$/,'home'],
[/^find my last meeting$/,'schedule-meeting'],
[/^(?:draft|write) (?:an? )?email$/,'draft-email'],
[/^set (?:a )?reminder$/,'new-task'],
[/^analy[sz]e (?:this |selected )?file$/,'analyze-file']
];for(const [rx,id] of aliases)if(rx.test(text)){await executeId(id);return}
const match=registry.filter(c=>c.title.toLowerCase()===text||c.id===text);if(match.length===1){await executeId(match[0].id);return}
const guess=selectMatches().filter(x=>x.title.toLowerCase()===text);if(guess.length===1){await executeId(guess[0].id);return}
// Unclassified text is an AI *conversation request*, not ungoverned command execution.
if(!await window.vishnuChatBridge?.requestConfirmation?.('Open this request in a normal Vishnu conversation? Vishnu will ask for any missing information and governed approvals.'))return;
await runPrompt(raw);
}
async function open(){if(state.active){$('ccCommandInput')?.focus();return}state.lastFocus=document.activeElement;await window.openModule('command');}
const original=window.openModule;if(typeof original!=='function')return;let navSeq=0;
window.openModule=async function(name,...args){const seq=++navSeq;if(name!=='command'){state.active=false;document.body.classList.remove('cc-page-mode');root=null;return original.call(this,name,...args)}await original.call(this,'command',...args);if(seq!==navSeq)return;state.active=true;document.body.classList.add('cc-page-mode');mount()};
window.vishnuOpenCommandCenter=open;
window.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.shiftKey&&e.key.toLowerCase()==='p'){if(e.target.closest?.('[contenteditable="true"]'))return;e.preventDefault();open().catch(error=>status(error.message,'error'));return}if(!state.active)return;if((e.ctrlKey||e.metaKey)&&e.key==='/'){if(e.target.closest?.('input,textarea,[contenteditable]'))return;e.preventDefault();$('ccCommandInput')?.focus();return}if(e.key==='Escape'&&e.target!==$('ccCommandInput')){e.preventDefault();go('home').catch(()=>{})}});
document.addEventListener('click',e=>{if(e.target.closest?.('[data-command-center-entry]')){e.preventDefault();e.stopImmediatePropagation();open().catch(err=>status(err.message,'error'))}},true);
window.addEventListener('vishnu:new-chat',()=>{state.active=false;document.body.classList.remove('cc-page-mode')});
window.vishnuCommandCenter={open,executeId,registry:registry.map(({id,title,category})=>({id,title,category})),get state(){return state}};
})();
