(()=>{
  'use strict';

  let currentProductId='';
  let enhanceToken=0;

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

  async function enhanceBuildHistory(){
    const id=currentProductId;
    if(!id)return;
    const token=++enhanceToken;
    try{
      const payload=await api(`/${encodeURIComponent(id)}/builds`);
      if(token!==enhanceToken||id!==currentProductId)return;
      const builds=payload.builds||[];
      const rows=historyRows();
      rows.forEach((row,index)=>{
        const build=builds[index];
        if(!build)return;
        const title=row.querySelector('b');
        if(title&&!title.dataset.buildNumberApplied){
          title.textContent=`Build #${build.build_number} · ${title.textContent}`;
          title.dataset.buildNumberApplied='true';
        }
        const status=row.querySelector('.status');
        if(status&&!status.dataset.buildLifecycleApplied){
          status.textContent=evidenceLabel(build);
          status.title=build.metadata?.signing_verified?'Signing verified':'No signing claim recorded';
          status.dataset.buildLifecycleApplied='true';
        }
      });
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
