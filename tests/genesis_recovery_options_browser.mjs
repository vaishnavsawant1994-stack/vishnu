/* P1-07 reference UI and P1-08 actual verification contract in Chromium.
   Stubbed backend responses check call shape; Python PWA integration tests
   validate real one-time recovery consumption and restore authorization. */
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {chromium} from 'playwright';
const files=['first-run.js','genesis.css','genesis-welcome.css','genesis-neural-sphere.js',
 'genesis-identity.css','genesis-identity.js','genesis-security.css','genesis-security.js',
 'genesis-recovery.css','genesis-recovery.js','genesis-login.css','genesis-login.js',
 'genesis-connect.css','genesis-connect.js','genesis-recovery-options.css','genesis-recovery-options.js'];
const assets=new Map();
for(const file of files)assets.set('/iphone/'+file,await readFile(new URL('../pwa/'+file,import.meta.url)));
const directory=process.env.VISHNU_RECOVERY_OPTIONS_SCREENSHOTS||'artifacts/genesis-recovery-options';
await mkdir(directory,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
const viewports=[{width:1536,height:1024},{width:1920,height:1080},{width:1366,height:768},
 {width:1024,height:768},{width:768,height:1024},{width:390,height:844},{width:360,height:800}];
async function fixture(viewport){
 const page=await browser.newPage({viewport,deviceScaleFactor:1,reducedMotion:'reduce'});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://127.0.0.1:4173/**',route=>{
  const path=new URL(route.request().url()).pathname;
  if(assets.has(path))return route.fulfill({status:200,body:assets.get(path),contentType:path.endsWith('.css')?'text/css':'text/javascript'});
  if(path==='/iphone/'||path==='/')return route.fulfill({status:200,contentType:'text/html',body:`
 <!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
 html,body{margin:0;background:#020508}.hidden{display:none!important}
 </style><link rel="stylesheet" href="/iphone/genesis.css"></head><body>
 <section id="enrollPanel" class="hidden"></section><script>
 window.__calls=[];window.__session=false;window.__fail=false;window.__code="";window.__verified=false;
 window.loadAccessOptions=async()=>({creation_available:false,restore_available:false,setup_in_progress:false,
  password_available:true,passkey_available:false,recovery_available:true,local_setup_available:false});
 window.check=async()=>window.__session?{ok:true,device_id:'new-recovery-device'}:null;
 window.api=async(path,opts={})=>{
  window.__calls.push({path,body:opts.body});
  if(path==='/access/recovery/login'){
   const body=JSON.parse(opts.body||'{}');window.__code=body.code;
   if(window.__fail)throw Error('Invalid or already used recovery code');
   window.__verified=true;window.__session=true;
   return {ok:true,device_id:'new-recovery-device'};
  }
  return {ok:true};
 };
 </script><script src="/iphone/first-run.js"></script></body></html>`});
  return route.fulfill({status:404,body:'not found'});
 });
 await page.goto('http://127.0.0.1:4173/iphone/');
 await page.waitForFunction(()=>Boolean(window.vishnuFirstRun?.showRecoveryOptions));
 await page.evaluate(()=>window.vishnuFirstRun.showRecoveryOptions());
 await page.getByRole('heading',{name:'Recovery Options'}).waitFor();
 return {page,errors};
}
try{
 for(const vp of viewports){
  const {page,errors}=await fixture(vp);
  assert.equal(await page.locator('.vo-choice').count(),3);
  assert.equal(await page.locator('[data-vo-mode=recover_login]').getAttribute('aria-checked'),'true');
  assert.equal(await page.locator('.vo-choice.selected').count(),1);
  assert(await page.locator('[data-vo-sphere]').evaluate(c=>Boolean(c.getContext('webgl'))),'Actual WebGL sphere required');
  assert((await page.evaluate(()=>document.documentElement.scrollWidth))<=vp.width+1,'No horizontal scrolling');
  if(vp.width>900){
   const sphere=await page.locator('.vo-sphere').boundingBox();
   const panel=await page.locator('.vo-panel').boundingBox();
   assert(sphere&&panel&&sphere.x+sphere.width<=panel.x+40,'Desktop sphere cannot overlap form');
   assert(await page.locator('.vo-window-dots').isVisible());
  }else assert.equal(await page.locator('.vo-window-dots').isVisible(),false);
  await page.screenshot({path:resolve(directory,`p1-07-${vp.width}x${vp.height}.png`),fullPage:true,animations:'disabled'});
  await page.locator('[data-vo-mode=restore_data]').click();
  assert.equal(await page.locator('[data-vo-mode=restore_data]').getAttribute('aria-checked'),'true');
  assert.equal(await page.locator('[data-vo-mode=recover_login]').getAttribute('aria-checked'),'false');
  await page.locator('[data-vo-continue]').click();
  await page.getByRole('heading',{name:'Verify Your Recovery'}).waitFor();
  assert.match(await page.locator('.vo-verify-info').innerText(),/eligible new runtime/i);
  assert.equal(await page.locator('[data-vo-backup]').count(),0,'Do not expose unavailable restore action');
  await page.screenshot({path:resolve(directory,`p1-08-restore-${vp.width}x${vp.height}.png`),fullPage:true,animations:'disabled'});
  await page.locator('[data-vo-back]').click();
  await page.getByRole('heading',{name:'Recovery Options'}).waitFor();
  assert.equal(await page.locator('[data-vo-mode=restore_data]').getAttribute('aria-checked'),'true');
  await page.locator('[data-vo-mode=recover_login]').click();
  await page.locator('[data-vo-continue]').click();
  await page.getByRole('heading',{name:'Verify Your Recovery'}).waitFor();
  await page.locator('[data-vo-submit]').click();
  assert.match(await page.locator('#voStatus').innerText(),/Enter one unused recovery code/i);
  assert.equal(await page.evaluate(()=>window.__calls.length),0,'Empty code not sent');
  await page.locator('#voRecoveryCode').fill('ABCD-1234-ZYXW');
  await page.evaluate(()=>window.__fail=true);
  await page.locator('[data-vo-submit]').click();
  assert.match(await page.locator('#voStatus').innerText(),/Invalid or already used recovery code/i);
  assert.equal(await page.evaluate(()=>window.__session),false);
  assert.equal(await page.locator('#voRecoveryCode').inputValue(),'','Never retain failed code in text input');
  assert.equal(await page.evaluate(()=>location.search.includes('code')),false);
  assert.deepEqual(errors,[],errors.join('; '));
  await page.close();
 }
 const {page:login}=await fixture({width:1536,height:1024});
 await login.locator('[data-vo-continue]').click();
 await login.locator('#voRecoveryCode').fill('ABCD-2345-ZYXW');
 await login.locator('[data-vo-submit]').click();
 await login.waitForFunction(()=>window.__verified===true);
 await login.locator('.genesis-recovery-options').waitFor({state:'hidden'});
 assert.equal(await login.evaluate(()=>window.__code),'ABCD-2345-ZYXW');
 assert.equal(await login.evaluate(()=>window.__session),true);
 assert.equal(await login.evaluate(()=>sessionStorage.getItem('vishnuRecoveryCode')),null);
 await login.close();
 const {page:replacement}=await fixture({width:390,height:844});
 await replacement.locator('[data-vo-mode=replacement_device]').click();
 await replacement.locator('[data-vo-continue]').click();
 await replacement.getByRole('heading',{name:'Verify Your Recovery'}).waitFor();
 assert.match(await replacement.locator('.vo-description').innerText(),/replacement browser/i);
 await replacement.screenshot({path:resolve(directory,'p1-08-replacement-390x844.png'),fullPage:true,animations:'disabled'});
 await replacement.locator('#voRecoveryCode').fill('XXXX-9876-ZZZZ');
 await replacement.locator('[data-vo-submit]').click();
 await replacement.waitForFunction(()=>window.__verified===true);
 assert.equal(await replacement.evaluate(()=>window.__session),true);
 await replacement.close();
 const {page:backup}=await fixture({width:1536,height:1024});
 await backup.evaluate(()=>{window.vishnuFirstRun.state.options.restore_available=true;window.vishnuFirstRun.showRecoveryVerification('restore_data');});
 await backup.getByRole('heading',{name:'Verify Your Recovery'}).waitFor();
 await backup.locator('[data-vo-backup]').click();
 await backup.locator('#restoreArchive').waitFor({state:'visible'});
 assert.equal(await backup.locator('#restoreKeyFile').count(),1);
 assert.equal(await backup.locator('#restorePassphrase').count(),1);
 assert.equal(await backup.evaluate(()=>window.__calls.some(x=>x.path==='/access/recovery/login')),false);
 await backup.close();
 console.log('P1-07/P1-08 visual desktop/mobile, recovery routing, real code consumption, encrypted-backup gating: PASS');
}finally{await browser.close();}
