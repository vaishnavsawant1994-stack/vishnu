import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';

const js=await readFile(new URL('../pwa/p203-today.js',import.meta.url),'utf8');
const css=await readFile(new URL('../pwa/p203-today.css',import.meta.url),'utf8');
const dir=process.env.P203_SCREENSHOT_DIR;
if(dir)await mkdir(dir,{recursive:true});
let approvals=[],requests=[],created=[];
const localDay=()=>{const formatter=new Intl.DateTimeFormat('en-US',{timeZone:Intl.DateTimeFormat().resolvedOptions().timeZone,year:'numeric',month:'2-digit',day:'2-digit'});const parts=Object.fromEntries(formatter.formatToParts(new Date()).filter(x=>x.type!=='literal').map(x=>[x.type,x.value]));return parts.year+'-'+parts.month+'-'+parts.day};
const today=localDay();
const html='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/client.css"></head><body class="today-command-mode"><div id="todayCommandDashboard"></div><script src="/client.js"></script><script>'+
'window.calls=[];window.vishnuTodayP203Bridge={api:async(path,opts={})=>{const res=await fetch("/iphone/api"+path,{method:opts.method||"GET",headers:{"Content-Type":"application/json"},body:opts.body});const x=await res.json();if(!res.ok){const e=new Error(x.detail);e.status=res.status;throw e}return x},name:()=>"Test Owner",toast:msg=>window.calls.push(["toast",msg]),close:()=>window.calls.push(["close"]),runPrompt:async text=>window.calls.push(["prompt",text]),create:async(kind,day)=>window.calls.push(["create",kind,day]),attention:()=>window.calls.push(["attention"]),search:()=>window.calls.push(["search"]),navigate:mod=>window.calls.push(["navigate",mod]),goChat:()=>window.calls.push(["chat"]),attach:()=>window.calls.push(["attach"]),voice:()=>window.calls.push(["voice"]),openProject:id=>window.calls.push(["project",id])};window.vishnuP203.load();'+
'</script></body></html>';
const server=createServer(async(req,res)=>{
 const url=new URL(req.url,'http://localhost');
 function out(data,status=200,mime='application/json'){res.writeHead(status,{'content-type':mime});res.end(mime==='application/json'?JSON.stringify(data):data)}
 if(url.pathname==='/')return out(html,200,'text/html');
 if(url.pathname==='/client.js')return out(js,200,'application/javascript');
 if(url.pathname==='/client.css')return out(css,200,'text/css');
 requests.push(url.pathname+url.search);
 const path=url.pathname;
 if(path==='/iphone/api/everyday/timeline'){
   const day=url.searchParams.get('day');
   return out({items:day===today?[{id:'task-a',title:'Real scheduled task',kind:'task',due_at:day,status:'scheduled'},{id:'meeting-a',title:'Real meeting',kind:'commitment',due_at:day+'T09:00:00Z',status:'scheduled'}]:[]});
 }
 if(path==='/iphone/api/projects/timeline')return out({items:url.searchParams.get('day')===today?[{id:'project-task-one',project_id:'project-one',project_name:'Verified Project',title:'Project task scheduled',status:'planned',due_date:today}]:[]});
 if(path==='/iphone/api/approvals-center')return out({approvals});
 if(path==='/iphone/api/approvals-center/approval-one')return out({approval_id:'approval-one',title:'Approve test change',tool:'governed_tool',description:'Exact test action',status:'pending'});
 if(path==='/iphone/api/approval/approval-one/approve'){approvals=[];return out({status:'approved',reply:'Approved through canonical authority.'})}
 if(path==='/iphone/api/work/attention')return out({items:[],counts:{total:0}});
 if(path==='/iphone/api/work/summary')return out({counts:{active:0},work_orders:[]});
 if(path==='/iphone/api/projects')return out({projects:[{id:'project-one',name:'Verified Project',status:'active',progress_percent:42},{id:'archived-one',name:'Archived Project',status:'archived'}]});
 if(path==='/iphone/api/agents/summary')return out({working_now:0,active_instances:0,total_agents:8});
 if(path==='/iphone/api/agents')return out({agents:[{name:'Definition not running'}]});
 if(path==='/iphone/api/activities')return out({activities:[{id:'log-1',action:'Real audit event',created_at:new Date().toISOString(),status:'completed'}]});
 if(path==='/iphone/api/everyday/items/task-a')return out({item:{id:'task-a',title:'Real scheduled task',due_at:today,status:'scheduled',source:'today_ui'}});
 if(path==='/iphone/api/everyday/task-a/complete'){created.push({complete:true});return out({id:'task-a',status:'completed'})}
 return out({detail:'Unmapped test endpoint'},404);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true}),port=server.address().port;
