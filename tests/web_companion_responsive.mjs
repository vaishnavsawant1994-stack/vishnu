import assert from "node:assert/strict";
import { chromium } from "playwright";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
const errors = [];
page.on("pageerror", error => errors.push(error.message));

try {
  await page.goto("http://127.0.0.1:4174/", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#home.active");
  const unnamedControls=await page.locator("button:visible").evaluateAll(buttons=>buttons
    .filter(button=>!((button.getAttribute("aria-label")||"").trim()||(button.innerText||button.textContent||"").trim()||button.getAttribute("title")))
    .map(button=>button.outerHTML));
  assert.deepEqual(unnamedControls,[],"visible buttons must have accessible names");
  for(const [id,name] of [["memory-query","Search memory"],["runtime-origin","Secure runtime URL"],["pair-token","Pairing token"],["pair-code","Pairing code"],["owner-secret","Owner secret"],["prompt","Ask Vishnu"]]){
    assert.equal(await page.locator(`#${id}`).getAttribute("aria-label"),name,`${id} must have a programmatic label`);
  }
  const widths = new Set([320, 360, 375, 390, 430, 600, 768, 820, 1024, 1280, 1440, 1920, 2560]);
  for (let width = 320; width <= 2560; width += 40) widths.add(width);
  for (const width of [...widths].sort((a, b) => a - b)) {
    await page.setViewportSize({ width, height: width < 700 ? 568 : 960 });
    const metrics = await page.evaluate(() => {
      const rect = selector => {
        const box = document.querySelector(selector).getBoundingClientRect();
        return { left: box.left, right: box.right, top: box.top, bottom: box.bottom, width: box.width, height: box.height };
      };
      return {
        viewport: innerWidth,
        document: document.documentElement.scrollWidth,
        composer: rect("footer form"),
        send: rect("footer form button"),
        mode: rect(".mode"),
        firstCard: rect(".cards article"),
        footer: rect("footer"),
        title: getComputedStyle(document.querySelector("h1")).fontSize,
      };
    });
    assert.ok(metrics.document <= width, `Web companion page overflow at ${width}: ${JSON.stringify(metrics)}`);
    assert.ok(metrics.composer.left >= -1 && metrics.composer.right <= width + 1, `Composer escaped viewport at ${width}`);
    assert.ok(metrics.send.width >= 44 && metrics.send.height >= 44, `Send touch target under 44px at ${width}`);
    assert.ok(parseFloat(metrics.title) >= 22, `Title became too small at ${width}`);
    if (width <= 600) assert.ok(metrics.mode.bottom <= metrics.footer.top + 1, `Home mode selector is covered by the composer at ${width}x568: ${JSON.stringify(metrics)}`);
    if (width <= 390) assert.ok(metrics.firstCard.bottom <= metrics.composer.top + 1, `First Home card is covered by the composer at ${width}x568: ${JSON.stringify(metrics)}`);
    if ([320, 390, 768, 1440, 2560].includes(width)) {
      const name = width < 400 ? "phone" : width < 900 ? "tablet" : width < 2000 ? "desktop" : "wide";
      await page.screenshot({ path: `artifacts/web-companion-${name}-${width}.png`, fullPage: true });
    }
  }

  for(const width of [320,390,768,1440,2560]){
    await page.setViewportSize({width,height:width<700?568:960});
    await page.getByRole("button",{name:"Memory"}).click();
    const memory=await page.evaluate(()=>({page:document.documentElement.scrollWidth,viewport:innerWidth,form:document.querySelector("#memory-search").getBoundingClientRect()}));
    assert.ok(memory.page<=width&&memory.form.left>=0&&memory.form.right<=width,`Memory screen reflow failed at ${width}: ${JSON.stringify(memory)}`);
    await page.fill("#memory-query","long-form project context");
    await page.locator("#memory-search button").click();
    assert.match(await page.locator("#memory-results").innerText(),/Pair a secure runtime first/,"unpaired memory search must explain how access becomes available");
    if(width===390)await page.screenshot({path:"artifacts/web-companion-memory-phone-390.png",fullPage:true});

    await page.getByRole("button",{name:"Control"}).click();
    const pairing=await page.evaluate(()=>({page:document.documentElement.scrollWidth,viewport:innerWidth,fields:[...document.querySelectorAll("#pair input,#emergency input")].map(input=>input.getBoundingClientRect())}));
    assert.ok(pairing.page<=width&&pairing.fields.every(field=>field.width>0&&field.left>=0&&field.right<=width),`Control form reflow failed at ${width}: ${JSON.stringify(pairing)}`);
    const controlFooter=await page.evaluate(()=>({position:getComputedStyle(document.querySelector("footer")).position,pair:document.querySelector("#pair button").getBoundingClientRect(),footer:document.querySelector("footer").getBoundingClientRect()}));
    assert.equal(controlFooter.position,"static","Control composer must not be fixed over pairing or emergency actions");
    assert.ok(controlFooter.pair.bottom<=controlFooter.footer.top,"Pairing action must remain above the composer in document flow");
    if(width===390)await page.screenshot({path:"artifacts/web-companion-control-phone-390.png",fullPage:true});

    await page.getByRole("button",{name:"Dashboard"}).click();
    const dashboard=await page.evaluate(()=>({page:document.documentElement.scrollWidth,viewport:innerWidth,cards:[...document.querySelectorAll("#dashboard article")].map(card=>card.getBoundingClientRect())}));
    assert.equal(dashboard.cards.length,4,"Dashboard retains all status cards");
    assert.ok(dashboard.page<=width&&dashboard.cards.every(card=>card.width>0&&card.left>=0&&card.right<=width),`Dashboard reflow failed at ${width}: ${JSON.stringify(dashboard)}`);
    if(width===768)await page.screenshot({path:"artifacts/web-companion-dashboard-tablet-768.png",fullPage:true});
  }

  await page.setViewportSize({ width: 390, height: 360 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const reduced = await page.evaluate(() => ({
    requested: matchMedia("(prefers-reduced-motion: reduce)").matches,
    pulse: getComputedStyle(document.querySelector(".core"), "::before").animationName,
  }));
  assert.equal(reduced.requested, true);
  assert.equal(reduced.pulse, "none");
  await page.getByRole("button", { name: "Memory" }).focus();
  assert.equal(await page.evaluate(() => document.activeElement?.textContent), "Memory");
  await page.getByRole("button", { name: "Control" }).click();
  assert.ok(await page.locator("#runtime-origin").isVisible(), "secure-pairing fields remain reachable on short screens");
  await page.getByRole("button",{name:"Home"}).click();
  await page.fill("#prompt","Long composer content must produce a useful unpaired response");
  await page.locator("#ask button").click();
  await page.waitForFunction(()=>document.querySelector("#reply").hidden===false);
  assert.match(await page.locator("#reply").innerText(),/Pair a secure runtime first/,"unpaired chat submission must remain a visible recovery state");
  assert.deepEqual(errors, [], "web companion renders without uncaught JavaScript errors");
  console.log(`Web companion responsive qualification passed ${widths.size} widths from 320px through 2560px, 360px short-height layout, keyboard focus and reduced motion.`);
} finally {
  await browser.close();
}
