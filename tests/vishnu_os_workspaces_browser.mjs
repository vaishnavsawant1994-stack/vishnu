/* Vishnu OS Workspace browser smoke at phone/tablet/desktop widths.
 * Isolated fake transport verifies UI wiring, not live owner/device authentication.
 */
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require('playwright');
const root=new URL('../',import.meta.url);
const css=await readFile(new URL('pwa/vishnu-os-workspaces.css',root),'utf8');
const js=await readFile(new URL('pwa/vishnu-os-workspaces.js',root),'utf8');
const browser=await chromium.launch({headless:true});
try{
 for(const viewport of [{width:390,height:844},{width:820,height:1024},{width:1440,height:900}]){
  const page=await browser.newPage({viewport});
  await page.setContent('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body></body></html>');
  await page.addStyleTag({content:css});
  await page.evaluate(()=>{
   window.osFixture={
    rows:[],views:{},calls:[],
    project:{id:'project-1',name:'Patient CRM',description:'Verified Project',status:'active',task_count:3}
   };
   window.vishnuChatBridge={
    openModule(name){window.osFixture.destination=name;},
    setDraft(value){window.osFixture.draft=value;},
    api:async function(path,options={}){
     const f=window.osFixture,method=options.method||'GET',body=options.body?JSON.parse(options.body):{};
     f.calls.push({path,method});
     if(path==='/work/summary')return {work_orders:[],authority:'read_only_projection'};
     if(path==='/work/attention')return {items:[],counts:{total:0},authority:'read_only_projection'};
     if(path==='/projects')return {projects:[f.project]};
     assert.ok(path.startsWith('/os/workspaces'),'Unexpected API '+path);
     const suffix=path.slice('/os/workspaces'.length);
     const expanded=w=>({...w,linked_counts:{project:w.links.length,work:0,agent:0,file:0,knowledge:0,product:0,artifact:0,conversation:0}});
     if(suffix===''&&method==='GET')return {workspaces:f.rows.map(expanded),templates:['blank','3d']};
     if(suffix===''&&method==='POST'){
      let w=f.rows.find(x=>x.request_id===body.request_id);
      if(!w){w={id:'space-'+(f.rows.length+1),name:body.name,description:body.description,template_id:body.template_id,
       request_id:body.request_id,status:'active',pinned:false,links:[]};f.rows.push(w);}
      return {workspace:expanded(w)};
     }
     const match=suffix.match(/^\/([^/]+)(.*)$/);
     if(!match)throw Error('Unknown Workspace route '+suffix);
     const w=f.rows.find(x=>x.id===match[1]);
     if(!w)throw Error('Workspace not found '+match[1]);
     const tail=match[2];
     if(tail==='/summary'&&method==='GET')return {workspace:expanded(w),
      projects:w.links.some(l=>l.resource_id==='project-1')?[f.project]:[]};
     if(tail==='/links'&&method==='POST'){w.links.push(body);return {workspace:expanded(w)};}
     if(tail==='/studio/views'&&method==='GET')return {views:f.views[w.id]||[]};
     if(tail==='/studio/views'&&method==='POST'){
      const view={id:'view-1',name:body.name,layout:body.layout};
      (f.views[w.id]||=[]).unshift(view);return {view};
     }
     if(tail.startsWith('/studio/views/')&&method==='PUT'){
      const view=f.views[w.id].find(v=>v.id===tail.split('/').pop());
      Object.assign(view,body);return {view};
     }
     if(tail===''&&method==='PATCH'){Object.assign(w,body);return {workspace:expanded(w)};}
     throw Error('Unexpected API '+path+' '+method);
    }
   };
  });
  await page.addScriptTag({content:js});
  await page.evaluate(()=>window.vishnuOsWorkspaces.open());
  await page.locator('#vishnuOs1620 h1').getByText('Workspaces').waitFor();
  await page.locator('#vishnuOs1620 [data-vos="create"]').first().click();
  await page.locator('#vishnuOs1620 h1').getByText('Create a Workspace').waitFor();
  await page.locator('#vishnuOs1620 [data-vos="template:3d"]').click();
  await page.locator('#vosWorkspaceForm [name="name"]').fill('Vishnu Character');
  await page.locator('#vosWorkspaceForm [name="description"]').fill('Sources and revisions');
  await page.locator('#vosWorkspaceForm button[type="submit"]').click();
  await page.locator('#vishnuOs1620 h1').getByText('Vishnu Character').waitFor();
  const created=await page.evaluate(()=>window.osFixture.rows[0]);
  assert.equal(created.template_id,'3d');
  assert.equal(created.description,'Sources and revisions');
  await page.locator('#vishnuOs1620 [data-vos="link-project"]').click();
  await page.locator('#vishnuOs1620').getByText('Patient CRM').waitFor();
  await page.locator('#vishnuOs1620 [data-vos="studio"]').first().click();
  await page.locator('#vishnuOs1620').getByText('Open panels (0)').waitFor();
  await page.locator('#vishnuOs1620 [data-vos="add-panel"]').click();
  await page.locator('#vishnuOs1620 .vos-studio-panel').getByText('Patient CRM').waitFor();
  await page.locator('#vishnuOs1620 [data-vos="save-view"]').click();
  await page.waitForFunction(()=>window.osFixture.views['space-1']?.length===1);
  await page.evaluate(()=>window.vishnuOsWorkspaces.command());
  await page.locator('#vosCommandTitle').waitFor();
  await page.locator('#vishnuOs1620 [data-vos-input="command"]').fill('Workspaces');
  assert.ok((await page.locator('#vishnuOs1620 .vos-command-panel .vos-list-row').count())>0);
  await page.locator('#vishnuOs1620 .vos-command-panel [data-vos="close-command"]').click();
  const rect=await page.evaluate(()=>({viewport:innerWidth,
   documentWidth:document.documentElement.scrollWidth,
   rootWidth:document.getElementById('vishnuOs1620').getBoundingClientRect().width}));
  assert.ok(rect.documentWidth<=rect.viewport+1,'No horizontal document overflow '+JSON.stringify(rect));
  assert.ok(rect.rootWidth<=rect.viewport+1,'Overlay fits viewport '+JSON.stringify(rect));
  await page.close();
 }
 console.log('Vishnu OS Workspace UI smoke passed for phone, tablet and desktop.');
}finally{await browser.close();}
