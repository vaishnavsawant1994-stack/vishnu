import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';

const source=await readFile(new URL('../pwa/p207-notifications.js',import.meta.url),'utf8');
const style=await readFile(new URL('../pwa/p207-notifications.css',import.meta.url),'utf8');
const shots=process.env.P207_SCREENSHOT_DIR;
if(shots)await mkdir(shots,{recursive:true});
let rows=[],requests=[],approvalStatus='pending';
const fixture=()=>{approvalStatus='pending';rows=[
{id:'n1',kind:'notification',category:'work',title:'Work completed',body:'Verified task finished',created_at:'2026-10-22T10:00:00Z',read_at:null,pinned_at:null,priority:'normal',source_type:'work',project_id:'p1',source_authority:'notification_service',read_supported:true,pin_supported:true,dismiss_supported:true,status:'unread'},
{id:'n2',kind:'notification',category:'security',title:'Security update',body:'A verified device event',created_at:'2026-10-21T10:00:00Z',read_at:null,pinned_at:null,priority:'high',source_type:'security',project_id:'',source_authority:'notification_service',read_supported:true,pin_supported:true,dismiss_supported:true,status:'unread'}
]};
const approval=()=>({id:'approval:a1',kind:'approval',category:'approvals',title:'Approval required: external tool',body:'A governed action requires your decision. Review the exact scope before responding.',created_at:'2026-10-22T11:00:00Z',read_at:null,pinned_at:null,priority:'high',source_type:'approval',source_id:'a1',status:approvalStatus,read_supported:false,pin_supported:false,dismiss_supported:false,source_authority:'approval_manager',approval:{approval_id:'a1',tool_id:'external_tool',status:approvalStatus,data_classification:'internal',expires_at:1799999999}});
const data=()=>[...rows,...(approvalStatus==='pending'?[approval()]:[])];
const html='<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+style+'</style></head><body><div id="sidebarInboxCount"></div><div id="modulePanel" class="open"><div class="module-head"><span id="moduleTitle"></span><span id="moduleText"></span><span id="moduleMetric"></span></div><div id="moduleBody" class="module-body"></div></div><script>'+
'window.openModule=async()=>{};window.openProject=async()=>{};window.vishnuChatBridge={api:async(path,opts={})=>{const response=await fetch("/iphone/api"+path,{method:opts.method||"GET",body:opts.body,headers:{"Content-Type":"application/json"}});const body=await response.json();if(!response.ok)throw new Error(body.detail||"Failed");return body},requestConfirmation:async()=>true};'+
'</script><script src="/p207"></script><script>window.openModule("notifications")</script></body></html>';
const server=createServer(async(req,res)=>{
 const url=new URL(req.url,'http://localhost'),path=url.pathname,method=req.method;
 const body=await new Promise(resolve=>{let b='';req.on('data',v=>b+=v);req.on('end',()=>resolve(b?JSON.parse(b):{}))});
 requests.push(method+' '+path);
 const reply=(value,status=200,type='application/json')=>{res.writeHead(status,{'content-type':type});res.end(type==='application/json'?JSON.stringify(value):value)};
 if(path==='/')return reply(html,200,'text/html');
 if(path==='/p207')return reply(source,200,'application/javascript');
 if(path==='/iphone/api/notifications-center'&&method==='GET'){
   const q=(url.searchParams.get('q')||'').toLowerCase(),cat=url.searchParams.get('category')||'all',unread=url.searchParams.get('unread')==='true';
   let filtered=data().filter(x=>(cat==='all'||x.category===cat)&&(!unread||(x.read_supported&&!x.read_at))&&(!q||(x.title+' '+x.body).toLowerCase().includes(q)));
   return reply({notifications:filtered,counts:{all:data().length,unread:rows.filter(x=>!x.read_at).length,pending_approvals:approvalStatus==='pending'?1:0,work:rows.filter(x=>x.category==='work').length,security:rows.filter(x=>x.category==='security').length,approvals:approvalStatus==='pending'?1:0,messages:0,projects:0,system:0},coverage:{inbox:'available',approvals:'available'},next_offset:null});
 }
 if(path==='/iphone/api/workspaces')return reply({workspaces:[]});
 if(path==='/iphone/api/projects')return reply({projects:[{id:'p1',name:'Test Project'}]});
 if(path==='/iphone/api/notifications-center/read-bulk'&&method==='POST'){let count=0;for(const x of rows){if(!x.read_at){x.read_at='2026-10-22T12:00:00Z';count++}}return reply({marked_read:count})}
 if(path==='/iphone/api/approvals-center/a1'&&method==='GET')return reply({approval_id:'a1',tool_id:'external_tool',status:approvalStatus});
 if(path==='/iphone/api/approval/a1/approve'&&method==='POST'){approvalStatus='completed';return reply({status:'approved'})}
 if(path==='/iphone/api/approval/a1/reject'&&method==='POST'){approvalStatus='rejected';return reply({status:'rejected'})}
 if(path==='/iphone/api/notifications-center/approval%3Aa1')return reply({notification:approval(),authority:'approval_manager',related:[]});
 const match=path.match(/^\/iphone\/api\/notifications-center\/(n[12])(?:\/(read|pin|dismiss))?$/);
 if(match){const item=rows.find(x=>x.id===match[1]);if(!item)return reply({detail:'Not found'},404);
 if(match[2]==='read'){item.read_at='2026-10-22T12:00:00Z';return reply({marked_read:true})}
 if(match[2]==='pin'){item.pinned_at=body.pinned?'2026-10-22T12:00:00Z':null;return reply({pinned:body.pinned})}
 if(match[2]==='dismiss'){rows=rows.filter(x=>x.id!==item.id);return reply({dismissed:true})}
 return reply({notification:item,related:[],authority:'notification_service'})}
 return reply({detail:'Unavailable'},404);
});
await new Promise(done=>server.listen(0,'127.0.0.1',done));
const browser=await chromium.launch({headless:true});
try{
 for(const width of [1536,390]){
  fixture();requests=[];
  const page=await browser.newPage({viewport:{width,height:width===390?844:1024},deviceScaleFactor:1});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:'+server.address().port+'/');
  await page.getByRole('heading',{name:'Notifications & Alerts'}).waitFor();
  await page.locator('.p207-item').first().waitFor();
  assert.equal(await page.locator('.p207-item').count(),3);
  assert.match(await page.locator('#p207Categories').innerText(),/Approvals/);
  await page.locator('[data-p207-cat="approvals"]').click();
  await page.locator('.p207-item').first().waitFor();
  assert.equal(await page.locator('.p207-item').count(),1);
  await page.locator('[data-p207-id="approval:a1"]').click();
  await page.getByText('Governed approval details').waitFor();
  if(width===390)assert.equal(await page.locator('#p207Detail.mobile-detail').count(),1);
  if(shots)await page.screenshot({path:shots+'/notifications-'+width+'.png'});
  await page.locator('[data-p207-action="approve"]').click();
  await page.getByText('Canonical result: approved',{exact:false}).waitFor();
  assert.ok(requests.includes('POST /iphone/api/approval/a1/approve'));
  assert.equal(approvalStatus,'completed');
  await page.locator('[data-p207-cat="all"]').click();
  await page.locator('[data-p207-id="n1"]').click();
  await page.locator('[data-p207-action="read"]').click();
  assert.ok(rows.find(x=>x.id==='n1').read_at);
  await page.locator('[data-p207-action="pin"]').click();
  assert.ok(rows.find(x=>x.id==='n1').pinned_at);
  if(width===1536){
    await page.locator('#p207ReadAll').click();
    assert.equal(rows.filter(x=>!x.read_at).length,0);
  }else{
    const layout=await page.evaluate(()=>({outer:document.documentElement.scrollWidth,view:innerWidth}));
    assert.ok(layout.outer<=layout.view+3,JSON.stringify(layout));
    await page.locator('[data-p207-id="n1"]').click();
    await page.locator('#p207Detail.mobile-detail').waitFor();
    await page.locator('[data-p207-action="back"]').click();
    await page.locator('[data-p207-action="togglefilters"]').click();
    assert.equal(await page.locator('.p207-page.filters-open').count(),1);
  }
  assert.deepEqual(errors,[],errors.join('\n'));
  await page.close();
 }
 console.log('P2-07 browser fixture: canonical notification list, category, preview, governed approval, read/pin/bulk and mobile geometry passed.');
}finally{await browser.close();await new Promise(done=>server.close(done))}
