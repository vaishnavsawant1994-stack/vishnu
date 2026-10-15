const $ = id => document.getElementById(id);
const pages = [...document.querySelectorAll('.page')];
const tabs = [...document.querySelectorAll('nav button')];
const state = {
  origin: sessionStorage.getItem('pai.origin') || '',
  deviceId: sessionStorage.getItem('pai.deviceId') || '',
  deviceToken: sessionStorage.getItem('pai.deviceToken') || '',
  sessionToken: sessionStorage.getItem('pai.sessionToken') || '',
  expiresAt: Number(sessionStorage.getItem('pai.expiresAt') || 0),
  eventsAbort: null,
  visionStream: null,
  visionTimer: null,
};

function setStatus(text, ok = false) {
  $('runtime-status').textContent = `● ${text}`;
  $('runtime-status').classList.toggle('offline', !ok);
}

function applyRuntime(s = {}) {
  const stopped = !!s.emergency_stop || !!s.enabled && s.event === 'emergency.stop';
  setStatus(stopped ? 'Stopped' : 'Connected', !stopped);
  if (s.state) {
    $('runtime-state').textContent = s.state;
    $('core-state').textContent = `Runtime ${s.state}`;
  }
  if (stopped) $('core-state').textContent = 'Emergency stop active';
  $('device-state').textContent = 'Paired';
  $('security-state').textContent = stopped ? 'STOPPED' : 'Protected';
  $('session-state').textContent = 'Active';
  if (s.event === 'approval.required') {
    $('approval-count').textContent = '1';
    $('approval-copy').textContent = `${s.tool || 'Action'} requires approval.`;
  }
  if (s.event === 'approval.approved' || s.event === 'approval.rejected') {
    $('approval-count').textContent = '0';
    $('approval-copy').textContent = 'No pending approvals.';
  }
}

function normOrigin(v) { return (v || '').trim().replace(/\/$/, ''); }
function nonce() {
  const b = new Uint8Array(18);
  crypto.getRandomValues(b);
  return [...b].map(x => x.toString(16).padStart(2, '0')).join('');
}
function headers(extra = {}) {
  return {
    'Content-Type': 'application/json',
    ...(state.sessionToken ? { Authorization: `Bearer ${state.sessionToken}` } : {}),
    ...extra,
  };
}

async function call(path, opts = {}) {
  if (!state.origin) throw new Error('Runtime origin not configured');
  const r = await fetch(state.origin + path, { ...opts, headers: { ...headers(), ...(opts.headers || {}) } });
  let body = {};
  try { body = await r.json(); } catch {}
  if (!r.ok) throw new Error(body.detail || body.error || `HTTP ${r.status}`);
  return body;
}

async function ensureSession() {
  if (state.sessionToken && Date.now() / 1000 < state.expiresAt - 30) return true;
  if (!state.deviceId || !state.deviceToken) return false;
  const body = await call('/cloud/session', { method: 'POST', body: JSON.stringify({ device_id: state.deviceId, device_token: state.deviceToken }) });
  state.sessionToken = body.session_token;
  state.expiresAt = body.expires_at;
  sessionStorage.setItem('pai.sessionToken', state.sessionToken);
  sessionStorage.setItem('pai.expiresAt', String(state.expiresAt));
  $('session-state').textContent = 'Active';
  startEvents();
  return true;
}

async function refreshStatus() {
  try {
    if (!await ensureSession()) { setStatus('Unpaired'); return; }
    applyRuntime(await call('/cloud/status'));
  } catch {
    setStatus('Offline');
    $('runtime-state').textContent = 'Offline';
  }
}

async function startEvents() {
  if (!state.origin || !state.sessionToken || state.eventsAbort) return;
  const ctrl = new AbortController();
  state.eventsAbort = ctrl;
  try {
    const r = await fetch(state.origin + '/cloud/events', { headers: { Authorization: `Bearer ${state.sessionToken}` }, signal: ctrl.signal });
    if (!r.ok || !r.body) throw new Error('event stream unavailable');
    const reader = r.body.getReader(), decoder = new TextDecoder();
    let buf = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const frame = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const line = frame.split('\n').find(x => x.startsWith('data: '));
        if (line) { try { applyRuntime(JSON.parse(line.slice(6))); } catch {} }
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') setTimeout(() => { state.eventsAbort = null; startEvents(); }, 3000);
  } finally {
    if (state.eventsAbort === ctrl) state.eventsAbort = null;
  }
}

