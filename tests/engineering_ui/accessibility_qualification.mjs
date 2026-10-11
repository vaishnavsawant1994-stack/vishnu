import assert from "node:assert/strict";
import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
await page.route("**/iphone/api/**", route => {
  const path = new URL(route.request().url()).pathname;
  if (path.endsWith("/status")) return route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Owner verification required" }) });
  if (path.endsWith("/access/options")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ password_available: true, passkey_available: false, google_available: false }) });
  return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
});
try {
  await page.goto("http://127.0.0.1:4173/standalone/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => !document.querySelector("#enrollPanel").classList.contains("hidden"));
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const blocking = results.violations.filter(item => ["critical", "serious"].includes(item.impact || ""));
  assert.deepEqual(blocking.map(item => ({ id: item.id, impact: item.impact, targets: item.nodes.map(node => node.target) })), [], `blocking accessibility violations: ${JSON.stringify(blocking)}`);

  await page.locator("#historyButton").focus();
  await page.keyboard.press("Tab");
  const focus = await page.evaluate(() => {
    const node = document.activeElement;
    if (!node || node === document.body) return null;
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return { id: node.id, width: rect.width, height: rect.height, outline: style.outlineStyle };
  });
  assert.ok(focus && focus.width > 0 && focus.height > 0, `keyboard focus must remain visible: ${JSON.stringify(focus)}`);
  console.log(`Accessibility qualification passed with ${results.passes.length} axe passes and no critical/serious violations.`);
} finally {
  await browser.close();
}
