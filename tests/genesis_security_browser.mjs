/* P1-03: real browser renders at reference dimensions; account creation is mocked
   but follows the production action/controller and server payload contract. */
import assert from 'node:assert/strict';
import { readFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';
const assetNames=['first-run.js','first-run-actions.js','genesis.css','genesis-welcome.css','genesis-neural-sphere.js','genesis-identity.css','genesis-identity.js','genesis-security.css','genesis-security.js',
 'assets/genesis/avatar-blue.svg','assets/genesis/avatar-mountain.svg','assets/genesis/avatar-forest.svg','assets/genesis/avatar-horizon.svg'];
const files=new Map();
for(const name of assetNames)files.set('/iphone/'+name,await readFile(new URL('../pwa/'+name,import.meta.url)));
const output=process.env.VISHNU_SECURITY_SCREENSHOTS||'artifacts/genesis-security';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
const viewports=[{width:1536,height:1024},{width:1920,height:1080},{width:1366,height:768},
 {width:768,height:1024},{width:390,height:844},{width:360,height:800}];
try{
 for(const vp of viewports){
  const page=await browser.newPage({viewport:vp,reducedMotion:'reduce',deviceScaleFactor:1});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://127.0.0.1:4173/**',route=>{
   const path=new URL(route.request().url()).pathname;
   if(files.has(path))return route.fulfill({status:200,contentType:path.endsWith('.css')?'text/css':path.endsWith('.svg')?'image/svg+xml':'text/javascript',body:files.get(path)});
   if(path==='/'||path==='/iphone/')return route.fulfill({status:200,contentType:'text/html',body:`<!doctype html><html><head>
     <meta name="viewport" content="width=device-width,initial-scale=1">
     <style>body,html{margin:0;background:#020509;min-height:100%}.hidden{display:none!important}</style>
     <link rel="stylesheet" href="/iphone/genesis.css"></head><body>
     <section id="enrollPanel" class="hidden"></section>
     <script>
       window.loadAccessOptions=async()=>({creation_available:true,local_setup_available:true});
       window.check=async()=>null;
       window.__apiCalls=[];
       window.api=async(path,options={})=>{
         window.__apiCalls.push({path,method:options.method,body:options.body});
         if(path==='/first-run/create')return {ok:true,recovery_codes:['recovery-one','recovery-two']};
         return {ok:true};
       };
     </script><script src="/iphone/first-run.js"></script>
     <script src="/iphone/first-run-actions.js"></script></body></html>`});
   return route.fulfill({status:404,body:'not found'});
  });
  await page.goto('http://127.0.0.1:4173/iphone/?genesisStep=2');
  await page.locator('.genesis-identity .vi-form').waitFor({state:'visible'});
  await page.locator('#firstRunFirstName').fill('Test Owner');
  await page.locator('.vi-continue').click();
  await page.locator('.genesis-security .vs-main').waitFor({state:'visible'});
  await page.waitForTimeout(120);
  assert.equal(await page.getByRole('heading',{name:'Secure Your Vishnu'}).count(),1);
  assert.equal(await page.locator('.vs-progress [aria-current="step"]').innerText(),'3\nSecurity');
  assert.equal(await page.locator('[data-vs-sphere]').count(),1,'Same WebGL sphere canvas exists');
  const layout=await page.evaluate(()=>{
    const rect=q=>{const r=document.querySelector(q).getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,bottom:r.bottom};};
    return {width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,sphere:rect('.vs-sphere'),body:rect('.vs-body'),main:rect('.vs-main'),buttons:rect('.vs-navigation')};
  });
  assert(layout.width<=vp.width+1,'P1-03 horizontal overflow: '+JSON.stringify(layout));
  if(vp.width>900)assert(layout.sphere.x+layout.sphere.w<layout.main.x+12,'Reference requires left sphere and right security: '+JSON.stringify(layout));
  else assert(layout.sphere.bottom<=layout.main.y+1,'Phone sphere should stack above security: '+JSON.stringify(layout));
  assert(await page.locator('.vs-sphere canvas').evaluate(node=>Boolean(node.getContext('webgl'))),'Sphere is real WebGL');
  await page.screenshot({path:resolve(output,`p1-03-${vp.width}x${vp.height}.png`),fullPage:true,animations:'disabled'});
  if(vp.width<=900){
    const scroller=await page.locator('#enrollPanel').evaluate(el=>({
      clientHeight:el.clientHeight,scrollHeight:el.scrollHeight,
      overflow:getComputedStyle(el).overflowY,
    }));
    assert(scroller.scrollHeight>=scroller.clientHeight,'Mobile scrolling measurements must be valid');
    await page.locator('.vs-navigation').scrollIntoViewIfNeeded();
    const bottom=await page.locator('.vs-navigation').boundingBox();
    assert(bottom && bottom.y>=0 && bottom.y+bottom.height<=vp.height+1,
      'Mobile Back and Continue must be reachable by scrolling: '+JSON.stringify({scroller,bottom}));
    await page.screenshot({path:resolve(output,`p1-03-mobile-bottom-${vp.width}x${vp.height}.png`),animations:'disabled'});
    await page.locator('.vs-main h1').scrollIntoViewIfNeeded();
  }
  // Password policy, visibility controls, matching confirmation.
  const password=page.locator('#firstRunPassword'), confirm=page.locator('#firstRunPasswordAgain');
  await page.locator('.vs-continue').click();
  await page.waitForFunction(()=>document.querySelector('#vsPasswordError')?.textContent.length>0);
  assert.equal((await page.locator('.genesis-security').count()),1,'Must not advance without a password');
  await password.fill('R4ndom$Ocean!9457236');
  assert.match(await page.locator('#vsStrength').innerText(),/Strong|Good/);
  await confirm.fill('wrong password');
  await page.locator('.vs-continue').click();
  assert.match(await page.locator('#vsPasswordError').innerText(),/do not match/i);
  const t1=await password.getAttribute('type');
  await page.locator('[data-visibility="firstRunPassword"]').click();
  const t2=await password.getAttribute('type');
  assert(t1==='password'&&t2==='text','visibility toggles must update associated input');
  await page.locator('[data-visibility="firstRunPassword"]').click();
  await confirm.fill('R4ndom$Ocean!9457236');
  await page.locator('#vsDeviceName').fill('Personal Linux Desktop');
  if(vp.width===1536){
    await page.evaluate(()=>{
      const oldApi=window.api;
      window.api=async (path,options)=>{
        if(path==='/first-run/create')await new Promise(resolve=>setTimeout(resolve,280));
        return oldApi(path,options);
      };
    });
  }
  await page.locator('.vs-continue').click();
  if(vp.width===1536){
    await page.waitForFunction(()=>document.querySelector('.vs-continue')?.disabled);
    // A second click while the real create request is outstanding must
    // remain inert; otherwise recovery credentials could be reissued.
    await page.locator('.vs-continue').evaluate(el=>el.click());
    assert.equal(await page.locator('.vs-continue').isDisabled(),true);
  }
  await page.locator('#firstRunRecoverySaved').waitFor();
  const info=await page.evaluate(()=>({calls:window.__apiCalls,state:window.vishnuFirstRun.state}));
  const created=info.calls.find(x=>x.path==='/first-run/create');
  assert(created,'Canonical create API must be used');
  const payload=JSON.parse(created.body);
  assert.equal(payload.device_name,'Personal Linux Desktop');
  assert.equal(payload.first_name,info.state.firstName);
  assert.equal(info.calls.filter(x=>x.path==='/first-run/create').length,1);
  await page.locator('.genesis-tertiary[data-genesis-back]').click();
  await page.locator('.genesis-security').waitFor();
  assert.equal(await page.locator('#vsDeviceName').inputValue(),'Personal Linux Desktop');
  assert.equal(await page.locator('#firstRunPassword').inputValue(),'','Do not persist plaintext passwords in UI state');

  if (vp.width === 1536) {
    // A deterministic fake authenticator exercises the actual presentation ->
    // WebAuthn serialization -> canonical API sequence, not fake UI success.
    // This is browser contract evidence, NOT physical Face ID acceptance.
    await page.evaluate(() => {
      window.PublicKeyCredential = class MockPublicKeyCredential {};
      Object.defineProperty(navigator, 'credentials', {configurable:true, value:{
        create: async ({publicKey}) => ({
          id:'credential-test',type:'public-key',rawId:new Uint8Array([1,2,3]).buffer,
          response:{clientDataJSON:new Uint8Array([4,5,6]).buffer,
                    attestationObject:new Uint8Array([7,8,9]).buffer,
                    getTransports:()=>['internal']},
          getClientExtensionResults:()=>({}),
        }),
      }});
      const oldApi = window.api;
      window.api = async (path, options={}) => {
        if(path==='/access/passkey/register/options'){
          window.__apiCalls.push({path,method:options.method});
          return {challenge_id:'test-challenge',public_key:{
            rp:{id:'localhost',name:'Vishnu'},
            challenge:'AQID',user:{id:'AQID',name:'owner',displayName:'Owner'},
            pubKeyCredParams:[{alg:-7,type:'public-key'}],
          }};
        }
        return oldApi(path,options);
      };
      window.vishnuFirstRun.render(3);
    });
    await page.locator('[data-vs-passkey]').waitFor({state:'visible'});
    await page.locator('[data-vs-passkey]').click();
    await page.waitForFunction(()=>window.vishnuFirstRun.state.passkeyCreated===true);
    assert.match(await page.locator('#vsPasskeyStatus').innerText(),/verified and registered/i);
    const apiCalls = await page.evaluate(()=>window.__apiCalls);
    assert(apiCalls.some(x=>x.path==='/access/passkey/register/options'));
    const completion=apiCalls.find(x=>x.path==='/access/passkey/register/complete');
    assert(completion,'Verified backend passkey completion must be required');
    assert.equal(JSON.parse(completion.body).credential.response.attestationObject,'BwgJ');
    assert.equal(apiCalls.filter(x=>x.path==='/first-run/create').length,1,'Passkey registration cannot create another owner');
  }

  await page.locator('[data-vs-back]').click();
  await page.locator('.genesis-identity').waitFor();
  assert.deepEqual(errors,[],'No JS browser exceptions: '+errors.join('; '));
  await page.close();
 }
 const fallback=await browser.newPage({viewport:{width:390,height:844},reducedMotion:'reduce'});
 await fallback.addInitScript(()=>{
   const original=HTMLCanvasElement.prototype.getContext;
   HTMLCanvasElement.prototype.getContext=function(type,...args){
     if(type==='webgl'||type==='webgl2')return null;
     return original.call(this,type,...args);
   };
 });
 await fallback.route('http://127.0.0.1:4173/**',route=>{
   const path=new URL(route.request().url()).pathname;
   if(files.has(path))return route.fulfill({status:200,
     contentType:path.endsWith('.css')?'text/css':path.endsWith('.svg')?'image/svg+xml':'text/javascript',
     body:files.get(path)});
   if(path==='/iphone/'||path==='/')return route.fulfill({status:200,contentType:'text/html',
     body:`<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"/>
     <link rel="stylesheet" href="/iphone/genesis.css"/></head><body>
     <section id="enrollPanel" class="hidden"></section><script>
       window.loadAccessOptions=async()=>({creation_available:true,local_setup_available:true});
       window.check=async()=>null;
       window.api=async()=>({ok:true});
     </script><script src="/iphone/first-run.js"></script><script src="/iphone/first-run-actions.js"></script></body></html>`});
   return route.fulfill({status:404,body:''});
 });
 await fallback.goto('http://127.0.0.1:4173/iphone/?genesisStep=2');
 await fallback.locator('.genesis-identity .vi-form').waitFor();
 await fallback.locator('#firstRunFirstName').fill('Fallback Owner');
 await fallback.locator('.vi-continue').click();
 await fallback.locator('.genesis-security .vs-main').waitFor();
 assert.equal(await fallback.locator('.vs-sphere.vw-static-fallback').count(),1,
   'When WebGL is unavailable keep actual controls and a restrained visual fallback');
 assert.equal(await fallback.locator('#firstRunPassword').count(),1);
 await fallback.close();

 console.log('P1-03 responsive rendering, real WebGL, password validation, visibility, device binding, recovery and Back: PASS');
}finally{await browser.close();}
