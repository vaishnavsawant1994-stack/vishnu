import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const html = await readFile(new URL('../pwa/index.html', import.meta.url), 'utf8');
const styleStart = html.indexOf('/* Screen 25 — Today command view.');
const styleEnd = html.indexOf('</style>', styleStart);
const codeStart = html.indexOf('function todayBoardLocalDate()');
const codeEnd = html.indexOf('async function refreshTodayScreen()', codeStart);
assert.ok(styleStart >= 0 && styleEnd > styleStart && codeStart >= 0 && codeEnd > codeStart, 'Today command UI source exists');
const styles = html.slice(styleStart, styleEnd);
const code = html.slice(codeStart, codeEnd);

const browser = await chromium.launch({ headless: true });
try {
  for (const viewport of [{ width: 1440, height: 960 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport, deviceScaleFactor: viewport.width < 500 ? 2 : 1, isMobile: viewport.width < 500 });
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    await page.setContent('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{margin:0;min-height:100%;background:#020812;color:#edf6ff;font-family:Arial,sans-serif}button,input{font:inherit}.today-row-icon{display:grid;place-items:center;width:28px;height:28px;color:#39d8ff}.today-row-icon svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:1.8}</style></head><body class="today-command-mode"><aside id="todayScreen"><div id="todayCommandDashboard"></div></aside><div id="globalSearch"></div><input id="chatInput"></body></html>');
    await page.addStyleTag({ content: styles });
    await page.addScriptTag({ content: `
      window.calls=[];
      var todayScreenDemo=true,todayScreenItems=[],todayScreenPlans=[];
      var todayCommandSources={
        work:{data:{counts:{active:1,waiting_approval:1,completed:1},work_orders:[{title:'Patient CRM implementation',objective:'Development fixture only',project_name:'Rudra Health Care',status:'RUNNING'},{title:'QA completed',project_name:'Vishnu Development',status:'COMPLETED'}]}},
        attention:{data:{counts:{total:1},items:[{title:'Review Face Model v8',summary:'Development fixture only',severity:'approval required'}]}},
        projects:{data:{projects:[{id:'project-fixture',name:'Patient CRM'}]}},
        activity:{data:{activities:[{action:'qa.validation.completed',created_at:'Today'}]}},
        workspaces:{data:{workspaces:[{name:'Vishnu Development',description:'Development fixture only',pinned:true}]}}
      };
      function $(id){return document.getElementById(id)}
      function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]))}
      function ownerDisplayName(){return 'Alex Morgan'}
      function greeting(){return 'Good afternoon.'}
      function todayScreenDateRecord(){return null}
      function todayScreenKind(){return 'tasks'}
      function todayClockLabel(){return 'Today'}
      function closeTodayScreen(){}
      function openTodayExistingCreate(kind){window.calls.push(['create',kind])}
      function openTimelineAttention(){window.calls.push(['attention'])}
      function openModule(name){window.calls.push(['module',name]);return Promise.resolve()}
      function showToast(message){window.calls.push(['toast',message])}
    ` });
    await page.addScriptTag({ content: `${code}\nrenderTodayCommandDashboard();` });
    await page.getByRole('heading', { name: /Good afternoon, Alex Morgan/ }).waitFor();
    assert.match(await page.locator('#todayCommandDashboard').innerText(), /Preview data, not saved/);
    assert.match(await page.locator('#todayCommandDashboard').innerText(), /Review Face Model v8/);
    assert.match(await page.locator('#todayCommandDashboard').innerText(), /Patient CRM implementation/);
    if (viewport.width < 500) {
      await page.getByRole('navigation', { name: 'Mobile Vishnu navigation' }).waitFor();
      const mobileText = await page.locator('#todayCommandDashboard').innerText();
      assert.ok(mobileText.indexOf('Needs Your Attention') < mobileText.indexOf('Today Summary'), 'Mobile-first priority items precede the desktop summary rail');
      const geometry = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
      assert.ok(geometry.scroll <= geometry.width + 2, JSON.stringify(geometry));
      await page.screenshot({ path: fileURLToPath(new URL('../artifacts/today-command-mobile.png', import.meta.url)), fullPage: true });
      await page.getByRole('button', { name: /Spaces/ }).click();
      assert.deepEqual(await page.evaluate(() => window.calls.at(-1)), ['module', 'labs']);
    } else {
      await page.locator('.today-board-nav').waitFor();
      await page.screenshot({ path: fileURLToPath(new URL('../artifacts/today-command-desktop.png', import.meta.url)), fullPage: true });
      await page.locator('.today-board-nav [data-today-nav="Workspaces"]').click();
      assert.deepEqual(await page.evaluate(() => window.calls.at(-1)), ['module', 'labs']);
    }
    assert.deepEqual(pageErrors, [], pageErrors.join(' | '));
    await page.close();
  }
} finally {
  await browser.close();
}
console.log('Today dashboard desktop/mobile render, fixture labeling, navigation and overflow checks passed.');
