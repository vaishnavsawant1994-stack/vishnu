import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';

const source=await readFile(new URL('../pwa/global-search.js',import.meta.url),'utf8');
const style=await readFile(new URL('../pwa/global-search.css',import.meta.url),'utf8');
const screenshot=process.env.P206_SCREENSHOT_DIR;
if(screenshot)await mkdir(screenshot,{recursive:true});
const records=[
 {type:'conversations',id:'conv-1',title:'API Integration Plan',excerpt:'Real persisted API conversation',updated_at:'2026-10-22T08:00:00Z',source:'continuity',project_id:'',workspace_id:'',tags:['API']},
 {type:'projects',id:'proj-1',title:'API Development',excerpt:'Integrate API services',updated_at:'2026-10-22T07:00:00Z',source:'canonical_project',project_id:'proj-1',workspace_id:'',status:'in_progress'},
 {type:'files',id:'file-1',title:'API blueprint.txt',excerpt:'Indexed file',updated_at:'2026-10-21T09:00:00Z',source:'project_file',project_id:'proj-1',workspace_id:'',status:'indexed'},
 {type:'work',id:'task-1',title:'API checklist',excerpt:'Canonical project task',updated_at:'2026-10-20T09:00:00Z',source:'canonical_project_task',project_id:'proj-1',workspace_id:'',status:'planned'},
 {type:'knowledge',id:'note-1',title:'API notes',excerpt:'Tested Knowledge',updated_at:'2026-10-19T09:00:00Z',source:'knowledge_document',project_id:'',workspace_id:''},
 {type:'workspaces',id:'workspace-1',title:'API Workspace',excerpt:'Workspace description',updated_at:'2026-10-18T09:00:00Z',source:'canonical_workspace',project_id:'',workspace_id:'workspace-1'},
 {type:'agents',id:'agent-1',title:'API Research Agent',excerpt:'Trusted template',updated_at:'2026-10-17T09:00:00Z',source:'agent_workforce',project_id:'',workspace_id:''}
];
const categories=['conversations','workspaces','projects','files','work','agents','knowledge','memory'];
const html='<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+style+'</style></head><body><header>VISHNU</header><div id="modulePanel" class="open"><div class="module-head"><span id="moduleTitle"></span><span id="moduleText"></span><span id="moduleMetric"></span></div><div id="moduleBody" class="module-body"></div></div><script>'+
'window.navs=[];window.openModule=async name=>{window.navs.push(name)};window.openConversation=async id=>window.navs.push("conversation:"+id);window.openProject=async id=>window.navs.push("project:"+id);window.showToast=msg=>window.navs.push("toast:"+msg);window.api=async(path,options={})=>{const reply=await fetch("/iphone/api"+path,{method:options.method||"GET",headers:{"content-type":"application/json"},body:options.body});const payload=await reply.json();if(!reply.ok)throw Error(payload.detail||"Error");return payload};'+
'</script><script src="/js"></script><script>window.openModule("search")</script></body></html>';
const calls=[];let archived=false;
const server=createServer(async(req,res)=>{
 const path=new URL(req.url,'http://test.local');
 const send=(obj,status=200,type='application/json')=>{res.writeHead(status,{'content-type':type});res.end(type==='application/json'?JSON.stringify(obj):obj)};
 if(path.pathname==='/')return send(html,200,'text/html');
 if(path.pathname==='/js')return send(source,200,'application/javascript');
 calls.push(path.pathname+'?'+path.searchParams.toString());
 if(path.pathname==='/iphone/api/search'){
  const q=(path.searchParams.get('q')||'').toLowerCase(),cat=path.searchParams.get('category')||'all';
  const items=records.filter(x=>(!archived||x.id!=='conv-1')&&(x.title+' '+x.excerpt).toLowerCase().includes(q));
  const counts={all:items.length};for(const k of categories)counts[k]=items.filter(x=>x.type===k).length;
  const selected=cat==='all'?items:items.filter(x=>x.type===cat);
  const offset=Number(path.searchParams.get('offset')||0),limit=Number(path.searchParams.get('limit')||25);
  return send({results:selected.slice(offset,offset+limit),counts,
   coverage:Object.fromEntries(categories.map(x=>[x,x==='memory'?'disabled':'available'])),
   next_offset:offset+limit<selected.length?offset+limit:null});
 }
 if(path.pathname.startsWith('/iphone/api/search/result/')){
  const id=path.pathname.split('/').at(-1),x=records.find(r=>r.id===id);
  if(!x)return send({detail:'Not found'},404);
  return send({result:x,preview:x.type==='conversations'?[{role:'user_message',text:'API original user message'},{role:'assistant_message',text:'Verified canonical reply'}]:[],related:x.type==='projects'?[{type:'work',id:'task-1',title:'API checklist',project_id:'proj-1'}]:[]});
 }
 if(path.pathname==='/iphone/api/workspaces')return send({workspaces:[{id:'workspace-1',name:'API Workspace'}]});
 if(path.pathname==='/iphone/api/projects')return send({projects:[{id:'proj-1',name:'API Development'}]});
 if(req.method==='POST'&&path.pathname==='/iphone/api/voice/turn')return send({status:'completed',reply:'Verified AI summary'});
 if(req.method==='POST'&&path.pathname==='/iphone/api/conversations/conv-1/organize')return send({conversation:{id:'conv-1'}});
 if(req.method==='GET'&&path.pathname==='/iphone/api/conversations/conv-1/export')return send({conversation:{id:'conv-1',title:'API Integration Plan'},events:[{kind:'user_message',payload:{text:'Verified canonical record'}}]});
 if(req.method==='POST'&&path.pathname==='/iphone/api/conversations/conv-1/archive'){archived=true;return send({ok:true,conversation_id:'conv-1',status:'archived'})}
 if(req.method==='DELETE'&&path.pathname==='/iphone/api/conversations/conv-1')return send({ok:true,conversation_id:'conv-1',status:'deleted'});
 if(req.method==='POST'&&path.pathname==='/iphone/api/projects/proj-1/tasks')return send({task:{id:'task-created'}},201);
 return send({detail:'Not found'},404);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true});
