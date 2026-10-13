/* Bounded offline continuation cache for Vishnu PWA.
   This is not an authoritative database and never stores raw/private file content. */
(function(scope){
  'use strict';
  const DB='vishnu-continuation-v1',VERSION=1,MAX_ITEM_BYTES=64*1024,MAX_OUTBOX=500;
  const ALLOWED=new Set(['project_id','project_name','status','progress','task_id','task_title','task_status','milestone_id','milestone_title','milestone_status','last_step','next_step','last_activity','allowed_notes','updated_at']);
  const FORBIDDEN=new Set(['password','passwd','passphrase','secret','token','access_token','refresh_token','api_key','apikey','authorization','cookie','credential','private_key','session_token','bearer_token','bytes','content_bytes','raw','raw_bytes','raw_content','file_bytes','image_bytes','audio_bytes','video_bytes','document_content']);
  const keyOf=value=>String(value||'').trim().toLowerCase().replace(/[ -]/g,'_');
  function containsForbidden(value,depth=0){
    if(depth>8)return true;
    if(!value)return false;
    if(Array.isArray(value))return value.some(v=>containsForbidden(v,depth+1));
    if(typeof value==='object')return Object.entries(value).some(([k,v])=>{const key=keyOf(k);return FORBIDDEN.has(key)||key.endsWith('_password')||key.endsWith('_secret')||key.endsWith('_token')||key.endsWith('_credential')||containsForbidden(v,depth+1)});
    return false;
  }
  function project(payload){
    if(!payload||typeof payload!=='object'||Array.isArray(payload))throw new TypeError('continuation payload must be an object');
    if(containsForbidden(payload))throw new Error('continuation payload contains prohibited data');
    const out={};for(const key of ALLOWED)if(Object.prototype.hasOwnProperty.call(payload,key))out[key]=payload[key];
    const raw=JSON.stringify(out);if(new TextEncoder().encode(raw).length>MAX_ITEM_BYTES)throw new Error('continuation payload exceeds offline cache limit');
    return out;
  }
  function open(){return new Promise((resolve,reject)=>{const request=indexedDB.open(DB,VERSION);request.onerror=()=>reject(request.error);request.onupgradeneeded=()=>{const db=request.result;if(!db.objectStoreNames.contains('items'))db.createObjectStore('items',{keyPath:'global_id'});if(!db.objectStoreNames.contains('outbox')){const store=db.createObjectStore('outbox',{keyPath:'source_event_id'});store.createIndex('created_at','created_at')}};request.onsuccess=()=>resolve(request.result)})}
  async function tx(storeName,mode,work){const db=await open();try{return await new Promise((resolve,reject)=>{const transaction=db.transaction(storeName,mode),store=transaction.objectStore(storeName);let value;try{value=work(store,transaction)}catch(error){reject(error);return}transaction.onerror=()=>reject(transaction.error);transaction.onabort=()=>reject(transaction.error||new Error('offline cache transaction aborted'));transaction.oncomplete=()=>resolve(value)})}finally{db.close()}}
  function requestResult(request){return new Promise((resolve,reject)=>{request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error)})}
  async function get(globalId){const db=await open();try{return await requestResult(db.transaction('items','readonly').objectStore('items').get(String(globalId)))}finally{db.close()}}
  async function put(globalId,entityType,payload,{baseVersion=null,origin='pwa'}={}){
    const id=String(globalId||'').trim();if(!id)throw new Error('global_id is required');const clean=project(payload),existing=await get(id);const nextVersion=Math.max(Number(existing?.version||0)+1,Number(baseVersion||0)+1,1);const stamp=new Date().toISOString();
    if(existing&&baseVersion!=null&&Number(existing.version)!==Number(baseVersion))return{applied:false,conflict:true,local_version:Number(existing.version),incoming_base_version:Number(baseVersion)};
    const item={global_id:id,entity_type:String(entityType||existing?.entity_type||'project').slice(0,80),version:nextVersion,payload:clean,tombstone:false,updated_at:stamp,authoritative:false,cache_policy:'continuation_only'};
    await tx('items','readwrite',store=>store.put(item));
    const event={source_event_id:crypto.randomUUID(),global_id:id,entity_type:item.entity_type,storage_policy:'progress_only',version:nextVersion,event_kind:'update',payload:clean,origin_device_id:String(origin).slice(0,120),created_at:stamp};
    await tx('outbox','readwrite',(store,transaction)=>{store.put(event);const count=store.count();count.onsuccess=()=>{if(count.result>MAX_OUTBOX)transaction.abort()}});
    return{applied:true,conflict:false,version:nextVersion,source_event_id:event.source_event_id,payload:clean};
  }
  async function tombstone(globalId,{baseVersion=null,origin='pwa'}={}){const id=String(globalId||'').trim(),existing=await get(id);if(!existing)throw new Error('continuation item not found');if(baseVersion!=null&&Number(existing.version)!==Number(baseVersion))return{deleted:false,conflict:true,local_version:Number(existing.version)};const version=Number(existing.version)+1,stamp=new Date().toISOString(),item={...existing,version,tombstone:true,payload:{updated_at:stamp},updated_at:stamp};await tx('items','readwrite',store=>store.put(item));const event={source_event_id:crypto.randomUUID(),global_id:id,entity_type:existing.entity_type,storage_policy:'progress_only',version,event_kind:'delete',payload:{updated_at:stamp},origin_device_id:String(origin).slice(0,120),created_at:stamp};await tx('outbox','readwrite',store=>store.put(event));return{deleted:true,version,source_event_id:event.source_event_id}}
  async function pending(limit=100){const db=await open();try{const rows=await requestResult(db.transaction('outbox','readonly').objectStore('outbox').getAll());return rows.sort((a,b)=>String(a.created_at).localeCompare(String(b.created_at))).slice(0,Math.max(1,Math.min(Number(limit)||100,500)))}finally{db.close()}}
  async function acknowledge(sourceEventId){return tx('outbox','readwrite',store=>store.delete(String(sourceEventId))).then(()=>true)}
  async function status(){const db=await open();try{const transaction=db.transaction(['items','outbox'],'readonly');const items=await requestResult(transaction.objectStore('items').count()),pendingCount=await requestResult(transaction.objectStore('outbox').count());return{items,pending_local_events:pendingCount,raw_file_bytes_stored:false,secrets_stored:false,authoritative:false,max_item_bytes:MAX_ITEM_BYTES}}finally{db.close()}}
  async function clear(){const db=await open();try{await Promise.all(['items','outbox'].map(name=>new Promise((resolve,reject)=>{const request=db.transaction(name,'readwrite').objectStore(name).clear();request.onsuccess=()=>resolve();request.onerror=()=>reject(request.error)})))}finally{db.close()}}
  const api={project,get,put,tombstone,pending,acknowledge,status,clear,containsForbidden};scope.VishnuOfflineContinuation=api;
  if(typeof scope.addEventListener==='function'&&typeof Window==='undefined')scope.addEventListener('message',event=>{const message=event.data||{};if(message.type!=='vishnu:continuation')return;const id=message.request_id||crypto.randomUUID(),port=event.ports&&event.ports[0],reply=value=>{const payload={type:'vishnu:continuation:result',request_id:id,...value};if(port)port.postMessage(payload);else event.source?.postMessage?.(payload)};(async()=>{try{const action=String(message.action||'');let result;if(action==='status')result=await status();else if(action==='get')result=await get(message.global_id);else if(action==='put')result=await put(message.global_id,message.entity_type,message.payload,message.options||{});else if(action==='pending')result=await pending(message.limit);else if(action==='ack')result=await acknowledge(message.source_event_id);else if(action==='tombstone')result=await tombstone(message.global_id,message.options||{});else if(action==='clear')result=await clear();else throw new Error('unsupported continuation cache action');reply({ok:true,result})}catch(error){reply({ok:false,error:String(error&&error.message||error)})}})()});
})(typeof self!=='undefined'?self:window);
