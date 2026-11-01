import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';

const js=await readFile(new URL('../pwa/p205-conversation-history.js',import.meta.url),'utf8');
const css=await readFile(new URL('../pwa/p205-conversation-history.css',import.meta.url),'utf8');
const target=process.env.P205_SCREENSHOT_DIR;
if(target)await mkdir(target,{recursive:true});
const fixture=[
 {id:'personal-1',title:'Verified Personal Conversation',updated_at:'2026-10-22T08:00:00Z',created_at:'2026-10-22T07:40:00Z',context:{},events:[{kind:'user_message',created_at:'2026-10-22T07:40:00Z',payload:{text:'Real persisted text from fixture'}}],closed_at:null},
 {id:'work-1',title:'Verified Work Plan',updated_at:'2026-10-21T08:00:00Z',created_at:'2026-10-21T07:00:00Z',context:{conversation_kind:'work'},events:[],closed_at:null},
 {id:'project-1',title:'Verified Project Thread',updated_at:'2026-10-20T08:00:00Z',created_at:'2026-10-20T07:00:00Z',context:{conversation_kind:'project',project_id:'project-id'},events:[],closed_at:null}
];
let records=JSON.parse(JSON.stringify(fixture)),events=[],opened=[],messageTurns=0;
const html='<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/css"></head><body><aside id="p205Root" class="hidden" role="dialog" aria-hidden="true"></aside><dialog id="p205Dialog" class="p205-dialog"><h2 id="p205ModalTitle"></h2><p id="p205ModalText"></p><div id="p205Choices" class="p205-dialog-options"></div></dialog><script>'+
'window.vishnuHistoryBridge={api:async(path,options={})=>{const response=await fetch("/iphone/api"+path,{method:options.method||"GET",headers:{"content-type":"application/json",...(options.headers||{})},body:options.body});let body=await response.json();if(!response.ok)throw Error(body.detail||"API error");return body},owner:()=>"Fixture Owner",confirm:async()=>true,navigate:x=>window.navCalls.push(x),openConversation:id=>window.navCalls.push("open:"+id),createTask:()=>window.navCalls.push("task"),continueVoice:id=>window.navCalls.push("voice:"+id),onClose:()=>{}};window.navCalls=[];'+
'</script><script src="/js"></script><script>window.vishnuP205.open();</script></body></html>';
const server=createServer(async(req,res)=>{
 const u=new URL(req.url,'http://test.local'),path=u.pathname;
 const out=(object,status=200,type='application/json')=>{res.writeHead(status,{'content-type':type});res.end(type==='application/json'?JSON.stringify(object):object)};
 if(path==='/')return out(html,200,'text/html');
 if(path==='/js')return out(js,200,'application/javascript');
 if(path==='/css')return out(css,200,'text/css');
 let body={};if(['POST','PATCH'].includes(req.method)){let str='';for await(const chunk of req)str+=chunk;body=JSON.parse(str||'{}')}
 events.push(req.method+' '+path);
 if(path==='/iphone/api/projects'&&req.method==='GET')return out({projects:[{id:'project-id',name:'Verified Project'}]});
 if(path==='/iphone/api/workspaces'&&req.method==='GET')return out({workspaces:[{id:'ws-id',name:'Verified Workspace'}]});
 if(path==='/iphone/api/conversations/history/search'){
  let filtered=records.filter(x=>u.searchParams.get('status')==='archived'?Boolean(x.closed_at):!x.closed_at);
  const kind=u.searchParams.get('kind')||'all';
  if(kind!=='all')filtered=filtered.filter(x=>(x.context.conversation_kind||'personal')===kind);
  if(u.searchParams.get('pinned')==='true')filtered=filtered.filter(x=>x.context.history_pinned);
  const q=(u.searchParams.get('q')||'').toLowerCase();
  if(q)filtered=filtered.filter(x=>x.title.toLowerCase().includes(q)||x.events.some(e=>e.payload?.text?.toLowerCase().includes(q)));
  filtered=filtered.map(x=>({...x,preview:x.events.at(-1)?.payload?.text||'',event_count:x.events.length})).sort((a,b)=>b.updated_at.localeCompare(a.updated_at));
  return out({conversations:filtered,next_cursor:null,has_more:false});
 }
 const found=records.find(x=>path.includes('/conversations/'+x.id+'/'));
 if(found){
  if(path.endsWith('/history-detail'))return out({conversation:found,events:found.events});
  if(path.endsWith('/related'))return out({projects:found.context.project_id?[{id:'project-id',name:'Verified Project'}]:[],workspaces:[],tasks:[],files:[]});
  if(path.endsWith('/metadata')&&req.method==='PATCH'){if(body.title!==undefined)found.title=body.title;if(body.tags!==undefined)found.context.history_tags=body.tags;if(body.pinned!==undefined)found.context.history_pinned=body.pinned;if(body.summary!==undefined)found.context.history_summary=body.summary;return out({conversation:found})}
  if(path.endsWith('/archive')&&req.method==='POST'){found.closed_at='2026-10-22T08:00:00Z';return out({status:'archived'})}
  if(path.endsWith('/restore')&&req.method==='POST'){found.closed_at=null;return out({conversation:found,status:'restored'})}
  if(path.endsWith('/organize')&&req.method==='POST'){found.context={...found.context,conversation_kind:body.kind,project_id:body.kind==='project'?body.target_id:undefined,workspace_id:body.kind==='workspace'?body.target_id:undefined};return out({conversation:found})}
  if(path.endsWith('/export'))return out({conversation:found,events:found.events});
 }
 if(path==='/iphone/api/voice/turn'){messageTurns++;const item=records.find(x=>x.id===body.conversation_id);if(!item)return out({detail:'Not found'},404);item.events.push({kind:'user_message',payload:{text:body.transcript}},{kind:'assistant_message',payload:{text:'Canonical AI response'}});return out({status:'completed',conversation_id:item.id,reply:'Canonical AI response'})}
 if(path==='/iphone/api/conversations'&&req.method==='POST'){const id='new-'+records.length;const item={id,title:body.title,context:body.context_type==='work'?{conversation_kind:'work'}:{},events:[],closed_at:null,created_at:new Date().toISOString(),updated_at:new Date().toISOString()};records.push(item);return out({conversation:item})}
 if(path.startsWith('/iphone/api/conversations/')&&req.method==='DELETE'){const key=path.split('/').at(-1);records=records.filter(x=>x.id!==key);return out({status:'deleted'})}
 return out({detail:'No fixture handler: '+path},404);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true});
