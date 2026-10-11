(()=>{
  'use strict';

  let currentProductId='';
  let enhanceToken=0;

  const esc=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const api=async path=>{
    const response=await fetch(`/iphone/api/products${path}`,{credentials:'same-origin'});
    let body=null;
    try{body=await response.json()}catch{body={detail:`Request failed (${response.status})`}}
    if(!response.ok)throw new Error(typeof body?.detail==='string'?body.detail:`Request failed (${response.status})`);
    return body;
  };

  const historyRows=()=>{
    const body=document.querySelector('#detailBody .detail-section');
    if(!body)return [];
    const heading=[...body.children].find(node=>node.tagName==='H3'&&node.textContent.trim()==='Build history');
    if(!heading)return [];
    const rows=[];
    let node=heading.nextElementSibling;
    while(node){
      if(node.classList?.contains('build-row'))rows.push(node);
      node=node.nextElementSibling;
    }
    return rows;
  };

  const evidenceLabel=build=>{
    if(build?.metadata?.artifact_ready)return 'Artifact qualified';
    if(build?.status==='succeeded'&&build?.metadata?.artifact_uri)return 'Artifact evidence incomplete';
    if(build?.status==='succeeded')return 'Completed · no qualified artifact';
    return 'Artifact pending';
  };

  const targetDescription=item=>{
    const build=item.latest_build||null;
    if(item.builder==='local-runtime'){
      if(build?.artifact_ready)return `Verified local artifact ready · Build #${build.build_number}`;
      if(build?.status==='failed')return `Local build failed${build.failure_reason?` · ${build.failure_reason}`:''}`;
      return 'Verified local runtime builder available';
    }
    if(item.builder!=='platform-runner')return 'No qualified builder is available for this target';
    if(build?.artifact_ready)return `Production artifact ready · Build #${build.build_number}`;
    if(build?.status==='running')return `Platform build running · Build #${build.build_number}`;
    if(build?.status==='queued'||build?.status==='requested')return `Waiting for platform runner · Build #${build.build_number}`;
    if(build?.status==='failed')return `Last platform build failed${build.failure_reason?` · ${build.failure_reason}`:''}`;
    const requirements=(item.production_requirements||[]).join(' + ');
    if(!item.runner_configured)return `Compiler implemented · runner authentication not configured${requirements?` · production needs ${requirements}`:''}`;
    return `Compiler implemented · runner authentication configured${requirements?` · production needs ${requirements}`:''}`;
  };

  function applyRunnerReadiness(payload){
    const section=document.querySelector('#detailBody .detail-section');
    if(!section)return;
    let panel=section.querySelector('[data-runner-readiness]');
    if(!panel){
      panel=document.createElement('div');
      panel.dataset.runnerReadiness='true';
      panel.className='detail-tile';
      const warning=section.querySelector('.warning');
      if(warning)warning.insertAdjacentElement('afterend',panel);else section.prepend(panel);
    }
    const targets=payload.targets||[];
    const ready=targets.filter(item=>item.latest_build?.artifact_ready).length;
    const waiting=targets.filter(item=>['requested','queued','running'].includes(item.latest_build?.status)).length;
    panel.innerHTML=`<small>BUILD & RUNNER READINESS</small><strong>${ready}/${targets.length} enabled targets have a qualified downloadable artifact</strong><div class="muted">Product-job signing: ${payload.production_job_signing_configured?'configured':'not configured'} · External runner authentication: ${payload.platform_runner_auth_configured?'configured':'not configured'}${waiting?` · ${waiting} build${waiting===1?'':'s'} waiting/running`:''}</div><div class="chips">${targets.map(item=>`<span class="chip">${esc(item.target)} · ${item.latest_build?.artifact_ready?'ready':esc(item.latest_build?.status||'not built')}</span>`).join('')}</div>`;

    for(const item of targets){
      const button=[...section.querySelectorAll('[data-build-target]')].find(node=>node.dataset.buildTarget===item.target);
      const row=button?.closest('.build-row');
      const detail=row?.querySelector('.muted');
      if(detail){
        detail.textContent=targetDescription(item);
        detail.title=(item.production_requirements||[]).length?`Production evidence: ${(item.production_requirements||[]).join(', ')}`:'';
      }
    }
  }

  async function enhanceBuildHistory(){
    const id=currentProductId;
    if(!id)return;
    const token=++enhanceToken;
    try{
      const [buildPayload,readinessPayload]=await Promise.all([
        api(`/${encodeURIComponent(id)}/builds`),
        api(`/${encodeURIComponent(id)}/runner-readiness`),
      ]);
      if(token!==enhanceToken||id!==currentProductId)return;
      const builds=buildPayload.builds||[];
      const rows=historyRows();
      rows.forEach((row,index)=>{
        const build=builds[index];
        if(!build)return;
        const title=row.querySelector('b');
        if(title&&!title.dataset.buildNumberApplied){
          const prefix=`Build #${build.build_number} · `;
          if(!title.textContent.startsWith(prefix))title.textContent=`${prefix}${title.textContent}`;
          title.dataset.buildNumberApplied='true';
        }
        const status=row.querySelector('.status');
        if(status&&!status.dataset.buildLifecycleApplied){
          status.textContent=evidenceLabel(build);
          status.title=build.metadata?.signing_verified?'Signing verified':'No signing claim recorded';
          status.dataset.buildLifecycleApplied='true';
        }
      });
      applyRunnerReadiness(readinessPayload);
    }catch{
      // The canonical Our Products surface owns auth/error messaging. This optional
      // progressive enhancement stays silent when the owner session is unavailable.
    }
  }

  document.addEventListener('click',event=>{
    const card=event.target.closest?.('[data-product-id]');
    if(card?.dataset?.productId)currentProductId=card.dataset.productId;
    const tab=event.target.closest?.('#detailTabs [data-tab="build"]');
    const buildButton=event.target.closest?.('[data-build-target]');
    if(tab||buildButton)setTimeout(enhanceBuildHistory,80);
  },true);

  const detailBody=document.getElementById('detailBody');
  if(detailBody){
    const observer=new MutationObserver(()=>{
      const active=document.querySelector('#detailTabs [data-tab="build"].active');
      if(active)setTimeout(enhanceBuildHistory,0);
    });
    observer.observe(detailBody,{childList:true,subtree:true});
  }
})();
