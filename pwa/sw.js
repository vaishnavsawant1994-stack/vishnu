importScripts('/iphone/data-plane-offline.js');
const CACHE='personal-ai-iphone-v37';
const SHELL=['/iphone/','/iphone/manifest.webmanifest','/iphone/data-plane-offline.js','/iphone/projects-workspace.css','/iphone/projects-workspace.js','/iphone/projects-workspace-views.css','/iphone/projects-workspace-views.js','/iphone/home-chat-redesign.js','/iphone/home-chat-redesign-core.js','/iphone/chat-experience.css','/iphone/chat-experience.js','/iphone/chat-context-owner.js','/iphone/projects-work-runtime.js','/iphone/project-autonomy-controls.js','/iphone/projects-work-visualization-runtime.js','/iphone/workorder-detail.js','/iphone/global-work-awareness.js','/iphone/work-attention-center.js','/iphone/owner-controls.css','/iphone/owner-controls.js','/iphone/agent-workforce-entry.js','/iphone/agents.html','/iphone/agents-workforce.css','/iphone/agents-workforce.js','/iphone/agents-workforce-work-mode.js'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  const privateDataPath=url.pathname.startsWith('/iphone/api/')||url.pathname.startsWith('/dashboard/')||url.pathname.startsWith('/cloud/');
  if(event.request.method!=='GET'||privateDataPath)return;
  event.respondWith(fetch(event.request).then(response=>{
    const copy=response.clone();
    caches.open(CACHE).then(cache=>cache.put(event.request,copy));
    return response;
  }).catch(()=>caches.match(event.request).then(r=>r||caches.match('/iphone/'))));
});