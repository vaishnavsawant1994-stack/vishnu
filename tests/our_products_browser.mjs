import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const base=process.env.PWA_PREVIEW_URL||'http://127.0.0.1:4173';
const screenshotDir=process.env.OUR_PRODUCTS_SCREENSHOT_DIR||'';
if(screenshotDir)fs.mkdirSync(screenshotDir,{recursive:true});
const shot=async(page,name)=>{if(screenshotDir)await page.screenshot({path:`${screenshotDir}/${name}`,fullPage:false})};
const product={
  id:'product-acme',name:'ACME Sales Employee',product_type:'ai_employee',description:'Finds leads, qualifies prospects, drafts outreach and updates CRM.',client_name:'ACME Ltd',status:'live',version:'2.1.0',source_project_id:'project-acme',ai_mode:'hybrid',component_count:4,
  ai_policy:{mode:'hybrid',provider:'openai',model:'client-selected',secret_ref:'vault://hidden'},branding:{},licensing:{},permissions:{},
  targets:[{target:'web',enabled:true,config:{}},{target:'android',enabled:true,config:{}},{target:'ios',enabled:true,config:{}},{target:'windows',enabled:true,config:{}}],created_at:'2026-10-10T08:00:00Z',updated_at:'2026-10-11T17:00:00Z'
};
const components=[{id:'component-1',product_id:product.id,component_type:'agent',component_ref:'agent:research',name:'Lead Research Agent',config:{},sort_order:0,created_at:'2026-10-10T08:00:00Z'}];
const activity=[{id:'activity-1',product_id:product.id,product_name:product.name,event_type:'product.updated',message:'Product settings updated',metadata:{},created_at:'2026-10-11T17:00:00Z'}];
const capabilities=[
  {id:'cap-lead',name:'Lead Research Agent',capability_type:'agent',description:'Research companies, leads and decision makers.',source_kind:'agent',source_ref:'lead-research',client_scope:'shared',commercial_state:'internal_reusable',qualification_state:'qualified',exportable:true,reusable:true,ai_required:true,ai_modes:['hybrid'],platforms:['web'],tags:['sales','research'],metadata:{}},
  {id:'cap-outreach',name:'Personalized Outreach Workflow',capability_type:'workflow',description:'Draft and send personalized prospect outreach.',source_kind:'workflow',source_ref:'outreach-v2',client_scope:'shared',commercial_state:'internal_sellable',qualification_state:'qualified',exportable:true,reusable:true,ai_required:true,ai_modes:['client_api','hybrid'],platforms:['web'],tags:['sales','email'],metadata:{version:'2.0.0'}},
  {id:'cap-crm',name:'HubSpot CRM',capability_type:'integration',description:'Create and update CRM contacts and pipeline records.',source_kind:'integration',source_ref:'hubspot',client_scope:'shared',commercial_state:'internal_reusable',qualification_state:'tested',exportable:true,reusable:true,ai_required:false,ai_modes:[],platforms:[],tags:['crm'],metadata:{}},
  {id:'cap-template',name:'Sales Employee Base',capability_type:'product_template',description:'Reusable sales employee foundation with research, outreach and reporting.',source_kind:'product',source_ref:'sales-base',client_scope:'shared',commercial_state:'template',qualification_state:'qualified',exportable:true,reusable:true,ai_required:true,ai_modes:['hybrid'],platforms:['web','windows'],tags:['sales','employee'],metadata:{version:'2.4.0'}}
];
let request={
  id:'request-real-estate',title:'Real Estate Sales Employee',client_name:'Example Realty',requirement:'Research real-estate companies and decision makers, send personalized outreach, update CRM, schedule meetings and add property valuation.',status:'analyzed',requested_product_type:'ai_employee',requested_ai_mode:'hybrid',requested_targets:['web','windows','android'],commercial_state:'client_specific',product_id:null,project_id:null,created_at:'2026-10-12T00:00:00Z',updated_at:'2026-10-12T00:02:00Z',
  blueprint:{schema:'vishnu.product-blueprint/v1',request_id:'request-real-estate',title:'Real Estate Sales Employee',client_name:'Example Realty',recommended_product_type:'ai_employee',ai_mode:'hybrid',targets:['web','windows','android'],commercial_state:'client_specific',coverage_percent:67,reuse_count:3,extend_count:1,create_count:1,generated_at:'2026-10-12T00:02:00Z',requirements:[
    {requirement:'lead research',decision:'reuse',score:.96,capability:capabilities[0],explanation:'Reuse Lead Research Agent'},
    {requirement:'outreach',decision:'reuse',score:.94,capability:capabilities[1],explanation:'Reuse Personalized Outreach Workflow'},
    {requirement:'crm integration',decision:'reuse',score:.92,capability:capabilities[2],explanation:'Reuse HubSpot CRM'},
    {requirement:'meeting scheduling',decision:'extend',score:.58,capability:{...capabilities[1],id:'cap-calendar',name:'Calendar Workflow'},explanation:'Extend Calendar Workflow to cover real-estate scheduling'},
    {requirement:'property valuation',decision:'create',score:.12,capability:null,explanation:'No sufficiently close reusable capability was found; create a new bounded capability'}
  ],missing_work:[{kind:'extend',title:'Extend capability for meeting scheduling',requirement:'meeting scheduling',capability_id:'cap-calendar'},{kind:'create',title:'Build capability for property valuation',requirement:'property valuation',capability_id:null}]}
};
const composerSummary={requests:1,open_requests:1,product_projects_created:0,capabilities:{total:4,reusable:4,sellable:2,qualified:3}};
const lineage=[{id:'lin-1',product_id:'product-acme',source_kind:'capability',source_ref:'cap-lead',relation:'reuse',source_version:'2.0.0',metadata:{},created_at:'2026-10-11T16:00:00Z'},{id:'lin-2',product_id:'product-acme',source_kind:'project',source_ref:'project-acme',relation:'implemented_by',source_version:'',metadata:{},created_at:'2026-10-11T16:10:00Z'}];

