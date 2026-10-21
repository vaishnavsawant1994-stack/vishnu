/* P1-09: verified recovery result screen. No state is persisted to browser storage. */
(() => {
  'use strict';
  if (new URLSearchParams(location.search).get('campaignDemo') === '1') return;

  const icons = {
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    data: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    device: '<path d="M4 4h16v13H4zM8 21h8m-4-4v4"/>',
    check: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    partial: '<circle cx="12" cy="12" r="9"/><path d="M12 7v6m0 4h.01"/>',
    neutral: '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
    shield: '<path d="M12 2 3.7 5.4v5.7c0 5.2 3.4 9 8.3 11 4.9-2 8.3-5.8 8.3-11V5.4z"/><path d="m8.4 12 2.7 2.8 5.2-5.6"/>',
    bulb: '<path d="M8.5 17a6.5 6.5 0 1 1 7 0l-1 2.4h-5zM10 22h4"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c5 6 5 12 0 18M12 3c-5 6-5 12 0 18"/>',
    arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    back: '<path d="M20 12H4m6-6-6 6 6 6"/>',
  };
  const svg = (name, size = 26) =>
    '<svg viewBox="0 0 24 24" width="' + size + '" height="' + size +
    '" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    icons[name] + '</svg>';

  const statusKind = value => ['completed', 'partial', 'pending', 'failed', 'not_applicable'].includes(value)
    ? value : 'pending';
  function statusCopy(key, status, result) {
    if (status === 'completed') {
      if (key === 'identity') return 'Owner profile and sign-in access recovered.';
      if (key === 'data') return Number.isFinite(result.restoredItems)
        ? result.restoredItems + ' backed-up items restored and verified.'
        : 'Verified encrypted backup data is available.';
      return 'This device is secured and ready to continue.';
    }
    const alternatives = {
      identity: {
        partial: 'Some owner access still requires verification.',
        pending: 'Owner verification has not finished.',
        failed: 'Owner recovery could not be verified.',
        not_applicable: 'No identity recovery was requested.',
      },
      data: {
        partial: 'Some backup data could not be verified. Review the recovery details.',
        pending: 'Data recovery is not yet verified.',
        failed: 'The backup could not be restored.',
        not_applicable: 'No encrypted data backup was restored in this recovery.',
      },
      device: {
        partial: 'Device security requires another verification step.',
        pending: 'Device approval is still required.',
        failed: 'This device could not be trusted.',
        not_applicable: 'This device has not been enrolled.',
      },
    };
    return alternatives[key][status];
  }
  function cards(result) {
    return [
      { key: 'identity', icon: 'user', title: 'Identity Restored', status: statusKind(result.identityStatus) },
      { key: 'data', icon: 'data', title: 'Data Available', status: statusKind(result.dataStatus) },
      { key: 'device', icon: 'device', title: 'Device Status', status: statusKind(result.deviceStatus) },
    ];
  }
  function cardMarkup(row, result) {
    const statusText = {
      completed: 'Verified', partial: 'Partial', pending: 'Pending',
      failed: 'Failed', not_applicable: 'Not applicable',
    }[row.status];
    const indicator = row.status === 'completed' ? 'check' : row.status === 'not_applicable' ? 'neutral' : 'partial';
    return '<article class="rc-status-card" data-recovery-card="' + row.key +
      '" data-status="' + row.status + '">' +
      '<span class="rc-card-icon">' + svg(row.icon, 34) + '</span>' +
      '<span class="rc-card-copy"><strong>' + row.title + '</strong><small>' +
      statusCopy(row.key, row.status, result) + '</small></span>' +
      '<span class="rc-indicator" role="img" aria-label="' + statusText + '">' +
      svg(indicator, 34) + '</span></article>';
  }

  // All points live in three-dimensional coordinates. Perspective and depth
  // shading are applied each frame, following the existing PWA neural-core
  // math without loading external rendering libraries or a static PNG.
  // Reuse the same live 3D neural geometry on all Phase 1 result surfaces.
  function animatedCore(canvas) {
    if (!window.vishnuNeuralSphere) return () => {};
    return window.vishnuNeuralSphere.attach(canvas);
  }

  let cleanup = null;
  function mount(panel, result, actions = {}) {
    cleanup?.();
    const rows = cards(result);
    const accessOnly = result.recoveryType === 'owner_access';
    const complete = result.identityStatus === 'completed' && result.deviceStatus === 'completed'
      && (result.dataStatus === 'completed' || result.dataStatus === 'not_applicable');
    const fullyRecovered = complete && !accessOnly && result.dataStatus === 'completed';
    const eyebrow = complete ? 'RECOVERY COMPLETE' : 'RECOVERY NEEDS ATTENTION';
    const heading = fullyRecovered ? 'Your <em>Vishnu</em> Has Been Recovered'
      : complete && accessOnly ? 'Your <em>Vishnu</em> Access Is Restored'
      : 'Your <em>Vishnu</em> Recovery Needs Attention';
    const message = fullyRecovered
      ? 'Your identity, recovery access, and available data have been restored successfully. You can now continue into Vishnu.'
      : complete && accessOnly ? 'Your owner access is restored. No encrypted backup data was restored during this sign-in.'
      : 'Some recovery steps still need attention. Review the verified statuses below before continuing.';
    const canContinue = result.canContinueToHome === true &&
      result.identityStatus === 'completed' && result.deviceStatus === 'completed';
    panel.setAttribute('aria-label', 'P1-09 Recovery Complete');
    panel.className = 'genesis rc-host';
    panel.innerHTML = '<main class="recovery-complete" data-recovery-overall="' + (complete ? 'complete' : 'needs-attention') +
      '" aria-labelledby="rcTitle">' +
      '<header class="rc-header"><div class="rc-brand"><span class="rc-brand-mark" aria-hidden="true"><i></i></span>' +
      '<span><strong>Vishnu 2.0</strong><small>Your Personal AI Companion</small></span></div>' +
      '<div class="rc-header-right"><span class="rc-locale" aria-label="Interface language: English">' +
      svg('globe', 25) + '<span>English</span></span><span class="rc-separator"></span><span class="rc-screen-id">P1-09</span></div></header>' +
      '<div class="rc-grid"><section class="rc-art" aria-label="Animated three-dimensional Vishnu neural core">' +
      '<canvas class="rc-core" id="rcCore" role="img" aria-label="Slowly rotating cyan neural network with connected nodes. Drag to rotate."></canvas>' +
      '<div class="rc-platform" aria-hidden="true"><span></span><span></span><span></span><span></span></div></section>' +
      '<section class="rc-details"><div class="rc-eyebrow">' + eyebrow + '</div>' +
      '<div class="rc-title-row"><div class="rc-shield">' + svg(complete ? 'shield' : 'partial', 86) + '</div>' +
      '<div><h1 id="rcTitle">' + heading + '</h1><p class="rc-description">' + message + '</p></div></div>' +
      '<div class="rc-card-stack">' + rows.map(row => cardMarkup(row, result)).join('') + '</div>' +
      '<section class="rc-next"><span class="rc-next-icon">' + svg('bulb', 37) + '</span>' +
      '<div><h2>Next Steps</h2><ul id="rcNextSteps"></ul></div></section>' +
      '<p class="rc-error" id="rcError" role="alert" aria-live="polite"></p>' +
      '<nav class="rc-actions" aria-label="Recovery navigation"><button class="rc-back" type="button">' +
      svg('back', 21) + ' Back</button><button class="rc-continue" type="button"' +
      (canContinue ? '' : ' disabled') + '>Continue to Vishnu ' + svg('arrow', 23) + '</button></nav>' +
      '</section></div></main>';
    const next = panel.querySelector('#rcNextSteps');
    const points = Array.isArray(result.securityActionsRequired) ? result.securityActionsRequired : [];
    const warnings = Array.isArray(result.warnings) ? result.warnings : [];
    const tips = [...new Set([...points, ...warnings,
      'Reconnect any optional AI providers if needed.',
      canContinue ? 'Continue to Vishnu to finish setup.' : 'Finish the pending security or recovery checks before entering Vishnu.'])].slice(0, 6);
    for (const tip of tips) {
      const li = document.createElement('li');
      li.textContent = String(tip).slice(0, 300);
      next.append(li);
    }
    cleanup = animatedCore(panel.querySelector('#rcCore'));
    const backButton = panel.querySelector('.rc-back');
    backButton.addEventListener('click', () => {
      const summary = panel.querySelector('.rc-eyebrow');
      const detail = panel.querySelector('.rc-description');
      if (summary.textContent !== 'RECOVERY SUMMARY') {
        summary.textContent = 'RECOVERY SUMMARY';
        detail.textContent = 'These statuses come from Vishnu’s verified recovery result. Use Continue to Vishnu to validate your current session and enter Home.';
        backButton.textContent = '← Return to recovery result';
      } else {
        summary.textContent = eyebrow;
        detail.textContent = message;
        backButton.innerHTML = svg('back', 21) + ' Back';
      }
    });
    const continueButton = panel.querySelector('.rc-continue');
    continueButton.addEventListener('click', async () => {
      if (!canContinue || continueButton.disabled) return;
      continueButton.disabled = true;
      continueButton.textContent = 'Verifying your session…';
      panel.querySelector('#rcError').textContent = '';
      try {
        if (typeof actions.continueToHome !== 'function') throw new Error('Trusted-session verification is unavailable.');
        await actions.continueToHome();
        cleanup?.(); cleanup = null;
      } catch (error) {
        panel.querySelector('#rcError').textContent = error?.message || 'Vishnu could not reconnect. Please try again.';
        continueButton.disabled = false;
        continueButton.innerHTML = 'Continue to Vishnu ' + svg('arrow', 23);
      }
    });
    continueButton.setAttribute('aria-describedby', 'rcError');
  }
  window.vishnuRecoveryComplete = { mount, stop() { cleanup?.(); cleanup = null; } };
})();
