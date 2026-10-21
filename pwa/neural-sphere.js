/* Shared Phase 1 Vishnu 3D-coordinate neural sphere.
 * Perspective, depth, node networks, pointer drag, reduced motion and disposal
 * are reused by P1-09 and P1-10. No decorative PNG masquerades as live 3D.
 */
(() => {
  'use strict';
  function attach(canvas) {
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


  window.vishnuNeuralSphere = { attach };
})();
