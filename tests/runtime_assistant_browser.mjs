import assert from 'node:assert/strict';
import { readFile, mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const [sphere, assistant, css] = await Promise.all([
  readFile(new URL('../pwa/neural-sphere.js', import.meta.url),'utf8'),
  readFile(new URL('../pwa/runtime-assistant.js', import.meta.url),'utf8'),
  readFile(new URL('../pwa/runtime-assistant.css', import.meta.url),'utf8'),
]);
const browser = await chromium.launch({ headless:true });
try {
  const page = await browser.newPage({ viewport:{width:1536,height:1024}, reducedMotion:'reduce' });
  await page.route('http://localhost/**', route => {
    if (route.request().url().endsWith('/iphone/api/access/options')) {
      return route.fulfill({status:200,contentType:'application/json',body:'{"creation_available":true}'});
    }
    return route.fulfill({contentType:'text/html', body:'<!doctype html><html><head></head><body style="margin:0;background:#00060e"><div id="enrollPanel"></div></body></html>'});
  });
  await page.goto('http://localhost/');
  await page.addStyleTag({content:css});
  await page.addScriptTag({content:sphere});
  await page.addScriptTag({content:assistant});
  await page.evaluate(() => {
    window.backVisits = 0;
    window.vishnuRuntimeAssistant.mount(document.getElementById('enrollPanel'), {
      origin:'recovery', onBack(origin) { window.backVisits++; window.lastOrigin = origin; },
    });
  });
  assert.match(await page.locator('#rtaTitle').innerText(), /Runtime Connection Assistant/);
  assert.equal(await page.locator('.rta-canvas').count(),1);
  assert.equal(await page.locator('[role="radio"]').count(),3);
  assert.equal(await page.locator('[role="radio"][aria-checked="true"]').count(),1);
  assert.equal(await page.locator('img').count(),0,'live 3D is drawn by shared neural renderer');
  await mkdir('artifacts',{recursive:true});
  for(const [width,height] of [[1536,1024],[1920,1080],[1366,768],[820,1180],[390,844],[430,932],[360,800]]) {
    await page.setViewportSize({width,height});
    await page.screenshot({path:'artifacts/p1-10-preview-'+width+'x'+height+'.png',fullPage:false});
    if (width <= 820) {
      // The P1-10 modal itself scrolls. A page-level fullPage screenshot only
      // captures the viewport when the scroll owner is the fixed modal.
      await page.locator('.runtime-assistant').screenshot({
        path:'artifacts/p1-10-preview-'+width+'x'+height+'-full.png',
      });
      await page.locator('[data-runtime-continue]').scrollIntoViewIfNeeded();
      assert.equal(await page.locator('[data-runtime-continue]').isVisible(),true);
      await page.locator('#rtaTitle').scrollIntoViewIfNeeded();
    }
    const size = await page.evaluate(() => ({
      document:document.documentElement.scrollWidth, viewport:window.innerWidth,
    }));
    assert.ok(size.document<=size.viewport+1,'horizontal overflow at '+width+'x'+height);
  }
  await page.setViewportSize({width:1536,height:1024});
  const local = page.locator('[data-runtime-choice="local"]');
  await local.click();
  assert.equal(await local.getAttribute('aria-checked'),'true');
  assert.equal(await page.locator('[role="radio"][aria-checked="true"]').count(),1);
  await local.press('ArrowDown');
  assert.equal(await page.locator('[data-runtime-choice="hosted"]').getAttribute('aria-checked'),'true');
  await page.locator('[data-runtime-continue]').click();
  assert.match(await page.locator('[data-runtime-flow="hosted"]').innerText(), /hosting account/);
  assert.equal(await page.locator('#rtaHostedConsent').isChecked(),false);
  await page.locator('.rta-provider-link').click();
  assert.match(await page.locator('#rtaStatus').innerText(),/Review and accept/);
  await page.locator('[data-runtime-back]').click();
  assert.equal(await page.locator('[data-runtime-flow]').count(),0,'back closes detail without leaving original journey');
  await page.locator('[data-runtime-back]').click();
  assert.equal(await page.evaluate(()=>window.backVisits),1);
  assert.equal(await page.evaluate(()=>window.lastOrigin),'recovery');

  await page.evaluate(() => window.vishnuRuntimeAssistant.mount(document.getElementById('enrollPanel'),{origin:'create'}));
  await page.locator('[data-runtime-choice="existing"]').click();
  await page.locator('[data-runtime-continue]').click();
  await page.locator('#rtaAddress').fill('https://example.test/?token=secret');
  await page.locator('[data-runtime-open]').click();
  assert.match(await page.locator('#rtaStatus').innerText(),/Do not include/);
  await page.locator('#rtaAddress').fill('http://remote.example.test/');
  await page.locator('[data-runtime-open]').click();
  assert.match(await page.locator('#rtaStatus').innerText(),/HTTPS/);
  await page.locator('#rtaAddress').fill('https://runtime.example.test');
  await page.locator('[data-runtime-open]').click();
  assert.match(await page.locator('#rtaStatus').innerText(),/has NOT verified/);
  assert.equal(await page.locator('[data-runtime-open]').isEnabled(),true);
  const url = await page.evaluate(()=>window.vishnuRuntimeAssistant.validateAddress('https://runtime.example.test/'));
  assert.equal(url,'https://runtime.example.test/iphone/');
  await page.locator('#rtaAddress').fill('https://other-runtime.example.test/');
  await page.locator('[data-runtime-open]').click();
  assert.match(await page.locator('#rtaStatus').innerText(),/has NOT verified/);

  const available=await page.evaluate(()=>window.vishnuRuntimeAssistant.probe());
  assert.equal(available.reachable,true);
  await page.route('http://localhost/iphone/api/access/options',route=>route.abort('failed'));
  const offline=await page.evaluate(()=>window.vishnuRuntimeAssistant.probe());
  assert.equal(offline.status,'offline');
  await page.evaluate(()=>window.vishnuRuntimeAssistant.stop());
  console.log('P1-10 runtime selection, safe address navigation, offline detection and seven preview viewports passed');
} finally { await browser.close(); }
