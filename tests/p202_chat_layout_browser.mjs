import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const base = process.env.PWA_PREVIEW_URL || 'http://127.0.0.1:4175';
await mkdir('artifacts', { recursive: true });
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHAT_TEST_CHROMIUM_PATH || undefined });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 }, serviceWorkers: 'block' });
const pageErrors = [];
page.on('pageerror', error => pageErrors.push(error.message));
await page.route('https://accounts.google.com/gsi/client', route => route.fulfill({ status: 200, contentType: 'application/javascript', body: '' }));
await page.route('**/iphone/api/**', async route => {
  const request = route.request();
  const url = new URL(request.url());
  const path = url.pathname.replace('/iphone/api', '');
  let body = {};
  if (path === '/status') body = { ok: true, owner_display_name: 'Layout Test Owner', model: { state: 'ready' }, conversation: null, conversations: [], memory_count: 0 };
  else if (path === '/preferences') body = { continuous_voice: false, voice_rate: 1, quiet_hours: false };
  else if (path === '/conversations' && request.method() === 'POST') body = { conversation: { id: 'layout-chat', title: 'New conversation' }, events: [] };
  else if (path === '/conversations' && request.method() === 'GET') body = { conversations: [] };
  else if (path === '/projects' || path === '/projects?status=active') body = { projects: [{ id: 'project-layout', name: 'Layout Test Project' }] };
  else if (path === '/everyday/active' || path === '/everyday/timeline') body = { items: [] };
  else if (path === '/activities') body = { activities: [] };
  else if (path === '/workflows') body = { runs: [] };
  else if (path === '/access/options') body = { passkey_available: false, password_available: false, google_available: false };
  return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
});

try {
  await page.goto(`${base}/iphone/`, { waitUntil: 'domcontentloaded' });
  await page.locator('.reference-desktop-sidebar [data-app-module="conversations"]').click();
  await page.waitForTimeout(250);
  await page.locator('#conversationDrawer').waitFor({ state: 'visible', timeout: 5000 });
  await page.locator('#newConversation').click();
  await page.waitForFunction(() => document.body.classList.contains('chat-new-empty'));
  await page.locator('#referenceSidebarToggle').click();
  await page.locator('.reference-desktop-sidebar').waitFor({ state: 'visible' });
  await page.waitForTimeout(250);
  assert.equal(await page.locator('#conversationDrawer').isVisible(), false, 'opening primary navigation closes conversation history');
  const navigationLabels = await page.locator('.reference-desktop-sidebar nav button').evaluateAll(buttons => buttons.map(button => button.innerText.trim()));
  assert.equal(navigationLabels.filter(label => label.split('\n').at(-1) === 'Chat').length, 1, 'Chat appears once in primary navigation');
  assert.equal(navigationLabels.filter(label => label.split('\n').at(-1) === 'Today').length, 1, 'Today appears once in primary navigation');
  assert.equal(await page.locator('.reference-desktop-sidebar [data-app-module="conversations"]').getAttribute('aria-current'), 'page', 'Chat is active while the Chat surface is open');
  const expandedSidebar = await page.locator('.reference-desktop-sidebar').boundingBox();
  const expandedShell = await page.locator('.app-shell').boundingBox();
  const sidebarStyle = await page.locator('.reference-desktop-sidebar').evaluate(node => ({ width: getComputedStyle(node).width, transform: getComputedStyle(node).transform }));
  assert.ok(expandedSidebar && expandedShell && Math.abs(expandedShell.x - expandedSidebar.width) < 2, 'expanded navigation reserves exactly its own width');
  await page.screenshot({ path: 'artifacts/p202-chat-navigation-expanded.png', fullPage: true });

  await page.locator('#referenceSidebarToggle').click();
  await page.waitForFunction(() => document.querySelector('.reference-desktop-sidebar')?.getAttribute('aria-hidden') === 'true');
  await page.waitForFunction(() => {
    const rect = document.querySelector('.reference-desktop-sidebar')?.getBoundingClientRect();
    return rect && rect.right <= 1;
  });
  const collapsedSidebar = await page.locator('.reference-desktop-sidebar').boundingBox();
  const collapsedShell = await page.locator('.app-shell').boundingBox();
  assert.ok(collapsedSidebar && collapsedSidebar.x + collapsedSidebar.width <= 1, 'collapsed navigation moves fully off-canvas');
  assert.ok(collapsedShell && collapsedShell.x < 20, 'collapsed navigation releases its reserved space');
  await page.screenshot({ path: 'artifacts/p202-chat-navigation-collapsed.png', fullPage: true });

  await page.locator('#referenceSidebarToggle').click();
  await page.locator('.reference-desktop-sidebar').waitFor({ state: 'visible' });
  await page.locator('.reference-desktop-sidebar [data-app-module="conversations"]').click();
  await page.locator('#conversationDrawer').waitFor({ state: 'visible' });
  await page.waitForTimeout(300);
  await page.waitForFunction(() => document.querySelector('.reference-desktop-sidebar')?.getAttribute('aria-hidden') === 'true');
  await page.waitForFunction(() => {
    const rect = document.querySelector('.reference-desktop-sidebar')?.getBoundingClientRect();
    return rect && rect.right <= 1;
  });
  const hiddenSidebar = await page.locator('.reference-desktop-sidebar').boundingBox();
  assert.ok(hiddenSidebar && hiddenSidebar.x + hiddenSidebar.width <= 1, 'history panel replaces primary navigation off-canvas');
  assert.equal(await page.locator('#conversationDrawer').getAttribute('aria-modal'), 'false', 'desktop history drawer is a non-modal replacement panel');
  assert.equal(await page.locator('.drawer-overlay').isVisible(), false, 'history panel does not dim or block the Chat surface');
  const contextState = await page.locator('#vContextChip').evaluate(node => ({ display: getComputedStyle(node).display, visibility: getComputedStyle(node).visibility, rect: node.getBoundingClientRect().toJSON(), parentDisplay: getComputedStyle(node.parentElement).display, parentClass: node.parentElement.className }));
  assert.equal(await page.locator('#vContextChip').isVisible(), true, `project-context selector remains available: ${JSON.stringify(contextState)}`);
  const drawer = await page.locator('#conversationDrawer').boundingBox();
  const drawerShell = await page.locator('.app-shell').boundingBox();
  const drawerStyle = await page.locator('#conversationDrawer').evaluate(node => ({ left: getComputedStyle(node).left, insetInlineStart: getComputedStyle(node).insetInlineStart, transform: getComputedStyle(node).transform, inlineStyle: node.getAttribute('style'), body: document.body.className }));
  assert.ok(drawer && drawerShell && Math.abs(drawerShell.x - (drawer.x + drawer.width)) < 2, `conversation panel and Chat content share one offset: ${JSON.stringify({ drawer, drawerShell, drawerStyle })}`);
  assert.equal(await page.locator('.conversations-drawer-header h2').isVisible(), true, 'conversation history title remains visible');
  await page.screenshot({ path: 'artifacts/p202-chat-history-open.png', fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('#vContextChip').waitFor({ state: 'visible' });
  const composer = await page.locator('#composer').boundingBox();
  const stream = await page.locator('#messageStream').boundingBox();
  assert.ok(composer && stream && composer.x >= 0 && composer.x + composer.width <= 390, 'mobile composer fits the viewport');
  assert.ok(stream && stream.x >= 0 && stream.x + stream.width <= 390, 'mobile message stream fits the viewport');
  assert.deepEqual(pageErrors, [], `no uncaught JavaScript errors: ${pageErrors.join('; ')}`);
} finally {
  await browser.close();
}
