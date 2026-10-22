/* P2-04: browser voice capture/UI over Vishnu's canonical conversation turn authority. */
(()=>{
'use strict';
if(window.vishnuP204)return;
const $=id=>document.getElementById(id), api=(url,options)=>window.vishnuVoiceBridge.api(url,options), id=v=>encodeURIComponent(String(v));
const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const S={open:false,mode:'expanded',context:'general',scope:null,scopeName:'General',thread:null,events:[],status:'idle',mic:false,muted:false,sending:false,playing:false,recognition:null,stream:null,audio:null,meter:null,frame:0,screen:null,voice:null,started:0,seconds:0,clock:null,request:null,draft:'',partial:'',tab:'conversation',items:[],token:0};
const copy={idle:['Voice is ready','Select Start Voice to request microphone permission.'],connecting:['Connecting…','Waiting for microphone permission.'],listening:['Vishnu is listening…','Speak naturally. I’m ready.'],muted:['Microphone muted','Tap Unmute to resume.'],thinking:['Vishnu is thinking…','Processing through the canonical AI runtime.'],speaking:['Vishnu is speaking…','Tap the Core to interrupt playback.'],approval:['Approval required','Review it through the trusted approval interface.'],error:['Voice needs attention','Use Text or retry starting the microphone.'],ended:['Voice session ended','Microphone and screen capture are stopped.']};
const nav=[['Home','home','⌂'],['Chat','chat','▢'],['Today','today','▣'],['Workspaces','labs','▦'],['Projects','projects','⬡'],['Agents','agents','♧'],['Create','products','✧'],['Library','knowledge','▤'],['Tools','tools','⌘'],['Devices','devices','▥'],['More','dashboard','⋯']];
const button=(key,label,cls='',attrs='')=>'<button type="button" data-p204="'+key+'" class="'+cls+'" '+attrs+'>'+label+'</button>';
function active(){return S.open&&$('p204Root')&&!$('p204Root').classList.contains('hidden')}
function info(text){if($('p204Info'))$('p204Info').textContent=text}
function phase(value,description){
 S.status=value;if(!active())return;
 $('p204Root').dataset.state=value;
 const [heading,defaultHint]=copy[value]||copy.idle;
 $('p204Status').textContent=heading;$('p204Hint').textContent=description||defaultHint;
 $('p204Start').hidden=!(value==='idle'||value==='ended'||value==='error');
 $('p204Mute').disabled=!S.mic||S.sending;
 $('p204Mute').textContent=S.muted?'♩':'♩̸';
 $('p204MuteLabel').textContent=S.muted?'Unmute':'Mute';
 $('p204End').disabled=value==='idle'||value==='ended';
}
function modal(title,description,options=[]){
 const d=$('p204Dialog');$('p204DialogTitle').textContent=title;$('p204DialogInfo').textContent=description;
 const box=$('p204DialogButtons');box.replaceChildren();
 for(const [label,fn] of [...options,['Close',()=>{}]]){const b=document.createElement('button');b.textContent=label;b.type='button';b.onclick=()=>{d.close();Promise.resolve(fn()).catch(e=>info(e.message))};box.append(b)}
 d.showModal();
}
function paint(){
 if(!active())return;
 $('p204Root').classList.toggle('p204-focus',S.mode==='focus');
 $('p204Scope').textContent=S.scopeName;
 $('p204Mode').textContent=S.mode==='focus'?'Focus Mode':'Expanded Mode';
 document.querySelectorAll('#p204Root [data-context]').forEach(b=>{
  const yes=b.dataset.context===S.context;b.classList.toggle('selected',yes);b.setAttribute('aria-pressed',String(yes));
 });
}
function renderEvents(){
 if(!active())return;
 const n=$('p204PanelBody');n.replaceChildren();
 const para=(value,cls='p204-fine')=>{const e=document.createElement('p');e.className=cls;e.textContent=value;n.append(e)};
 if(S.tab==='conversation'){
  if(!S.events.length)para('No messages in this conversation yet.');
  for(const ev of S.events.slice(-100)){
   if(!['user_message','assistant_message'].includes(ev.kind))continue;
   const row=document.createElement('article');row.className='p204-message '+(ev.kind==='user_message'?'mine':'assistant');
   const strong=document.createElement('strong');strong.textContent=ev.kind==='user_message'?'You':'Vishnu';
   const body=document.createElement('p');const raw=String(ev.payload?.text||'');body.textContent=ev.kind==='user_message'&&S.context==='workspace'?raw.split('Owner request: ').pop():raw;
   row.append(strong,body);n.append(row);
  }
 }else if(S.tab==='transcript'){
  para('Only final recognized speech becomes a canonical message. Partial speech is not persisted.');
  S.events.filter(x=>x.kind==='user_message').slice(-30).forEach(ev=>para(String(ev.payload?.text||''),'p204-transcript'));
  if(S.partial)para('Recognizing: '+S.partial,'p204-partial');
 }else if(S.tab==='context'){
  para('Scope: '+S.scopeName);para('Conversation ID: '+(S.thread||'Not created'));
  para('Context association is verified by existing Project/Workspace services. Context selection does not grant additional tool permissions.');
 }else{
  para('Tool activity and approvals remain governed by the existing Vishnu Work and Approval systems.');
  S.items.filter(x=>x.source==='attention').slice(0,8).forEach(x=>para(String(x.title||x.summary||x.kind||'Owner attention'),'p204-transcript'));
 }
 n.scrollTop=n.scrollHeight;
 document.querySelectorAll('#p204Root [data-p204-tab]').forEach(b=>{const a=b.dataset.p204Tab===S.tab;b.classList.toggle('selected',a);b.setAttribute('aria-selected',String(a))});
}
async function refreshThread(){
 if(!S.thread||!active())return;
 const url=S.context==='project'?'/projects/'+id(S.scope)+'/conversations/'+id(S.thread):
 S.context==='workspace'?'/workspaces/'+id(S.scope)+'/conversations/'+id(S.thread):'/conversations/'+id(S.thread);
 const result=await api(url);if(!active())return;
 const meta=result.conversation?.context||{};
 if(S.context==='project'&&meta.project_id!==S.scope)throw Error('Project conversation scope mismatch.');
 if(S.context==='workspace'&&meta.workspace_id!==S.scope)throw Error('Workspace conversation scope mismatch.');
 S.events=result.events||[];renderEvents();
}
async function ensureConversation(){
 if(S.thread)return S.thread;
 let response;
 if(S.context==='project')response=await api('/projects/'+id(S.scope)+'/conversations',{method:'POST',body:JSON.stringify({title:'Live Voice'})});
 else if(S.context==='workspace')response=await api('/workspaces/'+id(S.scope)+'/conversations',{method:'POST',body:JSON.stringify({title:'Live Voice',request_id:crypto.randomUUID()})});
 else response=await api('/conversations',{method:'POST',body:JSON.stringify({title:'Live Voice',context_type:S.context==='work'?'work':'personal'})});
 const conversation=response.conversation;if(!conversation?.id)throw Error('Canonical conversation creation failed.');
 if(S.context==='project'&&conversation.context?.project_id!==S.scope)throw Error('Invalid Project conversation association.');
 if(S.context==='workspace'&&conversation.context?.workspace_id!==S.scope)throw Error('Invalid Workspace conversation association.');
 S.thread=conversation.id;return S.thread;
}
function stopSpeech(){
 if(S.voice){S.voice.onstart=null;S.voice.onend=null;S.voice.onerror=null;S.voice=null}
 if(window.speechSynthesis)window.speechSynthesis.cancel();S.playing=false;
}
function pauseRecognition(){
 if(!S.recognition)return;
 const r=S.recognition;S.recognition=null;r.onend=null;r.onerror=null;r.onresult=null;r.onstart=null;try{r.stop()}catch{}
}
function releaseAudio(){
 pauseRecognition();S.mic=false;S.muted=false;
 if(S.stream){S.stream.getTracks().forEach(track=>track.stop());S.stream=null}
 if(S.audio){S.audio.close().catch(()=>{});S.audio=null}
 S.meter=null;cancelAnimationFrame(S.frame);S.frame=0;
 document.querySelectorAll('#p204Root .p204-wave i').forEach(bar=>bar.style.removeProperty('--volume'));
}
async function releaseScreen(){if(S.screen){S.screen.getTracks().forEach(x=>x.stop());S.screen=null}if($('p204Share'))$('p204Share').textContent='Screen Share'}
function elapsed(){
 if(!active())return;
 const diff=S.seconds+(S.started?performance.now()-S.started:0),sec=Math.floor(diff/1000);
 $('p204Timer').textContent=String(Math.floor(sec/60)).padStart(2,'0')+':'+String(sec%60).padStart(2,'0');
}
function beginClock(){if(!S.started){S.started=performance.now();clearInterval(S.clock);S.clock=setInterval(elapsed,1000);elapsed()}}
function haltClock(){if(S.started){S.seconds+=performance.now()-S.started;S.started=0}clearInterval(S.clock);S.clock=null;elapsed()}
function waveform(){
 if(!S.meter||!S.mic||!active())return;
 const a=new Uint8Array(S.meter.fftSize);S.meter.getByteTimeDomainData(a);
 const rms=Math.sqrt(a.reduce((sum,v)=>sum+Math.pow((v-128)/128,2),0)/a.length);
 const amp=Math.min(1,rms*6);
 document.querySelectorAll('#p204Root .p204-wave i').forEach((el,i)=>el.style.setProperty('--volume',String(Math.max(.05,amp*(.4+(i%5)*.15)))));
 S.frame=requestAnimationFrame(waveform);
}
async function listen(){
 if(!active()||S.mic)return;
 const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
 if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia||!Recognition){phase('error','Speech recognition requires a compatible browser, HTTPS, and microphone permission. Use Text if unavailable.');return}
 if((S.context==='project'||S.context==='workspace')&&!S.scope){info('Select an authorized scope before starting.');return}
 phase('connecting');
 try{
  const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
  if(!active()){stream.getTracks().forEach(t=>t.stop());return}
  S.stream=stream;
  stream.getAudioTracks()[0]?.addEventListener('ended',()=>{if(S.mic){releaseAudio();phase('error','Microphone disconnected or permission revoked.')}});
  try{
   const Audio=window.AudioContext||window.webkitAudioContext;
   if(Audio){S.audio=new Audio();const src=S.audio.createMediaStreamSource(stream);S.meter=S.audio.createAnalyser();S.meter.fftSize=512;src.connect(S.meter)}
  }catch{}
  const r=new Recognition();r.lang=navigator.language||'en-US';r.continuous=true;r.interimResults=true;
  r.onstart=()=>{if(!active())return;S.mic=true;beginClock();phase('listening');waveform();info('Browser speech recognition may process audio using an external service. No raw audio is saved by this screen.')};
  r.onresult=event=>{let final='',partial='';for(let i=event.resultIndex;i<event.results.length;i++){const result=event.results[i];if(result.isFinal)final+=result[0].transcript;else partial+=result[0].transcript}S.partial=partial;renderEvents();if(final.trim()&&!S.sending){S.partial='';send(final.trim(),'voice')}};
  r.onerror=ev=>{if(['no-speech','aborted'].includes(ev.error))return;releaseAudio();phase('error',ev.error==='not-allowed'?'Microphone permission denied.':('Speech recognition error: '+ev.error))};
  r.onend=()=>{if(!S.mic||!active()||S.muted||S.sending)return;releaseAudio();phase('error','Recognizer stopped. Select Start Voice to reconnect.')};
  S.recognition=r;r.start();
 }catch(err){releaseAudio();phase('error',err.name==='NotAllowedError'?'Microphone permission denied.':err.message)}
}
async function mute(){
 if(!S.mic)return;
 S.muted=true;pauseRecognition();S.stream?.getAudioTracks().forEach(t=>t.enabled=false);phase('muted','Capture paused. Select Unmute to restart.');
 // Restart only by an explicit subsequent user gesture; never auto-listen in the background.
}
async function unmute(){
 if(!S.muted)return;
 releaseAudio();phase('idle','Unmuted. Select Start Voice to resume microphone capture.');
}
function speak(text){
 if(!window.speechSynthesis||!window.SpeechSynthesisUtterance){info('Response persisted. TTS is not available in this browser.');phase('idle');return}
 const utterance=new SpeechSynthesisUtterance(String(text||'').slice(0,3000));utterance.lang=navigator.language||'en-US';utterance.rate=1;
 utterance.onstart=()=>{S.playing=true;if(active())phase('speaking')};
 utterance.onend=()=>{S.playing=false;S.voice=null;if(active())phase('idle','Voice playback completed. Start Voice to speak again.')};
 utterance.onerror=()=>{S.playing=false;S.voice=null;if(active()){phase('idle');info('Audio playback unavailable; text response remains saved.')}};
 S.voice=utterance;window.speechSynthesis.cancel();window.speechSynthesis.speak(utterance);
}
async function send(raw,modality='text'){
 const text=String(raw||'').trim();if(!text||S.sending)return;
 if((S.context==='project'||S.context==='workspace')&&!S.scope){info('Select a Project or Workspace before sending.');return}
 S.sending=true;S.request=crypto.randomUUID();const nonce=S.token;S.draft=text;releaseAudio();phase('thinking');
 try{
  await ensureConversation();
  const payload={request_id:S.request,conversation_id:S.thread,transcript:text};
  if(S.context==='workspace')payload.workspace_id=S.scope;
  const reply=await api('/voice/turn',{method:'POST',headers:{'X-Personal-AI-Input-Modality':modality},body:JSON.stringify(payload)});
  if(nonce!==S.token||!active())return;
  S.request=null;S.draft='';$('p204Text').value='';
  await refreshThread();
  if(reply.status==='approval_required'){phase('approval');info('A governed action requires your explicit approval; no automatic approval is performed.')}
  else if(modality==='voice'&&reply.reply)speak(reply.reply);
  else phase('idle','Canonical response received. Choose Start Voice to resume speaking.');
 }catch(error){if(nonce===S.token&&active()){phase('error',error.message);info('No confirmed success. Unsent text remains in the composer.')}}
 finally{S.sending=false;S.request=null}
}
async function interrupt(){
 stopSpeech();try{await api('/voice/barge',{method:'POST',body:JSON.stringify({speaking:true})})}catch(e){info('Playback interrupted locally; server response unavailable: '+e.message)}phase('idle');
}
async function end(hide=false){
 S.token++;
 if(S.request){try{await api('/voice/operation/cancel',{method:'POST',body:JSON.stringify({request_id:S.request})})}catch(e){info('Canonical cancellation unconfirmed; check Work before retry.')}S.request=null}
 stopSpeech();releaseAudio();await releaseScreen();haltClock();S.partial='';phase('ended');renderEvents();
 if(hide){S.open=false;$('p204Root').classList.add('hidden');$('p204Root').setAttribute('aria-hidden','true');window.vishnuVoiceBridge.onClose?.()}
}
function select(kind,scope=null,name=null){
 if(!['general','work','project','workspace'].includes(kind)||S.sending)return;
 if(S.mic){info('End microphone capture before switching contexts.');return}
 if(S.thread&&!confirm('Create a separate '+kind+' conversation? Your prior transcript stays in its original context.'))return;
 S.context=kind;S.scope=scope;S.scopeName=name||kind[0].toUpperCase()+kind.slice(1);S.thread=null;S.events=[];S.partial='';S.draft='';$('p204Text').value='';paint();renderEvents();
}
async function choose(kind){
 if(kind==='general'||kind==='work'){select(kind);return}
 const x=await api(kind==='project'?'/projects?status=active':'/workspaces?status=active');
 const list=kind==='project'?x.projects:x.workspaces;
 if(!list?.length){modal('No '+kind+' available','Open the existing '+kind+' module to create or select one.',[['Open '+kind,()=>navigate(kind==='project'?'projects':'labs')]]);return}
 modal('Select '+kind,'Choose a saved, owner-authorized resource. No existing transcript is copied.',
 list.slice(0,30).map(item=>[item.name,()=>select(kind,item.id,item.name)]));
}
async function share(){
 if(S.screen){releaseScreen();info('Screen sharing ended.');return}
 if(!navigator.mediaDevices?.getDisplayMedia){modal('Screen share unavailable','This browser or device cannot capture a screen/window.');return}
 if(!confirm('Choose a screen/window to preview locally. Screen content is NOT sent to Vishnu AI by this implementation.'))return;
 try{S.screen=await navigator.mediaDevices.getDisplayMedia({video:true,audio:false});S.screen.getVideoTracks()[0]?.addEventListener('ended',releaseScreen);$('p204Share').textContent='Stop Sharing';info('Local screen capture is active, but frames are not analyzed or sent to AI.')}
 catch(err){info('Screen sharing cancelled or failed: '+err.message)}
}
async function refreshItems(){
 const results=await Promise.allSettled([api('/work/attention?limit=15'),api('/everyday/timeline?day='+new Date().toISOString().slice(0,10)+'&timezone='+encodeURIComponent(Intl.DateTimeFormat().resolvedOptions().timeZone))]);
 if(!active())return;
 const attention=results[0].status==='fulfilled'?(results[0].value.items||[]):[];
 const tasks=results[1].status==='fulfilled'?(results[1].value.items||[]):[];
 S.items=[...attention.map(x=>({...x,source:'attention'})),...tasks.map(x=>({...x,source:'today'}))].slice(0,8);
 const host=$('p204Items');host.replaceChildren();
 if(!S.items.length){host.textContent=results.some(x=>x.status==='rejected')?'Some key items are unavailable. Open Today for details.':'No key items need attention right now.'}
 S.items.forEach(x=>{const b=document.createElement('button');b.type='button';b.textContent=String(x.title||x.summary||'View item')+' · '+String(x.status||x.kind||x.source);b.onclick=()=>navigate(x.source==='today'?'today':'attention');host.append(b)});
 renderEvents();
}
async function settings(){
 const devices=await navigator.mediaDevices?.enumerateDevices?.().catch(()=>[])||[];
 const microphones=devices.filter(x=>x.kind==='audioinput').length,speakers=devices.filter(x=>x.kind==='audiooutput').length;
 modal('Voice Settings','Browser inputs: '+microphones+'; outputs: '+speakers+'. The browser/OS controls speech devices. This screen does not claim support for direct device routing.',[['AI Settings',()=>navigate('settings')]]);
}
function navigate(dest){
 if(S.mic||S.sending||S.screen){modal('End Live Voice?','Leaving stops audio and screen capture but does not cancel unrelated durable Work.',[['End and continue',async()=>{await end(true);window.vishnuVoiceBridge.navigate(dest)}]]);return}
 end(true).then(()=>window.vishnuVoiceBridge.navigate(dest));
}
function tool(name){
 if(name==='notes')return modal('Take Notes','Notes can be saved through existing Knowledge workflows. Voice does not silently create Memory.',[['Open Knowledge',()=>navigate('knowledge')]]);
 if(name==='search')return navigate('search');
 if(name==='analyze'){S.draft='Analyze the verified information in this conversation: ';$('p204Text').value=S.draft;$('p204Text').focus();return}
 if(name==='create')return navigate('products');
 if(name==='apps')return navigate('tools');
 return modal('Voice tools','Open an available, governed destination.',[['Today',()=>navigate('today')],['Work',()=>navigate('workflows')],['Voice Settings',settings]]);
}
function paint(){
 if(!active())return;
 $('p204Root').classList.toggle('p204-focus',S.mode==='focus');$('p204Mode').textContent=S.mode==='focus'?'Focus Mode':'Expanded Mode';
 $('p204Scope').textContent=S.scopeName;
 document.querySelectorAll('#p204Root [data-context]').forEach(b=>{const a=b.dataset.context===S.context;b.classList.toggle('selected',a);b.setAttribute('aria-pressed',String(a))});
}
async function handle(name){
 if(name.startsWith('nav:'))return name==='nav:voice'?null:navigate(name.slice(4));
 if(name.startsWith('context:'))return choose(name.slice(8));
 if(name.startsWith('tool:'))return tool(name.slice(5));
 if(name==='start')return S.playing?interrupt():listen();
 if(name==='mute')return S.muted?unmute():mute();
 if(name==='end')return end(true);
 if(name==='text'){$('p204Text').focus();return}
 if(name==='mode'){S.mode=S.mode==='expanded'?'focus':'expanded';paint();return}
 if(name==='share')return share();
 if(name==='settings')return settings();
 if(name==='attach')return modal('Attach sources','Use the existing authorized Knowledge/Project file workflows. No file is silently uploaded.',[['Open Library',()=>navigate('knowledge')]]);
 if(name==='menu'){$('p204Root').classList.toggle('menu-open');return}
 if(name==='more')return modal('Voice options','Select an available action.',[['Change voice mode',()=>handle('mode')],['Settings',settings],['End',()=>end(true)]]);
}
const wave='<div class="p204-wave" aria-hidden="true">'+Array.from({length:19},()=>'<i></i>').join('')+'</div>';
function build(){
 const sidebar=nav.map(([title,dest,glyph])=>button('nav:'+dest,'<span>'+glyph+'</span>'+escape(title),'p204-nav-item')).join('');
 const contexts=[['general','General'],['work','Work'],['project','Project'],['workspace','Workspace']].map(([kind,label])=>button('context:'+kind,escape(label),'','data-context="'+kind+'" aria-pressed="false"')).join('');
 const tabs=[['conversation','Conversation'],['transcript','Live Transcript'],['activity','Tools & Activity'],['context','Context']].map(([name,title])=>'<button type="button" role="tab" aria-selected="false" data-p204-tab="'+name+'">'+title+'</button>').join('');
 const tools=[['notes','Take Notes'],['search','Search'],['analyze','Analyze'],['create','Create'],['apps','Open Apps'],['more','More']].map(([key,name])=>button('tool:'+key,escape(name))).join('');
 const mobile=[['Home','home','⌂'],['Chat','chat','▢'],['Today','today','▣'],['Voice','voice','🎙'],['More','dashboard','⋯']].map(([title,dest,glyph])=>button('nav:'+dest,'<span>'+glyph+'</span><small>'+title+'</small>',dest==='voice'?'active':'')).join('');
 $('p204Root').innerHTML='<div class="p204-shell"><aside class="p204-sidebar"><div class="p204-brand">V I S H N U</div><nav aria-label="Vishnu sections">'+sidebar+'</nav><div class="p204-owner">Authenticated owner session</div></aside><div class="p204-main"><header class="p204-top">'+button('menu','☰','p204-menu')+'<strong class="p204-mobile-logo">V I S H N U</strong>'+button('nav:search','⌕ Search or ask anything…','p204-search')+button('nav:attention','♧','p204-top-icon','aria-label="Owner attention"')+button('nav:chat','▢','p204-top-icon','aria-label="Conversations"')+button('nav:settings','◉','p204-top-icon','aria-label="Account Settings"')+'</header><section class="p204-page"><div class="p204-page-head"><div class="p204-heading"><span class="p204-voice-icon">〽</span><div><h1>Live Voice</h1><p>Talk to Vishnu naturally. Get real-time help, work done and stay in flow.</p></div></div><div class="p204-actions">'+button('mode','Voice Mode','p204-primary','id="p204Mode"')+button('share','Screen Share','','id="p204Share"')+button('settings','Settings')+button('more','⋯')+'</div></div><div class="p204-columns"><main class="p204-stage"><div class="p204-orb-row">'+wave+button('start','<span class="p204-orb-light"></span><span class="p204-particle one"></span><span class="p204-particle two"></span><span class="p204-particle three"></span>','p204-orb','id="p204Orb" aria-label="Start voice"')+wave+'</div><h2 id="p204Status">Voice is ready</h2><p id="p204Hint"></p><small class="p204-scope" id="p204Scope">General</small><div class="p204-context" role="group" aria-label="Voice context">'+contexts+'</div><div class="p204-controls"><div>'+button('mute','♩̸','p204-round','id="p204Mute" disabled')+'<small id="p204MuteLabel">Mute</small></div><div>'+button('end','×','p204-round p204-end','id="p204End" disabled')+'<small>End</small></div><div>'+button('text','⌨','p204-round')+'<small>Text</small></div></div><div class="p204-bottom-wave">'+wave+'<time id="p204Timer">00:00</time></div>'+button('start','Start Voice','p204-start p204-primary','id="p204Start"')+'<div class="p204-tools">'+tools+'</div></main><aside class="p204-inspector"><nav role="tablist" class="p204-tabs" aria-label="Voice conversation details">'+tabs+'</nav><div id="p204PanelBody" class="p204-panel-body" role="tabpanel"></div><section class="p204-key"><header><h2>Today’s Key Items</h2>'+button('nav:today','View All')+'</header><div id="p204Items">Loading source records…</div></section><form id="p204Form" class="p204-composer">'+button('attach','＋','','aria-label="Attach"')+'<input id="p204Text" aria-label="Speak or type message" maxlength="8000" placeholder="Speak or type a message…">'+button('start','♩','','aria-label="Start microphone"')+'<button type="submit" aria-label="Send text">➤</button></form><div id="p204Info" class="p204-info" role="status"></div></aside></div></section><nav class="p204-mobile-nav" aria-label="Voice mobile navigation">'+mobile+'</nav></div></div>';
 $('p204Form').addEventListener('submit',e=>{e.preventDefault();send($('p204Text').value)});
 $('p204Text').addEventListener('input',e=>S.draft=e.target.value);
 $('p204Root').addEventListener('click',e=>{const b=e.target.closest('button[data-p204]');if(b)handle(b.dataset.p204).catch(x=>info(x.message))});
 $('p204Root').querySelectorAll('[data-p204-tab]').forEach(b=>b.addEventListener('click',()=>{S.tab=b.dataset.p204Tab;renderEvents()}));
 paint();phase('idle');renderEvents();
}
async function open(){
 if(S.open)return;
 S.open=true;const root=$('p204Root');if(!root){S.open=false;throw Error('Voice screen is not installed.')}
 root.classList.remove('hidden');root.setAttribute('aria-hidden','false');build();
 await refreshItems().catch(x=>info('Key items unavailable: '+x.message));
}
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&S.mic){releaseAudio();phase('idle','Microphone released while app is inactive. Restart explicitly to listen again.')}});
window.addEventListener('pagehide',()=>{if(S.open){stopSpeech();releaseAudio();releaseScreen();haltClock();S.token++;S.open=false}});
window.vishnuP204={open,close:()=>end(true),get state(){return {phase:S.status,scope:S.context,thread:S.thread,mode:S.mode,recording:S.mic}}};
})();