async function mockApi(page){
  const builds=[];
  await page.route('**/iphone/api/products**',async route=>{
    const requestHttp=route.request();const url=new URL(requestHttp.url());const path=url.pathname;const method=requestHttp.method();let body;let status=200;
    if(path==='/iphone/api/products'&&method==='GET')body={products:[product]};
    else if(path==='/iphone/api/products/summary')body={summary:{total:1,development:0,ready:0,live:1,clients:1,needs_attention:0}};
    else if(path==='/iphone/api/products/activity')body={activity};
    else if(path==='/iphone/api/products/composer/summary')body={summary:{...composerSummary,product_projects_created:request.product_id?1:0,open_requests:request.product_id?0:1}};
    else if(path==='/iphone/api/products/composer/requests'&&method==='GET')body={requests:[request]};
    else if(path===`/iphone/api/products/composer/requests/${request.id}`&&method==='GET')body={request,matches:[]};
    else if(path===`/iphone/api/products/composer/requests/${request.id}/analyze`&&method==='POST')body={request,matches:[]};
    else if(path===`/iphone/api/products/composer/requests/${request.id}/product-project`&&method==='POST'){
      request={...request,status:'product_project_created',product_id:'product-real-estate',project_id:'project-real-estate'};
      body={request,product:{id:'product-real-estate',name:request.title},project:{id:'project-real-estate',name:request.title},existing:false,work_start:{status:'started',mode:'active',plan_created:true,stop_reason:'awaiting_approval',executed_task_ids:['task-1'],execution_authority:'governed'}};status=201;
    }
    else if(path===`/iphone/api/products/composer/requests/${request.id}/start-work`&&method==='POST')body={request_id:request.id,project_id:'project-real-estate',work_start:{status:'started',mode:'active',plan_created:false,stop_reason:'awaiting_approval',executed_task_ids:[],execution_authority:'governed'}};
    else if(path==='/iphone/api/products/composer/capabilities'&&method==='GET')body={capabilities,summary:composerSummary.capabilities};
    else if(path==='/iphone/api/products/composer/sync'&&method==='POST')body={synced:{agents:2,tools:3,automations:1,workflows:1,integrations:1,products:1,components:1},summary:composerSummary.capabilities};
    else if(path.startsWith('/iphone/api/products/composer/capabilities/')&&method==='PATCH')body={capability:capabilities.find(cap=>path.endsWith(cap.id))||capabilities[0]};
    else if(path==='/iphone/api/products/composer/capabilities/promote'&&method==='POST')body={capability:{...capabilities[0],id:'promoted-1'}};
    else if(path==='/iphone/api/products/composer/capabilities'&&method==='POST')body={capability:{...capabilities[0],id:'manual-1'}};
    else if(path===`/iphone/api/products/composer/products/${product.id}/lineage`)body={product_id:product.id,classification:{product_id:product.id,commercial_state:'internal_sellable',notes:'',updated_at:'2026-10-11T16:00:00Z'},lineage};
    else if(path==='/iphone/api/products/composer/products/product-real-estate/lineage')body={product_id:'product-real-estate',classification:{product_id:'product-real-estate',commercial_state:'client_specific',notes:'Created by Product Composer'},lineage:[{id:'lin-r1',product_id:'product-real-estate',source_kind:'product_request',source_ref:request.id,relation:'created_from',source_version:'',metadata:{},created_at:'2026-10-12T00:03:00Z'},{id:'lin-r2',product_id:'product-real-estate',source_kind:'project',source_ref:'project-real-estate',relation:'implemented_by',source_version:'',metadata:{},created_at:'2026-10-12T00:03:00Z'}]};
    else if(path.startsWith('/iphone/api/products/composer/products/')&&path.endsWith('/classification')&&method==='PUT')body={classification:{commercial_state:'commercial'}};
    else if(path===`/iphone/api/products/${product.id}`&&method==='GET')body={product,components,builds};
    else if(path===`/iphone/api/products/${product.id}/distribution/status`)body={signing_configured:true,portable_package:true,current_version:'2.1.0',current_version_frozen:true,frozen_versions:['2.1.0'],production_distribution_ready:true,verified_local_build_targets:['web','pwa','api','worker'],native_builds:'target-builder qualification required'};
    else if(path===`/iphone/api/products/${product.id}/builds`&&method==='GET')body={builds};
    else if(path===`/iphone/api/products/${product.id}/builds`&&method==='POST'){
      const build={id:'build-web-1',product_id:product.id,version:'2.1.0',target:'web',status:'requested',build_number:1,artifact_name:null,checksum:null,metadata:{artifact_ready:false},created_at:'2026-10-11T17:10:00Z',completed_at:null};
      builds.splice(0,builds.length,build);body={build};status=201;
    }
    else if(path===`/iphone/api/products/${product.id}/builds/build-web-1/execute`&&method==='POST'){
      Object.assign(builds[0],{status:'succeeded',artifact_name:'ACME-Sales-Employee-2.1.0-web.zip',checksum:'a'.repeat(64),completed_at:'2026-10-11T17:11:00Z',metadata:{artifact_ready:true,artifact_uri:'product-artifact://product-acme/build-web-1/ACME-Sales-Employee-2.1.0-web.zip',signing_verified:false}});body={build:builds[0],builder:'verified-local-runtime',download_ready:true};
    }
    else if(path===`/iphone/api/products/${product.id}/licenses`&&method==='GET')body={licenses:[]};
    else if(path===`/iphone/api/products/${product.id}/manifest`)body={manifest:{schema:'vishnu.product/v1',product_id:product.id,name:product.name,version:product.version,ai_policy:{mode:'hybrid',credentials:'runtime-provisioned'}}};
    if(body===undefined)return route.fulfill({status:404,contentType:'application/json',body:JSON.stringify({detail:`No mock for ${method} ${path}`})});
    return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  });
}

