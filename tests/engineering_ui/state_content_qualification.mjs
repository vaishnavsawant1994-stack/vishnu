import assert from "node:assert/strict";
import { chromium } from "playwright";

const browser = await chromium.launch({ headless: true });
const base = "http://127.0.0.1:4173/standalone/";
const statuses = [401, 403, 404, 500];
const stress = [
  "Ein außergewöhnlich langer deutscher Beschreibungstext für die responsive Benutzeroberfläche und ihre Sicherheitsfunktionen",
  "Vishnu 🚀🧠✨ — हिन्दी العربية 日本語 Deutsch français español português",
  "https://example.test/" + "very-long-path-segment-".repeat(30),
  "NOBREAK_" + "X".repeat(700),
];

try {
  for (const status of statuses) {
    const context = await browser.newContext({ viewport: { width: 320, height: 568 }, serviceWorkers: "block" });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("https://accounts.google.com/**", route => route.fulfill({ status: 200, contentType: "application/javascript", body: "" }));
    await page.route("**/iphone/api/**", route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/status")) {
        return route.fulfill({ status, contentType: "application/json", body: JSON.stringify({ detail: `Qualification fixture ${status}` }) });
      }
      if (path.endsWith("/access/options")) {
        return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ password_available: true, passkey_available: false, google_available: false, recovery_available: true }) });
      }
      return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });
    await page.goto(base, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(250);
    const state = await page.evaluate(() => ({
      viewport: innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      text: (document.body.innerText || "").trim(),
      interactive: [...document.querySelectorAll("button,input,select,textarea")].some(element => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
      }),
    }));
    assert.ok(state.text.length > 0, `${status} response left the application visually empty`);
    assert.ok(state.interactive, `${status} response left no reachable control`);
    assert.ok(state.scrollWidth <= state.viewport + 1, `${status} response causes horizontal overflow: ${JSON.stringify(state)}`);
    assert.deepEqual(errors, [], `${status} response caused page errors: ${JSON.stringify(errors)}`);
    await context.close();
  }

  const context = await browser.newContext({ viewport: { width: 320, height: 568 }, serviceWorkers: "block" });
  const page = await context.newPage();
  await page.route("https://accounts.google.com/**", route => route.fulfill({ status: 200, contentType: "application/javascript", body: "" }));
  await page.route("**/iphone/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/status")) return route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Owner verification required" }) });
    if (path.endsWith("/access/options")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ password_available: true, passkey_available: false, google_available: false, recovery_available: true }) });
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => !document.querySelector("#enrollPanel")?.classList.contains("hidden"));

  for (const [index, value] of stress.entries()) {
    await page.evaluate(({ value, index }) => {
      const panel = document.querySelector("#enrollPanel");
      const heading = panel?.querySelector("h1");
      const copy = panel?.querySelector("p");
      const input = panel?.querySelector("input");
      if (heading) heading.textContent = value;
      if (copy) copy.textContent = value + " " + value;
      if (input) input.value = value;
      document.documentElement.dir = index === 2 ? "rtl" : "ltr";
      document.documentElement.style.fontSize = index === 3 ? "125%" : "100%";
    }, { value, index });
    const layout = await page.evaluate(() => {
      const panel = document.querySelector("#enrollPanel").getBoundingClientRect();
      return { viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth, left: panel.left, right: panel.right, width: panel.width };
    });
    assert.ok(layout.scrollWidth <= layout.viewport + 1, `stress fixture ${index} caused horizontal overflow: ${JSON.stringify(layout)}`);
    assert.ok(layout.width > 0 && layout.left >= -1 && layout.right <= layout.viewport + 1, `stress fixture ${index} escaped viewport: ${JSON.stringify(layout)}`);
  }
  await context.close();
  console.log("engineering failure-state, localization, RTL, text-scale and extreme-content qualification passed");
} finally {
  await browser.close();
}
