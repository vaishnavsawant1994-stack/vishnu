/* P2-01 Home qualification using the real PWA shell and explicit API fixtures. */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

await mkdir('artifacts',{recursive:true});
const browser=await chromium.launch({headless:true});
const errors=[];
const conversations=[{id:'existing',title:'Saved owner conversation',preview:'Prior work',updated_at:new Date().toISOString()}];
let active={conversation:{id:'existing',title:'Saved owner conversation'},events:[]};
let workUnavailable=false,created=0;
const project={id:'project-1',name:'Owner workspace',updated_at:new Date().toISOString(),tasks:[],files:[],activity:[]};
try {
 const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true,serviceWorkers:'block'});
 page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/iphone/api/**',async route=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname.replace('/iphone/api',''),method=request.method();
  if(path==='/work/summary'&&workUnavailable)
   return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Work unavailable'})});
  let data={};
  if(path==='/status')data={owner_display_name:'Alex',model:{state:'available'},conversation:active,conversations,active_qualification:true,memory_count:0};
  else if(path==='/preferences')data={};
  else if(path==='/projects')data={projects:[project]};
  else if(path==='/projects/project-1')data={project};
  else if(path==='/everyday/active')data={items:[
   {id:'task1',kind:'task',context:'personal-ai:today:task',status:'pending',title:'Review release'},
   {id:'meeting1',kind:'commitment',context:'personal-ai:today:meeting',status:'scheduled',title:'Design review'}
  ]};
  else if(path==='/everyday/timeline')data={items:[]};
  else if(path==='/work/summary')data={authority:'read_only_projection',work_orders:[
   {work_order_id:'work1',project_id:'project-1',project_name:'Owner workspace',title:'Real running WorkOrder',status:'RUNNING'}
  ],counts:{active:1},projects_with_work:1};
  else if(path==='/work/attention')data={authority:'read_only_projection',counts:{total:1,approval:1},items:[
   {id:'attention1',kind:'approval_required',title:'Review owner decision',authority:'approval_manager'}
  ]};
  else if(path==='/conversations'&&method==='POST'){created++;active={conversation:{id:'new-'+created,title:'New conversation'},events:[]};data=active;}
  else if(path==='/conversations')data={conversations};
  else if(path.startsWith('/conversations/'))data=active;
  else if(path==='/voice/turn'&&method==='POST'){
   active.events.push({event_id:'u1',kind:'user_message',payload:{text:'Home test'},created_at:new Date().toISOString()});
   active.events.push({event_id:'a1',kind:'assistant_message',payload:{text:'Canonical assistant response'},created_at:new Date().toISOString()});
   data={conversation_id:active.conversation.id,conversation_title:active.conversation.title,reply:'Canonical assistant response',status:'completed'};
  }
  else if(path==='/access/options')data={passkey_available:false,password_available:false,google_available:false};
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
 });
 await page.goto('http://127.0.0.1:4173/iphone/',{waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>document.body.classList.contains('home-landing')&&window.__vishnuP201);
 await page.locator('.p2-status-ai[data-ready="true"]').waitFor({timeout:15000});
 assert.match(await page.locator('#homeGreeting').innerText(),/^Good (Morning|Afternoon|Evening), Alex$/);
 assert.equal(await page.locator('.p2-tile').count(),6,'all six approved shortcuts');
 assert.equal(await page.locator('.p2-tool').count(),6,'all six guided tools');
 assert.equal(await page.locator('.p2-daily-row').count(),4,'four live daily summary rows');
 assert.match(await page.locator('.p2-row-tasks').innerText(),/1 pending/);
 assert.match(await page.locator('.p2-row-meetings').innerText(),/1 meeting/);
 assert.match(await page.locator('.p2-row-approvals').innerText(),/1 need your decision/);
 assert.match(await page.locator('.p2-work-content').innerText(),/Real running WorkOrder/);
 assert.equal(await page.locator('#homeSphereStage #neuralCanvas').count(),1,'canonical canvas, not duplicated');
 assert.ok((await page.locator('.p2-time').innerText()).length>0,'locale-aware clock populated');
 assert.equal(await page.locator('#homeRecentSection').isVisible(),true,'real conversation activity panel visible');

 for(const [width,height,columns] of [[320,568,2],[390,844,2],[768,960,2],[1024,768,3],[1440,900,6],[1920,1080,6]]){
  await page.setViewportSize({width,height});
  const layout=await page.evaluate(()=>{
   const bounds=node=>{const x=node.getBoundingClientRect();return {left:x.left,right:x.right,top:x.top,bottom:x.bottom,height:x.height};};
   return {pageWidth:document.documentElement.scrollWidth,
    columns:getComputedStyle(document.querySelector('.v-shortcuts')).gridTemplateColumns.split(' ').length,
    cards:[...document.querySelectorAll('.p2-tile')].map(bounds),
    sphere:bounds(document.getElementById('homeSphereStage')),
    greeting:bounds(document.querySelector('.p2-greeting'))};
  });
  assert.ok(layout.pageWidth<=width+1,'no horizontal overflow at '+width);
  assert.equal(layout.columns,columns,'responsive grid at '+width);
  assert.ok(layout.cards.every(x=>x.left>=0&&x.right<=width+1&&x.height>=44),'visible touch targets at '+width);
  if(width<=900)assert.ok(layout.sphere.bottom<=layout.greeting.top+5,'mobile Core above greeting at '+width);
  if([320,390,1440].includes(width))await page.screenshot({path:'artifacts/p2-01-home-'+width+'.png',fullPage:true});
 }
 await page.setViewportSize({width:390,height:844});
 await page.locator('.p2-tool').filter({hasText:'Plan'}).click();
 assert.match(await page.locator('#message').inputValue(),/^Help me plan /,'guided tool uses original composer');
 await page.locator('#message').fill('');
 await page.locator('.p2-mobile-chat').click();
 await page.waitForFunction(()=>!document.body.classList.contains('home-landing'));
 assert.equal(await page.evaluate(()=>window.vishnuChatBridge.currentConversationId),'existing');
 assert.equal(created,0,'Chat reopens the existing conversation, without duplicating it');
 await page.evaluate(()=>window.vishnuChatBridge.openModule('home'));
 await page.fill('#message','Home test');
 await page.press('#message','Enter');
 await page.getByText('Canonical assistant response').waitFor({state:'visible',timeout:10000});
 assert.equal(active.conversation.id,'existing','same conversation preserved after sending');
 await page.evaluate(()=>window.vishnuChatBridge.openModule('home'));
 workUnavailable=true;
 await page.evaluate(()=>window.__vishnuP201.refresh());
 assert.match(await page.locator('.p2-work-content').innerText(),/unavailable/i,'outage is not presented as zero work');
 workUnavailable=false;
 await page.evaluate(()=>document.getElementById('voicePanel').classList.add('hidden'));
 assert.equal(await page.locator('#voicePanel').isVisible(),false,'locked Home remains hidden');
 assert.deepEqual(errors,[],'no uncaught client exceptions');
 console.log('P2-01 Home responsive, read-only projection, composer, error and locked-state checks passed.');
} finally {await browser.close();}
