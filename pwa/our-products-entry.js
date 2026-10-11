(()=>{
  'use strict';
  if(window.__vishnuOurProductsEntry)return;
  window.__vishnuOurProductsEntry=true;

  const target='/iphone/our-products.html';
  const icon=`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 4.8 7v10L12 21l7.2-4V7L12 3Z"/><path d="m4.8 7 7.2 4 7.2-4M12 11v10"/></svg>`;
  const textOf=node=>String(node?.textContent||'').replace(/\s+/g,' ').trim().toLowerCase();

  function makeEntry(reference){
    const tag=reference?.tagName?.toLowerCase()==='a'?'a':'button';
    const entry=document.createElement(tag);
    entry.dataset.vishnuOurProductsEntry='true';
    entry.className=reference?.className||'';
    entry.setAttribute('aria-label','Our Products');
    if(tag==='a')entry.href=target;else entry.type='button';
    entry.innerHTML=`${icon}<span>Our Products</span>`;
    entry.addEventListener('click',event=>{event.preventDefault();window.location.assign(target)});
    return entry;
  }

  function injectInto(container){
    if(!container||container.querySelector('[data-vishnu-our-products-entry]'))return;
    const candidates=[...container.querySelectorAll(':scope > a,:scope > button,a,button')].filter(node=>!node.closest('[data-vishnu-our-products-entry]'));
    const workflows=candidates.find(node=>/^workflows?\b/.test(textOf(node)));
    const tools=candidates.find(node=>/^tools?\b/.test(textOf(node)));
    const projects=candidates.find(node=>/^projects?\b/.test(textOf(node)));
    const anchor=workflows||tools||projects||candidates.at(-1);
    if(!anchor)return;
    anchor.insertAdjacentElement('afterend',makeEntry(anchor));
  }

  function inject(){
    if(location.pathname==='/iphone/our-products.html')return;
    injectInto(document.querySelector('.nav'));
    for(const container of document.querySelectorAll('aside,nav,.sidebar,.side-panel,.drawer,.menu-panel')){
      if(container.classList.contains('nav'))continue;
      injectInto(container);
    }
  }

  let scheduled=false;
  const schedule=()=>{
    if(scheduled)return;
    scheduled=true;
    requestAnimationFrame(()=>{scheduled=false;inject()});
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',schedule,{once:true});else schedule();
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});
})();
