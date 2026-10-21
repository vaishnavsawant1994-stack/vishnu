/* Reference-led global search. Uses existing authenticated resource APIs only. */
(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (value) => window.escapeHtml(String(value ?? ''));
  let query = '';
  let scope = 'all';
  let epoch = 0;
  // Reject asynchronous module openings that are superseded by a later route.
  // Otherwise an older openModule('search') promise can remount Global Search
  // over a newer screen while an owner is interacting with its controls.
  let navigationEpoch = 0;
  let timer = 0;
  const cache = { conversations: [], projects: [] };

  const scopes = [
    ['all', 'All'], ['conversations', 'Conversations'], ['projects', 'Projects']
  ];

  function openItem(type, id) {
    if (type === 'conversation') {
      document.body.classList.remove('global-search-mode');
      if (typeof window.openConversation === 'function') window.openConversation(id).catch((e) => window.showToast(e.message));
      else window.showToast('Conversation navigation is unavailable in this view.');
      return;
    }
    if (type === 'project') {
      if (typeof window.openProject !== 'function') {
        window.showToast('Project navigation is unavailable in this view.');
        return;
      }
      window.openModule('projects')
        .then(() => window.openProject(id))
        .catch((error) => window.showToast(error?.message || 'The selected project could not be opened.'));
    }
  }

  function resultCard(type, item) {
    const conversation = type === 'conversation';
    const id = item.id;
    const title = item.title || (conversation ? 'New conversation' : 'Untitled project');
    const preview = conversation
      ? (item.preview || item.last_message || 'No messages recorded yet.')
      : (item.description || item.summary || 'No project summary recorded.');
    const location = conversation
      ? (item.context || 'Conversation')
      : (item.workspace_name || item.workspace || 'Project');
    const status = item.status ? `<span class="gs-status">${esc(item.status.replaceAll('_', ' '))}</span>` : '';
    const stamp = item.updated_at || item.created_at;
    const time = stamp ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(stamp)) : '';
    return `<article class="gs-result"><button type="button" class="gs-result-main" data-gs-open="${esc(type)}" data-gs-id="${esc(id)}">
      <span class="gs-result-icon" aria-hidden="true">${conversation ? '◉' : '◇'}</span><span class="gs-result-copy"><strong>${esc(title)}</strong><span class="gs-location">${esc(location)}${time ? ` · ${esc(time)}` : ''}</span><span class="gs-summary">${esc(preview)}</span></span>${status}<span class="gs-arrow" aria-hidden="true">›</span>
    </button></article>`;
  }

  function filtered(rows, type) {
    const q = query.trim().toLocaleLowerCase();
    if (!q) return rows;
    return rows.filter((item) => {
      const text = type === 'conversation'
        ? [item.title, item.preview, item.last_message, item.context].join(' ')
        : [item.title, item.name, item.description, item.summary, item.workspace_name].join(' ');
      return text.toLocaleLowerCase().includes(q);
    });
  }

  function resultsMarkup() {
    const conversations = scope === 'projects' ? [] : filtered(cache.conversations, 'conversation');
    const projects = scope === 'conversations' ? [] : filtered(cache.projects, 'project');
    const groups = [];
    if (conversations.length) groups.push(`<section class="gs-group"><header><h2>Conversations</h2><span>${conversations.length}</span></header>${conversations.map((row) => resultCard('conversation', row)).join('')}</section>`);
    if (projects.length) groups.push(`<section class="gs-group"><header><h2>Projects</h2><span>${projects.length}</span></header>${projects.map((row) => resultCard('project', row)).join('')}</section>`);
    const total = conversations.length + projects.length;
    return total ? groups.join('') : `<div class="gs-empty"><span aria-hidden="true">⌕</span><strong>${query ? 'No matching results' : 'Search your Vishnu'}</strong><p>${query ? 'Try a different phrase or search another connected category.' : 'Search is currently connected to your conversations and projects.'}</p></div>`;
  }

  function bind() {
    document.querySelectorAll('[data-gs-scope]').forEach((button) => button.onclick = () => {
      scope = button.dataset.gsScope;
      render(false);
    });
    document.querySelectorAll('[data-gs-open]').forEach((button) => button.onclick = () => openItem(button.dataset.gsOpen, button.dataset.gsId));
    const input = $('globalSearchQuery');
    if (input) {
      input.oninput = () => {
        query = input.value;
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => load(), 220);
      };
      input.onkeydown = (event) => {
        if (event.key === 'Escape') { query = ''; render(); input.focus(); }
        if (event.key === 'Enter') { event.preventDefault(); load(); }
      };
    }
  }

  function render(focus = false) {
    const root = $('moduleBody');
    if (!root) return;
    root.innerHTML = `<div class="global-search-page"><header class="gs-heading"><span class="gs-heading-icon" aria-hidden="true">⌕</span><div><h1>Global Search</h1><p>Find anything in your connected Vishnu sources.</p></div></header>
      <label class="gs-input-wrap"><span aria-hidden="true">⌕</span><input id="globalSearchQuery" type="search" value="${esc(query)}" placeholder="Search conversations and projects…" aria-label="Search Vishnu resources" autocomplete="off"><button type="button" class="gs-clear" aria-label="Clear search" ${query ? '' : 'hidden'}>×</button></label>
      <div class="gs-scopes" role="group" aria-label="Search scope">${scopes.map(([id, label]) => `<button type="button" data-gs-scope="${id}" class="${scope === id ? 'active' : ''}" aria-pressed="${scope === id}">${label}</button>`).join('')}</div>
      <p class="gs-coverage" role="status">Connected sources: Conversations and Projects. Other Vishnu sources are not yet indexed in this search.</p><div id="globalSearchResults" aria-live="polite">${resultsMarkup()}</div></div>`;
    bind();
    const clear = root.querySelector('.gs-clear');
    clear.onclick = () => { query = ''; load().then(() => $('globalSearchQuery')?.focus()); };
    if (focus) $('globalSearchQuery')?.focus();
  }

  async function load() {
    const current = ++epoch;
    const q = query.trim();
    if (!q) {
      render();
      return;
    }
    const panel = $('globalSearchResults');
    if (panel) panel.innerHTML = '<div class="gs-loading" role="status">Searching connected sources…</div>';
    const wantsConversations = scope !== 'projects';
    const wantsProjects = scope !== 'conversations';
    try {
      const [conversationData, projectData] = await Promise.all([
        wantsConversations ? window.api(`/conversations?q=${encodeURIComponent(q)}&limit=100`) : Promise.resolve({ conversations: [] }),
        wantsProjects ? window.api(`/projects?q=${encodeURIComponent(q)}&status=all&sort=recent`) : Promise.resolve({ projects: [] })
      ]);
      if (current !== epoch) return;
      cache.conversations = Array.isArray(conversationData.conversations) ? conversationData.conversations : [];
      cache.projects = Array.isArray(projectData.projects) ? projectData.projects : [];
      const resultHost = $('globalSearchResults');
      if (resultHost) resultHost.innerHTML = resultsMarkup();
      bind();
    } catch (error) {
      if (current !== epoch) return;
      const resultHost = $('globalSearchResults');
      if (resultHost) resultHost.innerHTML = `<div class="gs-error" role="alert"><strong>${error?.status === 401 ? 'Sign in again to search your Vishnu.' : 'Search could not reach your connected sources.'}</strong><button type="button" class="ui-button" data-gs-retry>Retry</button></div>`;
      resultHost?.querySelector('[data-gs-retry]')?.addEventListener('click', load);
    }
  }

  const originalOpenModule = window.openModule;
  if (typeof originalOpenModule !== 'function') return;
  window.openModule = function (name) {
    const request = ++navigationEpoch;
    if (name !== 'search') {
      ++epoch; // Cancel in-flight search responses during navigation.
      if (timer) { clearTimeout(timer); timer = 0; }
      document.body.classList.remove('global-search-mode');
      return originalOpenModule.call(this, name);
    }
    return originalOpenModule.call(this, name).then(() => {
      // Respect the most recent navigation, even if older promises resolve last.
      if (request !== navigationEpoch) return;
      document.body.classList.add('global-search-mode');
      const title = $('moduleTitle');
      const subtitle = $('moduleText');
      const metric = $('moduleMetric');
      if (title) title.textContent = 'Global Search';
      if (subtitle) subtitle.textContent = 'Find resources in connected Vishnu sources.';
      if (metric) metric.textContent = '';
      cache.conversations = [];
      cache.projects = [];
      render(true);
      if (!query.trim()) {
        // Keep the empty state honest; only make authenticated requests after a query.
      } else load();
    });
  };

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-reference-search]');
    if (!trigger) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    window.openModule('search');
  }, true);
  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      window.openModule('search');
    }
  });
  window.addEventListener('vishnu:new-chat', () => document.body.classList.remove('global-search-mode'));
})();
