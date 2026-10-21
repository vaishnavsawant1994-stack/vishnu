/* P1-08: live Chromium screenshots and functional integration adapter checks.
 * Mock transport exercises the exact existing URI contracts; Python PWA tests
 * independently exercise the real backend authorization/recovery semantics.
 */
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {chromium} from 'playwright';
const names=['first-run.js','genesis.css','genesis-welcome.css','genesis-neural-sphere.js',
 'genesis-identity.css','genesis-identity.js','genesis-security.css','genesis-security.js',
 'genesis-recovery.css','genesis-recovery.js','genesis-login.css','genesis-login.js',
 'genesis-connect.css','genesis-connect.js','genesis-recovery-options.css','genesis-recovery-options.js',
 'genesis-verification.css','genesis-verification.js'];
const assets=new Map();
for(const name of names)assets.set('/iphone/'+name,await readFile(new URL('../pwa/'+name,import.meta.url)));
const output=process.env.VISHNU_VERIFICATION_SCREENSHOTS||'artifacts/genesis-verification';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
const sizes=[{width:1536,height:1024},{width:1920,height:1080},{width:1440,height:900},
 {width:1280,height:800},{width:768,height:1024},{width:390,height:844},
 {width:375,height:812},{width:320,height:700}];
async function fixture(viewport,{restore=false}={}){
 const page=await browser.newPage({viewport,deviceScaleFactor:1,reducedMotion:'reduce'});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://127.0.0.1:4173/**',route=>{
  const path=new URL(route.request().url()).pathname;
  if(assets.has(path))return route.fulfill({status:200,body:assets.get(path),
    contentType:path.endsWith('.css')?'text/css':'text/javascript'});
  if(path==='/iphone/'||path==='/')return route.fulfill({status:200,contentType:'text/html',
   body:`<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
    <style>html,body{margin:0;background:#020508}.hidden{display:none!important}</style>
    <link rel="stylesheet" href="/iphone/genesis.css"></head><body>
    <section id="enrollPanel" class="hidden"></section><script>
    window.__calls=[];window.__uploads=[];window.__verified=false;window.__session=false;window.__fail=false;
    window.loadAccessOptions=async()=>({creation_available:false,restore_available:${restore},
       setup_in_progress:false,recovery_available:${!restore},local_setup_available:true,
       password_available:${!restore},passkey_available:false});
    window.check=async()=>window.__session?{ok:true,device_id:'verified-recovery-browser'}:null;
    window.api=async(path,opts={})=>{
     window.__calls.push({path,body:opts.body});
     if(path==='/access/recovery/login'){
      if(window.__fail)throw Error('Invalid or already used recovery code');
      window.__verified=true;window.__session=true;
      return {ok:true,device_id:'verified-recovery-browser'};
     }
     if(path==='/first-run/restore/schedule')return {ok:true,status:'restart_required'};
     return {ok:true};
    };
    </script><script src="/iphone/first-run.js"></script></body></html>`});
  if(path==='/iphone/api/first-run/restore/archive')return route.fulfill({
   status:200,contentType:'application/json',body:JSON.stringify({ok:true,session_id:'valid-recovery-session-id_123456'})});
  if(path==='/iphone/api/first-run/restore/key')return route.fulfill({
   status:200,contentType:'application/json',body:'{"ok":true}'});
  return route.fulfill({status:404,body:'not found'});
 });
 await page.goto('http://127.0.0.1:4173/iphone/');
 await page.waitForFunction(()=>Boolean(window.vishnuFirstRun?.showRecoveryVerification));
 // Let the canonical initial check and owner-state routing finish before
 // deliberately entering P1-08. Otherwise initial login can unmount the
 // test page after P1-08 was shown, producing a false UI failure.
 if(restore)await page.locator('.genesis-screen[data-step="1"]').waitFor({state:'visible'});
 else await page.locator('.genesis-login .vl-panel').waitFor({state:'visible'});
 await page.evaluate(mode=>window.vishnuFirstRun.showRecoveryVerification(mode),restore?'restore_data':'recover_login');
 await page.locator('.genesis-verification .v8-method').first().waitFor({state:'visible'});
 await page.getByRole('heading',{name:'Recovery Verification'}).waitFor();
 return {page,errors};
}
try{
 for(const size of sizes){
  const {page,errors}=await fixture(size);
  assert.equal(await page.locator('.v8-method').count(),2,'Both reference methods always appear');
  assert.equal(await page.locator('[data-v8-group]').count(),6,'Six visual groups, two real code characters each');
  assert.equal(await page.locator('[data-v8-method=code]').evaluate(e=>e.classList.contains('selected')),true);
  assert.equal(await page.locator('input[type=password]').count()>=1,true);
  assert(await page.locator('[data-v8-sphere]').evaluate(c=>Boolean(c.getContext('webgl'))),'Shared genuine WebGL neural sphere');
  const actual=await page.evaluate(()=>document.documentElement.scrollWidth);
  assert(actual<=size.width+1,'Horizontal overflow '+size.width+' '+actual);
  if(size.width>900){
   const sphere=await page.locator('.vo-sphere').boundingBox(),panel=await page.locator('.vo-panel').boundingBox();
   assert(sphere&&panel&&sphere.x+sphere.width<=panel.x+40,'Sphere and form cannot overlap');
   const safety=await page.locator('.v8-safety').boundingBox();
   const primary=await page.locator('[data-v8-submit]').boundingBox();
   assert(safety&&primary&&safety.y+safety.height<=primary.y-2,
    'Desktop safety notice must never overlap Verify & Continue');
   assert(await page.locator('.vo-window-dots').isVisible());
  }else{
   assert.equal(await page.locator('.vo-window-dots').isVisible(),false);
   const last=await page.locator('[data-v8-group="5"]').boundingBox();
   const codeCard=await page.locator('[data-v8-method=code]').boundingBox();
   if(size.width>=350)assert(last&&codeCard&&last.x+last.width<=codeCard.x+codeCard.width-3,
    'Mobile last code input must not extend outside the card');
  }
  await page.screenshot({path:resolve(output,`p1-08-${size.width}x${size.height}.png`),fullPage:true,animations:'disabled'});
  if(size.width<=900){
   await page.locator('[data-v8-submit]').scrollIntoViewIfNeeded();
   const btn=await page.locator('[data-v8-submit]').boundingBox();
   assert(btn&&btn.y>=0&&btn.y+btn.height<=size.height+1,'Mobile Verify must be reachable after scrolling');
   await page.screenshot({path:resolve(output,`p1-08-mobile-action-${size.width}x${size.height}.png`),animations:'disabled'});
  }
  await page.locator('[data-v8-submit]').click();
  assert.match(await page.locator('#v8Status').innerText(),/complete 12-character/i);
  assert.equal(await page.evaluate(()=>window.__calls.length),0,'Empty code never submitted');
  // Six group inputs distribute one 4-4-4 code; backend sees its real format.
  await page.locator('[data-v8-group="0"]').fill('ABCD-EFGH-JKLM');
  assert.deepEqual(await page.locator('[data-v8-group]').evaluateAll(nodes=>nodes.map(n=>n.value)),
    ['AB','CD','EF','GH','JK','LM']);
  await page.evaluate(()=>window.__fail=true);
  await page.locator('[data-v8-submit]').click();
  assert.match(await page.locator('#v8Status').innerText(),/Invalid or already used/i);
  assert.equal(await page.evaluate(()=>window.__session),false);
  assert.deepEqual(await page.locator('[data-v8-group]').evaluateAll(nodes=>nodes.map(n=>n.value)),['','','','','',''],
    'Submitted code is wiped even if verification fails');
  await page.locator('[data-v8-select=backup]').click();
  assert.equal(await page.locator('[data-v8-method=backup]').evaluate(e=>e.classList.contains('selected')),true);
  await page.locator('[data-v8-submit]').click();
  assert.match(await page.locator('#v8Status').innerText(),/eligible Vishnu runtime/i);
  assert.equal(await page.evaluate(()=>window.__calls.length),1,'Unavailable restore must not call backend');
  assert.deepEqual(errors,[],'Browser page errors: '+errors.join('; '));
  await page.close();
 }
 const {page:login}=await fixture({width:1536,height:1024});
 await login.locator('[data-v8-group="0"]').fill('ABCD-EFGH-JKLM');
 await login.locator('[data-v8-submit]').click();
 await login.waitForFunction(()=>window.__verified===true);
 assert.equal(await login.evaluate(()=>window.__calls[0].path),'/access/recovery/login');
 assert.equal(await login.evaluate(()=>JSON.parse(window.__calls[0].body).code),'ABCD-EFGH-JKLM');
 await login.locator('.genesis-verification').waitFor({state:'hidden'});
 assert.equal(await login.evaluate(()=>window.__session),true);
 await login.close();
 const {page:backup}=await fixture({width:1536,height:1024},{restore:true});
 assert.equal(await backup.locator('[data-v8-method=backup]').evaluate(e=>e.classList.contains('selected')),true);
 await backup.locator('#v8Archive').setInputFiles({name:'verified-backup.vdr',mimeType:'application/octet-stream',buffer:Buffer.from('VISHNUDR1\nfixture')});
 await backup.locator('#v8KeyFile').setInputFiles({name:'separate-key.vrk',mimeType:'application/octet-stream',buffer:Buffer.from('VISHNU-RECOVERY-KEY-1\nfixture')});
 await backup.locator('#v8Passphrase').fill('this-is-a-test-passphrase');
 await backup.locator('[data-v8-submit]').click();
 await backup.waitForFunction(()=>window.__calls.some(x=>x.path==='/first-run/restore/schedule'));
 assert.match(await backup.locator('#v8Status').innerText(),/Restart the local Vishnu runtime/i);
 assert.equal(await backup.evaluate(()=>window.__calls.some(x=>x.path==='/access/recovery/login')),false,
  'Decrypting backup must not be confused with owner recovery-code authentication');
 assert.equal(await backup.evaluate(()=>JSON.parse(window.__calls.find(x=>x.path==='/first-run/restore/schedule').body).passphrase),
  'this-is-a-test-passphrase');
 assert.equal(await backup.locator('#v8Passphrase').inputValue(),'');
 await backup.screenshot({path:resolve(output,'p1-08-backup-selected-1536x1024.png'),fullPage:true,animations:'disabled'});
 await backup.close();
 console.log('P1-08: screenshot matrix, WebGL, six-two-character real code, no fake auth, two-file restore, error/memory cleanup: PASS');
}finally{await browser.close();}
