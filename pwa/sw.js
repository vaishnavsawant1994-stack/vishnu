const CACHE='personal-ai-iphone-v57';
const SHELL=[
  '/iphone/','/iphone/manifest.webmanifest','/iphone/genesis.css','/iphone/first-run.js','/iphone/first-run-actions.js','/iphone/genesis-welcome.css','/iphone/genesis-neural-sphere.js','/iphone/genesis-identity.css','/iphone/genesis-identity.js','/iphone/genesis-security.css','/iphone/genesis-security.js','/iphone/genesis-recovery.css','/iphone/genesis-recovery.js','/iphone/genesis-login.css','/iphone/genesis-login.js','/iphone/genesis-connect.css','/iphone/genesis-connect.js','/iphone/genesis-recovery-options.css','/iphone/genesis-recovery-options.js','/iphone/genesis-verification.css','/iphone/genesis-verification.js','/iphone/campaign-demo.css','/iphone/campaign-demo.js','/iphone/campaign-demo-data.js','/iphone/global-search.css','/iphone/global-search.js','/iphone/command-center.css','/iphone/command-center.js','/iphone/workspaces-ui.css','/iphone/workspaces-ui.js',
  '/iphone/assets/genesis/avatar-blue.svg','/iphone/assets/genesis/avatar-mountain.svg','/iphone/assets/genesis/avatar-forest.svg','/iphone/assets/genesis/avatar-horizon.svg',
  '/iphone/assets/genesis/vishnu-core.png','/iphone/assets/genesis/cosmic-desktop.png','/iphone/assets/genesis/cosmic-mobile.png','/iphone/projects-workspace.css','/iphone/projects-workspace.js',
  '/iphone/reference-home.css','/iphone/reference-home.js',
  '/iphone/projects-workspace-views.css','/iphone/projects-workspace-views.js','/iphone/home-chat-redesign.js',
  '/iphone/home-chat-redesign-core.js','/iphone/chat-experience.css','/iphone/chat-experience.js',
  '/iphone/chat-context-owner.js','/iphone/adaptive-composer.js','/iphone/projects-work-runtime.js','/iphone/project-autonomy-controls.js',
  '/iphone/projects-work-visualization-runtime.js','/iphone/workorder-detail.js','/iphone/global-work-awareness.js',
  '/iphone/work-attention-center.js','/iphone/owner-controls.css','/iphone/owner-controls.js',
  '/iphone/agent-workforce-entry.js','/iphone/agents.html','/iphone/agents-workforce.css',
  '/iphone/agents-workforce.js','/iphone/agents-workforce-work-mode.js','/iphone/data-plane-cache.js'
];
const SHELL_SET=new Set(SHELL);

self.addEventListener('install',event=>event.waitUntil(
  caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting())
));

self.addEventListener('activate',event=>event.waitUntil(
  caches.keys()
    .then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))))
    .then(()=>self.clients.claim())
));

function noStore(response){
  const cacheControl=(response.headers.get('cache-control')||'').toLowerCase();
  const dataPolicy=(response.headers.get('x-vishnu-data-policy')||'').toLowerCase();
  return cacheControl.includes('no-store') || dataPolicy==='device_only' || response.headers.get('x-vishnu-no-persist')==='1';
}

self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(event.request.method!=='GET' || url.origin!==self.location.origin) return;

  // API/data requests are never written to Cache Storage. Permitted continuation
  // metadata is handled by the bounded IndexedDB data-plane cache in page code.
  if(url.pathname.startsWith('/iphone/api/') || url.pathname.startsWith('/api/')) return;

  if(!SHELL_SET.has(url.pathname)) return;
  event.respondWith(
    fetch(event.request,{cache:'no-store'})
      .then(response=>{
        if(response.ok && !noStore(response)){
          const copy=response.clone();
          event.waitUntil(caches.open(CACHE).then(cache=>cache.put(event.request,copy)));
        }
        return response;
      })
      .catch(()=>caches.match(event.request).then(r=>r||caches.match('/iphone/')))
  );
});
