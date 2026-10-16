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
  visionResource: null,
  visionSensorSession: null,
  liveSession: null,
  liveInterval: null,
  liveDeadline: 0,
  liveFingerprint: null,
  voiceStream: null,
  recognition: null,
};

const MIN_LIVE_BATTERY_PERCENT = 15;

function setStatus(text, ok = false) {
  $('runtime-status').textContent = `● ${text}`;
  $('runtime-status').classList.toggle('offline', !ok);
}
function applyRuntime(s = {}) {
  const stopped = !!s.emergency_stop || !!s.enabled && s.event === 'emergency.stop';
  setStatus(stopped ? 'Stopped' : 'Connected', !stopped);
  if (s.state) { $('runtime-state').textContent = s.state; $('core-state').textContent = `Runtime ${s.state}`; }
  if (stopped) $('core-state').textContent = 'Emergency stop active';
  $('device-state').textContent = 'Paired'; $('security-state').textContent = stopped ? 'STOPPED' : 'Protected'; $('session-state').textContent = 'Active';
  if (s.event === 'approval.required') { $('approval-count').textContent = '1'; $('approval-copy').textContent = `${s.tool || 'Action'} requires approval.`; }
  if (s.event === 'approval.approved' || s.event === 'approval.rejected') { $('approval-count').textContent = '0'; $('approval-copy').textContent = 'No pending approvals.'; }
}
function normOrigin(v) { return (v || '').trim().replace(/\/$/, ''); }
function nonce() { const b = new Uint8Array(18); crypto.getRandomValues(b); return [...b].map(x => x.toString(16).padStart(2, '0')).join(''); }
function headers(extra = {}) { return {'Content-Type': 'application/json', ...(state.sessionToken ? {Authorization: `Bearer ${state.sessionToken}`} : {}), ...extra}; }
function deviceHeaders() { return {'Content-Type':'application/json', Authorization:`Bearer ${state.deviceToken}`, 'X-Device-Id':state.deviceId}; }
async function call(path, opts = {}) {
  if (!state.origin) throw new Error('Runtime origin not configured');
  const r = await fetch(state.origin + path, {...opts, headers:{...headers(), ...(opts.headers || {})}});
  let body = {}; try { body = await r.json(); } catch {}
  if (!r.ok) throw new Error(body.detail || body.error || `HTTP ${r.status}`); return body;
}
async function sensorCall(path, opts = {}) {
  if (!state.origin || !state.deviceId || !state.deviceToken) throw new Error('Pair this browser with Vishnu first.');
  const r = await fetch(state.origin + '/owner/ai/sensorium/camera' + path, {...opts, headers:{...deviceHeaders(), ...(opts.headers || {})}});
  let body = {}; try { body = await r.json(); } catch {}
  if (!r.ok) throw new Error(body.detail || body.error || `Sensorium request failed (${r.status})`); return body;
}
async function ensureSession() {
  if (state.sessionToken && Date.now()/1000 < state.expiresAt - 30) return true;
  if (!state.deviceId || !state.deviceToken) return false;
  const body = await call('/cloud/session', {method:'POST', body:JSON.stringify({device_id:state.deviceId, device_token:state.deviceToken})});
  state.sessionToken = body.session_token; state.expiresAt = body.expires_at;
  sessionStorage.setItem('pai.sessionToken', state.sessionToken); sessionStorage.setItem('pai.expiresAt', String(state.expiresAt)); $('session-state').textContent='Active'; startEvents(); return true;
}
async function refreshStatus() { try { if (!await ensureSession()) {setStatus('Unpaired');return;} applyRuntime(await call('/cloud/status')); } catch { setStatus('Offline'); $('runtime-state').textContent='Offline'; } }
async function startEvents() {
  if (!state.origin || !state.sessionToken || state.eventsAbort) return;
  const ctrl = new AbortController(); state.eventsAbort = ctrl;
  try {
    const r = await fetch(state.origin + '/cloud/events', {headers:{Authorization:`Bearer ${state.sessionToken}`},signal:ctrl.signal}); if (!r.ok || !r.body) throw new Error('event stream unavailable');
    const reader=r.body.getReader(),decoder=new TextDecoder();let buf='';
    while(true){const{value,done}=await reader.read();if(done)break;buf+=decoder.decode(value,{stream:true});let idx;while((idx=buf.indexOf('\n\n'))>=0){const frame=buf.slice(0,idx);buf=buf.slice(idx+2);const line=frame.split('\n').find(x=>x.startsWith('data: '));if(line){try{applyRuntime(JSON.parse(line.slice(6)));}catch{}}}}
  } catch(e) { if(e.name!=='AbortError')setTimeout(()=>{state.eventsAbort=null;startEvents();},3000); } finally { if(state.eventsAbort===ctrl)state.eventsAbort=null; }
}

