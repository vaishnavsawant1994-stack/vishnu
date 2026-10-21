import assert from 'node:assert/strict';
import { readFile, mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const script = await readFile(new URL('../pwa/recovery-complete.js', import.meta.url), 'utf8');
const sphere = await readFile(new URL('../pwa/neural-sphere.js', import.meta.url), 'utf8');
const canonical = await readFile(new URL('../pwa/genesis-neural-sphere.js', import.meta.url), 'utf8');
const style = await readFile(new URL('../pwa/recovery-complete.css', import.meta.url), 'utf8');
const browser = await chromium.launch({ headless: true, args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader'] });
try {
  const page = await browser.newPage({ viewport: { width: 1536, height: 864 }, reducedMotion: 'reduce' });
  await page.route('http://localhost/**', route => {
    if (new URL(route.request().url()).pathname === '/iphone/genesis-neural-sphere.js') {
      return route.fulfill({status:200,contentType:'text/javascript',body:canonical});
    }
    return route.fulfill({
      contentType: 'text/html',
      body: '<!doctype html><html lang="en"><body style="margin:0;background:#02060d"><div id="enrollPanel" class="genesis"></div></body></html>',
    });
  });
  await page.goto('http://localhost/');
  await page.addStyleTag({ content: style });
  await page.addScriptTag({ content: sphere });
  await page.addScriptTag({ content: script });
  const mount = async result => page.evaluate(value => {
    window.calls = 0;
    window.vishnuRecoveryComplete.mount(document.getElementById('enrollPanel'), value, {
      async continueToHome() { window.calls++; },
    });
  }, result);
  const full = {
    recoveryType: 'encrypted_data', identityStatus: 'completed', dataStatus: 'completed',
    deviceStatus: 'completed', restoredItems: 27, skippedSecurityItems: 2,
    securityActionsRequired: ['Review trusted devices.'],
    warnings: [], canContinueToHome: true,
  };
  await mount(full);
  assert.match(await page.locator('#rcTitle').innerText(), /Your Vishnu Has Been Recovered/);
  assert.equal(await page.locator('.rc-status-card[data-status="completed"]').count(), 3);
  assert.equal(await page.locator('#rcCore').count(), 1, 'the sphere uses live canvas geometry');
  await page.waitForFunction(() => document.querySelector('#rcCore')?.dataset.neuralRenderer === 'webgl');
  assert.equal(await page.locator('#rcCore').getAttribute('data-neural-renderer'), 'webgl', 'P1-09 must use the canonical WebGL neural geometry');
  assert.equal(await page.locator('img').count(), 0, 'static image cannot replace rotating geometry');
  assert.match(await page.locator('[data-recovery-card="data"]').innerText(), /27 backed-up items/);
  assert.equal(await page.locator('.rc-continue').isEnabled(), true);
  // Preview artifacts from controlled result fixtures, not end-to-end evidence.
  await mkdir('artifacts', { recursive: true });
  for (const [width, height] of [[1536,864],[1920,1080],[1366,768],[820,1180],[390,844],[360,800]]) {
    await page.setViewportSize({ width, height });
    await page.screenshot({
      path: 'artifacts/p1-09-preview-' + width + 'x' + height + '.png',
      fullPage: width <= 820,
    });
  }
  await page.setViewportSize({ width: 1536, height: 864 });
  await page.locator('.rc-back').click();
  assert.match(await page.locator('.rc-eyebrow').innerText(), /RECOVERY SUMMARY/);
  await page.locator('.rc-back').click();
  assert.match(await page.locator('.rc-eyebrow').innerText(), /RECOVERY COMPLETE/);
  await page.evaluate(() => { const button = document.querySelector('.rc-continue'); button.click(); button.click(); });
  assert.equal(await page.evaluate(() => window.calls), 1, 'double submit must not repeat navigation');

  await mount({
    recoveryType: 'owner_access', identityStatus: 'completed', dataStatus: 'not_applicable',
    deviceStatus: 'completed', warnings: ['Owner access only.'], canContinueToHome: true,
  });
  assert.match(await page.locator('#rcTitle').innerText(), /Access Is Restored/);
  assert.equal(await page.locator('[data-recovery-card="data"][data-status="not_applicable"]').count(), 1);
  assert.match(await page.locator('[data-recovery-card="data"]').innerText(), /No encrypted data backup/);

  await mount({
    recoveryType: 'encrypted_data', identityStatus: 'completed', dataStatus: 'partial',
    deviceStatus: 'pending', canContinueToHome: false, warnings: [],
  });
  assert.equal(await page.locator('.rc-continue').isDisabled(), true, 'pending device cannot enter Home');
  assert.match(await page.locator('#rcNextSteps').innerText(), /Finish the pending security or recovery checks/);
  assert.doesNotMatch(await page.locator('#rcNextSteps').innerText(), /Continue to Vishnu to finish setup/);
  assert.match(await page.locator('.rc-eyebrow').innerText(), /NEEDS ATTENTION/,
    'a partial or pending recovery must not present a complete-success heading');
  assert.equal(await page.locator('[data-recovery-overall="needs-attention"]').count(), 1);
  await page.locator('.rc-back').click();
  assert.match(await page.locator('.rc-eyebrow').innerText(), /RECOVERY SUMMARY/);
  await page.locator('.rc-back').click();
  assert.match(await page.locator('.rc-eyebrow').innerText(), /NEEDS ATTENTION/,
    'returning from a partial recovery summary must not imply full success');
  assert.equal(await page.locator('.rc-status-card[data-status="completed"]').count(), 1,
    'partial data or pending device must not receive a verified check');
  await page.setViewportSize({ width: 390, height: 844 });
  const width = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth, inner: window.innerWidth,
  }));
  assert.ok(width.scroll <= width.inner + 1, 'mobile must not horizontally scroll');
  assert.equal(await page.locator('.rc-header').isVisible(), true);
  assert.equal(await page.locator('.rc-next').isVisible(), true);

  // Failed runtime verification must leave a safe retry path.
  await page.evaluate(value => {
    window.vishnuRecoveryComplete.mount(document.getElementById('enrollPanel'), value, {
      async continueToHome() { throw new Error('Runtime connection unavailable'); },
    });
  }, full);
  await page.locator('.rc-continue').click();
  assert.match(await page.locator('#rcError').innerText(), /Runtime connection unavailable/);
  assert.equal(await page.locator('.rc-continue').isEnabled(), true);
  await page.evaluate(() => window.vishnuRecoveryComplete.stop());
  console.log('P1-09 browser states, responsive layout and navigation checks passed');
} finally {
  await browser.close();
}
