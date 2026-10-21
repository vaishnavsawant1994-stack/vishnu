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
  // Password policy, visibility controls, matching confirmation.
  const password=page.locator('#firstRunPassword'), confirm=page.locator('#firstRunPasswordAgain');
  await page.locator('.vs-continue').click();
  await page.waitForFunction(()=>document.querySelector('#vsPasswordError')?.textContent.length>0);
  assert.equal((await page.locator('.genesis-security').count()),1,'Must not advance without a password');
  await password.fill('StrongPassword!23456789');
  assert.match(await page.locator('#vsStrength').innerText(),/Strong|Good/);
  await confirm.fill('wrong password');
  await page.locator('.vs-continue').click();
  assert.match(await page.locator('#vsPasswordError').innerText(),/do not match/i);
  const t1=await password.getAttribute('type');
  await page.locator('[data-visibility="firstRunPassword"]').click();
  const t2=await password.getAttribute('type');
  assert(t1==='password'&&t2==='text','visibility toggles must update associated input');
  await page.locator('[data-visibility="firstRunPassword"]').click();
  await confirm.fill('StrongPassword!23456789');
  await page.locator('#vsDeviceName').fill('Personal Linux Desktop');
  await page.locator('.vs-continue').click();
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
  await page.locator('[data-vs-back]').click();
  await page.locator('.genesis-identity').waitFor();
  assert.deepEqual(errors,[],'No JS browser exceptions: '+errors.join('; '));
  await page.close();
 }
 console.log('P1-03 responsive rendering, real WebGL, password validation, visibility, device binding, recovery and Back: PASS');
}finally{await browser.close();}
