import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

await mkdir('artifacts', { recursive: true });
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHAT_TEST_CHROMIUM_PATH || undefined });
const errors = [];
let active = null;
let conversations = [];
let created = 0;
let turns = 0;
let modalities = [],turnRequests=[];

function bundle(){ return active || { conversation: { id: '', title: 'New conversation' }, events: [] }; }
async function wire(page){
  page.on('pageerror', e => errors.push(e.message));
  await page.route('**/iphone/api/**', async route => {
    const req=route.request(), url=new URL(req.url()), path=url.pathname.replace('/iphone/api',''), method=req.method();
    let body={};
    if(path==='/status') body={ok:true,owner_display_name:'Test Owner',model:{state:'ready'},conversation:null,conversations:[],memory_count:0};
    else if(path==='/preferences') body={continuous_voice:false,voice_rate:1,quiet_hours:false};
    else if(path==='/projects'||path==='/projects?status=active') body={projects:[{id:'p1',name:'Test Project',conversation_id:'project-chat-p1'}]};
    else if(path==='/projects/p1/conversation'&&method==='POST') body={conversation_id:'project-chat-p1',project:{id:'p1',name:'Test Project'}};
    else if(path==='/projects/p1/discussions'&&method==='POST'){
      const input=JSON.parse(req.postData()||'{}');await page.evaluate(value=>window.__projectDiscussion=value,input);body={project:{id:'p1',name:'Test Project'}};
    }
    else if(path==='/everyday/active'||path==='/everyday/timeline') body={items:[]};
    else if(path==='/conversations'&&method==='POST'){
      created++;active={conversation:{id:'chat-'+created,title:'New conversation'},events:[]};conversations.unshift(active.conversation);body=active;
    } else if(path==='/conversations'&&method==='GET') body={conversations};
    else if(path==='/voice/turn'&&method==='POST'){
      turns++;modalities.push(req.headers()['x-personal-ai-input-modality']||'');turnRequests.push({headers:req.headers(),post:req.postData()});const input=JSON.parse(req.postData()||'{}');const now=new Date().toISOString();
      active.events.push({event_id:'u-'+turns,kind:'user_message',created_at:now,payload:{text:input.transcript}});
      active.events.push({event_id:'a-'+turns,kind:'assistant_message',created_at:now,payload:{text:'Here is a concise plan based on your question.',sources:[{title:'Planning reference',description:'Source metadata returned by the conversation service.',url:'https://example.test/reference'}]}});
      body={conversation_id:active.conversation.id,conversation_title:active.conversation.title,reply:'Here is a concise plan based on your question.',status:'completed'};
    } else if(path==='/conversations/project-chat-p1/activate'&&method==='POST') {active={conversation:{id:'project-chat-p1',title:'Test Project'},events:[]};body=active;}
    else if(path.startsWith('/conversations/')&&path.endsWith('/activate')) body=active||{};
    else if(path.startsWith('/conversations/')&&method==='GET') body=active||{};
    else if(path.startsWith('/conversations/')&&path.endsWith('/export')) body={conversation:active?.conversation,events:active?.events||[]};
    else if(path.startsWith('/conversations/')&&method==='PATCH'){const input=JSON.parse(req.postData()||'{}');active.conversation.title=input.title;body={conversation:active.conversation};}
    else if(path.startsWith('/conversations/')&&method==='DELETE') body={deleted:true};
    else if(path.endsWith('/archive')&&method==='POST') body={ok:true,status:'archived'};
    else if(path==='/access/options') body={passkey_available:false,password_available:false,google_available:false};
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
  });
}

