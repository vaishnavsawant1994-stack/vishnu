import assert from "node:assert/strict";
import { mkdirSync, readFileSync } from "node:fs";
import { chromium, firefox, webkit } from "playwright";

const source = readFileSync("server/owner_release_ui.py", "utf8");
const match = source.match(/JS = r'''([\s\S]*?)'''/);
assert.ok(match, "Owner Release UI JavaScript must remain extractable for browser qualification");
const ownerReleaseJs = match[1];
const engines = { chromium, webkit, firefox };
const widths = [320, 390, 768, 1440];
const screenshotRoot = process.env.OWNER_RELEASE_UI_SCREENSHOT_DIR || "";
if (screenshotRoot) mkdirSync(screenshotRoot, { recursive: true });

const summary = {
  available: true,
  policy: {
    mode: "approval_required",
    allow_production: true,
    require_preview: true,
    require_exact_revision_evidence: true,
    require_production_smoke: true,
    require_canary: true,
    canary_min_requests: 20,
    canary_max_error_rate_regression: 0.05,
    canary_max_latency_ratio: 1.35,
    allow_automatic_rollback: false,
    max_monitoring_observations: 1000,
  },
  providers: ["render", "vercel"],
  provider_capabilities: {
    render: { production_observation: true, production_telemetry: true, telemetry_evidence_sanitized: true },
    vercel: { production_observation: true, production_telemetry: true, telemetry_evidence_sanitized: true },
  },
  releases: [
    {
      id: "release-monitoring-1",
      candidate_revision: "b".repeat(40),
      provider: "vercel",
      target: "owner/repo",
      production_url: "https://production.example.test",
      status: "monitoring",
      risk_class: "low",
      approval_required: false,
      approved_by: "",
      evidence: [
        {
          kind: "production_monitor_observation",
          summary: "Production monitor proved the exact deployment healthy.",
          trusted: true,
          created_at: "2026-10-11T18:00:00Z",
          metadata: { provider_telemetry_available: true, provider_telemetry_observed: true },
        },
        {
          kind: "production_provider_telemetry",
          summary: "Provider telemetry sampled 100 requests; server error rate 0.0100.",
          trusted: true,
          created_at: "2026-10-11T18:01:00Z",
          metadata: {
            request_count: 100,
            server_error_count: 1,
            error_rate: 0.01,
            p95_latency_ms: 182.4,
            window_seconds: 300,
            message: "DO_NOT_RENDER_PRIVATE_LOG_MESSAGE",
            token: "DO_NOT_RENDER_SECRET_TOKEN",
          },
        },
        {
          kind: "production_provider_telemetry_error",
          summary: "Provider telemetry was unavailable: ProductionTelemetryError",
          trusted: true,
          created_at: "2026-10-11T18:02:00Z",
          metadata: {
            error_type: "ProductionTelemetryError",
            arbitrary_provider_payload: "DO_NOT_RENDER_ARBITRARY_METADATA",
          },
        },
      ],
    },
    {
      id: "release-incident-2",
      candidate_revision: "c".repeat(40),
      provider: "render",
      target: "owner/repo",
      production_url: "https://production-2.example.test",
      status: "rollback_recommended",
      risk_class: "high",
      approval_required: true,
      approved_by: "device:owner-device",
      evidence: [
        {
          kind: "production_monitor_error",
          summary: "Production monitor could not prove release health: RuntimeError",
          trusted: true,
          created_at: "2026-10-11T18:03:00Z",
          metadata: { error_type: "RuntimeError" },
        },
      ],
    },
  ],
};

