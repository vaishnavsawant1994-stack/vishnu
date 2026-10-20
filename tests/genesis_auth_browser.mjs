import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const script = await readFile(new URL('../pwa/first-run.js', import.meta.url), 'utf8');
const actions = await readFile(new URL('../pwa/first-run-actions.js', import.meta.url), 'utf8');
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.route('http://localhost/**', route => route.fulfill({
    contentType: 'text/html',
    body: '<!doctype html><html><body><div id="enrollPanel"></div></body></html>',
  }));
  await page.goto('http://localhost/');
  await page.evaluate(() => {
    window.testAccessOptions = {};
    window.loadAccessOptions = async () => window.testAccessOptions;
    window.check = async () => null;
  });
  await page.addScriptTag({ content: script });
  await page.evaluate(() => {
    window.vishnuFirstRun.state.options = { local_setup_available: true };
    window.vishnuFirstRun.render(3);
  });
  assert.equal(await page.locator('#firstRunBootstrap').count(), 0, 'local mode must not show setup-code input');
  assert.match(await page.locator('.local-setup-note').innerText(), /restricted to this computer/);
  const passwordCard = page.locator('input[name="auth"][value="password"]');
  await passwordCard.click();
  assert.equal(await passwordCard.isChecked(), true);
  const passkeyCard = page.locator('input[name="auth"][value="passkey"]');
  await passkeyCard.click();
  assert.equal(await passkeyCard.isChecked(), true);
  assert.match(await page.locator('h1').innerText(), /Secure your Vishnu/);
  await page.addScriptTag({ content: actions });
  await page.evaluate(() => {
    window.createCalls = [];
    window.api = async path => { window.createCalls.push(path); return {}; };
    window.vishnuFirstRun.state.identityCreated = true;
    // A resumed setup has no plaintext codes in browser memory; it must offer
    // regeneration instead of throwing while rendering the recovery screen.
    window.vishnuFirstRun.state.recoveryCodes = undefined;
    window.vishnuFirstRun.render(3);
    window.dispatchEvent(new CustomEvent('vishnu:genesis-next', { detail: { step: 3 } }));
  });
  await page.locator('#firstRunCodes').getByText('Recovery codes were already generated').waitFor();
  assert.deepEqual(await page.evaluate(() => window.createCalls), [],
    'resuming after owner creation must not call create again or produce a duplicate-account error');
  await page.evaluate(async () => {
    window.api = async path => {
      if (path === '/first-run/recovery-codes') {
        throw new Error('This web browser is not currently trusted by Vishnu.');
      }
      return { ok: true, status: 'setup_in_progress' };
    };
    try { await window.vishnuFirstRun.setupApi('/first-run/recovery-codes', { method: 'POST', body: '{}' }); }
    catch { /* UI asks the owner to reauthenticate instead of losing setup. */ }
  });
  await page.getByRole('heading', { name: 'Restore this browser’s setup access' }).waitFor();
  await page.getByRole('textbox', { name: 'Owner password' }).fill('test owner password 123');
  await page.getByRole('button', { name: 'Reconnect this browser' }).click();
  await page.locator('#genesisStatus').getByText('Browser access restored').waitFor();
  await page.evaluate(() => {
    window.vishnuFirstRun.render(4);
    window.dispatchEvent(new CustomEvent('vishnu:genesis-next', { detail: { step: 4 } }));
  });
  await page.locator('#genesisStatus').getByText('Save your recovery codes somewhere secure').waitFor();
  assert.equal(await page.locator('[data-genesis-next]').isDisabled(), false, 'failed save remains retryable');
  assert.doesNotMatch(await page.locator('[data-genesis-next]').innerText(), /Saving data placement/,
    'failed save restores the original button label');
  await page.evaluate(async () => {
    window.testAccessOptions = {
      creation_available: true,
      setup_in_progress: true,
      setup_resume_step: 4,
      local_setup_available: true,
      password_available: true,
    };
    await window.check();
  });
  await page.getByRole('heading', { name: 'Continue your Vishnu setup' }).waitFor();
  await page.getByRole('button', { name: /Continue setup/ }).click();
  assert.equal(await page.locator('.genesis-screen').getAttribute('data-step'), '4',
    'an interrupted owner setup resumes at its saved checkpoint rather than starting account creation again');
  const retried = await page.evaluate(async () => {
    const requests = [];
    window.api = async path => {
      requests.push(path);
      if (path === '/first-run/data-policy' && requests.filter(item => item === path).length === 1) {
        const error = new Error('First-device setup is not pending');
        error.status = 409;
        throw error;
      }
      return path === '/first-run/data-policy' ? { ok: true } : { ok: true, status: 'setup_in_progress' };
    };
    const result = await window.vishnuFirstRun.setupApi('/first-run/data-policy', { method: 'PUT' });
    return { requests, result };
  });
  assert.deepEqual(retried.requests, ['/first-run/data-policy', '/first-run/resume', '/first-run/data-policy'],
    'expired/missing setup claims are renewed through the trusted first device and the original action is retried');
  assert.deepEqual(retried.result, { ok: true });
  console.log('Genesis three-stage local create flow, auth choices, recovery progression, and retry behavior passed.');
} finally {
  await browser.close();
}
