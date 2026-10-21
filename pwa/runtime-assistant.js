/* Vishnu 2.0 · P1-10 conditional runtime connection assistant.
 * This browser cannot install local Python or provision cloud infrastructure.
 * Only canonical same-origin /access/options can confirm local runtime presence.
 * An external address is a user-confirmed navigation, NEVER "connected" status.
 */
(() => {
  'use strict';
  if (new URLSearchParams(location.search).get('campaignDemo') === '1') return;
  const choices = [
    ['existing', 'Connect to Existing Vishnu',
     'Connect this device to your existing Vishnu runtime running on another device or server.'],
    ['local', 'Set Up Vishnu on This Device',
     'Run Vishnu locally on this device. Recommended for personal use when supported.'],
    ['hosted', 'Set Up an Online Runtime',
     'Connect to your own private hosted runtime. Use this if you want to run Vishnu on a server or cloud.'],
  ];
  const iconPaths = {
    link: '<path d="m10 13 4-4m-6 9H6a4 4 0 0 1-3-6l4-4a4 4 0 0 1 6 0m-2-2h2a4 4 0 0 1 3 6l-4 4a4 4 0 0 1-6 0"/>',
    local: '<rect x="3" y="4" width="18" height="14" rx="2"/><path d="M8 21h8m-4-3v3"/>',
    cloud: '<path d="M7 19h11a4 4 0 0 0 .5-8A7 7 0 0 0 5 10a4.5 4.5 0 0 0 2 9Z"/>',
    cog: '<path d="M12 2v3m0 14v3m10-10h-3M5 12H2m16.5-6.5-2 2m-9 9-2 2m13 0-2-2m-9-9-2-2"/><circle cx="12" cy="12" r="4"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c5 6 5 12 0 18M12 3c-5 6-5 12 0 18"/>',
    arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    back: '<path d="M20 12H4m6-6-6 6 6 6"/>',
  };
  const icon = (name, size = 30) => '<svg viewBox="0 0 24 24" width="' + size +
    '" height="' + size + '" stroke="currentColor" stroke-width="1.75" fill="none" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    iconPaths[name] + '</svg>';
  const safeHTML = x => String(x || '').replace(/[&<>"']/g,
    char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const inputAddress = raw => {
    const cleaned = String(raw || '').trim();
    if (cleaned.length > 500 || !cleaned) throw new Error('Enter the HTTPS address of your own Vishnu runtime.');
    let url;
    try { url = new URL(cleaned); } catch { throw new Error('Enter a full URL beginning with https://.'); }
    if (url.username || url.password || url.search || url.hash) {
      throw new Error('Do not include a username, password, pairing token, query or fragment in the address.');
    }
    if (!['/', '/iphone', '/iphone/'].includes(url.pathname)) {
      throw new Error('Enter the runtime origin or its /iphone/ page, not another API endpoint.');
    }
    const loopback = /^(localhost|127\.0\.0\.1|\[::1\])$/i.test(url.hostname);
    const localPage = /^(localhost|127\.0\.0\.1|\[::1\])$/i.test(location.hostname);
    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback && localPage)) {
      throw new Error('Only secure HTTPS runtimes are supported. Local development may use loopback HTTP.');
    }
    return url.origin + '/iphone/';
  };
  let activePanel = null, destroySphere = null, busy = false, origin = 'welcome';
  let selected = 'existing', awaitingConfirmation = false, address = '', reachable = false;
  let backCallback = null, resumeCallback = null;

  async function probe() {
    // A response from the same-origin canonical runtime does not imply trust.
    // Unreachable/offline is deliberately distinct from a 401 owner challenge.
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 4000);
    try {
      const response = await fetch('/iphone/api/access/options', {
        method: 'GET', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Accept': 'application/json' }, signal: controller.signal,
      });
      if (!response.ok) return { reachable: response.status === 401 || response.status === 403, status: response.status };
      const options = await response.json();
      const fields = ['creation_available', 'restore_available', 'password_available', 'recovery_available', 'setup_in_progress', 'restore_setup_in_progress'];
      if (!options || typeof options !== 'object' || !fields.some(key => Object.hasOwn(options, key))) {
        return { reachable: false, status: 'unknown' };
      }
      return { reachable: true, status: 'responding', options };
    } catch {
      return { reachable: false, status: 'offline' };
    } finally { clearTimeout(timeout); }
  }
  function stop() {
    destroySphere?.(); destroySphere = null;
    activePanel = null; busy = false;
  }
  function setStatus(message, type = 'info') {
    const el = activePanel?.querySelector('#rtaStatus');
    if (!el) return;
    el.textContent = message;
    el.dataset.kind = type;
  }
  function setBusy(value) {
    busy = value;
    activePanel?.querySelectorAll('button[data-runtime-continue], button[data-runtime-open], button[data-runtime-check]')
      .forEach(button => { button.disabled = value; });
  }
  function selection(key) {
    if (busy || !choices.some(item => item[0] === key)) return;
    selected = key; awaitingConfirmation = false;
    const host = activePanel;
    if (!host) return;
    for (const button of host.querySelectorAll('[data-runtime-choice]')) {
      const yes = button.dataset.runtimeChoice === selected;
      button.setAttribute('aria-checked', String(yes));
      button.classList.toggle('selected', yes);
    }
    host.querySelector('#rtaFlow').replaceChildren();
    setStatus('');
  }
  function addInformation(id, title, message, helpHref, helpLabel) {
    const flow = activePanel.querySelector('#rtaFlow');
    flow.replaceChildren();
    const section = document.createElement('section');
    section.className = 'rta-flow'; section.dataset.runtimeFlow = id;
    const heading = document.createElement('h3');
    heading.textContent = title;
    const p = document.createElement('p');
    p.textContent = message;
    section.append(heading, p);
    if (helpHref) {
      const link = document.createElement('a');
      link.href = helpHref; link.target = '_blank'; link.rel = 'noopener noreferrer';
      link.textContent = helpLabel;
      section.append(link);
    }
    flow.append(section);
    return section;
  }
  function renderExisting() {
    const section = addInformation('existing', 'Existing Vishnu runtime',
      'Enter the address you control. Your browser will open that runtime in a new origin-specific session. Owner sign-in and device approval happen there; no credentials are transferred from this page.');
    const label = document.createElement('label');
    label.htmlFor = 'rtaAddress'; label.textContent = 'Secure runtime address';
    const field = document.createElement('input');
    field.id = 'rtaAddress'; field.type = 'url'; field.autocomplete = 'url';
    field.placeholder = 'https://your-vishnu.example'; field.value = address;
    field.addEventListener('input', () => {
      address = field.value; awaitingConfirmation = false;
      const action = activePanel.querySelector('[data-runtime-open]');
      if (action) action.textContent = 'Validate address and review navigation';
      setStatus('');
    });
    section.append(label, field);
    const notice = document.createElement('p'); notice.className = 'rta-hint';
    notice.textContent = 'QR scanning and automatic LAN discovery are not implemented in the web app. You can use an approved HTTPS address instead.';
    section.append(notice);
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'rta-inline-action'; button.dataset.runtimeOpen = '';
    button.textContent = 'Validate address and review navigation';
    button.onclick = () => {
      try {
        const target = inputAddress(field.value);
        if (!awaitingConfirmation) {
          awaitingConfirmation = true;
          setStatus('Address accepted: ' + target + ' — This has NOT verified the runtime or device. Select the button again to open the address and authenticate on that runtime.', 'info');
          button.textContent = 'Open runtime securely →';
          return;
        }
        setBusy(true);
        // A top-level navigation never forwards this page's HttpOnly cookies
        // or recovery secrets to another origin. The destination must verify
        // server identity via HTTPS and re-authenticate its own owner.
        location.assign(target);
      } catch (e) {
        awaitingConfirmation = false;
        button.textContent = 'Validate address and review navigation';
        setBusy(false); setStatus(e.message, 'error');
      }
    };
    section.append(button);
    field.focus();
  }
  function renderLocal() {
    const isLoopback = /^(localhost|127\.0\.0\.1|\[::1\])$/i.test(location.hostname);
    const section = addInformation('local', 'Set up Vishnu on this device',
      isLoopback
        ? 'This browser is on a local development address. Check the running Vishnu service. If it is unavailable, use the supported installer or startup script first.'
        : 'A web page or phone browser cannot install the Vishnu Python runtime. Use the supported desktop launcher on a compatible computer, then connect this browser to it using a secure runtime address.',
      'https://github.com/vaishnavsawant1994-stack/vishnu/blob/main/docs/LOCAL_DEVELOPMENT_WEB_AND_WINDOWS.md',
      'Open the verified local setup instructions ↗');
    const button = document.createElement('button');
    button.type = 'button'; button.dataset.runtimeCheck = '';
    button.className = 'rta-inline-action';
    button.textContent = 'Check running Vishnu';
    button.onclick = async () => {
      if (busy) return;
      setBusy(true); setStatus('Checking the current Vishnu runtime…');
      const state = await probe();
      setBusy(false);
      if (state.reachable) {
        setStatus('Vishnu is responding on this origin. Continue with existing owner sign-in or first-run setup.', 'success');
        if (typeof resumeCallback === 'function') await resumeCallback();
      } else {
        setStatus('No working Vishnu runtime was verified on this origin. Start Vishnu using the supported launcher, or choose an existing/hosted runtime.', 'error');
      }
    };
    section.append(button);
  }
  function renderHosted() {
    const section = addInformation('hosted', 'Set up an online runtime',
      'Vishnu has a deployment template for a private hosted runtime. Deployment happens in your hosting account, subject to your consent, service availability, regional privacy choices, and provider billing. This app cannot provision or pay for a server automatically.',
      'https://github.com/vaishnavsawant1994-stack/vishnu/blob/main/render.yaml',
      'Review the existing hosting configuration ↗');
    const fieldLabel = document.createElement('label');
    fieldLabel.className = 'rta-consent';
    const consent = document.createElement('input');
    consent.type = 'checkbox'; consent.id = 'rtaHostedConsent';
    const span = document.createElement('span');
    span.textContent = 'I understand that hosted setup occurs in my own provider account and may incur costs. No personal data will be uploaded by this screen.';
    fieldLabel.append(consent, span);
    section.append(fieldLabel);
    const link = document.createElement('a');
    link.href = 'https://dashboard.render.com/';
    link.target = '_blank'; link.rel = 'noopener noreferrer';
    link.className = 'rta-provider-link';
    link.textContent = 'Open hosting dashboard ↗';
    link.onclick = event => {
      if (!consent.checked) {
        event.preventDefault(); setStatus('Review and accept the hosting and billing notice first.', 'error');
      } else {
        setStatus('The hosting dashboard opened. Complete any deployment there, then return and choose Connect to Existing Vishnu using the verified HTTPS address.', 'info');
      }
    };
    section.append(link);
  }

  function mount(panel, config = {}) {
    if (!panel) return;
    stop();
    activePanel = panel;
    origin = config.origin || 'welcome';
    backCallback = config.onBack || null;
    resumeCallback = config.onReady || null;
    reachable = false; selected = config.selected || selected;
    panel.setAttribute('aria-label', 'P1-10 Runtime Connection Assistant');
    panel.className = 'genesis runtime-host';
    panel.innerHTML = '<main class="runtime-assistant" aria-labelledby="rtaTitle">' +
      '<header class="rta-header"><div class="rta-brand">' +
      '<span class="rta-brand-mark" aria-hidden="true"><i></i></span><span><strong>Vishnu 2.0</strong><small>Your Personal AI Companion</small></span></div>' +
      '<div class="rta-right"><span class="rta-locale" aria-label="Interface language: English">' + icon('globe', 24) +
      'English</span><span class="rta-screen">P1-10</span></div></header>' +
      '<div class="rta-layout"><section class="rta-art"><canvas class="rta-canvas" id="rtaCanvas" role="img" ' +
      'aria-label="Glowing animated cyan 3D network sphere. Drag to rotate."></canvas>' +
      '<div class="rta-platform" aria-hidden="true"><i></i><i></i><i></i><i></i></div></section>' +
      '<section class="rta-panel"><p class="rta-eyebrow">CONDITIONAL SETUP</p>' +
      '<h1 id="rtaTitle">Runtime Connection <em>Assistant</em></h1>' +
      '<p class="rta-intro">Vishnu needs a runtime to work. Choose how you want to connect or set it up.</p>' +
      '<div role="radiogroup" aria-label="How Vishnu should connect" class="rta-choices">' +
      choices.map(([key,title,copy],index) => '<button type="button" role="radio" aria-checked="' +
        (key === selected ? 'true' : 'false') + '" class="rta-choice ' + (key === selected ? 'selected' : '') +
        '" data-runtime-choice="' + key + '"><span class="rta-icon">' + icon(['link','local','cloud'][index], 49) +
        '</span><span class="rta-choice-copy"><strong>' + title + '</strong><small>' + copy +
        '</small></span><span class="rta-chevron" aria-hidden="true">' + icon('arrow', 28) +
        '</span></button>').join('') +
      '</div><section class="rta-explainer"><span class="rta-explainer-icon">' + icon('cog', 42) +
      '</span><div><h2>What is a Runtime?</h2><p>The runtime is where Vishnu runs, processes information and securely connects to your devices and data. You can always change this later in Settings.</p></div></section>' +
      '<div id="rtaFlow" aria-live="polite"></div><p id="rtaStatus" role="status" aria-live="polite"></p></section></div>' +
      '<nav class="rta-footer" aria-label="Runtime navigation"><button type="button" class="rta-back" data-runtime-back>' +
      icon('back', 22) + ' Back</button><button type="button" class="rta-continue" data-runtime-continue>' +
      'Continue ' + icon('arrow', 25) + '</button></nav></main>';
    panel.querySelectorAll('[data-runtime-choice]').forEach(button => {
      button.addEventListener('click', () => selection(button.dataset.runtimeChoice));
      button.addEventListener('keydown', e => {
        if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) return;
        e.preventDefault();
        const i = choices.findIndex(x => x[0] === button.dataset.runtimeChoice);
        const direction = /Right|Down/.test(e.key) ? 1 : -1;
        const next = choices[(i + direction + choices.length) % choices.length][0];
        selection(next);
        panel.querySelector('[data-runtime-choice="' + next + '"]').focus();
      });
    });
    panel.querySelector('[data-runtime-continue]').addEventListener('click', () => {
      if (busy) return;
      if (selected === 'existing') renderExisting();
      else if (selected === 'local') renderLocal();
      else renderHosted();
    });
    panel.querySelector('[data-runtime-back]').addEventListener('click', () => {
      if (busy) return;
      if (panel.querySelector('#rtaFlow')?.children.length) {
        panel.querySelector('#rtaFlow').replaceChildren();
        awaitingConfirmation = false; setStatus('');
        return;
      }
      stop();
      if (typeof backCallback === 'function') backCallback(origin);
    });
    destroySphere = window.vishnuNeuralSphere?.attach(panel.querySelector('#rtaCanvas')) || (() => {});
    return { choose: selection, stop };
  }
  window.vishnuRuntimeAssistant = { mount, probe, stop, validateAddress: inputAddress };
})();