tabs.forEach(t => t.addEventListener('click', () => {
  tabs.forEach(x => x.classList.toggle('active', x === t));
  pages.forEach(p => p.classList.toggle('active', p.id === t.dataset.page));
}));

$('runtime-origin').value = state.origin;
$('pair').addEventListener('submit', async e => {
  e.preventDefault();
  const origin = normOrigin($('runtime-origin').value);
  const token = $('pair-token').value.trim();
  const code = $('pair-code').value.trim();
  if (!origin || !token || !code) return;
  $('pair-message').textContent = 'Pairing…';
  try {
    if (state.eventsAbort) { state.eventsAbort.abort(); state.eventsAbort = null; }
    stopVision('Camera off');
    state.origin = origin;
    sessionStorage.setItem('pai.origin', origin);
    const r = await fetch(origin + '/pair/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, code, name: 'Vishnu Web Companion', platform: 'web' }),
    });
    const body = await r.json();
    if (!r.ok) throw new Error(body.detail || 'Pairing failed');
    state.deviceId = body.device.id;
    state.deviceToken = body.bearer_token;
    state.sessionToken = '';
    sessionStorage.setItem('pai.deviceId', state.deviceId);
    sessionStorage.setItem('pai.deviceToken', state.deviceToken);
    sessionStorage.removeItem('pai.sessionToken');
    $('pair-token').value = '';
    $('pair-code').value = '';
    await ensureSession();
    $('pair-message').textContent = 'Paired securely for this browser session.';
    await refreshStatus();
  } catch (err) {
    $('pair-message').textContent = err.message;
    setStatus('Pairing failed');
  }
});

$('ask').addEventListener('submit', async e => {
  e.preventDefault();
  const input = $('prompt');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  $('reply').hidden = false;
  $('reply').textContent = 'Thinking…';
  try {
    if (!await ensureSession()) throw new Error('Pair a secure runtime first');
    const body = await call('/cloud/command', { method: 'POST', body: JSON.stringify({ text, nonce: nonce() }) });
    if (body.approval_required) {
      $('approval-count').textContent = '1';
      $('approval-copy').textContent = `${body.tool} requires approval.`;
      $('reply').innerHTML = `<b>Approval required</b><p>${body.description || body.tool}</p><div class="row"><button class="action" id="approve-now">Approve once</button><button class="danger" id="reject-now">Reject</button></div>`;
      const decide = async decision => {
        const x = await call('/cloud/approval', { method: 'POST', body: JSON.stringify({ approval_id: body.approval_id, decision, nonce: nonce() }) });
        $('reply').textContent = x.reply || `Action ${decision}d.`;
        $('approval-count').textContent = '0';
        $('approval-copy').textContent = 'No pending approvals.';
      };
      $('approve-now').onclick = () => decide('approve').catch(x => $('reply').textContent = x.message);
      $('reject-now').onclick = () => decide('reject').catch(x => $('reply').textContent = x.message);
    } else $('reply').textContent = body.reply || 'Completed.';
  } catch (err) { $('reply').textContent = err.message; }
});

$('memory-search').addEventListener('submit', async e => {
  e.preventDefault();
  const q = $('memory-query').value.trim();
  try {
    if (!await ensureSession()) throw new Error('Pair a secure runtime first');
    const body = await call('/cloud/memory/search', { method: 'POST', body: JSON.stringify({ query: q, include_sensitive: false }) });
    $('memory-results').innerHTML = '';
    if (!body.results.length) { $('memory-results').textContent = 'No permitted memories found.'; return; }
    body.results.forEach(m => {
      const p = document.createElement('p');
      const b = document.createElement('b');
      b.textContent = m.subject || m.type || 'Memory';
      p.append(b, document.createElement('br'), document.createTextNode(m.content || ''));
      $('memory-results').appendChild(p);
    });
  } catch (err) { $('memory-results').textContent = err.message; }
});

