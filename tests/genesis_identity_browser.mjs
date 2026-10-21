/* P1-02 actual Chromium identity screen acceptance and desktop/mobile screenshots. */
import assert from 'node:assert/strict';
import {mkdir,readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {chromium} from 'playwright';

const assetNames=[
 'first-run.js','first-run-actions.js','genesis.css','genesis-welcome.css','genesis-neural-sphere.js',
 'genesis-identity.js','genesis-identity.css','genesis-security.js','genesis-security.css',
 'assets/genesis/avatar-blue.svg','assets/genesis/avatar-mountain.svg',
 'assets/genesis/avatar-forest.svg','assets/genesis/avatar-horizon.svg',
];
const files=new Map();
for(const name of assetNames)files.set('/iphone/'+name,await readFile(new URL('../pwa/'+name,import.meta.url)));
const output=process.env.VISHNU_IDENTITY_SCREENSHOTS || 'artifacts/genesis-identity';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
const viewports=[{width:1536,height:864},{width:1136,height:810},{width:1920,height:1080},{width:1440,height:900},
 {width:1366,height:768},{width:768,height:1024},{width:390,height:844},{width:360,height:740},{width:428,height:926}];
try{
 for(const vp of viewports){
  const page=await browser.newPage({viewport:vp,deviceScaleFactor:1,reducedMotion:'reduce'});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://127.0.0.1:4173/**',route=>{
   const path=new URL(route.request().url()).pathname;
   if(files.has(path)){
    const type=path.endsWith('.css')?'text/css':path.endsWith('.svg')?'image/svg+xml':'text/javascript';
    return route.fulfill({status:200,contentType:type,body:files.get(path)});
   }
   if(path==='/iphone/'||path==='/'){
    return route.fulfill({status:200,contentType:'text/html',body:`<!doctype html>
     <html><head><meta name="viewport" content="width=device-width,initial-scale=1"/>
     <style>html,body{margin:0;background:#02070d;min-height:100%;}.hidden{display:none!important}</style>
     <link rel="stylesheet" href="/iphone/genesis.css"/></head><body>
     <div id="enrollPanel" class="hidden"></div>
     <script>
      window.loadAccessOptions=async()=>({creation_available:true,local_setup_available:true});
      window.check=async()=>null;
      window.__apiCalls=[];
      window.api=async(path,opts)=>{window.__apiCalls.push({path,method:opts?.method,body:opts?.body});return {ok:true};};
     </script>
     <script src="/iphone/first-run.js"></script>
     <script src="/iphone/first-run-actions.js"></script>
     </body></html>`});
   }
   return route.fulfill({status:404,body:''});
  });
  await page.goto('http://127.0.0.1:4173/iphone/?genesisStep=2');
  await page.locator('.genesis-identity .vi-form').waitFor({state:'visible'});
  await page.locator('.vi-avatar-row img').first().waitFor();
  await page.waitForTimeout(180);
  assert.equal(await page.locator('.vi-progress [aria-current="step"]').innerText(),'2\nYour Identity');
  assert.equal(await page.getByRole('heading',{name:'What should Vishnu call you?'}).count(),1);
  assert.equal(await page.locator('[data-vi-sphere] canvas').count(),0); // no nested canvas
  assert.equal(await page.locator('[data-vi-sphere]').count(),1);
  const layout=await page.evaluate(()=>{
   const dim=q=>{let r=document.querySelector(q).getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,bottom:r.bottom};};
   return {width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,
    main:dim('.genesis-identity'),sphere:dim('.vi-sphere'),form:dim('.vi-form'),
    header:dim('.vi-header'),buttons:dim('.vi-actions')};
  });
  assert(layout.width<=vp.width+1,'Horizontal overflow at '+vp.width+': '+JSON.stringify(layout));
  if(vp.width>900)assert(layout.sphere.x+layout.sphere.w<layout.form.x,'Desktop sphere must stay left of form: '+JSON.stringify(layout));
  else assert(layout.sphere.bottom<=layout.form.y+1,'Mobile sphere must stack above form: '+JSON.stringify(layout));
  if(vp.width===1536)assert(layout.height<=vp.height+1,'Reference desktop should fit without scroll: '+JSON.stringify(layout));
  if(vp.width===390 || vp.width===428)assert(layout.buttons.bottom<=vp.height,'Phone actions must fit above the safe area: '+JSON.stringify(layout));
  await page.screenshot({path:resolve(output,`p1-02-${vp.width}x${vp.height}.png`),fullPage:true,animations:'disabled'});
  const field=page.locator('#firstRunFirstName');
  await page.locator('[data-genesis-next]').click();
  assert.match(await page.locator('#viNameError').innerText(),/enter your name/i);
  assert.equal(await page.locator('.genesis-identity').count(),1,'Empty name stays on P1-02');
  await field.fill('Alexander');
  assert.equal(await page.locator('#viGreetingTitle').innerText(),'Hello, Alexander!');
  await page.locator('#firstRunDisplayName').fill('Alex');
  assert.equal(await page.locator('#viGreetingTitle').innerText(),'Hello, Alex!');
  assert.match(await page.locator('#viGreetingDetail').innerText(),/call you Alex/i);
  await page.locator('[data-vi-avatar="mountain"]').click();
  assert.equal(await page.locator('[data-vi-avatar="mountain"]').getAttribute('aria-pressed'),'true');
  assert.equal(await page.locator('#viSelectedAvatarPreview').isVisible(),true,'Selected avatar must appear immediately in owner preview');
  await page.locator('[data-vi-remove]').click();
  assert.equal(await page.locator('[data-vi-avatar="mountain"]').getAttribute('aria-pressed'),'false');
  await page.locator('#viAvatarFile').setInputFiles({name:'not-image.txt',mimeType:'text/plain',buffer:Buffer.from('not an image')});
  assert.match(await page.locator('#viAvatarError').innerText(),/PNG, JPEG or WebP/i);
  await page.locator('#viAvatarFile').setInputFiles({name:'owner-preview.png',mimeType:'image/png',
   buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGPUWHWHgYGBiYGBgYGBAQATngGybaReSgAAAABJRU5ErkJggg==','base64')});
  await page.waitForFunction(()=>window.vishnuFirstRun?.state?.avatarSource==='upload');
  assert.equal(await page.locator('#viSelectedAvatarPreview').isVisible(),true,'Validated upload appears in preview');
  await page.locator('[data-vi-remove]').click();
  assert.equal(await page.locator('#viSelectedAvatarPreview').isVisible(),false,'Remove clears preview');

  await page.locator('[data-genesis-next]').click();
  await page.getByRole('heading',{name:'Secure Your Vishnu'}).waitFor();
  const state=await page.evaluate(()=>({first:window.vishnuFirstRun?.state?.firstName,display:window.vishnuFirstRun?.state?.displayName}));
  assert.deepEqual(state,{first:'Alexander',display:'Alex'});
  await page.locator('[data-vs-back]').click();
  await page.locator('#firstRunFirstName').waitFor();
  assert.equal(await page.locator('#firstRunFirstName').inputValue(),'Alexander');
  assert.equal(await page.locator('#firstRunDisplayName').inputValue(),'Alex');
  if(vp.width===1536) {
    // Exercise the full approved identity -> security -> recovery journey.
    // The avatar endpoint must be invoked only after the canonical owner is
    // created; a selected photo must not be silently omitted at completion.
    await page.locator('[data-vi-avatar="forest"]').click();
    await page.locator('[data-genesis-next]').click();
    await page.getByRole('heading',{name:'Secure your Vishnu'}).waitFor();
    await page.locator('#firstRunPassword').fill('vishnu-test-password-123');
    await page.locator('#firstRunPasswordAgain').fill('vishnu-test-password-123');
    await page.evaluate(()=>{window.vishnuFirstRun.state.auth='password';});
    await page.locator('.vs-continue[data-genesis-next]').click();
    await page.locator('#firstRunRecoverySaved').waitFor();
    await page.locator('#firstRunRecoverySaved').check();
    await page.locator('.genesis-primary[data-genesis-next]').click();
    await page.waitForFunction(()=>window.__apiCalls.some(x=>x.path==='/first-run/complete'));
    const calls=await page.evaluate(()=>window.__apiCalls);
    const createIndex=calls.findIndex(x=>x.path==='/first-run/create');
    const avatarIndex=calls.findIndex(x=>x.path==='/first-run/avatar');
    const completeIndex=calls.findIndex(x=>x.path==='/first-run/complete');
    assert(createIndex>=0 && avatarIndex>createIndex && completeIndex>avatarIndex,
      'Private avatar persistence must happen after secure creation and before final completion');
    const avatar=JSON.parse(calls[avatarIndex].body);
    assert.deepEqual(avatar,{source:'preset',preset_id:'forest',image_b64:''});
  } else {
    await page.locator('[data-vi-back]').click();
    await page.getByRole('heading',{name:'Welcome to Vishnu.'}).waitFor();
  }
  assert.deepEqual(errors,[],'No browser errors at '+vp.width+': '+errors.join('; '));
  await page.close();
 }
 console.log('P1-02 responsive visual snapshots, live names, avatar selection, validation, and navigation: PASS');
}finally{await browser.close();}
