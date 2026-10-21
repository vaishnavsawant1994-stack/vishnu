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
  const localPreviewStep = /^(localhost|127\.0\.0\.1)$/.test(location.hostname) && /^(?:[1-4])$/.test(requestedStep || '')
    ? Number(requestedStep) : 1;
  const s = {
    step: localPreviewStep, options: {}, identityCreated: false, recoveryCodes: [], recoverySaved: false,
    policySaved: false, modelSaved: false, passkeyCreated: false,
    auth: 'passkey', dataPolicy: 'device_only', intelligence: 'skip', privacy: 'local_only',
    accessIntent: accessIntent || '', authView: 'welcome', pendingPostAuthAction: '',
  };
  const panel = $('enrollPanel');
  panel.className = 'genesis hidden';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-modal', 'true');
  panel.setAttribute('aria-label', 'Vishnu Genesis onboarding');
  const backgroundNavigation = [...document.querySelectorAll('.reference-desktop-sidebar,.reference-desktop-tools,.reference-mobile-nav,#drawerOverlay,#appDrawer,#conversationDrawer')];
  let priorNavigationState = [];
  let disposeWelcome = () => {};
  let welcomeMountId = 0;

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
  const dots = n => `<div class="genesis-dots" aria-hidden="true">${Array.from({ length: 3 }, (_, i) => `<i class="${i < n ? 'on' : ''}"></i>`).join('')}</div>`;
  const coreState = n => n >= 4 ? 'recovery' : n >= 3 ? 'security' : 'identity';
  const badge = text => text ? `<span class="genesis-badge">${text}</span>` : '';
  const field = (id, placeholder, type = 'text', autocomplete = 'off', cls = '') => `<input class="${cls}" id="${id}" type="${type}" autocomplete="${autocomplete}" placeholder="${placeholder}">`;
  const heading = (title, copy) => `<div class="genesis-copy"><h1>${title}</h1><p>${copy}</p></div>`;
  const actions = (primary = 'Continue &rarr;', secondary = true) => `<div class="genesis-actions"><button class="genesis-primary" data-genesis-next type="button">${primary}</button>${secondary ? '<button class="genesis-tertiary" data-genesis-back type="button">&larr; Back</button>' : ''}<p id="genesisStatus" class="genesis-error" role="status" aria-live="polite"></p></div>`;
  const footer = '<footer class="genesis-footer"><a href="#" data-genesis-info="privacy">Privacy</a><span>|</span><a href="#" data-genesis-info="accessibility">Accessibility</a></footer>';
  const features = items => `<div class="genesis-features">${items.map(([title, copy]) => `<div class="genesis-feature"><strong>&#10003; ${title}</strong>${copy}</div>`).join('')}</div>`;
  const card = ({ value, title, copy, badgeText = '', name = 'choice', selected = false, iconName = 'check', details = '' }) => `<label class="genesis-card ${selected ? 'selected' : ''}"><input type="radio" name="${name}" value="${value}" ${selected ? 'checked' : ''}><div class="genesis-card-head">${icon(iconName)}<div><h3>${title}${badge(badgeText)}</h3><p>${copy}</p></div></div>${details}</label>`;

  function content(n) {
    if (n === 1) return `${heading('Welcome to Vishnu', 'Your personal AI. Your world.')}<div class="genesis-actions"><button class="genesis-primary" data-genesis-create>Create My Vishnu &rarr;</button><div class="genesis-secondary-row"><button class="genesis-tertiary" data-genesis-join>I Already Have Vishnu</button><span>|</span><button class="genesis-tertiary" data-genesis-restore>Restore Vishnu</button></div><p id="genesisStatus" class="genesis-error" role="status" aria-live="polite"></p></div>`;
    if (n === 2) return `${heading('What should Vishnu call you?', 'Your name helps personalize your Vishnu.')}<div class="genesis-content narrow"><div class="genesis-fields">${field('firstRunFirstName', 'First name', 'text', 'given-name')}${field('firstRunLastName', 'Last name (optional)', 'text', 'family-name')}${field('firstRunDisplayName', 'Display name', 'text', 'nickname', 'wide')}</div><p class="genesis-note">You can add a profile picture later from your profile.</p>${actions()}</div>`;
    if (n === 3) return `${heading('Secure your Vishnu', 'Choose a sign-in method and set a strong owner password.')}<div class="genesis-content medium"><div class="genesis-grid stack">${card({ value: 'passkey', title: 'Password + passkey', copy: 'Use your owner password and add this device’s secure sign-in.', badgeText: 'Recommended', name: 'auth', selected: true, iconName: 'user' })}${card({ value: 'password', title: 'Password only', copy: 'Use your owner password to sign in.', name: 'auth', iconName: 'lock' })}</div><p class="genesis-note">This runtime requires an owner password to protect setup and recovery. A passkey is an additional sign-in method and may be added later.</p><div class="genesis-fields">${field('firstRunBootstrap', 'Local runtime setup code', 'password', 'one-time-code', 'wide')}${field('firstRunPassword', 'Owner password - 12 characters minimum', 'password', 'new-password')}${field('firstRunPasswordAgain', 'Confirm owner password', 'password', 'new-password')}</div>${actions('Secure Vishnu &rarr;')}</div>`;
    if (n === 4) return `${heading('Save your Vishnu Recovery Key', 'Keep these one-time recovery codes somewhere safe. They help you regain access if you lose your sign-in method.')}<div class="genesis-content medium">${s.options.restore_report?.status === 'restored' ? `<div class="genesis-note" role="status">Recovery complete: ${Number(s.options.restore_report.restored_items) || 0} files restored from an authenticated encrypted package. Owner and Vishnu identity preserved. Device credentials and prior security state were not restored.</div>` : ''}<article class="genesis-card selected"><div class="genesis-card-head">${icon('key')}<div><h3>Recovery codes${badge('Required')}</h3><p>Each code can be used once. Vishnu does not keep a readable copy.</p></div></div><pre id="firstRunCodes" class="genesis-recovery">Recovery codes are shown only once. If you did not save your earlier codes, generate a fresh set below.</pre><button type="button" class="genesis-tertiary" data-genesis-regenerate-codes>Generate fresh recovery codes</button></article><label class="genesis-check"><input id="firstRunRecoverySaved" type="checkbox" ${s.options.setup_recovery_saved ? 'checked' : ''}>I have safely saved my recovery codes.</label>${actions('Create My Vishnu &rarr;')}</div>`;
    if (n === 1) return `${heading('Welcome to Vishnu', 'Your personal AI. Your world.')}<div class="genesis-actions"><button class="genesis-primary" data-genesis-create>Create My Vishnu &rarr;</button><div class="genesis-secondary-row"><button class="genesis-tertiary" data-genesis-join>I Already Have Vishnu</button><span>|</span><button class="genesis-tertiary" data-genesis-restore>Restore Vishnu</button></div><p id="genesisStatus" class="genesis-error" role="status" aria-live="polite"></p></div>`;

    if (n === 2) return `${heading('What should Vishnu call you?', 'Your name helps personalize your Vishnu.')}<div class="genesis-content narrow"><div class="genesis-fields">${field('firstRunFirstName', 'First name', 'text', 'given-name')}${field('firstRunLastName', 'Last name (optional)', 'text', 'family-name')}${field('firstRunDisplayName', 'Display name', 'text', 'nickname', 'wide')}</div><p class="genesis-note">You can add a profile picture later from your profile.</p>${actions()}</div>`;

    if (n === 3) return `${heading('Secure your Vishnu', 'Choose a sign-in method and set a strong owner password.')}<div class="genesis-content medium"><div class="genesis-grid stack">${card({ value: 'passkey', title: 'Passkey', copy: 'Add your device’s secure sign-in as a convenient way to return.', badgeText: 'Recommended', name: 'auth', selected: true, iconName: 'user' })}${card({ value: 'password', title: 'Password only', copy: 'Use your owner password to sign in.', name: 'auth', iconName: 'lock' })}</div><p class="genesis-note">This runtime currently requires an owner password to protect setup and recovery. A passkey can be added when supported.</p><div class="genesis-fields">${field('firstRunBootstrap', 'Local runtime setup code', 'password', 'one-time-code', 'wide')}${field('firstRunPassword', 'Owner password - 12 characters minimum', 'password', 'new-password')}${field('firstRunPasswordAgain', 'Confirm owner password', 'password', 'new-password')}</div>${actions('Secure Vishnu &rarr;')}</div>`;

    if (n === 4) return `${heading('Configure your authentication', 'Set up the authentication method you selected.')}<div class="genesis-content medium"><article class="genesis-card selected" data-auth-choice="passkey"><div class="genesis-card-head">${icon('user')}<div><h3>Create your passkey${badge('Recommended')}</h3><p>Use your device\'s biometric authentication to create secure owner access for Vishnu.</p></div></div>${features([['Fast and secure', 'Uses your device secure hardware.'], ['Works across your devices', 'Uses supported passkey providers.'], ['Private', 'Biometric data never leaves your device.'], ['Can be added later', 'Manage from Security settings.']])}</article><div class="genesis-or">OR</div><article class="genesis-card" data-auth-choice="password"><div class="genesis-card-head">${icon('lock')}<div><h3>Create a password instead</h3><p>Set a private owner password to verify it\'s you.</p></div></div></article><div class="genesis-fields" style="margin-top:14px">${field('firstRunBootstrap', 'Local runtime setup code', 'password', 'one-time-code', 'wide')}${field('firstRunPassword', 'Owner password — 12 characters minimum', 'password', 'new-password')}${field('firstRunPasswordAgain', 'Confirm owner password', 'password', 'new-password')}</div>${actions('Create passkey &rarr;')}</div>`;

    if (n === 5) return `${heading('Protect your Vishnu', 'Set up recovery so you can restore Vishnu if you lose access to your devices.')}<div class="genesis-content medium"><article class="genesis-card selected"><div class="genesis-card-head">${icon('key')}<div><h3>Recovery codes${badge('Required')}</h3><p>These one-time codes are shown only once. Store them somewhere secure; Vishnu keeps no readable copy.</p></div></div>${features([['One-time codes', 'Each code can be used once.'], ['Keep them safe', 'Store them somewhere secure.'], ['Not stored by Vishnu', 'We do not keep a readable copy.']])}<pre id="firstRunCodes" class="genesis-recovery">Your existing recovery codes cannot be displayed again. If you did not save them, generate a fresh set below; this invalidates the old set.</pre><button type="button" class="genesis-tertiary" data-genesis-regenerate-codes>Generate fresh recovery codes</button></article><article class="genesis-card"><div class="genesis-card-head">${icon('cloud')}<div><h3>Encrypted recovery package${badge('Recommended')}</h3><p>Create an encrypted recovery package that can help restore configuration and identity on another trusted device.</p></div></div>${features([['Your data, encrypted', 'Encrypted with your keys.'], ['Choose where to save', 'You decide the location.'], ['Use when needed', 'Helps restore your Vishnu.']])}</article><label class="genesis-check"><input id="firstRunRecoverySaved" type="checkbox">I have safely stored my current recovery codes somewhere secure.</label>${actions()}</div>`;

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


  function welcomeMarkup() {
    return `<main class="genesis-shell genesis-screen genesis-welcome" data-step="1">
      <div class="vw-window-dots" aria-hidden="true"><i></i><i></i><i></i></div>
      <header class="vw-header">
        <div class="vw-brand"><span class="vw-logo" aria-hidden="true">
          <svg viewBox="0 0 48 48" fill="none"><path d="M24 3c2.7 12.7 5.3 15.3 18 21-12.7 2.7-15.3 5.3-18 21C21.3 32.3 18.7 29.7 6 24 18.7 21.3 21.3 18.7 24 3Z" fill="#e7ffff"/><path d="M24 9c1.8 9 3.9 11.1 13 15-9.1 1.9-11.2 4-13 13C22.2 28 20.1 25.9 11 24c9.1-1.9 11.2-4 13-15Z" fill="#73dfff"/></svg>
        </span><span>VISHNU 2.0</span></div>
        <span class="vw-screen-id" aria-label="Screen P1-01">P1-01</span>
      </header>
      <section class="vw-stage" aria-labelledby="vwHeadline">
        <div class="vw-sphere" aria-hidden="true"><canvas id="vwSphereCanvas"></canvas></div>
        <p class="vw-eyebrow">A NEW BEGINNING</p>
        <h1 class="vw-heading" id="vwHeadline">Welcome to <em>Vishnu.</em></h1>
        <p class="vw-subtitle">Your personal AI. Simple, secure, always with you.</p>
        <div class="vw-actions">
          <button type="button" class="vw-primary" data-genesis-create><span>Create My Vishnu</span><span class="vw-primary-arrow" aria-hidden="true">&rarr;</span></button>
          <div class="vw-cards">
            <button type="button" class="vw-card" data-genesis-join>
              <span class="vw-card-icon" aria-hidden="true"><svg viewBox="0 0 32 32"><circle cx="16" cy="10" r="5"/><path d="M7 28v-4a9 9 0 0 1 18 0v4Z"/></svg></span>
              <span class="vw-card-copy"><strong>I Already Have Vishnu</strong><small>Unlock or securely connect this device.</small></span><span class="vw-chevron" aria-hidden="true">&#8250;</span>
            </button>
            <button type="button" class="vw-card" data-genesis-restore>
              <span class="vw-card-icon" aria-hidden="true"><svg viewBox="0 0 32 32"><path d="M7 13a11 11 0 1 1-1 9M6 6v8h8"/></svg></span>
              <span class="vw-card-copy"><strong>Restore My Vishnu</strong><small>Recover login access or restore encrypted data.</small></span><span class="vw-chevron" aria-hidden="true">&#8250;</span>
            </button>
          </div>
          <p class="vw-status" id="genesisStatus" role="status" aria-live="polite"></p>
        </div>
      </section>
      <footer class="vw-footer">
        <div class="vw-privacy">PRIVATE BY DESIGN</div>
        <div class="vw-tools">
          <button type="button" class="vw-tool" data-vw-language><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2c-6 6-6 14 0 20M12 2c6 6 6 14 0 20"/></svg>Language</button>
          <span class="vw-tool-divider" aria-hidden="true"></span>
          <button type="button" class="vw-tool" data-vw-help><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M9.5 9a2.7 2.7 0 1 1 4.7 1.8c-.8.8-2.2 1.4-2.2 3.2M12 18h.01"/></svg>Help</button>
        </div>
      </footer>
      <dialog class="vw-dialog" id="vwLanguageDialog" aria-labelledby="vwLanguageTitle">
        <h2 id="vwLanguageTitle">Language</h2>
        <label for="vwLanguageSelection">Available language</label>
        <select id="vwLanguageSelection"><option value="en" selected>English</option></select>
        <p>English is currently supported in this onboarding experience. More languages will be offered when fully translated.</p>
        <button type="button" data-vw-close>Close</button>
      </dialog>
      <dialog class="vw-dialog" id="vwHelpDialog" aria-labelledby="vwHelpTitle">
        <h2 id="vwHelpTitle">Getting started with Vishnu</h2>
        <p><strong>Create My Vishnu</strong> begins a new owner setup only when the connected runtime allows it.</p>
        <p><strong>I Already Have Vishnu</strong> signs in or requests approval for an additional device.</p>
        <p><strong>Restore My Vishnu</strong> lets you recover access or verify encrypted recovery files. Recovery codes do not restore backup data.</p>
        <button type="button" data-vw-close>Close</button>
      </dialog>
    </main>`;
  }

  async function startWelcomeCreation() {
    const button = panel.querySelector('[data-genesis-create]');
    if (!button) return;
    button.disabled = true;
    try {
      const options = await window.loadAccessOptions();
      // Keep the UI state consistent with the authoritative status just fetched.
      // A disconnected or stale cached state must never enable duplicate owner creation.
      if (!options || typeof options !== 'object') throw new Error('Access options unavailable');
      s.options = options;
      if (options.setup_in_progress) {
        renderPendingSetup();
      } else if (options.creation_available) {
        render(2);
      } else {
        renderReturning('welcome');
      }
    } catch {
      setError('Could not verify owner setup status. Check your runtime connection and retry.');
      button.disabled = false;
    }
  }

  function render(n = s.step) {
    s.step = Math.max(1, Math.min(4, n));
    const progress = s.step > 1;
    const journeyStep = s.step - 1;

    disposeWelcome();
    const mountId = ++welcomeMountId;
    if (s.step === 1) {
      panel.setAttribute('aria-label', 'Welcome to Vishnu');
      panel.innerHTML = welcomeMarkup();
      bind();
      panel.querySelector('[data-vw-language]')?.addEventListener('click', () => $('vwLanguageDialog').showModal());
      panel.querySelector('[data-vw-help]')?.addEventListener('click', () => $('vwHelpDialog').showModal());
      panel.querySelectorAll('[data-vw-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
      import('/iphone/genesis-neural-sphere.js').then(({ mountNeuralSphere }) => {
        const canvas = $('vwSphereCanvas');
        if (mountId !== welcomeMountId || !canvas || !canvas.isConnected) return;
        disposeWelcome = mountNeuralSphere(canvas);
      }).catch(() => { $('vwSphereCanvas')?.parentElement?.classList.add('vw-static-fallback'); });
      return;
    }
    if (s.step === 2) {
      panel.setAttribute('aria-label', 'Vishnu owner identity');
      panel.innerHTML = '<main class="genesis-shell genesis-screen genesis-identity" data-step="2"><div id="viRoot" role="status" aria-live="polite">Loading your identity screen…</div></main>';
      import('/iphone/genesis-identity.js').then(({ mountIdentityScreen }) => {
        const root = document.getElementById('viRoot');
        if (mountId !== welcomeMountId || !root || !root.isConnected) return;
        disposeWelcome = mountIdentityScreen(root, s, {
          onBack: () => render(1),
          onContinue: () => window.dispatchEvent(new CustomEvent('vishnu:genesis-next', { detail: {step: 2} })),
        });
      }).catch(() => {
        const root = document.getElementById('viRoot');
        if (mountId !== welcomeMountId || !root) return;
        root.innerHTML = '<div class="vi-load-error" role="alert"><p>The identity screen could not load. Your Vishnu account has not been changed.</p><button type="button" data-vi-retry>Retry</button></div>';
        root.querySelector('[data-vi-retry]')?.addEventListener('click', () => render(2));
      });
      return;
    }
    if (s.step === 3) {
      panel.setAttribute('aria-label', 'Secure Your Vishnu');
      panel.innerHTML = '<main class="genesis-shell genesis-screen genesis-security" data-step="3"><div id="vsRoot" role="status" aria-live="polite">Loading the secure setup screen…</div></main>';
      import('/iphone/genesis-security.js').then(({ mountSecurityScreen }) => {
        const root = document.getElementById('vsRoot');
        if (mountId !== welcomeMountId || !root || !root.isConnected) return;
        disposeWelcome = mountSecurityScreen(root, s, {
          onBack: () => render(2),
          onContinue: () => window.vishnuFirstRun.continueSecurity(),
          onPasskey: options => window.vishnuFirstRun.startPasskeySetup(options),
        });
      }).catch(() => {
        const root = document.getElementById('vsRoot');
        if (mountId !== welcomeMountId || !root) return;
        root.innerHTML = '<div class="vi-load-error" role="alert"><p>The security screen could not load. Your setup has not been changed.</p><button type="button" data-vs-retry>Retry</button></div>';
        root.querySelector('[data-vs-retry]')?.addEventListener('click', () => render(3));
      });
      return;
    }
    if (s.step === 4) {
      panel.setAttribute('aria-label', 'Save Your Recovery Codes');
      panel.innerHTML = '<main class="genesis-shell genesis-screen genesis-security genesis-recovery-screen" data-step="4"><div id="vrRoot" role="status" aria-live="polite">Loading recovery codes…</div></main>';
      import('/iphone/genesis-recovery.js').then(({mountRecoveryScreen})=>{
        const root=document.getElementById('vrRoot');
        if(mountId!==welcomeMountId || !root || !root.isConnected)return;
        disposeWelcome=mountRecoveryScreen(root,s,{
          onBack:()=>render(3),
          onFinish:()=>window.vishnuFirstRun.finishRecovery(),
          onRegenerate:()=>window.vishnuFirstRun.regenerateRecoveryCodes(),
        });
      }).catch(()=>{
        const root=document.getElementById('vrRoot');
        if(mountId!==welcomeMountId || !root)return;
        root.textContent='Recovery screen could not load. Your recovery codes were not regenerated. ';
        const retry=document.createElement('button');
        retry.type='button';retry.textContent='Retry loading';
        retry.addEventListener('click',()=>render(4));root.append(retry);
      });
      return;
    }
    panel.setAttribute('aria-label', 'Vishnu owner setup');
    panel.innerHTML = `<main class="genesis-shell genesis-screen" data-step="${s.step}"><header class="genesis-top"><button class="genesis-back ${progress ? '' : 'hidden'}" type="button" data-genesis-back>&larr; Back</button><div class="genesis-brand">VISHNU</div><div class="genesis-progress ${progress ? '' : 'hidden'}">Step ${journeyStep} of 3${dots(journeyStep)}</div></header><section class="genesis-stage"><div class="genesis-core" data-state="${coreState(s.step)}" role="img" aria-label="Vishnu intelligence core, setup step ${journeyStep} of 3"><div class="genesis-network"></div></div>${content(s.step)}</section>${footer}</main>`;
    bind();
  }

  function bind() {
    panel.querySelectorAll('[data-genesis-back]').forEach(button => { button.onclick = () => s.step > 1 && render(s.step-1); });
    panel.querySelector('[data-genesis-create]')?.addEventListener('click', startWelcomeCreation);
    panel.querySelector('[data-genesis-join]')?.addEventListener('click', () => showLegacy('join'));
    panel.querySelector('[data-genesis-restore]')?.addEventListener('click', () => showLegacy('restore'));
    panel.querySelector('[data-genesis-next]')?.addEventListener('click', () => window.dispatchEvent(new CustomEvent('vishnu:genesis-next', { detail: { step: s.step } })));
    panel.querySelectorAll('input[name=auth]').forEach(input => { input.onchange = () => s.auth = input.value; });
    if (s.step === 3) {
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
    panel.querySelector('[data-genesis-regenerate-codes]')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      button.disabled = true;
      button.textContent = 'Generating fresh codes…';
      try {
        const request = window.vishnuFirstRun?.setupApi || api;
        const result = await request('/first-run/recovery-codes', { method: 'POST', body: '{}' });
        s.recoveryCodes = result.recovery_codes || [];
        $('firstRunCodes').textContent = s.recoveryCodes.join('\n');
        $('firstRunRecoverySaved').checked = false;
        setError('The previous recovery codes are now invalid. Save this new set before continuing.');
      } catch (error) {
        setError(error.message || 'Fresh recovery codes could not be generated.');
      } finally {
        button.disabled = false;
        button.textContent = 'Generate fresh recovery codes';
      }
    });
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
    disposeWelcome();
    const mountId = ++welcomeMountId;
    s.authView = view;
    panel.setAttribute('aria-label', view === 'restore' ? 'Recover owner access' : 'Vishnu owner authentication');
    const configured = Boolean(s.options.passkey_available || s.options.password_available || s.options.recovery_available || s.options.google_available);
    const freshRuntime = Boolean((s.options.creation_available || s.options.restore_available) && !s.options.setup_in_progress);
    const supportedPasskey = Boolean(s.options.passkey_available && window.PublicKeyCredential && navigator.credentials);
    // P1-05 is a separate returning-owner entry, not a fifth mandatory
    // first-run step. Reuse canonical password / WebAuthn / DeviceRegistry.
    if ((view === 'welcome' || view === 'login') && configured && !freshRuntime) {
      panel.className = 'genesis';
      panel.setAttribute('aria-label','Unlock Vishnu — returning owner');
      panel.innerHTML='<main class="genesis-shell genesis-screen genesis-security genesis-login" data-step="P1-05"><div id="vlRoot" role="status" aria-live="polite">Loading secure login…</div></main>';
      import('/iphone/genesis-login.js').then(({mountLoginScreen,publicKeyRequestOptions,serializeAuthentication})=>{
        const root=document.getElementById('vlRoot');
        if(mountId!==welcomeMountId || !root || !root.isConnected)return;
        const completeLogin=async result=>{
          if(result?.status==='approval_required'){
            renderJoinPending(result);
            return;
          }
          if(!result?.ok)throw new Error('Vishnu did not confirm authentication.');
          s.returnToConnect=false;
          const session=await window.check();
          if(!session)throw new Error('Your session was not confirmed. Retry sign-in.');
        };
        disposeWelcome=mountLoginScreen(root,s.options,{
          onPassword:async password=>{
            if(!s.options.password_available)throw new Error('Password sign-in is not configured for this Vishnu.');
            s.accessIntent='';
            const result=await api('/access/password/login',{method:'POST',body:JSON.stringify({
              password,name:`${navigator.userAgentData?.platform || navigator.platform || 'Web'} browser`
            })});
            return completeLogin(result);
          },
          onPasskey:async()=>{
            if(!supportedPasskey)throw new Error('No supported, configured passkey is available.');
            s.accessIntent='';
            const start=await api('/access/passkey/login/options',{method:'POST',body:'{}'});
            const credential=await navigator.credentials.get({publicKey:publicKeyRequestOptions(start.public_key)});
            if(!credential)throw new Error('The authenticator was cancelled.');
            const result=await api('/access/passkey/login/complete',{method:'POST',body:JSON.stringify({
              challenge_id:start.challenge_id,credential:serializeAuthentication(credential),
              name:`${navigator.userAgentData?.platform || navigator.platform || 'Web'} browser`
            })});
            return completeLogin(result);
          },
          onRecover:()=>{s.recoveryOrigin='login';renderRecoveryOptions();},
          onManage:()=>{
            s.pendingPostAuthAction='devices';
            return 'Sign in first. Vishnu will open your trusted devices after verification.';
          },
          onBack:()=>{
            s.pendingPostAuthAction='';s.accessIntent='';
            if(s.returnToConnect){s.returnToConnect=false;renderConnect();return;}
            show();render(1);
          },
        });
      }).catch(()=>{
        const root=document.getElementById('vlRoot');
        if(mountId!==welcomeMountId||!root)return;
        root.textContent='Could not load secure sign-in. No authentication state was changed. ';
        const retry=document.createElement('button');
        retry.textContent='Retry';retry.type='button';
        retry.addEventListener('click',()=>renderReturning('login'));
        root.append(retry);
      });
      return;
    }

    const body = view === 'restore' && freshRuntime
      ? `<div class="returning-notice" role="note"><strong>Restore your existing Vishnu</strong><span>Choose the encrypted recovery package and its separate recovery key. Vishnu authenticates both before scheduling any data changes.</span></div><div class="returning-actions returning-form"><label class="returning-password-label" for="restoreArchive">Encrypted recovery package (.vdr)</label><input id="restoreArchive" type="file" accept=".vdr,application/octet-stream"><label class="returning-password-label" for="restoreKeyFile">Encrypted recovery key (.vrk)</label><input id="restoreKeyFile" type="file" accept=".vrk,application/octet-stream"><label class="returning-password-label" for="restorePassphrase">Recovery key passphrase</label><input id="restorePassphrase" type="password" autocomplete="current-password" placeholder="Enter the passphrase used to protect the recovery key">${s.options.local_setup_available ? '' : '<label class="returning-password-label" for="restoreBootstrap">Local runtime setup code</label><input id="restoreBootstrap" type="password" autocomplete="one-time-code" placeholder="Enter the secure setup code">'}<button id="portableRestoreStart" class="genesis-primary" type="button">Verify recovery and continue →</button></div>`
      : view === 'restore'
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
    const title = view === 'restore' && freshRuntime ? 'Restore your <em>Vishnu</em>' : view === 'restore' ? 'Recover owner <em>access</em>' : freshRuntime ? 'Welcome to <em>Vishnu</em>' : 'Welcome back to <em>Vishnu</em>';
    const subtitle = view === 'restore' && freshRuntime ? 'Verify an encrypted recovery package and separate recovery key to restore available data.' : view === 'restore' ? 'Use a saved one-time recovery code to verify ownership and sign in. Recovery codes do not restore backup data.' : freshRuntime ? 'This runtime is ready for a new owner setup or a verified restore.' : 'Sign in to continue with your personal Vishnu.';
    panel.innerHTML = `<main class="genesis-shell returning-shell"><header class="genesis-top"><button class="genesis-back" type="button" data-auth-action="${view === 'restore' ? 'welcome' : 'back'}">← ${view === 'restore' ? 'Back to Welcome' : 'Back to Welcome'}</button><div class="genesis-brand">VISHNU</div><span></span></header><section class="genesis-stage"><div class="genesis-core" role="img" aria-label="Vishnu intelligence core. Ready for owner authentication."></div><div class="genesis-copy"><h1>${title}</h1><p>${subtitle}</p></div>${body}<p id="returningStatus" class="genesis-error" role="status" aria-live="polite"></p></section><footer class="genesis-footer"><a href="#" data-genesis-info="privacy">Privacy</a><span>|</span><a href="#" data-genesis-info="accessibility">Accessibility</a></footer></main>`;
    if (view === 'restore') {
      const notice = document.createElement('div');
      notice.className = 'returning-notice';
      notice.setAttribute('role', 'note');
      if (!freshRuntime) {
        notice.innerHTML = '<strong>A recovery code restores sign-in access only.</strong><span>Enter a saved one-time recovery code to sign in. To recover backup data, use a verified encrypted recovery package and its separate recovery key.</span>';
        panel.querySelector('.genesis-copy').after(notice);
        const label = panel.querySelector('label[for="recoveryCode"]');
        if (label) label.textContent = 'One-time recovery code';
        const submit = panel.querySelector('#recoveryLogin');
        if (submit) submit.textContent = 'Verify owner access';
      }
    }
    if (freshRuntime) {
      const noticeText = panel.querySelector('.returning-notice span');
      if (noticeText) noticeText.textContent = 'Create a new Vishnu here, or restore available data from an encrypted recovery package and its recovery key.';
      const recoveryAction = panel.querySelector('[data-auth-action="restore"]');
      if (recoveryAction) {
        recoveryAction.querySelector('strong').textContent = 'Restore Vishnu';
        recoveryAction.querySelector('small').textContent = 'Verify an encrypted recovery package and key.';
      }
    }
    panel.querySelectorAll('[data-auth-action]').forEach(button => button.addEventListener('click', () => handleReturningAction(button.dataset.authAction)));
    panel.querySelectorAll('[data-genesis-info]').forEach(link => link.addEventListener('click', event => {
      event.preventDefault();
      $('returningStatus').textContent = link.dataset.genesisInfo === 'privacy'
        ? 'Your sign-in stays local to this Vishnu runtime and uses its configured owner security.'
        : 'Keyboard navigation, visible focus and reduced motion are supported.';
    }));
    panel.querySelector('#portableRestoreStart')?.addEventListener('click', submitPortableRestore);
    if (view === 'restore') $('recoveryLogin')?.addEventListener('click', async () => { try { s.accessIntent = ''; const login = await api('/access/recovery/login', { method: 'POST', body: JSON.stringify({ code: $('recoveryCode').value, name: 'Vishnu owner recovery browser' }) }); if (!showRecoveryResult(login.recovery_result)) await check(); } catch (error) { $('returningStatus').textContent = error.message; } });
    if (view === 'google') renderGoogleLogin();
  }
  async function scheduleVerifiedPortableRestore({archive,keyFile,passphrase,bootstrap='',onProgress=()=>{}}){
    // Reuse the preexisting owner's strictly governed staged .vdr/.vrk
    // endpoints for both the legacy restore entry and P1-08.
    if(!s.options.restore_available||s.options.restore_setup_in_progress)
      throw new Error('Encrypted restore requires an eligible uninitialized Vishnu runtime.');
    if(!archive||!keyFile||!archive.name.toLowerCase().endsWith('.vdr')||
       !keyFile.name.toLowerCase().endsWith('.vrk'))
      throw new Error('Choose a valid .vdr recovery package and its separate .vrk key file.');
    if(passphrase.length<12)throw new Error('Enter a recovery-key passphrase of at least 12 characters.');
    if(!s.options.local_setup_available&&bootstrap.length<32)
      throw new Error('Enter the secure setup code provided for this runtime.');
    const upload=async(url,file)=>{
      const response=await fetch(url,{method:'POST',credentials:'same-origin',body:file,
        headers:bootstrap?{'X-Vishnu-Setup-Code':bootstrap}:{}});
      let payload={};try{payload=await response.json();}catch{}
      if(!response.ok)throw new Error(payload.detail||payload.error||'Recovery file verification failed.');
      return payload;
    };
    onProgress('Verifying the encrypted recovery package…');
    const staged=await upload('/iphone/api/first-run/restore/archive',archive);
    onProgress('Verifying the separate recovery key…');
    await upload('/iphone/api/first-run/restore/key?session_id='+encodeURIComponent(staged.session_id),keyFile);
    onProgress('Authenticating the recovery materials and scheduling a safe restore…');
    const scheduled=await api('/first-run/restore/schedule',{method:'POST',
      body:JSON.stringify({session_id:staged.session_id,bootstrap_secret:bootstrap,passphrase})});
    if(scheduled.status!=='restart_required')
      throw new Error('The runtime did not confirm that recovery was scheduled.');
    return scheduled;
  }
  async function submitPortableRestore(event){
    const button=event.currentTarget,status=$('returningStatus');
    const archive=$('restoreArchive')?.files?.[0],keyFile=$('restoreKeyFile')?.files?.[0];
    const passphrase=$('restorePassphrase')?.value||'',bootstrap=$('restoreBootstrap')?.value||'';
    if(button.disabled)return;
    button.disabled=true;
    try{
      const result=await scheduleVerifiedPortableRestore({archive,keyFile,passphrase,bootstrap,
        onProgress:message=>{status.textContent=message;}});
      status.textContent=result.status==='restart_required'
        ? 'Recovery package authenticated. Restart this local Vishnu runtime to restore data, then secure your replacement device.'
        : 'Recovery was not confirmed.';
    }catch(error){
      status.textContent=error?.message||'The recovery package could not be verified. No restoration was confirmed.';
      button.disabled=false;
    }finally{
      // Do not keep backup decryption material in a password input after use.
      if($('restorePassphrase'))$('restorePassphrase').value='';
      if($('restoreBootstrap'))$('restoreBootstrap').value='';
    }
  }
  function renderRestoreSecurity() {
    disposeWelcome();
    ++welcomeMountId;
    panel.setAttribute('aria-label', 'Secure restored Vishnu');
    panel.className = 'genesis';
    panel.innerHTML = `<main class="genesis-shell returning-shell"><header class="genesis-top"><span></span><div class="genesis-brand">VISHNU</div><span></span></header><section class="genesis-stage"><div class="genesis-core" role="img" aria-label="Vishnu recovery complete"></div><div class="genesis-copy"><h1>Secure your restored <em>Vishnu</em></h1><p>Available encrypted data has been restored. Security credentials were not imported. Set a fresh owner password and trust this web device.</p></div><div class="returning-actions returning-form">${s.options.local_setup_available ? '' : '<label class="returning-password-label" for="restoreSecureBootstrap">Local runtime setup code</label><input id="restoreSecureBootstrap" type="password" autocomplete="one-time-code" placeholder="Enter the secure setup code">'}<label class="returning-password-label" for="restoreOwnerPassword">New owner password</label><input id="restoreOwnerPassword" type="password" autocomplete="new-password" placeholder="At least 12 characters"><label class="returning-password-label" for="restoreOwnerPasswordAgain">Confirm new owner password</label><input id="restoreOwnerPasswordAgain" type="password" autocomplete="new-password" placeholder="Repeat the new password"><button id="restoreSecureDevice" class="genesis-primary" type="button">Secure this web device →</button></div><p id="returningStatus" class="genesis-error" role="status" aria-live="polite"></p></section><footer class="genesis-footer"><a href="#" data-genesis-info="privacy">Privacy</a><span>|</span><a href="#" data-genesis-info="accessibility">Accessibility</a></footer></main>`;
    panel.querySelector('#restoreSecureDevice')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      const password = $('restoreOwnerPassword')?.value || '';
      if (password.length < 12) { $('returningStatus').textContent = 'Use a password with at least 12 characters.'; return; }
      if (password !== $('restoreOwnerPasswordAgain')?.value) { $('returningStatus').textContent = 'The passwords do not match.'; return; }
      const bootstrap = $('restoreSecureBootstrap')?.value || '';
      if (!s.options.local_setup_available && bootstrap.length < 32) { $('returningStatus').textContent = 'Enter the secure setup code provided for this Vishnu runtime.'; return; }
      button.disabled = true;
      try {
        const result = await api('/first-run/restore/secure-device', { method: 'POST', body: JSON.stringify({
          bootstrap_secret: bootstrap, password,
          device_name: `${navigator.userAgentData?.platform || navigator.platform || 'Web'} browser`,
        }) });
        s.identityCreated = true;
        s.recoveryCodes = result.recovery_codes || [];
        s.owner = result.identity?.display_name || 'Vishnu Owner';
        render(4);
        $('firstRunCodes').textContent = s.recoveryCodes.join('\n');
        $('firstRunRecoverySaved').checked = false;
      } catch (error) {
        $('returningStatus').textContent = error?.message || 'This web device could not be secured.';
        button.disabled = false;
      }
    });
  }
  function renderRestoreRestartRequired() {
    disposeWelcome();
    ++welcomeMountId;
    panel.setAttribute('aria-label', 'Restart Vishnu to restore data');
    panel.className = 'genesis';
    panel.innerHTML = '<main class="genesis-shell returning-shell"><header class="genesis-top"><span></span><div class="genesis-brand">VISHNU</div><span></span></header><section class="genesis-stage"><div class="genesis-core" role="img" aria-label="Verified Vishnu recovery package"></div><div class="genesis-copy"><h1>Recovery is ready</h1><p>The encrypted package was authenticated. Restart the local Vishnu runtime to restore available data. Your existing security state will not be imported.</p></div><div class="returning-actions"><button type="button" class="genesis-primary" data-restore-check>Check recovery status →</button></div></section><footer class="genesis-footer"><a href="#" data-genesis-info="privacy">Privacy</a><span>|</span><a href="#" data-genesis-info="accessibility">Accessibility</a></footer></main>';
    panel.querySelector('[data-restore-check]')?.addEventListener('click', () => location.reload());
  }
  function renderPendingSetup() {
    disposeWelcome();
    ++welcomeMountId;
    const resumeStep = Number(s.options.setup_resume_step) || 4;
    s.identityCreated = resumeStep >= 4;
    panel.setAttribute('aria-label', 'Continue Vishnu setup');
    panel.className = 'genesis';
    panel.innerHTML = `<main class="genesis-shell returning-shell"><header class="genesis-top"><span></span><div class="genesis-brand">VISHNU</div><span></span></header><section class="genesis-stage"><div class="genesis-core" role="img" aria-label="Vishnu setup in progress"></div><div class="genesis-copy"><h1>Continue your Vishnu setup</h1><p>Your owner account is already created on this local runtime. Continue setup to finish it; do not create another account.</p></div><div class="returning-actions"><button type="button" class="genesis-primary" data-auth-action="resume-setup">Continue setup &rarr;</button></div><p id="returningStatus" class="genesis-error" role="status" aria-live="polite"></p></section><footer class="genesis-footer"><a href="#" data-genesis-info="privacy">Privacy</a><span>|</span><a href="#" data-genesis-info="accessibility">Accessibility</a></footer></main>`;
    panel.querySelector('[data-auth-action="resume-setup"]')?.addEventListener('click', () => {
      s.accessIntent = '';
      s.step = resumeStep;
      show();
      render(resumeStep);
    });
  }
  let joinPollTimer = 0;
  const safeText = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  function renderConnect(join = null) {
    disposeWelcome();
    const mountId=++welcomeMountId;
    if(join?.request_id){
      // Only publicly displayable request metadata is retained. The secret
      // join token remains exclusively in the httpOnly, scoped cookie.
      sessionStorage.setItem('vishnuPendingJoin',JSON.stringify({
        request_id:join.request_id,verification_code:join.verification_code,
        name:join.name,expires_at:join.expires_at
      }));
    }
    panel.className='genesis';
    panel.setAttribute('aria-label','Connect this device to your Vishnu');
    panel.innerHTML='<main class="genesis-shell genesis-screen genesis-security genesis-login genesis-connect" data-step="P1-06"><div id="vcRoot" role="status" aria-live="polite">Loading device connection…</div></main>';
    import('/iphone/genesis-connect.js').then(({mountConnectScreen})=>{
      const root=document.getElementById('vcRoot');
      if(mountId!==welcomeMountId||!root||!root.isConnected)return;
      disposeWelcome=mountConnectScreen(root,join,{
        onBack:async()=>{
          if(join?.request_id){
            // Do not claim a cancelled request before backend confirmation.
            try{
              await api('/access/join/cancel',{method:'POST',body:JSON.stringify({request_id:join.request_id})});
            }catch(error){
              const message=root.querySelector('#vcStatus');
              if(message)message.textContent='Could not cancel the pending request. Ask a trusted device to deny it or wait for expiry. '+(error.message||'');
              return;
            }
            sessionStorage.removeItem('vishnuPendingJoin');
          }
          s.accessIntent='';
          renderReturning('login');
        },
        onAuthenticate:()=>{s.accessIntent='';s.returnToConnect=true;renderReturning('login');},
        onCheck:request_id=>api('/access/join/status',{method:'POST',body:JSON.stringify({request_id})}),
        onComplete:async()=>{
          sessionStorage.removeItem('vishnuPendingJoin');
          s.accessIntent='';s.returnToConnect=false;
          const result=await window.check();
          if(!result)throw new Error('Approval completed but session was not confirmed. Retry verification.');
        },
      });
    }).catch(()=>{
      const root=document.getElementById('vcRoot');
      if(mountId!==welcomeMountId||!root)return;
      root.textContent='Device connection could not load. Your trusted devices have not changed. ';
      const retry=document.createElement('button');retry.type='button';retry.textContent='Retry';
      retry.addEventListener('click',()=>renderConnect(join));root.append(retry);
    });
  }
  function renderJoinPending(join){renderConnect(join);}
  function renderRecoveryOptions(mode='recover_login'){
    disposeWelcome();
    const mountId=++welcomeMountId;
    s.recoveryMode=['recover_login','restore_data','replacement_device'].includes(mode)?mode:'recover_login';
    panel.className='genesis';
    panel.setAttribute('aria-label','Recovery Options');
    panel.innerHTML='<main class="genesis-shell genesis-screen genesis-security genesis-login genesis-recovery-options" data-step="P1-07"><div id="voRoot">Loading recovery options…</div></main>';
    import('/iphone/genesis-recovery-options.js').then(({mountRecoveryOptionsScreen})=>{
      const root=document.getElementById('voRoot');
      if(mountId!==welcomeMountId||!root||!root.isConnected)return;
      disposeWelcome=mountRecoveryOptionsScreen(root,s.options,{
        mode:s.recoveryMode,
        onBack:()=>{s.accessIntent='';if(s.recoveryOrigin==='login')renderReturning('login');else{show();render(1);}},
        onContinue:mode=>{s.recoveryMode=mode;renderRecoveryVerification(mode);},
      });
    }).catch(()=>{
      const root=document.getElementById('voRoot');
      if(mountId!==welcomeMountId||!root)return;
      root.textContent='Recovery options could not load. Nothing has been changed. ';
      const retry=document.createElement('button');retry.type='button';retry.textContent='Retry';
      retry.addEventListener('click',()=>renderRecoveryOptions(s.recoveryMode));root.append(retry);
    });
  }
  function renderRecoveryVerification(mode=s.recoveryMode||'recover_login'){
    if(!['recover_login','restore_data','replacement_device'].includes(mode))return renderRecoveryOptions();
    disposeWelcome();
    const mountId=++welcomeMountId;
    s.recoveryMode=mode;
    panel.className='genesis';
    panel.setAttribute('aria-label','Recovery Verification');
    panel.innerHTML='<main class="genesis-shell genesis-screen genesis-security genesis-login genesis-recovery-options genesis-verification" data-step="P1-08"><div id="voRoot">Loading recovery verification…</div></main>';
    import('/iphone/genesis-verification.js').then(({mountRecoveryVerificationScreen})=>{
      const root=document.getElementById('voRoot');
      if(mountId!==welcomeMountId||!root||!root.isConnected)return;
      disposeWelcome=mountRecoveryVerificationScreen(root,mode,s.options,{
        onBack:()=>renderRecoveryOptions(mode),
        onContinue:()=>renderRecoveryOptions(mode),
        onVerifyCode:async({code,mode})=>{
          // The canonical owner authority validates and consumes the code.
          // Never pass it in the URL, session storage, logs or UI history.
          const result=await api('/access/recovery/login',{method:'POST',
            body:JSON.stringify({code,name:'Vishnu recovery browser'})});
          if(!result?.ok)throw new Error('Vishnu could not verify recovery access.');
          s.accessIntent='';s.recoveryOrigin='';s.recoveryMode='';
          if(mode==='replacement_device')s.pendingPostAuthAction='devices';
          if(result.recovery_result && showRecoveryResult(result.recovery_result))return;
          const session=await window.check();
          if(!session)throw new Error('Recovery was verified, but this browser session has not been confirmed. Retry securely.');
        },
        onRestore:async({archive,keyFile,passphrase,bootstrap})=>
          scheduleVerifiedPortableRestore({archive,keyFile,passphrase,bootstrap}),
      });
    }).catch(()=>{
      const root=document.getElementById('voRoot');
      if(mountId!==welcomeMountId||!root)return;
      root.textContent='Secure recovery verification could not load. Nothing has been changed. ';
      const retry=document.createElement('button');retry.type='button';retry.textContent='Retry';
      retry.addEventListener('click',()=>renderRecoveryVerification(mode));root.append(retry);
    });
  }

  async function handleReturningAction(action) {
    const status = $('returningStatus');
    try {
      if (action === 'back') { s.accessIntent = ''; show(); render(1); return; }
      if (action === 'create') { s.accessIntent = ''; show(); render(1); return; }
      if (action === 'resume-setup') { s.accessIntent = ''; const step = Number(s.options.setup_resume_step) || 4; s.step = step; show(); render(step); return; }
      if (action === 'methods') { renderReturning('methods'); return; }
      if (action === 'welcome') { renderReturning('welcome'); return; }
      if (action === 'restore') {
        s.recoveryOrigin='welcome';
        renderRecoveryOptions();
        return;
      }
      if (action === 'device') { s.pendingPostAuthAction = 'devices'; renderReturning('methods'); $('returningStatus').textContent = 'Verify your identity to continue to trusted devices.'; return; }
      if (action === 'passkey') {
        if (!window.PublicKeyCredential || !navigator.credentials || !s.options.passkey_available) throw new Error('A passkey is not available for this Vishnu on this device. Choose another configured sign-in method.');
        s.accessIntent = '';
        const start = await api('/access/passkey/login/options', { method: 'POST', body: '{}' });
        const {publicKeyRequestOptions,serializeAuthentication}=await import('/iphone/genesis-login.js');
        const credential = await navigator.credentials.get({ publicKey: publicKeyRequestOptions(start.public_key) });
        if(!credential)throw new Error('Authentication was cancelled.');
        const result = await api('/access/passkey/login/complete', { method: 'POST', body: JSON.stringify({ challenge_id: start.challenge_id, credential: serializeAuthentication(credential), name: `${navigator.userAgentData?.platform || 'Web'} browser` }) });
        if (result.status === 'approval_required') { renderJoinPending(result); return; }
        await check();
      }
      if (action === 'password') {
        panel.querySelector('.returning-actions').innerHTML = '<label class="returning-password-label" for="returningPassword">Owner password</label><input id="returningPassword" type="password" autocomplete="current-password" placeholder="Enter your owner password"/><button type="button" class="genesis-primary" data-auth-action="password-submit">Unlock Vishnu →</button><button type="button" class="returning-text-action" data-auth-action="methods">← Other sign-in methods</button>';
        panel.querySelectorAll('[data-auth-action]').forEach(button => button.addEventListener('click', () => handleReturningAction(button.dataset.authAction)));
        $('returningPassword').focus(); return;
      }
      if (action === 'password-submit') {
        s.accessIntent = '';
        const result = await api('/access/password/login', { method: 'POST', body: JSON.stringify({ password: $('returningPassword').value, name: `${navigator.userAgentData?.platform || 'Web'} browser` }) });
        if (result.status === 'approval_required') { renderJoinPending(result); return; }
        await check();
      }
      if (action === 'recovery'){s.recoveryOrigin='login';renderRecoveryOptions();}
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
    disposeWelcome();
    // Uploads are transient previews. Never retain image bytes or object URLs
    // once the first-run surface is dismissed.
    if (s.avatarPreviewUrl) URL.revokeObjectURL(s.avatarPreviewUrl);
    s.avatarPreviewUrl = null;
    s.avatarFile = null;
    ++welcomeMountId;
    document.body.classList.remove('genesis-active'); panel.classList.add('hidden');
    for (const { element, ariaHidden, inert } of priorNavigationState) {
      if (ariaHidden === null) element.removeAttribute('aria-hidden'); else element.setAttribute('aria-hidden', ariaHidden);
      element.inert = inert;
    }
    priorNavigationState = [];
  }

  function showRecoveryResult(result) {
    if (!result || result.identityStatus !== 'completed' ||
        !['completed','partial','pending','not_applicable'].includes(result.dataStatus) ||
        !window.vishnuRecoveryComplete) return false;
    s.recoveryResult = result;
    show();
    window.vishnuRecoveryComplete.mount(panel, result, {
      async continueToHome() {
        const authorized = await originalCheck();
        if (!authorized) {
          panel.classList.remove('hidden');
          const status = await window.vishnuRuntimeAssistant?.probe?.();
          if (window.vishnuRuntimeAssistant && (status?.status === 'offline' || status?.status === 503)) {
            window.vishnuRuntimeAssistant.mount(panel, {
              origin: 'recovery',
              onBack: () => showRecoveryResult(s.recoveryResult),
              onReady: () => showRecoveryResult(s.recoveryResult),
            });
          }
          throw new Error('Vishnu could not verify this trusted browser or runtime. Reconnect and retry.');
        }
        s.recoveryResult = null;
        const destination = s.pendingPostAuthAction;
        s.pendingPostAuthAction = '';
        hide();
        if (destination) {
          // Replacement-device recovery must bring the verified owner directly
          // to trusted-device management, where a lost device can be revoked.
          setTimeout(() => window.vishnuChatBridge?.openModule(destination), 0);
        }
      },
    });
    return true;
  }

  window.vishnuFirstRun = { state: s, render, setError, showLegacy, showRecoveryResult, $,
    showLogin:()=>{show();renderReturning('login');},
    showConnect:join=>{show();renderConnect(join||null);},
    showRecoveryOptions:()=>{show();s.recoveryOrigin='welcome';renderRecoveryOptions();},
    showRecoveryVerification:mode=>{show();renderRecoveryVerification(mode);}
  };
  window.loadAccessOptions = async (...args) => { s.options = await originalLoad(...args) || {}; return s.options; };
  window.check = async (...args) => {
    const result = await originalCheck(...args);
    if (s.recoveryResult) { panel.classList.remove('hidden'); return result; }
    try {
      s.options = await originalLoad() || {};
      if (!result && Object.keys(s.options).length === 0 && window.vishnuRuntimeAssistant) {
        const connection = await window.vishnuRuntimeAssistant.probe();
        if (connection.status === 'offline' || connection.status === 503) {
          show();
          window.vishnuRuntimeAssistant.mount(panel, {
            origin: s.accessIntent || 'welcome',
            onBack: () => { show(); renderReturning(s.accessIntent === 'restore' ? 'restore' : 'welcome'); },
            onReady: () => window.check(),
          });
          return result;
        }
      }
      const pendingJoin = (() => { try { return JSON.parse(sessionStorage.getItem('vishnuPendingJoin') || 'null'); } catch { return null; } })();
      if (s.options.restore_setup_in_progress) { show(); renderRestoreSecurity(); }
      else if (s.options.restore_restart_required) { show(); renderRestoreRestartRequired(); }
      else if (s.options.setup_in_progress && s.options.creation_available) { show(); renderPendingSetup(); }
      else if (pendingJoin && !result) { show(); renderJoinPending(pendingJoin); }
      else if (s.accessIntent === 'join') { show(); renderConnect(); }
      else if (s.accessIntent === 'restore') { show(); s.recoveryOrigin='welcome'; renderRecoveryOptions(); }
      else if (s.options.creation_available || s.options.restore_available) show();
      else if (!result) {
        // No active trusted session on a configured runtime: show the real
        // returning-owner page instead of leaving the prior login hidden.
        show();
        renderReturning('login');
      }
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
