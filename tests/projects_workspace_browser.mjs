import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdir, readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const root = new URL('../', import.meta.url);
const read = path => readFile(new URL(path, root));
const screenshotDir = process.env.PROJECT_SCREENSHOT_DIR;
if (screenshotDir) await mkdir(screenshotDir, { recursive: true });
const serverState = { projects: [], conversations: [], turns: [], nextId: 1 };
const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const send = (status, body, type = 'application/json') => { res.writeHead(status, { 'content-type': type, 'cache-control': 'no-store' }); res.end(type === 'application/json' ? JSON.stringify(body) : body); };
  if (req.method === 'GET' && url.pathname === '/iphone/') return send(200, await read('pwa/index.html'), 'text/html; charset=utf-8');
  if (req.method === 'GET' && url.pathname === '/iphone/projects-workspace.js') return send(200, await read('pwa/projects-workspace.js'), 'application/javascript');
  if (req.method === 'GET' && url.pathname === '/iphone/projects-workspace.css') return send(200, await read('pwa/projects-workspace.css'), 'text/css');
  if (req.method === 'GET' && url.pathname === '/iphone/projects-workspace-views.css') return send(200, await read('pwa/projects-workspace-views.css'), 'text/css');
  if (req.method === 'GET' && url.pathname === '/iphone/projects-workspace-views.js') return send(200, await read('pwa/projects-workspace-views.js'), 'application/javascript');
  if (req.method === 'GET' && url.pathname === '/iphone/p202c-project-conversation.js') return send(200, await read('pwa/p202c-project-conversation.js'), 'application/javascript');
  if (req.method === 'GET' && url.pathname === '/iphone/p202c-project-conversation.css') return send(200, await read('pwa/p202c-project-conversation.css'), 'text/css');
  if (req.method === 'GET' && url.pathname === '/iphone/v1-runtime.js') return send(200, await read('pwa/v1-runtime.js'), 'application/javascript');
  if (req.method === 'GET' && url.pathname === '/iphone/manifest.webmanifest') return send(200, '{}', 'application/manifest+json');
  if (req.method === 'GET' && url.pathname === '/iphone/sw.js') return send(200, await read('pwa/sw.js'), 'application/javascript');
  if (url.pathname.startsWith('/iphone/api/')) {
    let raw = ''; for await (const chunk of req) raw += chunk;
    const body = raw ? JSON.parse(raw) : {};
    const path = url.pathname.slice('/iphone/api'.length);
    if (path === '/status') return send(200, { model: { state: 'ready' }, conversations: [], conversation: null, memory_count: 0, active_qualification: false });
    if (path === '/preferences') return send(200, { continuous_voice: true, voice_rate: 1, quiet_hours: true });
    if (path === '/everyday/active') return send(200, { items: [] });
    if (path === '/conversations') return send(200, { conversations: serverState.conversations });
    if (path === '/approvals-center') return send(200, { approvals: [] });
    if (path === '/projects' && req.method === 'GET') return send(200, { projects: serverState.projects.filter(item => url.searchParams.get('status') === 'archived' ? item.status === 'archived' : item.status !== 'archived') });
    if (path === '/projects' && req.method === 'POST') {
      const milestoneIds = new Map((body.milestones || []).map(item => [item.client_id, `milestone-${serverState.nextId++}`]));
      const tasks = (body.tasks || []).map(item => ({ id: `task-${serverState.nextId++}`, ...item, milestone_id: milestoneIds.get(item.milestone_client_id) || null, status: 'planned', created_at: new Date().toISOString(), updated_at: new Date().toISOString() }));
      const milestones = (body.milestones || []).map(item => ({ id: milestoneIds.get(item.client_id), ...item, status: 'planned', task_ids: tasks.filter(task => task.milestone_id === milestoneIds.get(item.client_id)).map(task => task.id) }));
      const project = { id: `project-${serverState.nextId++}`, ...body, status: 'active', conversation_id: null, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), task_count: tasks.length, done_count: 0, milestone_count: milestones.length, tasks, milestones, files: [], approvals: [], threads: [], activity: [] };
      serverState.projects.unshift(project); project.activity.push({ id: 'event-create', actor: 'owner', action: 'created project', target_type: 'project', detail: project.name, created_at: project.created_at });
      return send(201, { project });
    }
    if (path === '/projects/walkthrough' && req.method === 'POST') {
      let project = serverState.projects.find(item => item.is_walkthrough);
      if (!project) {
        project = { id: `project-${serverState.nextId++}`, name: 'Walkthrough · Personal AI redesign', is_walkthrough: true,
          description: 'Illustrative walkthrough records created on request.', goal: 'Learn the saved project workflow.', project_type: 'software', status: 'active',
          task_count: 1, done_count: 0, milestone_count: 1, tasks: [{ id: `task-${serverState.nextId++}`, title: 'Review walkthrough', status: 'planned', owner: 'owner', priority: 'medium', file_ids: [] }],
          milestones: [{ id: `milestone-${serverState.nextId++}`, title: 'Workspace review', status: 'planned', task_ids: [] }], files: [], approvals: [], threads: [], activity: [], created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
        serverState.projects.unshift(project);
      }
      return send(201, { project });
    }
    const projectPath = path.match(/^\/projects\/([^/]+)(.*)$/);
    if (projectPath) {
      const project = serverState.projects.find(item => item.id === decodeURIComponent(projectPath[1]));
      if (!project) return send(404, { detail: 'Project not found' });
      const tail = projectPath[2];
      const result = () => { project.task_count = project.tasks.length; project.done_count = project.tasks.filter(item => item.status === 'done').length; project.milestone_count = project.milestones.length; project.updated_at = new Date().toISOString(); return { project }; };
      if (!tail && req.method === 'GET') return send(200, result());
      if (!tail && req.method === 'PATCH') { Object.assign(project, body); return send(200, result()); }
      if (!tail && req.method === 'DELETE') { project.status = 'archived'; return send(204, ''); }
      if (tail === '/restore' && req.method === 'POST') { project.status = 'active'; return send(200, result()); }
      if (tail === '/tasks' && req.method === 'POST') { project.tasks.push({ id: `task-${serverState.nextId++}`, project_id: project.id, status: 'planned', created_at: new Date().toISOString(), updated_at: new Date().toISOString(), ...body }); project.activity.push({ id: `event-${serverState.nextId++}`, actor: 'owner', action: 'created task', target_type: 'task', detail: body.title, created_at: new Date().toISOString() }); return send(201, result()); }
      const taskPath = tail.match(/^\/tasks\/([^/]+)$/);
      if (taskPath && req.method === 'PATCH') { const task = project.tasks.find(item => item.id === decodeURIComponent(taskPath[1])); if (!task) return send(404, { detail: 'Task not found' }); Object.assign(task, body); task.updated_at = new Date().toISOString(); return send(200, result()); }
      if (tail === '/milestones' && req.method === 'POST') { project.milestones.push({ id: `milestone-${serverState.nextId++}`, status: 'planned', task_ids: body.task_ids || [], ...body }); return send(201, result()); }
      const milestonePath = tail.match(/^\/milestones\/([^/]+)$/);
      if (milestonePath && req.method === 'PATCH') { Object.assign(project.milestones.find(item => item.id === decodeURIComponent(milestonePath[1])), body); return send(200, result()); }
      if (tail === '/approvals' && req.method === 'POST') { project.approvals.unshift({ id: `proposal-${serverState.nextId++}`, status: 'pending', proposed_at: new Date().toISOString(), history: [], reviewer_comments: '', ...body }); return send(201, result()); }
      const proposalDecision = tail.match(/^\/approvals\/([^/]+)\/decision$/);
      if (proposalDecision && req.method === 'POST') { const item = project.approvals.find(row => row.id === decodeURIComponent(proposalDecision[1])); item.status = body.decision; item.decision = body.decision; item.reviewer = 'owner'; item.reviewed_at = new Date().toISOString(); item.reviewer_comments = body.comments; item.history.push({ actor: 'owner', decision: body.decision, comments: body.comments, created_at: item.reviewed_at }); return send(200, { ...result(), execution_started: false }); }
      const proposalResubmit = tail.match(/^\/approvals\/([^/]+)\/resubmit$/);
      if (proposalResubmit && req.method === 'POST') { const item = project.approvals.find(row => row.id === decodeURIComponent(proposalResubmit[1])); Object.assign(item, body, { status: 'pending', reviewer_comments: '', decision: null, reviewed_at: null }); item.history.push({ actor: 'owner', decision: 'resubmitted', comments: '', created_at: new Date().toISOString() }); return send(200, result()); }
      if (tail === '/conversations' && req.method === 'GET') {
        const matches = serverState.conversations.filter(entry => entry.conversation.context?.project_id === project.id);
        return send(200, { project_id: project.id, primary_conversation_id: project.conversation_id, conversations: matches.map(entry => entry.conversation) });
      }
      if (tail === '/conversations' && req.method === 'POST') {
        const id = 'conversation-' + serverState.nextId++;
        const entry = { conversation: { id, title: body.title || 'New Project Conversation', context: { conversation_kind: 'project', project_id: project.id } }, events: [] };
        serverState.conversations.push(entry); project.conversation_id ||= id;
        return send(201, { conversation: entry.conversation, project_id: project.id, primary_conversation_id: project.conversation_id });
      }
      const selectedProjectConversation = tail.match(/^\/conversations\/([^/]+)$/);
      if (selectedProjectConversation && req.method === 'GET') {
        const id = decodeURIComponent(selectedProjectConversation[1]);
        const entry = serverState.conversations.find(item => item.conversation.id === id && item.conversation.context?.project_id === project.id);
        return entry ? send(200, entry) : send(404, { detail: 'Project conversation not found' });
      }
      if (tail === '/conversation' && req.method === 'POST') { project.conversation_id ||= 'conversation-' + serverState.nextId++; return send(201, { conversation_id: project.conversation_id, project }); }
      if (tail === '/activity' && req.method === 'POST') { project.activity.push({ id: `event-${serverState.nextId++}`, actor: 'owner', action: 'asked Vishnu', target_type: 'conversation', detail: body.content, created_at: new Date().toISOString() }); return send(201, result()); }
      if (tail === '/discussions' && req.method === 'POST') { const thread = { id: `thread-${serverState.nextId++}`, title: body.title, status: 'open', linked_item_type: body.linked_item_type || '', linked_item_id: body.linked_item_id || null, linked_item_title: body.linked_item_type === 'task' ? project.tasks.find(item => item.id === body.linked_item_id)?.title : '', followed: false, updated_at: new Date().toISOString(), replies: [{ id: `reply-${serverState.nextId++}`, author: 'owner', content: body.content, created_at: new Date().toISOString() }] }; project.threads.unshift(thread); return send(201, result()); }
      const discussionReply = tail.match(/^\/discussions\/([^/]+)\/replies$/);
      if (discussionReply && req.method === 'POST') { const thread = project.threads.find(row => row.id === decodeURIComponent(discussionReply[1])); if (!thread) return send(404, { detail: 'Discussion not found' }); thread.replies.push({ id: `reply-${serverState.nextId++}`, author: 'owner', content: body.content, created_at: new Date().toISOString() }); thread.updated_at = new Date().toISOString(); return send(201, result()); }
      const discussionUpdate = tail.match(/^\/discussions\/([^/]+)$/);
      if (discussionUpdate && req.method === 'PATCH') { const thread = project.threads.find(row => row.id === decodeURIComponent(discussionUpdate[1])); if (!thread) return send(404, { detail: 'Discussion not found' }); Object.assign(thread, body); if (body.status === 'resolved') { thread.resolved_by = 'owner'; thread.resolved_at = new Date().toISOString(); } return send(200, result()); }
      if (tail === '/files/upload' && req.method === 'POST') { const file = { id: `file-${serverState.nextId++}`, title: body.filename, kind: 'upload', created_at: new Date().toISOString(), content: Buffer.from(body.content_base64, 'base64') }; project.files.push(file); return send(201, result()); }
      const fileUpdate = tail.match(/^\/files\/([^/]+)$/);
      if (fileUpdate && req.method === 'PATCH') { const file = project.files.find(item => item.id === decodeURIComponent(fileUpdate[1])); if (!file) return send(404, { detail: 'File not found' }); Object.assign(file, body); return send(200, result()); }
      const downloadPath = tail.match(/^\/files\/([^/]+)\/download$/);
      if (downloadPath && req.method === 'GET') { const file = project.files.find(item => item.id === decodeURIComponent(downloadPath[1])); return file ? send(200, file.content, 'text/markdown') : send(404, { detail: 'File not found' }); }
    }
    if (path.startsWith('/conversations/') && req.method === 'GET') {
      const id = decodeURIComponent(path.split('/')[2]); const conversation = serverState.conversations.find(item => item.conversation.id === id);
      return send(200, conversation || { conversation: { id }, events: [] });
    }
    if (path === '/voice/turn' && req.method === 'POST') { serverState.turns.push(body); const answer = `Vishnu plan for: ${body.transcript.slice(body.transcript.lastIndexOf('Owner request:') + 14).trim()}`; const id = body.conversation_id; let conversation = serverState.conversations.find(item => item.conversation.id === id); if (!conversation) { conversation = { conversation: { id, title: 'Project conversation' }, events: [] }; serverState.conversations.push(conversation); } conversation.events.push({ kind: 'user_message', payload: { text: body.transcript } }, { kind: 'assistant_message', payload: { text: answer } }); return send(200, { status: 'completed', conversation_id: id, reply: answer }); }
    if (path === '/approvals-center/pending' || path === '/workflows') return send(200, { approvals: [], workflows: [], runs: [] });
    return send(200, {});
  }
  return send(404, 'not found', 'text/plain');
});

