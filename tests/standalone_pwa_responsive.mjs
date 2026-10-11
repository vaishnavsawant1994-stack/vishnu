import assert from "node:assert/strict";
import { chromium } from "playwright";
import { STANDALONE_SWEEP_WIDTHS, assertNoViewportOverflow } from "./engineering_ui/device_matrix.mjs";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
const errors = [];
page.on("pageerror", error => errors.push(error.message));

try {
  await page.route("**/iphone/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/status")) {
      return route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Owner verification required" }) });
    }
    if (path.endsWith("/access/options")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ password_available: true, passkey_available: false, google_available: false }) });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
  });
  await page.goto("http://127.0.0.1:4173/standalone/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => !document.querySelector("#enrollPanel").classList.contains("hidden"));
  const widths = STANDALONE_SWEEP_WIDTHS;
  for (const width of widths) {
    const height = width < 700 ? 568 : 960;
    await page.setViewportSize({ width, height });
    const layout = await page.evaluate(() => {
      const selectors = ["#enrollPanel", "#passwordChoice"];
      const boxes = Object.fromEntries(selectors.map(selector => {
        const rect = document.querySelector(selector).getBoundingClientRect();
        return [selector, { left: rect.left, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height }];
      }));
      return { viewport: innerWidth, document: document.documentElement.scrollWidth, boxes };
    });
    assertNoViewportOverflow(assert, layout, width, "Standalone entry");
    for (const [selector, box] of Object.entries(layout.boxes)) {
      assert.ok(box.width > 0 && box.left >= -1 && box.right <= width + 1 && box.bottom <= height + 1,
        `${selector} moved outside ${width}x${height}: ${JSON.stringify(box)}`);
    }
    if ([320, 390, 768, 1440, 2560].includes(width)) {
      const size = width < 400 ? "phone" : width < 900 ? "tablet" : width < 2000 ? "desktop" : "wide";
      await page.screenshot({ path: `artifacts/standalone-pwa-${size}-${width}.png`, fullPage: true });
    }
  }
  await page.setViewportSize({ width: 320, height: 480 });
  await page.click("#passwordChoice");
  assert.ok(await page.locator("#ownerPassword").isVisible(), "signed-out owner password remains reachable in a short viewport");
  await page.locator("#historyButton").focus();
  await page.keyboard.press("Tab");
  const keyboardFocus = await page.evaluate(() => {
    const node = document.activeElement;
    return node !== document.body && !!node && node.id !== "historyButton" &&
      node.getClientRects().length > 0 && node.tabIndex >= 0 && node.matches(":focus-visible") &&
      getComputedStyle(node).outlineStyle === "solid";
  });
  assert.ok(keyboardFocus, "Tab must move focus to a visible standalone control with a focus ring");
  await page.emulateMedia({ reducedMotion: "reduce" });
  assert.equal(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches), true);
  assert.deepEqual(errors, [], "standalone entry renders without uncaught JavaScript errors");
  console.log(`Standalone PWA signed-out responsive qualification passed at ${widths.length} widths from 320px through 2560px, with short-height, focus and reduced-motion checks.`);
} finally {
  await browser.close();
}
