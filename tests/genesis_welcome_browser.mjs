/* P1-01 focused visual and navigation acceptance in an isolated PWA shell. */
import assert from 'node:assert/strict';
import { readFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';

const root = new URL('../pwa/', import.meta.url);
const assets = new Map();
for (const name of ['first-run.js', 'genesis.css', 'genesis-welcome.css', 'genesis-neural-sphere.js']) {
  assets.set('/iphone/' + name, await readFile(new URL(name, root), 'utf8'));
}
const dir = process.env.VISHNU_WELCOME_SCREENSHOTS || 'artifacts/genesis-welcome';
await mkdir(dir, { recursive: true });
const browser = await chromium.launch({ headless: true, args: ['--enable-webgl', '--use-gl=angle', '--use-angle=swiftshader'] });
try {
  for (const viewport of [{width:1536,height:961},{width:1920,height:1080},{width:1366,height:768},{width:1024,height:768},{width:768,height:1024},{width:430,height:932},{width:393,height:852},{width:390,height:844},{width:360,height:800}]) {
    const page = await browser.newPage({ viewport, deviceScaleFactor: 1, reducedMotion: 'reduce' });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('http://127.0.0.1:4173/**', route => {
      const path = new URL(route.request().url()).pathname;
      if (assets.has(path)) {
        const type = path.endsWith('.css') ? 'text/css' : 'text/javascript';
        return route.fulfill({ status: 200, contentType: type, body: assets.get(path) });
      }
      if (path === '/iphone/' || path === '/') {
        return route.fulfill({ status: 200, contentType: 'text/html', body: `<!doctype html>
          <html><head><meta name="viewport" content="width=device-width,initial-scale=1">
          <style>html,body{margin:0;min-height:100%;background:#02060b}.hidden{display:none!important}</style>
          <link rel="stylesheet" href="/iphone/genesis.css"></head><body>
          <div id="enrollPanel" class="hidden"></div>
          <script>
            window.__previewOptions = { creation_available:true, restore_available:true, local_setup_available:true };
            window.loadAccessOptions = async () => window.__previewOptions;
            window.check = async () => null;
          </script>
          <script src="/iphone/first-run.js"></script>
          </body></html>` });
      }
      return route.fulfill({ status: 404, body: '' });
    });
    await page.goto('http://127.0.0.1:4173/iphone/');
    await page.locator('.genesis-welcome').waitFor();
    await page.locator('#vwSphereCanvas').waitFor();
    await page.waitForFunction(() => window.vishnuFirstRun?.state?.options?.creation_available === true);
    assert.equal(await page.locator('h1').textContent(), 'Welcome to Vishnu.');
    await page.waitForTimeout(180); // Allow asynchronous 3D module mount before capturing the evidence frame.
    for (const label of ['Create My Vishnu', 'I Already Have Vishnu', 'Restore My Vishnu', 'Language', 'Help']) {
      assert.equal(await page.getByRole('button', {name: new RegExp(label)}).count(), 1, label);
    }
    const metrics = await page.evaluate(() => {
      const sphere = document.querySelector('.vw-sphere').getBoundingClientRect();
      const heading = document.querySelector('.vw-heading').getBoundingClientRect();
      const cards = [...document.querySelectorAll('.vw-card')].map(e => e.getBoundingClientRect());
      const primary = document.querySelector('.vw-primary').getBoundingClientRect();
      const footer = document.querySelector('.vw-footer').getBoundingClientRect();
      return {docWidth:document.documentElement.scrollWidth,docHeight:document.documentElement.scrollHeight,innerWidth,innerHeight,
        sphere:{x:sphere.x,y:sphere.y,width:sphere.width,bottom:sphere.bottom},
        headingY:heading.y,primaryY:primary.y,primaryWidth:primary.width,
        cardsY:cards[0].y,footerY:footer.y,footerBottom:footer.bottom,
        cardsSideBySide:Math.abs(cards[0].y-cards[1].y)<3 };
    });
    assert(metrics.docWidth <= viewport.width+1, `Horizontal overflow on ${viewport.width}px: ${JSON.stringify(metrics)}`);
    assert(metrics.sphere.width >= 185 && metrics.sphere.width <= 390, `Sphere size out of range: ${JSON.stringify(metrics)}`);
    assert(metrics.sphere.y < metrics.headingY && metrics.headingY < metrics.primaryY && metrics.primaryY < metrics.cardsY,
      `Welcome content order changed: ${JSON.stringify(metrics)}`);
    assert.equal(metrics.cardsSideBySide, viewport.width > 800);
    if (viewport.width === 1536) {
      // Primary source of truth is the originally approved 1536 x 961 screenshot.
      assert(metrics.sphere.x > 550 && metrics.sphere.x < 610, `Original sphere alignment changed: ${JSON.stringify(metrics)}`);
      assert(metrics.sphere.y >= 55 && metrics.sphere.y <= 120, `Original sphere vertical alignment changed: ${JSON.stringify(metrics)}`);
      assert(metrics.headingY >= 490 && metrics.headingY <= 550, `Original headline alignment changed: ${JSON.stringify(metrics)}`);
      assert(metrics.primaryY >= 610 && metrics.primaryY <= 680, `Original primary action alignment changed: ${JSON.stringify(metrics)}`);
      assert(metrics.cardsY >= 700 && metrics.cardsY <= 765, `Original card alignment changed: ${JSON.stringify(metrics)}`);
    }
    if (viewport.width === 1536 || viewport.width === 1920) {
      assert(metrics.footerBottom <= viewport.height, `Desktop footer is cropped: ${JSON.stringify(metrics)}`);
      assert(metrics.docHeight <= viewport.height+1, `Desktop should fit without scrolling: ${JSON.stringify(metrics)}`);
    }
    const fileName = viewport.width===1536 ? 'p1-01-desktop.png' :
      viewport.width===390 ? 'p1-01-mobile.png' : `p1-01-${viewport.width}.png`;
    await page.screenshot({ path: resolve(dir,fileName), fullPage: true, animations:'disabled' });
    if (viewport.width === 1536) {
      const canvas = page.locator('#vwSphereCanvas');
      const webglReady = await canvas.evaluate(node => Boolean(node.getContext('webgl')) &&
        !node.parentElement.classList.contains('vw-static-fallback'));
      assert(webglReady, 'Neural sphere must use a working WebGL renderer rather than a static fallback');
      await page.emulateMedia({ reducedMotion: 'no-preference' });
      await page.waitForTimeout(150);
      const rotationBefore = await canvas.screenshot();
      await page.waitForTimeout(450);
      const rotationAfter = await canvas.screenshot();
      assert.notDeepEqual(rotationAfter, rotationBefore, 'Neural sphere should visibly rotate without user input');
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.waitForTimeout(100);
      const dragBefore = await canvas.screenshot();
      const bounds = await canvas.boundingBox();
      await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
      await page.mouse.down();
      await page.mouse.move(bounds.x + bounds.width / 2 + 65, bounds.y + bounds.height / 2 + 32, { steps: 5 });
      await page.mouse.up();
      await page.waitForTimeout(120);
      const dragAfter = await canvas.screenshot();
      assert.notDeepEqual(dragAfter, dragBefore, 'Pointer drag should change the true 3D sphere orientation');
    }
    await page.getByRole('button', { name:'Help' }).click();
    assert.equal(await page.locator('#vwHelpDialog').evaluate(e=>e.open),true);
    await page.locator('#vwHelpDialog [data-vw-close]').click();
    await page.getByRole('button', { name:'Language' }).click();
    assert.equal(await page.locator('#vwLanguageSelection').inputValue(),'en');
    await page.locator('#vwLanguageDialog [data-vw-close]').click();
    await page.getByRole('button', {name:/Create My Vishnu/}).click();
    await page.getByRole('heading', {name:'What should Vishnu call you?'}).waitFor();
    assert.equal(await page.locator('.genesis-screen').getAttribute('data-step'),'2');
    assert.deepEqual(errors, [], `Browser errors: ${errors.join('; ')}`);
    await page.close();
  }
  const page = await browser.newPage({viewport:{width:1536,height:961}});
  await page.route('http://127.0.0.1:4173/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (assets.has(path)) return route.fulfill({ status:200,
      contentType: path.endsWith('.css')?'text/css':'text/javascript', body:assets.get(path) });
    return route.fulfill({ status:200, contentType:'text/html', body:`<!doctype html>
      <html><head><style>body{margin:0}.hidden{display:none!important}</style><link rel="stylesheet" href="/iphone/genesis.css"></head>
      <body><div id="enrollPanel"></div><script>
      window.__previewOptions={creation_available:true,restore_available:true};
      window.loadAccessOptions=async()=>window.__previewOptions;
      window.check=async()=>null;</script><script src="/iphone/first-run.js"></script></body></html>` });
  });
  await page.goto('http://127.0.0.1:4173/iphone/');
  await page.locator('.genesis-welcome').waitFor();
  await page.evaluate(() => {window.__previewOptions={creation_available:false,password_available:true,restore_available:false};});
  await page.getByRole('button',{name:/Create My Vishnu/}).click();
  await page.getByRole('heading',{name:/Welcome back to Vishnu/}).waitFor();
  assert.equal(await page.locator('[data-step="2"]').count(),0,'Existing owner cannot enter new identity creation');
  await page.close();
  console.log('Vishnu P1-01 responsive screenshots, entry controls, help and guarded creation passed.');
} finally {
  await browser.close();
}