tabs.forEach(t=>t.addEventListener('click',()=>{tabs.forEach(x=>x.classList.toggle('active',x===t));pages.forEach(p=>p.classList.toggle('active',p.id===t.dataset.page));document.body.classList.toggle('page-with-footer',t.dataset.page!=='home');}));
$('runtime-origin').value=state.origin;
$('pair').addEventListener('submit',async e=>{e.preventDefault();const origin=normOrigin($('runtime-origin').value),token=$('pair-token').value.trim(),code=$('pair-code').value.trim();if(!origin||!token||!code)return;$('pair-message').textContent='Pairing…';try{if(state.eventsAbort){state.eventsAbort.abort();state.eventsAbort=null;}await stopVision('Camera off');state.origin=origin;sessionStorage.setItem('pai.origin',origin);const r=await fetch(origin+'/pair/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token,code,name:'Vishnu Web Companion',platform:'web'})});const body=await r.json();if(!r.ok)throw new Error(body.detail||'Pairing failed');state.deviceId=body.device.id;state.deviceToken=body.bearer_token;state.sessionToken='';sessionStorage.setItem('pai.deviceId',state.deviceId);sessionStorage.setItem('pai.deviceToken',state.deviceToken);sessionStorage.removeItem('pai.sessionToken');$('pair-token').value='';$('pair-code').value='';await ensureSession();$('pair-message').textContent='Paired securely for this browser session.';await refreshStatus();}catch(err){$('pair-message').textContent=err.message;setStatus('Pairing failed');}});
$('ask').addEventListener('submit',async e=>{e.preventDefault();const input=$('prompt'),text=input.value.trim();if(!text)return;input.value='';$('reply').hidden=false;$('reply').textContent='Thinking…';try{if(!await ensureSession())throw new Error('Pair a secure runtime first');const body=await call('/cloud/command',{method:'POST',body:JSON.stringify({text,nonce:nonce()})});if(body.approval_required){$('approval-count').textContent='1';$('approval-copy').textContent=`${body.tool} requires approval.`;$('reply').innerHTML=`<b>Approval required</b><p>${body.description||body.tool}</p><div class="row"><button class="action" id="approve-now">Approve once</button><button class="danger" id="reject-now">Reject</button></div>`;const decide=async decision=>{const x=await call('/cloud/approval',{method:'POST',body:JSON.stringify({approval_id:body.approval_id,decision,nonce:nonce()})});$('reply').textContent=x.reply||`Action ${decision}d.`;$('approval-count').textContent='0';$('approval-copy').textContent='No pending approvals.';};$('approve-now').onclick=()=>decide('approve').catch(x=>$('reply').textContent=x.message);$('reject-now').onclick=()=>decide('reject').catch(x=>$('reply').textContent=x.message);}else $('reply').textContent=body.reply||'Completed.';}catch(err){$('reply').textContent=err.message;}});
$('memory-search').addEventListener('submit',async e=>{e.preventDefault();const q=$('memory-query').value.trim();try{if(!await ensureSession())throw new Error('Pair a secure runtime first');const body=await call('/cloud/memory/search',{method:'POST',body:JSON.stringify({query:q,include_sensitive:false})});$('memory-results').innerHTML='';if(!body.results.length){$('memory-results').textContent='No permitted memories found.';return;}body.results.forEach(m=>{const p=document.createElement('p'),b=document.createElement('b');b.textContent=m.subject||m.type||'Memory';p.append(b,document.createElement('br'),document.createTextNode(m.content||''));$('memory-results').appendChild(p);});}catch(err){$('memory-results').textContent=err.message;}});
async function emergency(enabled){const owner=$('owner-secret').value;try{if(!state.origin)throw new Error('Runtime origin not configured');const r=await fetch(state.origin+'/cloud/emergency-stop',{method:'POST',headers:{'Content-Type':'application/json','X-Personal-AI-Owner-Key':owner},body:JSON.stringify({enabled})});const body=await r.json();if(!r.ok)throw new Error(body.detail||body.error||'Emergency control failed');$('owner-secret').value='';if(enabled)await stopVision('Camera stopped by emergency control');await refreshStatus();}catch(err){$('owner-secret').value='';alert(err.message);}}
$('stop').addEventListener('click',()=>emergency(true));$('resume').addEventListener('click',()=>emergency(false));

function setVisionUI(active,text){$('vision-indicator').textContent=active?'● Camera active':'Camera off';$('vision-status').textContent=text;$('vision-preview').style.display=active?'block':'none';$('vision-start').disabled=active;$('vision-analyze').disabled=!active;$('vision-stop').disabled=!active;$('vision-camera').disabled=active;$('vision-policy').disabled=active;$('vision-live-start').disabled=!active;$('vision-voice-start').disabled=!active;}
async function refreshCameraList(){if(!navigator.mediaDevices?.enumerateDevices)return;try{const devices=(await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==='videoinput');const select=$('vision-camera'),chosen=select.value;select.innerHTML='<option value="">Default camera</option>';devices.forEach((d,i)=>{const o=document.createElement('option');o.value=d.deviceId;o.textContent=d.label||`Camera ${i+1}`;select.appendChild(o);});if([...select.options].some(o=>o.value===chosen))select.value=chosen;}catch{}}
function clearVisionTimer(){if(state.visionTimer)clearTimeout(state.visionTimer);state.visionTimer=null;}
async function revokeSensorSession(){if(!state.visionResource||!state.deviceToken)return;try{await sensorCall('/session/revoke',{method:'POST',body:JSON.stringify({resource_id:state.visionResource,ttl_seconds:300,explicit_consent:false})});}catch{}state.visionSensorSession=null;}
async function stopLive(reason='Live Vision stopped'){if(state.liveInterval)clearInterval(state.liveInterval);state.liveInterval=null;const id=state.liveSession;state.liveSession=null;state.liveDeadline=0;state.liveFingerprint=null;$('vision-live-start').disabled=!state.visionStream;$('vision-live-stop').disabled=true;$('vision-live-timer').textContent=reason;if(id){try{await sensorCall(`/live/${encodeURIComponent(id)}/stop`,{method:'POST',body:'{}'});}catch{}}}
function stopVoice(reason='Microphone off'){if(state.recognition){try{state.recognition.stop();}catch{}state.recognition=null;}if(state.voiceStream)state.voiceStream.getTracks().forEach(t=>t.stop());state.voiceStream=null;$('vision-voice-start').disabled=!state.visionStream;$('vision-voice-stop').disabled=true;$('vision-voice-status').textContent=reason;}
async function stopVision(reason='Camera off'){await stopLive('Live Vision off');stopVoice('Microphone off');clearVisionTimer();if(state.visionStream)state.visionStream.getTracks().forEach(track=>track.stop());state.visionStream=null;$('vision-preview').srcObject=null;await revokeSensorSession();state.visionResource=null;setVisionUI(false,reason);}

async function setCameraPolicy(resource,mode){return sensorCall('/permission',{method:'POST',body:JSON.stringify({resource_id:resource,mode})});}
async function browserBatteryPercent(){if(typeof navigator.getBattery!=='function')return null;try{const battery=await navigator.getBattery();return Math.max(0,Math.min(100,Math.round(Number(battery.level)*100)));}catch{return null;}}
async function requireLiveBattery(){const battery=await browserBatteryPercent();if(battery!==null&&battery<MIN_LIVE_BATTERY_PERCENT)throw new Error(`Live Vision requires at least ${MIN_LIVE_BATTERY_PERCENT}% battery on this device.`);return battery;}
async function startVision(){
  $('vision-result').textContent='';if(!state.deviceId||!state.deviceToken){$('vision-result').textContent='Pair this browser with Vishnu first.';return;}if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){$('vision-result').textContent='Camera access requires HTTPS (or localhost) and a supported browser.';return;}
  await stopVision('Requesting camera permission…');
  try{
    const selected=$('vision-camera').value;const constraints=selected?{deviceId:{exact:selected}}:{facingMode:{ideal:'environment'}};
    const stream=await navigator.mediaDevices.getUserMedia({audio:false,video:constraints});state.visionStream=stream;$('vision-preview').srcObject=stream;await $('vision-preview').play();
    await refreshCameraList();const settings=stream.getVideoTracks()[0]?.getSettings?.()||{};const deviceId=settings.deviceId||selected||'default';state.visionResource=`browser:${deviceId}`;
    const mode=$('vision-policy').value;if(mode==='never'){await setCameraPolicy(state.visionResource,'never');throw new Error('Camera policy is set to Never. Change it to Ask every time before starting.');}
    await setCameraPolicy(state.visionResource,'ask');state.visionSensorSession=crypto.randomUUID?crypto.randomUUID():nonce();
    await sensorCall('/session/grant',{method:'POST',body:JSON.stringify({resource_id:state.visionResource,ttl_seconds:300,session_id:state.visionSensorSession,explicit_consent:true})});
    setVisionUI(true,'Vishnu Vision is active for this browser only. It stops automatically after 5 minutes or when the page is hidden.');state.visionTimer=setTimeout(()=>stopVision('Vision session expired after 5 minutes.'),5*60*1000);
  }catch(err){if(state.visionStream)state.visionStream.getTracks().forEach(t=>t.stop());state.visionStream=null;setVisionUI(false,'Camera off');$('vision-result').textContent=err?.name==='NotAllowedError'?'Camera permission was not granted.':(err.message||'This camera could not be opened.');}
}

function captureCanvas(){const video=$('vision-preview');if(!state.visionStream||!video.videoWidth||!video.videoHeight)throw new Error('Start the camera first.');const maxWidth=1024,scale=Math.min(1,maxWidth/video.videoWidth),canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(video.videoWidth*scale));canvas.height=Math.max(1,Math.round(video.videoHeight*scale));const ctx=canvas.getContext('2d',{alpha:false});ctx.drawImage(video,0,0,canvas.width,canvas.height);return canvas;}
function pixelateCanvasRect(canvas,box){const ctx=canvas.getContext('2d'),x=Math.max(0,Math.floor(box.x)),y=Math.max(0,Math.floor(box.y)),w=Math.min(canvas.width-x,Math.ceil(box.width)),h=Math.min(canvas.height-y,Math.ceil(box.height));if(w<2||h<2)return;const tiny=document.createElement('canvas');tiny.width=Math.max(1,Math.floor(w/20));tiny.height=Math.max(1,Math.floor(h/20));const t=tiny.getContext('2d');t.drawImage(canvas,x,y,w,h,0,0,tiny.width,tiny.height);ctx.save();ctx.imageSmoothingEnabled=false;ctx.drawImage(tiny,0,0,tiny.width,tiny.height,x,y,w,h);ctx.restore();}
async function applyLocalPrivacy(canvas){const redact=$('vision-redact-faces').checked;if(!redact)return{faces_processed:false,require_face_redaction:false};if(!('FaceDetector'in window))throw new Error('Face redaction was requested, but this browser does not provide local face detection. Turn it off or use a supported device.');const detector=new FaceDetector({fastMode:true,maxDetectedFaces:32});const faces=await detector.detect(canvas);faces.forEach(face=>pixelateCanvasRect(canvas,face.boundingBox));return{faces_processed:true,require_face_redaction:true,faces_detected:faces.length};}
function fingerprint(canvas){const small=document.createElement('canvas');small.width=16;small.height=16;const ctx=small.getContext('2d',{willReadFrequently:true});ctx.drawImage(canvas,0,0,16,16);const d=ctx.getImageData(0,0,16,16).data,out=[];for(let i=0;i<d.length;i+=4)out.push(Math.round((d[i]+d[i+1]+d[i+2])/3));return out;}
function fingerprintDelta(a,b){if(!a||a.length!==b.length)return 1;let sum=0;for(let i=0;i<a.length;i++)sum+=Math.abs(a[i]-b[i]);return sum/(255*a.length);}
function visionOptions(){return{question:$('vision-question').value.trim()||'Describe what you can see.',resource_id:state.visionResource,sensor_session_id:state.visionSensorSession,task_mode:$('vision-task').value,memory_mode:$('vision-memory').value,speak:false};}
function browserSpeak(text){if(!$('vision-speak').checked||!('speechSynthesis'in window)||!text)return;window.speechSynthesis.cancel();window.speechSynthesis.speak(new SpeechSynthesisUtterance(text.slice(0,4000)));}
async function preparedFrame(){const canvas=captureCanvas();const local=await applyLocalPrivacy(canvas);const dataUrl=canvas.toDataURL('image/jpeg',0.72);if(dataUrl.length>2_050_000)throw new Error('Snapshot is too large. Move closer or reduce camera resolution.');return{canvas,dataUrl,privacy:{max_edge:1024,crop:null,redact_regions:[],faces_processed:local.faces_processed,require_face_redaction:local.require_face_redaction}};}
async function analyzeVision(){if(!state.visionSensorSession){$('vision-result').textContent='Start the camera first.';return;}$('vision-analyze').disabled=true;$('vision-result').textContent='Analyzing one privacy-processed snapshot…';try{const frame=await preparedFrame();const body=await sensorCall('/browser/snapshot',{method:'POST',body:JSON.stringify({...visionOptions(),data_url:frame.dataUrl,privacy:frame.privacy})});$('vision-result').textContent=body.analysis||'Vishnu returned no visual description.';browserSpeak(body.analysis);}catch(err){$('vision-result').textContent=err.message||'Vision analysis failed.';}finally{$('vision-analyze').disabled=!state.visionStream;}}

function updateLiveTimer(){if(!state.liveSession)return;const remaining=Math.max(0,Math.ceil((state.liveDeadline-Date.now())/1000));$('vision-live-timer').textContent=`Live Vision active · ${remaining}s remaining · battery floor ${MIN_LIVE_BATTERY_PERCENT}% · data budget 40 MB`;if(remaining<=0)stopLive('Live Vision expired.');}
async function liveTick(){if(!state.liveSession||!state.visionStream)return;try{await requireLiveBattery();const frame=await preparedFrame();const fp=fingerprint(frame.canvas),delta=fingerprintDelta(state.liveFingerprint,fp);if(state.liveFingerprint&&delta<0.02){updateLiveTimer();return;}state.liveFingerprint=fp;const body=await sensorCall(`/live/${encodeURIComponent(state.liveSession)}/browser/tick`,{method:'POST',body:JSON.stringify({data_url:frame.dataUrl,sensor_session_id:state.visionSensorSession,speak:false,privacy:frame.privacy})});if(body.analyzed&&body.observation?.analysis){$('vision-result').textContent=body.observation.analysis;browserSpeak(body.observation.analysis);}updateLiveTimer();}catch(err){if(/interval has not elapsed/i.test(err.message))return;$('vision-result').textContent=err.message;await stopLive(/battery/i.test(err.message)?`Live Vision stopped below ${MIN_LIVE_BATTERY_PERCENT}% battery.`:'Live Vision stopped after an error.');}}
async function startLive(){if(!state.visionStream||!state.visionSensorSession)return;await stopLive('Starting Live Vision…');try{await requireLiveBattery();const fps=Math.max(.2,Math.min(1,Number($('vision-fps').value)||.5));const body=await sensorCall('/live/start',{method:'POST',body:JSON.stringify({target_device_id:state.deviceId,resource_id:state.visionResource,question:$('vision-question').value.trim()||'Watch for meaningful changes and tell me what I should know.',task_mode:$('vision-task').value,memory_mode:$('vision-memory').value,sample_fps:fps,duration_seconds:300,scene_threshold:.035,max_frames:150,max_bytes:40*1024*1024,max_model_calls:90})});state.liveSession=body.session_id;state.liveDeadline=Date.now()+300000;state.liveFingerprint=null;$('vision-live-start').disabled=true;$('vision-live-stop').disabled=false;updateLiveTimer();state.liveInterval=setInterval(()=>liveTick(),Math.round(1000/fps));await liveTick();}catch(err){$('vision-result').textContent=err.message;await stopLive('Live Vision off');}}

async function startVisionVoice(){if(!state.visionStream)await startVision();if(!state.visionStream)return;stopVoice('Requesting microphone…');try{state.voiceStream=await navigator.mediaDevices.getUserMedia({audio:true,video:false});$('vision-voice-start').disabled=true;$('vision-voice-stop').disabled=false;const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;if(!Recognition){$('vision-voice-status').textContent='Microphone active; speech recognition is unavailable in this browser.';return;}const recognition=new Recognition();state.recognition=recognition;recognition.continuous=true;recognition.interimResults=false;recognition.onresult=async event=>{for(let i=event.resultIndex;i<event.results.length;i++){if(!event.results[i].isFinal)continue;const text=event.results[i][0].transcript.trim();if(!text)continue;$('vision-question').value=text;$('vision-voice-status').textContent=`Heard: ${text}`;await analyzeVision();}};recognition.onerror=e=>{$('vision-voice-status').textContent=`Voice recognition: ${e.error||'error'}`;};recognition.onend=()=>{if(state.voiceStream&&state.recognition===recognition){try{recognition.start();}catch{}}};recognition.start();$('vision-voice-status').textContent='Vision + Voice active · listening for your question';}catch(err){stopVoice('Microphone off');$('vision-result').textContent=err?.name==='NotAllowedError'?'Microphone permission was not granted.':(err.message||'Microphone unavailable.');}}

$('vision-start').addEventListener('click',startVision);$('vision-analyze').addEventListener('click',analyzeVision);$('vision-stop').addEventListener('click',()=>stopVision('Camera stopped by you.'));
$('vision-live-start').addEventListener('click',startLive);$('vision-live-stop').addEventListener('click',()=>stopLive('Live Vision stopped by you.'));
$('vision-voice-start').addEventListener('click',startVisionVoice);$('vision-voice-stop').addEventListener('click',()=>stopVoice('Microphone stopped by you.'));
$('vision-policy').addEventListener('change',async()=>{if(state.visionResource){try{await setCameraPolicy(state.visionResource,$('vision-policy').value);}catch(err){$('vision-result').textContent=err.message;}}});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopVision('Camera stopped because the page was hidden.');});window.addEventListener('pagehide',()=>stopVision('Camera stopped.'));
navigator.mediaDevices?.addEventListener?.('devicechange',refreshCameraList);

refreshCameraList();refreshStatus();startEvents();setInterval(refreshStatus,60000);if('serviceWorker'in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
