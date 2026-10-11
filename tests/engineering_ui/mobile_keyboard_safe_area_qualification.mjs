import assert from "node:assert/strict";
import { chromium, webkit } from "playwright";

const engines = { chromium, webkit };

for (const [name, engine] of Object.entries(engines)) {
  const browser = await engine.launch({ headless: true });
  try {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
      deviceScaleFactor: 2,
      serviceWorkers: "block",
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("https://accounts.google.com/**", route => route.fulfill({ status: 200, contentType: "application/javascript", body: "" }));
    await page.route("**/iphone/api/**", route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/status")) return route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Owner verification required" }) });
      if (path.endsWith("/access/options")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ password_available: true, passkey_available: false, google_available: false, recovery_available: true }) });
      return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });
    await page.goto("http://127.0.0.1:4173/standalone/", { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => !document.querySelector("#enrollPanel")?.classList.contains("hidden"));
    const input = page.locator("#enrollPanel input").first();
    assert.ok(await input.count(), `${name} owner access input missing`);
    await input.focus();
    await input.fill("keyboard-safe-area-fixture");

    for (const viewport of [{ width: 390, height: 560 }, { width: 844, height: 390 }, { width: 320, height: 480 }]) {
      await page.setViewportSize(viewport);
      await input.scrollIntoViewIfNeeded();
      const layout = await page.evaluate(() => {
        const active = document.activeElement?.getBoundingClientRect();
        const panel = document.querySelector("#enrollPanel")?.getBoundingClientRect();
        const buttons = [...document.querySelectorAll("#enrollPanel button")].map(node => node.getBoundingClientRect()).filter(rect => rect.width > 0 && rect.height > 0);
        return {
          width: innerWidth,
          height: innerHeight,
          scrollWidth: document.documentElement.scrollWidth,
          active: active ? { top: active.top, bottom: active.bottom, left: active.left, right: active.right } : null,
          panel: panel ? { left: panel.left, right: panel.right, width: panel.width } : null,
          reachableButton: buttons.some(rect => rect.top < innerHeight && rect.bottom > 0 && rect.left < innerWidth && rect.right > 0),
        };
      });
      assert.ok(layout.active, `${name} lost focused input at ${viewport.width}x${viewport.height}`);
      assert.ok(layout.active.bottom <= layout.height + 1 && layout.active.top >= -1, `${name} focused input is obscured after keyboard-like shrink: ${JSON.stringify(layout)}`);
      assert.ok(layout.reachableButton, `${name} has no reachable owner action after keyboard-like shrink: ${JSON.stringify(layout)}`);
      assert.ok(layout.scrollWidth <= layout.width + 1, `${name} safe-area/keyboard shrink causes horizontal overflow: ${JSON.stringify(layout)}`);
      assert.ok(layout.panel && layout.panel.width > 0 && layout.panel.left >= -1 && layout.panel.right <= layout.width + 1, `${name} access panel escapes viewport: ${JSON.stringify(layout)}`);
    }
    assert.deepEqual(errors, [], `${name} keyboard/safe-area qualification has page errors: ${JSON.stringify(errors)}`);
    await context.close();
    console.log(`${name} mobile keyboard and safe-area qualification passed`);
  } finally {
    await browser.close();
  }
}
