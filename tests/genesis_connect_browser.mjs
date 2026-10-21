/* P1-06 responsive and security-contract browser qualification.
   Only isolated fixtures are synthetic. No fake QR/token is rendered. */
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {chromium} from 'playwright';
const names=['first-run.js','genesis.css','genesis-welcome.css','genesis-neural-sphere.js',
 'genesis-identity.css','genesis-identity.js','genesis-security.css','genesis-security.js',
 'genesis-recovery.css','genesis-recovery.js','genesis-login.css','genesis-login.js',
 'genesis-connect.css','genesis-connect.js'];
const assets=new Map();
for(const name of names)assets.set('/iphone/'+name,await readFile(new URL('../pwa/'+name,import.meta.url)));
const dir=process.env.VISHNU_CONNECT_SCREENSHOTS||'artifacts/genesis-connect';
await mkdir(dir,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
const sizes=[{width:1536,height:1024},{width:1920,height:1080},{width:1366,height:768},
 {width:1024,height:768},{width:768,height:1024},{width:390,height:844},{width:360,height:800}];
const make=async viewport=>{
 const page=await browser.newPage({viewport,deviceScaleFactor:1,reducedMotion:'reduce'});
 const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://127.0.0.1:4173/**',route=>{
  const path=new URL(route.request().url()).pathname;
  if(assets.has(path))return route.fulfill({status:200,body:assets.get(path),contentType:path.endsWith('.css')?'text/css':'text/javascript'});
  if(path==='/iphone/'||path==='/')return route.fulfill({status:200,contentType:'text/html',
   body:`<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
   <style>html,body{margin:0;background:#020508}.hidden{display:none!important}</style>
   <link rel="stylesheet" href="/iphone/genesis.css"></head><body><section id="enrollPanel" class="hidden"></section>
   <script>
   window.__calls=[];window.__session=false;window.__approved=false;window.__cancelled=false;
   window.__testJoin={request_id:'00000000-0000-0000-0000-000000000001',verification_code:'A2B4C6',
       expires_at:Date.now()/1000+300,name:'New web browser',status:'approval_required'};
   window.loadAccessOptions=async()=>({creation_available:false,restore_available:false,
     password_available:true,passkey_available:true,recovery_available:true});
   window.check=async()=>window.__session?{ok:true,device_id:'verified-new-device'}:null;
   window.api=async(path,opts={})=>{
     window.__calls.push({path,body:opts.body});
     if(path==='/access/password/login')return window.__testJoin;
     if(path==='/access/join/status'){
       if(window.__cancelled)return {status:'denied'};
       if(window.__approved){window.__session=true;return {status:'complete',device_id:'verified-new-device'};}
       return {status:'pending'};
     }
     if(path==='/access/join/cancel'){window.__cancelled=true;return {status:'cancelled'};}
     return {ok:true};
   };
   </script><script src="/iphone/first-run.js"></script></body></html>`});
  return route.fulfill({status:404,body:'not found'});
 });
 await page.goto('http://127.0.0.1:4173/iphone/');
 await page.waitForFunction(()=>Boolean(window.vishnuFirstRun?.showConnect));
 await page.evaluate(()=>window.vishnuFirstRun.showConnect());
 await page.locator('.genesis-connect .vc-panel').waitFor();
 return {page,errors};
};
try{
 for(const viewport of sizes){
  const {page,errors}=await make(viewport);
  assert.equal(await page.getByRole('heading',{name:'Connect This Device'}).count(),1);
  assert.equal(await page.locator('.vc-method').count(),5);
  assert.equal(await page.locator('.vc-method.selected').count(),1);
  assert.equal(await page.locator('[data-vc-method=qr]').getAttribute('aria-checked'),'true');
  assert.equal(await page.locator('.vc-qr-symbol small').innerText(),'QR pairing\nnot issued');
  assert.equal(await page.locator('img[src*="qr"]').count(),0,'Never fabricate a QR code');
  assert(await page.locator('[data-vc-sphere]').evaluate(node=>Boolean(node.getContext('webgl'))),'Real WebGL sphere');
  const width=await page.evaluate(()=>document.documentElement.scrollWidth);
  assert(width<=viewport.width+1,'Horizontal overflow '+viewport.width+' '+width);
  if(viewport.width>900){
    const sphere=await page.locator('.vc-sphere').boundingBox();
    const panel=await page.locator('.vc-panel').boundingBox();
    assert(sphere&&panel&&sphere.x+sphere.width<=panel.x+30,'Globe overlaps the desktop panel');
    assert(await page.locator('.vc-desktop-back').isVisible());
  }else{
    const sphere=await page.locator('.vc-sphere').boundingBox();
    const hero=await page.locator('.vc-hero').boundingBox();
    assert(sphere&&hero&&sphere.y>=hero.y-1&&sphere.y+sphere.height<=hero.y+hero.height+1,'Mobile globe cropped');
  }
  await page.screenshot({path:resolve(dir,`p1-06-${viewport.width}x${viewport.height}.png`),
    fullPage:true,animations:'disabled'});
  await page.locator('[data-vc-continue]').click();
  assert.match(await page.locator('#vcStatus').innerText(),/QR pairing is not supported/i);
  assert.equal(await page.evaluate(()=>window.__calls.length),0,'QR placeholder must not create an unauthorized request');
  for(const m of ['code','link']){
   await page.locator('[data-vc-method='+m+']').click();
   await page.locator('[data-vc-continue]').click();
   assert.match(await page.locator('#vcStatus').innerText(),/runtime/i);
   assert.equal(await page.evaluate(()=>window.__calls.length),0);
  }
  await page.locator('[data-vc-method=approval]').click();
  assert.equal(await page.locator('[data-vc-method=approval]').getAttribute('aria-checked'),'true');
  await page.locator('[data-vc-continue]').click();
  await page.getByRole('heading',{name:'Unlock Vishnu'}).waitFor();
  await page.locator('#vlPassword').fill('valid password');
  await page.locator('[data-vl-submit]').click();
  await page.locator('.vc-request').waitFor({state:'visible'});
  assert.equal(await page.locator('#vcVerificationCode').innerText(),'A2B4C6');
  assert.match(await page.locator('#vcExpiry').innerText(),/Expires in/);
  assert.equal(await page.evaluate(()=>window.__session),false,'Awaiting approval cannot grant session');
  assert.equal(await page.locator('[aria-current=step]').innerText(),'3\nApproval');
  await page.screenshot({path:resolve(dir,`p1-06-pending-${viewport.width}x${viewport.height}.png`),
    fullPage:true,animations:'disabled'});
  if(viewport.width<=900){
    await page.locator('.vc-mobile-back').scrollIntoViewIfNeeded();
    assert(await page.locator('.vc-mobile-back').isVisible());
  }
  assert.deepEqual(errors,[],'Uncaught browser errors: '+errors.join('; '));
  await page.close();
 }
 const {page:cancel}=await make({width:1536,height:1024});
 await cancel.evaluate(()=>window.vishnuFirstRun.showConnect(window.__testJoin));
 await cancel.locator('.vc-request').waitFor({state:'visible'});
 await cancel.locator('.vc-desktop-back').click();
 await cancel.getByRole('heading',{name:'Unlock Vishnu'}).waitFor();
 assert.equal(await cancel.evaluate(()=>window.__cancelled),true);
 assert.equal(await cancel.evaluate(()=>window.__session),false);
 assert.equal(await cancel.evaluate(()=>window.__calls.filter(x=>x.path==='/access/join/cancel').length),1);
 await cancel.close();
 const {page:approved}=await make({width:1536,height:1024});
 await approved.evaluate(()=>{window.__approved=true;window.vishnuFirstRun.showConnect(window.__testJoin);});
 await approved.locator('.vc-request').waitFor({state:'visible'});
 await approved.locator('[data-vc-continue]').click();
 await approved.waitForFunction(()=>window.__session===true);
 await approved.locator('.genesis-connect').waitFor({state:'hidden'});
 assert.equal(await approved.evaluate(()=>window.__calls.some(c=>c.path==='/access/join/status')),true);
 await approved.close();
 console.log('P1-06 WebGL, layout, truthful pairing options, real joining, pending, cancellation, verified success: PASS');
}finally{await browser.close();}
