/* Vishnu Genesis: canonical responsive onboarding for desktop and mobile. */
(() => {
  if (new URLSearchParams(location.search).get('campaignDemo') === '1') return;
  const $ = id => document.getElementById(id);
  const originalLoad = window.loadAccessOptions;
  const originalCheck = window.check;
  if (typeof originalLoad !== 'function' || typeof originalCheck !== 'function') return;

  const accessIntent = sessionStorage.getItem('vishnuAccessIntent');
  if (accessIntent) {
    sessionStorage.removeItem('vishnuAccessIntent');
  }

  const requestedStep = new URLSearchParams(location.search).get('genesisStep');
  const localPreviewStep = /^(localhost|127\.0\.0\.1)$/.test(location.hostname) && /^(?:[1-9]|10)$/.test(requestedStep || '')
    ? Number(requestedStep) : 1;
  const s = {
    step: localPreviewStep, options: {}, identityCreated: false, recoverySaved: false,
    policySaved: false, modelSaved: false, passkeyCreated: false,
    auth: 'passkey', dataPolicy: 'progress_only', intelligence: 'skip', privacy: 'local_preferred',
    accessIntent: accessIntent || '', authView: 'welcome', pendingPostAuthAction: '',
  };
  const panel = $('enrollPanel');
  panel.className = 'genesis hidden';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-modal', 'true');
  panel.setAttribute('aria-label', 'Vishnu Genesis onboarding');
  const backgroundNavigation = [...document.querySelectorAll('.reference-desktop-sidebar,.reference-desktop-tools,.reference-mobile-nav,#drawerOverlay,#appDrawer,#conversationDrawer')];
  let priorNavigationState = [];

  const paths = {
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    key: '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9m-3 3 3 3m-6 0 3 3"/>',
    shield: '<path d="M12 2 4 5v6c0 5 3.4 9.7 8 11 4.6-1.3 8-6 8-11V5z"/><path d="m9 12 2 2 4-5"/>',
    device: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>',
    data: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    cloud: '<path d="M7 18h11a4 4 0 0 0 .5-8A7 7 0 0 0 5 9a4.5 4.5 0 0 0 2 9Z"/><path d="m9 14 3 3 3-3m-3 3V9"/>',
    brain: '<path d="M9.5 4A3.5 3.5 0 0 0 6 7.5c0 .4.1.8.2 1.2A3.5 3.5 0 0 0 7 15.5 3.5 3.5 0 0 0 12 19V5.5A3.5 3.5 0 0 0 9.5 4ZM14.5 4A3.5 3.5 0 0 1 18 7.5c0 .4-.1.8-.2 1.2a3.5 3.5 0 0 1-.8 6.8 3.5 3.5 0 0 1-5 3.5V5.5A3.5 3.5 0 0 1 14.5 4Z"/>',
    sparkle: '<path d="m12 3 1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2ZM5 14l.8 2.2L8 17l-2.2.8L5 20l-.8-2.2L2 17l2.2-.8ZM19 13l.7 1.8 1.8.7-1.8.7L19 18l-.7-1.8-1.8-.7 1.8-.7Z"/>',
    folder: '<path d="M3 6h7l2 2h9v11H3z"/>',
    check: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  };
  const icon = name => `<span class="genesis-card-icon" aria-hidden="true"><svg width="27" height="27" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${paths[name] || paths.check}</svg></span>`;
  const dots = n => `<div class="genesis-dots" aria-hidden="true">${Array.from({ length: 10 }, (_, i) => `<i class="${i < n ? 'on' : ''}"></i>`).join('')}</div>`;
  const coreState = n => n >= 10 ? 'ready' : n >= 9 ? 'privacy' : n >= 3 ? 'security' : 'identity';
  const badge = text => text ? `<span class="genesis-badge">${text}</span>` : '';
  const field = (id, placeholder, type = 'text', autocomplete = 'off', cls = '') => `<input class="${cls}" id="${id}" type="${type}" autocomplete="${autocomplete}" placeholder="${placeholder}">`;
  const heading = (title, copy) => `<div class="genesis-copy"><h1>${title}</h1><p>${copy}</p></div>`;
  const actions = (primary = 'Continue &rarr;', secondary = true) => `<div class="genesis-actions"><button class="genesis-primary" data-genesis-next type="button">${primary}</button>${secondary ? '<button class="genesis-tertiary" data-genesis-back type="button">&larr; Back</button>' : ''}<p id="genesisStatus" class="genesis-error" role="status" aria-live="polite"></p></div>`;
  const footer = '<footer class="genesis-footer"><a href="#" data-genesis-info="privacy">Privacy</a><span>|</span><a href="#" data-genesis-info="accessibility">Accessibility</a></footer>';
  const features = items => `<div class="genesis-features">${items.map(([title, copy]) => `<div class="genesis-feature"><strong>&#10003; ${title}</strong>${copy}</div>`).join('')}</div>`;
  const card = ({ value, title, copy, badgeText = '', name = 'choice', selected = false, iconName = 'check', details = '' }) => `<label class="genesis-card ${selected ? 'selected' : ''}"><input type="radio" name="${name}" value="${value}" ${selected ? 'checked' : ''}><div class="genesis-card-head">${icon(iconName)}<div><h3>${title}${badge(badgeText)}</h3><p>${copy}</p></div></div>${details}</label>`;

  function content(n) {
    if (n === 1) return `${heading('Welcome to Vishnu', 'Your personal intelligence. Your data. Your world.')}<div class="genesis-actions"><button class="genesis-primary" data-genesis-create>Create my Vishnu &rarr;</button><div class="genesis-secondary-row"><button class="genesis-tertiary" data-genesis-join>I already have Vishnu</button><span>|</span><button class="genesis-tertiary" data-genesis-restore>Restore Vishnu</button></div><p id="genesisStatus" class="genesis-error" role="status" aria-live="polite"></p></div>`;

    if (n === 2) return `${heading('Create your Vishnu identity', 'This is how Vishnu will know and address you.')}<div class="genesis-content narrow"><div class="genesis-fields">${field('firstRunFirstName', 'First name', 'text', 'given-name')}${field('firstRunLastName', 'Last name', 'text', 'family-name')}${field('firstRunDisplayName', 'Display name', 'text', 'nickname', 'wide')}</div><div class="genesis-card-head">${icon('user')}<div><h3>Profile picture</h3><p>Optional &middot; Add after setup from your owner profile</p></div></div>${actions()}</div>`;

    if (n === 3) return `${heading('Secure your Vishnu', 'Choose how Vishnu should verify it\'s you.')}<div class="genesis-content medium"><div class="genesis-grid stack">${card({ value: 'passkey', title: 'Passkey', copy: 'Use your device\'s secure authentication &mdash; Face ID, Touch ID, Windows Hello or device biometrics.', badgeText: 'Recommended', name: 'auth', selected: true, iconName: 'user' })}${card({ value: 'password', title: 'Password', copy: 'Create a private owner password. A simple and secure way to verify it\'s you.', name: 'auth', iconName: 'lock' })}${card({ value: 'both', title: 'Passkey + Password', copy: 'Use both methods for maximum security and flexibility.', name: 'auth', iconName: 'shield' })}</div><p class="genesis-note">&#9432; You can add or remove authentication methods later from Security settings.</p>${actions()}</div>`;

    if (n === 4) return `${heading('Configure your authentication', 'Set up the authentication method you selected.')}<div class="genesis-content medium"><article class="genesis-card selected" data-auth-choice="passkey"><div class="genesis-card-head">${icon('user')}<div><h3>Create your passkey${badge('Recommended')}</h3><p>Use your device\'s biometric authentication to create secure owner access for Vishnu.</p></div></div>${features([['Fast and secure', 'Uses your device secure hardware.'], ['Works across your devices', 'Uses supported passkey providers.'], ['Private', 'Biometric data never leaves your device.'], ['Can be added later', 'Manage from Security settings.']])}</article><div class="genesis-or">OR</div><article class="genesis-card" data-auth-choice="password"><div class="genesis-card-head">${icon('lock')}<div><h3>Create a password instead</h3><p>Set a private owner password to verify it\'s you.</p></div></div></article><div class="genesis-fields" style="margin-top:14px">${field('firstRunBootstrap', 'Local runtime setup code', 'password', 'one-time-code', 'wide')}${field('firstRunPassword', 'Owner password — 12 characters minimum', 'password', 'new-password')}${field('firstRunPasswordAgain', 'Confirm owner password', 'password', 'new-password')}</div>${actions('Create passkey &rarr;')}</div>`;

    if (n === 5) return `${heading('Protect your Vishnu', 'Set up recovery so you can restore Vishnu if you lose access to your devices.')}<div class="genesis-content medium"><article class="genesis-card selected"><div class="genesis-card-head">${icon('key')}<div><h3>Recovery codes${badge('Required')}</h3><p>Generate one-time recovery codes that can restore your Vishnu if you lose access to every device.</p></div></div>${features([['One-time codes', 'Each code can be used once.'], ['Keep them safe', 'Store them somewhere secure.'], ['Not stored by Vishnu', 'We do not keep a readable copy.']])}<pre id="firstRunCodes" class="genesis-recovery">Recovery codes will appear after security is created.</pre></article><article class="genesis-card"><div class="genesis-card-head">${icon('cloud')}<div><h3>Encrypted recovery package${badge('Recommended')}</h3><p>Create an encrypted recovery package that can help restore configuration and identity on another trusted device.</p></div></div>${features([['Your data, encrypted', 'Encrypted with your keys.'], ['Choose where to save', 'You decide the location.'], ['Use when needed', 'Helps restore your Vishnu.']])}</article><label class="genesis-check"><input id="firstRunRecoverySaved" type="checkbox">I have safely stored my recovery codes somewhere secure.</label>${actions()}</div>`;

    if (n === 6) return `${heading('Register this device', 'Make this device part of your trusted Vishnu network.')}<div class="genesis-content medium"><div class="genesis-grid"><article class="genesis-card selected"><div class="genesis-card-head">${icon('device')}<div><h3>This device</h3><p id="genesisDeviceName">Your browser</p></div></div>${features([['Secure storage available', 'Local credentials stay on this device.'], ['Device key created', 'Independent and revocable.']])}</article><article class="genesis-card"><div class="genesis-card-head">${icon('shield')}<div><h3>Trusted devices can</h3><p>Sign in to Vishnu, continue your work, access allowed data, and help restore your Vishnu.</p></div></div>${features([['Continue your work', 'Your context stays with you.'], ['Receive capabilities', 'Only approved features.']])}</article></div>${field('genesisDeviceAlias', 'Device name', 'text', 'off')}${actions('Trust this device &rarr;')}</div>`;

    if (n === 7) return `${heading('Choose where your data lives', 'Decide how Vishnu stores and reaches your information across trusted devices.')}<div class="genesis-content medium"><div class="genesis-grid">${card({ value: 'device_only', title: 'Device Only', copy: 'Keep this data only on this device.', name: 'data', iconName: 'device', details: features([['Maximum local privacy', 'Offline use and no automatic cross-device copy.']]) })}${card({ value: 'progress_only', title: 'Progress Only', copy: 'Share only the minimum continuation state needed to keep working.', badgeText: 'Recommended', name: 'data', selected: true, iconName: 'folder', details: features([['Privacy plus continuity', 'Ideal for most owners.']]) })}${card({ value: 'sync_everywhere', title: 'Sync Everywhere', copy: 'Keep permitted synchronized copies on your trusted devices.', name: 'data', iconName: 'cloud', details: features([['Seamless access', 'Your allowed data stays in sync.']]) })}${card({ value: 'on_demand', title: 'On Demand', copy: 'Keep data in place and reach it securely only when needed.', name: 'data', iconName: 'data', details: features([['No automatic copies', 'Good for large or external files.']]) })}</div><p class="genesis-note">&#9432; Changing this default never silently moves data that already exists.</p>${actions()}</div>`;

    if (n === 8) return `${heading('Set up Vishnu\'s intelligence', 'Choose how Vishnu should think and which AI providers it may use.')}<div class="genesis-content medium"><div class="genesis-grid">${card({ value: 'skip', title: 'Recommended Setup', copy: 'Vishnu chooses the best configured intelligence for you.', badgeText: 'Recommended', name: 'ai', selected: true, iconName: 'sparkle', details: features([['Best model for your needs', 'Balanced performance and privacy.']]) })}${card({ value: 'local', title: 'Local Intelligence', copy: 'Use a compatible model running on this device where available.', name: 'ai', iconName: 'device', details: features([['Maximum privacy', 'Offline use; no data leaves this device.']]) })}${card({ value: 'provider', title: 'Connect an AI Provider', copy: 'Configure OpenAI, Gemini, OpenRouter, DeepSeek, xAI, Groq and more.', name: 'ai', iconName: 'cloud', details: features([['Your preferred provider', 'Credentials are stored securely.']]) })}${card({ value: 'later', title: 'Set Up Later', copy: 'Finish Vishnu first and configure intelligence later from Settings.', name: 'ai', iconName: 'brain', details: features([['Quick setup now', 'Configure at any time.']]) })}</div><div id="genesisProviderFields" class="genesis-fields hidden"><select id="firstRunProvider"><option value="openai">OpenAI</option><option value="gemini">Gemini</option><option value="openrouter">OpenRouter</option><option value="deepseek">DeepSeek</option><option value="xai">xAI</option><option value="groq">Groq</option><option value="cerebras">Cerebras</option><option value="mistral">Mistral</option></select>${field('firstRunModel', 'Model name')}${field('firstRunApiKey', 'Provider API key', 'password', 'new-password', 'wide')}</div>${actions()}</div>`;

    if (n === 9) return `${heading('Choose what Vishnu can access', 'You stay in control. Vishnu only uses permissions and information you allow.')}<div class="genesis-content"><div class="genesis-grid"><article class="genesis-card"><div class="genesis-card-head">${icon('brain')}<div><h3>Personal Intelligence</h3><p>Memory, knowledge, files, projects and work context.</p></div></div><select id="firstRunPrivacy" style="margin-top:12px"><option value="local_only">Local only</option><option value="local_preferred" selected>Allow with local preference</option><option value="external_allowed">Allow external providers</option></select></article><article class="genesis-card"><div class="genesis-card-head">${icon('device')}<div><h3>Device Capabilities</h3><p>Microphone, camera, notifications, screen and clipboard.</p></div></div><select aria-label="Device capability policy" style="margin-top:12px"><option>Ask when needed</option><option>Do not allow</option></select></article><article class="genesis-card"><div class="genesis-card-head">${icon('device')}<div><h3>Computer &amp; Browser Control</h3><p>Approval is required for consequential device and browser actions.</p></div></div></article><article class="genesis-card"><div class="genesis-card-head">${icon('cloud')}<div><h3>Connected Services</h3><p>Apps connected later keep their own permission scopes.</p></div></div></article></div><label class="genesis-check genesis-card"><input id="genesisApproval" type="checkbox" checked><span><strong>Ask before important actions</strong><br>Vishnu will ask for your approval before important external changes.</span></label>${actions()}</div>`;

    const owner = s.owner || 'Vishnu Owner';
    const review = [
      ['user', 'Owner', `${owner}<br>Personal identity configured`],
      ['shield', 'Security', `${s.auth}<br>Recovery setup complete`],
      ['device', 'Trusted Device', 'This device<br>Full trust ready'],
      ['data', 'Data', `${s.dataPolicy.replaceAll('_', ' ')}<br>Placement policy selected`],
      ['sparkle', 'Intelligence', `${s.intelligence === 'skip' ? 'Recommended setup' : s.intelligence}<br>Choice saved securely`],
      ['check', 'Privacy & Permissions', 'Owner controlled<br>Important actions require approval'],
    ];
    return `${heading('Your Vishnu is ready to be created', 'Review your setup, then create your Vishnu.')}<div class="genesis-content"><div class="genesis-grid">${review.map(([iconName, title, copy]) => `<article class="genesis-card genesis-review"><div class="genesis-card-head">${icon(iconName)}<div><strong>${title}</strong><small>${copy}</small></div></div></article>`).join('')}</div>${actions('Create my Vishnu &rarr;')}</div>`;
  }

  function render(n = s.step) {
    s.step = Math.max(1, Math.min(10, n));
    const progress = s.step > 1;
    panel.innerHTML = `<main class="genesis-shell genesis-screen" data-step="${s.step}"><header class="genesis-top"><button class="genesis-back ${progress ? '' : 'hidden'}" type="button" data-genesis-back>&larr; Back</button><div class="genesis-brand">VISHNU</div><div class="genesis-progress ${progress ? '' : 'hidden'}">Step ${s.step} of 10${dots(s.step)}</div></header><section class="genesis-stage"><div class="genesis-core" data-state="${coreState(s.step)}" role="img" aria-label="Vishnu intelligence core, onboarding step ${s.step}"><div class="genesis-network"></div></div>${content(s.step)}</section>${footer}</main>`;
    bind();
  }

  function bind() {
    panel.querySelectorAll('[data-genesis-back]').forEach(button => { button.onclick = () => s.step > 1 && render(s.step-1); });
    panel.querySelector('[data-genesis-create]')?.addEventListener('click', () => render(2));
    panel.querySelector('[data-genesis-join]')?.addEventListener('click', () => showLegacy('join'));
    panel.querySelector('[data-genesis-restore]')?.addEventListener('click', () => showLegacy('restore'));
    panel.querySelector('[data-genesis-next]')?.addEventListener('click', () => window.dispatchEvent(new CustomEvent('vishnu:genesis-next', { detail: { step: s.step } })));
    panel.querySelectorAll('input[name=auth]').forEach(input => { input.onchange = () => s.auth = input.value; });
    if (s.step === 4) {
      const choices = [...panel.querySelectorAll('[data-auth-choice]')];
      const selectAuth = choice => {
        s.auth = choice.dataset.authChoice;
        choices.forEach(card => {
          const selected = card === choice;
          card.classList.toggle('selected', selected);
          card.setAttribute('aria-checked', String(selected));
        });
        const next = panel.querySelector('[data-genesis-next]');
        if (next) next.innerHTML = s.auth === 'password' ? 'Create password &rarr;' : 'Create passkey &rarr;';
      };
      choices.forEach(card => {
        card.setAttribute('role', 'radio');
        card.tabIndex = 0;
        card.addEventListener('click', () => selectAuth(card));
        card.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectAuth(card); }
        });
      });
      selectAuth(choices.find(card => card.dataset.authChoice === s.auth) || choices[0]);
      if (s.options.local_setup_available) {
        const code = $('firstRunBootstrap');
        code?.remove();
        const notice = document.createElement('p');
        notice.className = 'genesis-note local-setup-note';
        notice.setAttribute('role', 'status');
        notice.textContent = 'Local development mode: setup code is not needed. This runtime is restricted to this computer.';
        panel.querySelector('.genesis-fields')?.prepend(notice);
      }
    }
    panel.querySelectorAll('input[name=data]').forEach(x => { x.onchange = () => { s.dataPolicy=x.value; }; });
    panel.querySelectorAll('input[name=ai]').forEach(x => { x.onchange = () => { s.intelligence=x.value; if (s.intelligence === 'later') s.intelligence = 'skip'; $('genesisProviderFields')?.classList.toggle('hidden', x.value !== 'provider'); }; });
    panel.querySelectorAll('[data-genesis-info]').forEach(link => { link.onclick = event => { event.preventDefault(); setError(link.dataset.genesisInfo === 'privacy' ? 'Your setup remains local and owner controlled.' : 'Keyboard, screen reader, large text and reduced motion are supported.'); }; });
    if ($('genesisDeviceName')) $('genesisDeviceName').textContent = `${navigator.userAgentData?.platform || navigator.platform || 'This device'} browser`;
  }

  function setError(message = '') { const element = $('genesisStatus'); if (element) element.textContent = message; }
  function showLegacy(kind) { sessionStorage.setItem('vishnuAccessIntent', kind); location.reload(); }
  const authIcon = name => ({
    passkey: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v10m-4-5h8"/></svg>',
    lock: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>',
    device: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/></svg>',
    recovery: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="8" cy="15" r="4"/><path d="m11 12 9-9m-3 3 3 3m-6 0 3 3"/></svg>',
    create: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 12-6.9M19 16v6m-3-3h6"/></svg>',
    restore: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>',
  }[name]);
  function authButton(kind, title, detail, action, primary = false) {
    return `<button type="button" class="returning-action ${primary ? 'primary' : ''}" data-auth-action="${kind}"><span class="returning-action-icon">${authIcon(kind) || ''}</span><span class="returning-action-copy"><strong>${title}</strong>${detail ? `<small>${detail}</small>` : ''}</span><span class="returning-arrow" aria-hidden="true">→</span></button>`;
  }
  function renderReturning(view = 'welcome') {
    s.authView = view;
    panel.setAttribute('aria-label', view === 'restore' ? 'Recover owner access' : 'Vishnu owner authentication');
    const configured = Boolean(s.options.passkey_available || s.options.password_available || s.options.recovery_available || s.options.google_available);
    const freshRuntime = Boolean(s.options.creation_available && !s.options.setup_in_progress);
    const supportedPasskey = Boolean(s.options.passkey_available && window.PublicKeyCredential && navigator.credentials);
    const body = view === 'restore'
      ? `<div class="returning-actions returning-form"><label class="returning-password-label" for="recoveryCode">Recovery code</label><input id="recoveryCode" type="text" autocomplete="one-time-code" autocapitalize="characters" placeholder="Enter a saved recovery code"/><button id="recoveryLogin" class="genesis-primary" type="button">Verify and continue →</button></div>`
      : freshRuntime
      ? `<div class="returning-notice" role="status"><strong>No existing Vishnu is configured on this local runtime.</strong><span>You can create a new Vishnu here, or restore one from recovery materials. Nothing has been signed in or changed.</span></div><div class="returning-actions">${authButton('create', 'Create my Vishnu', 'Start owner setup on this device.', null, true)}${authButton('restore', 'Restore Vishnu', 'Choose recovery materials to begin.', null)}</div>`
      : !configured
        ? `<div class="returning-notice" role="status"><strong>No sign-in method is available on this device.</strong><span>Use another trusted device to connect, or choose a recovery method.</span></div><div class="returning-actions">${authButton('device', 'Connect another device', 'Continue from a trusted device.')}${authButton('restore', 'Restore Vishnu', 'Use verified recovery materials.')}</div>`
      : view === 'methods'
        ? `<div class="returning-actions">${supportedPasskey ? authButton('passkey', 'Passkey', 'Use a passkey configured for this Vishnu.', null, true) : ''}${s.options.password_available ? authButton('password', 'Owner password', 'Use your existing owner password.') : ''}${s.options.recovery_available ? authButton('recovery', 'Recovery code', 'Use a saved one-time recovery code.') : ''}${s.options.google_available ? authButton('google', 'Google', 'Continue with the configured Google sign-in.') : ''}${!supportedPasskey && !s.options.password_available && !s.options.recovery_available && !s.options.google_available ? '<div class="returning-notice" role="status"><strong>No sign-in method is available in this browser.</strong><span>Use another trusted device or restore Vishnu using verified recovery materials.</span></div>' : ''}</div><button class="returning-text-action" type="button" data-auth-action="welcome">← Back</button>`
        : view === 'google'
          ? '<div id="googleLogin" class="google-login" aria-label="Sign in with Google"></div><button class="returning-text-action" type="button" data-auth-action="methods">← Other sign-in methods</button>'
        : `<div class="returning-actions">${supportedPasskey ? authButton('passkey', 'Continue with passkey', 'Use this device’s secure authentication.', null, true) : ''}${authButton('methods', 'Use another sign-in method', 'Choose from methods configured for this Vishnu.')}${authButton('device', 'Connect another device', 'Sign in first, then manage trusted devices.')}</div><div class="returning-recovery"><span>Lost access to your Vishnu?</span><button type="button" class="returning-text-action" data-auth-action="restore">Restore Vishnu →</button></div>`;
    panel.className = 'genesis';
    const title = view === 'restore' ? 'Recover owner <em>access</em>' : freshRuntime ? 'Welcome to <em>Vishnu</em>' : 'Welcome back to <em>Vishnu</em>';
    const subtitle = view === 'restore' ? 'Use a saved one-time recovery code to verify ownership and sign in.' : freshRuntime ? 'This runtime is ready for a new owner setup or a verified restore.' : 'Sign in to continue with your personal Vishnu.';
    panel.innerHTML = `<main class="genesis-shell returning-shell"><header class="genesis-top"><button class="genesis-back" type="button" data-auth-action="${view === 'restore' ? 'welcome' : 'back'}">← ${view === 'restore' ? 'Back to Welcome' : 'Back to Welcome'}</button><div class="genesis-brand">VISHNU</div><span></span></header><section class="genesis-stage"><div class="genesis-core" role="img" aria-label="Vishnu intelligence core. Ready for owner authentication."></div><div class="genesis-copy"><h1>${title}</h1><p>${subtitle}</p></div>${body}<p id="returningStatus" class="genesis-error" role="status" aria-live="polite"></p></section><footer class="genesis-footer"><a href="#" data-genesis-info="privacy">Privacy</a><span>|</span><a href="#" data-genesis-info="accessibility">Accessibility</a></footer></main>`;
    if (view === 'restore') {
      const notice = document.createElement('div');
      notice.className = 'returning-notice';
      notice.setAttribute('role', 'note');
      notice.innerHTML = '<strong>This recovers owner access, not backup data.</strong><span>Enter a saved one-time recovery code to sign in. To restore a .vdr or .paibackup file, use the Vishnu desktop first-run restore workflow.</span>';
      panel.querySelector('.genesis-copy').after(notice);
      const label = panel.querySelector('label[for="recoveryCode"]');
      if (label) label.textContent = 'One-time recovery code';
      const submit = panel.querySelector('#recoveryLogin');
      if (submit) submit.textContent = 'Verify owner access';
    }
    if (freshRuntime) {
      const noticeText = panel.querySelector('.returning-notice span');
      if (noticeText) noticeText.textContent = 'Create a new Vishnu here, or use the desktop first-run restore workflow to restore backup data. A recovery code only restores owner access.';
      const recoveryAction = panel.querySelector('[data-auth-action="restore"]');
      if (recoveryAction) {
        recoveryAction.querySelector('strong').textContent = 'Recover owner access';
        recoveryAction.querySelector('small').textContent = 'Sign in with a saved one-time recovery code.';
      }
    }
    panel.querySelectorAll('[data-auth-action]').forEach(button => button.addEventListener('click', () => handleReturningAction(button.dataset.authAction)));
    panel.querySelectorAll('[data-genesis-info]').forEach(link => link.addEventListener('click', event => {
      event.preventDefault();
      $('returningStatus').textContent = link.dataset.genesisInfo === 'privacy'
        ? 'Your sign-in stays local to this Vishnu runtime and uses its configured owner security.'
        : 'Keyboard navigation, visible focus and reduced motion are supported.';
    }));
    if (view === 'restore') $('recoveryLogin').onclick = async () => { try { s.accessIntent = ''; await api('/access/recovery/login', { method: 'POST', body: JSON.stringify({ code: $('recoveryCode').value, name: 'Vishnu owner recovery browser' }) }); await check(); } catch (error) { $('returningStatus').textContent = error.message; } };
    if (view === 'google') renderGoogleLogin();
  }
  async function handleReturningAction(action) {
    const status = $('returningStatus');
    try {
      if (action === 'back') { s.accessIntent = ''; show(); render(1); return; }
      if (action === 'create') { s.accessIntent = ''; show(); render(1); return; }
      if (action === 'methods') { renderReturning('methods'); return; }
      if (action === 'welcome') { renderReturning('welcome'); return; }
      if (action === 'restore') {
        renderReturning('restore');
        return;
      }
      if (action === 'device') { s.pendingPostAuthAction = 'devices'; renderReturning('methods'); $('returningStatus').textContent = 'Verify your identity to continue to trusted devices.'; return; }
      if (action === 'passkey') {
        if (!window.PublicKeyCredential || !navigator.credentials || !s.options.passkey_available) throw new Error('A passkey is not available for this Vishnu on this device. Choose another configured sign-in method.');
        s.accessIntent = '';
        const start = await api('/access/passkey/login/options', { method: 'POST', body: '{}' });
        const credential = await navigator.credentials.get({ publicKey: requestOptions(start.public_key) });
        await api('/access/passkey/login/complete', { method: 'POST', body: JSON.stringify({ challenge_id: start.challenge_id, credential: credentialJson(credential), name: 'Vishnu owner browser' }) });
        await check();
      }
      if (action === 'password') {
        panel.querySelector('.returning-actions').innerHTML = '<label class="returning-password-label" for="returningPassword">Owner password</label><input id="returningPassword" type="password" autocomplete="current-password" placeholder="Enter your owner password"/><button type="button" class="genesis-primary" data-auth-action="password-submit">Unlock Vishnu →</button><button type="button" class="returning-text-action" data-auth-action="methods">← Other sign-in methods</button>';
        panel.querySelectorAll('[data-auth-action]').forEach(button => button.addEventListener('click', () => handleReturningAction(button.dataset.authAction)));
        $('returningPassword').focus(); return;
      }
      if (action === 'password-submit') {
        s.accessIntent = '';
        await api('/access/password/login', { method: 'POST', body: JSON.stringify({ password: $('returningPassword').value, name: 'Vishnu owner browser' }) });
        await check();
      }
      if (action === 'recovery') renderReturning('restore');
      if (action === 'google') { s.accessIntent = ''; renderReturning('google'); }
    } catch (error) {
      const message = error?.name === 'NotAllowedError' ? 'Authentication was cancelled or unavailable.' : error?.message || 'Vishnu could not complete sign-in.';
      if (status) status.textContent = message;
    }
  }
  function show() {
    if (!document.body.classList.contains('genesis-active')) {
      priorNavigationState = backgroundNavigation.map(element => ({ element, ariaHidden: element.getAttribute('aria-hidden'), inert: element.inert }));
      backgroundNavigation.forEach(element => { element.setAttribute('aria-hidden', 'true'); element.inert = true; });
    }
    document.body.classList.add('genesis-active'); panel.className = 'genesis'; render(s.step);
  }
  function hide() {
    document.body.classList.remove('genesis-active'); panel.classList.add('hidden');
    for (const { element, ariaHidden, inert } of priorNavigationState) {
      if (ariaHidden === null) element.removeAttribute('aria-hidden'); else element.setAttribute('aria-hidden', ariaHidden);
      element.inert = inert;
    }
    priorNavigationState = [];
  }

  window.vishnuFirstRun = { state: s, render, setError, showLegacy, $ };
  window.loadAccessOptions = async (...args) => { s.options = await originalLoad(...args) || {}; return s.options; };
  window.check = async (...args) => {
    const result = await originalCheck(...args);
    try {
      s.options = await originalLoad() || {};
      if (s.accessIntent === 'join' || s.accessIntent === 'restore') { show(); renderReturning(s.accessIntent === 'restore' ? 'restore' : 'welcome'); }
      else if (s.options.creation_available) show();
      else if (result) {
        hide();
        if (s.pendingPostAuthAction) {
          const destination = s.pendingPostAuthAction;
          s.pendingPostAuthAction = '';
          setTimeout(() => window.vishnuChatBridge?.openModule(destination), 0);
        }
      }
    } catch { /* legacy surface reports its own error */ }
    return result;
  };
  window.loadAccessOptions().then(() => window.check()).catch(() => {});
})();
