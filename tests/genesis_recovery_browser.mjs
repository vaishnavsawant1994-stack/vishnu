/* P1-04 recovery presentation/browser contract qualification.
 * TEST CODES below are mocked fixtures, not issued credentials.
 * Real server verification is separately in test_p3_iphone_pwa.py. */
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {chromium} from 'playwright';
const assets=['first-run.js','first-run-actions.js','genesis.css','genesis-welcome.css',
 'genesis-neural-sphere.js','genesis-identity.css','genesis-identity.js',
 'genesis-security.css','genesis-security.js','genesis-recovery.css','genesis-recovery.js','genesis-login.js','genesis-login.css','genesis-connect.css','genesis-connect.js','genesis-recovery-options.css','genesis-recovery-options.js','genesis-verification.css','genesis-verification.js',
 'assets/genesis/avatar-blue.svg','assets/genesis/avatar-mountain.svg',
 'assets/genesis/avatar-forest.svg','assets/genesis/avatar-horizon.svg'];
const files=new Map();
for(const name of assets)files.set('/iphone/'+name,await readFile(new URL('../pwa/'+name,import.meta.url)));
const first=['A2BC-D3EF-G4HJ','B3CD-E4FG-H5JK','C4DE-F5GH-J6KL','D5EF-G6HJ-K7LM',
 'E6FG-H7JK-L8MN','F7GH-J8KL-M9NP','G8HJ-K9LM-N2PQ','H9JK-L2MN-P3QR'];
const second=['J2KL-M3NP-Q4RS','K3LM-N4PQ-R5ST','L4MN-P5QR-S6TU','M5NP-Q6RS-T7UV',
 'N6PQ-R7ST-U8VW','P7QR-S8TU-V9WX','Q8RS-T9UV-W2XY','R9ST-U2VW-X3YZ'];
const out=process.env.VISHNU_RECOVERY_SCREENSHOTS||'artifacts/genesis-recovery';
await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
const viewports=[{width:1536,height:1024},{width:1920,height:1080},{width:1366,height:768},
 {width:768,height:1024},{width:390,height:844},{width:360,height:800}];
