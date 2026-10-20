import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const script = await readFile(new URL('../pwa/first-run.js', import.meta.url), 'utf8');
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.route('http://localhost/**', route => route.fulfill({
    contentType: 'text/html',
    body: '<!doctype html><html><body><div id="enrollPanel"></div></body></html>',
  }));
  await page.goto('http://localhost/');
  await page.evaluate(() => {
    window.loadAccessOptions = async () => ({});
    window.check = async () => null;
  });
  await page.addScriptTag({ content: script });
  await page.evaluate(() => {
    window.vishnuFirstRun.state.options = { local_setup_available: true };
    window.vishnuFirstRun.render(4);
  });
  assert.equal(await page.locator('#firstRunBootstrap').count(), 0, 'local mode must not show setup-code input');
  assert.match(await page.locator('.local-setup-note').innerText(), /restricted to this computer/);
  const passwordCard = page.locator('[data-auth-choice="password"]');
  await passwordCard.click();
  assert.equal(await passwordCard.getAttribute('aria-checked'), 'true');
  assert.match(await page.locator('[data-genesis-next]').innerText(), /Create password/);
  const passkeyCard = page.locator('[data-auth-choice="passkey"]');
  await passkeyCard.focus();
  await page.keyboard.press('Enter');
  assert.equal(await passkeyCard.getAttribute('aria-checked'), 'true');
  assert.match(await page.locator('[data-genesis-next]').innerText(), /Create passkey/);
  console.log('Genesis local auth choices and setup-code visibility passed.');
} finally {
  await browser.close();
}
