/* Vishnu 2.0 P2-02A — Personal Chat presentation, not a chat authority.
 * Existing Conversation/Voice API, context guards, owner identity and Work governance own actions.
 */
(() => {
  'use strict';
  if (window.__vishnuP202A) return;
  const $ = id => document.getElementById(id);
  const bridge = () => window.vishnuChatBridge;
  // The canonical context projection, never a client-side guess, identifies a Project chat.
  // A Project conversation keeps its existing Project UI rather than acquiring Personal controls.
  const projectContext = () => /^\\s*Project\\s*[·:]/i.test($('vContextChip')?.querySelector('span')?.textContent||'');
  const active = () => document.body.classList.contains('chat-experience') &&
    !$('voicePanel')?.classList.contains('hidden') && !projectContext();
  const qs = (sel,root=document) => root.querySelector(sel);
  const create = (tag,cls,txt) => {
    const e=document.createElement(tag); if(cls)e.className=cls;
    if(txt!==undefined)e.textContent=String(txt);return e;
  };
  const button=(label,cls,handler)=>{
    const b=create('button',cls,label);b.type='button';b.addEventListener('click',handler);return b;
  };
  const notify = message => bridge()?.showToast?.(message);
  const guarded = async work => {
    try {await work();}
    catch(error){notify(error?.message||'This action is unavailable.');}
  };
  const navigate = name => bridge()?.openModule?.(name);
  const drafts = new Map(); // ephemeral only; never sync personal draft text to unapproved storage.
  const key = id => id ? 'conversation:'+String(id) : 'personal:new';
  let lastId=null, lastActive=false, profile=null, scheduled=false, modelState=null;
  const refs = {};

  function installShell(){
    const presence=qs('#voicePanel .presence');
    if(!presence||$('p202Header'))return;
    const head=create('header','p202-header');
    head.id='p202Header';head.hidden=true;
    head.setAttribute('aria-label','Personal conversation');
    const orb=create('span','p202-head-core');
    orb.setAttribute('aria-hidden','true');
    orb.append(create('span','p202-head-core-inner'));
    const identity=create('div','p202-head-identity');
    const name=create('strong','p202-conversation-name','New Chat');
    const scope=button('Personal Conversation ▾','p202-context',()=>{
      // Canonical context picker enforces owner/project boundaries.
      const native=$('vContextChip');
      if(native)native.click();else notify('Conversation context controls are unavailable.');
    });
    identity.append(name,scope);
    const opts=button('•••','p202-more',()=>{
      if(bridge()?.current?.id && !$('chatMenuButton')?.classList.contains('hidden'))$('chatMenuButton').click();
      else $('chatDetailsTop')?.click();
    });
    opts.setAttribute('aria-label','Conversation options');
    head.append(orb,identity,opts);
    presence.insertBefore(head,presence.firstChild);
    refs.title=name;refs.scope=scope;
    const intro=$('homeIntro');
    if(intro){
      const welcome=create('section','p202-welcome');
      welcome.id='p202Welcome';welcome.hidden=true;
      const art=create('img','p202-welcome-core');
      art.src='/iphone/assets/genesis/vishnu-core.png';
      art.alt='';art.loading='lazy';art.decoding='async';
      const hello=create('h2','p202-hello','Hello');
      const line=create('p','p202-welcome-main',"I'm Vishnu, your personal AI assistant.");
      const helper=create('p','p202-welcome-helper','Ask me anything, get ideas, plan your day, or just have a conversation.');
      welcome.append(art,hello,line,helper);
      const chips=create('div','p202-suggestions');chips.setAttribute('aria-label','Suggested conversation starters');
      [
        ['Plan my day','▣','Help me organize my day. First ask about my real commitments and priorities, then suggest a balanced plan.'],
        ['Brainstorm ideas','♧','Help me brainstorm ideas for '],
        ['Help me write','✎','Help me write '],
        ['Learn something new','◫','Teach me something new about ']
      ].forEach(([label,glyph,text])=>{
        const b=button('', 'p202-prompt',()=>bridge()?.setDraft?.(text));
        b.append(create('span','p202-prompt-icon',glyph),create('span','',label));
        chips.append(b);
      });
      welcome.append(chips);
      const anchor=qs('.home-greeting',intro);
      if(anchor)anchor.after(welcome);else intro.prepend(welcome);
      refs.hello=hello;
    }
    // Reuse existing authenticated conversation list and CRUD handlers.
    const drawerHeader=qs('#conversationsDrawerMode .conversations-drawer-header');
    if(drawerHeader&&!$('p202NewChat')){
      const newChat=button('✎','p202-new-chat',()=>guarded(async()=>{
        if(bridge()?.getDraft?.()?.trim()) {notify('Send or clear your current draft before creating a new chat.');return;}
        await bridge().createConversation();
      }));
      newChat.id='p202NewChat';newChat.hidden=true;newChat.setAttribute('aria-label','Start a new personal conversation');
      drawerHeader.append(newChat);
      refs.drawerTitle=qs('h2',drawerHeader);
    }
    const mobileNav=create('nav','p202-mobile-nav');
    mobileNav.id='p202MobileNav';mobileNav.hidden=true;mobileNav.setAttribute('aria-label','Personal Chat navigation');
    [
      ['Home','⌂',()=>navigate('home')],
      ['Chat','▢',()=>$('message')?.focus()],
      ['Today','▣',()=>bridge()?.openTodayScreen?.('all')],
      ['Work','▦',()=>navigate('workflows')],
      ['More','•••',()=>$('historyButton')?.click()]
    ].forEach(([label,glyph,handler])=>{
      const tab=button('', 'p202-mobile-tab p202-mobile-tab-'+label.toLowerCase(),handler);
      tab.append(create('span','',glyph),create('small','',label));
      if(label==='Chat')tab.setAttribute('aria-current','page');
      mobileNav.append(tab);
    });
    document.body.append(mobileNav);
    const topbar=qs('.topbar');
    if(topbar&&!$('p202MobileActions')){
      const actions=create('div','p202-mobile-actions');actions.id='p202MobileActions';
      const bell=button('♧','p202-mobile-bell',()=>openNotifications());
      bell.setAttribute('aria-label','Open notifications');
      const owner=button('◯','p202-mobile-profile',()=>navigate('owner'));
      owner.setAttribute('aria-label','Open owner profile');
      actions.append(bell,owner);actions.hidden=true;topbar.append(actions);refs.ownerButton=owner;
      const brand=create('span','p202-mobile-brand','VISHNU');brand.setAttribute('aria-hidden','true');
      brand.hidden=true;topbar.append(brand);
    }
    const model=button('Vishnu AI ▾','p202-model',()=>openModelInfo());
    model.setAttribute('aria-label','View Vishnu AI routing and model availability');
    model.setAttribute('aria-haspopup','dialog');
    const composer=$('composer'),microphone=$('micButton'),send=$('sendButton');
    if(composer&&!$('p202ModelPlacement')){
      const wrapper=create('div','p202-model-placement');wrapper.id='p202ModelPlacement';wrapper.hidden=true;
      wrapper.append(model);
      if(microphone)composer.insertBefore(wrapper,microphone);else if(send)composer.insertBefore(wrapper,send);else composer.append(wrapper);
    }
    refs.model=model;
    if($('message'))$('message').placeholder='Ask Vishnu anything…';
    const upload=$('attachmentButton');
    if(upload)upload.addEventListener('click',attachmentMenu,true);
    document.addEventListener('click',event=>{
      const btn=event.target.closest?.('[data-reference-search]');
      if(btn&&active()){
        event.preventDefault();event.stopImmediatePropagation();
        navigate('search');
      }
    },true);
    document.addEventListener('click',event=>{
      if(event.target.closest?.('#chatDetailsMenuItem,#chatDetailsTop,[data-chat-detail="more"]')){
        document.body.dataset.p202DetailsExplicit='true';
      }
    },true);
    $('message')?.addEventListener('input',()=>{
      if(!active())return;
      drafts.set(key(bridge()?.current?.id),$('message').value);
    });
    // Do not replace the canonical conversation-list event handlers.
    // Stash before row clicks; restore only after a verified conversation switch.
    $('conversationManagerList')?.addEventListener('pointerdown',()=>{
      if(active())drafts.set(key(bridge()?.current?.id),$('message')?.value||'');
    },true);
    window.addEventListener('vishnu:new-chat',()=>{lastId=null;queueSync()});
    $('messageStream')?.addEventListener('click',event=>{
      const follow=event.target.closest?.('[data-p202-followup]');
      if(!follow||!active())return;
      const id=follow.dataset.p202Followup;
      const choices={
        meetings:'Revise the plan from your previous answer around my actual meetings. Ask for commitments if calendar access is unavailable.',
        personal:'Revise the previous plan to include more personal time while keeping it realistic.',
        shorter:'Give me a concise version of the plan in your previous answer.'
      };
      if(choices[id])bridge()?.setDraft?.(choices[id]);
    });
    document.addEventListener('keydown',event=>{
      if(!active()||event.defaultPrevented)return;
      if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){
        event.preventDefault();navigate('search');
      }
    });
    const bodyWatch=new MutationObserver(()=>queueSync());
    bodyWatch.observe(document.body,{attributes:true,attributeFilter:['class']});
    const stream=$('messageStream');
    if(stream)new MutationObserver(()=>queueSync()).observe(stream,{childList:true,subtree:true});
    const contextChip=$('vContextChip');
    if(contextChip)new MutationObserver(queueSync).observe(contextChip,{childList:true,subtree:true});
    const canonicalComposer=$('composer');
    if(canonicalComposer)new MutationObserver(()=>{
      // When the canonical transport accepted a send, it clears the input
      // before setting sending. Never restore already-submitted text as a draft.
      if(canonicalComposer.classList.contains('sending')&&!$('message')?.value.trim()){
        drafts.delete(key(bridge()?.current?.id));drafts.delete('personal:new');
      }
    }).observe(canonicalComposer,{attributes:true,attributeFilter:['class']});
    window.addEventListener('focus',queueSync);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)queueSync()});
    queueSync();
  }
  function openNotifications(){
    if(window.__vishnuWorkAttentionCenter?.open)return window.__vishnuWorkAttentionCenter.open('all');
    return navigate('activities'); // fallback is an actual existing owner activity view.
  }
  function attachmentMenu(event){
    if(!active())return;
    event.preventDefault();event.stopImmediatePropagation();
    if($('p202AttachmentDialog'))return;
    const dialog=create('dialog','p202-dialog');dialog.id='p202AttachmentDialog';
    const h=create('h2','','Add content');
    const p=create('p','','Conversation-only attachments are not enabled by this chat backend. You can explicitly add a supported document to your permanent Knowledge Library instead.');
    const actions=create('div','p202-dialog-actions');
    const cancel=button('Cancel','',()=>dialog.close());
    const knowledge=button('Add to Knowledge','p202-primary',()=>{
      dialog.close();$('attachmentInput')?.click();
    });
    actions.append(cancel,knowledge);dialog.append(h,p,actions);
    document.body.append(dialog);
    dialog.addEventListener('close',()=>dialog.remove(),{once:true});
    dialog.showModal();cancel.focus();
  }
  function openModelInfo(){
    if($('p202ModelDialog'))return;
    const dialog=create('dialog','p202-dialog');dialog.id='p202ModelDialog';
    const h=create('h2','','Vishnu AI');
    const state=String(modelState?.state||'').replaceAll('_',' ');
    const p=create('p','',
      state==='ready'||state==='available'?'Vishnu is using your configured AI routing. This chat does not silently switch providers.':
      state?'Configured model state: '+state+'. Change or repair your model connection in AI Settings.':
      'Model availability has not been verified. Configure an AI model in Settings. This chat will not simulate a response.');
    const actions=create('div','p202-dialog-actions');
    const dismiss=button('Close','',()=>dialog.close());
    const settings=button('AI Settings','p202-primary',()=>{dialog.close();navigate('settings')});
    actions.append(dismiss,settings);dialog.append(h,p,actions);
    document.body.append(dialog);dialog.addEventListener('close',()=>dialog.remove(),{once:true});
    dialog.showModal();dismiss.focus();
  }
  function setProfile(data){
    if(!data||typeof data!=='object')return;
    profile=data;
    modelState=data.model||null;
    const owner=String(data.owner_display_name||data.owner?.display_name||data.owner?.name||'').trim();
    const tokens=owner.split(/\s+/).filter(Boolean);
    const initials=tokens.length?tokens.slice(0,2).map(s=>s[0].toUpperCase()).join(''):'◯';
    if(refs.ownerButton)refs.ownerButton.textContent=initials;
    const sidebarName=qs('#sidebarAccountButton .sidebar-account-copy strong');
    if(sidebarName)sidebarName.textContent=owner||'Vishnu Owner';
    const avatar=qs('#sidebarAccountButton .sidebar-avatar');
    if(avatar)avatar.textContent=initials;
    refreshGreeting();
  }
  async function refreshProfile(){
    if(!active()||!bridge()?.api)return;
    try {const data=await bridge().api('/status');if(active())setProfile(data);}
    catch {
      if(refs.model)refs.model.title='AI status unavailable. Open AI Settings.';
    }
  }
  function refreshGreeting(){
    if(!refs.hello)return;
    const hour=new Date().getHours();
    const time=hour<12?'Good morning':hour<18?'Good afternoon':'Good evening';
    const owner=String(profile?.owner_display_name||profile?.owner?.display_name||profile?.owner?.name||'').trim();
    refs.hello.textContent=owner?time+', '+owner+' 👋':time+' 👋';
  }
  function updateHeader(){
    const current=bridge()?.current||{};
    const id=current.id||null;
    const title=String(current.title||'').trim();
    if(refs.title)refs.title.textContent=title&&title!=='Current conversation'&&title!=='New conversation'?title:'New Chat';
    const chip=$('vContextChip')?.querySelector('span')?.textContent||'';
    const isProject=/project/i.test(chip),unknown=/unavailable|checking/i.test(chip);
    if(refs.scope)refs.scope.textContent=isProject?chip+' ▾':unknown?'Context unverified ▾':'Personal Conversation ▾';
    if(refs.drawerTitle)refs.drawerTitle.textContent='Chats';
    if(refs.model)refs.model.textContent='◈ Vishnu AI ▾';
    const profileControl=qs('.reference-desktop-tools .reference-profile');
    if(profileControl&&profile)profileControl.textContent=refs.ownerButton?.textContent||'◯';
    if(id!==lastId){
      delete document.body.dataset.p202DetailsExplicit;
      document.body.classList.remove('chat-details-open');
      $('chatDetailDesktop')?.classList.add('hidden');
      $('chatDetailDesktop')?.setAttribute('aria-hidden','true');
      // Conversations remain owned by the canonical store; only unsent local drafts are restored.
      const before=key(lastId),after=key(id);
      if(lastId!==null||drafts.has(after)){
        const editor=$('message'),unsent=editor?.value||'';
        if(lastId!==null&&!drafts.has(before))drafts.set(before,unsent);
        if(editor&&drafts.has(after)&&!bridge()?.turnInFlight){
          const restored=drafts.get(after);
          if(restored!==unsent)bridge()?.setDraft?.(restored);
        }
      }
      lastId=id;
    }
  }
  // Parse only actual canonical assistant messages. Never generate a fictional schedule.
  function planRows(text){
    if(!/\b(plan for today|daily plan|today.s plan|schedule for today)\b/i.test(text))return [];
    const rows=[];
    for(const line of text.split('\n')){
      const clean=line.replace(/^\s*[-*|]\s*/,'').trim();
      const m=clean.match(/^(\d{1,2}(?::\d{2})?\s*(?:AM|PM)?\s*[–-]\s*\d{1,2}(?::\d{2})?\s*(?:AM|PM)?)\s*[:|\-–]\s*(.{3,100})$/i);
      if(m) rows.push({time:m[1],description:m[2].trim()});
    }
    return rows.length>=2?rows.slice(0,16):[];
  }
  function enhanceResponses(){
    const events=(bridge()?.current?.events||[]).filter(e=>e.kind==='assistant_message');
    const entries=[...document.querySelectorAll('#messageStream .message-entry.assistant')];
    entries.forEach((entry,i)=>{
      if(entry.querySelector('.p202-plan-card'))return;
      const source=String(events[i]?.payload?.text||'');
      const rows=planRows(source);
      if(!rows.length)return;
      const content=entry.querySelector('.message-content-wrap');
      if(!content)return;
      const card=create('section','p202-plan-card');
      card.setAttribute('aria-label','Schedule extracted from Vishnu response');
      card.append(create('h3','','▣ Your Plan for Today'));
      const list=create('div','p202-plan-rows');
      rows.forEach(({time,description})=>{
        const row=create('div','p202-plan-row');
        row.append(create('span','p202-plan-dot','●'),create('time','',time),create('span','',description));
        list.append(row);
      });
      card.append(list);
      const footer=content.querySelector('.message-footer');
      if(footer)content.insertBefore(card,footer);else content.append(card);
      const suggestions=create('div','p202-followups');
      [['meetings','Adjust for my meetings'],['personal','Add more personal time'],['shorter','Make a short version']].forEach(([id,label])=>{
        const b=button(label,'p202-followup',()=>{});
        b.dataset.p202Followup=id;
        suggestions.append(b);
      });
      if(footer)content.insertBefore(suggestions,footer);else content.append(suggestions);
    });
  }
  function sync(){
    scheduled=false;
    const enabled=active();
    if(enabled!==lastActive){
      lastActive=enabled;
      if(enabled){
        refreshProfile();
        const editor=$('message');if(editor)editor.placeholder='Ask Vishnu anything…';
      }
    }
    document.body.classList.toggle('p202-personal-chat',enabled);
    for(const id of ['p202Header','p202NewChat','p202MobileNav','p202MobileActions','p202ModelPlacement']){
      const el=$(id);if(el)el.hidden=!enabled;
    }
    const welcome=$('p202Welcome');if(welcome)welcome.hidden=!enabled || !document.body.classList.contains('chat-new-empty');
    const brand=qs('.p202-mobile-brand');if(brand)brand.hidden=!enabled;
    if(!enabled)return;
    updateHeader();
    if(document.body.classList.contains('chat-details-open')&&!document.body.dataset.p202DetailsExplicit){
      document.body.classList.remove('chat-details-open');
      $('chatDetailDesktop')?.classList.add('hidden');
      $('chatDetailDesktop')?.setAttribute('aria-hidden','true');
    }
    refreshGreeting();
    enhanceResponses();
  }
  function queueSync(){if(scheduled)return;scheduled=true;queueMicrotask(sync);}
  window.__vishnuP202A={version:1,authority:'presentation_only',parsePlan:planRows,refresh:queueSync};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',installShell,{once:true});
  else installShell();
})();