try{
 for(const vp of viewports){
  const page=await browser.newPage({viewport:vp,reducedMotion:'reduce',acceptDownloads:true});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
    window.__copied=[];
    Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async s=>{window.__copied.push(s);}}});
  });
  await page.route('http://127.0.0.1:4173/**',route=>{
   const path=new URL(route.request().url()).pathname;
   if(files.has(path))return route.fulfill({status:200,contentType:path.endsWith('.css')?'text/css':path.endsWith('.svg')?'image/svg+xml':'text/javascript',body:files.get(path)});
   if(path==='/'||path==='/iphone/')return route.fulfill({status:200,contentType:'text/html',
      body:`<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
      <style>body,html{margin:0;background:#020509;min-height:100%}.hidden{display:none!important}</style>
      <link rel="stylesheet" href="/iphone/genesis.css"></head><body>
      <section id="enrollPanel" class="hidden"></section>
      <section class="genesis-content hidden" aria-hidden="true"></section>
      <script>
      window.loadAccessOptions=async()=>({creation_available:true,local_setup_available:true});
      window.check=async()=>null;window.__apiCalls=[];
      window.api=async(path,options={})=>{
       window.__apiCalls.push({path,method:options.method,body:options.body});
       if(path==='/first-run/create')return {ok:true,recovery_codes:${JSON.stringify(first)}};
       if((path==='/first-run/recovery-codes'||path==='/first-run/recovery-saved')&&window.__requireSetupReauth){
        window.__requireSetupReauth=false;
        throw new Error('The first-device setup session expired');
       }
       if(path==='/first-run/resume'&&!JSON.parse(options.body||'{}').password)
        throw new Error('This browser needs owner-password verification to resume setup');
       if(path==='/first-run/recovery-codes')return {shown_once:true,recovery_codes:${JSON.stringify(second)}};
       return {ok:true};
      };
      </script><script src="/iphone/first-run.js"></script><script src="/iphone/first-run-actions.js"></script>
      </body></html>`});
   return route.fulfill({status:404,body:'not found'});
  });
  await page.goto('http://127.0.0.1:4173/iphone/?genesisStep=2');
  await page.locator('.genesis-identity .vi-form').waitFor();
  await page.locator('#firstRunFirstName').fill('Test Owner');
  await page.locator('.vi-continue').click();
  await page.locator('.genesis-security .vs-main').waitFor({timeout:5000}).catch(async error=>{
    console.error('Step 3 screen debug:', await page.locator('#enrollPanel').innerText(), errors);
    throw error;
  });
  await page.locator('#firstRunPassword').fill('Tru5t!Sample$519876');
  await page.locator('#firstRunPasswordAgain').fill('Tru5t!Sample$519876');
  await page.locator('#vsDeviceName').fill('My Test Laptop');
  await page.locator('.vs-continue').click();
  await page.locator('.genesis-recovery-screen .vr-panel').waitFor();
  assert.equal(await page.getByRole('heading',{name:'Save Your Recovery Codes'}).count(),1);
  assert.equal(await page.locator('.vs-progress [aria-current=step]').innerText(),'4\nRecovery');
  assert.equal(await page.locator('[data-vr-sphere]').count(),1);
  assert(await page.locator('[data-vr-sphere]').evaluate(el=>Boolean(el.getContext('webgl'))),'Neural sphere must remain real WebGL');
  assert.equal(await page.locator('.vr-code').count(),first.length);
  assert.equal(await page.locator('#firstRunRecoverySaved').isChecked(),false,'New codes must not be pre-acknowledged');
  const width=await page.evaluate(()=>document.documentElement.scrollWidth);
  assert(width<=vp.width+1,'No horizontal overflow at '+vp.width+': '+width);
  if(vp.width>900)assert.equal(await page.locator('.vr-code-grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),3);
  else {
    assert.equal(await page.locator('.vr-code-grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),2);
    const globe=await page.locator('.vs-sphere').boundingBox();
    const hero=await page.locator('.vs-hero').boundingBox();
    assert(globe&&hero&&globe.y>=hero.y-1&&globe.y+globe.height<=hero.y+hero.height+1,
      'Mobile WebGL globe must fit fully inside its visual region: '+JSON.stringify({globe,hero}));
  }
  await page.screenshot({path:resolve(out,`p1-04-${vp.width}x${vp.height}.png`),fullPage:true,animations:'disabled'});
  if(vp.width<=900){
    await page.locator('.vr-nav').scrollIntoViewIfNeeded();
    const bb=await page.locator('.vr-nav').boundingBox();
    assert(bb&&bb.y>=0&&bb.y+bb.height<=vp.height+1,'Bottom actions must be reachable by scrolling');
    await page.screenshot({path:resolve(out,`p1-04-mobile-bottom-${vp.width}x${vp.height}.png`),animations:'disabled'});
  }
  await page.locator('.vr-nav .vs-continue').click();
  assert.match(await page.locator('#genesisStatus').innerText(),/acknowledgement|check/i);
  assert.equal(await page.evaluate(()=>window.__apiCalls.filter(x=>x.path==='/first-run/complete').length),0);
  await page.locator('.vr-copy').first().click();
  assert.equal((await page.evaluate(()=>window.__copied))[0],first[0]);
  await page.locator('[data-vr-copy-all]').click();
  const clipboard=await page.evaluate(()=>window.__copied.at(-1));
  assert(clipboard.startsWith('01  '+first[0])&&clipboard.includes('08  '+first[7]));
  const download=page.waitForEvent('download');
  await page.locator('[data-vr-download]').click();
  const file=await download;
  assert.equal(file.suggestedFilename(),'Vishnu-Recovery-Codes.txt');
  assert.match(await page.locator('#genesisStatus').innerText(),/file prepared/i);
  await page.locator('[data-vr-review]').click();
  await page.locator('#vrReviewDialog').waitFor({state:'visible'});
  assert.match(await page.locator('#vrReviewRows').innerText(),/My Test Laptop/);
  assert(!/Tru5t!Sample/.test(await page.locator('#vrReviewRows').innerText()));
  await page.locator('[data-vr-review-close]').click();
  await page.locator('[data-vr-regenerate]').click();
  assert.equal(await page.locator('#vrRegenerateDialog').evaluate(x=>x.open),true);
  assert.equal(await page.evaluate(()=>window.__apiCalls.filter(x=>x.path==='/first-run/recovery-codes').length),0);
  await page.locator('[data-vr-cancel]').click();
  assert.equal(await page.evaluate(()=>window.__apiCalls.filter(x=>x.path==='/first-run/recovery-codes').length),0,'Cancel is non-destructive');
  await page.evaluate(()=>{window.__requireSetupReauth=true;});
  await page.locator('#firstRunRecoverySaved').check();
  await page.locator('[data-vr-regenerate]').click();
  await page.locator('[data-vr-confirm]').click();
  await page.locator('[data-setup-device-reauth]').waitFor({state:'visible',timeout:5000}).catch(async error=>{
    console.error('Recovery reauth debug:', await page.locator('#genesisStatus').innerText(),
      await page.evaluate(()=>window.__apiCalls), errors);
    throw error;
  });
  assert.match(await page.locator('#genesisStatus').innerText(),/owner.?password|reconnect|verify your owner/i,
    'Recovery must explain that owner verification is needed, not report code rotation as the only failure');
  await page.getByRole('textbox',{name:'Owner password'}).waitFor({state:'visible'});
  await page.getByRole('textbox',{name:'Owner password'}).fill('Tru5t!Sample$519876');
  await page.getByRole('button',{name:'Reconnect this browser'}).click();
  await page.locator('#genesisStatus').getByText('Browser access restored').waitFor();
  await page.locator('[data-vr-regenerate]').click();
  await page.locator('[data-vr-confirm]').click();
  await page.waitForFunction(()=>document.querySelector('.vr-code code')?.textContent==='J2KL-M3NP-Q4RS');
  assert.equal(await page.locator('#firstRunRecoverySaved').isChecked(),false,'Rotation resets acknowledgement');
  assert.equal(await page.locator('.vr-code').count(),second.length);
  assert.equal(await page.evaluate(()=>window.__apiCalls.filter(x=>x.path==='/first-run/recovery-codes').length),2,
    'the failed request and explicit user retry must both reach the recovery-code endpoint');
  if(vp.width===1536){
    await page.locator('#firstRunRecoverySaved').check();
    await page.evaluate(()=>{window.__requireSetupReauth=true;});
    await page.locator('.vr-nav .vs-continue').click();
    await page.getByRole('textbox',{name:'Owner password'}).waitFor({state:'visible'});
    await page.getByRole('textbox',{name:'Owner password'}).fill('Tru5t!Sample$519876');
    await page.getByRole('button',{name:'Reconnect this browser'}).click();
    await page.locator('#genesisStatus').getByText('Browser access restored').waitFor();
    assert.equal(await page.evaluate(()=>window.__apiCalls.filter(x=>x.path==='/first-run/resume').length),4,
      'a failed silent resume must offer owner verification, then reconnect securely after entry');
    await page.locator('.vr-nav .vs-continue').click();
    await page.waitForFunction(()=>window.__apiCalls.some(x=>x.path==='/first-run/complete'));
    const calls=await page.evaluate(()=>window.__apiCalls);
    const saved=calls.findIndex(x=>x.path==='/first-run/recovery-saved');
    const final=calls.findIndex(x=>x.path==='/first-run/complete');
    assert(saved>=0&&final>saved,'Backend confirms recovery before completion');
    assert.equal(await page.locator('.vr-code').count(),0,'Codes are cleared after successful setup');
    const completion=JSON.parse(calls.find(x=>x.path==='/first-run/complete').body);
    assert.equal(completion.passkey_unavailable_confirmed,true,
      'Password-only P1-03 must finish without demanding a never-enrolled passkey');
    assert(!calls.some(x=>x.path==='/access/passkey/register/options'),
      'Optional passkey must not be enrolled implicitly at P1-04');
  }else{
    await page.locator('[data-vr-back]').click();
    await page.locator('.genesis-security .vs-main').waitFor();
    await page.locator('.vs-continue').click();
    await page.locator('.genesis-recovery-screen .vr-panel').waitFor();
    assert.equal(await page.locator('.vr-code').count(),second.length,'Back keeps one-time codes in current memory only');
    assert.equal(await page.locator('#firstRunRecoverySaved').isChecked(),false);
  }
  assert.deepEqual(errors,[],errors.join('; '));
  await page.close();
 }

 // Regression: a browser whose first-device cookie/claim is no longer valid
 // must surface owner password reauthentication *in* P1-04. It must not
 // silently regenerate recovery codes or create a second account.
 const expired=await browser.newPage({viewport:{width:1366,height:768},reducedMotion:'reduce'});
 await expired.route('http://127.0.0.1:4173/**',route=>{
   const path=new URL(route.request().url()).pathname;
   if(files.has(path))return route.fulfill({status:200,contentType:path.endsWith('.css')?'text/css':path.endsWith('.svg')?'image/svg+xml':'text/javascript',body:files.get(path)});
   if(path==='/'||path==='/iphone/')return route.fulfill({status:200,contentType:'text/html',
     body:`<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
     <link rel="stylesheet" href="/iphone/genesis.css"></head><body>
     <section id="enrollPanel" class="hidden"></section><script>
       window.loadAccessOptions=async()=>({creation_available:true,local_setup_available:true});
       window.check=async()=>null;window.__apiCalls=[];window.__lostClaim=false;
       window.api=async(path,options={})=>{
         window.__apiCalls.push({path,body:options.body||''});
         if(path==='/first-run/create')return {ok:true,recovery_codes:${JSON.stringify(first)}};
         if(path==='/first-run/resume'){
           if(!JSON.parse(options.body||'{}').password)throw new Error('This browser needs owner-password verification to resume setup');
           window.__lostClaim=false;
           return {ok:true,status:'setup_in_progress'};
         }
         if(window.__lostClaim && path==='/first-run/recovery-saved')
           throw new Error('A verified first-device setup is required');
         return {ok:true,status:path==='/first-run/complete'?'ready':'ok'};
       };
     </script><script src="/iphone/first-run.js"></script><script src="/iphone/first-run-actions.js"></script>
     </body></html>`});
   return route.fulfill({status:404,body:'not found'});
 });
 await expired.goto('http://127.0.0.1:4173/iphone/?genesisStep=2');
 await expired.locator('#firstRunFirstName').fill('Recovery Owner');
 await expired.locator('.vi-continue').click();
 await expired.locator('#firstRunPassword').fill('Tru5t!Sample$519876');
 await expired.locator('#firstRunPasswordAgain').fill('Tru5t!Sample$519876');
 await expired.locator('.vs-continue').click();
 await expired.locator('.vr-panel').waitFor();
 await expired.evaluate(()=>window.__lostClaim=true);
 await expired.locator('#firstRunRecoverySaved').check();
 await expired.locator('.vr-nav .vs-continue').click();
 await expired.locator('[data-setup-device-reauth]').waitFor();
 assert.equal(await expired.locator('.vr-code').count(),8,'Unexpired displayed codes must not disappear on a failed finish');
 assert.match(await expired.locator('#genesisStatus').innerText(),/owner.password verification/i);
 await expired.locator('[data-setup-device-reauth] input[aria-label="Owner password"]').fill('Tru5t!Sample$519876');
 await expired.locator('[data-setup-device-reauth] button').click();
 await expired.getByText(/Browser access restored/).waitFor();
 assert.equal(await expired.locator('[data-setup-device-reauth]').count(),0);
 await expired.locator('.vr-nav .vs-continue').click();
 await expired.waitForFunction(()=>window.__apiCalls.some(c=>c.path==='/first-run/complete'));
 const log=await expired.evaluate(()=>window.__apiCalls);
 assert.equal(log.filter(c=>c.path==='/first-run/create').length,1);
 assert.equal(log.filter(c=>c.path==='/first-run/recovery-codes').length,0,'Reauthentication must not rotate codes');
 assert.equal(JSON.parse(log.find(c=>c.path==='/first-run/complete').body).passkey_unavailable_confirmed,true);
 await expired.close();

 console.log('P1-04 responsive, WebGL, one-time code controls, regeneration and backend flow: PASS');
}finally{await browser.close();}
