/* Vishnu P1-01: standalone, deterministic WebGL neural network; no external runtime or provider dependencies. */
export function mountNeuralSphere(canvas) {
  if (!canvas) return () => {};
  const host = canvas.parentElement;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let gl;
  try { gl = canvas.getContext('webgl', { alpha: true, antialias: true, depth: false, premultipliedAlpha: false, powerPreference: 'low-power' }); } catch {}
  if (!gl) {
    host.classList.add('vw-static-fallback');
    return () => host.classList.remove('vw-static-fallback');
  }
  const vertex = `
    attribute vec4 a_point;
    uniform vec2 u_rotation;
    uniform float u_aspect;
    uniform float u_ratio;
    uniform float u_scale;
    uniform float u_time;
    varying float v_depth;
    varying float v_phase;
    void main() {
      float cy = cos(u_rotation.x), sy = sin(u_rotation.x);
      float cx = cos(u_rotation.y), sx = sin(u_rotation.y);
      vec3 a = vec3(cy * a_point.x + sy * a_point.z, a_point.y, -sy * a_point.x + cy * a_point.z);
      vec3 p = vec3(a.x, cx * a.y - sx * a.z, sx * a.y + cx * a.z);
      float w = 2.9 - p.z * 0.38;
      gl_Position = vec4(p.x * 2.60 / u_aspect, p.y * 2.60, 0.0, w);
      v_depth = p.z;
      v_phase = a_point.w * 0.57 + a_point.x * 5.0 + a_point.y * 3.0;
      gl_PointSize = max(1.0, a_point.w * u_ratio * u_scale * (2.9 / w));
    }
  `;
  const fragment = `
    precision mediump float;
    uniform float u_mode;
    uniform float u_time;
    varying float v_depth;
    varying float v_phase;
    void main() {
      float front = clamp((v_depth + 1.0) * 0.5, 0.0, 1.0);
      if (u_mode < 0.5) {
        gl_FragColor = vec4(0.07, 0.66 + 0.20 * front, 1.0, 0.19 + front * 0.26);
      } else {
        vec2 uv = gl_PointCoord - vec2(0.5);
        float radius = length(uv);
        if (radius > 0.5) discard;
        if (u_mode > 1.5) {
          float halo = exp(-14.0 * radius * radius) * (0.31 + 0.23 * front);
          gl_FragColor = vec4(0.12, 0.74, 1.0, halo);
          return;
        }
        float core = smoothstep(0.29, 0.015, radius);
        float bloom = smoothstep(0.50, 0.02, radius) * 0.38;
        float pulse = 0.90 + 0.10 * sin(u_time * 1.4 + v_phase);
        float alpha = min(1.0, (core + bloom) * pulse * (0.68 + 0.32 * front));
        gl_FragColor = vec4(0.22 + 0.70 * core, 0.73 + 0.26 * core, 1.0, alpha);
      }
    }
  `;
  const makeShader = (type, source) => {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const message = gl.getShaderInfoLog(shader);
      gl.deleteShader(shader);
      throw new Error(message || 'WebGL shader could not compile');
    }
    return shader;
  };
  let program, lineBuffer, pointBuffer, signalBuffer, vertexShader, fragmentShader;
  try {
    vertexShader = makeShader(gl.VERTEX_SHADER, vertex);
    fragmentShader = makeShader(gl.FRAGMENT_SHADER, fragment);
    program = gl.createProgram();
    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
  } catch {
    if (program) gl.deleteProgram(program);
    if (vertexShader) gl.deleteShader(vertexShader);
    if (fragmentShader) gl.deleteShader(fragmentShader);
    host.classList.add('vw-static-fallback');
    return () => host.classList.remove('vw-static-fallback');
  }
  let seed = 32471;
  const random = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
  const nodes = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  const shellCount = 170;
  for (let i = 0; i < shellCount; i++) {
    const y = 1 - 2 * (i + 0.5) / shellCount;
    const radius = Math.sqrt(1 - y * y);
    const angle = i * golden + (random() - 0.5) * 0.14;
    nodes.push([Math.cos(angle) * radius, y, Math.sin(angle) * radius, i % 11 === 0 ? 16 : 6.5 + random() * 5]);
  }
  // Populate the sphere's *volume*, not just its outer silhouette.
  for (let i = 0; i < 50; i++) {
    const y = random() * 2 - 1;
    const angle = random() * Math.PI * 2;
    const radius = 0.12 + 0.78 * random();
    const flat = Math.sqrt(1 - y * y) * radius;
    nodes.push([Math.cos(angle) * flat, y * radius, Math.sin(angle) * flat, i % 9 === 0 ? 12 : 5.8 + random() * 5]);
  }
  nodes.push([0.06, 0.02, 0.17, 19]);
  const pairs = [];
  const seen = new Set();
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i];
    const neighbors = [];
    for (let j = 0; j < nodes.length; j++) {
      if (i === j) continue;
      const b = nodes[j];
      const distance = (a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2;
      neighbors.push([distance,j]);
    }
    neighbors.sort((a,b) => a[0]-b[0]);
    for (const [,j] of neighbors.slice(0,i < shellCount ? 3 : 3)) {
      const key = i < j ? i + ':' + j : j + ':' + i;
      if (seen.has(key)) continue;
      seen.add(key);
      pairs.push([i,j]);
    }
  }
  const edges = new Float32Array(pairs.length * 8);
  pairs.forEach(([a,b],i) => {
    edges.set([nodes[a][0],nodes[a][1],nodes[a][2],1, nodes[b][0],nodes[b][1],nodes[b][2],1],i*8);
  });
  const points = new Float32Array(nodes.flat());
  const pulses = new Float32Array(24 * 4);
  const buffer = (data, usage) => {
    const item = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, item);
    gl.bufferData(gl.ARRAY_BUFFER, data, usage);
    return item;
  };
  lineBuffer = buffer(edges, gl.STATIC_DRAW);
  pointBuffer = buffer(points, gl.STATIC_DRAW);
  signalBuffer = buffer(pulses, gl.DYNAMIC_DRAW);
  const attribute = gl.getAttribLocation(program, 'a_point');
  const rotation = gl.getUniformLocation(program, 'u_rotation');
  const aspect = gl.getUniformLocation(program, 'u_aspect');
  const ratio = gl.getUniformLocation(program, 'u_ratio');
  const pointScale = gl.getUniformLocation(program, 'u_scale');
  const mode = gl.getUniformLocation(program, 'u_mode');
  const time = gl.getUniformLocation(program, 'u_time');
  gl.useProgram(program);
  gl.enableVertexAttribArray(attribute);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
  let yaw = 0.2, pitch = 0.17, width = 0, height = 0;
  let frame = 0, lastTime = 0, stopped = false, visible = true, drag = null;
  const updateSize = () => {
    const rect = canvas.getBoundingClientRect();
    width = Math.max(1, Math.round(rect.width));
    height = Math.max(1, Math.round(rect.height));
    const pixelRatio = Math.min(window.devicePixelRatio || 1, width < 300 ? 1.5 : 2);
    const pw = Math.round(width * pixelRatio), ph = Math.round(height * pixelRatio);
    if (canvas.width !== pw || canvas.height !== ph) { canvas.width = pw; canvas.height = ph; gl.viewport(0, 0, pw, ph); }
    gl.uniform1f(aspect, pw / ph);
    gl.uniform1f(ratio, pixelRatio);
  };
  const draw = (timestamp) => {
    frame = 0;
    if (stopped || document.hidden || !visible) return;
    updateSize();
    const now = timestamp / 1000;
    if (!reducedMotion.matches && !drag && lastTime) yaw += Math.min(0.05, now-lastTime) * (Math.PI * 2 / 52);
    lastTime = now;
    gl.clearColor(0,0,0,0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(rotation, yaw, pitch);
    gl.uniform1f(time, now);
    const renderBuffer = (item, count, kind, drawMode) => {
      gl.bindBuffer(gl.ARRAY_BUFFER, item);
      gl.vertexAttribPointer(attribute, 4, gl.FLOAT, false, 16, 0);
      gl.uniform1f(mode, kind);
      gl.uniform1f(pointScale, (kind > 1.5 ? 3.10 : 1.0) * (width < 130 ? Math.max(.22, width / 310) : 1.0));
      gl.drawArrays(drawMode, 0, count);
    };
    renderBuffer(lineBuffer, edges.length / 4, 0, gl.LINES);
    renderBuffer(pointBuffer, nodes.length, 2, gl.POINTS);
    renderBuffer(pointBuffer, nodes.length, 1, gl.POINTS);
    if (!reducedMotion.matches) {
      for (let i = 0; i < 24; i++) {
        const [a,b] = pairs[(i * 41) % pairs.length];
        const t = (now * (0.11 + (i%5)*0.018) + i * 0.173) % 1;
        const j = i * 4;
        pulses[j] = nodes[a][0] + (nodes[b][0]-nodes[a][0])*t;
        pulses[j+1] = nodes[a][1] + (nodes[b][1]-nodes[a][1])*t;
        pulses[j+2] = nodes[a][2] + (nodes[b][2]-nodes[a][2])*t;
        pulses[j+3] = 5;
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, signalBuffer);
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, pulses);
      renderBuffer(signalBuffer, 24, 1, gl.POINTS);
      frame = requestAnimationFrame(draw);
    }
  };
  const restart = () => { cancelAnimationFrame(frame); lastTime=0; if (!stopped && !document.hidden && visible) frame=requestAnimationFrame(draw); };
  const onStart = e => { if(e.button !== undefined && e.button !== 0) return; drag={id:e.pointerId,x:e.clientX,y:e.clientY}; canvas.setPointerCapture(e.pointerId); };
  const onMove = e => {
    if (!drag || drag.id !== e.pointerId) return;
    yaw += (e.clientX - drag.x) * 0.006;
    pitch = Math.max(-0.8, Math.min(0.8, pitch + (e.clientY-drag.y)*0.004));
    drag.x=e.clientX; drag.y=e.clientY;
    if (reducedMotion.matches) restart();
  };
  const onEnd = e => { if (drag && drag.id===e.pointerId) { drag=null; if(canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId); } };
  const onVisibility = () => restart();
  const onMotionChange = () => restart();
  const onContextLost = event => { event.preventDefault(); cancelAnimationFrame(frame); host.classList.add('vw-static-fallback'); };
  const resizeObserver = 'ResizeObserver' in window ? new ResizeObserver(restart) : null;
  resizeObserver?.observe(canvas);
  const intersectionObserver = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {visible=entries[0]?.isIntersecting ?? true;restart();}) : null;
  intersectionObserver?.observe(canvas);
  canvas.addEventListener('pointerdown',onStart);
  canvas.addEventListener('pointermove',onMove);
  canvas.addEventListener('pointerup',onEnd);
  canvas.addEventListener('pointercancel',onEnd);
  canvas.addEventListener('webglcontextlost',onContextLost);
  window.addEventListener('resize',restart);
  document.addEventListener('visibilitychange',onVisibility);
  reducedMotion.addEventListener?.('change',onMotionChange);
  restart();
  return () => {
    stopped = true;
    cancelAnimationFrame(frame);
    resizeObserver?.disconnect();
    intersectionObserver?.disconnect();
    canvas.removeEventListener('pointerdown',onStart);
    canvas.removeEventListener('pointermove',onMove);
    canvas.removeEventListener('pointerup',onEnd);
    canvas.removeEventListener('pointercancel',onEnd);
    canvas.removeEventListener('webglcontextlost',onContextLost);
    window.removeEventListener('resize',restart);
    document.removeEventListener('visibilitychange',onVisibility);
    reducedMotion.removeEventListener?.('change',onMotionChange);
    gl.deleteBuffer(lineBuffer);
    gl.deleteBuffer(pointBuffer);
    gl.deleteBuffer(signalBuffer);
    gl.deleteProgram(program);
    gl.deleteShader(vertexShader);
    gl.deleteShader(fragmentShader);
    host.classList.remove('vw-static-fallback');
  };
}
