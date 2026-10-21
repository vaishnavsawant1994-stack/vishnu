(() => {
  const flow = window.vishnuFirstRun;
  if (!flow) return;
  const { state, render, setError, $ } = flow;
  const busy = (enabled, label) => {
    const button = document.querySelector('[data-genesis-next]');
    if (!button) return;
    if (enabled) {
      if (!button.dataset.idleLabel) button.dataset.idleLabel = button.innerHTML;
      button.disabled = true;
      if (label) button.textContent = label;
      return;
    }
    button.disabled = false;
    if (button.dataset.idleLabel) {
      button.innerHTML = button.dataset.idleLabel;
      delete button.dataset.idleLabel;
    }
  };
  const fail = error => setError(error?.message || 'Vishnu setup could not continue. Try again.');

  async function setupApi(path, options = {}) {
    try {
      return await api(path, options);
    } catch (error) {
      if (/not currently trusted|saved sign-in credential/i.test(error?.message || '')) {
        showSetupDeviceReauth();
        throw error;
      }
      if (!/setup session expired|setup is not pending/i.test(error?.message || '')) throw error;
      await api('/first-run/resume', { method: 'POST', body: '{}' });
      return api(path, options);
    }
  }
  flow.setupApi = setupApi;

  function showSetupDeviceReauth() {
    if (document.querySelector('[data-setup-device-reauth]')) return;
    const content = document.querySelector('.genesis-content');
    if (!content) return;
    const panel = document.createElement('section');
    panel.className = 'genesis-card';
    panel.setAttribute('data-setup-device-reauth', '');
    panel.setAttribute('aria-label', 'Verify owner to restore browser access');
    const title = document.createElement('h3');
    title.textContent = 'Restore this browser’s setup access';
    const note = document.createElement('p');
    note.textContent = 'This browser’s saved trust credential is no longer valid. Verify the owner password you created to securely reconnect it.';
    const password = document.createElement('input');
    password.type = 'password';
    password.autocomplete = 'current-password';
    password.placeholder = 'Owner password';
    password.setAttribute('aria-label', 'Owner password');
    panel.append(title, note);
    if (!state.options.local_setup_available) {
      const bootstrap = document.createElement('input');
      bootstrap.type = 'password';
      bootstrap.autocomplete = 'one-time-code';
      bootstrap.placeholder = 'Secure runtime setup code';
      bootstrap.setAttribute('aria-label', 'Secure runtime setup code');
      panel.append(bootstrap);
      panel.dataset.bootstrapInput = 'required';
    }
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'genesis-primary';
    button.textContent = 'Reconnect this browser';
    button.addEventListener('click', async () => {
      const bootstrap = panel.querySelector('[aria-label="Secure runtime setup code"]')?.value || '';
      if (password.value.length < 12) { setError('Enter your owner password to reconnect this browser.'); return; }
      if (panel.dataset.bootstrapInput && bootstrap.length < 32) { setError('Enter the secure runtime setup code.'); return; }
      button.disabled = true;
      try {
        await api('/first-run/resume', { method: 'POST', body: JSON.stringify({
          password: password.value,
          bootstrap_secret: bootstrap,
          device_name: state.deviceName || `${navigator.userAgentData?.platform || navigator.platform || 'Web'} browser`,
        }) });
        password.value = '';
        panel.remove();
        setError('Browser access restored. Continue setup, or generate fresh recovery codes if needed.');
      } catch (reauthError) {
        setError(reauthError?.message || 'This browser could not be reconnected.');
        button.disabled = false;
      }
    });
    panel.append(password, button);
    content.append(panel);
  }

  async function createIdentity() {
    const firstName = $('firstRunFirstName')?.value.trim();
    if (!firstName) throw new Error('Enter your first name to continue.');
    state.firstName = firstName;
    state.lastName = $('firstRunLastName')?.value.trim() || '';
    state.displayName = $('firstRunDisplayName')?.value.trim() || '';
    state.owner = state.displayName || [state.firstName, state.lastName].filter(Boolean).join(' ');
  }

  async function configureSecurity({ stayOnSecurity = false } = {}) {
    // An interrupted setup can resume after owner security already exists.
    // Do not post /first-run/create again; that would be a duplicate-owner
    // attempt. The user may still change the passkey choice before finishing.
    if (state.identityCreated) {
      if (stayOnSecurity) return;
      render(4);
      const recoveryCodes = Array.isArray(state.recoveryCodes) ? state.recoveryCodes : [];
      $('firstRunCodes').textContent = recoveryCodes.join('\n') ||
        'Recovery codes were already generated. If you did not save them, generate a fresh set below.';
      return;
    }
    const password = $('firstRunPassword')?.value || '';
    const confirmation = $('firstRunPasswordAgain')?.value || '';
    if (!state.options.local_setup_available && ($('firstRunBootstrap')?.value || '').length < 32) {
      throw new Error('Enter the secure setup code provided by your Vishnu runtime administrator.');
    }
    if (password.length < 12) throw new Error('Use an owner password with at least 12 characters.');
    if (password !== confirmation) throw new Error('The passwords do not match.');

    busy(true, 'Securing Vishnu…');
    // Never submit an empty or invalid friendly device name; the backend
    // binds the label to the new DeviceRegistry record without changing trust.
    if (!state.deviceName || !state.deviceName.trim() || state.deviceName.length > 120)
      throw new Error('Enter a device name with no more than 120 characters.');
    const result = await api('/first-run/create', {
      method: 'POST',
      body: JSON.stringify({
        bootstrap_secret: $('firstRunBootstrap')?.value || '',
        first_name: state.firstName,
        last_name: state.lastName,
        display_name: state.displayName,
        password,
        device_name: state.deviceName,
      }),
    });
    state.identityCreated = true;
    state.auth = state.passkeyCreated ? 'passkey' : 'password';
    state.recoveryCodes = result.recovery_codes || [];
    if (stayOnSecurity) busy(false);
    if (!stayOnSecurity) {
      render(4);
      $('firstRunCodes').textContent = state.recoveryCodes.join('\n');
      if (state.options.setup_recovery_saved) $('firstRunRecoverySaved').checked = true;
    }
  }

  const decodeBase64Url = text => {
    const padded = String(text).replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(padded + '='.repeat((4 - padded.length % 4) % 4));
    return Uint8Array.from(raw, c => c.charCodeAt(0));
  };
  const encodeBase64Url = buffer => {
    const data = new Uint8Array(buffer);
    let raw = '';
    for (const byte of data) raw += String.fromCharCode(byte);
    return btoa(raw).split('+').join('-').split('/').join('_').replace(/=+$/, '');
  };
  const creationOptions = options => ({
    ...options,
    challenge: decodeBase64Url(options.challenge),
    user: { ...options.user, id: decodeBase64Url(options.user.id) },
    excludeCredentials: (options.excludeCredentials || []).map(item => ({
      ...item, id: decodeBase64Url(item.id),
    })),
  });
  const credentialJson = credential => ({
    id: credential.id,
    rawId: encodeBase64Url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: encodeBase64Url(credential.response.clientDataJSON),
      attestationObject: encodeBase64Url(credential.response.attestationObject),
      transports: credential.response.getTransports?.() || [],
    },
    clientExtensionResults: credential.getClientExtensionResults?.() || {},
    authenticatorAttachment: credential.authenticatorAttachment || null,
  });

  async function createPasskey() {
    if (state.passkeyCreated) return true;
    if (!window.PublicKeyCredential || !navigator.credentials) return false;
    try {
      const start = await api('/access/passkey/register/options', { method: 'POST', body: '{}' });
      const credential = await navigator.credentials.create({ publicKey: creationOptions(start.public_key) });
      const savedCredential = await api('/access/passkey/register/complete', {
        method: 'POST',
        body: JSON.stringify({
          challenge_id: start.challenge_id,
          credential: credentialJson(credential),
          name: 'Vishnu web passkey',
        }),
      });
      if (!savedCredential || !savedCredential.ok) throw new Error('Passkey registration was not confirmed by Vishnu.');
      state.passkeyCreated = true;
      return true;
    } catch (error) {
      if (error?.name === 'NotAllowedError') return false;
      throw error;
    }
  }

  async function startPasskeySetup({ password, confirmation, bootstrap, deviceName } = {}) {
    if (state.passkeyCreated) return true;
    if (!window.PublicKeyCredential || !navigator.credentials?.create) return false;
    if (!state.identityCreated) {
      // WebAuthn registration is bound to the real owner/device. Create the
      // canonical owner first, but do not navigate away from P1-03 until
      // the user finishes or cancels the platform authenticator ceremony.
      if ((password || '').length < 12 || password !== confirmation)
        throw new Error('Enter a matching owner password of at least 12 characters first.');
      if (!state.options.local_setup_available && (bootstrap || '').length < 32)
        throw new Error('Enter the secure setup code before enrolling a passkey.');
      const passwordField = $('firstRunPassword');
      const confirmField = $('firstRunPasswordAgain');
      if (!passwordField || !confirmField) throw new Error('The security form is unavailable.');
      state.deviceName = deviceName || state.deviceName;
      try {
        await configureSecurity({stayOnSecurity:true});
      } catch(error) {
        busy(false);
        throw error;
      }
      passwordField.value = '';
      confirmField.value = '';
    }
    const result = await createPasskey();
    if (result) state.auth = 'passkey';
    return result;
  }
  flow.startPasskeySetup = startPasskeySetup;

  async function persistOwnerAvatar() {
    const source = state.avatarSource || 'none';
    if (source === 'none' || state.avatarSaved) return;
    let image_b64 = '';
    if (source === 'upload') {
      if (!state.avatarFile) throw new Error('The selected photo is no longer available. Return to Your Identity and select it again.');
      // FileReader keeps raw pixels out of local/session storage; the backend
      // re-encodes validated pixels and binds the file to the canonical owner.
      image_b64 = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(new Error('Cannot read the selected photo. Choose another image.'));
        reader.onload = () => {
          const data = String(reader.result || '');
          const sep = data.indexOf(',');
          if (sep < 0) reject(new Error('The selected photo is invalid.'));
          else resolve(data.slice(sep + 1));
        };
        reader.readAsDataURL(state.avatarFile);
      });
    }
    await setupApi('/first-run/avatar', { method: 'PUT', body: JSON.stringify({
      source, preset_id: source === 'preset' ? (state.avatarId || '') : '', image_b64,
    })});
    state.avatarSaved = true;
  }

  async function finish() {
    if (!$('firstRunRecoverySaved')?.checked) {
      throw new Error('Save your recovery codes somewhere secure, then confirm to continue.');
    }

    busy(true, 'Finishing secure setup…');
    // Avatar persistence is optional, but a selected picture must not be
    // silently discarded or announced as saved when the upload fails.
    await persistOwnerAvatar();
    await setupApi('/first-run/recovery-saved', {
      method: 'POST', body: JSON.stringify({ saved: true }),
    });

    let passkeyCreated = false;
    if (state.auth === 'passkey') {
      passkeyCreated = await createPasskey();
      if (!passkeyCreated) {
        throw new Error('A passkey was not created. Try again, or choose Password only and continue.');
      }
    }

    // Safe defaults are applied through existing authorities, not shown as
    // extra onboarding pages: no provider connection and no data sync.
    await setupApi('/first-run/model', {
      method: 'POST', body: JSON.stringify({ provider_id: 'skip' }),
    });
    await setupApi('/first-run/data-policy', {
      method: 'PUT', body: JSON.stringify({ default_policy: 'device_only' }),
    });
    await setupApi('/first-run/complete', {
      method: 'POST',
      body: JSON.stringify({
        recovery_saved: true,
        privacy_mode: 'local_only',
        autonomy_mode: 'ask',
        passkey_unavailable_confirmed: !passkeyCreated,
      }),
    });
    setError('Your Vishnu is ready. Enter to start using it.');
    setTimeout(() => window.check(), 700);
  }

  window.addEventListener('vishnu:genesis-next', async event => {
    setError('');
    try {
      if (event.detail.step === 2) {
        await createIdentity();
        render(3);
      } else if (event.detail.step === 3) {
        await configureSecurity();
      } else if (event.detail.step === 4) {
        await finish();
      }
    } catch (error) {
      fail(error);
      busy(false);
    }
  });
})();
