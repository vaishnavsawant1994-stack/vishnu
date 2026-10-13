const VISHNU_DATA_CACHE_DB='vishnu-data-plane-cache-v1';
const VISHNU_DATA_CACHE_VERSION=1;
const MAX_ENTRIES=512;
const MAX_TOTAL_BYTES=8*1024*1024;
const MAX_RECORD_BYTES=64*1024;
const DEFAULT_TTL_MS=7*24*60*60*1000;
export const VISHNU_CONTINUATION_LIMITS=Object.freeze({
  maxEntries:MAX_ENTRIES,
  maxTotalBytes:MAX_TOTAL_BYTES,
  maxRecordBytes:MAX_RECORD_BYTES,
  maxTtlMs:DEFAULT_TTL_MS,
  minTtlMs:60_000
});
const PROGRESS_FIELDS=new Set([
  'project_id','project_name','status','progress','task_id','task_title','task_status',
  'milestone_id','milestone_title','milestone_status','last_step','next_step','last_activity',
  'allowed_notes','updated_at'
]);
const FORBIDDEN_KEYS=new Set([
  'password','passwd','passphrase','secret','token','access_token','refresh_token','api_key','apikey',
  'authorization','cookie','credential','private_key','session_token','bearer_token','bytes','content_bytes',
  'raw','raw_bytes','raw_content','file_bytes','image_bytes','audio_bytes','video_bytes','document_content',
  'ciphertext','wrapped_key','wrap_nonce'
]);

function normalizedKey(value){return String(value||'').trim().toLowerCase().replaceAll('-','_').replaceAll(' ','_');}
function containsForbidden(value,depth=0){
  if(depth>8)return true;
  if(value&&typeof value==='object'&&!Array.isArray(value)){
    return Object.entries(value).some(([key,child])=>{
      const k=normalizedKey(key);
      if(FORBIDDEN_KEYS.has(k)||k.endsWith('_password')||k.endsWith('_secret')||k.endsWith('_token')||k.endsWith('_credential'))return true;
      return containsForbidden(child,depth+1);
    });
  }
  if(Array.isArray(value))return value.some(item=>containsForbidden(item,depth+1));
  return false;
}
function progressProjection(payload){
  const result={};
  for(const [key,value] of Object.entries(payload||{}))if(PROGRESS_FIELDS.has(key))result[key]=value;
  return result;
}
function requestPromise(request){return new Promise((resolve,reject)=>{request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});}
function txDone(tx){return new Promise((resolve,reject)=>{tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error||new Error('cache transaction aborted'));tx.onerror=()=>reject(tx.error);});}

export function boundedContinuationTtl(ttlMs=DEFAULT_TTL_MS){
  return Math.max(VISHNU_CONTINUATION_LIMITS.minTtlMs,Math.min(Number(ttlMs)||DEFAULT_TTL_MS,DEFAULT_TTL_MS));
}

export function continuationPrunePlan(rows,{now=Date.now(),maxEntries=MAX_ENTRIES,maxTotalBytes=MAX_TOTAL_BYTES}={}){
  const expiredIds=new Set((rows||[]).filter(row=>Number(row.expiresAt||0)<=now).map(row=>String(row.globalId)));
  const survivors=(rows||[])
    .filter(row=>!expiredIds.has(String(row.globalId)))
    .slice()
    .sort((a,b)=>Number(a.lastAccess||0)-Number(b.lastAccess||0));
  let total=survivors.reduce((sum,row)=>sum+Number(row.storedBytes||0),0);
  const removeIds=[...expiredIds];
  while(survivors.length>maxEntries||total>maxTotalBytes){
    const row=survivors.shift();
    if(!row)break;
    removeIds.push(String(row.globalId));
    total-=Number(row.storedBytes||0);
  }
  return {removeIds,remainingEntries:survivors.length,remainingBytes:Math.max(0,total)};
}

async function openDb(){
  return new Promise((resolve,reject)=>{
    const request=indexedDB.open(VISHNU_DATA_CACHE_DB,VISHNU_DATA_CACHE_VERSION);
    request.onupgradeneeded=()=>{
      const db=request.result;
      if(!db.objectStoreNames.contains('entries')){
        const store=db.createObjectStore('entries',{keyPath:'globalId'});
        store.createIndex('lastAccess','lastAccess');
        store.createIndex('expiresAt','expiresAt');
      }
      if(!db.objectStoreNames.contains('keys'))db.createObjectStore('keys',{keyPath:'id'});
    };
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error);
  });
}

async function cacheKey(db){
  const readTx=db.transaction('keys','readonly');
  let row=await requestPromise(readTx.objectStore('keys').get('cache-key'));
  await txDone(readTx);
  if(row?.key)return row.key;
  const key=await crypto.subtle.generateKey({name:'AES-GCM',length:256},false,['encrypt','decrypt']);
  const writeTx=db.transaction('keys','readwrite');
  writeTx.objectStore('keys').put({id:'cache-key',key,createdAt:Date.now()});
  await txDone(writeTx);
  return key;
}

