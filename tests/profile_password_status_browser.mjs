import assert from "node:assert/strict";
import { chromium } from "playwright";

const browser = await chromium.launch({
  headless: true,
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}),
  ...(process.env.PLAYWRIGHT_CHROMIUM_ARGS ? { args: process.env.PLAYWRIGHT_CHROMIUM_ARGS.split(" ").filter(Boolean) } : {}),
});

try {
  const page = await browser.newPage();
  await page.goto(process.env.PWA_PREVIEW_URL || "http://127.0.0.1:4173/web/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => typeof renderSettings === "function" && typeof api === "function");
  await page.evaluate(() => {
    api = async path => {
      if (path === "/system/status") return { model: { providers: [] }, integrations: [], tools: [] };
      if (path === "/devices") return { devices: [] };
      if (path === "/profile/metadata") return { display_name: "Synthetic Test Owner", account_id_masked: "•••• 0000" };
      if (path === "/access/security") return { password_configured: true, passkeys: [], google_configured: false };
      throw new Error(`Unexpected API request: ${path}`);
    };
  });

  await page.evaluate(() => renderSettings("profile"));
  const passwordAction = page.locator("[data-profile-password]");
  await page.waitForFunction(() => document.querySelector("[data-profile-password]")?.textContent === "Manage password");
  assert.equal(await passwordAction.isDisabled(), false, "configured password should remain manageable");

  await page.evaluate(() => {
    api = async path => {
      if (path === "/system/status") return { model: { providers: [] }, integrations: [], tools: [] };
      if (path === "/devices") return { devices: [] };
      if (path === "/profile/metadata") return { display_name: "Synthetic Test Owner" };
      if (path === "/access/security") throw new Error("Security status unavailable");
      throw new Error(`Unexpected API request: ${path}`);
    };
  });
  await page.evaluate(() => renderSettings("profile"));
  await page.waitForFunction(() => document.querySelector("[data-profile-password]")?.textContent === "Status unavailable");
  assert.equal(await passwordAction.isDisabled(), true, "unknown status must not offer a misleading setup action");

  await page.evaluate(() => {
    api = async path => {
      if (path === "/system/status") return { model: { providers: [] }, integrations: [], tools: [] };
      if (path === "/devices") return { devices: [] };
      if (path === "/profile/metadata") return { display_name: "Synthetic Test Owner" };
      if (path === "/access/security") return { password_configured: false, passkeys: [], google_configured: false };
      throw new Error(`Unexpected API request: ${path}`);
    };
  });
  await page.evaluate(() => renderSettings("profile"));
  await page.waitForFunction(() => document.querySelector("[data-profile-password]")?.textContent === "Set up password");
  assert.equal(await passwordAction.isDisabled(), false, "confirmed unconfigured status should allow password setup");

  console.log("Profile password status browser regression passed: configured, unconfigured, and unavailable states are distinguished correctly.");
} finally {
  await browser.close();
}