async function emergency(enabled) {
  const owner = $('owner-secret').value;
  try {
    if (!state.origin) throw new Error('Runtime origin not configured');
    const r = await fetch(state.origin + '/cloud/emergency-stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Personal-AI-Owner-Key': owner },
      body: JSON.stringify({ enabled }),
    });
    const body = await r.json();
    if (!r.ok) throw new Error(body.detail || body.error || 'Emergency control failed');
    $('owner-secret').value = '';
    if (enabled) stopVision('Camera stopped by emergency control');
    await refreshStatus();
  } catch (err) { $('owner-secret').value = ''; alert(err.message); }
}
$('stop').addEventListener('click', () => emergency(true));
$('resume').addEventListener('click', () => emergency(false));

function setVisionUI(active, text) {
  $('vision-indicator').textContent = active ? '● Camera active' : 'Camera off';
  $('vision-status').textContent = text;
  $('vision-preview').style.display = active ? 'block' : 'none';
  $('vision-start').disabled = active;
  $('vision-analyze').disabled = !active;
  $('vision-stop').disabled = !active;
  $('vision-facing').disabled = active;
}

function stopVision(reason = 'Camera off') {
  if (state.visionTimer) clearTimeout(state.visionTimer);
  state.visionTimer = null;
  if (state.visionStream) state.visionStream.getTracks().forEach(track => track.stop());
  state.visionStream = null;
  $('vision-preview').srcObject = null;
  setVisionUI(false, reason);
}

async function startVision() {
  $('vision-result').textContent = '';
  if (!state.deviceId || !state.deviceToken) { $('vision-result').textContent = 'Pair this browser with Vishnu first.'; return; }
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    $('vision-result').textContent = 'Camera access requires HTTPS (or localhost) and a supported browser.';
    return;
  }
  stopVision('Requesting camera permission…');
  try {
    const facingMode = $('vision-facing').value;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: facingMode } } });
    state.visionStream = stream;
    $('vision-preview').srcObject = stream;
    await $('vision-preview').play();
    setVisionUI(true, 'Vishnu Vision is active for this browser only. It stops automatically after 5 minutes or when the page is hidden.');
    state.visionTimer = setTimeout(() => stopVision('Vision session expired after 5 minutes.'), 5 * 60 * 1000);
  } catch (err) {
    stopVision('Camera off');
    $('vision-result').textContent = err?.name === 'NotAllowedError' ? 'Camera permission was not granted.' : 'This camera could not be opened.';
  }
}

async function analyzeVision() {
  const stream = state.visionStream;
  const video = $('vision-preview');
  if (!stream || !video.videoWidth || !video.videoHeight) { $('vision-result').textContent = 'Start the camera first.'; return; }
  if (!state.origin || !state.deviceId || !state.deviceToken) { $('vision-result').textContent = 'Pair this browser with Vishnu first.'; return; }
  $('vision-analyze').disabled = true;
  $('vision-result').textContent = 'Analyzing one snapshot…';
  const maxWidth = 1024;
  const scale = Math.min(1, maxWidth / video.videoWidth);
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
  canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
  const ctx = canvas.getContext('2d', { alpha: false });
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL('image/jpeg', 0.72);
  canvas.width = 1;
  canvas.height = 1;
  try {
    if (dataUrl.length > 2_050_000) throw new Error('Snapshot is too large. Move closer or reduce camera resolution.');
    const r = await fetch(state.origin + '/owner/ai/sensorium/camera/browser/snapshot', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${state.deviceToken}`,
        'X-Device-Id': state.deviceId,
      },
      body: JSON.stringify({ data_url: dataUrl, question: $('vision-question').value.trim() || 'Describe what you can see.' }),
    });
    let body = {};
    try { body = await r.json(); } catch {}
    if (!r.ok) throw new Error(body.detail || body.error || `Vision request failed (${r.status})`);
    $('vision-result').textContent = body.analysis || 'Vishnu returned no visual description.';
  } catch (err) {
    $('vision-result').textContent = err.message || 'Vision analysis failed.';
  } finally {
    $('vision-analyze').disabled = !state.visionStream;
  }
}

$('vision-start').addEventListener('click', startVision);
$('vision-analyze').addEventListener('click', analyzeVision);
$('vision-stop').addEventListener('click', () => stopVision('Camera stopped by you.'));
document.addEventListener('visibilitychange', () => { if (document.hidden) stopVision('Camera stopped because the page was hidden.'); });
window.addEventListener('pagehide', () => stopVision('Camera stopped.'));

refreshStatus();
startEvents();
setInterval(refreshStatus, 60000);
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