async function encryptJson(db,value){
  const key=await cacheKey(db);
  const nonce=crypto.getRandomValues(new Uint8Array(12));
  const plaintext=new TextEncoder().encode(JSON.stringify(value));
  if(plaintext.byteLength>MAX_RECORD_BYTES)throw new Error('offline continuation record exceeds bounded cache size');
  const encrypted=await crypto.subtle.encrypt({name:'AES-GCM',iv:nonce},key,plaintext);
  return {nonce,encrypted,plainBytes:plaintext.byteLength,storedBytes:encrypted.byteLength+nonce.byteLength};
}
async function decryptJson(db,row){
  const key=await cacheKey(db);
  const plaintext=await crypto.subtle.decrypt({name:'AES-GCM',iv:row.nonce},key,row.encrypted);
  return JSON.parse(new TextDecoder().decode(plaintext));
}

async function allEntries(db){
  const tx=db.transaction('entries','readonly');
  const rows=await requestPromise(tx.objectStore('entries').getAll());
  await txDone(tx);
  return rows||[];
}
async function removeIds(db,ids){
  if(!ids.length)return;
  const tx=db.transaction('entries','readwrite');
  const store=tx.objectStore('entries');
  ids.forEach(id=>store.delete(id));
  await txDone(tx);
}
async function prune(db){
  const plan=continuationPrunePlan(await allEntries(db));
  await removeIds(db,plan.removeIds);
}

export async function putVishnuContinuation(record,{ttlMs=DEFAULT_TTL_MS}={}){
  const globalId=String(record?.global_id||record?.globalId||'').trim();
  const policy=String(record?.storage_policy||record?.storagePolicy||'').trim();
  if(!globalId)throw new Error('global_id is required for offline continuation cache');
  if(policy==='device_only')throw new Error('device-only data is never persisted in the PWA continuation cache');
  if(!['progress_only','sync_everywhere','on_demand'].includes(policy))throw new Error('unsupported data policy for offline continuation cache');
  const rawPayload={...(record?.payload||record?.metadata||{})};
  if(containsForbidden(rawPayload))throw new Error('offline continuation cache rejects secrets/raw content');
  const payload=policy==='progress_only'?progressProjection(rawPayload):rawPayload;
  if(containsForbidden(payload))throw new Error('offline continuation payload is not cache-safe');
  const safe={
    global_id:globalId,
    storage_policy:policy,
    version:Number(record?.version||0),
    updated_at:String(record?.updated_at||record?.updatedAt||''),
    payload
  };
  const db=await openDb();
  try{
    const encrypted=await encryptJson(db,safe);
    const now=Date.now();
    const boundedTtl=boundedContinuationTtl(ttlMs);
    const tx=db.transaction('entries','readwrite');
    tx.objectStore('entries').put({
      globalId,policy,version:safe.version,lastAccess:now,expiresAt:now+boundedTtl,
      nonce:encrypted.nonce,encrypted:encrypted.encrypted,storedBytes:encrypted.storedBytes
    });
    await txDone(tx);
    await prune(db);
    return {global_id:globalId,stored:true,expires_at:now+boundedTtl,encrypted:true};
  }finally{db.close();}
}

export async function getVishnuContinuation(globalId){
  const id=String(globalId||'').trim();
  if(!id)return null;
  const db=await openDb();
  try{
    const tx=db.transaction('entries','readonly');
    const row=await requestPromise(tx.objectStore('entries').get(id));
    await txDone(tx);
    if(!row)return null;
    if(row.expiresAt<=Date.now()){
      await removeIds(db,[id]);
      return null;
    }
    const result=await decryptJson(db,row);
    const touch=db.transaction('entries','readwrite');
    row.lastAccess=Date.now();
    touch.objectStore('entries').put(row);
    await txDone(touch);
    return result;
  }catch(error){
    // Authentication/decryption failure is fail-closed: remove the corrupted cache record.
    try{await removeIds(db,[id]);}catch(_ignored){}
    throw error;
  }finally{db.close();}
}

export async function removeVishnuContinuation(globalId){
  const db=await openDb();
  try{await removeIds(db,[String(globalId||'')]);}finally{db.close();}
}

export async function clearVishnuContinuationCache(){
  const db=await openDb();
  try{
    const tx=db.transaction('entries','readwrite');
    tx.objectStore('entries').clear();
    await txDone(tx);
  }finally{db.close();}
}

export async function vishnuContinuationCacheStats(){
  const db=await openDb();
  try{
    await prune(db);
    const rows=await allEntries(db);
    return {
      entries:rows.length,
      stored_bytes:rows.reduce((sum,row)=>sum+Number(row.storedBytes||0),0),
      max_entries:MAX_ENTRIES,
      max_bytes:MAX_TOTAL_BYTES,
      max_record_bytes:MAX_RECORD_BYTES,
      encrypted:true,
      device_only_persisted:false
    };
  }finally{db.close();}
}

export async function revokeVishnuOfflineData(globalIds=[]){
  const ids=[...new Set((globalIds||[]).map(value=>String(value||'').trim()).filter(Boolean))];
  if(!ids.length)return;
  const db=await openDb();
  try{await removeIds(db,ids);}finally{db.close();}
}