import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';

const js=await readFile(new URL('../pwa/p204-live-voice.js',import.meta.url),'utf8');
const css=await readFile(new URL('../pwa/p204-live-voice.css',import.meta.url),'utf8');
const dir=process.env.P204_SCREENSHOT_DIR;
if(dir)await mkdir(dir,{recursive:true});
const workspace={id:'workspace-one',name:'Product Development'},project={id:'project-one',name:'Vishnu UI'};
let voice=[],reads=[],created=0;
const active={id:null,context:null};
const html='<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/css"></head><body><aside id="p204Root" class="hidden" aria-hidden="true"></aside><dialog id="p204Dialog" class="p204-dialog"><h2 id="p204DialogTitle"></h2><p id="p204DialogInfo"></p><div id="p204DialogButtons" class="p204-dialog-options"></div></dialog><script>'+
'window.moves=[];window.vishnuVoiceBridge={api:async(path,options={})=>{const r=await fetch("/iphone/api"+path,{method:options.method||"GET",headers:{"content-type":"application/json",...(options.headers||{})},body:options.body});const v=await r.json();if(!r.ok){const e=new Error(v.detail||"Unsuccessful request");e.status=r.status;throw e}return v},onClose:()=>window.moves.push("closed"),navigate:x=>window.moves.push(x)};'+
'</script><script src="/js"></script><script>window.vishnuP204.open();</script></body></html>';
const server=createServer(async(req,res)=>{
 const url=new URL(req.url,'http://localhost');
 function out(value,status=200,type='application/json'){res.writeHead(status,{'content-type':type});res.end(type==='application/json'?JSON.stringify(value):value)}
 if(url.pathname==='/')return out(html,200,'text/html');
 if(url.pathname==='/js')return out(js,200,'application/javascript');
 if(url.pathname==='/css')return out(css,200,'text/css');
 reads.push(req.method+' '+url.pathname);
 let body={};if(req.method==='POST'){let raw='';for await(const part of req)raw+=part.toString();body=JSON.parse(raw||'{}')}
 if(url.pathname==='/iphone/api/work/attention')return out({items:[]});
 if(url.pathname==='/iphone/api/everyday/timeline')return out({items:[{id:'today-item',title:'Verified Today event',status:'scheduled'}]});
 if(url.pathname==='/iphone/api/projects'&&req.method==='GET')return out({projects:[project]});
 if(url.pathname==='/iphone/api/workspaces'&&req.method==='GET')return out({workspaces:[workspace]});
 const path=url.pathname;
 const isScoped=path.endsWith('/conversations')&&req.method==='POST';
 if((path==='/iphone/api/conversations'||isScoped)&&req.method==='POST'){
  created++;const ctx=path.includes('/projects/')?{conversation_kind:'project',project_id:project.id}:path.includes('/workspaces/')?{conversation_kind:'workspace',workspace_id:workspace.id}:body.context_type==='work'?{conversation_kind:'work'}:{};
  active.id='voice-'+created;active.context=ctx;voice=[];
  return out({conversation:{id:active.id,context:ctx}},201);
 }
 if(path.endsWith('/conversations/'+active.id)||path==='/iphone/api/conversations/'+active.id){
  return out({conversation:{id:active.id,context:active.context},events:voice});
 }
 if(path==='/iphone/api/voice/turn'&&req.method==='POST'){
  if(body.conversation_id!==active.id)return out({detail:'Wrong canonical conversation'},409);
  if(active.context?.workspace_id&&body.workspace_id!==active.context.workspace_id)return out({detail:'Wrong Workspace'},404);
  voice.push({kind:'user_message',payload:{text:body.transcript}});
  voice.push({kind:'assistant_message',payload:{text:'Verified canonical response'}});
  return out({status:'completed',conversation_id:active.id,reply:'Verified canonical response'});
 }
 if(path==='/iphone/api/voice/barge'||path==='/iphone/api/voice/operation/cancel')return out({ok:true});
 return out({detail:'No handler: '+path},404);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true});
try{
 for(const width of [390,1440]){
  reads=[];voice=[];created=0;active.id=null;
  const page=await browser.newPage({viewport:{width,height:width<500?844:980},deviceScaleFactor:width<500?2:1,isMobile:width<500,hasTouch:width<500});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>d.accept());
  await page.addInitScript(()=>{
   window.__micRequests=0;window.__micStops=0;
   Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async()=>{
    window.__micRequests++;const track={enabled:true,stop:()=>window.__micStops++,addEventListener:()=>{}};
    return {getTracks:()=>[track],getAudioTracks:()=>[track]};
   },enumerateDevices:async()=>[],getDisplayMedia:async()=>{throw Error('Unavailable in fixture')}}});
   window.SpeechRecognition=class{start(){window.__rec=this;queueMicrotask(()=>this.onstart?.())}stop(){this.onend?.()}};
  });
  await page.goto('http://127.0.0.1:'+server.address().port+'/');
  await page.locator('.p204-shell').waitFor();
  assert.equal(await page.locator('#p204Status').textContent(),'Voice is ready');
  assert.equal(await page.evaluate(()=>window.__micRequests),0,'Opening voice must not capture audio');
  await page.locator('#p204Mode').click();
  assert.ok(await page.locator('#p204Root').evaluate(n=>n.classList.contains('p204-focus')));
  await page.locator('#p204Mode').click();
  await page.locator('#p204Start').click();
  await page.getByText('Vishnu is listening…').waitFor();
  assert.equal(await page.evaluate(()=>window.__micRequests),1);
  await page.locator('#p204Mute').click();
  await page.getByText('Microphone muted').waitFor();
  await page.locator('#p204Mute').click();
  await page.getByText('Voice is ready').waitFor();
  await page.locator('#p204Text').fill('Hello from canonical voice UI');
  await page.locator('#p204Form').evaluate(form=>form.requestSubmit());
  await page.getByText('Verified canonical response').waitFor();
  assert.equal(created,1);
  assert.ok(reads.includes('POST /iphone/api/voice/turn'));
  await page.locator('[data-p204="context:workspace"]').click();
  await page.getByRole('button',{name:workspace.name}).click();
  await page.locator('#p204Text').fill('Workspace status');
  await page.locator('#p204Form').evaluate(form=>form.requestSubmit());
  await page.getByText('Verified canonical response').waitFor();
  assert.equal(created,2);
  assert.equal(active.context.workspace_id,workspace.id);
  await page.locator('[data-p204-tab="context"]').click();
  await page.getByText('Scope: '+workspace.name).waitFor();
  if(width<500){
    const overflow=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
    assert.ok(overflow.scroll<=overflow.width+3,'mobile overflow '+JSON.stringify(overflow));
  }
  if(dir)await page.screenshot({path:dir+'/live-voice-'+width+'.png',fullPage:false});
  await page.locator('#p204End').click();
  await page.locator('#p204Root.hidden').waitFor();
  assert.ok(await page.evaluate(()=>window.__micStops)>0,'End releases microphone tracks');
  assert.deepEqual(errors,[],errors.join(' | '));
  await page.close();
 }
}finally{await browser.close();await new Promise(resolve=>server.close(resolve))}
console.log('P2-04 Live Voice: no autoplay, microphone/mute cleanup, Focus mode, canonical text, Workspace scoping, End and mobile passed.');