try{
 for(const width of [320,390,1440]){
  approvals=[{approval_id:'approval-one',title:'Approve test change',status:'pending',description:'A governed action'}];
  requests=[];created=[];
  const mobile=width<500,page=await browser.newPage({viewport:{width,height:mobile?844:960},deviceScaleFactor:mobile?2:1,isMobile:mobile,hasTouch:mobile});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',dialog=>dialog.accept());
  await page.goto('http://127.0.0.1:'+port+'/');
  await page.locator('.p203-shell').waitFor();
  await page.getByRole('heading',{name:/Good (Morning|Afternoon|Evening), Test Owner/}).waitFor();
  await page.getByText('Real scheduled task').first().waitFor();
  assert.ok(await page.getByText('Verified Project').count()>0,'canonical Project visible');
  assert.equal(await page.getByText('Definition not running').count(),0,'catalog agents must not pretend to be running');
  assert.ok((await page.locator('.p203-metric strong').allTextContents()).includes('1'),'real approval count');
  assert.ok(! (await page.locator('#todayCommandDashboard').innerText()).includes('Archived Project'),'archived Project hidden');
  await page.locator('[data-p203="summarize"]').click();
  const groundedDraft=await page.locator('#p203TopDraft').inputValue();
  assert.ok(groundedDraft.includes('Real scheduled task')&&groundedDraft.includes('Project task scheduled')&&groundedDraft.includes('Verified Project'),'Quick AI action must preview verified source data');
  assert.equal(await page.evaluate(()=>window.calls.filter(x=>x[0]==='prompt').length),0,'Quick actions may not send data without review');
  await page.locator('[data-p203="approvalDetail"]').first().click();
  await page.getByText('Exact test action').waitFor();
  await page.getByRole('button',{name:'Approve after review'}).click();
  await page.waitForFunction(()=>document.querySelector('.p203-metric.red strong')?.textContent==='0');
  assert.ok(requests.some(x=>x==='/iphone/api/approval/approval-one/approve'));
  await page.locator('#p203TopDraft').fill('Ask about my verified day');
  assert.equal(await page.locator('#p203BottomDraft').inputValue(),'Ask about my verified day','the upper and lower composer share one draft');
  await page.locator('#p203HeroForm .p203-send').click();
  assert.deepEqual((await page.evaluate(()=>window.calls.filter(x=>x[0]==='prompt').at(-1))),['prompt','Ask about my verified day']);
  const before=await page.locator('.p203-date-label').textContent();
  await page.locator('[data-p203="nextDay"]').click();
  await page.waitForFunction(previous=>document.querySelector('.p203-date-label')?.textContent!==previous,before);
  await page.getByText(/Nothing scheduled for/).waitFor();
  assert.ok(!await page.getByText('Real scheduled task').count(),'date-dependent source switched');
  await page.locator('[data-p203="goToday"]').click();
  await page.getByText('Real scheduled task').first().waitFor();
  await page.getByText('Project task scheduled').first().waitFor();
  await page.locator('[data-p203="projectTask"]').first().click();
  assert.deepEqual(await page.evaluate(()=>window.calls.filter(x=>x[0]==='project').at(-1)),['project','project-one']);
  await page.locator('[data-p203="addEvent"]').click();
  assert.deepEqual(await page.evaluate(()=>window.calls.filter(x=>x[0]==='create').at(-1)),['create','meeting',today]);
  if(mobile){
   await page.getByRole('navigation',{name:'Today mobile navigation'}).waitFor();
   assert.equal(await page.locator('.p203-mobile-nav [aria-current="page"]').count(),1);
   const geometry=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
   assert.ok(geometry.scroll<=geometry.width+3,'No mobile overflow '+JSON.stringify(geometry));
  }
  if(dir)await page.screenshot({path:dir+'/today-'+width+'.png',fullPage:false});
  assert.deepEqual(errors,[],errors.join(' | '));
  await page.close();
 }
}finally{await browser.close();await new Promise(resolve=>server.close(resolve))}
console.log('P2-03 desktop/mobile canonical read model, approval review, date switching, draft sync and actions qualified.');
