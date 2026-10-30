/* P2-01 Home. Presentation-only adaptation of the existing Vishnu shell.
 * Owner-scoped reads use the canonical conversation, Today, Work and attention APIs.
 */
(() => {
  'use strict';
  if (window.__vishnuP201) return;
  const $ = id => document.getElementById(id);
  const bridge = () => window.vishnuChatBridge;
  const home = () => document.body.classList.contains('home-landing') && !$('voicePanel')?.classList.contains('hidden');
  const activeStates = new Set(['RUNNING', 'VERIFYING', 'RECOVERING', 'RETRYING']);
  let initialized = false, wasHome = false, refreshEpoch = 0, nextRefresh = 0, requestController = null;
  const model = {today: null, work: null, attention: null, status: null};
  const elements = {};
  const icon = (name) => ({
    chat: '▣', today: '▣', work: '▣', spaces: '▦',
    files: '▤', create: '✦', home: '⌂', search: '⌕',
    notification: '♧', settings: '⚙', more: '•••'
  })[name] || '◈';

  const run = async (action) => {
    try { await action(); }
    catch (error) { bridge()?.showToast?.(error?.message || 'This action is unavailable.'); }
  };
  const module = name => {
    if (!bridge()?.openModule) return bridge()?.showToast?.('This area is unavailable.');
    return bridge().openModule(name);
  };
  const navigate = {
    chat: () => run(async () => {
      const current = bridge()?.current?.id;
      if (current) return bridge().openConversation(current);
      const data = await bridge().api('/conversations?limit=1');
      const last = Array.isArray(data?.conversations) ? data.conversations.slice().sort((a,b) => Date.parse(b.updated_at || b.created_at || 0)-Date.parse(a.updated_at || a.created_at || 0))[0] : null;
      if (last?.id) return bridge().openConversation(last.id);
      return bridge().createConversation();
    }),
    today: () => bridge()?.openTodayScreen?.('all'),
    work: () => module('projects'),
    spaces: () => module('labs'),
    files: () => module('knowledge'),
    create: () => { bridge()?.setDraft?.('Create '); },
    home: () => module('home'),
    search: () => typeof window.openModule === 'function' ? window.openModule('search') : module('search'),
    notification: () => window.__vishnuWorkAttentionCenter?.open?.('all') || bridge()?.showToast?.('Owner notifications and attention are not available on this runtime.'),
    settings: () => module('settings'),
    more: () => $('historyButton')?.click()
  };
  const safeRead = async (path, signal) => {
    if (!bridge()?.api) throw new Error('Vishnu is not connected');
    return bridge().api(path, {signal});
  };
  function make(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  function actionButton(label, cls, onClick) {
    const button = make('button', cls, label);
    button.type = 'button';
    button.addEventListener('click', onClick);
    return button;
  }
  function build() {
    if (initialized || !$('homeIntro') || !$('homeSphereStage') || !$('homeGreeting')) return;
    initialized = true;
    document.body.classList.add('p2-home-ready');
    const intro = $('homeIntro'), greeting = $('homeGreeting').parentNode, sphere = $('homeSphereStage');
    const hero = make('section', 'p2-hero');
    hero.setAttribute('aria-label', 'Vishnu intelligence home');
    intro.insertBefore(hero, sphere);
    greeting.classList.add('p2-greeting');
    hero.append(greeting, sphere);
    const subtitle = $('homeSubtitle');
    if (subtitle) subtitle.textContent = "I'm Vishnu. What would you like to do today?";
    const status = make('div', 'p2-status');
    const ai = actionButton('Checking AI status…', 'p2-status-ai', () => module('settings'));
    const systems = actionButton('View system status', 'p2-status-system', () => module('system'));
    status.append(ai, systems);
    greeting.append(status);
    elements.ai = ai; elements.systems = systems;
    sphere.setAttribute('role', 'img');
    sphere.setAttribute('aria-label', 'Vishnu neural intelligence Core');
    const avatar = make('div', 'p2-core-avatar');
    avatar.setAttribute('aria-hidden', 'true');
    avatar.innerHTML = '<svg viewBox="0 0 80 80" focusable="false"><circle cx="40" cy="28" r="11"/><path d="M19 65c1-15 9-23 21-23s20 8 21 23"/></svg>';
    sphere.append(avatar);
    const daily = make('section', 'p2-daily');
    daily.setAttribute('aria-label', 'Local time and daily summary');
    const date = make('div', 'p2-date');
    const time = make('div', 'p2-time');
    const details = make('div', 'p2-daily-rows');
    daily.append(date, time, details);
    hero.append(daily);
    elements.date = date; elements.time = time; elements.daily = details;
    [
      ['meetings', 'Upcoming meetings', navigate.today],
      ['tasks', 'Important tasks', navigate.today],
      ['approvals', 'Approval requests', () => window.__vishnuWorkAttentionCenter?.open?.('approvals') || module('activities')],
      ['work', 'Active work', navigate.work]
    ].forEach(([id, label, onClick]) => {
      const button = actionButton('', 'p2-daily-row p2-row-' + id, onClick);
      const symbol = make('span', 'p2-row-icon', ({meetings:'▣',tasks:'✓',approvals:'♙',work:'◈'})[id]);
      symbol.setAttribute('aria-hidden', 'true');
      const content = make('span', 'p2-row-content');
      content.append(make('strong', '', label), make('small', '', 'Loading…'));
      const arrow = make('span', 'p2-row-chevron', '›');
      arrow.setAttribute('aria-hidden', 'true');
      button.append(symbol, content, arrow);
      details.append(button);
      elements[id] = button;
    });
    const slot = $('referenceComposerSlot');
    slot?.classList.add('p2-composer-slot');
    const message = $('message');
    if (message) message.placeholder = 'Ask Vishnu anything or give it a task…';

    // Replace the old four Home tiles, which otherwise retain stale click listeners.
    const quick = intro.querySelector('.v-shortcuts');
    if (quick) {
      quick.replaceChildren();
      [
        ['Continue Chat', 'Pick up where you left off', 'chat', navigate.chat],
        ['Today', 'View your day', 'today', navigate.today],
        ['My Work', 'Tasks and agents', 'work', navigate.work],
        ['Workspaces', 'Projects and products', 'spaces', navigate.spaces],
        ['My Files', 'Find and analyze', 'files', navigate.files],
        ['Create', 'Generate with AI', 'create', navigate.create]
      ].forEach(([title, sub, glyph, onClick], i) => {
        const button = actionButton('', 'v-card p2-tile p2-tile-' + glyph, onClick);
        // Do not reuse legacy tile IDs; older Home adapters bind onclick to them.
        const symbol = make('span', 'v-icon', icon(glyph));
        symbol.setAttribute('aria-hidden', 'true');
        const copy = make('span', 'p2-tile-copy');
        copy.append(make('strong', '', title), make('small', '', sub));
        const arrow = make('span', 'v-chev', '›');
        arrow.setAttribute('aria-hidden', 'true');
        button.append(symbol, copy, arrow);
        quick.append(button);
      });
    }
    const lower = make('div', 'p2-lower');
    slot?.parentNode?.insertBefore(lower, $('homeProjectsSection'));
    const recent = $('homeRecentSection');
    if (recent) {
      lower.append(recent);
      const label = $('homeRecentHeading');
      if (label) label.textContent = 'Recent Activity';
    }
    const work = make('section', 'p2-panel p2-work-panel');
    work.innerHTML = '<div class="p2-panel-heading"><h2>Active Work</h2><button type="button" data-p2-view-work>View all ›</button></div><div class="p2-work-content" role="status">Loading Work summary…</div>';
    work.querySelector('[data-p2-view-work]').onclick = navigate.work;
    lower.append(work);
    elements.workPanel = work.querySelector('.p2-work-content');
    const tools = make('section', 'p2-panel p2-tools-panel');
    tools.innerHTML = '<div class="p2-panel-heading"><h2>Quick Tools</h2><button type="button" data-p2-edit-tools>Edit</button></div><div class="p2-tool-grid"></div>';
    const grid = tools.querySelector('.p2-tool-grid');
    const definitions = [
      ['Summarize', '▤', 'Summarize '], ['Analyze', '▥', 'Analyze '],
      ['Plan', '☷', 'Help me plan '], ['Code', '⌘', 'Help me code '],
      ['Create Image', '▧', 'Create an image of '],
      ['Research', '⌕', 'Research ']
    ];
    const storageKey = 'vishnu.p2.quick-tools.v1';
    const allowed = new Set(definitions.map(item => item[0]));
    const readSelection = () => {
      try {
        const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
        return Array.isArray(saved) && saved.length && saved.every(id => allowed.has(id)) ? [...new Set(saved)] : definitions.map(item => item[0]);
      } catch { return definitions.map(item => item[0]); }
    };
    let visibleTools = readSelection();
    const renderTools = () => {
      grid.replaceChildren();
      visibleTools.forEach(id => {
        const found = definitions.find(item => item[0] === id);
        if (!found) return;
        const [title, symbol, draft] = found;
        const btn = actionButton('', 'p2-tool', () => bridge()?.setDraft?.(draft));
        btn.append(make('span', '', symbol), make('small', '', title));
        btn.title = 'Prepare a ' + title + ' request; availability depends on configured capabilities';
        grid.append(btn);
      });
    };
    renderTools();
    tools.querySelector('[data-p2-edit-tools]').onclick = () => {
      const dialog = make('dialog', 'p2-edit-tools');
      const heading = make('h2', '', 'Customize Quick Tools');
      const note = make('p', '', 'Select shortcuts to show on this device. This does not enable unavailable AI capabilities.');
      const choices = make('div', 'p2-tool-choices');
      definitions.forEach(([title]) => {
        const label = make('label', '');
        const box = make('input');
        box.type = 'checkbox'; box.value = title; box.checked = visibleTools.includes(title);
        label.append(box, document.createTextNode(' ' + title));
        choices.append(label);
      });
      const buttons = make('div', 'p2-dialog-buttons');
      const cancel = actionButton('Cancel', 'p2-tool-cancel', () => dialog.close());
      const save = actionButton('Save shortcuts', 'p2-tool-save', () => {
        const selected = [...choices.querySelectorAll('input:checked')].map(item => item.value);
        if (!selected.length) return bridge()?.showToast?.('Choose at least one shortcut.');
        try {
          localStorage.setItem(storageKey, JSON.stringify(selected));
          visibleTools = selected;
          renderTools();
          dialog.close();
          bridge()?.showToast?.('Quick Tools saved on this device.');
        } catch {
          bridge()?.showToast?.('This browser blocked saving the shortcut preference.');
        }
      });
      buttons.append(cancel,save);
      dialog.append(heading,note,choices,buttons);
      document.body.append(dialog);
      dialog.addEventListener('close', () => dialog.remove(), {once:true});
      dialog.showModal();
      choices.querySelector('input')?.focus();
    };
    lower.append(tools);
    $('homeProjectsSection')?.classList.add('p2-secondary-projects');
    intro.querySelector('.today-panel')?.classList.add('p2-secondary-today');
    installNavigation();
    paintClock();
    paintEmpty('Loading Home information…');
  }
  function installNavigation() {
    const sidebar = document.querySelector('.reference-desktop-sidebar nav');
    if (sidebar) {
      const knowledge = sidebar.querySelector('[data-app-module="knowledge"]');
      if (knowledge) knowledge.lastChild.textContent = 'Library';
      const tools = sidebar.querySelector('[data-app-module="tools"]');
      if (tools) tools.lastChild.textContent = 'Tools';
      const devices = sidebar.querySelector('[data-app-module="devices"]');
      if (devices) {
        const more = actionButton(' More', 'p2-sidebar-added p2-sidebar-more', navigate.more);
        more.prepend(make('span', '', '◫'));
        devices.after(more);
      }
      const search = actionButton(' Search', 'p2-sidebar-added p2-sidebar-search', navigate.search);
      search.prepend(make('span', '', '⌕'));
      const notifications = actionButton(' Notifications', 'p2-sidebar-added', navigate.notification);
      notifications.prepend(make('span', '', '♧'));
      const anchor = sidebar.querySelector('[data-app-module="settings"]');
      if (anchor) anchor.before(search, notifications);
    }
    const nav = document.querySelector('.reference-mobile-nav');
    if (nav) {
      nav.replaceChildren();
      [
        ['Home','home', navigate.home], ['Chat','chat', navigate.chat],
        ['Today','today', navigate.today], ['Work','work', navigate.work],
        ['More','more', navigate.more]
      ].forEach(([label, glyph, onClick]) => {
        const button = actionButton('', 'p2-mobile-' + glyph, onClick);
        button.dataset.p2Mobile = glyph;
        button.append(make('span', '', icon(glyph)), make('small', '', label));
        nav.append(button);
      });
    }
    document.querySelectorAll('[data-reference-search]').forEach(button => {
      // Capture takes precedence over the legacy History-only search handler.
      button.addEventListener('click', event => {
        event.stopImmediatePropagation();
        navigate.search();
      }, true);
    });
    const headerNotification = document.querySelector('.reference-desktop-tools [aria-label="Notifications"]');
    headerNotification?.addEventListener('click', event => {
      event.stopImmediatePropagation();
      navigate.notification();
    }, true);
    const profile = document.querySelector('.reference-desktop-tools .reference-profile');
    profile?.addEventListener('click', event => {
      event.stopImmediatePropagation();
      module('owner');
    }, true);
    const headerActions = document.querySelector('.topbar-actions');
    if (headerActions && !headerActions.querySelector('.p2-mobile-notifications')) {
      const notifications = actionButton('♧', 'p2-mobile-notifications', navigate.notification);
      notifications.setAttribute('aria-label', 'Open notifications and approvals');
      headerActions.prepend(notifications);
    }
    const owner = document.querySelector('[data-reference-owner]');
    if (owner) owner.textContent = 'Owner';
    const ownerSub = document.querySelector('.reference-owner small');
    if (ownerSub) ownerSub.textContent = 'Owner account';
  }
  function paintClock() {
    if (!elements.time) return;
    const now = new Date();
    const locale = navigator.language || undefined;
    elements.time.textContent = new Intl.DateTimeFormat(locale, {hour:'numeric', minute:'2-digit'}).format(now);
    elements.date.textContent = new Intl.DateTimeFormat(locale, {weekday:'long', day:'numeric', month:'long', year:'numeric'}).format(now);
    const name = model.status?.owner_display_name || model.status?.owner?.display_name || model.status?.owner?.name ||
      (typeof window.ownerDisplayName === 'function' ? window.ownerDisplayName() : '');
    if (home() && $('homeGreeting')) {
      const hour = now.getHours();
      const part = hour < 12 ? 'Good Morning' : hour < 18 ? 'Good Afternoon' : 'Good Evening';
      $('homeGreeting').textContent = part + (String(name).trim() ? ', ' + String(name).trim() : '');
      const displayName = String(name).trim();
      const owner = document.querySelector('[data-reference-owner]');
      if (owner) owner.textContent = displayName || 'Owner';
      const initials = displayName ? displayName.split(/\s+/).slice(0,2).map(part => part[0].toUpperCase()).join('') : '◯';
      const avatar = document.querySelector('.reference-owner .reference-avatar');
      if (avatar) avatar.textContent = initials;
      const profile = document.querySelector('.reference-desktop-tools .reference-profile');
      if (profile) profile.textContent = initials;
    }
  }
  function setRow(key, title, detail) {
    const button = elements[key];
    if (!button) return;
    button.querySelector('strong').textContent = title;
    button.querySelector('small').textContent = detail;
  }
  function paintEmpty(reason) {
    ['meetings','tasks','approvals','work'].forEach(id => {
      setRow(id, ({meetings:'Upcoming meetings',tasks:'Important tasks',approvals:'Approval requests',work:'Active work'})[id], reason);
    });
    if (elements.workPanel) elements.workPanel.textContent = reason;
  }
  function paintToday(result) {
    if (result.status !== 'fulfilled' || !Array.isArray(result.value?.items)) {
      setRow('meetings', 'Upcoming meetings', 'Today data temporarily unavailable');
      setRow('tasks', 'Important tasks', 'Today data temporarily unavailable');
      return;
    }
    const items = result.value.items.filter(item => !['completed','dismissed','cancelled'].includes(String(item.status||'').toLowerCase()));
    const kind = item => {
      const match = String(item.context||'').match(/^personal-ai:today:(meeting|task|work|reminder)$/);
      return match ? match[1] : String(item.kind||'').toLowerCase();
    };
    const meetings = items.filter(item => {
      if (kind(item) !== 'meeting') return false;
      const raw = item.due_at || item.start_at || item.scheduled_at;
      if (!raw) return true; // Undated Vishnu commitments are still in the plan.
      const due = new Date(raw);
      return Number.isNaN(due.getTime()) || due.getTime() >= Date.now();
    });
    const tasks = items.filter(item => kind(item) === 'task');
    setRow('meetings','Upcoming meetings', meetings.length ? meetings.length + ' meeting(s) in your Vishnu plan' : 'No meetings in your Vishnu plan');
    setRow('tasks','Pending tasks', tasks.length ? tasks.length + ' pending task(s) across priorities' : 'No pending tasks');
  }
  function paintAttention(result) {
    if (result.status !== 'fulfilled' || result.value?.authority !== 'read_only_projection') {
      setRow('approvals','Approval requests','Approval data temporarily unavailable');
      return;
    }
    const count = result.value?.counts?.approval == null ? NaN : Number(result.value.counts.approval);
    const approvals = Number.isFinite(count) && count >= 0 ? count :
      (result.value.items || []).filter(item => ['approval_required','owner_decision_required'].includes(item.kind)).length;
    setRow('approvals','Approval requests', approvals ? approvals + ' need your decision' : 'No pending Work approvals');
  }
  function paintWork(result) {
    const panel = elements.workPanel;
    if (result.status !== 'fulfilled' || result.value?.authority !== 'read_only_projection') {
      setRow('work','Active work','Work data temporarily unavailable');
      if (panel) panel.textContent = 'Work summary is unavailable. Open My Work to retry.';
      return;
    }
    const data = result.value, orders = (Array.isArray(data.work_orders) ? data.work_orders : []);
    const active = orders.filter(item => activeStates.has(String(item.status||'').toUpperCase()));
    const reported = data?.counts?.active == null ? NaN : Number(data.counts.active);
    const count = Number.isFinite(reported) && reported >= 0 ? reported : active.length;
    setRow('work','Active work', count ? count + ' running or verifying' : 'No active WorkOrders');
    if (!panel) return;
    panel.replaceChildren();
    if (!active.length) {
      panel.append(make('p', 'p2-work-empty', count ? 'Active WorkOrders are running; open My Work for details.' : 'No active work right now.'));
      return;
    }
    active.slice(0, 2).forEach(order => {
      const button = actionButton('', 'p2-work-order', () => run(async () => {
        if (order.project_id && typeof window.openProject === 'function') {
          await module('projects'); await window.openProject(order.project_id, 'live');
        } else navigate.work();
      }));
      const copy = make('span', 'p2-work-copy');
      copy.append(make('strong','',order.title || order.objective || 'WorkOrder'),
        make('small','',String(order.status || 'Active').replaceAll('_',' ') +
          (order.project_name ? ' · ' + order.project_name : '')));
      button.append(make('span','p2-work-symbol','◈'),copy,make('span','p2-row-chevron','›'));
      panel.append(button);
    });
  }
  function paintStatus(result) {
    if (result.status !== 'fulfilled') {
      elements.ai.textContent = 'AI status unavailable';
      elements.ai.dataset.ready = 'false';
      elements.systems.textContent = 'System status unavailable ›';
      return;
    }
    const data = result.value || {};
    const state = String(data.model?.state || '').toLowerCase();
    const ready = state === 'available' || state === 'ready';
    elements.ai.textContent = ready ? '● AI Ready' :
      state === 'configured' ? 'AI configured' : 'AI setup or connection required';
    elements.ai.dataset.ready = String(ready);
    elements.systems.textContent = 'View system status ›';
    model.status = data;
    paintClock();
  }
  async function refreshData() {
    if (!home() || document.visibilityState === 'hidden') return;
    const epoch = ++refreshEpoch;
    requestController?.abort();
    const controller = new AbortController();
    requestController = controller;
    const paths = ['/everyday/active?limit=200','/work/summary','/work/attention','/status'];
    const timeout = setTimeout(() => controller.abort(), 8000);
    let results;
    try { results = await Promise.allSettled(paths.map(path => safeRead(path, controller.signal))); }
    finally { clearTimeout(timeout); if (requestController === controller) requestController = null; }
    if (epoch !== refreshEpoch || !home()) return;
    paintToday(results[0]);
    paintWork(results[1]);
    paintAttention(results[2]);
    paintStatus(results[3]);
  }
  function onRouteChange() {
    const nowHome = home();
    if (nowHome && !wasHome) {
      paintClock();
      refreshData();
      clearInterval(nextRefresh);
      nextRefresh = setInterval(() => { if (home() && document.visibilityState === 'visible') refreshData(); }, 45000);
    } else if (!nowHome && wasHome) {
      requestController?.abort();
      ++refreshEpoch;
      clearInterval(nextRefresh); nextRefresh = 0;
    }
    wasHome = nowHome;
    document.querySelectorAll('.reference-mobile-nav [data-p2-mobile]').forEach(button => {
      const active = nowHome && button.dataset.p2Mobile === 'home';
      button.classList.toggle('active', active);
      if (active) button.setAttribute('aria-current','page');
      else button.removeAttribute('aria-current');
    });
  }
  function boot() {
    build();
    const observer = new MutationObserver(onRouteChange);
    observer.observe(document.body, {attributes:true, attributeFilter:['class']});
    if ($('voicePanel')) observer.observe($('voicePanel'), {attributes:true, attributeFilter:['class']});
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') { paintClock(); refreshData(); } });
    window.addEventListener('focus', () => { paintClock(); refreshData(); });
    setInterval(() => { if (home() && document.visibilityState === 'visible') paintClock(); }, 60000);
    onRouteChange();
  }
  window.__vishnuP201 = {version:1, authority:'presentation_only', refresh:refreshData};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();