(()=>{
  'use strict';

  let currentProductId='';
  const esc=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));

  async function api(path,options={}){
    const response=await fetch(`/iphone/api/products${path}`,{
      credentials:'same-origin',
      headers:{'Content-Type':'application/json',...(options.headers||{})},
      ...options,
    });
    if(response.status===204)return null;
    let body=null;
    try{body=await response.json()}catch{body={detail:`Request failed (${response.status})`}}
    if(!response.ok)throw new Error(typeof body?.detail==='string'?body.detail:`Request failed (${response.status})`);
    return body;
  }

  function notice(message,error=false){
    const node=document.querySelector('#message');
    if(!node)return;
    node.textContent=message;
    node.classList.toggle('error',error);
    node.classList.remove('hidden');
    clearTimeout(notice.timer);
    notice.timer=setTimeout(()=>node.classList.add('hidden'),4500);
  }

  function body(){return document.querySelector('#detailBody')}

  function permissionsView(product){
    const p=product.permissions||{};
    const rows=[
      ['browser.search','Browser search'],['browser.open','Open websites'],['files.read','Read files'],['files.write','Write files'],
      ['email.read','Read email'],['email.draft','Draft email'],['email.send','Send email'],['calendar.write','Change calendar'],
      ['crm.read','Read CRM'],['crm.write','Write CRM'],['system.execute','Run system commands'],['payments.execute','Execute payments'],
    ];
    return `<div class="detail-section">
      <div class="warning">Exported products are allow-listed. Any capability not listed here is denied by default.</div>
      ${rows.map(([key,label])=>`<div class="setting-row"><div><b>${esc(label)}</b><div class="muted">${esc(key)}</div></div><select data-permission="${esc(key)}"><option value="deny" ${(p[key]||'deny')==='deny'?'selected':''}>Deny</option><option value="ask" ${p[key]==='ask'?'selected':''}>Ask for approval</option><option value="allow" ${p[key]==='allow'?'selected':''}>Allow</option></select></div>`).join('')}
      <button class="button primary" id="saveProductPermissions">Save permissions</button>
    </div>`;
  }

  function brandingView(product){
    const b=product.branding||{};
    return `<div class="detail-section">
      <p class="muted">White-label settings are product metadata. Platform builders consume these values when generating target-specific applications.</p>
      <div class="form-grid">
        <label>App name<input id="brandName" maxlength="160" value="${esc(b.name||product.name||'')}"></label>
        <label>Company<input id="brandCompany" maxlength="160" value="${esc(b.company||'')}"></label>
        <label>Support email<input id="brandSupport" maxlength="240" value="${esc(b.support_email||'')}"></label>
        <label>Custom domain<input id="brandDomain" maxlength="300" value="${esc(b.domain||'')}"></label>
        <label>App / bundle ID<input id="brandBundle" maxlength="240" value="${esc(b.bundle_id||'')}"></label>
        <label>Brand mode<select id="brandMode"><option value="vishnu" ${b.mode==='vishnu'?'selected':''}>Vishnu branded</option><option value="powered_by" ${b.mode==='powered_by'?'selected':''}>Powered by Vishnu</option><option value="white_label" ${b.mode==='white_label'?'selected':''}>Fully white-labelled</option></select></label>
      </div>
      <button class="button primary" id="saveProductBranding">Save branding</button>
    </div>`;
  }

  function licensingView(product){
    const l=product.licensing||{};
    return `<div class="detail-section">
      <div class="warning">License configuration does not expose the Vishnu signing private key. Release licenses are signed by the owner-side license authority.</div>
      <div class="form-grid">
        <label>License type<select id="licenseType"><option value="trial">Trial</option><option value="monthly">Monthly</option><option value="annual">Annual</option><option value="perpetual">Perpetual</option><option value="organization">Per organization</option><option value="custom">Custom</option></select></label>
        <label>Edition<input id="licenseEdition" maxlength="120" value="${esc(l.edition||'standard')}"></label>
        <label>Device limit<input id="licenseDevices" type="number" min="1" value="${esc(l.device_limit||'')}"></label>
        <label>User limit<input id="licenseUsers" type="number" min="1" value="${esc(l.user_limit||'')}"></label>
        <label><input id="licenseManagedAI" type="checkbox" ${l.managed_ai_allowed?'checked':''}> Managed AI entitlement</label>
        <label><input id="licenseUpdates" type="checkbox" ${l.updates_allowed!==false?'checked':''}> Product updates</label>
      </div>
      <button class="button primary" id="saveProductLicensing">Save licensing policy</button>
    </div>`;
  }

  async function loadCommercialTab(tab){
    if(!currentProductId)return;
    const target=body();
    if(!target)return;
    target.innerHTML='<p class="muted">Loading…</p>';
    try{
      const response=await api(`/${encodeURIComponent(currentProductId)}`);
      const product=response.product;
      if(tab==='permissions')target.innerHTML=permissionsView(product);
      if(tab==='branding')target.innerHTML=brandingView(product);
      if(tab==='licensing'){
        target.innerHTML=licensingView(product);
        const select=document.querySelector('#licenseType');if(select&&product.licensing?.type)select.value=product.licensing.type;
      }
    }catch(error){target.innerHTML=`<p class="message error">${esc(error.message)}</p>`}
  }

  document.addEventListener('click',event=>{
    const card=event.target.closest?.('.product-card');
    if(card?.dataset.productId)currentProductId=card.dataset.productId;

    const tabButton=event.target.closest?.('#detailTabs [data-tab]');
    const tab=tabButton?.dataset.tab;
    if(['permissions','branding','licensing'].includes(tab)){
      setTimeout(()=>loadCommercialTab(tab),0);
      return;
    }

    if(event.target.closest?.('#saveProductPermissions')){
      const permissions={};
      document.querySelectorAll('[data-permission]').forEach(select=>{permissions[select.dataset.permission]=select.value});
      api(`/${encodeURIComponent(currentProductId)}/permissions`,{method:'PUT',body:JSON.stringify({permissions})})
        .then(()=>notice('Product permissions saved.')).catch(error=>notice(error.message,true));
    }

    if(event.target.closest?.('#saveProductBranding')){
      const branding={
        name:document.querySelector('#brandName')?.value.trim()||'',
        company:document.querySelector('#brandCompany')?.value.trim()||'',
        support_email:document.querySelector('#brandSupport')?.value.trim()||'',
        domain:document.querySelector('#brandDomain')?.value.trim()||'',
        bundle_id:document.querySelector('#brandBundle')?.value.trim()||'',
        mode:document.querySelector('#brandMode')?.value||'vishnu',
      };
      api(`/${encodeURIComponent(currentProductId)}/branding`,{method:'PUT',body:JSON.stringify({branding})})
        .then(()=>notice('Product branding saved.')).catch(error=>notice(error.message,true));
    }

    if(event.target.closest?.('#saveProductLicensing')){
      const numberOrNull=id=>{const value=document.querySelector(id)?.value;return value?Number(value):null};
      const licensing={
        type:document.querySelector('#licenseType')?.value||'custom',
        edition:document.querySelector('#licenseEdition')?.value.trim()||'standard',
        device_limit:numberOrNull('#licenseDevices'),
        user_limit:numberOrNull('#licenseUsers'),
        managed_ai_allowed:Boolean(document.querySelector('#licenseManagedAI')?.checked),
        updates_allowed:Boolean(document.querySelector('#licenseUpdates')?.checked),
      };
      api(`/${encodeURIComponent(currentProductId)}/licensing`,{method:'PUT',body:JSON.stringify({licensing})})
        .then(()=>notice('Product licensing policy saved.')).catch(error=>notice(error.message,true));
    }
  },true);
})();
