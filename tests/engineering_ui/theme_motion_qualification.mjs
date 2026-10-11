import assert from "node:assert/strict";
import { chromium } from "playwright";

const browser = await chromium.launch({ headless: true });
try {
  for (const colorScheme of ["dark", "light"]) {
    for (const reducedMotion of ["no-preference", "reduce"]) {
      const context = await browser.newContext({
        viewport: { width: 390, height: 844 },
        colorScheme,
        reducedMotion,
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
      const state = await page.evaluate(() => {
        const panel = document.querySelector("#enrollPanel");
        const rect = panel?.getBoundingClientRect();
        const interactive = [...document.querySelectorAll("#enrollPanel button,#enrollPanel input")]
          .filter(node => { const r=node.getBoundingClientRect(); return r.width>0&&r.height>0; });
        const transitions = interactive.map(node => getComputedStyle(node).transitionDuration);
        return {
          dark: matchMedia("(prefers-color-scheme: dark)").matches,
          reduced: matchMedia("(prefers-reduced-motion: reduce)").matches,
          scrollWidth: document.documentElement.scrollWidth,
          width: innerWidth,
          rect: rect ? { left: rect.left, right: rect.right, width: rect.width } : null,
          interactive: interactive.length,
          transitions,
        };
      });
      assert.equal(state.dark, colorScheme === "dark", `color scheme was not propagated for ${colorScheme}`);
      assert.equal(state.reduced, reducedMotion === "reduce", `reduced motion was not propagated for ${reducedMotion}`);
      assert.ok(state.rect && state.rect.width > 0 && state.rect.left >= -1 && state.rect.right <= state.width + 1, `theme/motion panel escaped viewport: ${JSON.stringify(state)}`);
      assert.ok(state.interactive > 0, `theme/motion fixture has no controls: ${JSON.stringify(state)}`);
      assert.ok(state.scrollWidth <= state.width + 1, `theme/motion fixture overflowed: ${JSON.stringify(state)}`);
      assert.deepEqual(errors, [], `theme/motion fixture had page errors: ${JSON.stringify(errors)}`);
      await context.close();
    }
  }
  console.log("light/dark and reduced-motion qualification passed");
} finally {
  await browser.close();
}
