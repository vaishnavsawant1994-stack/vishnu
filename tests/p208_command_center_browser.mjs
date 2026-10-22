/* P2-08 actual-browser fixture for command routing, keyboard and responsive layout. */
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';
const js=await readFile(new URL('../pwa/command-center.js',import.meta.url),'utf8');
const css=await readFile(new URL('../pwa/command-center.css',import.meta.url),'utf8');
const neuralCore=await readFile(new URL('../pwa/assets/genesis/vishnu-core.png',import.meta.url));
const screenshots=process.env.P208_SCREENSHOT_DIR;
if(screenshots)await mkdir(screenshots,{recursive:true});
const html=`<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{margin:0;background:#020b1c;color:white;font:14px system-ui}#modulePanel{position:fixed;inset:66px 0 0 214px;overflow:auto}
.module-body{height:100%}.module-head{display:block}.reference-desktop-tools{position:fixed;top:0;left:214px;right:0;height:64px;background:#06152b}
@media(max-width:760px){#modulePanel{inset:58px 0 55px}.reference-desktop-tools{left:0;height:55px}}
</style><style>${css}</style></head><body><div class="reference-desktop-tools"><button data-command-center-entry>Command Center</button></div>
<div id="modulePanel" class="open"><header class="module-head">Current Module</header><div class="module-body" id="moduleBody"></div></div>
<script>
window.routeCalls=[];window.historySaved=[];window.promptCalls=[];
window.openModule=async(name)=>{routeCalls.push(name);document.getElementById('moduleBody').innerHTML=name==='projects'?'<button data-project-action="new-project">New Project</button>':name==='labs'?'<button data-workspace-new>New Workspace</button><button data-workspace-open="w-rudra">Rudra Health Care</button>':name==='workflows'?'<button id="workflowAdd">New Workflow</button>':'<main>'+name+'</main>'; if(name==='projects')document.querySelector('[data-project-action]').onclick=()=>{document.getElementById('moduleBody').innerHTML='<input name="name" />';window.projectWizardOpened=true};if(name==='labs')document.querySelector('[data-workspace-new]').onclick=()=>{document.getElementById('moduleBody').innerHTML='<form data-workspace-form><input name="name"></form>';window.workspaceWizardOpened=true};if(name==='labs')document.querySelector('[data-workspace-open]').onclick=()=>{window.lastOpenedWorkspace='w-rudra'};if(name==='workflows')document.getElementById('workflowAdd').onclick=()=>{window.workflowComposerOpened=true}};
window.vishnuChatBridge={api:async(path,opt={})=>{if(path==='/command-center/recent'&&(!opt.method||opt.method==='GET'))return {recent:window.historySaved};if(path==='/command-center/recent'&&opt.method==='POST'){const id=JSON.parse(opt.body).command_id;window.historySaved=[{id,at:new Date().toISOString()},...window.historySaved.filter(x=>x.id!==id)].slice(0,12);return {recent:window.historySaved}}if(path==='/command-center/recent'&&opt.method==='DELETE'){window.historySaved=[];return {cleared:true}}if(path.startsWith('/workspaces?'))return {workspaces:path.includes('Rudra%20Health%20Care')?[{id:'w-rudra',name:'Rudra Health Care'}]:path.includes('Hidden%20Workspace')?[{id:'w-hidden',name:'Hidden Workspace'}]:[]};throw Error('Unexpected route '+path)},createConversation:async()=>{window.newChats=(window.newChats||0)+1},requestConfirmation:async()=>true,showToast:(m)=>{window.lastToast=m}};
window.vishnuTodayP203Bridge={create:kind=>window.createdKind=kind,goChat:()=>{window.chatViewOpened=(window.chatViewOpened||0)+1},runPrompt:async text=>{window.promptCalls.push(text)}};window.openKnowledgeNoteEditor=async()=>{window.noteEditorOpened=true};
</script><script src="/p208"></script></body></html>`;
const server=createServer((req,res)=>{if(req.url==='/iphone/assets/genesis/vishnu-core.png'){res.writeHead(200,{'Content-Type':'image/png'});res.end(neuralCore)}else if(req.url==='/p208'){res.writeHead(200,{'Content-Type':'text/javascript'});res.end(js)}else{res.writeHead(200,{'Content-Type':'text/html'});res.end(html)}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true});
try{
 for(const size of [[1536,1024],[390,844],[320,720]]){
  const [width,height]=size;const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:1});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('http://127.0.0.1:'+server.address().port+'/');
  await page.evaluate(()=>window.vishnuOpenCommandCenter());
  await page.getByRole('heading',{name:'Command Center'}).waitFor();
  const coreValid=await page.locator('.cc-neural').evaluate(async el=>{await el.decode();return el.naturalWidth>0});
  assert.equal(coreValid,true,'approved neural Core asset must render');
  assert.equal(await page.locator('.cc-primary-card').count(),6,'six quick actions');
  assert.equal(await page.locator('#ccFilters button').count(),9,'nine category filters');
  assert.equal(await page.locator('.cc-command').count()>0,true,'canonical command entries');
  if(screenshots&&width!==320)await page.screenshot({path:screenshots+'/command-center-'+width+'x'+height+'.png',fullPage:true});
  const dims=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,viewport:innerWidth}));
  assert.ok(dims.scroll<=dims.viewport+4,'Horizontal overflow '+JSON.stringify(dims));
  await page.locator('[data-cc-filter="Create"]').click();
  assert.equal(await page.locator('[data-cc-id="new-project"]').count()>0,true);
  await page.locator('[data-cc-filter="All"]').click();
  await page.locator('[data-cc-id="new-project"]').first().click();
  assert.equal(await page.evaluate(()=>window.projectWizardOpened),true,'opened canonical project wizard');
  await page.evaluate(()=>window.vishnuOpenCommandCenter());
  await page.locator('[data-cc-id="new-workspace"]').first().click();
  assert.equal(await page.evaluate(()=>window.workspaceWizardOpened),true,'opened canonical workspace wizard');
  await page.evaluate(()=>window.vishnuOpenCommandCenter());
  await page.locator('#ccCommandInput').fill('open Rudra Health Care workspace');
  await page.locator('#ccCommandInput').press('Enter');
  await page.waitForFunction(()=>window.lastOpenedWorkspace==='w-rudra');
  await page.evaluate(()=>window.vishnuOpenCommandCenter());
  await page.locator('#ccCommandInput').fill('open Hidden Workspace workspace');
  await page.locator('#ccCommandInput').press('Enter');
  await page.waitForFunction(()=>window.lastToast?.includes('library entry is not loaded'));
  await page.evaluate(()=>window.vishnuOpenCommandCenter());
  await page.locator('[data-cc-id="new-automation"]').first().click();
  assert.equal(await page.evaluate(()=>window.workflowComposerOpened),true,'canonical workflow composer');
  await page.evaluate(()=>window.vishnuOpenCommandCenter());
  await page.locator('[data-cc-id="new-note"]').first().click();
  assert.equal(await page.evaluate(()=>window.noteEditorOpened),true,'canonical Knowledge Note editor');
  await page.evaluate(()=>window.vishnuOpenCommandCenter());
  await page.locator('#ccCommandInput').fill('Summarize my day');
  await page.locator('#ccCommandInput').press('Enter');
  await page.waitForFunction(()=>window.promptCalls.length===1);
  assert.match((await page.evaluate(()=>window.promptCalls[0])),/Summarize my day/i);
  assert.equal(await page.evaluate(()=>window.chatViewOpened),1,'Uses the canonical conversation bridge without resetting context');
  await page.evaluate(()=>window.vishnuOpenCommandCenter());
  assert.equal(await page.locator('.cc-panel-list').last().innerText().then(x=>x.includes('Summarize my day')),true,'recent history real result');
  await page.locator('#ccCommandInput').fill('create a project called Patient CRM');
  await page.locator('#ccCommandInput').press('Enter');
  await page.waitForFunction(()=>window.projectWizardOpened&&document.querySelector('[name="name"]')?.value==='Patient CRM');
  await page.keyboard.press('Control+Shift+P');
  await page.getByRole('heading',{name:'Command Center'}).waitFor();
  await page.locator('#ccCommandInput').fill('<img src=x onerror=alert(1)>');
  assert.equal(await page.locator('img[onerror]').count(),0,'XSS payload escaped');
  const observed=await page.evaluate(()=>({isActive:document.body.classList.contains('cc-page-mode'),history:window.historySaved.map(x=>x.id),errors:window.promptCalls.length}));
  assert.equal(observed.isActive,true);
  assert.ok(observed.history.includes('new-project')&&observed.history.includes('summarize-day'));
  assert.deepEqual(errors,[],errors.join('\n'));
  await page.close();
 }
 console.log('P2-08 Chromium: passed desktop, mobile, 320px width, 9 filters, 6 cards, canonical forms, NL routing, keyboard, escaped input, device history.');
}finally{await browser.close();await new Promise(done=>server.close(done))}