try{
 for(const width of [1536,390]){
  archived=false;
  const page=await browser.newPage({viewport:{width,height:width===390?844:1024},deviceScaleFactor:width===390?2:1,isMobile:width===390,hasTouch:width===390});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept('1'));
  await page.goto('http://127.0.0.1:'+server.address().port+'/');
  await page.getByRole('heading',{name:'Global Search'}).waitFor();
  await page.locator('#globalSearchQuery').fill('API');
  await page.locator('#gsForm').evaluate(f=>f.requestSubmit());
  await page.locator('.gs-result-main').first().waitFor();
  assert.equal(await page.locator('.gs-result-main').count(),7);
  await page.locator('[data-gs-category="projects"]').click();
  await page.locator('.gs-result-main').first().waitFor();
  assert.equal(await page.locator('.gs-result-main').count(),1);
  await page.locator('[data-gs-category="all"]').click();
  await page.locator('[data-gs-select="conversations"]').click();
  await page.getByText('Verified canonical reply').waitFor();
  if(width===1536&&screenshot)await page.screenshot({path:screenshot+'/search-'+width+'.png',fullPage:false});
  await page.locator('[data-gs-action="summarize"]').click();
  await page.getByText('Verified AI summary').waitFor();
  await page.locator('.gs-result-more summary').click();
  await page.locator('[data-gs-action="organize"]').click();
  await page.getByText('The original conversation is now linked to the selected Project.').waitFor();
  await page.locator('.gs-result-more summary').click();
  await page.locator('[data-gs-action="workspace-organize"]').click();
  await page.getByText('Original conversation successfully moved to Workspace API Workspace.').waitFor();
  await page.locator('.gs-result-more summary').click();
  const [download]=await Promise.all([page.waitForEvent('download'),page.locator('[data-gs-action="export"]').click()]);
  assert.match(download.suggestedFilename(),/vishnu-conversation-conv-1.*json/);
  if(width===390){
   await page.locator('#gsDetail.mobile-open').waitFor();
   await page.locator('[data-gs-action="back"]').click();
   assert.equal(await page.locator('#gsDetail.mobile-open').count(),0);
   await page.locator('[data-gs-action="filters"]').click();
   assert.equal(await page.locator('#gsAdvanced.expanded').count(),1);
   const w=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
   assert.ok(w.scroll<=w.width+3,JSON.stringify(w));
   if(screenshot)await page.screenshot({path:screenshot+'/search-'+width+'.png',fullPage:false});
   await page.locator('[data-gs-select="conversations"]').click();
  }
  if(!await page.locator('.gs-result-more').evaluate(el=>el.open))await page.locator('.gs-result-more summary').click();
  await page.locator('[data-gs-action="archive"]').click();
  await page.getByText('Conversation archived. Open Conversation History to restore it.').waitFor();
  assert.equal(await page.locator('[data-gs-select="conversations"]').count(),0);
  await page.locator('[data-gs-action="clear"]').click();
  assert.equal(await page.locator('.gs-result-main').count(),0);
  assert.deepEqual(errors,[],errors.join('\n'));
  await page.close();
 }
 assert.ok(calls.some(x=>x.startsWith('/iphone/api/search?q=API')));
 console.log('P2-06 Global Search browser: actual typed query, categories, real scoped preview, mobile detail/filters and clear passed.');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve))}
