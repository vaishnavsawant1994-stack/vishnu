import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true, executablePath: process.env.CHAT_TEST_CHROMIUM_PATH || undefined });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, serviceWorkers: 'block' });
const webBaseUrl = process.env.VISHNU_WEB_BASE_URL || 'http://127.0.0.1:8770';
const errors = [];
const assetResponses = new Map();
const nonCanonicalWebPaths = [];
page.on('pageerror', error => errors.push(error.message));
page.on('response', response => {
  const path = new URL(response.url()).pathname;
  if (path.startsWith('/iphone/')) nonCanonicalWebPaths.push(path);
  if (/campaign-demo|global-search/.test(response.url())) assetResponses.set(path, response.status());
});
try {
  await page.goto(`${webBaseUrl}/web/campaign-demo`, { waitUntil: 'domcontentloaded' });
  await page.locator('#vishnuCampaignDemo .vd-demo-banner').waitFor({ timeout: 10000 });
  assert.equal(await page.getByRole('heading', { name: 'Good afternoon, Alex.' }).count(), 1);
  assert.equal(await page.locator('.vd-project-card').count(), 3);
  assert.equal(await page.locator('.vd-core img').first().evaluate(image => image.complete && image.naturalWidth > 0), true);
  assert.deepEqual(nonCanonicalWebPaths, [], 'browser requests must use platform-neutral web paths');
  for (const path of [
    '/web/campaign-demo.js', '/web/campaign-demo.css', '/web/campaign-demo-data.js',
    '/web/global-search.js', '/web/global-search.css',
  ]) assert.equal(assetResponses.get(path), 200, `${path} must load without an owner session`);
  assert.deepEqual(errors, []);
  console.log('Live local web campaign demo loaded; public assets returned 200; local fixture rendered without owner sign-in.');
} finally {
  await browser.close();
}
