/* Safe command/navigation palette. It only dispatches existing canonical UI actions. */
(() => {
  // Both the OS shell and lazy UI loader may request this module.
  // Never bind a second global hotkey listener or open two modal palettes.
  if (typeof window.vishnuOpenCommandCenter === 'function') return;
  const entries = [
    { label: 'Home', detail: 'Return to your Vishnu home', category: 'Navigation', module: 'home', keywords: 'start overview' },
    { label: 'Workspaces', detail: 'Open the current workspace directory', category: 'Navigation', module: 'labs', keywords: 'spaces workspace library' },
    { label: 'Projects', detail: 'Open project workspaces', category: 'Navigation', module: 'projects', keywords: 'project work' },
    { label: 'Agents', detail: 'Inspect available agents', category: 'Navigation', event: 'data-reference-agents', keywords: 'agent' },
    { label: 'Knowledge', detail: 'Open your knowledge library', category: 'Navigation', module: 'knowledge', keywords: 'documents files memory' },
    { label: 'Apps & Tools', detail: 'Manage connected capabilities', category: 'Navigation', module: 'tools', keywords: 'apps capabilities integrations' },
    { label: 'Devices', detail: 'Review trusted devices', category: 'Navigation', module: 'devices', keywords: 'device security' },
    { label: 'Activity', detail: 'Review recent activity', category: 'Navigation', module: 'activities', keywords: 'notifications attention' },
    { label: 'Mission Control', detail: 'Open system status', category: 'Navigation', module: 'dashboard', keywords: 'system' },
    { label: 'Settings', detail: 'Open Vishnu settings', category: 'Navigation', module: 'settings', keywords: 'preferences' },
    { label: 'New conversation', detail: 'Start a conversation with Vishnu', category: 'Actions', action: 'conversation', keywords: 'chat ask' },
    { label: 'Global Search', detail: 'Find conversations and projects', category: 'Actions', action: 'search', keywords: 'find search' },
  ];
  const historyKey = 'vishnu.command.recent.v1';
  const safeHistory = () => {
    try { const value = JSON.parse(localStorage.getItem(historyKey) || '[]'); return Array.isArray(value) ? value.filter(label => entries.some(item => item.label === label)).slice(0, 5) : []; }
    catch { return []; }
  };
  let dialog, query = '', category = 'All', focusOrigin = null;
  const esc = value => String(value).replace(/[&<>"']/g, char => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[char]);
  const matching = () => {
    const needle = query.trim().toLocaleLowerCase();
    return entries.filter(item => (category === 'All' || item.category === category) && (!needle || `${item.label} ${item.detail} ${item.keywords}`.toLocaleLowerCase().includes(needle)));
  };
  function render() {
    if (!dialog?.isConnected) return;
    const recent = safeHistory().map(label => entries.find(item => item.label === label)).filter(Boolean);
    const rows = matching();
    dialog.innerHTML = `<section class="cc-panel" role="document"><header class="cc-heading"><span class="cc-mark" aria-hidden="true">⌘</span><div><h1>Command Center</h1><p>What do you want Vishnu to do?</p></div><kbd>Ctrl ⇧ P</kbd><button type="button" class="cc-close" aria-label="Close Command Center">×</button></header><label class="cc-input-wrap"><span aria-hidden="true">›_</span><input type="search" data-cc-query value="${esc(query)}" placeholder="Type a command, action or question…" aria-label="Type a command, action or question" autocomplete="off"></label><div class="cc-filters" role="group" aria-label="Command category">${['All','Actions','Navigation'].map(item => `<button type="button" class="cc-filter ${category===item?'selected':''}" data-cc-category="${item}" aria-pressed="${category===item}">${item}</button>`).join('')}</div>${recent.length?`<div class="cc-section-head"><h2>Recent commands</h2><button type="button" class="cc-link" data-cc-clear>Clear all</button></div><div class="cc-list" aria-label="Recent commands">${recent.map((item,index)=>row(item,index)).join('')}</div>`:''}<div class="cc-section-head"><h2>${query?'Results':'Navigation'}</h2><span class="cc-count">${rows.length}</span></div><div class="cc-list" role="listbox" aria-label="Available commands">${rows.length?rows.map((item,index)=>row(item,index)).join(''):'<p class="cc-empty">No matching command. Try a navigation destination or action.</p>'}</div><p class="cc-footnote">Commands use existing Vishnu screens. Unavailable Workspace creation and external actions are not simulated here.</p></section>`;
    const input = dialog.querySelector('[data-cc-query]'); input.addEventListener('input', () => { query=input.value; const caret=input.selectionStart;render();const next=dialog.querySelector('[data-cc-query]');next.focus();next.setSelectionRange(caret,caret); });
    dialog.querySelector('.cc-close').onclick=close;
    dialog.querySelectorAll('[data-cc-category]').forEach(button=>button.onclick=()=>{category=button.dataset.ccCategory;render();dialog.querySelector('[data-cc-query]').focus()});
    dialog.querySelector('[data-cc-clear]')?.addEventListener('click',()=>{localStorage.removeItem(historyKey);render();dialog.querySelector('[data-cc-query]').focus()});
    dialog.querySelectorAll('[data-cc-run]').forEach(button=>button.onclick=()=>run(entries.find(item=>item.label===button.dataset.ccRun)));
    input.focus();
  }
  function row(item,index){return `<button type="button" class="cc-row" role="option" aria-selected="${index===0}" data-cc-run="${esc(item.label)}"><span class="cc-row-icon" aria-hidden="true">${item.category==='Actions'?'✦':'⌁'}</span><span class="cc-row-copy"><strong>${esc(item.label)}</strong><small>${esc(item.detail)}</small></span><span class="cc-row-category">${esc(item.category)}</span><kbd>↵</kbd></button>`;}
  async function run(item){
    if(!item)return;
    const history=[item.label,...safeHistory().filter(label=>label!==item.label)].slice(0,5);
    try{localStorage.setItem(historyKey,JSON.stringify(history));}catch{}
    close();
    if(item.module){await window.openModule(item.module);return;}
    if(item.action==='search'){await window.openModule('search');return;}
    if(item.action==='conversation'){
      if(window.personalAiDemoMode){window.showToast?.('Preview only — no conversation is created.');return;}
      try{await window.vishnuChatBridge.createConversation();}catch(error){window.showToast?.(error?.message||'Could not start a conversation.');}
      return;
    }
    if(item.event){document.querySelector(`[${item.event}]`)?.click();return;}
  }
  function close(){if(!dialog)return;dialog.close();dialog.remove();dialog=null;document.body.classList.remove('cc-open');focusOrigin?.focus?.();focusOrigin=null;}
  function open(){if(dialog?.isConnected){dialog.querySelector('[data-cc-query]').focus();return;}focusOrigin=document.activeElement;query='';category='All';dialog=document.createElement('dialog');dialog.className='cc-dialog';dialog.setAttribute('aria-label','Command Center');dialog.addEventListener('cancel',event=>{event.preventDefault();close()});dialog.addEventListener('click',event=>{if(event.target===dialog)close()});document.body.append(dialog);document.body.classList.add('cc-open');render();dialog.showModal();dialog.querySelector('[data-cc-query]').focus();}
  window.vishnuOpenCommandCenter=open;
  window.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.shiftKey&&event.key.toLowerCase()==='p'){event.preventDefault();open();}if(!dialog)return;if(event.key==='Escape'){event.preventDefault();close();return;}if(event.key==='ArrowDown'||event.key==='ArrowUp'){const rows=[...dialog.querySelectorAll('[data-cc-run]')];if(!rows.length)return;event.preventDefault();const active=rows.indexOf(document.activeElement),step=event.key==='ArrowDown'?1:-1;rows[(active+step+rows.length)%rows.length].focus();}if(event.key==='Enter'&&document.activeElement.matches('[data-cc-query]')){const first=dialog.querySelector('[data-cc-run]');if(first){event.preventDefault();first.click();}}});
  document.addEventListener('click',event=>{if(event.target.closest('[data-command-center-entry]')){event.preventDefault();open();}});
})();
