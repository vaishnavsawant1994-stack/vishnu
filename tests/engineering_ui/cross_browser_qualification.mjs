import assert from "node:assert/strict";
import { chromium, firefox, webkit } from "playwright";
import { assertNoViewportOverflow } from "./device_matrix.mjs";

const engines = { chromium, webkit, firefox };
const widths = [320, 390, 768, 1440, 1920];
const artifactRoot = process.env.ENGINEERING_UI_SCREENSHOT_DIR || "artifacts/engineering-ui";

for (const [name, engine] of Object.entries(engines)) {
  const browser = await engine.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
  await page.route("**/iphone/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/status")) return route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Owner verification required" }) });
    if (path.endsWith("/access/options")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ password_available: true, passkey_available: false, google_available: false }) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
  });
  try {
    await page.goto("http://127.0.0.1:4173/standalone/", { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => !document.querySelector("#enrollPanel").classList.contains("hidden"));
    for (const width of widths) {
      const height = width < 700 ? 844 : 960;
      await page.setViewportSize({ width, height });
      const layout = await page.evaluate(() => ({
        document: document.documentElement.scrollWidth,
        viewport: innerWidth,
        panel: (() => { const r = document.querySelector("#enrollPanel").getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width }; })(),
      }));
      assertNoViewportOverflow(assert, layout, width, `${name} standalone`);
      assert.ok(layout.panel.width > 0 && layout.panel.left >= -1 && layout.panel.right <= width + 1, `${name} enrollment panel escapes ${width}px viewport: ${JSON.stringify(layout)}`);
      if ([390, 1440].includes(width)) {
        await page.screenshot({ path: `${artifactRoot}/${name}-${width}.png`, fullPage: true });
      }
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator("#historyButton").focus();
    await page.keyboard.press("Tab");
    assert.notEqual(await page.evaluate(() => document.activeElement?.id), "historyButton", `${name} keyboard focus must advance`);
    assert.deepEqual(pageErrors, [], `${name} has uncaught page errors: ${JSON.stringify(pageErrors)}`);
    assert.deepEqual(consoleErrors, [], `${name} has console errors: ${JSON.stringify(consoleErrors)}`);
    console.log(`${name} engineering UI qualification passed at ${widths.join(", ")}px.`);
  } finally {
    await context.close();
    await browser.close();
  }
}
