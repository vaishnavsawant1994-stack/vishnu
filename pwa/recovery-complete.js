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
  function animatedCore(canvas) {
    const context = canvas.getContext('2d');
    if (!context) return () => {};
    let seed = 271828;
    const rand = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
    const nodes = [], edges = [];
    const count = 195, golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < count; i++) {
      const y = 1 - (2 * i) / (count - 1), r = Math.sqrt(1 - y * y);
      // Keep a transparent outer shell while giving the network real inner
      // branches and occasional brighter high-activity nodes.
      const inward = i % 4 === 0 ? .36 + rand() * .58 : 1;
      nodes.push({ x: Math.cos(golden * i) * r * inward, y: y * inward,
        z: Math.sin(golden * i) * r * inward,
        size: i % 11 === 0 ? 3.1 + rand() * 1.5 : 1.05 + rand() * 1.3,
        phase: rand() * 7 });
    }
    for (let i = 0; i < count; i++) {
      const near = [];
      for (let j = 0; j < count; j++) {
        if (i === j) continue;
        const a = nodes[i], b = nodes[j];
        const d = Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
        if (d < .44) near.push([j, d]);
      }
      near.sort((a, b) => a[1] - b[1]);
      for (const [j] of near.slice(0, 4)) if (i < j) edges.push([i, j]);
    }
    const specks = Array.from({ length: 110 }, () => ({
      angle: rand() * Math.PI * 2, radius: .95 + rand() * .48,
      size: .4 + rand() * 1.05, phase: rand() * Math.PI * 2,
    }));
    const motion = matchMedia('(prefers-reduced-motion: reduce)');
    let width = 1, height = 1, dpr = 1, raf = 0, yaw = -.25, pitch = .11;
    let drag = null, previous = 0, paused = false;
    const resize = () => {
      const bounds = canvas.getBoundingClientRect();
      width = Math.max(1, bounds.width); height = Math.max(1, bounds.height);
      dpr = Math.min(devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      paint(performance.now());
    };
    const project = (node, scale) => {
      const cy = Math.cos(yaw), sy = Math.sin(yaw);
      const x = node.x * cy - node.z * sy, z = node.x * sy + node.z * cy;
      const ct = Math.cos(pitch), st = Math.sin(pitch);
      const y = node.y * ct - z * st, depth = node.y * st + z * ct;
      const lens = 1 / (1 - depth * .19);
      return { x: width / 2 + x * scale * lens,
        y: height * .49 + y * scale * lens, depth, lens };
    };
    function paint(now) {
      context.clearRect(0, 0, width, height);
      const centerX = width / 2, centerY = height * .49;
      const radius = Math.min(width * .45, height * .46);
      const bloom = context.createRadialGradient(centerX, centerY, radius * .03, centerX, centerY, radius * 1.32);
      bloom.addColorStop(0, 'rgba(0,185,255,.29)');
      bloom.addColorStop(.55, 'rgba(0,95,200,.08)');
      bloom.addColorStop(1, 'rgba(0,95,200,0)');
      context.fillStyle = bloom; context.fillRect(0, 0, width, height);
      // Flecks of ambient neural energy extend only slightly beyond the core.
      for (const fleck of specks) {
        const x = centerX + Math.cos(fleck.angle) * fleck.radius * radius;
        const y = centerY + Math.sin(fleck.angle) * fleck.radius * radius;
        const alpha = motion.matches ? .27 : .2 + .22 * (1 + Math.sin(now * .001 + fleck.phase)) / 2;
        context.fillStyle = 'rgba(16,171,255,' + alpha + ')';
        context.beginPath(); context.arc(x, y, fleck.size, 0, Math.PI * 2); context.fill();
      }
      const projected = nodes.map(node => project(node, radius));
      context.lineWidth = .65;
      for (let i = 0; i < edges.length; i++) {
        const [a, b] = edges[i], p = projected[a], q = projected[b];
        const depth = (p.depth + q.depth) / 2;
        const alpha = .19 + Math.max(0, depth) * .36;
        context.strokeStyle = 'rgba(55,201,255,' + alpha + ')';
        context.beginPath(); context.moveTo(p.x, p.y); context.lineTo(q.x, q.y); context.stroke();
        if (i % 17 === 0) {
          const t = (now * .00011 + i * .061) % 1;
          context.fillStyle = 'rgba(150,244,255,.7)';
          context.beginPath(); context.arc(p.x + (q.x - p.x) * t, p.y + (q.y - p.y) * t, 1.15, 0, Math.PI * 2); context.fill();
        }
      }
      context.strokeStyle = 'rgba(47,198,255,.72)';
      context.lineWidth = 1.1; context.shadowBlur = 15; context.shadowColor = '#05bfff';
      context.beginPath(); context.arc(centerX, centerY, radius, 0, Math.PI * 2); context.stroke();
      for (let i = 0; i < projected.length; i++) {
        const p = projected[i], n = nodes[i];
        const brightness = .58 + Math.max(0, p.depth) * .42;
        const pulse = motion.matches ? 1 : .83 + Math.sin(now * .0014 + n.phase) * .17;
        context.fillStyle = 'rgba(47,214,255,' + brightness + ')';
        context.shadowBlur = n.size > 2 ? 24 : 12;
        context.beginPath(); context.arc(p.x, p.y, n.size * p.lens * pulse, 0, Math.PI * 2); context.fill();
      }
      context.shadowBlur = 0;
      const core = context.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius * .28);
      core.addColorStop(0, 'rgba(170,252,255,.92)');
      core.addColorStop(.21, 'rgba(0,188,255,.52)');
      core.addColorStop(1, 'rgba(0,140,255,0)');
      context.fillStyle = core; context.beginPath(); context.arc(centerX, centerY, radius * .28, 0, Math.PI * 2); context.fill();
    }
    function frame(now) {
      raf = 0;
      if (!canvas.isConnected || paused || motion.matches) return;
      if (now - previous > 28) {
        if (!drag) yaw += Math.min((now - (previous || now)), 60) * (2 * Math.PI / 45000);
        previous = now; paint(now);
      }
      raf = requestAnimationFrame(frame);
    }
    function start() {
      cancelAnimationFrame(raf); raf = 0;
      if (!paused && !motion.matches && canvas.isConnected) raf = requestAnimationFrame(frame);
      else paint(performance.now());
    }
    function visibility() { paused = document.hidden; if (!paused) start(); else cancelAnimationFrame(raf); }
    function down(event) { drag = { x: event.clientX, y: event.clientY }; canvas.setPointerCapture?.(event.pointerId); }
    function move(event) {
      if (!drag) return;
      yaw += (event.clientX - drag.x) * .007;
      pitch = Math.max(-.65, Math.min(.65, pitch + (event.clientY - drag.y) * .005));
      drag = { x: event.clientX, y: event.clientY };
      paint(performance.now());
    }
    function up() { drag = null; }
    canvas.addEventListener('pointerdown', down);
    canvas.addEventListener('pointermove', move);
    canvas.addEventListener('pointerup', up);
    canvas.addEventListener('pointercancel', up);
    document.addEventListener('visibilitychange', visibility);
    motion.addEventListener?.('change', start);
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(resize) : null;
    observer?.observe(canvas);
    window.addEventListener('resize', resize);
    resize(); start();
    return () => {
      cancelAnimationFrame(raf); observer?.disconnect();
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', visibility);
      motion.removeEventListener?.('change', start);
      canvas.removeEventListener('pointerdown', down);
      canvas.removeEventListener('pointermove', move);
      canvas.removeEventListener('pointerup', up);
      canvas.removeEventListener('pointercancel', up);
    };
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
      'Continue to Vishnu to finish setup.'])].slice(0, 6);
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