async function noOverflow(page,label){
  const value=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
  assert.ok(value.scroll<=value.client+2,`${label} horizontal overflow ${value.scroll}>${value.client}`);
}

const browser=await chromium.launch({headless:true});
try{
  const desktop=await browser.newPage({viewport:{width:1536,height:1024}});await mockApi(desktop);
  await desktop.goto(`${base}/iphone/our-products.html`,{waitUntil:'networkidle'});
  await desktop.getByRole('heading',{name:'Our Products'}).waitFor();
  assert.equal(await desktop.locator('#metricTotal').textContent(),'1');
  await desktop.locator('[data-product-id="product-acme"] h3').getByText('ACME Sales Employee',{exact:true}).waitFor();
  assert.ok(await desktop.getByRole('button',{name:/Create Product/}).first().isVisible());
  assert.ok(await desktop.getByRole('button',{name:'New Request'}).isVisible());
  assert.ok(await desktop.locator('.sidebar a.active').getByText('Our Products').isVisible());
  const columns=await desktop.locator('#productGrid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length);
  assert.ok(columns>=2,'desktop product catalog should use multiple columns');
  await noOverflow(desktop,'desktop');await shot(desktop,'our-products-desktop.png');

  await desktop.getByRole('button',{name:'Requests',exact:true}).click();
  await desktop.getByRole('heading',{name:'Product Requests'}).waitFor();
  await desktop.getByRole('heading',{name:'Real Estate Sales Employee'}).waitFor();
  assert.equal(await desktop.locator('#composerRequestCount').textContent(),'1');
  assert.ok(await desktop.getByText('Reuse 3').isVisible());
  assert.ok(await desktop.getByText('Create 1').isVisible());
  await noOverflow(desktop,'requests desktop');await shot(desktop,'our-products-requests-desktop.png');

  await desktop.getByRole('button',{name:'View Blueprint'}).click();
  await desktop.locator('#requestDetailDialog[open]').waitFor();
  await desktop.getByText('67% existing coverage').waitFor();
  await desktop.locator('.requirement-list').getByText('property valuation',{exact:true}).waitFor();
  assert.ok(await desktop.locator('.requirement-list').getByText(/No sufficiently close reusable capability/).isVisible());
  await noOverflow(desktop,'blueprint desktop');await shot(desktop,'our-products-blueprint-desktop.png');
  await desktop.getByRole('button',{name:/Create Product Project/}).click();
  await desktop.getByText('Product Project created',{exact:false}).first().waitFor();
  await desktop.getByText('Vishnu work started').waitFor();
  await desktop.getByText('Created From').waitFor();
  await desktop.getByRole('button',{name:'Close'}).click();

  await desktop.getByRole('button',{name:'Reusable Components'}).click();
  await desktop.getByRole('heading',{name:'Reusable Components'}).waitFor();
  await desktop.getByRole('heading',{name:'Lead Research Agent'}).waitFor();
  assert.equal(await desktop.locator('#catalogTotal').textContent(),'4');
  await noOverflow(desktop,'capabilities desktop');await shot(desktop,'our-products-capabilities-desktop.png');

  await desktop.getByRole('button',{name:'Templates',exact:true}).click();
  await desktop.getByRole('heading',{name:'Product Templates'}).waitFor();
  await desktop.getByRole('heading',{name:'Sales Employee Base'}).waitFor();
  await noOverflow(desktop,'templates desktop');await shot(desktop,'our-products-templates-desktop.png');

  await desktop.getByRole('button',{name:'Products',exact:true}).click();
  await desktop.locator('[data-product-id="product-acme"] [data-action="open"]').click();
  await desktop.locator('#detailDialog[open]').waitFor();
  await desktop.getByRole('button',{name:'Package & License'}).click();
  await desktop.getByText('Production portable package').waitFor();
  assert.ok(await desktop.locator('[data-download-production]').isEnabled());
  assert.ok(await desktop.getByRole('button',{name:'Issue signed license'}).isEnabled());
  assert.ok(await desktop.getByText('Frozen / immutable').isVisible());
  await shot(desktop,'our-products-package-license-desktop.png');

  await desktop.getByRole('button',{name:'Commercial'}).click();
  await desktop.getByText('Product purpose').waitFor();
  await shot(desktop,'our-products-commercial-desktop.png');
  await desktop.getByRole('button',{name:'Lineage'}).click();
  await desktop.getByText('Implemented By').waitFor();
  await shot(desktop,'our-products-lineage-desktop.png');

  await desktop.getByRole('button',{name:'Build & Export'}).click();
  await desktop.getByText('Web',{exact:true}).first().waitFor();
  await desktop.getByRole('button',{name:'Generate verified bundle'}).click();
  await desktop.getByRole('button',{name:'Download',exact:true}).waitFor();
  assert.ok(await desktop.getByText('Verified artifact generated').isVisible());
  assert.ok(await desktop.getByText(/Build #1/).isVisible());
  await noOverflow(desktop,'desktop build');await shot(desktop,'our-products-verified-build-desktop.png');

  const mobile=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});await mockApi(mobile);
  await mobile.goto(`${base}/iphone/our-products.html`,{waitUntil:'networkidle'});
  await mobile.getByRole('heading',{name:'Our Products'}).waitFor();
  await mobile.locator('[data-product-id="product-acme"] h3').getByText('ACME Sales Employee',{exact:true}).waitFor();
  const mobileColumns=await mobile.locator('#productGrid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length);
  assert.equal(mobileColumns,1,'mobile product catalog should be one column');
  assert.equal(await mobile.locator('.side-nav').evaluate(el=>getComputedStyle(el).display),'none');
  await noOverflow(mobile,'mobile');await shot(mobile,'our-products-mobile.png');

  await mobile.getByRole('button',{name:'Requests',exact:true}).click();
  await mobile.getByRole('heading',{name:'Product Requests'}).waitFor();
  await mobile.getByRole('heading',{name:'Real Estate Sales Employee'}).waitFor();
  await noOverflow(mobile,'requests mobile');await shot(mobile,'our-products-requests-mobile.png');
  await mobile.getByRole('button',{name:'View Blueprint'}).click();
  await mobile.locator('#requestDetailDialog[open]').waitFor();
  await mobile.getByText('67% existing coverage').waitFor();
  await noOverflow(mobile,'blueprint mobile');await shot(mobile,'our-products-blueprint-mobile.png');
  await mobile.getByRole('button',{name:'Close'}).click();

  await mobile.getByRole('button',{name:'Reusable Components'}).click();
  await mobile.getByRole('heading',{name:'Reusable Components'}).waitFor();
  await mobile.getByRole('heading',{name:'Lead Research Agent'}).waitFor();
  await noOverflow(mobile,'capabilities mobile');await shot(mobile,'our-products-capabilities-mobile.png');
} finally {await browser.close()}
console.log('Our Products Product Composer desktop/mobile browser qualification passed');
