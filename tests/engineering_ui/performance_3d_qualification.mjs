import assert from "node:assert/strict";
import { chromium } from "playwright";

const browser = await chromium.launch({ headless: true });
const origin = "http://127.0.0.1:4173/standalone/";

async function mockApi(page, status = 401) {
  await page.route("https://accounts.google.com/**", route => route.fulfill({ status: 200, contentType: "application/javascript", body: "" }));
  await page.route("**/iphone/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/status")) {
      if (status !== 200) return route.fulfill({ status, contentType: "application/json", body: JSON.stringify({ detail: "Owner verification required" }) });
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ model: { state: "ready" }, conversations: [], conversation: null, memory_count: 0, active_qualification: null }),
      });
    }
    if (path.endsWith("/access/options")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ password_available: true, passkey_available: false, google_available: false }) });
    if (path.endsWith("/everyday/active") || path.endsWith("/everyday/timeline")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [] }) });
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

try {
  {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "block", reducedMotion: "reduce" });
    const page = await context.newPage();
    await page.addInitScript(() => {
      window.__engineeringCls = 0;
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) if (!entry.hadRecentInput) window.__engineeringCls += entry.value;
      }).observe({ type: "layout-shift", buffered: true });
    });
    await mockApi(page, 401);
    const started = Date.now();
    await page.goto(origin, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => !document.querySelector("#enrollPanel")?.classList.contains("hidden"));
    const firstUsableMs = Date.now() - started;
    const metrics = await page.evaluate(() => {
      const resources = performance.getEntriesByType("resource");
      const transferBytes = resources.reduce((sum, item) => sum + Math.max(0, Number(item.transferSize || 0)), 0);
      const navigation = performance.getEntriesByType("navigation")[0];
      return {
        resourceCount: resources.length,
        transferBytes,
        domContentLoadedMs: navigation ? Math.round(navigation.domContentLoadedEventEnd) : 0,
        cls: Number(window.__engineeringCls || 0),
      };
    });
    assert.ok(firstUsableMs <= 5000, `first usable owner surface exceeded 5s safety budget: ${firstUsableMs}ms`);
    assert.ok(metrics.resourceCount <= 100, `resource count exceeded safety budget: ${JSON.stringify(metrics)}`);
    assert.ok(metrics.transferBytes <= 10_000_000, `transfer size exceeded 10MB safety budget: ${JSON.stringify(metrics)}`);
    assert.ok(metrics.cls <= 0.25, `layout shift exceeded qualification budget: ${JSON.stringify(metrics)}`);
    console.log(`performance qualification passed: firstUsable=${firstUsableMs}ms resources=${metrics.resourceCount} transfer=${metrics.transferBytes} cls=${metrics.cls}`);
    await context.close();
  }

  {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "block", reducedMotion: "reduce" });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.addInitScript(() => {
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function(kind, ...args) {
        if (kind === "webgl" || kind === "webgl2" || kind === "experimental-webgl") return null;
        return original.call(this, kind, ...args);
      };
    });
    await mockApi(page, 200);
    await page.goto(origin, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(500);
    const presence = await page.evaluate(() => {
      document.dispatchEvent(new Event("visibilitychange"));
      const canvas = document.querySelector("#neuralCanvas");
      const glow = document.querySelector(".core-glow");
      const rect = canvas?.getBoundingClientRect();
      const style = glow ? getComputedStyle(glow) : null;
      return {
        canvasPresent: Boolean(canvas),
        canvasWidth: rect?.width || 0,
        canvasHeight: rect?.height || 0,
        reducedMotionMatches: matchMedia("(prefers-reduced-motion: reduce)").matches,
        animationDuration: style?.animationDuration || "",
        horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
      };
    });
    assert.ok(presence.canvasPresent, "living Vishnu canvas is missing");
    assert.ok(presence.canvasWidth > 0 && presence.canvasHeight > 0, `living Vishnu canvas has no geometry: ${JSON.stringify(presence)}`);
    assert.equal(presence.reducedMotionMatches, true, "reduced-motion preference was not propagated");
    assert.ok(!presence.horizontalOverflow, `living presence causes mobile horizontal overflow: ${JSON.stringify(presence)}`);
    assert.deepEqual(errors, [], `living presence failed when WebGL was unavailable: ${JSON.stringify(errors)}`);
    console.log(`living Vishnu / WebGL fallback / reduced-motion qualification passed (${presence.animationDuration || "no animation"})`);
    await context.close();
  }
} finally {
  await browser.close();
}
