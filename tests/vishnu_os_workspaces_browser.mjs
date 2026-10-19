/* Vishnu OS Workspace browser smoke at phone/tablet/desktop widths.
 * Isolated fake transport verifies UI wiring, not live owner/device authentication.
 */
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require('playwright');
const root=new URL('../',import.meta.url);
const css=await readFile(new URL('pwa/vishnu-os-workspaces.css',root),'utf8');
const js=await readFile(new URL('pwa/vishnu-os-workspaces.js',root),'utf8');
const outputDir=process.env.VISHNU_OS_SCREENSHOT_DIR;
if(outputDir)await mkdir(outputDir,{recursive:true});
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
     if(path==='/agents')return {agents:[{id:'agent-1',name:'Research Agent',role:'research',description:'Canonical demo agent'}]};
     if(path==='/projects/project-1')return {project:{...f.project,files:[{id:'file-1',title:'patient-schema.md',kind:'source',size_bytes:2048,indexing_state:'indexed',is_pinned:true,version_count:1}]}};
     if(!path.startsWith('/os/workspaces'))throw Error('Unexpected API '+path);
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
  if(outputDir)await page.screenshot({path:outputDir+'/screen18-create-'+viewport.width+'.png',fullPage:false});
  await page.locator('#vosWorkspaceForm [name="name"]').fill('Vishnu Character');
  await page.locator('#vosWorkspaceForm [name="description"]').fill('Sources and revisions');
  await page.locator('#vosWorkspaceForm button[type="submit"]').click();
  await page.locator('#vishnuOs1620 h1').getByText('Vishnu Character').waitFor();
  const created=await page.evaluate(()=>window.osFixture.rows[0]);
  assert.equal(created.template_id,'3d');
  assert.equal(created.description,'Sources and revisions');
  if(outputDir)await page.screenshot({path:outputDir+'/screen19-overview-'+viewport.width+'.png',fullPage:false});
  await page.locator('#vishnuOs1620 [data-vos="link-project"]').click();
  await page.locator('#vishnuOs1620').getByText('Patient CRM').waitFor();
  // Screens 21–25 exercise real navigation and the existing Workspace PATCH authority.
  await page.locator('#vishnuOs1620 [data-vos="spatial"]').click();
  await page.locator('#vishnuOs1620 .vos-spatial-viewport').waitFor();
  assert.equal(await page.locator('#vishnuOs1620 .vos-spatial-object').count(),1);
  await page.locator('#vishnuOs1620 [data-vos="spatial-orbit"]').click();
  assert.ok((await page.locator('#vishnuOs1620 .vos-spatial-scene').getAttribute('style')).includes('35deg'));
  if(outputDir)await page.screenshot({path:outputDir+'/screen21-spatial-'+viewport.width+'.png',fullPage:false});
  await page.locator('#vishnuOs1620 [data-vos="agents"]').first().click();
  await page.locator('#vishnuOs1620').getByText('Research Agent').first().waitFor();
  assert.equal(await page.locator('#vishnuOs1620 .vos-agent-row').count(),1);
  await page.locator('#vishnuOs1620 .vos-agent-row').click();
  if(viewport.width<=650){await page.locator('#vishnuOs1620 .vos-inspector.mobile-open').waitFor();await page.locator('#vishnuOs1620 [data-vos="close-inspector"]').last().click();}
  if(outputDir)await page.screenshot({path:outputDir+'/screen22-agents-'+viewport.width+'.png',fullPage:false});
  await page.locator('#vishnuOs1620 [data-vos="assets"]').first().click();
  await page.locator('#vishnuOs1620 .vos-file-card').getByText('patient-schema.md').waitFor();
  assert.equal(await page.locator('#vishnuOs1620 .vos-file-card').count(),1);
  await page.locator('#vishnuOs1620 .vos-file-card').click();
  if(viewport.width<=650){await page.locator('#vishnuOs1620 .vos-inspector.mobile-open').waitFor();await page.locator('#vishnuOs1620 [data-vos="close-inspector"]').last().click();}
  await page.locator('#vishnuOs1620 [data-vos="asset-filter:pinned"]').click();
  assert.equal(await page.locator('#vishnuOs1620 .vos-file-card').count(),1);
  if(outputDir)await page.screenshot({path:outputDir+'/screen23-assets-'+viewport.width+'.png',fullPage:false});
  await page.locator('#vishnuOs1620 [data-vos="settings"]').first().click();
  await page.locator('#vosWorkspaceSettingsForm input[name="name"]').fill('Vishnu Character Workshop');
  await page.locator('#vosWorkspaceSettingsForm textarea[name="description"]').fill('Verified updated description');
  await page.locator('#vosWorkspaceSettingsForm button[type="submit"]').click();
  await page.locator('#vishnuOs1620').getByText('Changes saved.').waitFor();
  assert.equal((await page.evaluate(()=>window.osFixture.rows[0])).name,'Vishnu Character Workshop');
  if(outputDir)await page.screenshot({path:outputDir+'/screen24-settings-'+viewport.width+'.png',fullPage:false});
  await page.locator('#vishnuOs1620 [data-vos="overview"]').first().click();
  await page.locator('#vishnuOs1620 [data-vos="today"]').click();
  await page.locator('#vishnuOs1620 .vos-today-hero').waitFor();
  if(outputDir)await page.screenshot({path:outputDir+'/screen25-today-'+viewport.width+'.png',fullPage:false});
  await page.evaluate(()=>window.vishnuOsWorkspaces.open());
  await page.locator('#vishnuOs1620 [data-vos="open:space-1"]').first().click();
  await page.locator('#vishnuOs1620 [data-vos="studio"]').first().click();
  await page.locator('#vishnuOs1620').getByText('Open panels (0)').waitFor();
  await page.locator('#vishnuOs1620 [data-vos="add-panel"]').click();
  await page.locator('#vishnuOs1620 .vos-studio-panel').getByText('Patient CRM').waitFor();
  await page.locator('#vishnuOs1620 [data-vos="save-view"]').click();
  await page.waitForFunction(()=>window.osFixture.views['space-1']?.length===1);
  if(outputDir)await page.screenshot({path:outputDir+'/screen20-studio-'+viewport.width+'.png',fullPage:false});
  await page.evaluate(()=>window.vishnuOsWorkspaces.command());
  await page.locator('#vosCommandTitle').waitFor();
  if(outputDir)await page.screenshot({path:outputDir+'/screen16-command-'+viewport.width+'.png',fullPage:false});
  await page.locator('#vishnuOs1620 [data-vos-input="command"]').fill('Workspaces');
  assert.ok((await page.locator('#vishnuOs1620 .vos-command-panel .vos-list-row').count())>0);
  await page.locator('#vishnuOs1620 .vos-command-panel [data-vos="close-command"]').click();
  await page.evaluate(()=>window.vishnuOsWorkspaces.open());
  await page.locator('#vishnuOs1620 h1').getByText('Workspaces').waitFor();
  if(outputDir)await page.screenshot({path:outputDir+'/screen17-library-'+viewport.width+'.png',fullPage:false});
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => document.getElementById('vishnuOs1620')?.classList.contains('vos-hidden'));
  await page.evaluate(()=>window.vishnuOsWorkspaces.command());
  await page.locator('#vishnuOs1620.vos-command-only #vosCommandTitle').waitFor();
  await page.locator('#vishnuOs1620 .vos-command-panel [data-vos="close-command"]').click();
  await page.waitForFunction(() => document.getElementById('vishnuOs1620')?.classList.contains('vos-hidden'));
  await page.evaluate(()=>window.vishnuOsWorkspaces.open());
  await page.locator('#vishnuOs1620 h1').getByText('Workspaces').waitFor();
  const rect=await page.evaluate(()=>({viewport:innerWidth,
   documentWidth:document.documentElement.scrollWidth,
   rootWidth:document.getElementById('vishnuOs1620').getBoundingClientRect().width}));
  assert.ok(rect.documentWidth<=rect.viewport+1,'No horizontal document overflow '+JSON.stringify(rect));
  assert.ok(rect.rootWidth<=rect.viewport+1,'Overlay fits viewport '+JSON.stringify(rect));
  await page.close();
 }
 console.log('Vishnu OS Workspace UI smoke passed for phone, tablet and desktop.');
}finally{await browser.close();}
