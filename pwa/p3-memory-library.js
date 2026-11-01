/* P3-02D/E: canonical-memory views. Data comes only from authenticated APIs. */
(() => {
  const esc = value => window.escapeHtml(String(value ?? ''));
  const api = (path, options) => window.api(path, options);
  const state = { view: 'all', memories: [], timeline: [], selected: null, detail: null, query: '', category: 'all', source: 'all', range: 'all', loading: false, error: '', epoch: 0 };
  let searchTimer = 0;
  const body = () => document.getElementById('moduleBody');
  const stamp = value => {
    if (!value) return 'Date unavailable';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'Date unavailable' : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
  };
  const title = row => row?.subject || row?.title || row?.label || 'Untitled memory';
  const content = row => row?.content || row?.summary || row?.description || '';
  const type = row => row?.type || row?.category || 'Uncategorized';
  const source = row => row?.source || row?.source_type || row?.origin || 'Source unavailable';
  const short = value => String(value || '').replace(/\s+/g, ' ').trim();
  function modeNav() {
    const views = [['overview', 'Overview'], ['ambient', 'Ambient'], ['tree', 'Tree'], ['graph', 'Graph'], ['timeline', 'Timeline'], ['all', 'All Memories']];
    return `<nav class="p3m-tabs" aria-label="Second Brain views">${views.map(([id, label]) => `<button type="button" data-p3m-view="${id}" aria-current="${state.view === id ? 'page' : 'false'}">${label}</button>`).join('')}</nav>`;
  }
  function shell() {
    const isTimeline = state.view === 'timeline';
    const heading = isTimeline ? 'Memory Timeline' : 'All Memories';
    const subtitle = isTimeline ? 'Browse authorized memory and life graph records by their recorded dates.' : 'Search and review the saved memories available to your account.';
    return `<section class="p3m-page" aria-labelledby="p3m-title"><header class="p3m-header"><div><span class="p3m-eyebrow">SECOND BRAIN</span><h1 id="p3m-title">${heading}</h1><p>${subtitle}</p></div><div class="p3m-header-actions"><button class="p3m-primary" type="button" data-p3m-add>Add Memory</button><button class="p3m-quiet" type="button" data-p3m-refresh>Refresh</button></div></header>${modeNav()}<div class="p3m-toolbar"><label class="p3m-search"><span class="sr-only">Search memories</span><input type="search" data-p3m-query placeholder="Search title, content, category or source" value="${esc(state.query)}"></label><label>Category<select data-p3m-category><option value="all">All categories</option>${categories().map(item => `<option value="${esc(item)}">${esc(item)}</option>`).join('')}</select></label><label>Source<select data-p3m-source><option value="all">All sources</option>${sources().map(item => `<option value="${esc(item)}">${esc(item)}</option>`).join('')}</select></label>${isTimeline ? '<label>Date range<select data-p3m-range><option value="all">All dates returned</option><option value="30">Last 30 days</option><option value="365">Last year</option></select></label>' : ''}<button class="p3m-quiet" type="button" data-p3m-clear>Clear filters</button></div>${state.error ? `<div class="p3m-state p3m-error" role="alert">${esc(state.error)} <button type="button" data-p3m-refresh>Retry</button></div>` : ''}${state.loading ? '<div class="p3m-state" role="status">Loading your authorized records…</div>' : renderContent(isTimeline) + details()}<p class="p3m-footnote">Records and dates are supplied by Vishnu’s authenticated memory services.</p></section>`;
  }
  function categories() { return [...new Set(rows().map(type).filter(x => x && x !== 'Uncategorized'))].sort((a, b) => a.localeCompare(b)); }
  function sources() { return [...new Set(rows().map(source).filter(x => x && x !== 'Source unavailable'))].sort((a, b) => a.localeCompare(b)); }
  function rows() { return state.view === 'timeline' ? state.timeline : state.memories; }
  function filtered() {
    const query = state.query.trim().toLocaleLowerCase();
    const cutoff = state.range === 'all' ? 0 : Date.now() - Number(state.range) * 86400000;
    return rows().filter(row => {
      const searchable = [title(row), content(row), type(row), source(row), row.project_id, row.scope, ...(Array.isArray(row.tags) ? row.tags : [])].join(' ').toLocaleLowerCase();
      const date = Date.parse(row.occurred_at || row.updated_at || row.created_at || '');
      return (!query || searchable.includes(query)) && (state.category === 'all' || type(row) === state.category) && (state.source === 'all' || source(row) === state.source) && (!cutoff || !Number.isFinite(date) || date >= cutoff);
    });
  }
  function renderContent(isTimeline) {
    const result = filtered();
    if (!result.length) return `<div class="p3m-state"><strong>${rows().length ? 'No records match these filters.' : isTimeline ? 'No timeline records are available.' : 'No saved memories are available.'}</strong><span>${rows().length ? 'Clear a filter or search for another term.' : 'When authorized memory data exists, it will appear here.'}</span></div>`;
    if (isTimeline) {
      let previous = '';
      return `<div class="p3m-timeline" aria-label="Memory timeline">${result.map(row => {
        const dateValue = row.occurred_at || row.updated_at || row.created_at;
        const day = dateValue ? new Intl.DateTimeFormat(undefined, { dateStyle: 'full' }).format(new Date(dateValue)) : 'Date unavailable';
        const group = day !== previous ? `<h2 class="p3m-day">${esc(day)}</h2>` : '';
        previous = day;
        const id = row.memory_id || row.id;
        return `${group}<button type="button" class="p3m-record p3m-event ${String(id) === String(state.selected) ? 'selected' : ''}" data-p3m-select="${esc(id)}"><time>${esc(stamp(dateValue))}</time><span class="p3m-record-body"><b>${esc(title(row))}</b><span>${esc(short(content(row)) || 'No content preview supplied.')}</span><small>${esc(type(row))} · ${esc(source(row))}${row.project_id ? ` · Project ${esc(row.project_id)}` : ''}</small></span><span class="p3m-arrow" aria-hidden="true">›</span></button>`;
      }).join('')}</div>`;
    }
    return `<div class="p3m-library"><div class="p3m-results">${result.length} records loaded</div><div class="p3m-list" role="list">${result.map(row => `<button role="listitem" type="button" class="p3m-record ${String(row.id) === String(state.selected) ? 'selected' : ''}" data-p3m-select="${esc(row.id)}"><span class="p3m-icon" aria-hidden="true">${esc(type(row).slice(0, 1).toUpperCase())}</span><span class="p3m-record-body"><b>${esc(title(row))}</b><span>${esc(short(content(row)) || 'No content preview supplied.')}</span><small>${esc(type(row))} · ${esc(source(row))}${row.scope ? ` · ${esc(row.scope)}` : ''}</small></span><time>${esc(stamp(row.updated_at || row.created_at))}</time></button>`).join('')}</div></div>`;
  }
  function render() {
    const root = body(); if (!root) return;
    root.innerHTML = shell();
    root.querySelectorAll('[data-p3m-view]').forEach(button => button.addEventListener('click', () => navigate(button.dataset.p3mView)));
    root.querySelector('[data-p3m-query]')?.addEventListener('input', event => { state.query = event.currentTarget.value; render(); const input = root.querySelector('[data-p3m-query]'); input?.focus(); input?.setSelectionRange(state.query.length, state.query.length); if(state.view!=='timeline'){clearTimeout(searchTimer);searchTimer=setTimeout(()=>load(state.view),260)} });
    root.querySelector('[data-p3m-category]')?.addEventListener('change', event => { state.category = event.currentTarget.value; render(); });
    root.querySelector('[data-p3m-source]')?.addEventListener('change', event => { state.source = event.currentTarget.value; render(); });
    root.querySelector('[data-p3m-range]')?.addEventListener('change', event => { state.range = event.currentTarget.value; render(); });
    root.querySelector('[data-p3m-clear]')?.addEventListener('click', () => { state.query = ''; state.category = state.source = 'all'; state.range = 'all'; render(); });
    root.querySelectorAll('[data-p3m-refresh]').forEach(button => button.addEventListener('click', () => load(state.view)));
    root.querySelector('[data-p3m-add]')?.addEventListener('click', () => {
      if (typeof window.addMemory === 'function') window.addMemory();
      else { window.openModule('memory'); window.showToast?.('Use the Memory screen’s Add Memory action.'); }
    });
    root.querySelectorAll('[data-p3m-select]').forEach(button => button.addEventListener('click', () => select(button.dataset.p3mSelect)));
    bindDetail();
  }
  function bindDetail() {
    const panel = body()?.querySelector('[data-p3m-detail]'); if (!panel) return;
    panel.querySelector('[data-p3m-close]')?.addEventListener('click', () => { state.selected = null; state.detail = null; render(); });
    panel.querySelector('[data-p3m-open]')?.addEventListener('click', () => { if (state.detail?.id) { window.openModule('memory'); window.showToast?.('Select this memory in the Memory view to open its full detail.'); } });
    panel.querySelector('[data-p3m-full]')?.addEventListener('click', () => {
      const id = state.detail?.memory_id || state.detail?.id;
      if (id && typeof window.openMemoryDetail === 'function') window.openMemoryDetail(String(id));
      else window.showToast?.('Full memory details are unavailable for this timeline record.');
    });
  }
  async function select(id) {
    state.selected = id;
    if (state.view === 'all') {
      try { state.detail = await api('/memory/' + encodeURIComponent(id)); }
      catch (error) { state.error = error?.message || 'Memory details are unavailable.'; }
    } else {
      const record = state.timeline.find(row => String(row.memory_id || row.id) === String(id));
      if (record?.memory_id) { try { state.detail = await api('/memory/' + encodeURIComponent(record.memory_id)); } catch (error) { state.detail = record; state.error = error?.message || 'Full memory details are unavailable.'; } }
      else state.detail = record || null;
    }
    render();
  }
  function details() {
    const row = state.detail; if (!row) return '';
    const metadata = row.metadata && typeof row.metadata === 'object' ? row.metadata : (() => { try { return JSON.parse(row.metadata_json || '{}'); } catch { return {}; } })();
    const privacy = metadata.scope || row.scope || 'Not provided';
    return `<aside class="p3m-detail" data-p3m-detail aria-label="Selected memory details"><header><h2>Memory Details</h2><button type="button" data-p3m-close aria-label="Close details">&times;</button></header><h3>${esc(title(row))}</h3><p>${esc(content(row) || 'No content supplied.')}</p><dl><dt>Category</dt><dd>${esc(type(row))}</dd><dt>Source</dt><dd>${esc(source(row))}</dd><dt>Scope</dt><dd>${esc(privacy)}</dd><dt>Created</dt><dd>${esc(stamp(row.created_at))}</dd><dt>Updated</dt><dd>${esc(stamp(row.updated_at || row.created_at))}</dd>${row.importance ? `<dt>Importance</dt><dd>${esc(row.importance)}</dd>` : ''}${row.confidence != null ? `<dt>Confidence</dt><dd>${esc(row.confidence)}</dd>` : ''}</dl><p class="p3m-honest">Only fields returned by Vishnu are shown.</p><button type="button" class="p3m-primary" data-p3m-full>Open full memory details</button></aside>`;
  }
  function renderBase() {
    const root = body(); if (!root) return;
    const prior = root.innerHTML;
    const selected = details();
    root.innerHTML = prior.replace('</section>', `${selected}</section>`);
    bindDetail();
  }
  function navigate(view) {
    if (['overview', 'ambient', 'tree', 'graph'].includes(view)) {
      const url = new URL(location.href); url.searchParams.set('memoryView', view); history.pushState({ memoryView: view }, '', url);
      if (typeof window.loadMemory === 'function') window.loadMemory(view === 'overview' ? 'list' : view); else window.openModule('memory');
      return;
    }
    const url = new URL(location.href); url.searchParams.set('memoryView', view); history.pushState({ memoryView: view }, '', url); window.openModule(view === 'timeline' ? 'memory-timeline' : 'memory-all');
  }
  async function load(view) {
    state.view = view; state.loading = true; state.error = ''; const epoch = ++state.epoch; render();
    try {
      if (view === 'timeline') {
        const result = await api('/life-graph/timeline?limit=500');
        if (epoch !== state.epoch) return;
        state.timeline = Array.isArray(result?.items) ? result.items : [];
      } else {
        const result = await api('/memory?limit=100&q=' + encodeURIComponent(state.query));
        if (epoch !== state.epoch) return;
        state.memories = Array.isArray(result?.memories) ? result.memories : [];
      }
    } catch (error) { if (epoch !== state.epoch) return; state.error = error?.status === 403 ? 'This device is not authorized to view these records.' : error?.message || 'Vishnu could not load these records.'; }
    state.loading = false; render();
  }
  const previous = window.openModule;
  window.openModule = async function (name) {
    if (name !== 'memory-timeline' && name !== 'memory-all') return previous.call(this, name);
    const result = await previous.call(this, name);
    await load(name === 'memory-timeline' ? 'timeline' : 'all');
    return result;
  };
  window.addEventListener('popstate', () => {
    const selected = new URLSearchParams(location.search).get('memoryView');
    if (selected === 'timeline' || selected === 'all') load(selected);
  });
})();
