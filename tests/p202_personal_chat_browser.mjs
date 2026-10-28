/* Browser regression for P2-02A using owner-scoped API fixtures.
 * UI qualification only: does not assert real-provider or physical-device acceptance.
 */
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';
await mkdir('artifacts/p202',{recursive:true});
const browser=await chromium.launch({headless:true});
const base=process.env.PWA_PREVIEW_URL||'http://127.0.0.1:4173';
const errors=[];
const createdAt=new Date().toISOString();
const convo={id:'personal-1',title:'My daily planning',updated_at:createdAt,preview:'Can you plan my day?'};
const events=[
 {event_id:'u-1',kind:'user_message',payload:{text:'Can you plan my day?'},created_at:createdAt},
 {event_id:'a-1',kind:'assistant_message',payload:{text:'## Your Plan for Today\n9:00 – 10:00 - Focused work\n10:00 – 10:30 - Take a break\n11:00 – 12:00 - Personal projects\nAdjust any block for your actual commitments.'},created_at:createdAt}
];
let conversations=[convo],active={conversation:convo,events},creates=0,turns=0;
const parsePath=url=>new URL(url).pathname.replace('/iphone/api','');
async function fixture(route){
 const req=route.request(),path=parsePath(req.url()),method=req.method();
 if(path==='/status')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({owner_display_name:'Mira Chen',model:{state:'ready'},conversation:active,conversations,memory_count:0,active_qualification:true})});
 let data={};
 if(path==='/preferences') data={};
 else if(path==='/projects'||path==='/projects?status=active')data={projects:[]};
 else if(path==='/conversations'&&method==='GET')data={conversations};
 else if(path==='/conversations'&&method==='POST'){
   creates++;
   const row={id:'personal-'+(creates+1),title:'New conversation',updated_at:new Date().toISOString()};
   conversations=[row,...conversations];active={conversation:row,events:[]};data=active;
 }
 else if(path.startsWith('/conversations/')&&method==='GET')data=active;
 else if(path.startsWith('/conversations/')&&path.endsWith('/activate'))data=active;
 else if(path==='/voice/turn'&&method==='POST'){
   turns++;const input=JSON.parse(req.postData()||'{}');
   active.events.push({event_id:'user-new-'+turns,kind:'user_message',payload:{text:input.transcript},created_at:new Date().toISOString()});
   active.events.push({event_id:'assistant-new-'+turns,kind:'assistant_message',payload:{text:'Canonical Vishnu assistant reply'},created_at:new Date().toISOString()});
   data={conversation_id:active.conversation.id,conversation_title:active.conversation.title,reply:'Canonical Vishnu assistant reply',status:'completed'};
 }
 else if(path==='/everyday/active'||path==='/everyday/timeline')data={items:[]};
 else if(path==='/access/options')data={passkey_available:false,password_available:false,google_available:false};
 return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
}
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},serviceWorkers:'block',hasTouch:false});
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('https://accounts.google.com/gsi/client',route=>route.fulfill({status:200,contentType:'application/javascript',body:''}));
 await page.route('**/web/api/**',fixture);
 await page.route('**/iphone/api/**',fixture);
 await page.goto(base+'/iphone/',{waitUntil:'commit',timeout:60000});
 // Vishnu intentionally starts on Home; open the saved Personal conversation
 // using the canonical transport before testing the dedicated Chat screen.
 await page.waitForFunction(()=>window.vishnuChatBridge&&document.body.classList.contains('home-landing'));
 await page.evaluate(()=>window.vishnuChatBridge.openConversation('personal-1'));
 await page.waitForFunction(()=>document.body.classList.contains('p202-personal-chat'),null,{timeout:20000});
 await page.locator('#p202Header').waitFor({state:'visible'});
 assert.equal(await page.locator('#p202Header .p202-conversation-name').innerText(),'My daily planning');
 assert.match(await page.locator('#p202Header .p202-context').innerText(),/Personal Conversation/);
 assert.equal(await page.locator('#neuralCanvas').count(),1,'canonical live neural canvas reused');
 assert.equal(await page.locator('#p202MobileNav').isVisible(),false,'mobile tabs hidden on desktop');
 assert.equal(await page.locator('#conversationsDrawerTitle').innerText(),'Chats');
 assert.equal(await page.locator('#p202Header').isVisible(),true);
 assert.equal(await page.locator('#messageStream .message-entry').count(),2,'canonical conversation history renders');
 assert.match(await page.locator('#messageStream').innerText(),/Can you plan my day/);
 assert.equal(await page.locator('.p202-plan-card').count(),1,'structured plan based only on real assistant message');
 assert.equal(await page.locator('.p202-plan-row').count(),3);
 assert.equal(await page.locator('.p202-followup').count(),3);
 assert.equal(await page.locator('#chatDetailDesktop').isVisible(),false,'no mandatory Work/Project details panel');
 await page.locator('[data-p202-followup="shorter"]').click();
 assert.match(await page.locator('#message').inputValue(),/concise version/,'follow up is editable and retains context');
 await page.locator('#message').fill('');
 await page.locator('#p202ModelPlacement .p202-model').click();
 await page.locator('#p202ModelDialog').waitFor();
 assert.match(await page.locator('#p202ModelDialog').innerText(),/configured AI routing/);
 await page.locator('#p202ModelDialog').getByText('Close').click();
 await page.locator('#attachmentButton').click();
 await page.locator('#p202AttachmentDialog').waitFor();
 assert.match(await page.locator('#p202AttachmentDialog').innerText(),/Knowledge Library/);
 assert.match(await page.locator('#p202AttachmentDialog').innerText(),/not enabled/i);
 await page.locator('#p202AttachmentDialog').getByText('Cancel').click();
 for(const [width,height] of [[320,650],[375,812],[390,844],[430,932],[768,1024],[1024,768],[1280,800],[1440,900],[1920,1080]]){
   await page.setViewportSize({width,height});
   const layout=await page.evaluate(()=>{
     const bb=s=>{const r=document.querySelector(s).getBoundingClientRect();return{left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}};
     return {scrollWidth:document.documentElement.scrollWidth,composer:bb('#composer'),header:bb('#p202Header'),stream:bb('#messageStream')};
   });
   assert.ok(layout.scrollWidth<=width+1,'no horizontal overflow at '+width);
   assert.ok(layout.composer.left>=-1&&layout.composer.right<=width+1,'composer in viewport '+width);
   assert.ok(layout.stream.height>150,'readable transcript height at '+width);
   if(width<=760){
     assert.equal(await page.locator('#p202MobileNav').isVisible(),true,'five mobile tabs visible '+width);
     assert.equal(await page.locator('#p202MobileNav button').count(),5);
     assert.equal(await page.locator('#p202MobileNav [aria-current="page"]').count(),1);
   }
   if([390,768,1440].includes(width))await page.screenshot({path:'artifacts/p202/personal-'+width+'.png',fullPage:true});
 }
 await page.setViewportSize({width:390,height:844});
 await page.locator('#message').fill('A follow up');
 await page.locator('#message').press('Enter');
 await page.getByText('Canonical Vishnu assistant reply').waitFor({timeout:10000});
 assert.equal(turns,1,'one canonical server turn');
 assert.equal(active.conversation.id,'personal-1','conversation ID preserved');
 assert.equal(await page.locator('.p202-plan-card').count(),1,'existing plan card survives refreshed message rendering');
 await page.locator('#message').fill('');
 await page.locator('#p202Header .p202-context').click();
 await page.getByText(/No active projects are available|Create a project first/).first().waitFor({timeout:10000});
 assert.equal(active.conversation.id,'personal-1','context picker does not silently move personal chat');
 // The Personal UI is only a presentation surface: a canonical Project
 // context must not be relabeled as a Personal Conversation.
 await page.evaluate(()=>document.querySelector('#vContextChip span').textContent='Project · Private Workspace');
 await page.waitForFunction(()=>!document.body.classList.contains('p202-personal-chat'));
 assert.equal(await page.locator('#p202Header').isVisible(),false,'Project context hides Personal-only controls');
 await page.evaluate(()=>document.querySelector('#vContextChip span').textContent='General chat · No project context');
 await page.waitForFunction(()=>document.body.classList.contains('p202-personal-chat'));
 // Canonical New Chat leaves the previous conversation and its messages intact.
 await page.evaluate(()=>window.vishnuChatBridge.createConversation());
 await page.waitForFunction(()=>document.body.classList.contains('chat-new-empty'));
 await page.locator('#p202Welcome').waitFor({state:'visible'});
 assert.equal(await page.locator('#p202Welcome .p202-prompt').count(),4,'new chat offers four personal prompts');
 assert.equal(active.conversation.id,'personal-2','new Personal conversation was persisted');
 await page.locator('#p202Welcome .p202-prompt').first().click();
 assert.match(await page.locator('#message').inputValue(),/organize my day/i,'starter prepares an editable draft, not a tool action');
 assert.equal(turns,1,'choosing a suggestion never triggers an AI turn');
 await page.locator('#message').fill('');
 await page.screenshot({path:'artifacts/p202/personal-empty-mobile.png',fullPage:true});
 await page.evaluate(()=>window.vishnuChatBridge.openModule('home'));
 await page.waitForFunction(()=>!document.body.classList.contains('p202-personal-chat'));
 assert.equal(await page.locator('#p202Header').isVisible(),false,'Chat header fully hidden on Home');
 assert.equal(await page.locator('#p202MobileNav').isVisible(),false,'Chat-only mobile tabs do not leak into Home');
 assert.equal(await page.locator('#p202ModelPlacement').isVisible(),false,'Chat model control not shown on Home');
 assert.deepEqual(errors,[],'no uncaught browser exceptions');
 console.log('P2-02A Personal Chat browser state, plan, composer, context, responsive and route isolation checks passed.');
}finally{await browser.close()}
