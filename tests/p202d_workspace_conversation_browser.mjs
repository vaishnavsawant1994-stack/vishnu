import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdir, readFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const root=new URL('../',import.meta.url);
const js=await readFile(new URL('pwa/p202d-workspace-conversation.js',root),'utf8');
const css=await readFile(new URL('pwa/p202d-workspace-conversation.css',root),'utf8');
const pages=[];
const screenshotDir=process.env.P202D_SCREENSHOT_DIR;
if(screenshotDir)await mkdir(screenshotDir,{recursive:true});
let created=0,chats=[],sent=[];
const project={id:'project-one',name:'Verified Project',status:'active',task_count:4,done_count:2,file_count:1};
const workspace={id:'workspace-one',name:'Product Development',description:'Canonical Workspace browser fixture',status:'active'};
const summary={workspace,projects:[project],counts:{projects:1,active_tasks:2,files:1,members:null,agents:null}};
const html='<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/client.css"></head>'+
'<body><div id="view"></div><div id="error"></div><script src="/client.js"></script><script>'+
'window.errors=[]; const api=async(path,options={})=>{const res=await fetch("/iphone/api"+path,{method:options.method||"GET",headers:{"Content-Type":"application/json"},body:options.body});const data=await res.json();if(!res.ok)throw Error(data.detail||"Request failed");return data};'+
'window.vishnuChatBridge={api,showToast:msg=>window.errors.push(msg),openModule:async()=>{},openTodayScreen:async()=>{}};'+
'window.vishnuP202D.mount(document.querySelector("#view"),{id:"workspace-one",name:"Product Development",description:"Canonical Workspace browser fixture"},window.vishnuChatBridge,'+
'{library:async()=>{},overview:async()=>{},studio:async()=>{},settings:async()=>{},agents:async()=>{},assets:async()=>{},linkProject:async()=>{}}).catch(err=>document.querySelector("#error").textContent=err.message);'+
'</script></body></html>';

const server=createServer(async(req,res)=>{
 const url=new URL(req.url,'http://localhost');
 const send=(status,data,type='application/json')=>{res.writeHead(status,{'content-type':type});res.end(type==='application/json'?JSON.stringify(data):data)};
 if(url.pathname==='/')return send(200,html,'text/html');
 if(url.pathname==='/client.js')return send(200,js,'application/javascript');
 if(url.pathname==='/client.css')return send(200,css,'text/css');
 let body={};if(req.method==='POST'){let t='';for await(const part of req)t+=part.toString();body=JSON.parse(t||'{}')}
 const prefix='/iphone/api/workspaces/workspace-one';
 if(url.pathname===prefix+'/summary')return send(200,summary);
 if(url.pathname===prefix+'/conversations'&&req.method==='GET')return send(200,{workspace_id:workspace.id,conversations:chats.map(c=>c.conversation)});
 if(url.pathname===prefix+'/conversations'&&req.method==='POST'){
   const ident='workspace-thread-'+(++created),entry={conversation:{id:ident,title:body.title||'New Workspace Conversation',context:{workspace_id:workspace.id,conversation_kind:'workspace',owner_id:'owner'}},events:[]};
   chats.unshift(entry);return send(201,{workspace_id:workspace.id,conversation:entry.conversation});
 }
 if(url.pathname.startsWith(prefix+'/conversations/')&&req.method==='GET'){
   const id=url.pathname.slice((prefix+'/conversations/').length),entry=chats.find(x=>x.conversation.id===id);
   return entry?send(200,entry):send(404,{detail:'Unknown scoped thread'});
 }
 if(url.pathname==='/iphone/api/voice/turn'&&req.method==='POST'){
   if(body.workspace_id!==workspace.id||!chats.some(x=>x.conversation.id===body.conversation_id))return send(403,{detail:'Invalid context'});
   sent.push(body);
   const item=chats.find(x=>x.conversation.id===body.conversation_id);
   item.events.push({kind:'user_message',payload:{text:'Owner request: '+body.transcript},created_at:new Date().toISOString()});
   item.events.push({kind:'assistant_message',payload:{text:'Verified Workspace reply'},created_at:new Date().toISOString()});
   return send(200,{status:'completed',conversation_id:body.conversation_id,reply:'Verified Workspace reply'});
 }
 return send(404,{detail:'No mock endpoint'});
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const port=server.address().port,browser=await chromium.launch({headless:true});
try{
 for(const width of [390,1440]){
  created=0;chats=[];sent=[];
  const mobile=width<500,page=await browser.newPage({viewport:{width,height:mobile?844:1000},deviceScaleFactor:mobile?2:1,isMobile:mobile,hasTouch:mobile});
  pages.push(page);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:'+port+'/');
  await page.locator('.p202d-root').waitFor();
  await page.getByText('Product Development').first().waitFor();
  if(!mobile)await page.getByText('Verified Project').first().waitFor();
  await page.waitForFunction(()=>document.querySelector('.p202d-stat strong')?.textContent==='1');
  assert.ok((await page.locator('.p202d-stat strong').allTextContents()).includes('1'),'Project count is based on server data');
  assert.equal(await page.getByText('12 Members').count(),0,'Do not inject fake member counts');
  if(mobile){
    await page.getByRole('button',{name:'Chats ▾'}).click();
    await page.getByRole('button',{name:'＋ New Workspace Chat'}).click();
    await page.locator('.p202d-tabs button:visible').count().then(count=>assert.equal(count,5,'mobile has five Workspace tabs'));
    const geometry=await page.evaluate(()=>({viewport:innerWidth,scroll:document.documentElement.scrollWidth}));
    assert.ok(geometry.scroll<=geometry.viewport+3,JSON.stringify(geometry));
  }else{
    await page.locator('.p202d-hero-actions button').first().click();
    assert.equal(await page.locator('.p202d-tabs button:visible').count(),10);
  }
  await page.locator('[data-p202d-input]').focus();
  await page.locator('[data-p202d-input]').fill('Show me authorized Workspace progress');
  await page.locator('[data-p202d-send]').click();
  await page.getByText('Verified Workspace reply').waitFor();
  assert.equal(sent.length,1);
  assert.equal(sent[0].workspace_id,workspace.id);
  assert.equal(sent[0].transcript,'Show me authorized Workspace progress');
  assert.equal(chats.length,1);
  assert.deepEqual(errors,[],'P2-02D must not cause runtime page errors');
  if(screenshotDir)await page.screenshot({path:screenshotDir+'/workspace-chat-'+width+'.png',fullPage:false});
  await page.close();
 }
}finally{await browser.close();await new Promise(resolve=>server.close(resolve))}
console.log('P2-02D desktop/mobile mock runtime, owner Project summary, conversation creation and canonical AI transport passed.');
