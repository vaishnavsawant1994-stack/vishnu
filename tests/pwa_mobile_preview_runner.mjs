import { readFile, writeFile, unlink } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

// The browser suite owns Node-side API fixtures. Playwright's click()/selectOption()
// waits for DOM event dispatch, but not for the async PATCH and follow-up Ambient
// Memory reload started by the change listener. Run the canonical suite with
// explicit network/UI boundaries so its existing assertions observe completed
// persistence. Assertions and accepted values stay unchanged.
const sourceUrl = new URL('./pwa_mobile_preview.mjs', import.meta.url);
const generatedUrl = new URL('./.pwa_mobile_preview.generated.mjs', import.meta.url);
const source = await readFile(sourceUrl, 'utf8');

const sourceBefore = `  await page.locator('[data-mx-source="projects"]').click();\n  assert.equal(ambientSettings.sources.projects,true,'Ambient source permissions persist');`;
const sourceAfter = `  const ambientSourceSaved=page.waitForResponse(response=>response.url().includes('/iphone/api/memory/ambient/settings')&&response.request().method()==='PATCH'&&response.ok());\n  const ambientSourceReloaded=page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/iphone/api/memory/ambient')&&response.request().method()==='GET'&&response.ok());\n  await page.locator('[data-mx-source="projects"]').click();\n  await ambientSourceSaved;\n  await ambientSourceReloaded;\n  assert.equal(ambientSettings.sources.projects,true,'Ambient source permissions persist');`;
const before = `  await page.locator('[data-mx-retention]').selectOption('6_months');\n  assert.equal(ambientSettings.retention,'6_months','Ambient retention selection persists');`;
const after = `  const ambientRetentionSaved=page.waitForResponse(response=>response.url().includes('/iphone/api/memory/ambient/settings')&&response.request().method()==='PATCH'&&response.ok());\n  const ambientRetentionReloaded=page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/iphone/api/memory/ambient')&&response.request().method()==='GET'&&response.ok());\n  await page.locator('[data-mx-retention]').selectOption('6_months');\n  await ambientRetentionSaved;\n  await ambientRetentionReloaded;\n  await page.waitForFunction(()=>document.querySelectorAll('.rp-page[data-rp-page="memory"] .mx-candidate').length===1);\n  assert.equal(ambientSettings.retention,'6_months','Ambient retention selection persists');`;
const sphereBefore = `    await page.evaluate(() => enterHomeLanding());\n    await page.waitForTimeout(180);\n    const layout = await page.evaluate(() => {`;
const sphereAfter = `    await page.evaluate(() => enterHomeLanding());\n    await page.waitForFunction(() => {\n      const canvas = document.querySelector('#neuralCanvas');\n      if (!canvas || !canvas.width || !canvas.height) return false;\n      const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;\n      let sphereInk = 0;\n      for (let i = 0; i < pixels.length; i += 4) {\n        if (pixels[i + 3] > 12 && (pixels[i] > 80 || pixels[i + 1] > 100 || pixels[i + 2] > 150)) sphereInk++;\n      }\n      return sphereInk > 90;\n    }, undefined, { timeout: 3000 });\n    const layout = await page.evaluate(() => {`;

if (!source.includes(sourceBefore)) {
  throw new Error('Canonical Ambient source-permission assertion changed; update the synchronization runner explicitly.');
}
if (!source.includes(before)) {
  throw new Error('Canonical Ambient retention assertion changed; update the synchronization runner explicitly.');
}
if (!source.includes(sphereBefore)) {
  throw new Error('Canonical responsive sphere synchronization point changed; update the runner explicitly.');
}
const sweepBefore = "    await page.setViewportSize({width,height:844});\n    await page.evaluate(()=>enterHomeLanding());\n    const sweep=await page.evaluate(()=>{";
const sweepAfter = "    await page.setViewportSize({width,height:844});\n    await page.evaluate(()=>enterHomeLanding());\n    await page.waitForFunction(()=>{const node=document.querySelector('.v-shortcuts');if(!node)return false;const r=node.getBoundingClientRect();return r.width>0&&r.height>0;});\n    const sweep=await page.evaluate(()=>{"

if (!source.includes(sweepBefore)) {
  throw new Error('Canonical responsive sweep changed; update the Home-layout synchronization runner explicitly.');
}

let generated = source
  .replace(sourceBefore, sourceAfter)
  .replace(before, after)
  .replace(sphereBefore, sphereAfter)
  .replace(sweepBefore, sweepAfter);
await writeFile(generatedUrl, generated, 'utf8');
try {
  await import(generatedUrl.href + '?run=' + Date.now());
} finally {
  await unlink(fileURLToPath(generatedUrl)).catch(() => {});
}
