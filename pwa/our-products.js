(()=>{
  'use strict';
  const $=selector=>document.querySelector(selector);
  const $$=selector=>[...document.querySelectorAll(selector)];
  const state={products:[],summary:{},activity:[],type:'all',sort:'recent',query:'',detail:null,detailTab:'overview'};
  const labels={ai_employee:'AI Employee',agent:'Agent',agent_team:'Agent Team',automation:'Automation',workflow:'Workflow',tool:'Tool',knowledge_assistant:'Knowledge Assistant',integration:'Integration',business_system:'Business System',custom:'Custom Product'};
  const platformLabels={web:'Web',pwa:'PWA',android:'Android',ios:'iOS',windows:'Windows',macos:'Mac',linux:'Linux',docker:'Server',api:'API',worker:'Worker'};
  const localBuildTargets=new Set(['web','pwa','api','worker']);
  const aiLabels={disabled:'AI: Disabled',client_api:'AI: Client-owned',managed:'AI: Our Managed AI',local:'AI: Local / self-hosted',hybrid:'AI: Hybrid'};
  const icons={ai_employee:'♙',agent:'◇',agent_team:'♙',automation:'⚙',workflow:'⌁',tool:'⌘',knowledge_assistant:'▤',integration:'↔',business_system:'▦',custom:'⬡'};
  const esc=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));

  async function api(path,options={}){
    const response=await fetch(`/iphone/api/products${path}`,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(options.headers||{})},...options});
    if(response.status===204)return null;
    let body=null;
    try{body=await response.json()}catch{body={detail:`Request failed (${response.status})`}}
    if(!response.ok)throw new Error(typeof body?.detail==='string'?body.detail:`Request failed (${response.status})`);
    return body;
  }

  function notice(message,error=false){
    const node=$('#message');node.textContent=message;node.classList.toggle('error',error);node.classList.remove('hidden');
    clearTimeout(notice.timer);notice.timer=setTimeout(()=>node.classList.add('hidden'),4500);
  }

  function statusLabel(value){return String(value||'').replaceAll('_',' ').replace(/\b\w/g,char=>char.toUpperCase())}
  function timeAgo(value){
    if(!value)return '—'; const stamp=new Date(value); if(Number.isNaN(stamp.getTime()))return value;
    const seconds=Math.max(0,Math.floor((Date.now()-stamp.getTime())/1000));
    if(seconds<60)return 'just now'; if(seconds<3600)return `${Math.floor(seconds/60)}m ago`; if(seconds<86400)return `${Math.floor(seconds/3600)}h ago`; return `${Math.floor(seconds/86400)}d ago`;
  }

  function renderSummary(){
    const s=state.summary||{};
    $('#metricTotal').textContent=s.total??0;$('#metricDevelopment').textContent=s.development??0;$('#metricReady').textContent=s.ready??0;
    $('#metricLive').textContent=s.live??0;$('#metricClients').textContent=s.clients??0;$('#metricAttention').textContent=s.needs_attention??0;
  }

  function productCard(product){
    const targets=(product.targets||[]).filter(item=>item.enabled).map(item=>`<span class="chip">${esc(platformLabels[item.target]||item.target)}</span>`).join('');
    return `<article class="product-card" data-product-id="${esc(product.id)}">
      <div class="card-head"><div class="card-title-wrap"><span class="product-avatar">${icons[product.product_type]||'⬡'}</span><div class="card-title"><h3>${esc(product.name)}</h3><small>${esc(labels[product.product_type]||product.product_type)}</small></div></div><span class="status ${esc(product.status)}">${esc(statusLabel(product.status))}</span></div>
      <p class="description">${esc(product.description||'No description yet. Open the product to configure its purpose and components.')}</p>
      <div class="meta"><span>▣ Client <b>${esc(product.client_name||'Internal use')}</b></span><span>◇ Version <b>${esc(product.version)}</b></span><span>◫ Components <b>${Number(product.component_count||0)}</b></span></div>
      <div class="chips">${targets||'<span class="chip">No delivery target</span>'}</div>
      <div class="ai-strip">${esc(aiLabels[product.ai_mode]||product.ai_mode)}</div>
      <div class="card-footer"><button class="open" data-action="open">Open</button><button data-action="manifest">Manifest</button></div>
    </article>`;
  }

  function renderProducts(){
    const grid=$('#productGrid'),empty=$('#emptyState');
    grid.innerHTML=state.products.map(productCard).join('');
    const noProducts=state.products.length===0;grid.classList.toggle('hidden',noProducts);empty.classList.toggle('hidden',!noProducts);
  }

  function renderActivity(){
    const node=$('#activityList');
    if(!state.activity.length){node.innerHTML='<p class="muted">No product activity yet.</p>';return}
    node.innerHTML=state.activity.slice(0,8).map(item=>`<div class="activity-item"><span class="activity-dot"></span><span><b>${esc(item.product_name||'Product')}</b> ${esc(item.message)}</span><time>${esc(timeAgo(item.created_at))}</time></div>`).join('');
  }

  async function load(){
    try{
      const params=new URLSearchParams({q:state.query,product_type:state.type,sort:state.sort});
      const [products,summary,activity]=await Promise.all([api(`?${params}`),api('/summary'),api('/activity?limit=30')]);
      state.products=products.products||[];state.summary=summary.summary||{};state.activity=activity.activity||[];
      renderProducts();renderSummary();renderActivity();
    }catch(error){
      $('#productGrid').innerHTML='';$('#emptyState').classList.add('hidden');
      notice(error.message==='This browser is not trusted or its session was revoked'?'Open this page from a trusted Vishnu owner session.':error.message,true);
    }
  }

  async function refreshDetail(productId,tab=state.detailTab){
    const body=await api(`/${encodeURIComponent(productId)}`);state.detail=body;state.detailTab=tab;renderDetail();
  }

  function renderOverview(product){
    const targets=(product.targets||[]).filter(item=>item.enabled).map(item=>platformLabels[item.target]||item.target).join(', ')||'None configured';
    return `<div class="detail-section"><div class="detail-grid">
      <div class="detail-tile"><small>Status</small><strong>${esc(statusLabel(product.status))}</strong></div>
      <div class="detail-tile"><small>Version</small><strong>${esc(product.version)}</strong></div>
      <div class="detail-tile"><small>Client</small><strong>${esc(product.client_name||'Internal use')}</strong></div>
      <div class="detail-tile"><small>AI mode</small><strong>${esc(statusLabel(product.ai_mode))}</strong></div>
      <div class="detail-tile"><small>Platforms</small><strong>${esc(targets)}</strong></div>
      <div class="detail-tile"><small>Components</small><strong>${Number(product.component_count||0)}</strong></div>
    </div><div class="detail-tile"><small>Description</small><strong>${esc(product.description||'No description yet.')}</strong></div>
    ${product.source_project_id?`<div class="detail-tile"><small>Source project</small><strong>${esc(product.source_project_id)}</strong></div>`:''}</div>`;
  }

  function renderAI(product){
    const p=product.ai_policy||{};
    return `<div class="detail-section"><div class="warning">AI is optional. Client products can run without AI, use the client's provider, use managed AI, use a local model, or combine them. Raw API keys are never accepted here; use an encrypted vault reference.</div>
      <div class="setting-row"><div><b>AI mode</b><div class="muted">Who provides model intelligence for this product.</div></div><select id="aiMode"><option value="disabled" ${product.ai_mode==='disabled'?'selected':''}>No AI</option><option value="client_api" ${product.ai_mode==='client_api'?'selected':''}>Client provides API</option><option value="managed" ${product.ai_mode==='managed'?'selected':''}>Our managed AI</option><option value="local" ${product.ai_mode==='local'?'selected':''}>Local / self-hosted</option><option value="hybrid" ${product.ai_mode==='hybrid'?'selected':''}>Hybrid</option></select></div>
      <div class="setting-row"><div><b>Provider</b><div class="muted">OpenAI, Anthropic, Gemini, Azure, OpenRouter or compatible gateway.</div></div><input id="aiProvider" value="${esc(p.provider||'')}" placeholder="Provider"></div>
      <div class="setting-row"><div><b>Model</b><div class="muted">Optional preferred model; the runtime may route by capability later.</div></div><input id="aiModel" value="${esc(p.model||'')}" placeholder="Model"></div>
      <div class="setting-row"><div><b>Secret reference</b><div class="muted">Reference to encrypted secret storage, never the API key itself.</div></div><input id="aiSecretRef" value="${esc(p.secret_ref||'')}" placeholder="vault://client/acme/openai"></div>
      <div class="setting-row"><div><b>Fallback</b><div class="muted">Allow a configured fallback provider in hybrid/managed modes.</div></div><label><input id="aiFallback" type="checkbox" ${p.allow_fallback?'checked':''}> Enabled</label></div>
      <button class="button primary" id="saveAI">Save AI policy</button></div>`;
  }

  function renderPlatforms(product){
    const enabled=new Set((product.targets||[]).filter(item=>item.enabled).map(item=>item.target));
    return `<div class="detail-section"><p class="muted">Choose where this product is intended to run. Web, PWA, API and Worker have verified runtime-bundle builders. Native mobile/desktop selections do not claim a signed binary exists until their platform runner and signing flow qualify it.</p><div class="platform-list">${Object.entries(platformLabels).map(([value,label])=>`<label class="platform-toggle"><input type="checkbox" data-platform="${value}" ${enabled.has(value)?'checked':''}><span><b>${esc(label)}</b></span></label>`).join('')}</div><button class="button primary" id="savePlatforms">Save platforms</button></div>`;
  }

  function renderComponents(components){
    return `<div class="detail-section"><div>${components.length?components.map(component=>`<div class="build-row"><div><b>${esc(component.name)}</b><div class="muted">${esc(component.component_type)}${component.component_ref?` · ${esc(component.component_ref)}`:''}</div></div><button class="button secondary" data-remove-component="${esc(component.id)}">Remove</button></div>`).join(''):'<p class="muted">No components connected yet.</p>'}</div>
      <div class="detail-tile"><b>Add component</b><div class="form-grid"><label>Type<input id="componentType" placeholder="agent / workflow / automation / tool"></label><label>Name<input id="componentName" placeholder="Lead Research Agent"></label><label class="span-2">Reference<input id="componentRef" placeholder="Optional internal component ID"></label></div><button class="button primary" id="addComponent">Add component</button></div></div>`;
  }

  function renderBuild(product,builds){
    const targets=(product.targets||[]).filter(item=>item.enabled);
    const targetRows=targets.map(item=>{
      const local=localBuildTargets.has(item.target);const action=local?'Generate verified bundle':'Request platform build';
      const detail=local?'Local builder available · frozen version required':`External ${platformLabels[item.target]||item.target} compiler/signing evidence required`;
      return `<div class="build-row"><div><b>${esc(platformLabels[item.target]||item.target)}</b><div class="muted">${esc(detail)}</div></div><button class="button primary" data-build-target="${esc(item.target)}">${esc(action)}</button></div>`;
    }).join('');
    const history=builds.map(build=>{
      const ready=Boolean(build.metadata?.artifact_ready);const local=localBuildTargets.has(build.target);
      const actions=ready?`<button class="button secondary" data-download-build="${esc(build.id)}">Download</button>`:(local&&['failed','cancelled'].includes(build.status)?`<button class="button secondary" data-retry-build="${esc(build.id)}">Retry</button>`:`<span class="status ${esc(build.status)}">${esc(statusLabel(build.status))}</span>`);
      return `<div class="build-row"><div><b>Build #${Number(build.build_number||0)} · ${esc(platformLabels[build.target]||build.target)} · ${esc(build.version)}</b><div class="muted">${ready?'Verified artifact generated':`${esc(statusLabel(build.status))} · ${esc(timeAgo(build.created_at))}`}</div></div>${actions}</div>`;
    }).join('');
    return `<div class="detail-section"><div class="warning">Web/PWA/API/Worker builders generate bounded client bundles from frozen manifests and verify their checksum before marking the file downloadable. APK, IPA, EXE, MSI, DMG and other native artifacts remain unavailable until a platform-specific compiler and signing runner supplies verified evidence.</div>${targets.length?targetRows:'<p class="muted">Enable at least one platform first.</p>'}<h3>Build history</h3>${builds.length?history:'<p class="muted">No builds requested yet.</p>'}</div>`;
  }

  async function renderManifest(product){
    $('#detailBody').innerHTML='<p class="muted">Loading manifest…</p>';
    try{const body=await api(`/${encodeURIComponent(product.id)}/manifest`);$('#detailBody').innerHTML=`<div class="warning">Canonical product definition. Secrets are intentionally excluded.</div><pre class="code-box">${esc(JSON.stringify(body.manifest,null,2))}</pre><button class="button secondary" id="freezeVersion">Freeze version ${esc(product.version)}</button>`}catch(error){$('#detailBody').innerHTML=`<p class="message error">${esc(error.message)}</p>`}
  }

  function renderDetail(){
    if(!state.detail)return; const product=state.detail.product;
    $('#detailName').textContent=product.name;$('#detailKind').textContent=(labels[product.product_type]||product.product_type).toUpperCase();$('#detailSubtitle').textContent=`${product.client_name||'Internal use'} · v${product.version}`;
    $$('#detailTabs button').forEach(button=>button.classList.toggle('active',button.dataset.tab===state.detailTab));
    if(state.detailTab==='overview')$('#detailBody').innerHTML=renderOverview(product);
    else if(state.detailTab==='ai')$('#detailBody').innerHTML=renderAI(product);
    else if(state.detailTab==='platforms')$('#detailBody').innerHTML=renderPlatforms(product);
    else if(state.detailTab==='components')$('#detailBody').innerHTML=renderComponents(state.detail.components||[]);
    else if(state.detailTab==='build')$('#detailBody').innerHTML=renderBuild(product,state.detail.builds||[]);
    else if(state.detailTab==='manifest')renderManifest(product);
  }

  function openCreate(type='ai_employee'){$('#productForm').reset();$('#productType').value=type;$('#productDialog').showModal()}
  function close(dialog){if(dialog?.open)dialog.close()}

  $('#createButton').addEventListener('click',()=>openCreate());$('#emptyCreate').addEventListener('click',()=>openCreate());
  $$('[data-quick-type]').forEach(button=>button.addEventListener('click',()=>openCreate(button.dataset.quickType)));
  $$('[data-close]').forEach(button=>button.addEventListener('click',()=>close($('#productDialog'))));
  const openConvert=()=>$('#convertDialog').showModal();$('#convertButton').addEventListener('click',openConvert);$('#convertBottom').addEventListener('click',openConvert);$$('[data-close-convert]').forEach(button=>button.addEventListener('click',()=>close($('#convertDialog'))));
  $$('[data-close-detail]').forEach(button=>button.addEventListener('click',()=>close($('#detailDialog'))));

  $('#productForm').addEventListener('submit',async event=>{
    event.preventDefault();const data=new FormData(event.currentTarget);const payload={name:data.get('name'),product_type:data.get('product_type'),description:data.get('description'),client_name:data.get('client_name'),ai_mode:data.get('ai_mode'),targets:data.getAll('targets')};
    try{await api('',{method:'POST',body:JSON.stringify(payload)});close($('#productDialog'));notice('Product created.');await load()}catch(error){notice(error.message,true)}
  });

  $('#convertForm').addEventListener('submit',async event=>{
    event.preventDefault();const data=new FormData(event.currentTarget);const id=String(data.get('project_id')||'').trim();
    try{await api(`/from-project/${encodeURIComponent(id)}`,{method:'POST',body:JSON.stringify({product_type:data.get('product_type'),client_name:data.get('client_name')})});close($('#convertDialog'));notice('Project promoted to Our Products.');await load()}catch(error){notice(error.message,true)}
  });

  let searchTimer;$('#search').addEventListener('input',event=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.query=event.target.value.trim();load()},250)});
  $('#sort').addEventListener('change',event=>{state.sort=event.target.value;load()});
  $('#filters').addEventListener('click',event=>{const button=event.target.closest('[data-type]');if(!button)return;$$('.filter').forEach(item=>item.classList.remove('active'));button.classList.add('active');state.type=button.dataset.type;load()});
  $('#refreshActivity').addEventListener('click',load);

  $('#productGrid').addEventListener('click',async event=>{
    const card=event.target.closest('[data-product-id]');const action=event.target.closest('[data-action]');if(!card||!action)return;
    try{await refreshDetail(card.dataset.productId,action.dataset.action==='manifest'?'manifest':'overview');$('#detailDialog').showModal()}catch(error){notice(error.message,true)}
  });

  $('#detailTabs').addEventListener('click',event=>{const button=event.target.closest('[data-tab]');if(!button||!state.detail)return;state.detailTab=button.dataset.tab;renderDetail()});
  $('#detailBody').addEventListener('click',async event=>{
    if(!state.detail)return;const id=state.detail.product.id;
    try{
      if(event.target.id==='saveAI'){
        const payload={mode:$('#aiMode').value,provider:$('#aiProvider').value.trim(),model:$('#aiModel').value.trim(),secret_ref:$('#aiSecretRef').value.trim(),allow_fallback:$('#aiFallback').checked};
        await api(`/${encodeURIComponent(id)}/ai-policy`,{method:'PUT',body:JSON.stringify(payload)});notice('AI policy saved.');await refreshDetail(id,'ai');await load();
      }else if(event.target.id==='savePlatforms'){
        const targets=$$('[data-platform]').map(input=>({target:input.dataset.platform,enabled:input.checked,config:{}}));
        await api(`/${encodeURIComponent(id)}/targets`,{method:'PUT',body:JSON.stringify({targets})});notice('Delivery targets saved.');await refreshDetail(id,'platforms');await load();
      }else if(event.target.id==='addComponent'){
        const name=$('#componentName').value.trim();if(!name)throw new Error('Component name is required');
        await api(`/${encodeURIComponent(id)}/components`,{method:'POST',body:JSON.stringify({component_type:$('#componentType').value.trim()||'custom',name,component_ref:$('#componentRef').value.trim()||null,config:{}})});notice('Component added.');await refreshDetail(id,'components');await load();
      }else if(event.target.dataset.removeComponent){
        await api(`/${encodeURIComponent(id)}/components/${encodeURIComponent(event.target.dataset.removeComponent)}`,{method:'DELETE'});notice('Component removed.');await refreshDetail(id,'components');await load();
      }else if(event.target.dataset.downloadBuild){
        window.location.assign(`/iphone/api/products/${encodeURIComponent(id)}/builds/${encodeURIComponent(event.target.dataset.downloadBuild)}/artifact`);
      }else if(event.target.dataset.retryBuild){
        const buildId=event.target.dataset.retryBuild;await api(`/${encodeURIComponent(id)}/builds/${encodeURIComponent(buildId)}/execute`,{method:'POST'});notice('Verified runtime bundle generated.');await refreshDetail(id,'build');await load();
      }else if(event.target.dataset.buildTarget){
        const target=event.target.dataset.buildTarget;
        if(localBuildTargets.has(target)){
          const distribution=await api(`/${encodeURIComponent(id)}/distribution/status`);
          if(!distribution.current_version_frozen)throw new Error(`Freeze version ${state.detail.product.version} in Manifest before generating a verified bundle.`);
        }
        const requested=await api(`/${encodeURIComponent(id)}/builds`,{method:'POST',body:JSON.stringify({target})});
        if(localBuildTargets.has(target)){
          await api(`/${encodeURIComponent(id)}/builds/${encodeURIComponent(requested.build.id)}/execute`,{method:'POST'});notice(`Verified ${platformLabels[target]||target} bundle generated.`);
        }else notice(`Build request recorded for ${platformLabels[target]||target}; waiting for a verified platform runner.`);
        await refreshDetail(id,'build');await load();
      }else if(event.target.id==='freezeVersion'){
        await api(`/${encodeURIComponent(id)}/versions`,{method:'POST',body:JSON.stringify({version:state.detail.product.version,notes:'Frozen from Our Products workspace'})});notice(`Version ${state.detail.product.version} frozen.`);await refreshDetail(id,'manifest');
      }
    }catch(error){notice(error.message,true)}
  });

  load();
})();
