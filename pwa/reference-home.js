(function () {
  const one = selector => document.querySelector(selector);
  const all = selector => [...document.querySelectorAll(selector)];
  const bridge = () => window.vishnuChatBridge;

  const referenceSidebarToggle = one('#referenceSidebarToggle');
  const referenceDesktopSidebar = one('#referenceDesktopSidebar');
  const referenceDesktopNav = referenceDesktopSidebar?.querySelector('nav');
  const referenceSidebarQuery = window.matchMedia?.('(min-width: 901px)');
  const referenceSidebarPreferenceKey = 'vishnu.referenceSidebarCollapsed';
  function setReferenceSidebarCollapsed(collapsed, persist = false) {
    const isDesktop = referenceSidebarQuery?.matches ?? window.innerWidth > 900;
    const isCollapsed = Boolean(collapsed && isDesktop);
    document.body.classList.toggle('reference-sidebar-collapsed', isCollapsed);
    const panelOpen = document.body.classList.contains('conversation-drawer-open');
    const navigationVisible = !isCollapsed && !panelOpen;
    if (referenceDesktopSidebar) {
      referenceDesktopSidebar.inert = !navigationVisible;
      referenceDesktopSidebar.setAttribute('aria-hidden', String(!navigationVisible));
    }
    if (referenceSidebarToggle) {
      const label = navigationVisible ? 'Collapse navigation' : 'Open navigation';
      referenceSidebarToggle.setAttribute('aria-expanded', String(navigationVisible));
      referenceSidebarToggle.setAttribute('aria-label', label);
      referenceSidebarToggle.title = label;
    }
    if (persist) {
      try { localStorage.setItem(referenceSidebarPreferenceKey, String(isCollapsed)); }
      catch { /* Navigation remains usable when storage is unavailable. */ }
    }
  }
  let savedSidebarPreference = false;
  try { savedSidebarPreference = localStorage.getItem(referenceSidebarPreferenceKey) === 'true'; }
  catch { /* Use the expanded default when storage is unavailable. */ }
  setReferenceSidebarCollapsed(savedSidebarPreference);
  window.setReferenceSidebarCollapsed = setReferenceSidebarCollapsed;
  window.toggleReferencePrimarySidebar = () => {
    if (document.body.classList.contains('conversation-drawer-open')) {
      window.closeDrawer?.(false);
      setReferenceSidebarCollapsed(false, true);
      return;
    }
    setReferenceSidebarCollapsed(!document.body.classList.contains('reference-sidebar-collapsed'), true);
  };
  referenceSidebarToggle?.addEventListener('click', () => window.toggleReferencePrimarySidebar?.());
  referenceSidebarQuery?.addEventListener?.('change', () => {
    let shouldCollapse = false;
    try { shouldCollapse = localStorage.getItem(referenceSidebarPreferenceKey) === 'true'; }
    catch { /* Keep the default expanded state. */ }
    setReferenceSidebarCollapsed(shouldCollapse);
  });
  new MutationObserver(() => setReferenceSidebarCollapsed(document.body.classList.contains('reference-sidebar-collapsed')))
    .observe(document.body, { attributes: true, attributeFilter: ['class'] });

  function placeForgeLauncherInNavigation() {
    if (!document.body.classList.contains('v-ref') || !referenceSidebarQuery?.matches || !referenceDesktopNav) return;
    const launcher = document.getElementById('vishnuForgeLauncher');
    if (!launcher || launcher.parentElement === referenceDesktopNav) return;
    launcher.classList.add('reference-forge-entry');
    launcher.setAttribute('aria-label', 'Open Capability Forge');
    const icon = document.createElement('span');
    icon.textContent = '✧';
    icon.setAttribute('aria-hidden', 'true');
    const label = document.createElement('span');
    label.textContent = 'Forge';
    launcher.replaceChildren(icon, label);
    referenceDesktopNav.appendChild(launcher);
  }
  placeForgeLauncherInNavigation();
  new MutationObserver(placeForgeLauncherInNavigation).observe(document.body, { childList: true, subtree: true });

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
      const active = button.dataset.appModule === name;
      button.classList.toggle('active', active);
      if (active) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
  }

  all('.reference-desktop-sidebar [data-app-module],.reference-mobile-nav [data-app-module]').forEach(button => {
    button.addEventListener('click', () => {
      syncActive(button.dataset.appModule);
      if (button.dataset.appModule === 'conversations') {
        window.openConversationsDrawer?.();
        return;
      }
      openModule(button.dataset.appModule);
    });
  });

  function syncCurrentSurface() {
    if (document.body.classList.contains('chat-experience')) syncActive('conversations');
    else if (document.body.classList.contains('home-landing')) syncActive('home');
  }
  syncCurrentSurface();
  new MutationObserver(syncCurrentSurface).observe(document.body, {
    attributes: true,
    attributeFilter: ['class']
  });

  all('[data-reference-search]').forEach(button => button.addEventListener('click', () => {
    if (window.matchMedia?.('(min-width: 901px)').matches) {
      openModule('search');
      return;
    }
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
    if (window.matchMedia?.('(min-width: 901px)').matches) window.toggleReferencePrimarySidebar?.();
    else document.getElementById('historyButton')?.click();
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

// Phase 2 Home assets are declared by index.html and the shared Home loader.
