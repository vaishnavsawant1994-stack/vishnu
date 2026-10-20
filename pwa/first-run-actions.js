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
      if (!/setup session expired|setup is not pending/i.test(error?.message || '')) throw error;
      await api('/first-run/resume', { method: 'POST', body: '{}' });
      return api(path, options);
    }
  }
  flow.setupApi = setupApi;

  async function createIdentity() {
    const firstName = $('firstRunFirstName')?.value.trim();
    if (!firstName) throw new Error('Enter your first name to continue.');
    state.firstName = firstName;
    state.lastName = $('firstRunLastName')?.value.trim() || '';
    state.displayName = $('firstRunDisplayName')?.value.trim() || '';
    state.owner = state.displayName || [state.firstName, state.lastName].filter(Boolean).join(' ');
  }

  async function configureSecurity() {
    // An interrupted setup can resume after owner security already exists.
    // Do not post /first-run/create again; that would be a duplicate-owner
    // attempt. The user may still change the passkey choice before finishing.
    if (state.identityCreated) {
      render(4);
      $('firstRunCodes').textContent = state.recoveryCodes.join('\n') ||
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
    const result = await api('/first-run/create', {
      method: 'POST',
      body: JSON.stringify({
        bootstrap_secret: $('firstRunBootstrap')?.value || '',
        first_name: state.firstName,
        last_name: state.lastName,
        display_name: state.displayName,
        password,
        device_name: `${navigator.userAgentData?.platform || navigator.platform || 'Web'} browser`,
      }),
    });
    state.identityCreated = true;
    state.recoveryCodes = result.recovery_codes || [];
    render(4);
    $('firstRunCodes').textContent = state.recoveryCodes.join('\n');
    if (state.options.setup_recovery_saved) $('firstRunRecoverySaved').checked = true;
  }

  async function createPasskey() {
    if (state.passkeyCreated || state.options.passkey_available) return true;
    if (!window.PublicKeyCredential || !navigator.credentials) return false;
    try {
      const start = await api('/access/passkey/register/options', { method: 'POST', body: '{}' });
      const credential = await navigator.credentials.create({ publicKey: creationOptions(start.public_key) });
      await api('/access/passkey/register/complete', {
        method: 'POST',
        body: JSON.stringify({
          challenge_id: start.challenge_id,
          credential: credentialJson(credential),
          name: 'Vishnu web passkey',
        }),
      });
      state.passkeyCreated = true;
      return true;
    } catch (error) {
      if (error?.name === 'NotAllowedError') return false;
      throw error;
    }
  }

  async function finish() {
    if (!$('firstRunRecoverySaved')?.checked) {
      throw new Error('Save your recovery codes somewhere secure, then confirm to continue.');
    }

    busy(true, 'Finishing secure setup…');
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
