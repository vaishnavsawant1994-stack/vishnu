(()=>{
  'use strict';
  let currentProductId=null;
  const $=selector=>document.querySelector(selector);
  const esc=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));

  async function api(path,options={}){
    const response=await fetch(`/iphone/api/products${path}`,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(options.headers||{})},...options});
    if(response.status===204)return null;
    let body=null;try{body=await response.json()}catch{body={detail:`Request failed (${response.status})`}}
    if(!response.ok)throw new Error(typeof body?.detail==='string'?body.detail:`Request failed (${response.status})`);
    return body;
  }

  function ensureTab(){
    const tabs=$('#detailTabs');
    if(!tabs||tabs.querySelector('[data-distribution-tab]'))return;
    const button=document.createElement('button');
    button.type='button';button.dataset.distributionTab='true';button.textContent='Package & License';
    const manifest=tabs.querySelector('[data-tab="manifest"]');
    if(manifest)tabs.insertBefore(button,manifest);else tabs.appendChild(button);
  }

  async function render(){
    if(!currentProductId)return;
    const body=$('#detailBody');if(!body)return;
    body.innerHTML='<p class="muted">Loading distribution settings…</p>';
    try{
      const [statusResponse,licensesResponse,productResponse]=await Promise.all([
        api(`/${encodeURIComponent(currentProductId)}/distribution/status`),
        api(`/${encodeURIComponent(currentProductId)}/licenses`),
        api(`/${encodeURIComponent(currentProductId)}`),
      ]);
      const product=productResponse.product||{};
      const licenses=licensesResponse.licenses||[];
      const signing=statusResponse.signing_configured;
      body.innerHTML=`<div class="detail-section">
        <div class="detail-grid">
          <div class="detail-tile"><small>Portable package</small><strong>Ready</strong></div>
          <div class="detail-tile"><small>Production signing</small><strong>${signing?'Configured':'Not configured'}</strong></div>
          <div class="detail-tile"><small>Native apps</small><strong>Builder qualification required</strong></div>
        </div>
        <div class="warning">A <b>.vishnu-product</b> package contains the client product contract, integrity metadata and optional Ed25519 signature—not your full Vishnu source, owner memories, API keys or other client data.</div>
        <div class="build-row"><div><b>Production portable package</b><div class="muted">Signed and suitable for client distribution when production signing is configured.</div></div><button class="button primary" data-download-production ${signing?'':'disabled'}>Download</button></div>
        <div class="build-row"><div><b>Development portable package</b><div class="muted">Explicitly unsigned. For development/testing only, never commercial distribution.</div></div><button class="button secondary" data-download-development>Download dev package</button></div>
        ${signing?'':`<div class="warning">Configure <code>VISHNU_PRODUCT_SIGNING_PRIVATE_KEY_B64</code> and the matching product public key before issuing commercial packages or licenses.</div>`}
        <div class="detail-tile">
          <b>Issue client license</b>
          <div class="form-grid">
            <label>Client<input id="licenseClient" value="${esc(product.client_name||'')}" placeholder="Client / company"></label>
            <label>License type<select id="licenseType"><option value="organization">Organization</option><option value="per_user">Per user</option><option value="per_device">Per device</option><option value="subscription">Subscription</option><option value="perpetual">Perpetual</option></select></label>
            <label>Max users<input id="licenseUsers" type="number" min="1" placeholder="Unlimited"></label>
            <label>Max devices<input id="licenseDevices" type="number" min="1" placeholder="Unlimited"></label>
            <label>Expires at<input id="licenseExpiry" type="datetime-local"></label>
            <label><span>Managed AI</span><select id="licenseManagedAI"><option value="false">Not included</option><option value="true">Included</option></select></label>
          </div>
          <button class="button primary" data-issue-license ${signing?'':'disabled'}>Issue signed license</button>
        </div>
        <h3>Licenses</h3>
        <div data-license-list>${licenses.length?licenses.map(record=>licenseRow(record)).join(''):'<p class="muted">No licenses issued yet.</p>'}</div>
      </div>`;
    }catch(error){body.innerHTML=`<div class="message error">${esc(error.message)}</div>`}
  }

  function licenseRow(record){
    return `<div class="build-row"><div><b>${esc(record.client_name)}</b><div class="muted">${esc(record.license_id)} · ${esc(record.license_type)} · ${esc(record.status)}${record.expires_at?` · expires ${esc(record.expires_at)}`:''}</div></div><div style="display:flex;gap:6px"><button class="button secondary" data-license-download="${esc(record.license_id)}">Download</button>${record.status!=='revoked'?`<button class="button secondary" data-license-revoke="${esc(record.license_id)}">Revoke</button>`:''}</div></div>`;
  }

  document.addEventListener('click',event=>{
    const card=event.target.closest?.('[data-product-id]');
    if(card)currentProductId=card.dataset.productId;
    ensureTab();
  },true);

  document.addEventListener('click',async event=>{
    const distributionTab=event.target.closest?.('[data-distribution-tab]');
    if(distributionTab){
      document.querySelectorAll('#detailTabs button').forEach(button=>button.classList.remove('active'));
      distributionTab.classList.add('active');await render();return;
    }
    if(event.target.closest?.('#detailTabs [data-tab]')){
      document.querySelector('[data-distribution-tab]')?.classList.remove('active');return;
    }
    if(!currentProductId)return;
    if(event.target.closest?.('[data-download-production]')){
      window.location.assign(`/iphone/api/products/${encodeURIComponent(currentProductId)}/package`);return;
    }
    if(event.target.closest?.('[data-download-development]')){
      window.location.assign(`/iphone/api/products/${encodeURIComponent(currentProductId)}/package?development=true`);return;
    }
    const licenseDownload=event.target.closest?.('[data-license-download]');
    if(licenseDownload){window.location.assign(`/iphone/api/products/${encodeURIComponent(currentProductId)}/licenses/${encodeURIComponent(licenseDownload.dataset.licenseDownload)}/download`);return}
    const revoke=event.target.closest?.('[data-license-revoke]');
    if(revoke){
      try{await api(`/${encodeURIComponent(currentProductId)}/licenses/${encodeURIComponent(revoke.dataset.licenseRevoke)}/revoke`,{method:'POST'});await render()}catch(error){alert(error.message)}return;
    }
    if(event.target.closest?.('[data-issue-license]')){
      const client=$('#licenseClient')?.value.trim();if(!client){alert('Client name is required');return}
      const rawExpiry=$('#licenseExpiry')?.value;
      const payload={client_name:client,license_type:$('#licenseType').value,max_users:$('#licenseUsers').value?Number($('#licenseUsers').value):null,max_devices:$('#licenseDevices').value?Number($('#licenseDevices').value):null,expires_at:rawExpiry?new Date(rawExpiry).toISOString():null,managed_ai:$('#licenseManagedAI').value==='true',metadata:{issued_from:'our-products'}};
      try{await api(`/${encodeURIComponent(currentProductId)}/licenses`,{method:'POST',body:JSON.stringify(payload)});await render()}catch(error){alert(error.message)}
    }
  });

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ensureTab,{once:true});else ensureTab();
  new MutationObserver(ensureTab).observe(document.documentElement,{childList:true,subtree:true});
})();
