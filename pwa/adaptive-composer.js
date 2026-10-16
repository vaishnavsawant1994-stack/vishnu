/* Vishnu Adaptive Universal Composer.
 *
 * This is an interaction/routing layer only. It never calls a privileged
 * execution endpoint and never replaces canonical Chat, ToolRegistry,
 * ApprovalManager, DeviceGateway, server permissions, or audit authorities.
 */
(()=>{
  'use strict';
  if(window.__vishnuAdaptiveComposer)return;

  // Direct module routing is deliberately conservative. Only canonical modules
  // that are known to exist in the current PWA are opened here. Every other
  // intent continues through canonical Chat so server-side planning/governance
  // stays authoritative.
  const INTENTS={
    chat:{label:'Chat',icon:'✦',description:'Continue as a normal Vishnu conversation.',module:null},
    projects:{label:'Projects',icon:'▣',description:'Plan, continue, or inspect project work.',module:'projects'},
    memory:{label:'Memory',icon:'◫',description:'Find or work with information Vishnu remembers.',module:'memory'},
    files:{label:'Files',icon:'⌑',description:'Find, read, summarize, or work with a file.',module:null},
    research:{label:'Research',icon:'⌕',description:'Investigate a topic and collect evidence.',module:null},
    code:{label:'Code',icon:'</>',description:'Build, debug, review, or change software.',module:null},
    automation:{label:'Automation',icon:'↻',description:'Create a reminder, schedule, or recurring workflow.',module:null},
    devices:{label:'Devices',icon:'◉',description:'Inspect or control a trusted device through Vishnu governance.',module:'devices'},
    capabilities:{label:'Capabilities',icon:'◇',description:'Find or manage a Vishnu capability or integration.',module:null},
    visualize:{label:'Visualize',icon:'◩',description:'Create or inspect a visual representation.',module:null},
    voice:{label:'Voice',icon:'◖',description:'Use Vishnu voice or Voice Lab.',module:null}
  };

  const RULES={
    projects:[
      [/\b(project|workspace|milestone|sprint|backlog|work order|workorder)\b/g,0.34],
      [/\b(assign|continue|resume|status|blocked|next task|plan)\b/g,0.12],
      [/\b(PR|pull request|branch|repository|repo)\b/gi,0.12]
    ],
    memory:[
      [/\b(remember|memory|memories|recall|what did i|we discussed|last time|past chat|previous conversation)\b/g,0.42],
      [/\b(saved|history|earlier|before)\b/g,0.10]
    ],
    files:[
      [/\b(file|document|pdf|spreadsheet|sheet|slides?|presentation|attachment|folder)\b/g,0.34],
      [/\b(find|open|read|summari[sz]e|extract|compare|upload|download)\b/g,0.12],
      [/\b[\w.-]+\.(pdf|docx?|xlsx?|pptx?|csv|txt|md|json|ya?ml|png|jpe?g)\b/gi,0.40]
    ],
    research:[
      [/\b(research|investigate|study|deep study|look into|evidence|sources?|fact[- ]check)\b/g,0.38],
      [/\b(compare|market|latest|current|news|competitor|trend)\b/g,0.12]
    ],
    code:[
      [/\b(code|coding|implement|debug|bug|fix|refactor|test|tests|function|class|API|endpoint|database|migration|deploy)\b/gi,0.30],
      [/\b(github|git|commit|branch|pull request|PR|typescript|javascript|python|react|swift|kotlin|sql)\b/gi,0.16]
    ],
    automation:[
      [/\b(remind|reminder|schedule|scheduled|every day|every week|daily|weekly|monthly|when .* happens|notify me|alert me|monitor)\b/g,0.42],
      [/\b(tomorrow|tonight|morning|afternoon|evening|at \d{1,2}(:\d{2})?\s?(am|pm)?|in \d+ (minute|hour|day|week)s?)\b/gi,0.14]
    ],
    devices:[
      [/\b(device|phone|iphone|ipad|android|laptop|desktop|computer|bluetooth|wifi|wi-fi|screen|camera|microphone|battery|cpu)\b/g,0.32],
      [/\b(turn on|turn off|enable|disable|inspect|control|connect|disconnect|pair|revoke)\b/g,0.18]
    ],
    capabilities:[
      [/\b(capability|capabilities|integration|connector|plugin|tool|MCP|OpenAPI)\b/gi,0.38],
      [/\b(connect|install|manage|credential|provider|API key)\b/gi,0.13]
    ],
    visualize:[
      [/\b(visuali[sz]e|diagram|chart|graph|architecture|flowchart|map|render|image|mockup|wireframe)\b/g,0.40],
      [/\b(show me|draw|create|generate|design)\b/g,0.10]
    ],
    voice:[
      [/\b(voice|speak|talk|call|phone call|telephony|speech|audio|TTS|STT|transcri(?:be|ption))\b/gi,0.40],
      [/\b(voice lab|clone voice|microphone)\b/gi,0.20]
    ]
  };

  const clamp=value=>Math.max(0,Math.min(0.99,value));
  const normalize=value=>String(value||'').trim().replace(/\s+/g,' ');

  function classifyDraft(value){
    const text=normalize(value);
    if(text.length<3)return {intent:'chat',confidence:0,alternatives:[],text};
    const lower=text.toLowerCase();
    const rows=Object.entries(RULES).map(([intent,rules])=>{
      let score=0.18;
      for(const [pattern,weight] of rules){
        pattern.lastIndex=0;
        const matches=lower.match(pattern);
        if(matches)score+=weight*Math.min(matches.length,2);
      }
      return {intent,confidence:clamp(score)};
    }).sort((a,b)=>b.confidence-a.confidence);
    const best=rows[0],second=rows[1];
    // One weak keyword should never steal the normal conversation surface.
    if(!best||best.confidence<0.51)return {intent:'chat',confidence:0.45,alternatives:rows.slice(0,2),text};
    const margin=best.confidence-(second?.confidence||0);
    const confidence=clamp(best.confidence+(margin>=0.20?0.08:0));
    return {...best,confidence,alternatives:rows.slice(1,3),text};
  }

  function stableIntent(previous,candidate){
    const prev=previous||{intent:'chat',confidence:0,pendingIntent:null,pendingWins:0};
    if(!candidate||candidate.intent==='chat')return {...prev,intent:'chat',confidence:candidate?.confidence||0,pendingIntent:null,pendingWins:0};
    if(prev.intent==='chat'||prev.intent===candidate.intent)return {intent:candidate.intent,confidence:candidate.confidence,pendingIntent:null,pendingWins:0};
    if(candidate.confidence>=0.93||candidate.confidence>=prev.confidence+0.24)return {intent:candidate.intent,confidence:candidate.confidence,pendingIntent:null,pendingWins:0};
    const wins=prev.pendingIntent===candidate.intent?(prev.pendingWins||0)+1:1;
    if(wins>=2&&candidate.confidence>=0.64)return {intent:candidate.intent,confidence:candidate.confidence,pendingIntent:null,pendingWins:0};
    return {...prev,pendingIntent:candidate.intent,pendingWins:wins};
  }

  let state={intent:'chat',confidence:0,pendingIntent:null,pendingWins:0};
  let dismissedFor='';

  function injectStyle(){
    if(document.getElementById('vAdaptiveComposerStyle'))return;
    const style=document.createElement('style');
    style.id='vAdaptiveComposerStyle';
    style.textContent=`
      #composer{position:relative}
      .v-adaptive-preview{position:absolute;left:0;right:0;bottom:calc(100% + 9px);z-index:58;display:none;align-items:center;gap:10px;min-height:54px;padding:9px 10px;border:1px solid rgba(145,157,179,.32);border-radius:16px;background:color-mix(in srgb,var(--panel,#fff) 94%,transparent);box-shadow:0 10px 32px rgba(18,25,38,.14);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);color:var(--text,#151922);pointer-events:none}
      body.chat-experience:not(.home-landing) .v-adaptive-preview{bottom:calc(100% + 56px)}
      .v-adaptive-preview[data-open="true"]{display:flex;animation:vAdaptiveIn .14s ease-out}
      .v-adaptive-icon{display:grid;place-items:center;flex:0 0 34px;width:34px;height:34px;border-radius:11px;background:rgba(112,91,255,.10);font-size:15px;font-weight:700}
      .v-adaptive-copy{min-width:0;flex:1;display:grid;gap:2px}
      .v-adaptive-copy strong{font-size:13px;line-height:1.2;font-weight:700}
      .v-adaptive-copy small{font-size:11.5px;line-height:1.25;color:var(--muted,#687083);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .v-adaptive-actions{display:flex;align-items:center;gap:6px;flex:0 0 auto;pointer-events:auto}
      .v-adaptive-action,.v-adaptive-dismiss{min-height:34px;border-radius:10px;border:1px solid rgba(125,137,159,.28);background:transparent;color:inherit;padding:0 10px;font:inherit;font-size:11.5px;font-weight:650;cursor:pointer}
      .v-adaptive-action{background:rgba(112,91,255,.10);border-color:rgba(112,91,255,.22)}
      .v-adaptive-dismiss{width:34px;padding:0;font-size:17px;color:var(--muted,#687083)}
      .v-adaptive-preview:focus-within{outline:2px solid rgba(112,91,255,.35);outline-offset:2px}
      @keyframes vAdaptiveIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
      @media(max-width:760px){
        .v-adaptive-preview{position:fixed;left:max(14px,env(safe-area-inset-left));right:max(14px,env(safe-area-inset-right));bottom:calc(var(--shared-composer-bottom,24px) + var(--shared-composer-h,54px) + 11px);min-height:50px;padding:8px 9px;border-radius:15px}
        body.chat-experience:not(.home-landing) .v-adaptive-preview{bottom:calc(var(--shared-composer-bottom,24px) + var(--shared-composer-h,54px) + 60px)}
        body.keyboard-open .v-adaptive-preview{bottom:max(calc(var(--shared-composer-bottom,24px) + var(--shared-composer-h,54px) + 11px),calc(100dvh - var(--keyboard-visible-height,100dvh) + var(--shared-composer-bottom,24px) + var(--shared-composer-h,54px) + 11px))}
        body.chat-experience.keyboard-open:not(.home-landing) .v-adaptive-preview{bottom:max(calc(var(--shared-composer-bottom,24px) + var(--shared-composer-h,54px) + 60px),calc(100dvh - var(--keyboard-visible-height,100dvh) + var(--shared-composer-bottom,24px) + var(--shared-composer-h,54px) + 60px))}
        .v-adaptive-copy small{max-width:44vw}.v-adaptive-action{padding:0 8px}
      }
      @media(max-width:380px){.v-adaptive-copy small{display:none}.v-adaptive-preview{gap:7px}.v-adaptive-icon{width:31px;height:31px;flex-basis:31px}.v-adaptive-action{font-size:11px}}
      @media(prefers-reduced-motion:reduce){.v-adaptive-preview[data-open="true"]{animation:none}}
    `;
    document.head.append(style);
  }

  function createPreview(composer){
    let preview=document.getElementById('vAdaptivePreview');
    if(preview)return preview;
    preview=document.createElement('section');
    preview.id='vAdaptivePreview';
    preview.className='v-adaptive-preview';
    preview.dataset.open='false';
    preview.setAttribute('role','region');
    preview.setAttribute('aria-label','Vishnu adaptive suggestion');
    preview.innerHTML='<span class="v-adaptive-icon" aria-hidden="true">✦</span><span class="v-adaptive-copy" aria-live="polite" aria-atomic="true"><strong></strong><small></small></span><span class="v-adaptive-actions"><button type="button" class="v-adaptive-action"></button><button type="button" class="v-adaptive-dismiss" aria-label="Dismiss suggestion">×</button></span>';
    preview.querySelector('.v-adaptive-dismiss').addEventListener('click',()=>{
      dismissedFor=normalize(document.getElementById('message')?.value);
      preview.dataset.open='false';
    });
    preview.querySelector('.v-adaptive-action').addEventListener('click',activateCurrent);
    composer.prepend(preview);
    return preview;
  }

  function render(candidate){
    const input=document.getElementById('message'),composer=document.getElementById('composer');
    if(!input||!composer)return;
    injectStyle();
    const preview=createPreview(composer),text=normalize(input.value),intent=INTENTS[state.intent]||INTENTS.chat;
    const show=state.intent!=='chat'&&state.confidence>=0.60&&text&&text!==dismissedFor;
    preview.dataset.open=show?'true':'false';
    if(!show)return;
    preview.dataset.intent=state.intent;
    preview.querySelector('.v-adaptive-icon').textContent=intent.icon;
    preview.querySelector('strong').textContent=`Looks like ${intent.label}`;
    preview.querySelector('small').textContent=intent.description;
    const action=preview.querySelector('.v-adaptive-action');
    action.textContent=intent.module?`Open ${intent.label}`:'Continue with Vishnu';
    action.setAttribute('aria-label',intent.module?`Open ${intent.label} while keeping this draft`:`Send this ${intent.label.toLowerCase()} request through Vishnu`);
    window.dispatchEvent(new CustomEvent('vishnu:adaptive-preview',{detail:{...candidate,stableIntent:state.intent,stableConfidence:state.confidence}}));
  }

  function update(){
    const input=document.getElementById('message');
    if(!input)return;
    const candidate=classifyDraft(input.value);
    state=stableIntent(state,candidate);
    render(candidate);
  }

  function activateCurrent(){
    const input=document.getElementById('message');
    if(!input)return;
    const current=INTENTS[state.intent]||INTENTS.chat;
    const detail={intent:state.intent,confidence:state.confidence,text:normalize(input.value),module:current.module};
    const event=new CustomEvent('vishnu:adaptive-intent',{detail,cancelable:true});
    window.dispatchEvent(event);
    if(event.defaultPrevented)return;
    if(current.module&&typeof window.openModule==='function'){
      try{
        const result=window.openModule(current.module);
        Promise.resolve(result).catch(()=>{});
        document.getElementById('vAdaptivePreview')?.setAttribute('data-open','false');
        return;
      }catch(_error){/* Canonical Send remains the fail-safe. */}
    }
    const send=document.getElementById('sendButton');
    if(send&&!send.disabled)send.click();
  }

  function mount(){
    const input=document.getElementById('message'),composer=document.getElementById('composer');
    if(!input||!composer)return false;
    injectStyle();
    createPreview(composer);
    if(!input.dataset.adaptiveComposerBound){
      input.dataset.adaptiveComposerBound='true';
      input.addEventListener('input',()=>{dismissedFor='';update()});
      input.addEventListener('focus',update);
      input.addEventListener('keydown',event=>{
        if(event.key==='Escape'){
          dismissedFor=normalize(input.value);
          document.getElementById('vAdaptivePreview')?.setAttribute('data-open','false');
        }
      });
    }
    update();
    return true;
  }

  const api={intents:Object.freeze({...INTENTS}),classifyDraft,stableIntent,mount,refresh:update,get state(){return {...state}}};
  window.__vishnuAdaptiveComposer=api;
  window.vishnuAdaptiveComposer=api;

  if(!mount()){
    const observer=new MutationObserver(()=>{if(mount())observer.disconnect()});
    observer.observe(document.documentElement,{childList:true,subtree:true});
  }
})();
