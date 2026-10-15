/* Owner-controlled Markdown notes layered on the canonical Knowledge library. */
(() => {
  const escape = value => window.escapeHtml(String(value ?? ''));
  const isNote = item => item?.metadata?.knowledge_kind === 'note';

  function markdownPreview(source) {
    let value = escape(source);
    value = value.replace(/^```([^\n]*)\n([\s\S]*?)^```\s*$/gm, '<pre><code>$2</code></pre>');
    value = value.replace(/^### (.+)$/gm, '<h3>$1</h3>').replace(/^## (.+)$/gm, '<h2>$1</h2>').replace(/^# (.+)$/gm, '<h1>$1</h1>');
    value = value.replace(/`([^`\n]+)`/g, '<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>').replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
    value = value.replace(/\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]/g, (_match, target, label) => `<span class="kn-wikilink">${label || target}</span>`);
    return value.split(/\n{2,}/).map(block => block.startsWith('<h') || block.startsWith('<pre') ? block : `<p>${block.replace(/\n/g, '<br>')}</p>`).join('');
  }

  async function downloadArchive() {
    if (window.sectionPreviewMode?.() || document.querySelector('.rp-page[data-rp-page="knowledge"] .rp-demo-notice')) return window.showToast('Preview only — no data is exported.');
    const response = await fetch('/iphone/api/knowledge/portable-export', { credentials: 'same-origin' });
    if (!response.ok) {
      let detail = 'The Knowledge archive could not be exported.';
      try { detail = (await response.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    const blob = await response.blob(), url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = 'vishnu-knowledge.zip'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    window.showToast('Portable Knowledge archive downloaded.');
  }

  async function noteLinks(noteId) {
    try { return await window.api(`/knowledge/notes/${encodeURIComponent(noteId)}/links`); }
    catch { return { outgoing: [], backlinks: [], unresolved: [] }; }
  }

  async function openEditor(note = null) {
    if (window.sectionPreviewMode?.() || document.querySelector('.rp-page[data-rp-page="knowledge"] .rp-demo-notice')) return window.showToast('Preview only — notes are not saved.');
    const dialog = document.createElement('dialog');
    dialog.className = 'knowledge-note-dialog';
    dialog.setAttribute('aria-labelledby', 'knowledgeNoteTitle');
    const noteId = note?.id || '';
    let baseline = JSON.stringify([note?.title || '', note?.content || '', (note?.metadata?.tags || []).join(', ')]);
    dialog.innerHTML = `<form method="dialog" class="kn-shell"><header class="kn-header"><div><span class="kn-eyebrow">Knowledge · Markdown</span><h2 id="knowledgeNoteTitle">${note ? 'Edit note' : 'New note'}</h2></div><button class="kn-close" type="submit" value="close" aria-label="Close note editor">×</button></header><label class="kn-field">Title<input id="kn-title" maxlength="240" required value="${escape(note?.title || '')}" autocomplete="off"></label><label class="kn-field">Tags<input id="kn-tags" maxlength="1000" value="${escape((note?.metadata?.tags || []).join(', '))}" placeholder="Ideas, Vishnu, research"></label><div class="kn-editor-tabs" role="tablist" aria-label="Note editor view"><button type="button" class="active" data-kn-tab="edit" role="tab" aria-selected="true">Edit</button><button type="button" data-kn-tab="preview" role="tab" aria-selected="false">Preview</button></div><label class="kn-field kn-content-label">Markdown<textarea id="kn-content" maxlength="10000000" spellcheck="true" placeholder="# Start writing…">${escape(note?.content || '')}</textarea></label><div id="kn-preview" class="kn-preview hidden" aria-live="polite"></div><div id="kn-links" class="kn-links" aria-live="polite"></div><footer class="kn-footer"><span id="kn-status">${note ? `Version ${escape(note.version || 1)} · Changes are saved as a new version` : 'Notes stay in your Knowledge library'}</span><div><button type="button" class="kn-cancel">Cancel</button><button type="button" class="kn-save">${note ? 'Save changes' : 'Create note'}</button></div></footer></form>`;
    document.body.append(dialog);
    const title = dialog.querySelector('#kn-title'), tags = dialog.querySelector('#kn-tags'), content = dialog.querySelector('#kn-content');
    const values = () => JSON.stringify([title.value, content.value, tags.value]);
    const dirty = () => values() !== baseline;
    const linksBox = dialog.querySelector('#kn-links');
    if (note) {
      noteLinks(noteId).then(links => {
        const row = (label, values, targetKey = 'id') => values.length ? `<section><strong>${label}</strong><div>${values.map(item => `<button type="button" class="kn-link" data-kn-open="${escape(item[targetKey])}">${escape(item.title || item.target || item.label)}</button>`).join('')}</div></section>` : '';
        linksBox.innerHTML = row('Links to', links.outgoing || []) + row('Linked from', links.backlinks || []) + ((links.unresolved || []).length ? `<section><strong>Unresolved links</strong><span>${links.unresolved.map(item => escape(item.target)).join(' · ')}</span></section>` : '');
        linksBox.querySelectorAll('[data-kn-open]').forEach(button => button.onclick = async () => {
          try { const target = await window.api(`/knowledge/${encodeURIComponent(button.dataset.knOpen)}`); dialog.close(); dialog.remove(); window.openKnowledgeDetail(target.id); }
          catch (error) { window.showToast(error.message); }
        });
      });
    }
    dialog.querySelectorAll('[data-kn-tab]').forEach(button => button.onclick = () => {
      const preview = button.dataset.knTab === 'preview';
      dialog.querySelectorAll('[data-kn-tab]').forEach(tab => { const active = tab === button; tab.classList.toggle('active', active); tab.setAttribute('aria-selected', String(active)); });
      dialog.querySelector('.kn-content-label').classList.toggle('hidden', preview);
      dialog.querySelector('#kn-preview').classList.toggle('hidden', !preview);
      if (preview) dialog.querySelector('#kn-preview').innerHTML = markdownPreview(content.value);
    });
    const close = async () => {
      if (dirty() && !await window.requestConfirmation('Discard your unsaved Markdown changes?')) return;
      dialog.close(); dialog.remove();
    };
    dialog.querySelector('.kn-cancel').onclick = close;
    dialog.querySelector('.kn-close').onclick = event => { event.preventDefault(); close(); };
    dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
    dialog.addEventListener('click', event => { if (event.target === dialog) close(); });
    dialog.querySelector('.kn-save').onclick = async event => {
      const save = event.currentTarget, cleanTitle = title.value.trim();
      if (!cleanTitle) { title.focus(); return; }
      save.disabled = true; dialog.querySelector('#kn-status').textContent = 'Saving securely…';
      const cleanTags = tags.value.split(',').map(value => value.trim()).filter(Boolean).slice(0, 30);
      try {
        const payload = { title: cleanTitle, content: content.value, tags: cleanTags };
        const saved = note ? await window.api(`/knowledge/notes/${encodeURIComponent(noteId)}`, { method: 'PUT', body: JSON.stringify(payload) })
                           : await window.api('/knowledge/notes', { method: 'POST', body: JSON.stringify(payload) });
        baseline = values(); dialog.close(); dialog.remove();
        if (document.querySelector('.rp-page[data-rp-page="knowledge"]')) await window.openModule('knowledge');
        else await window.loadKnowledge(window.knowledgePageQuery || '');
        window.showToast(note ? 'Note saved as a new version.' : 'Markdown note created.');
        if (!note && saved?.id) await window.openKnowledgeDetail(saved.id);
      } catch (error) { dialog.querySelector('#kn-status').textContent = error.message || 'The note could not be saved.'; save.disabled = false; }
    };
    dialog.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); dialog.querySelector('.kn-save').click(); } });
    dialog.showModal(); title.focus();
  }

  function enhanceKnowledgePage() {
    const page = document.querySelector('#moduleBody .rp-page[data-rp-page="knowledge"]') || document.querySelector('#moduleBody .section-page');
    const referencePage = page?.matches('.rp-page[data-rp-page="knowledge"]');
    const grid = referencePage ? Array.from(page.querySelectorAll('.rp-section-head')).find(head => head.querySelector('.rp-section-title')?.textContent.trim() === 'Knowledge items') : page?.querySelector('.section-shortcut-grid');
    if (!grid || grid.querySelector('#knowledgeNoteCreate')) return;
    const create = document.createElement('button'); create.type = 'button'; create.id = 'knowledgeNoteCreate'; create.className = 'section-action-card'; create.innerHTML = '<span class="section-action-icon">✎</span><span><strong>New note</strong><small>Write a Markdown note</small></span><span aria-hidden="true">›</span>';
    const importButton = document.createElement('button'); importButton.type = 'button'; importButton.id = 'knowledgePortableImport'; importButton.className = 'section-action-card'; importButton.innerHTML = '<span class="section-action-icon">⇧</span><span><strong>Import notes</strong><small>Markdown or Vishnu archive</small></span><span aria-hidden="true">›</span>';
    const portable = document.createElement('button'); portable.type = 'button'; portable.id = 'knowledgePortableExport'; portable.className = 'section-action-card'; portable.innerHTML = '<span class="section-action-icon">⇩</span><span><strong>Markdown archive</strong><small>Export notes and files</small></span><span aria-hidden="true">›</span>';
    let input = page.querySelector('#knowledgeFile');
    if (referencePage) {
      create.className = importButton.className = portable.className = 'rp-button';
      create.textContent = '＋ New note'; importButton.textContent = '⇧ Import'; portable.textContent = '⇩ Export archive';
      create.setAttribute('aria-label', 'Create Markdown note'); importButton.setAttribute('aria-label', 'Import Markdown notes or Knowledge archive'); portable.setAttribute('aria-label', 'Export Knowledge archive');
      const actions = document.createElement('div'); actions.className = 'kn-page-actions';
      actions.append(create, importButton, portable); grid.append(actions);
      if (!input) { input = document.createElement('input'); input.id = 'knowledgeFile'; input.type = 'file'; input.multiple = true; input.hidden = true; page.append(input); }
    } else { grid.prepend(create); grid.append(importButton, portable); }
    create.onclick = () => openEditor();
    if (input) {
      input.multiple = true; input.accept = '.md,.markdown,.txt,.csv,.json,.pdf,.docx,.xlsx,.png,.jpg,.jpeg,.webp,.tif,.tiff,.zip';
      input.onchange = async event => {
        const files = Array.from(event.target.files || []);
        if (!files.length) return;
        if (window.sectionPreviewMode?.() || document.querySelector('.rp-page[data-rp-page="knowledge"] .rp-demo-notice')) { window.showToast('Preview only — imports are not saved.'); event.target.value = ''; return; }
        try {
          for (const file of files) {
            if (/\.zip$/i.test(file.name)) {
              const response = await fetch('/iphone/api/knowledge/portable-import', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/zip' }, body: file });
              if (!response.ok) { let detail = 'The Knowledge archive could not be imported.'; try { detail = (await response.json()).detail || detail; } catch {} throw new Error(detail); }
              const result = await response.json(); window.showToast(`${result.imported_count} Knowledge items imported.`);
            } else await window.uploadKnowledge(file);
          }
          if (document.querySelector('.rp-page[data-rp-page="knowledge"]')) await window.openModule('knowledge');
          else await window.loadKnowledge(typeof knowledgePageQuery === 'undefined' ? '' : knowledgePageQuery);
        } catch (error) { window.showToast(error.message || 'Import failed.'); }
        finally { event.target.value = ''; }
      };
    }
    importButton.onclick = () => window.sectionPreviewMode?.() || document.querySelector('.rp-page[data-rp-page="knowledge"] .rp-demo-notice') ? window.showToast('Preview only — imports are not saved.') : input?.click();
    portable.onclick = () => downloadArchive().catch(error => window.showToast(error.message));
  }

  const previousOpen = window.openKnowledgeDetail;
  window.openKnowledgeDetail = async id => {
    if (window.sectionPreviewMode?.()) return previousOpen(id);
    try {
      const item = await window.api(`/knowledge/${encodeURIComponent(id)}`);
      if (isNote(item)) return openEditor(item);
      return window.renderKnowledgeDetail(item);
    } catch (error) { window.showToast(error.message || 'Unable to open Knowledge item.'); }
  };

  const previousUpload = window.uploadKnowledge;
  window.uploadKnowledge = file => {
    if (!file) return Promise.resolve(null);
    if (/\.(md|markdown)$/i.test(file.name)) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = async () => {
          try {
            const content = String(reader.result || '').replace(/^\uFEFF/, '');
            const title = file.name.replace(/\.(md|markdown)$/i, '').replace(/[-_]+/g, ' ');
            const note = await window.api('/knowledge/notes', { method: 'POST', body: JSON.stringify({ title, content }) });
            if (document.querySelector('.rp-page[data-rp-page="knowledge"]')) await window.openModule('knowledge');
            else if (typeof activeModule !== 'undefined' && activeModule === 'knowledge') await loadKnowledge(knowledgePageQuery || '');
            resolve(note);
          } catch (error) { reject(error); }
        };
        reader.onerror = () => reject(new Error('The selected Markdown file could not be read.'));
        reader.readAsText(file);
      });
    }
    return previousUpload(file);
  };

  const observer = new MutationObserver(enhanceKnowledgePage);
  observer.observe(document.getElementById('moduleBody') || document.body, { childList: true, subtree: true });
  enhanceKnowledgePage();
  window.openKnowledgeNoteEditor = openEditor;
})();
