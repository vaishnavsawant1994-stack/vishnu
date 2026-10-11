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

async function mockApi(page){
  await page.route('**/iphone/api/products**',async route=>{
    const request=route.request();const url=new URL(request.url());const path=url.pathname;const method=request.method();let body;
    if(path==='/iphone/api/products'&&method==='GET')body={products:[product]};
    else if(path==='/iphone/api/products/summary')body={summary:{total:1,development:0,ready:0,live:1,clients:1,needs_attention:0}};
    else if(path==='/iphone/api/products/activity')body={activity};
    else if(path===`/iphone/api/products/${product.id}`&&method==='GET')body={product,components,builds:[]};
    else if(path===`/iphone/api/products/${product.id}/distribution/status`)body={signing_configured:true,portable_package:true,current_version:'2.1.0',current_version_frozen:true,frozen_versions:['2.1.0'],production_distribution_ready:true,native_builds:'target-builder qualification required'};
    else if(path===`/iphone/api/products/${product.id}/licenses`&&method==='GET')body={licenses:[]};
    else if(path===`/iphone/api/products/${product.id}/manifest`)body={manifest:{schema:'vishnu.product/v1',product_id:product.id,name:product.name,version:product.version,ai_policy:{mode:'hybrid',credentials:'runtime-provisioned'}}};
    if(body===undefined)return route.fulfill({status:404,contentType:'application/json',body:JSON.stringify({detail:`No mock for ${method} ${path}`})});
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
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
  assert.ok(await desktop.locator('.sidebar a.active').getByText('Our Products').isVisible());
  const columns=await desktop.locator('#productGrid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length);
  assert.ok(columns>=2,'desktop product catalog should use multiple columns');
  await noOverflow(desktop,'desktop');await shot(desktop,'our-products-desktop.png');

  await desktop.locator('[data-product-id="product-acme"] [data-action="open"]').click();
  await desktop.locator('#detailDialog[open]').waitFor();
  await desktop.getByRole('button',{name:'Package & License'}).click();
  await desktop.getByText('Production portable package').waitFor();
  assert.ok(await desktop.locator('[data-download-production]').isEnabled());
  assert.ok(await desktop.getByRole('button',{name:'Issue signed license'}).isEnabled());
  assert.ok(await desktop.getByText('Frozen / immutable').isVisible());
  await shot(desktop,'our-products-package-license-desktop.png');

  const mobile=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});await mockApi(mobile);
  await mobile.goto(`${base}/iphone/our-products.html`,{waitUntil:'networkidle'});
  await mobile.getByRole('heading',{name:'Our Products'}).waitFor();
  await mobile.locator('[data-product-id="product-acme"] h3').getByText('ACME Sales Employee',{exact:true}).waitFor();
  const mobileColumns=await mobile.locator('#productGrid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length);
  assert.equal(mobileColumns,1,'mobile product catalog should be one column');
  assert.equal(await mobile.locator('.side-nav').evaluate(el=>getComputedStyle(el).display),'none');
  await noOverflow(mobile,'mobile');await shot(mobile,'our-products-mobile.png');

  await mobile.locator('[data-product-id="product-acme"] [data-action="open"]').click();
  await mobile.getByRole('button',{name:'Package & License'}).click();
  await mobile.getByText('Production portable package').waitFor();
  await noOverflow(mobile,'mobile detail');await shot(mobile,'our-products-package-license-mobile.png');
} finally {await browser.close()}
console.log('Our Products desktop/mobile browser qualification passed');