try{
  const desktop=await browser.newPage({viewport:{width:1440,height:960},serviceWorkers:'block'});
  await wire(desktop);
  await desktop.addInitScript(()=>sessionStorage.setItem('vishnuAccessIntent','join'));
  await desktop.goto('http://127.0.0.1:4173/iphone/',{waitUntil:'load'});
  await desktop.locator('#vNewChat').evaluate(node=>node.click());
  await desktop.waitForFunction(()=>document.body.classList.contains('chat-new-empty'));
  await desktop.screenshot({path:'artifacts/chat-new-empty-desktop.png',fullPage:true});
  assert.equal(await desktop.locator('#chatPromptGrid .chat-prompt-card').count(),4);
  assert.equal(await desktop.locator('#appDrawer').isVisible(),true,'desktop uses existing global navigation');
  assert.equal(await desktop.locator('#conversationDrawer').isVisible(),true,'desktop uses the existing conversation list');
  assert.equal(await desktop.locator('#vContextChip').isVisible(),true,'new chat keeps its project context selector visible');
  assert.equal(await desktop.locator('#sendButton').isVisible(),true,'send control remains visible for an empty draft');
  await desktop.locator('#chatPromptGrid .chat-prompt-card').first().click();
  assert.match(await desktop.locator('#message').inputValue(),/plan a project/i);
  assert.equal(turns,0,'a suggestion fills the draft without submitting it');
  await desktop.locator('#vContextChip').click();
  await desktop.locator('.project-dialog select[name="project_id"]').selectOption('p1');
  await desktop.locator('.project-dialog .project-btn.primary').click();
  await desktop.waitForFunction(()=>document.querySelector('#vContextChip')?.getAttribute('aria-label')?.includes('Test Project'));
  assert.match(await desktop.locator('#vContextChip').innerText(),/Project\s*·\s*Test Project/,'desktop chip visibly names the selected project');
  assert.match(await desktop.locator('#message').inputValue(),/plan a project/i,'switching context preserves an unsent draft');
  await desktop.locator('#sendButton').click();
  await desktop.waitForFunction(()=>document.body.classList.contains('has-conversation'));
  await desktop.getByText('Here is a concise plan based on your question.',{exact:true}).waitFor({state:'visible'});
  assert.match(await desktop.locator('#messageStream').innerText(),/Help me plan a project/i);
  assert.match(await desktop.locator('#messageStream').innerText(),/Here is a concise plan/i);
  assert.equal(modalities[0],'text','typed prompt stays a text turn; captured request '+JSON.stringify(turnRequests[0]));
  await desktop.waitForTimeout(500);
  assert.equal((await desktop.locator('#voiceAlert').innerText()).trim(),'','typed chats do not trigger unsolicited speech playback');
  assert.ok((await desktop.locator('#messageStream').boundingBox()).height>250,'desktop transcript has a usable reading area');
  await desktop.waitForSelector('#chatDetailDesktop .chat-details-section',{state:'visible'});
  assert.equal(await desktop.locator('#chatDetailDesktop').isVisible(),true);
  await desktop.locator('.chat-source-preview').waitFor();
  assert.equal(await desktop.locator('.chat-source-preview').count(),1,'source card uses source metadata from the saved assistant event');
  assert.match(await desktop.locator('#chatDetailDesktop').innerText(),/You asked|Vishnu responded/);
  await desktop.screenshot({path:'artifacts/chat-details-desktop.png',fullPage:true});
  await desktop.locator('#chatDetailDesktop [data-chat-detail="close"]').click();
  await desktop.screenshot({path:'artifacts/chat-active-desktop.png',fullPage:true});
  await desktop.locator('#chatMenuButton').evaluate(node=>node.click());
  await desktop.locator('#chatDetailsMenuItem').evaluate(node=>node.click());
  await desktop.locator('#chatDetailDesktop [data-chat-detail="project"]').click();
  await desktop.locator('.project-dialog select[name="project_id"]').selectOption('p1');
  await desktop.locator('.project-dialog .project-btn.primary').click();
  await desktop.waitForFunction(()=>document.querySelector('#actionDialog')?.open===true);
  assert.match(await desktop.locator('#actionDialogMessage').innerText(),/copies the conversation transcript/i);
  await desktop.locator('#actionDialogSubmit').click();
  await desktop.waitForFunction(()=>Boolean(window.__projectDiscussion));
  assert.match(await desktop.evaluate(()=>window.__projectDiscussion.content),/You: Help me plan a project/i,'Add to project stores only the owner-confirmed conversation transcript via project discussions');
  await desktop.locator('#chatMenuButton').evaluate(node=>node.click());
  await desktop.locator('#chatDetailsMenuItem').evaluate(node=>node.click());
  await desktop.locator('#chatDetailDesktop [data-chat-detail="today"]').waitFor({state:'visible'});
  await desktop.locator('#chatDetailDesktop [data-chat-detail="today"]').evaluate(node=>node.click());
  await desktop.waitForFunction(()=>document.querySelector('#todayDialog')?.open===true);
  await desktop.waitForFunction(()=>/Follow up: Help me plan a project/i.test(document.querySelector('#todayTitle')?.value||''));
  assert.match(await desktop.locator('#todayTitle').inputValue(),/Follow up: Help me plan a project/i,'Add to Today opens an editable task draft from the conversation');
  await desktop.locator('#todayCancel').click();
  await desktop.locator('#actionDialogSubmit').click();
  await desktop.waitForFunction(()=>document.querySelector('#todayDialog')?.open===false);
  await desktop.locator('#chatMenuButton').evaluate(node=>node.click());
  await desktop.locator('#chatDetailsMenuItem').evaluate(node=>node.click());
  await desktop.locator('#chatDetailDesktop [data-chat-detail="delete"]').evaluate(node=>node.click());
  assert.equal(await desktop.locator('#actionDialog').evaluate(node=>node.open),true,'deletion asks for confirmation');
  await desktop.locator('#actionDialogCancel').click();
  await desktop.locator('#vContextChip').click();
  await desktop.locator('.project-dialog select[name="project_id"]').selectOption('');
  await desktop.locator('.project-dialog .project-btn.primary').click();
  await desktop.waitForFunction(()=>document.body.innerText.includes('General chat · No project context'));
  assert.notEqual(await desktop.evaluate(()=>window.vishnuChatBridge.current.id),'project-chat-p1','switching to general opens a separate general conversation');

  const mobile=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:2,isMobile:true,hasTouch:true,serviceWorkers:'block'});
  active=null;conversations=[];created=0;turns=0;modalities=[];
  await wire(mobile);
  await mobile.addInitScript(()=>sessionStorage.setItem('vishnuAccessIntent','join'));
  await mobile.goto('http://127.0.0.1:4173/iphone/',{waitUntil:'load'});
  await mobile.locator('#vNewChat').evaluate(node=>node.click());
  await mobile.waitForFunction(()=>document.body.classList.contains('chat-new-empty'));
  await mobile.screenshot({path:'artifacts/chat-new-empty-mobile.png',fullPage:true});
  assert.equal(await mobile.locator('#vContextChip').isVisible(),true,'mobile new chat exposes its current project context');
  assert.equal(await mobile.locator('#sendButton').isVisible(),true,'mobile keeps the send control visible');
  assert.ok((await mobile.locator('#composer').boundingBox()).y>700,'mobile new chat composer remains at the bottom');
  await mobile.locator('#vContextChip').click();
  await mobile.locator('.project-dialog select[name="project_id"]').selectOption('p1');
  await mobile.locator('.project-dialog .project-btn.primary').click();
  await mobile.waitForFunction(()=>document.querySelector('#vContextChip')?.getAttribute('aria-label')?.includes('Test Project'));
  assert.match(await mobile.locator('#vContextChip').innerText(),/Project\s*·\s*Test Project/,'mobile chip visibly names the selected project');
  await mobile.locator('#vContextChip').click();
  await mobile.locator('.project-dialog select[name="project_id"]').selectOption('');
  await mobile.locator('.project-dialog .project-btn.primary').click();
  await mobile.waitForFunction(()=>document.body.innerText.includes('General chat · No project context'));
  await mobile.locator('#chatPromptGrid .chat-prompt-card').nth(1).click();
  assert.equal(turns,0);
  await mobile.locator('#sendButton').click();
  await mobile.waitForFunction(()=>document.body.classList.contains('has-conversation'));
  await mobile.getByText('Here is a concise plan based on your question.',{exact:true}).waitFor({state:'visible'});
  assert.match(await mobile.locator('#messageStream').innerText(),/Here is a concise plan/i);
  assert.equal(modalities[0],'text','mobile typed prompt stays a text turn');
  await mobile.waitForTimeout(500);
  assert.equal((await mobile.locator('#voiceAlert').innerText()).trim(),'','typed chats do not trigger unsolicited speech playback');
  assert.ok((await mobile.locator('#composer').boundingBox()).y>700,'mobile composer stays at the bottom of the viewport');
  await mobile.screenshot({path:'artifacts/chat-active-mobile.png',fullPage:true});
  await mobile.locator('#chatMenuButton').evaluate(node=>node.click());
  await mobile.locator('#chatDetailsMenuItem').evaluate(node=>node.click());
  await mobile.waitForFunction(()=>document.querySelector('#chatDetailMobile').classList.contains('open'));
  assert.match(await mobile.locator('#chatDetailMobile').innerText(),/Chat details/);
  assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'mobile page has no horizontal overflow');
  await mobile.screenshot({path:'artifacts/chat-details-mobile.png',fullPage:true});
  await mobile.locator('#chatDetailMobile [data-chat-detail="back"]').click();
  assert.equal(await mobile.locator('#chatDetailMobile').evaluate(n=>n.classList.contains('open')),false,'mobile details returns to the conversation');
  assert.deepEqual(errors,[],'browser has no uncaught errors');
  console.log('Chat experience desktop/mobile checks passed. Screenshots: artifacts/chat-active-desktop.png, artifacts/chat-details-mobile.png');
}finally{await browser.close()}