try{
 for(const width of [1440,390]){
  records=JSON.parse(JSON.stringify(fixture));events=[];opened=[];messageTurns=0;
  const page=await browser.newPage({viewport:{width,height:width===390?844:900},isMobile:width===390,deviceScaleFactor:width===390?2:1,hasTouch:width===390});
  const errs=[];page.on('pageerror',e=>errs.push(e.message));page.on('dialog',d=>d.accept());
  await page.goto('http://127.0.0.1:'+server.address().port+'/');
  await page.getByText('Verified Personal Conversation').waitFor();
  assert.equal(await page.locator('.p205-row').count(),3);
  assert.ok(!await page.getByText('UI Design for Phase 2 Home').count(),'No screenshot example data');
  await page.locator('[data-h-select="personal-1"]').click();
  await page.locator('.p205-detail-content').getByText('Real persisted text from fixture').waitFor();
  await page.locator('[data-h-tab="details"]').click();
  await page.getByText('Personal',{exact:true}).first().waitFor();
  await page.locator('[data-h-tab="chat"]').click();
  await page.locator('#p205Message').fill('Continue canonical thread');
  await page.locator('#p205Form').evaluate(f=>f.requestSubmit());
  await page.locator('.p205-detail-content').getByText('Canonical AI response').waitFor();
  assert.equal(messageTurns,1);
  if(width===390){
   await page.locator('[data-h-action="back"]').click();
   await page.waitForFunction(()=>!document.querySelector('#p205Detail')?.classList.contains('mobile-open'));
  }
  await page.locator('[data-h-action="pin:personal-1"]').first().click();
  const pinnedFilter=page.locator('[data-h-filter="pinned"]');
  if(width===390){await pinnedFilter.focus();await pinnedFilter.press('Enter')}
  else await pinnedFilter.click();
  await page.locator('[data-h-select="personal-1"]').waitFor();
  assert.equal(await page.locator('.p205-row').count(),1);
  await page.locator('[data-h-filter="archived"]').click();
  await page.getByText('No matching conversations').waitFor();
  await page.locator('[data-h-filter="all"]').click();
  await page.locator('#p205Search').fill('Verified Work Plan');
  await page.waitForTimeout(330);
  assert.equal(await page.locator('.p205-row').count(),1);
  await page.locator('#p205Search').fill('');
  await page.waitForTimeout(330);
  assert.equal(await page.locator('.p205-row').count(),3);
  if(width===390){
   await page.locator('[data-h-select="work-1"]').click();
   await page.locator('#p205Detail.mobile-open').waitFor();
   await page.locator('[data-h-action="back"]').click();
   assert.equal(await page.locator('#p205Detail.mobile-open').count(),0);
   const dims=await page.evaluate(()=>({w:innerWidth,scroll:document.documentElement.scrollWidth}));
   assert.ok(dims.scroll<=dims.w+2,'Mobile horizontal overflow: '+JSON.stringify(dims));
  }
  assert.deepEqual(errs,[],errs.join(' | '));
  if(target)await page.screenshot({path:target+'/history-'+width+'.png',fullPage:false});
  await page.close();
 }
 console.log('P2-05 History: canonical list/detail, original IDs, send, pin, filters, search, mobile navigation and no demo records passed');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve))}
