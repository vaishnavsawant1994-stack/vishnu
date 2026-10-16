import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const browser=await chromium.launch({headless:true});
const errors=[];

async function wire(page){
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/iphone/api/**',async route=>{
    const req=route.request(),url=new URL(req.url()),path=url.pathname.replace('/iphone/api',''),method=req.method();
    let body={};
    if(path==='/status') body={ok:true,owner_display_name:'Adaptive Test',model:{state:'ready'},conversation:null,conversations:[],memory_count:0};
    else if(path==='/preferences') body={continuous_voice:false,voice_rate:1,quiet_hours:false};
    else if(path==='/projects'||path==='/projects?status=active') body={projects:[]};
    else if(path==='/everyday/active'||path==='/everyday/timeline') body={items:[]};
    else if(path==='/conversations'&&method==='GET') body={conversations:[]};
    else if(path==='/access/options') body={passkey_available:false,password_available:false,google_available:false};
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
  });
}

try{
  const page=await browser.newPage({viewport:{width:1280,height:860},serviceWorkers:'block'});
  await wire(page);
  await page.goto('http://127.0.0.1:4173/iphone/',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>Boolean(window.vishnuAdaptiveComposer));

  const classified=await page.evaluate(()=>({
    reminder:window.vishnuAdaptiveComposer.classifyDraft('remind me tomorrow at 9'),
    file:window.vishnuAdaptiveComposer.classifyDraft('find my budget.pdf'),
    memory:window.vishnuAdaptiveComposer.classifyDraft('remember what we discussed last time'),
    research:window.vishnuAdaptiveComposer.classifyDraft('research the latest battery technology with sources'),
    chat:window.vishnuAdaptiveComposer.classifyDraft('hello there')
  }));
  assert.equal(classified.reminder.intent,'automation');
  assert.equal(classified.file.intent,'files');
  assert.equal(classified.memory.intent,'memory');
  assert.equal(classified.research.intent,'research');
  assert.equal(classified.chat.intent,'chat');
  assert.ok(classified.reminder.confidence>=0.60);

  const hysteresis=await page.evaluate(()=>{
    const api=window.vishnuAdaptiveComposer;
    const initial={intent:'projects',confidence:0.80,pendingIntent:null,pendingWins:0};
    const challenger={intent:'memory',confidence:0.72};
    const once=api.stableIntent(initial,challenger);
    const twice=api.stableIntent(once,challenger);
    return {once,twice};
  });
  assert.equal(hysteresis.once.intent,'projects','one moderate challenger must not flicker the committed UI');
  assert.equal(hysteresis.once.pendingIntent,'memory');
  assert.equal(hysteresis.twice.intent,'memory','a repeated strong challenger can change the committed UI');

  await page.locator('#message').fill('remember what we discussed last time');
  await page.waitForFunction(()=>document.querySelector('#vAdaptivePreview')?.dataset.open==='true');
  assert.match(await page.locator('#vAdaptivePreview').innerText(),/Looks like Memory/);
  assert.match(await page.locator('#vAdaptivePreview .v-adaptive-action').innerText(),/Open Memory/);

  await page.locator('#vAdaptivePreview .v-adaptive-dismiss').click();
  assert.equal(await page.locator('#vAdaptivePreview').getAttribute('data-open'),'false');
  await page.locator('#message').fill('remember what we discussed last time please');
  await page.waitForFunction(()=>document.querySelector('#vAdaptivePreview')?.dataset.open==='true');

  await page.evaluate(()=>{
    window.__adaptiveCaptured=null;
    window.addEventListener('vishnu:adaptive-intent',event=>{
      window.__adaptiveCaptured=event.detail;
      event.preventDefault();
    },{once:true});
  });
  await page.locator('#vAdaptivePreview .v-adaptive-action').click();
  const captured=await page.evaluate(()=>window.__adaptiveCaptured);
  assert.equal(captured.intent,'memory');
  assert.match(captured.text,/remember what we discussed/i);

  await page.locator('#message').fill('research current battery technology with evidence and sources');
  await page.waitForFunction(()=>document.querySelector('#vAdaptivePreview')?.dataset.open==='true'&&document.querySelector('#vAdaptivePreview')?.dataset.intent==='research');
  await page.evaluate(()=>{
    window.__canonicalSendClicks=0;
    document.getElementById('sendButton').addEventListener('click',event=>{
      window.__canonicalSendClicks+=1;
      event.preventDefault();
      event.stopImmediatePropagation();
    },true);
  });
  assert.match(await page.locator('#vAdaptivePreview .v-adaptive-action').innerText(),/Continue with Vishnu/);
  await page.locator('#vAdaptivePreview .v-adaptive-action').click();
  assert.equal(await page.evaluate(()=>window.__canonicalSendClicks),1,'non-navigation intents must use the canonical Send path');

  const mobile=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:2,isMobile:true,hasTouch:true,serviceWorkers:'block'});
  await wire(mobile);
  await mobile.goto('http://127.0.0.1:4173/iphone/',{waitUntil:'domcontentloaded'});
  await mobile.waitForFunction(()=>Boolean(window.vishnuAdaptiveComposer));
  await mobile.locator('#message').fill('remind me tomorrow at 9');
  await mobile.waitForFunction(()=>document.querySelector('#vAdaptivePreview')?.dataset.open==='true');
  const previewBox=await mobile.locator('#vAdaptivePreview').boundingBox();
  const composerBox=await mobile.locator('#composer').boundingBox();
  assert.ok(previewBox&&composerBox&&previewBox.y<composerBox.y,'mobile intent preview stays above the composer');
  assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'adaptive preview introduces no horizontal overflow');
  await mobile.close();

  assert.deepEqual(errors,[],'adaptive composer browser flow has no uncaught errors');
  console.log('Adaptive universal composer desktop/mobile checks passed.');
}finally{
  await browser.close();
}
