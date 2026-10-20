import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const ui = await readFile(new URL('../pwa/workspaces-ui.js', import.meta.url), 'utf8');
const css = await readFile(new URL('../pwa/workspaces-ui.css', import.meta.url), 'utf8');
const html = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>${css}</style></head><body><div id="moduleTitle"></div><div id="moduleText"></div><div id="moduleBody"></div><script>window.openModule=async()=>{};window.vishnuChatBridge={showToast:()=>{},api:async(path,options={})=>{const response=await fetch('/iphone/api'+path,{method:options.method||'GET',headers:{'Content-Type':'application/json'},body:options.body});const data=await response.json();if(!response.ok)throw new Error(data.detail||'request failed');return data}};</script><script>${ui}</script></body></html>`;
let workspace = null, views = [], nextId = 1, opened = 0;
const server = createServer(async (request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1');
  if (url.pathname === '/') { response.writeHead(200, {'content-type':'text/html'}); response.end(html); return; }
  if(url.pathname==='/iphone/api/agents'||url.pathname==='/iphone/api/agents/summary'){response.writeHead(200,{'content-type':'application/json'});response.end(JSON.stringify(url.pathname.endsWith('/summary')?{total_agents:1,total_instances:0,active_instances:0,working_now:0,idle:0}:{agents:[{id:'agent-test',name:'Test Agent',description:'Browser test fixture',instance_count:0,active_instance_count:0}]}));return;}
  if (!url.pathname.startsWith('/iphone/api/workspaces')) { response.writeHead(404); response.end(); return; }
  let body = {}; if (request.method !== 'GET') { const chunks=[]; for await (const chunk of request) chunks.push(chunk); if(chunks.length)body=JSON.parse(Buffer.concat(chunks).toString()); }
  const base='/iphone/api/workspaces';
  if(url.pathname===base && request.method==='GET') { const rows=workspace&&((url.searchParams.get('status')==='all')||workspace.status===url.searchParams.get('status'))?[workspace]:[]; response.writeHead(200,{'content-type':'application/json'});response.end(JSON.stringify({workspaces:rows,counts:{all:workspace&&workspace.status==='active'?1:0,pinned:workspace?.is_pinned?1:0,archived:workspace?.status==='archived'?1:0,types:{business:workspace?.workspace_type==='business'?1:0}}}));return; }
  if(url.pathname===base && request.method==='POST') { workspace={id:'ws-'+nextId++,owner_id:'owner',name:body.name,description:body.description,workspace_type:body.workspace_type,status:'active',is_pinned:false,is_demo:false};response.writeHead(201,{'content-type':'application/json'});response.end(JSON.stringify({workspace}));return; }
  if(url.pathname===base+'/reference-demo' && request.method==='POST') { workspace={id:'demo-1',owner_id:'owner',name:'Rudra Health Care · Reference Demo',description:'Illustrative only',workspace_type:'business',status:'active',is_pinned:false,is_demo:true};response.writeHead(201,{'content-type':'application/json'});response.end(JSON.stringify({workspace,notice:'Illustrative reference demo; not a real organization or customer record.'}));return; }
  const match=url.pathname.slice(base.length).match(/^\/([^/]+)(?:\/(.*))?$/);if(!match){response.writeHead(404);response.end();return;}const id=decodeURIComponent(match[1]),sub=match[2]||'';
  if(!workspace||workspace.id!==id){response.writeHead(404,{'content-type':'application/json'});response.end(JSON.stringify({detail:'Workspace not found'}));return;}
  if(sub==='open'&&request.method==='POST'){opened++;workspace.last_opened_at=new Date().toISOString();response.writeHead(200,{'content-type':'application/json'});response.end(JSON.stringify({workspace}));return;}
  if(!sub&&request.method==='PATCH'){workspace={...workspace,...body};response.writeHead(200,{'content-type':'application/json'});response.end(JSON.stringify({workspace}));return;}
  if(sub==='studio/views'&&request.method==='GET'){response.writeHead(200,{'content-type':'application/json'});response.end(JSON.stringify({views}));return;}
  if(sub==='studio/views'&&request.method==='PUT'){let view=views.find(item=>item.name===body.name);if(view)view.layout=body.layout;else{view={id:'view-1',name:body.name,layout:body.layout};views.push(view)}response.writeHead(200,{'content-type':'application/json'});response.end(JSON.stringify({view}));return;}
  response.writeHead(404,{'content-type':'application/json'});response.end(JSON.stringify({detail:'unsupported'}));
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const port=server.address().port;const browser=await chromium.launch({headless:true});
try {
  for(const viewport of [{width:1440,height:960,isMobile:false},{width:390,height:844,isMobile:true}]){
    workspace=null;views=[];opened=0;
    const page=await browser.newPage({viewport,deviceScaleFactor:viewport.isMobile?2:1,isMobile:viewport.isMobile,hasTouch:viewport.isMobile});const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`http://127.0.0.1:${port}/`);await page.evaluate(()=>window.openModule('labs'));await page.getByRole('heading',{name:'Workspaces'}).first().waitFor();
    assert.match(await page.locator('#moduleBody').innerText(),/No workspaces here yet/);
    await page.getByRole('button',{name:/New Workspace/}).click();await page.locator('[data-workspace-form]').waitFor();
    await page.locator('[data-workspace-template="business"]').click();await page.locator('[name="name"]').fill('My Development Space');await page.locator('[name="description"]').fill('Actual test workspace record');await page.locator('[data-workspace-form] button[type="submit"]').first().click();
    await page.getByRole('heading',{name:'My Development Space'}).waitFor();assert.match(await page.locator('#moduleBody').innerText(),/No Projects are linked/);
    await page.locator('[data-workspace-settings]').click();await page.locator('[data-workspace-settings-form]').waitFor();await page.locator('[data-workspace-settings-form] [name="name"]').fill('Renamed Workspace');await page.locator('[data-workspace-settings-form] button[type="submit"]').click();await page.getByRole('heading',{name:/Renamed Workspace/}).waitFor();assert.equal(workspace.name,'Renamed Workspace');
    await page.locator('[data-workspace-agents]').click();await page.getByRole('heading',{name:'Test Agent'}).waitFor();assert.match(await page.locator('#moduleBody').innerText(),/canonical local Agent Workforce service/);
    await page.locator('[data-workspace-assets]').click();await page.getByRole('heading',{name:'No files in linked Projects'}).waitFor();
    await page.locator('[data-workspace-overview]').first().click();await page.getByRole('heading',{name:'Renamed Workspace'}).first().waitFor();
    await page.locator('[data-workspace-studio]').first().click();await page.locator('[data-studio-canvas]').waitFor();await page.locator('[data-studio-add]').click();await page.locator('[data-studio-save]').click();await page.getByText(/Studio layout saved/).waitFor({timeout:1000}).catch(()=>{});
    assert.equal(views.length,1);assert.equal(views[0].layout.panels[0].resource_id,workspace.id);
    if(viewport.isMobile){const geometry=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));assert.ok(geometry.scroll<=geometry.width+2,JSON.stringify(geometry));await page.screenshot({path:fileURLToPath(new URL('../artifacts/workspaces-mobile.png',import.meta.url)),fullPage:true});}
    else await page.screenshot({path:fileURLToPath(new URL('../artifacts/workspaces-desktop.png',import.meta.url)),fullPage:true});
    assert.equal(opened,1);assert.deepEqual(errors,[],errors.join(' | '));await page.close();
  }
} finally { await browser.close(); await new Promise(resolve=>server.close(resolve)); }
console.log('Workspace create, profile settings, Agent and Asset routes, Studio persistence and responsive browser checks passed.');
