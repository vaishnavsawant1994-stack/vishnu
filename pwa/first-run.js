/* Vishnu Genesis: canonical responsive onboarding for desktop and mobile. */
(() => {
  const $ = id => document.getElementById(id);
  const originalLoad = window.loadAccessOptions;
  const originalCheck = window.check;
  if (typeof originalLoad !== 'function' || typeof originalCheck !== 'function') return;

  const accessIntent = sessionStorage.getItem('vishnuAccessIntent');
  if (accessIntent) {
    sessionStorage.removeItem('vishnuAccessIntent');
    setTimeout(() => {
      if (accessIntent === 'join') ($('passkeyLogin').disabled ? $('passwordChoice') : $('passkeyLogin'))?.focus();
      else { $('troubleOptions')?.classList.remove('hidden'); $('recoveryCode')?.focus(); }
    }, 0);
    return;
  }

  const requestedStep = new URLSearchParams(location.search).get('genesisStep');
  const localPreviewStep = /^(localhost|127\.0\.0\.1)$/.test(location.hostname) && /^(?:[1-9]|10)$/.test(requestedStep || '')
    ? Number(requestedStep) : 1;
  const s = {
    step: localPreviewStep, options: {}, identityCreated: false, recoverySaved: false,
    policySaved: false, modelSaved: false, passkeyCreated: false,
    auth: 'passkey', dataPolicy: 'progress_only', intelligence: 'skip', privacy: 'local_preferred',
  };
  const panel = $('enrollPanel');
  panel.className = 'genesis hidden';
  panel.setAttribute('aria-label', 'Vishnu Genesis onboarding');

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

    if (n === 4) return `${heading('Configure your authentication', 'Set up the authentication method you selected.')}<div class="genesis-content medium"><article class="genesis-card selected"><div class="genesis-card-head">${icon('user')}<div><h3>Create your passkey${badge('Recommended')}</h3><p>Use your device\'s biometric authentication to create secure owner access for Vishnu.</p></div></div>${features([['Fast and secure', 'Uses your device secure hardware.'], ['Works across your devices', 'Uses supported passkey providers.'], ['Private', 'Biometric data never leaves your device.'], ['Can be added later', 'Manage from Security settings.']])}<div class="genesis-fields" style="margin-top:14px">${field('firstRunBootstrap', 'Local runtime setup code', 'password', 'one-time-code', 'wide')}${field('firstRunPassword', 'Owner password — 12 characters minimum', 'password', 'new-password')}${field('firstRunPasswordAgain', 'Confirm owner password', 'password', 'new-password')}</div></article><div class="genesis-or">OR</div><article class="genesis-card"><div class="genesis-card-head">${icon('lock')}<div><h3>Create a password instead</h3><p>Set a private owner password to verify it\'s you.</p></div></div></article>${actions('Create passkey &rarr;')}</div>`;

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
    panel.querySelectorAll('input[name=data]').forEach(x => { x.onchange = () => { s.dataPolicy=x.value; }; });
    panel.querySelectorAll('input[name=ai]').forEach(x => { x.onchange = () => { s.intelligence=x.value; if (s.intelligence === 'later') s.intelligence = 'skip'; $('genesisProviderFields')?.classList.toggle('hidden', x.value !== 'provider'); }; });
    panel.querySelectorAll('[data-genesis-info]').forEach(link => { link.onclick = event => { event.preventDefault(); setError(link.dataset.genesisInfo === 'privacy' ? 'Your setup remains local and owner controlled.' : 'Keyboard, screen reader, large text and reduced motion are supported.'); }; });
    if ($('genesisDeviceName')) $('genesisDeviceName').textContent = `${navigator.userAgentData?.platform || navigator.platform || 'This device'} browser`;
  }

  function setError(message = '') { const element = $('genesisStatus'); if (element) element.textContent = message; }
  function showLegacy(kind) { sessionStorage.setItem('vishnuAccessIntent', kind); location.reload(); }
  function show() { document.body.classList.add('genesis-active'); panel.className = 'genesis'; render(s.step); }
  function hide() { document.body.classList.remove('genesis-active'); panel.classList.add('hidden'); }

  window.vishnuFirstRun = { state: s, render, setError, showLegacy, $ };
  window.loadAccessOptions = async (...args) => { s.options = await originalLoad(...args) || {}; return s.options; };
  window.check = async (...args) => {
    const result = await originalCheck(...args);
    try { s.options = await originalLoad() || {}; if (s.options.creation_available) show(); else if (result) hide(); } catch { /* legacy surface reports its own error */ }
    return result;
  };
  window.loadAccessOptions().then(() => window.check()).catch(() => {});
})();
