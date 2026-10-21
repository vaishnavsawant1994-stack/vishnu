/* P1-05 real browser UI tests. Synthetic account/API and platform credential fixtures
   are isolated to Playwright. Server owner/device enforcement is tested separately. */
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {chromium} from 'playwright';
const assets=['first-run.js','first-run-actions.js','genesis.css','genesis-welcome.css',
 'genesis-neural-sphere.js','genesis-identity.css','genesis-identity.js','genesis-security.css',
 'genesis-security.js','genesis-recovery.css','genesis-recovery.js','genesis-login.css',
 'genesis-login.js','genesis-connect.css','genesis-connect.js','assets/genesis/avatar-blue.svg','assets/genesis/avatar-mountain.svg',
 'assets/genesis/avatar-forest.svg','assets/genesis/avatar-horizon.svg'];
const files=new Map();
for(const name of assets)files.set('/iphone/'+name,await readFile(new URL('../pwa/'+name,import.meta.url)));
const output=process.env.VISHNU_LOGIN_SCREENSHOTS||'artifacts/genesis-login';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
const viewports=[{width:1536,height:1024},{width:1920,height:1080},{width:1440,height:900},
 {width:1280,height:800},{width:768,height:1024},{width:390,height:844},{width:375,height:812}];
const fixturePage=async(vp)=>{
 const page=await browser.newPage({viewport:vp,reducedMotion:'reduce',deviceScaleFactor:1});
 const exceptions=[];page.on('pageerror',e=>exceptions.push(e.message));
 await page.route('http://127.0.0.1:4173/**',route=>{
  const url=new URL(route.request().url());
  if(files.has(url.pathname))return route.fulfill({status:200,body:files.get(url.pathname),
   contentType:url.pathname.endsWith('.css')?'text/css':url.pathname.endsWith('.svg')?'image/svg+xml':'text/javascript'});
  if(url.pathname==='/'||url.pathname==='/iphone/')return route.fulfill({status:200,contentType:'text/html',
    body:`<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
     <style>html,body{margin:0;background:#020509;min-height:100%}.hidden{display:none!important}</style>
     <link rel="stylesheet" href="/iphone/genesis.css"></head><body>
     <section id="enrollPanel" class="hidden"></section><script>
       window.__mode='normal';window.__session=false;window.__calls=[];window.__opened=[];
       window.vishnuChatBridge={openModule:name=>window.__opened.push(name)};
       window.loadAccessOptions=async()=>({password_available:true,passkey_available:true,
         recovery_available:true,creation_available:false,setup_in_progress:false});
       window.check=async()=>window.__session?{ok:true,device_id:'trusted-browser'}:null;
       window.api=async(path,options={})=>{
         window.__calls.push({path,body:options.body});
         if(path==='/access/password/login'){
           const payload=JSON.parse(options.body);
           if(payload.password==='incorrect')throw new Error('Incorrect owner password');
           if(window.__mode==='approval')return {status:'approval_required',
             request_id:'00000000-0000-0000-0000-000000000001',verification_code:'AB1234',name:'Laptop',
             expires_at:'2027-12-01T00:00:00Z'};
           window.__session=true;return {ok:true,device_id:'trusted-browser'};
         }
         if(path==='/access/passkey/login/options')return {challenge_id:'synthetic-challenge',
           public_key:{challenge:'AQID',rpId:'localhost',allowCredentials:[{type:'public-key',id:'AQID'}],
             timeout:60000,userVerification:'required'}};
         if(path==='/access/passkey/login/complete'){window.__session=true;return {ok:true,device_id:'trusted-browser'};}
         return {ok:true};
       };
     </script><script src="/iphone/first-run.js"></script>
     <script src="/iphone/first-run-actions.js"></script></body></html>`});
  return route.fulfill({status:404,body:'not found'});
 });
 await page.goto('http://127.0.0.1:4173/iphone/');
 await page.waitForFunction(()=>Boolean(window.vishnuFirstRun?.showLogin));
 // An existing owner without a trusted session must be taken directly to
 // P1-05; the user should not have to manually enter a test-only route.
 await page.locator('.genesis-login .vl-panel').waitFor();
 assert.equal(await page.locator('.genesis-login').count(),1);
 return {page,exceptions};
};
try{
 for(const vp of viewports){
  const {page,exceptions}=await fixturePage(vp);
  assert.equal(await page.getByRole('heading',{name:'Unlock Vishnu'}).count(),1);
  assert.equal(await page.locator('[aria-current=step]').innerText(),'5\nLogin');
  assert.equal(await page.locator('.vl-tabs [aria-selected=true]').innerText(),'Password');
  assert.equal(await page.locator('[data-vl-sphere]').count(),1);
  assert(await page.locator('[data-vl-sphere]').evaluate(c=>Boolean(c.getContext('webgl'))),
   'P1-05 reuses a real WebGL neural sphere');
  assert.equal(await page.locator('#vlRemember').isChecked(),false,'Remember cannot imply automatic trust');
  assert.match(await page.locator('[data-vl-trust-title]').innerText(),/checked on sign-in/i);
  const width=await page.evaluate(()=>document.documentElement.scrollWidth);
  assert(width<=vp.width+1,'Horizontal overflow at '+vp.width+': '+width);
  await page.screenshot({path:resolve(output,`p1-05-${vp.width}x${vp.height}.png`),fullPage:true,animations:'disabled'});
  if(vp.width>900){
   const sphere=await page.locator('.vl-sphere').boundingBox();
   const panel=await page.locator('.vl-panel').boundingBox();
   assert(sphere&&panel&&sphere.x+sphere.width<=panel.x+15,
    'Desktop sphere must be beside rather than behind login panel');
   assert.equal(await page.locator('.vl-back').isVisible(),true);
  }else{
   const sphere=await page.locator('.vl-sphere').boundingBox();
   const hero=await page.locator('.vl-hero').boundingBox();
   assert(sphere&&hero&&sphere.y>=hero.y-1&&sphere.y+sphere.height<=hero.y+hero.height+1,
    'Mobile sphere must fit inside visual region');
   await page.locator('.vl-mobile-back').scrollIntoViewIfNeeded();
   const bottom=await page.locator('.vl-mobile-back').boundingBox();
   assert(bottom&&bottom.y>=0&&bottom.y+bottom.height<=vp.height+1);
  }
  if(vp.width<=900){
    await page.screenshot({path:resolve(output,`p1-05-mobile-bottom-${vp.width}x${vp.height}.png`),animations:'disabled'});
  }
  await page.locator('[data-vl-submit]').click();
  assert.match(await page.locator('#vlPasswordError').innerText(),/enter your owner password/i);
  assert.equal(await page.evaluate(()=>window.__calls.filter(c=>c.path==='/access/password/login').length),0);
  await page.locator('#vlPassword').fill('incorrect');
  assert.equal(await page.locator('#vlPassword').getAttribute('type'),'password');
  await page.locator('[data-vl-visibility]').click();
  assert.equal(await page.locator('#vlPassword').getAttribute('type'),'text');
  await page.locator('[data-vl-visibility]').click();
  assert.equal(await page.locator('#vlPassword').getAttribute('type'),'password');
  await page.locator('[data-vl-submit]').click();
  await page.waitForFunction(()=>document.querySelector('#returningStatus')?.textContent.includes('Incorrect owner password'));
  assert.equal(await page.locator('#vlPassword').inputValue(),'','Password must not remain in DOM after submit');
  assert.equal(await page.evaluate(()=>window.__session),false);
  await page.locator('[data-vl-tab=passkey]').click();
  assert.equal(await page.locator('#vlPasswordPanel').isHidden(),true);
  assert.equal(await page.locator('#vlPasskeyPanel').isVisible(),true);
  await page.locator('[data-vl-tab=biometric]').click();
  assert.equal(await page.locator('#vlBiometricPanel').isVisible(),true);
  await page.locator('[data-vl-tab=password]').click();
  assert.equal(await page.locator('#vlPasswordPanel').isVisible(),true);
  await page.locator('[data-vl-devices]').click();
  assert.match(await page.locator('#returningStatus').innerText(),/sign in first/i);
  await page.locator('#vlRemember').check();
  assert.match(await page.locator('#returningStatus').innerText(),/cannot bypass approval/i);
  assert.equal(await page.evaluate(()=>window.__calls.filter(c=>c.path==='/access/password/login').length),1);
  await page.locator('#vlPassword').fill('correct-owner-password');
  await page.locator('#vlPassword').press('Enter');
  await page.waitForFunction(()=>window.__session===true);
  await page.waitForFunction(()=>window.__opened.includes('devices'));
  const calls=await page.evaluate(()=>window.__calls);
  const login=calls.filter(c=>c.path==='/access/password/login');
  assert.equal(login.length,2);
  const data=JSON.parse(login[1].body);
  assert.deepEqual(Object.keys(data).sort(),['name','password']);
  assert.equal(data.password,'correct-owner-password');
  assert.deepEqual(exceptions,[],exceptions.join('; '));
  await page.close();
 }
 // Explicit trust boundary: even a valid password on an unknown device
 // requests approval; the frontend must not open Vishnu Home.
 const {page:join}=await fixturePage({width:1536,height:1024});
 await join.evaluate(()=>{window.__mode='approval';});
 await join.locator('#vlPassword').fill('owner-authenticated');
 await join.locator('[data-vl-submit]').click();
 await join.locator('#vcVerificationCode').waitFor();
 assert.match(await join.locator('.vc-request').innerText(),/trusted device/i);
 assert.equal(await join.evaluate(()=>window.__session),false);
 await join.close();
 // A mocked authenticator verifies that passkey login serializes a real
 // challenge and credential response instead of simulating UI success.
 const {page:auth}=await fixturePage({width:1536,height:1024});
 await auth.evaluate(()=>{
  window.PublicKeyCredential=class FakePasskey{};
  Object.defineProperty(navigator,'credentials',{configurable:true,value:{get:async({publicKey})=>{
    window.__challengeOK=publicKey.challenge instanceof Uint8Array&&publicKey.userVerification==='required';
    return {id:'AQID',type:'public-key',rawId:Uint8Array.of(1,2,3).buffer,
      response:{clientDataJSON:Uint8Array.of(4,5,6).buffer,
        authenticatorData:Uint8Array.of(7,8,9).buffer,signature:Uint8Array.of(10,11,12).buffer,
        userHandle:null},getClientExtensionResults:()=>({})};
  }}});
  window.vishnuFirstRun.showLogin();
 });
 await auth.locator('[data-vl-passkey]').click();
 await auth.waitForFunction(()=>window.__calls.some(x=>x.path==='/access/passkey/login/complete'));
 assert.equal(await auth.evaluate(()=>window.__challengeOK),true);
 const result=await auth.evaluate(()=>window.__calls.find(x=>x.path==='/access/passkey/login/complete'));
 const body=JSON.parse(result.body);
 assert.equal(body.credential.response.signature,'CgsM');
 assert.equal(body.credential.response.authenticatorData,'BwgJ');
 assert.equal(body.credential.response.clientDataJSON,'BAUG');
 await auth.close();
 // Recovery and Back keep owner identity intact and return to approved entry.
 const {page:recover}=await fixturePage({width:390,height:844});
 await recover.locator('[data-vl-recovery]').click();
 await recover.getByRole('heading',{name:'Recover owner access'}).waitFor();
 assert.equal(await recover.locator('#recoveryCode').count(),1);
 await recover.close();
 const {page:back}=await fixturePage({width:1536,height:1024});
 await back.locator('.vl-back').click();
 await back.getByRole('heading',{name:'Welcome to Vishnu.'}).waitFor();
 await back.close();
 // Explicit fallback with no configured passkey: no fake ceremony or
 // credential is attempted.
 const {page:unsupported}=await fixturePage({width:1536,height:1024});
 await unsupported.evaluate(()=>{
   window.PublicKeyCredential=undefined;
   window.vishnuFirstRun.showLogin();
 });
 await unsupported.locator('[data-vl-passkey]').click();
 assert.match(await unsupported.locator('#returningStatus').innerText(),/unavailable/i);
 assert.equal(await unsupported.evaluate(()=>window.__calls.some(x=>x.path==='/access/passkey/login/options')),false);
 await unsupported.close();
 // Authenticator cancellation must return safely to the login form.
 const {page:cancelled}=await fixturePage({width:1536,height:1024});
 await cancelled.evaluate(()=>{
   window.PublicKeyCredential=class FakePasskey{};
   Object.defineProperty(navigator,'credentials',{configurable:true,value:{
     get:async()=>{const err=new Error('not permitted');err.name='NotAllowedError';throw err;}
   }});
   window.vishnuFirstRun.showLogin();
 });
 await cancelled.locator('[data-vl-passkey]').click();
 await cancelled.waitForFunction(()=>document.querySelector('#returningStatus')?.textContent.includes('cancelled'));
 assert.equal(await cancelled.locator('.vl-panel').isVisible(),true);
 assert.equal(await cancelled.evaluate(()=>window.__session),false);
 await cancelled.close();
 console.log('P1-05 desktop/mobile/WebGL/password/passkey/trust/recovery/cancellation browser qualification: PASS');
}finally{await browser.close();}
