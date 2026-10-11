import assert from "node:assert/strict";
import { chromium } from "playwright";
import { breakpointNeighbours, assertNoViewportOverflow } from "./device_matrix.mjs";

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "block", reducedMotion: "reduce" });
const page = await context.newPage();
const pageErrors = [];
page.on("pageerror", error => pageErrors.push(error.message));

await page.route("https://accounts.google.com/**", route => route.fulfill({ status: 200, contentType: "application/javascript", body: "" }));
await page.route("**/iphone/api/**", async route => {
  const path = new URL(route.request().url()).pathname;
  if (path.endsWith("/status")) return route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Owner verification required" }) });
  if (path.endsWith("/access/options")) {
    await new Promise(resolve => setTimeout(resolve, 40));
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ password_available: true, passkey_available: false, google_available: false }) });
  }
  return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
});

try {
  await page.goto("http://127.0.0.1:4173/standalone/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => !document.querySelector("#enrollPanel").classList.contains("hidden"));
  const widths = breakpointNeighbours();
  for (const width of widths) {
    const height = width < 700 ? 844 : 960;
    await page.setViewportSize({ width, height });
    const layout = await page.evaluate(() => {
      const rect = document.querySelector("#enrollPanel").getBoundingClientRect();
      return {
        viewport: innerWidth,
        document: document.documentElement.scrollWidth,
        panel: { left: rect.left, right: rect.right, width: rect.width, bottom: rect.bottom },
      };
    });
    assertNoViewportOverflow(assert, layout, width, "breakpoint-neighbour qualification");
    assert.ok(layout.panel.width > 0 && layout.panel.left >= -1 && layout.panel.right <= width + 1,
      `enrollment panel escapes breakpoint-neighbour viewport ${width}px: ${JSON.stringify(layout)}`);
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await context.setOffline(true);
  assert.ok(await page.locator("#enrollPanel").isVisible(), "already-rendered owner entry remains visible when network drops");
  assert.ok(await page.locator("#passwordChoice").isVisible(), "owner password choice remains reachable when offline");
  await context.setOffline(false);
  await page.click("#passwordChoice");
  assert.ok(await page.locator("#ownerPassword").isVisible(), "owner flow recovers after network reconnects");
  assert.deepEqual(pageErrors, [], `breakpoint/network qualification has page errors: ${JSON.stringify(pageErrors)}`);
  console.log(`Breakpoint-neighbour qualification passed at ${widths.length} widths with slow API, offline visibility and reconnect checks.`);
} finally {
  await context.close();
  await browser.close();
}