for (const [engineName, engine] of Object.entries(engines)) {
  const browser = await engine.launch({ headless: true });
  const context = await browser.newContext({ serviceWorkers: "block", reducedMotion: "reduce" });
  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
  try {
    await page.setContent(`<!doctype html><html><head><meta charset="utf-8"></head><body><main id="moduleBody"><span>Read & understand</span><span>Edit / organize</span></main></body></html>`);
    await page.evaluate(fixture => {
      window.api = async (path, options = undefined) => {
        if (path === "/owner/release/summary" && !options) return structuredClone(fixture);
        throw new Error(`Unexpected Owner Release browser qualification API call: ${path}`);
      };
      window.showToast = () => {};
    }, summary);
    await page.addScriptTag({ content: ownerReleaseJs });
    await page.waitForSelector("#ocReleaseProduction");
    await page.waitForFunction(() => document.body.innerText.includes("release-monitoring-1"));

    const initialText = await page.locator("#ocReleaseProduction").innerText();
    for (const required of [
      "Release Control",
      "Monitoring observation limit",
      "Configured provider monitoring",
      "sanitized telemetry",
      "release-monitoring-1",
      "release-incident-2",
      "Production incident requires owner decision",
    ]) assert.ok(initialText.includes(required), `${engineName} Owner Release UI is missing ${required}`);
    for (const forbidden of [
      "DO_NOT_RENDER_PRIVATE_LOG_MESSAGE",
      "DO_NOT_RENDER_SECRET_TOKEN",
      "DO_NOT_RENDER_ARBITRARY_METADATA",
    ]) assert.ok(!initialText.includes(forbidden), `${engineName} leaked arbitrary telemetry metadata before expansion`);

    const observationLimit = await page.locator('[data-rel-key="max_monitoring_observations"]').inputValue();
    assert.equal(observationLimit, "1000", `${engineName} did not render the persisted monitoring observation limit`);

    await page.locator('[data-rel-details="release-monitoring-1"]').click();
    await page.waitForFunction(() => document.body.innerText.includes("Monitoring & evidence history"));
    const expandedText = await page.locator("#ocReleaseProduction").innerText();
    for (const required of [
      "Monitoring & evidence history",
      "Requests 100",
      "5xx 1",
      "Error rate 1.00%",
      "p95 182.4 ms",
      "Window 300s",
      "Telemetry unavailable · ProductionTelemetryError · no rollback authority",
      "Trusted",
    ]) assert.ok(expandedText.includes(required), `${engineName} evidence history is missing ${required}`);
    for (const forbidden of [
      "DO_NOT_RENDER_PRIVATE_LOG_MESSAGE",
      "DO_NOT_RENDER_SECRET_TOKEN",
      "DO_NOT_RENDER_ARBITRARY_METADATA",
    ]) assert.ok(!expandedText.includes(forbidden), `${engineName} leaked arbitrary telemetry metadata after expansion`);

    for (const width of widths) {
      await page.setViewportSize({ width, height: width < 700 ? 844 : 960 });
      const layout = await page.evaluate(() => ({ viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
      assert.ok(layout.scrollWidth <= layout.viewport + 1, `${engineName} Owner Release UI overflows ${width}px: ${JSON.stringify(layout)}`);
      if (screenshotRoot && [390, 1440].includes(width)) {
        await page.screenshot({ path: `${screenshotRoot}/${engineName}-${width}.png`, fullPage: true, animations: "disabled" });
      }
    }

    await page.locator('[data-rel-details="release-monitoring-1"]').focus();
    await page.keyboard.press("Enter");
    assert.ok(!(await page.locator("#ocReleaseProduction").innerText()).includes("Monitoring & evidence history"), `${engineName} keyboard activation did not collapse evidence`);
    assert.deepEqual(pageErrors, [], `${engineName} Owner Release UI has uncaught page errors: ${JSON.stringify(pageErrors)}`);
    assert.deepEqual(consoleErrors, [], `${engineName} Owner Release UI has console errors: ${JSON.stringify(consoleErrors)}`);
    console.log(`${engineName} Owner Release monitoring UI qualification passed at ${widths.join(", ")}px.`);
  } finally {
    await context.close();
    await browser.close();
  }
}
