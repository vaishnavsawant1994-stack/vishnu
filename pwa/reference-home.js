(function () {
  const one = selector => document.querySelector(selector);
  const all = selector => [...document.querySelectorAll(selector)];
  const bridge = () => window.vishnuChatBridge;

  const composer = document.getElementById('composer');
  const composerSlot = document.getElementById('referenceComposerSlot');
  const composerAnchor = document.createComment('reference-composer-anchor');
  if (composer?.parentNode) composer.parentNode.insertBefore(composerAnchor, composer);

  function syncComposerLocation() {
    if (!composer || !composerSlot || !composerAnchor.parentNode) return;
    if (document.body.classList.contains('home-landing')) {
      if (composer.parentNode !== composerSlot) composerSlot.appendChild(composer);
    } else if (composer.parentNode === composerSlot) {
      composerAnchor.parentNode.insertBefore(composer, composerAnchor.nextSibling);
    }
  }

  syncComposerLocation();
  new MutationObserver(syncComposerLocation).observe(document.body, {
    attributes: true,
    attributeFilter: ['class']
  });

  function openModule(name) {
    if (bridge()?.openModule) bridge().openModule(name);
  }

  function syncActive(name) {
    all('.reference-desktop-sidebar [data-app-module],.reference-mobile-nav [data-app-module]').forEach(button => {
      button.classList.toggle('active', button.dataset.appModule === name);
    });
  }

  all('.reference-desktop-sidebar [data-app-module],.reference-mobile-nav [data-app-module]').forEach(button => {
    button.addEventListener('click', () => {
      syncActive(button.dataset.appModule);
      openModule(button.dataset.appModule);
    });
  });

  all('[data-reference-search]').forEach(button => button.addEventListener('click', () => {
    document.getElementById('historyButton')?.click();
    requestAnimationFrame(() => {
      document.getElementById('sidebarSearchToggle')?.click();
      document.getElementById('sidebarSearch')?.focus();
    });
  }));

  all('[data-reference-create]').forEach(button => button.addEventListener('click', () => {
    if (bridge()?.setDraft) bridge().setDraft('Create ');
  }));

  all('[data-reference-agents]').forEach(button => button.addEventListener('click', () => {
    window.location.assign('/iphone/agents.html');
  }));

  all('[data-reference-more]').forEach(button => button.addEventListener('click', () => {
    document.getElementById('historyButton')?.click();
  }));

  const quickBindings = [
    ['vProjects', 'Code', 'Build, debug and improve a project', () => openModule('projects')],
    ['vAssign', 'Create', 'Generate content, designs and plans', () => bridge()?.setDraft?.('Create ')],
    ['vToday', 'Research', 'Turn questions into clear insights', () => bridge()?.setDraft?.('Research ')],
    ['vMemory', 'Files', 'Work with your knowledge and files', () => openModule('knowledge')]
  ];
  quickBindings.forEach(([id, title, subtitle, action]) => {
    const button = document.getElementById(id);
    if (!button) return;
    const strong = button.querySelector('strong');
    const small = button.querySelector('small');
    if (strong) strong.textContent = title;
    if (small) small.textContent = subtitle;
    button.addEventListener('click', action);
  });

  const greeting = document.getElementById('homeGreeting');
  const ownerName = document.querySelector('[data-reference-owner]');
  const observer = new MutationObserver(() => {
    const raw = greeting?.textContent || '';
    const match = raw.match(/,\s*([^.!]+)[.!]?$/);
    if (match && ownerName) ownerName.textContent = match[1].trim();
  });
  if (greeting) observer.observe(greeting, { childList: true, characterData: true, subtree: true });
})();

// P2-01 extends the existing Home shell. Do not add a second composer/router.
(() => {
  if (!document.getElementById('p201Styles')) {
    const styles = document.createElement('link');
    styles.id = 'p201Styles';
    styles.rel = 'stylesheet';
    styles.href = '/iphone/p2-home.css';
    document.head.append(styles);
  }
  if (!document.querySelector('script[data-p201-home]')) {
    const script = document.createElement('script');
    script.src = '/iphone/p2-home.js';
    script.dataset.p201Home = 'true';
    script.onerror = () => console.warn('P2-01 Home enhancement unavailable; existing Home remains accessible.');
    document.body.append(script);
  }
})();
