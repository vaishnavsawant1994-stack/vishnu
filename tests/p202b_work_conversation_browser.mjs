/* P2-02B browser acceptance fixture: same canonical chat and Work projections.
 * Mock backend only: real provider, Work execution and native parity unverified.
 */
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';
await mkdir('artifacts/p202b',{recursive:true});
const browser=await chromium.launch({headless:true});
const base=process.env.PWA_PREVIEW_URL||'http://127.0.0.1:4173';
const errors=[];
const createdAt=new Date().toISOString();
const convo={id:'c-work-1',title:'Current discussion',updated_at:createdAt,preview:'Help review the quarterly plan',context:{conversation_kind:'work'}};
let conversations=[convo],active={conversation:convo,events:[
 {event_id:'u1',kind:'user_message',created_at:createdAt,payload:{text:'Help review the quarterly plan'}},
 {event_id:'a1',kind:'assistant_message',created_at:createdAt,payload:{text:'Here are the areas to review. This is advice, not a running WorkOrder.'}}
 ]},workLoaded=0,turns=0,created=0,projectTaskStatus='planned',linkedProjectWrites=0,taskWrites=0;
const apiPath=url=>new URL(url).pathname.replace('/iphone/api','');
const fixture=async route=>{
 const request=route.request(),path=apiPath(request.url()),method=request.method();
 let response={};
 if(path==='/status')response={owner_display_name:'Test Owner',model:{state:'ready'},conversation:active,conversations,active_qualification:true};
 else if(path==='/preferences')response={};
 
 else if(path==='/projects')response={projects:[{id:'project-1',name:'Assigned Project',status:'active'}]};
 else if(path==='/projects/project-1'&&method==='GET')response={project:{
   id:'project-1',name:'Assigned Project',status:'active',
   files:[{id:'file-p1',title:'Assigned brief.md',kind:'upload',size_bytes:128}],
   tasks:[{id:'task-p1',title:'Review design brief',status:projectTaskStatus}],approvals:[]}};
 else if(path==='/projects/project-1/work'&&method==='GET')response={
   state:'planned',p10_plan:{id:'plan-p1',state:'RUNNING',
    tasks:[{id:'step-p1',objective:'Review implementation evidence',status:'WAITING'}]}};
 else if(path==='/approvals-center')response={authority:'approval_manager',approvals:[
   {id:'approval-p1',title:'Approve scoped task',status:'pending',project_id:'project-1'},
   {id:'approval-unrelated',title:'Unrelated approval',status:'pending',project_id:'other-project'}]};
 else if(path==='/projects/project-1/files/file-p1/index')response={extracted_text:'Signed Project document preview'};
 else if(path==='/projects/project-1/tasks/task-p1'&&method==='PATCH'){
   const body=JSON.parse(request.postData()||'{}');
   assert.ok(['done','planned'].includes(body.status));
   projectTaskStatus=body.status;taskWrites++;response={project:{id:'project-1'}};
 }
 else if(path==='/conversations'&&method==='GET'){
   const kind=new URL(request.url()).searchParams.get('kind');
   response={active_conversation_id:active.conversation.id,
     conversations:kind?conversations.filter(c=>(c.context?.conversation_kind||'personal')===kind):conversations};
 }
 else if(path==='/conversations'&&method==='POST'){
   created++;
   const body=JSON.parse(request.postData()||'{}');
   assert.equal(body.context_type,'work','new Work chat must be persisted as Work in canonical API');
   const c={id:'c-work-'+(created+1),title:'New Work Conversation',updated_at:new Date().toISOString(),context:{conversation_kind:'work'}};
   conversations=[c,...conversations];active={conversation:c,events:[]};response=active;
 }
 
 else if(path.startsWith('/conversations/')&&path.endsWith('/work-project')&&method==='PUT'){
   const body=JSON.parse(request.postData()||'{}');
   assert.equal(body.confirm,true,'Project link requires explicit confirmation');
   assert.ok(body.project_id===null||body.project_id==='project-1');
   assert.equal(active.conversation.context.conversation_kind,'work');
   active.conversation.context.work_project_id=body.project_id;
   linkedProjectWrites++;response={conversation:active.conversation};
 }
 else if(path.startsWith('/conversations/')&&method==='GET')response=active;
 else if(path.startsWith('/conversations/')&&path.endsWith('/activate'))response=active;
 else if(path==='/work/summary'){
   workLoaded++;
   response={authority:'read_only_projection',counts:{active:1},work_orders:[{
     project_id:'external-project',project_name:'Separate project',task_id:'task1',
     title:'Independent Project WorkOrder',status:'RUNNING'}]};
 }
 else if(path==='/work/attention')response={authority:'read_only_projection',counts:{total:0,approval:0},items:[]};
 else if(path==='/voice/turn'&&method==='POST'){
   turns++;
   const input=JSON.parse(request.postData()||'{}');
   const now=new Date().toISOString();
   active.events.push({event_id:'u'+turns,kind:'user_message',created_at:now,payload:{text:input.transcript}});
   active.events.push({event_id:'a'+turns,kind:'assistant_message',created_at:now,payload:{text:'Real transport fixture response '+turns}});
   response={conversation_id:active.conversation.id,conversation_title:active.conversation.title,reply:'Real transport fixture response '+turns,status:'completed'};
 }
 else if(path==='/everyday/active'||path==='/everyday/timeline')response={items:[]};
 else if(path==='/access/options')response={passkey_available:false,password_available:false,google_available:false};
 return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(response)});
};
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},serviceWorkers:'block'});
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/web/api/**',fixture);
 await page.route('**/iphone/api/**',fixture);
 await page.goto(base+'/iphone/',{waitUntil:'commit',timeout:60000});
 await page.waitForFunction(()=>window.__vishnuP202B&&window.vishnuChatBridge,{timeout:20000});
 await page.evaluate(()=>window.__vishnuP202B.open());
 await page.waitForFunction(()=>document.body.classList.contains('p202-work-chat'),null,{timeout:20000});
 assert.equal(await page.locator('#messageStream .message-entry').count(),2,'one canonical user + assistant transcript');
 assert.equal(await page.locator('#neuralCanvas').count(),1,'canonical neural canvas reused once');
 assert.equal(await page.locator('#p202Header').isVisible(),false,'Personal-only header suppressed in Work view');
 assert.equal(active.conversation.context.conversation_kind,'work','Work scope is canonical, not a relabeled personal transcript');
 assert.equal(await page.locator('#p202bShell').isVisible(),true);
 assert.equal(await page.locator('.p202b-tab').count(),7,'seven approved Work tabs');
 assert.equal(await page.locator('.p202b-quick-button').count(),6,'six approved Work quick actions');
 await page.waitForFunction(()=>document.querySelector('#p202bShell')?.textContent.includes('Independent Project WorkOrder'));
 assert.match(await page.locator('.p202b-context').innerText(),/not attached to this conversation/i,'unlinked Work truthfully labeled');
 assert.match(await page.locator('.p202b-context').innerText(),/No files are linked/i,'unlinked files never fabricated');
 assert.match(await page.locator('.p202b-context').innerText(),/No linked conversation tasks/i,'unlinked tasks never fabricated');
 assert.ok(workLoaded>=1,'owner-scoped Work projection requested');
 await page.locator('.p202b-quick-button').filter({hasText:'Summarize'}).click();
 assert.match(await page.locator('#message').inputValue(),/Summarize the current work conversation/);
 assert.equal(turns,0,'quick actions never pretend execution');
 await page.locator('#message').fill('');
 await page.locator('.p202b-search-actions button').first().click();
 await page.locator('.p202b-search input').fill('quarterly plan');
 assert.ok(await page.locator('.p202b-search-hit').count()>0,'real loaded conversation search');
 await page.locator('.p202b-search input').fill('');
 await page.locator('.p202b-search-actions button').first().click();
 await page.locator('.p202b-tab[data-tab=Files]').click();
 await page.locator('dialog[open]').waitFor();
 assert.match(await page.locator('dialog[open]').innerText(),/not linked|No file/i);
 await page.locator('dialog[open]').getByText('Close').click();
 // Resource cards become populated only when the owner links a real Project.
 await page.locator('.p202b-context').getByRole('button',{name:'Link Project'}).click();
 await page.locator('dialog[open]').getByRole('button',{name:'Assigned Project'}).click();
 await page.waitForFunction(()=>document.querySelector('.p202b-context')?.textContent.includes('Assigned brief.md'));
 assert.equal(active.conversation.context.work_project_id,'project-1','linked Project persisted in continuity');
 assert.ok(linkedProjectWrites>=1,'owner-confirmed Project link request recorded');
 assert.match(await page.locator('.p202b-context').innerText(),/Review design brief/);
 assert.match(await page.locator('.p202b-context').innerText(),/WorkPlan/);
 assert.match(await page.locator('.p202b-context').innerText(),/Approve scoped task/);
 assert.doesNotMatch(await page.locator('.p202b-context').innerText(),/Unrelated approval/);
 await page.locator('.p202b-tab[data-tab=Files]').click();
 await page.locator('dialog[open]').getByRole('button',{name:/Assigned brief.md/}).click();
 await page.locator('dialog[open]').getByRole('button',{name:'Preview text'}).click();
 assert.match(await page.locator('dialog[open]').innerText(),/Signed Project document preview/);
 await page.locator('dialog[open]').getByRole('button',{name:'Close'}).click();
 await page.locator('.p202b-context .p202b-resource').filter({hasText:'Review design brief'}).click();
 await page.locator('dialog[open]').getByRole('button',{name:'Mark done'}).click();
 await page.waitForFunction(()=>document.querySelector('.p202b-context')?.textContent.includes('done'));
 assert.equal(projectTaskStatus,'done','task updated through the Project API');
 assert.equal(taskWrites,1,'single Project task mutation');
 await page.locator('.p202b-context').getByRole('button',{name:'Change Project'}).click();
 await page.locator('dialog[open]').getByRole('button',{name:'Unlink Project'}).click();
 await page.waitForFunction(()=>document.querySelector('.p202b-context')?.textContent.includes('Independent Project WorkOrder'));
 assert.equal(active.conversation.context.work_project_id,null,'unlink persisted');
 for(const [width,height] of [[320,650],[375,812],[390,844],[430,932],[768,1024],[1024,768],[1280,800],[1440,900],[1920,1080]]){
   await page.setViewportSize({width,height});
   const layout=await page.evaluate(()=>{
      const b=(selector)=>{const n=document.querySelector(selector);const r=n.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,height:r.height}};
      return {w:document.documentElement.scrollWidth,composer:b('#composer'),stream:b('#messageStream')};
   });
   assert.ok(layout.w<=width+2,'no horizontal overflow '+width);
   assert.ok(layout.stream.height>100,'conversation remains usable '+width);
   assert.ok(layout.composer.left>=-2&&layout.composer.right<=width+2,'composer remains in viewport '+width);
   if(width<=900)assert.equal(await page.locator('#p202bMobileNav button').count(),5,'five mobile tabs '+width);
   if([390,768,1440].includes(width))await page.screenshot({path:'artifacts/p202b/work-'+width+'.png',fullPage:true});
 }
 await page.setViewportSize({width:390,height:844});
 await page.locator('.p202b-more').click();
 await page.getByText('Work conversation sections').waitFor();
 await page.getByRole('button',{name:'Search messages'}).click();
 await page.locator('.p202b-search-modal input').fill('quarterly plan');
 assert.ok(await page.locator('.p202b-search-modal .p202b-search-hit').count()>0,
   'mobile Work search uses canonical loaded messages');
 await page.locator('.p202b-search-modal').getByRole('button',{name:'Close'}).click();
 await page.locator('#message').fill('Follow-up in Work conversation');
 await page.locator('#message').press('Enter');
 await page.getByText('Real transport fixture response 1').waitFor({timeout:10000});
 assert.equal(turns,1,'canonical AI endpoint was called exactly once');
 assert.equal(active.conversation.id,'c-work-1','canonical conversation ID unchanged');
 await page.reload({waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>document.body.classList.contains('p202-work-chat'),null,{timeout:20000});
 assert.match(await page.locator('#messageStream').innerText(),/Follow-up in Work conversation/,'conversation survives mock reload');
 await page.evaluate(()=>document.querySelector('#vContextChip span').textContent='Project · Private');
 await page.waitForFunction(()=>!document.body.classList.contains('p202-work-chat'));
 await page.evaluate(()=>document.querySelector('#vContextChip span').textContent='General chat · No project context');
 await page.waitForFunction(()=>document.body.classList.contains('p202-work-chat'));
 await page.evaluate(()=>window.__vishnuP202B.newChat());
 await page.waitForFunction(()=>document.body.classList.contains('chat-new-empty'));
 assert.equal(active.conversation.id,'c-work-2','New Work Chat reuses canonical creation');
 assert.deepEqual(errors,[],'no uncaught browser errors');
 console.log('P2-02B Work Chat mock API browser checks passed; external providers and real Work execution not qualified.');
}finally{await browser.close()}