await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const address = server.address();
const browser = await chromium.launch({ headless: true });
try {
  for (const viewport of [{ width: 390, height: 844, isMobile: true }, { width: 820, height: 1000, isMobile: false }, { width: 1440, height: 1000, isMobile: false }]) {
    const page = await browser.newPage({ viewport, deviceScaleFactor: viewport.isMobile ? 2 : 1, isMobile: viewport.isMobile, hasTouch: viewport.isMobile, serviceWorkers: 'block' });
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${address.port}/iphone/`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => document.body.classList.contains('home-landing'));
    await page.locator('#historyButton').click();
    await page.locator('#appDrawer [data-app-module="projects"]').click();
    await page.locator('.project-list-page').waitFor();
    if (viewport.width <= 900) {
     await page.locator('#historyButton').click();
     await page.locator('#appDrawer').waitFor({ state: 'visible' });
     assert.equal(await page.locator('#appDrawer [data-app-module="projects"]').isVisible(), true, `The hamburger should open usable navigation from the Projects list at ${viewport.width}px`);
     await page.locator('#closeAppDrawer').click();
     await page.locator('#appDrawer').waitFor({ state: 'hidden' });
    }
    const openProjectTab = async key => { let tab = page.locator(`[data-project-tab="${key}"]:visible`).first(); if (!(await tab.count())) { await page.locator('.project-more-tabs > summary').click(); tab = page.locator(`[data-project-tab="${key}"]:visible`).first(); } await tab.click(); };
    if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/projects-${viewport.width}.png`, fullPage: false });
    const projectSurface = await page.evaluate(() => {
      const panel = document.querySelector('#modulePanel').getBoundingClientRect();
      const page = document.querySelector('.project-list-page').getBoundingClientRect();
      const shell = document.querySelector('.app-shell').getBoundingClientRect();
      const panelStyle = getComputedStyle(document.querySelector('#modulePanel'));
      return { viewport: innerWidth, projectClass: !!document.querySelector('#modulePanel.module-panel.open[data-surface=\"projects\"]'), shellLeft: shell.left, shellWidth: shell.width, panelWidth: panel.width, panelHeight: panel.height, panelLeft: panel.left, panelPosition: panelStyle.position, panelTransform: panelStyle.transform, pageLeft: page.left, bodyWidth: document.body.scrollWidth };
    });
    if (viewport.width > 900) {
      assert.ok(projectSurface.panelLeft >= 200 && projectSurface.panelLeft + projectSurface.panelWidth >= projectSurface.viewport - 1, `Desktop Projects should begin beside the global navigation and fill the remaining width: ${JSON.stringify(projectSurface)}`);
    } else {
      assert.ok(projectSurface.panelWidth >= projectSurface.viewport - 1, `Mobile Projects should use the full available width: ${JSON.stringify(projectSurface)}`);
    }
    assert.ok(projectSurface.panelHeight > 0, `Projects should fill the workspace height: ${JSON.stringify(projectSurface)}`);
    assert.ok(projectSurface.bodyWidth <= projectSurface.viewport + 1, `Projects should not overflow horizontally: ${JSON.stringify(projectSurface)}`);
    if (viewport.isMobile) assert.ok(projectSurface.pageLeft >= -1 && projectSurface.pageLeft < 20, `Mobile Projects should not sit inside an inset card: ${JSON.stringify(projectSurface)}`);
    await page.getByRole('button', { name: /New project/i }).first().click();
    await page.locator('.project-wizard-page').waitFor();
    if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/project-setup-${viewport.width}.png`, fullPage: false });
    const wizardSurface = await page.evaluate(() => {
      const panel = document.querySelector('#modulePanel').getBoundingClientRect();
      const body = document.querySelector('#moduleBody').getBoundingClientRect();
      const wizard = document.querySelector('.project-wizard-page').getBoundingClientRect();
      const actions = document.querySelector('.project-wizard-actions').getBoundingClientRect();
      const fields = [...document.querySelectorAll('.project-wizard-form input:not([type="file"]), .project-wizard-form textarea, .project-wizard-form select')].map(field => { const rect = field.getBoundingClientRect(); return { left: rect.left, right: rect.right, width: rect.width }; });
      return { viewport: innerWidth, panelWidth: panel.width, panelHeight: panel.height, bodyHeight: body.height, wizardWidth: wizard.width, wizardHeight: wizard.height, actionsBottom: actions.bottom, bodyWidth: document.body.scrollWidth, fields, verticalScrollbar: getComputedStyle(document.querySelector('.project-wizard-layout')).scrollbarWidth };
    });
    assert.ok(wizardSurface.wizardWidth >= wizardSurface.panelWidth - 3, `Project setup should fill its page surface: ${JSON.stringify(wizardSurface)}`);
    assert.ok(wizardSurface.wizardHeight >= wizardSurface.bodyHeight - 20, `Project setup should fill the available page content: ${JSON.stringify(wizardSurface)}`);
    assert.ok(wizardSurface.bodyWidth <= wizardSurface.viewport + 1, `Project setup should not overflow horizontally: ${JSON.stringify(wizardSurface)}`);
    if (viewport.isMobile) {
      assert.ok(wizardSurface.fields.every(field => field.left >= -1 && field.right <= wizardSurface.viewport + 1), `Mobile project fields must fit the viewport: ${JSON.stringify(wizardSurface)}`);
      assert.equal(wizardSurface.verticalScrollbar, 'none', 'Mobile wizard scrolling should not show a scrollbar');
    }
    await page.locator('.project-wizard-page input[name="name"]').fill(`Responsive workspace ${viewport.width}`);
    await page.locator('.project-wizard-page textarea[name="goal"]').fill('Ship the project workspace and verify owner-controlled data.');
    await page.locator('[data-wizard-next]').click();
    await page.locator('[data-wizard-next]').click();
    await page.locator('[data-wizard-create]').click();
    await page.getByRole('heading', { name: `Responsive workspace ${viewport.width}` }).waitFor();
    const detailShell = await page.evaluate(() => {
      const drawer = document.querySelector('#appDrawer').getBoundingClientRect();
      const panel = document.querySelector('#modulePanel').getBoundingClientRect();
      const projectNav = document.querySelector('.project-workspace-sidebar').getBoundingClientRect();
      const main = document.querySelector('.project-workspace-main').getBoundingClientRect();
      return { viewport: innerWidth, bodyWidth: document.body.scrollWidth, drawerLeft: drawer.left, drawerWidth: drawer.width, drawerDisplay: getComputedStyle(document.querySelector('#appDrawer')).display, panelLeft: panel.left, panelRight: panel.right, projectNavWidth: projectNav.width, projectNavDisplay: getComputedStyle(document.querySelector('.project-workspace-sidebar')).display, mainLeft: main.left, mainRight: main.right, mobileHeadDisplay: getComputedStyle(document.querySelector('.project-mobile-head')).display, mobileTitleDisplay: getComputedStyle(document.querySelector('.project-mobile-title')).display, mobileGoalDisplay: getComputedStyle(document.querySelector('.project-mobile-goal')).display, tabsDisplay: getComputedStyle(document.querySelector('.project-tabbar')).display, topbarDisplay: getComputedStyle(document.querySelector('.topbar')).display, globalBrand: document.querySelector('#appDrawer .sidebar-brand-copy strong') ? getComputedStyle(document.querySelector('#appDrawer .sidebar-brand-copy strong')).whiteSpace : 'hidden' };
    });
    assert.ok(detailShell.bodyWidth <= detailShell.viewport + 1, `Project detail must not overflow horizontally: ${JSON.stringify(detailShell)}`);
    assert.equal(detailShell.topbarDisplay, 'none', `Project workspace should use its own header without overlapping the shared app header: ${JSON.stringify(detailShell)}`);
    if (viewport.width > 900) {
      assert.equal(detailShell.drawerDisplay, 'flex', `The existing global navigation should become the desktop rail: ${JSON.stringify(detailShell)}`);
      assert.ok(detailShell.drawerLeft <= 0 && detailShell.drawerWidth >= 180, `The global rail should occupy the far left: ${JSON.stringify(detailShell)}`);
      assert.ok(detailShell.panelLeft >= detailShell.drawerWidth - 1, `The project content should start after the global rail: ${JSON.stringify(detailShell)}`);
      assert.ok(detailShell.projectNavWidth >= 180 && detailShell.mainLeft > detailShell.panelLeft + detailShell.projectNavWidth - 1, `Desktop project navigation should have its own column: ${JSON.stringify(detailShell)}`);
      assert.equal(detailShell.globalBrand, 'nowrap', `Desktop product identity must stay on one line: ${JSON.stringify(detailShell)}`);
    } else {
      assert.equal(detailShell.mobileHeadDisplay, 'grid', `Mobile should show a compact project header: ${JSON.stringify(detailShell)}`);
      assert.equal(detailShell.mobileTitleDisplay, 'grid', `Mobile project identity and status should remain visible: ${JSON.stringify(detailShell)}`);
      assert.equal(detailShell.mobileGoalDisplay, 'block', `Mobile should show the collapsible project goal before workspace sections: ${JSON.stringify(detailShell)}`);
      assert.equal(detailShell.tabsDisplay, 'flex', `Mobile should show its compact project section navigation: ${JSON.stringify(detailShell)}`);
      assert.equal(detailShell.projectNavDisplay, 'block', `The mobile project shell should reflow instead of reserving a sidebar: ${JSON.stringify(detailShell)}`);
    }
    if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/project-overview-${viewport.width}.png`, fullPage: false });
    await page.getByRole('button', { name: 'Add task' }).click();
    const taskDialog = page.locator('dialog.project-dialog');
    await taskDialog.locator('input[name="title"]').fill('Verify the responsive workspace');
    await taskDialog.locator('textarea[name="context_notes"]').fill('Review the design brief before this task.');
    await taskDialog.getByRole('button', { name: 'Save' }).click();
    await page.getByRole('button', { name: /Add milestone/i }).first().click();
    const milestoneDialog = page.locator('dialog.project-dialog');
    await milestoneDialog.locator('input[name="title"]').fill('Workspace ready');
    await milestoneDialog.locator('textarea[name="outcome"]').fill('The responsive workspace is ready to use.');
    await milestoneDialog.locator('input[name="target_date"]').fill('2026-12-15');
    await milestoneDialog.locator('textarea[name="completion_criteria"]').fill('The owner reviewed the mobile and desktop layout.');
    await milestoneDialog.locator('input[name="task_ids"]').check();
    await milestoneDialog.getByRole('button', { name: 'Save' }).click();
    const savedProject = serverState.projects.find(item => item.name === `Responsive workspace ${viewport.width}`);
    assert.equal(savedProject.tasks[0].context_notes, 'Review the design brief before this task.');
    assert.deepEqual(savedProject.milestones[0].task_ids, [savedProject.tasks[0].id]);
    if (viewport.isMobile) {
      const metrics = await page.evaluate(() => {
        const grid = document.querySelector('.project-stat-grid');
        const donut = document.querySelector('.project-progress-donut');
        const value = donut.querySelector('strong');
        const a = donut.getBoundingClientRect(), b = value.getBoundingClientRect();
        return { columns: getComputedStyle(grid).gridTemplateColumns.split(' ').length, donutCenterX: a.left + a.width / 2, valueCenterX: b.left + b.width / 2, donutCenterY: a.top + a.height / 2, valueCenterY: b.top + b.height / 2, bodyWidth: document.body.scrollWidth, viewport: innerWidth };
      });
      assert.equal(metrics.columns, 2, `Phone overview metrics should use readable two-column cards: ${JSON.stringify(metrics)}`);
      assert.ok(Math.abs(metrics.donutCenterX - metrics.valueCenterX) < 1 && Math.abs(metrics.donutCenterY - metrics.valueCenterY) < 1, `Progress value should be centered in its donut: ${JSON.stringify(metrics)}`);
      assert.ok(metrics.bodyWidth <= metrics.viewport + 1, `Phone overview should not overflow horizontally: ${JSON.stringify(metrics)}`);
    }
    await openProjectTab('plan');
    await page.locator('.project-task-title').filter({ hasText: 'Verify the responsive workspace' }).first().waitFor();
    await page.getByText('Workspace ready').first().waitFor();
    await page.locator('.project-task-row').first().waitFor();
    if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/project-plan-${viewport.width}.png`, fullPage: false });
    await page.getByRole('button', { name: 'Ask Vishnu' }).first().click();
    await page.locator('#p202cRoot').waitFor();
    assert.equal(await page.locator('.p202c-tabs button').count(),10,'Project navigation has ten genuine destinations');
    await page.locator('#projectChatForm textarea').fill('Please make a safe implementation plan.');
    await page.locator('#projectChatForm button[type="submit"]').click();
    await page.getByText(/Vishnu plan for:/).waitFor();
    assert.equal(serverState.turns.at(-1).conversation_id, serverState.projects[0].conversation_id, 'Project chat must use its linked canonical conversation');
    assert.equal(serverState.conversations.at(-1).conversation.context.project_id,serverState.projects[0].id,'Project thread uses saved Project ID');
    const before=serverState.conversations.length;
    if(viewport.width>900){await page.locator('.p202c-primary').first().click();}
    assert.ok(serverState.conversations.length>=before,'Existing Project conversations remain retained');
    if(viewport.width<=900){
      const projectTabs=page.locator('.p202c-tabs button:visible');
      assert.equal(await projectTabs.count(),5,'Mobile Project tabs expose Chat, Tasks, Files, Agents and More');
      await page.getByRole('button',{name:'Chats ▾'}).click();
      await page.locator('dialog.p202c-chat-sheet').getByRole('button',{name:'＋ New Project Chat'}).click();
      await page.waitForFunction(()=>document.querySelector('#p202cChats')===null || document.querySelector('#p202cRoot'));
      assert.ok(serverState.conversations.some(item=>item.conversation.context?.project_id===serverState.projects[0].id));
    }
    if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/project-chat-${viewport.width}.png`, fullPage: false });
    await openProjectTab('files');
    await page.locator('[data-project-action="add-files"]:visible').first().click();
    const filesDialog = page.locator('dialog.project-files-dialog');
    await filesDialog.locator('input[type=file]').setInputFiles({ name: 'project-notes.md', mimeType: 'text/markdown', buffer: Buffer.from('Responsive acceptance criteria') });
    await filesDialog.getByText('project-notes.md').waitFor();
    await filesDialog.getByRole('button', { name: 'Add to project' }).click();
    await page.getByText('project-notes.md').first().waitFor();
    await page.locator('[data-file-select]').click();
    if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/project-files-${viewport.width}.png`, fullPage: false });
    if (viewport.isMobile) {
      await page.locator('.project-file-inspector-backdrop').waitFor({ state: 'visible' });
      await page.locator('.project-file-inspector .project-file-close').click();
      await page.locator('.project-file-inspector-backdrop').waitFor({ state: 'hidden' });
    }
    await openProjectTab('plan');
    await page.locator('[data-project-task-edit]').first().click();
    const editTaskDialog = page.locator('dialog.project-dialog');
    await editTaskDialog.locator('input[name="file_ids"]').check();
    await editTaskDialog.getByRole('button', { name: 'Save' }).click();
    assert.deepEqual(savedProject.tasks[0].file_ids, [savedProject.files[0].id]);
    await page.getByText(/Uses project-notes\.md/).waitFor();
    await openProjectTab('discussions');
    await page.locator('[data-project-action="new-discussion"]:visible').first().click();
    const discussionDialog = page.locator('dialog.project-dialog');
    await discussionDialog.locator('input[name="title"]').fill('Review the mobile project composer');
    await discussionDialog.locator('textarea[name="content"]').fill('Check that the reply field stays visible around the keyboard.');
    await discussionDialog.locator('select[name="linked_item"]').selectOption({ label: 'Task · Verify the responsive workspace' });
    await discussionDialog.getByRole('button', { name: 'Save' }).click();
    await page.getByRole('heading', { name: 'Review the mobile project composer' }).waitFor();
    assert.equal(new URL(page.url()).searchParams.get('discussion'), savedProject.threads[0].id, 'Discussion URL should include the stable thread ID');
    await page.locator('[data-thread-reply-form] textarea').fill('The composer stays in the thread panel.');
    await page.locator('[data-thread-reply-form] button[type="submit"]').click();
    await page.getByText('The composer stays in the thread panel.').waitFor();
    if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/project-discussions-${viewport.width}.png`, fullPage: false });
    await page.getByRole('button', { name: 'Follow', exact: true }).click();
    await page.getByRole('button', { name: 'Following', exact: true }).waitFor();
    const decisionPin = page.locator('[data-thread-pin]').last();
    await decisionPin.click();
    await page.getByText('Pinned to project context').waitFor();
    await page.locator('.project-thread-head .project-thread-actions>button[data-thread-resolve]').click();
    if (viewport.isMobile) await page.locator('.project-thread-mobile-back').dispatchEvent('click');
    await page.locator('[data-discussion-filter]').selectOption('resolved');
    await page.getByRole('button', { name: 'Review the mobile project composer' }).click();
    await page.locator('.project-thread-head .project-thread-actions>button[data-thread-resolve]').click();
    assert.equal(savedProject.threads[0].status, 'open');
    await openProjectTab('files');
    await page.locator('[data-file-select]').click();
    await page.locator('[data-file-pin]').click();
    assert.equal(savedProject.files[0].is_pinned, true, 'File pin should persist through the project data API');
    if (viewport.isMobile) await page.locator('.project-file-inspector .project-file-close').click();
    await openProjectTab('approvals');
    await page.getByRole('button', { name: 'New proposal' }).click();
    const proposalDialog = page.locator('dialog.project-dialog');
    await proposalDialog.locator('input[name="title"]').fill('Review scoped project change');
    await proposalDialog.locator('textarea[name="summary"]').fill('A specific change for this workspace.');
    await proposalDialog.locator('textarea[name="impact_summary"]').fill('Only the project workflow changes.');
    await proposalDialog.locator('textarea[name="scope_summary"]').fill('This project and linked task only.');
    await proposalDialog.locator('input[name="task_ids"]').check();
    await proposalDialog.locator('input[name="file_ids"]').check();
    await proposalDialog.getByRole('button', { name: 'Save' }).click();
    await page.getByRole('button', { name: 'Review' }).click();
    const reviewDialog = page.locator('dialog.project-approval-dialog');
    await reviewDialog.locator('textarea[name="comments"]').fill('Clarify the rollback scope.');
    await reviewDialog.getByRole('button', { name: 'Request changes' }).click();
    await page.getByText(/changes requested/).waitFor();
    await page.getByRole('button', { name: 'Revise' }).click();
    const reviseDialog = page.locator('dialog.project-dialog');
    await reviseDialog.locator('textarea[name="summary"]').fill('Revised with bounded rollback scope.');
    await reviseDialog.getByRole('button', { name: 'Save' }).click();
    await page.getByRole('button', { name: 'Review' }).click();
    const approvalDialog = page.locator('dialog.project-approval-dialog');
    await approvalDialog.getByRole('button', { name: 'Approve & continue' }).click();
    assert.equal(savedProject.approvals[0].status, 'approved');
    assert.equal(savedProject.approvals[0].history.length, 3);
    assert.equal(savedProject.approvals[0].history[0].comments, 'Clarify the rollback scope.');
    await openProjectTab('activity');
    await page.getByRole('heading', { name: 'Activity' }).waitFor();
    await page.locator('[data-pa-event]').first().waitFor({ state: 'visible' });
    await page.locator('[data-pa-query]').fill('Verify the responsive workspace');
    await page.locator('[data-pa-event]').filter({ hasText: 'created task' }).first().waitFor({ state: 'visible' });
    await page.locator('[data-pa-category="tasks"]').click();
    await page.locator('[data-pa-actor]').selectOption('you');
    assert.equal(await page.locator('[data-pa-event]').count(), 1, 'Activity category, actor, and search filters should combine');
    await page.locator('[data-pa-reset]').first().click();
    if (screenshotDir) {
      await page.locator('#toast.show').waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {});
      await page.evaluate(() => { window.scrollTo(0, 0); const body = document.querySelector('#moduleBody'); if (body) body.scrollTop = 0; });
      await page.screenshot({ path: `${screenshotDir}/project-activity-${viewport.width}.png`, fullPage: false });
    }
    await openProjectTab('live');
    await page.getByRole('heading', { name: 'Live work' }).waitFor();
    if (screenshotDir) { await page.locator('#toast.show').waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {}); await page.evaluate(() => window.scrollTo(0, 0)); await page.screenshot({ path: `${screenshotDir}/project-live-${viewport.width}.png`, fullPage: false }); }
    await page.getByText('Queue order is based on saved task creation time').waitFor();
    await page.locator('[data-live-manage]').click();
    await page.getByRole('heading', { name: 'Work plan' }).waitFor();
    await openProjectTab('status');
    await page.getByRole('heading', { name: '3D status' }).waitFor();
    if (screenshotDir) { await page.locator('#toast.show').waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {}); await page.evaluate(() => window.scrollTo(0, 0)); await page.screenshot({ path: `${screenshotDir}/project-status-${viewport.width}.png`, fullPage: false }); }
    await page.locator('[data-status-view="2d"]').click();
    await page.locator('.pa-status-visual.is-list').waitFor();
    await page.locator('[data-status-task-select]').first().click();
    await page.locator('.pa-status-detail').getByRole('heading', { name: 'Verify the responsive workspace' }).waitFor();
    await openProjectTab('structure');
    await page.getByRole('heading', { name: '3D project structure' }).waitFor();
    if (screenshotDir) { await page.locator('#toast.show').waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {}); await page.evaluate(() => window.scrollTo(0, 0)); await page.screenshot({ path: `${screenshotDir}/project-structure-${viewport.width}.png`, fullPage: false }); }
    await page.locator('[data-structure-view="2d"]').click();
    await page.locator('.pa-structure-graph.is-map').waitFor();
    await page.locator('[data-structure-select="task:' + savedProject.tasks[0].id + '"]').first().click();
    await page.locator('.pa-structure-detail').getByRole('heading', { name: 'Verify the responsive workspace' }).waitFor();
    await openProjectTab('live');
    await page.getByText('No pending project proposals need review.').waitFor();
    await openProjectTab('plan');
    for (const mode of ['board', 'timeline', 'list']) {
      await page.locator(`[data-plan-view="${mode}"]`).click();
      await page.locator('.project-plan-page').waitFor();
    }
    const overflow = await page.evaluate(() => ({ body: document.body.scrollWidth, viewport: innerWidth, module: document.querySelector('#moduleBody').scrollWidth }));
    assert.ok(overflow.body <= overflow.viewport + 1, `Workspace must not cause page-width overflow: ${JSON.stringify(overflow)}`);
    assert.deepEqual(errors, [], `No browser exceptions at ${viewport.width}px: ${errors.join(' | ')}`);
    await page.close();
  }
  const preview = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, serviceWorkers: 'block' });
  await preview.goto(`http://127.0.0.1:${address.port}/iphone/?uiDemo=1`, { waitUntil: 'domcontentloaded' });
  await preview.waitForFunction(() => document.body.classList.contains('home-landing'));
  await preview.locator('#historyButton').click();
  await preview.locator('#appDrawer [data-app-module="projects"]').click();
  await preview.getByText('Preview data · sample projects only; these records are not saved to your account.').waitFor();
  assert.equal(await preview.locator('.project-card-rich').count(), 4, 'demo preview should show four clearly labeled sample projects');
  assert.ok((await preview.locator('.project-card-rich [data-project-open]').first().innerText()).includes('Preview'), 'demo project action must remain labeled as preview');
  await preview.locator('.project-card-rich [data-project-open]').first().click();
  await preview.getByText(/Preview project only/).waitFor();
  await preview.close();
  console.log('Projects workspace browser smoke passed at 390px, 820px, and 1440px: project CRUD, Activity filters, Live work, status and structure views, task/file links, proposal review, chat, and responsive overflow.');
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
