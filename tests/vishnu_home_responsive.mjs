import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

await mkdir("artifacts", { recursive: true });
const browser = await chromium.launch({ headless: true });
const project = {
  id: "project-1", name: "Responsive workspace", goal: "Verify the Vishnu Home layout",
  description: "Browser fixture", status: "active", updated_at: new Date().toISOString(),
  task_count: 1, done_count: 0, tasks: [{ id: "task-1", title: "Check mobile layout", owner: "vishnu", status: "planned", priority: "medium" }],
  milestones: [], files: [], activity: [],
};
const conversations = [{ id: "global-existing", title: "Existing general chat", preview: "Saved thread", updated_at: new Date().toISOString() }];
let active = { conversation: { id: "global-existing", title: "Existing general chat" }, events: [] };
let created = 0;
const errors = [];

try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, serviceWorkers: "block" });
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/iphone/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/iphone/api", "");
    const method = request.method();
    let body = {};
    if (path === "/status") body = { ok: true, owner_display_name: "Vaishnav", model: { state: "ready" }, conversation: active, conversations, memory_count: 0 };
    else if (path === "/preferences") body = { continuous_voice: true, voice_rate: 1, quiet_hours: true };
    else if (path === "/projects") body = { projects: [project] };
    else if (path === "/projects/project-1") body = { project };
    else if (path.startsWith("/conversations") && method === "POST") {
      created += 1;
      active = { conversation: { id: `global-new-${created}`, title: "New conversation" }, events: [] };
      conversations.unshift(active.conversation);
      body = active;
    } else if (path.startsWith("/conversations/") && path.endsWith("/activate")) body = active;
    else if (path.startsWith("/conversations/")) body = active;
    else if (path === "/voice/turn" && method === "POST") {
      const input = JSON.parse(request.postData() || "{}");
      active.events.push({ event_id: `user-${created}`, kind: "user_message", payload: { text: input.transcript }, created_at: new Date().toISOString() });
      active.events.push({ event_id: `assistant-${created}`, kind: "assistant_message", payload: { text: "Vishnu reply from the system-wide conversation." }, created_at: new Date().toISOString() });
      body = { conversation_id: active.conversation.id, conversation_title: active.conversation.title, reply: "Vishnu reply from the system-wide conversation.", status: "completed" };
    } else if (path === "/everyday/active" || path === "/everyday/timeline") body = { items: [] };
    else if (path === "/access/options") body = { passkey_available: false, password_available: false, google_available: false };
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });

  await page.goto("http://127.0.0.1:4173/iphone/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.body.classList.contains("home-landing") && document.querySelector("#homeProjectList .v-project"));
  assert.match(await page.locator("#homeGreeting").innerText(), /^Good (morning|afternoon|evening), Vaishnav$/, "greeting should use the saved preferred name and local time");
  assert.equal(await page.locator("#homeProjectList").innerText().then(text => text.includes("Responsive workspace")), true, "recent project row should render live project data");
  assert.equal(await page.locator("#appDrawer").isVisible(), false, "navigation drawer starts collapsed");
  assert.equal(await page.locator("#homeSphereStage #neuralCanvas").count(), 1, "Home should reuse the existing particle sphere canvas");
  assert.equal(await page.evaluate(() => currentConversationId), "global-existing", "Home should preserve the active general conversation binding");

  for (const [width, height, columns] of [[320, 568, 2], [390, 844, 2], [768, 960, 4], [1440, 900, 4]]) {
    await page.setViewportSize({ width, height });
    const layout = await page.evaluate(() => {
      const rect = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { left:r.left, right:r.right, top:r.top, bottom:r.bottom, width:r.width, height:r.height }; };
      return {
        documentWidth: document.documentElement.scrollWidth,
        gridColumns: getComputedStyle(document.querySelector(".v-shortcuts")).gridTemplateColumns.split(" ").length,
        greeting: rect("#homeGreeting"), sphere: rect("#homeSphereStage"), intro: rect("#homeIntro"), topbar: rect(".topbar"),
        cards: [...document.querySelectorAll(".v-card")].map(node => rect(`#${node.id}`)),
        dock: rect("#vChatDock"), newChat: rect("#vNewChat"), viewAll: rect("#vViewAllProjects"),
        homePanel: rect("#voicePanel"), presence: rect(".presence"),
        sidebarButton: rect("#ownerButton"),
        projectsHeading: rect("#homeProjectsHeading"), projectList: rect("#homeProjectList"),
        composer: rect("#composer"), home: rect("#homeIntro"),
        scrollbar: getComputedStyle(document.querySelector("#homeIntro")).scrollbarWidth,
        composerBackground: getComputedStyle(document.querySelector("#composer")).backgroundColor,
        composerBackgroundImage: getComputedStyle(document.querySelector("#composer")).backgroundImage,
        composerShadow: getComputedStyle(document.querySelector("#composer")).boxShadow,
        dockBackground: getComputedStyle(document.querySelector("#vChatDock")).backgroundColor,
        homeScroll: { height: document.querySelector("#homeIntro").clientHeight, scrollHeight: document.querySelector("#homeIntro").scrollHeight, maxHeight: getComputedStyle(document.querySelector("#homeIntro")).maxHeight },
      };
    });
    if (width <= 600) console.log(`mobile layout ${width}x${height}: ${JSON.stringify(layout)}`);
      assert.ok(layout.documentWidth <= width, `horizontal overflow at ${width}px`);
      assert.equal(layout.gridColumns, columns, `shortcut grid should have ${columns} columns at ${width}px`);
      assert.ok(layout.sphere.bottom <= layout.greeting.top + 1, `particle sphere should sit above the greeting at ${width}px`);
    assert.equal(layout.cards.length, 4);
    assert.ok(layout.cards.every(card => card.left >= 0 && card.right <= width && card.height >= 44), `shortcut card clips at ${width}px`);
    assert.ok(layout.dock.left >= 0 && layout.dock.right <= width && layout.dock.bottom <= layout.composer.top + 1, `New chat dock overlaps or clips at ${width}px`);
    if (width <= 600) {
      assert.equal(await page.locator("#vNewChat").evaluate(node => Math.round(node.getBoundingClientRect().width)), 44, "mobile New chat remains a circle");
      assert.equal(await page.locator("#vNewChat").getAttribute("aria-label"), "New chat");
      assert.ok(Math.max(...layout.cards.map(card => card.height)) - Math.min(...layout.cards.map(card => card.height)) <= 1, "all four mobile shortcuts have matching heights");
      assert.ok(layout.sidebarButton.width >= 44 && layout.sidebarButton.right <= width, "right timeline sidebar button is visible and usable");
      assert.ok(layout.sphere.top >= layout.topbar.bottom && layout.sphere.top - layout.topbar.bottom <= 32, `mobile sphere should start just below the header at ${width}px`);
      assert.equal(layout.scrollbar, "none", "Home scrolling works without a visible scrollbar");
      assert.equal(layout.composerBackground, "rgba(0, 0, 0, 0)", "composer has no backing panel behind the input");
      assert.equal(layout.composerBackgroundImage, "none", "composer has no background image or footer band");
      assert.equal(layout.composerShadow, "none", "composer has no drop shadow that creates a background layer");
      assert.equal(layout.dockBackground, "rgba(0, 0, 0, 0)", "New chat dock has no backing panel");
      assert.ok(layout.home.bottom <= layout.dock.top + 1, `Scrollable Home content extends under the fixed dock at ${width}px`);
      assert.ok(layout.home.bottom <= layout.composer.top + 1, `Scrollable Home content extends under the composer at ${width}px`);
      assert.ok(layout.homePanel.bottom >= height - 1, `Home background panel ends early and exposes a different page background at ${width}px`);
      assert.ok(layout.presence.bottom <= layout.dock.top + 1, `Home content area extends underneath New chat at ${width}px`);
      const headingVisible = layout.projectsHeading.bottom > layout.home.top && layout.projectsHeading.top < layout.home.bottom;
      if (headingVisible) assert.ok(layout.newChat.left >= layout.viewAll.right || layout.newChat.right <= layout.viewAll.left || layout.newChat.bottom <= layout.viewAll.top || layout.newChat.top >= layout.viewAll.bottom, `New chat covers View all at ${width}px`);
    } else assert.equal(await page.locator("#vNewChat span").isVisible(), true, "desktop New chat shows its label");
    if ([320, 390, 1440].includes(width)) await page.screenshot({ path: `artifacts/vishnu-home-${width}.png`, fullPage: true });
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.click("#historyButton");
  assert.equal(await page.locator("#appDrawer").isVisible(), true, "hamburger opens the existing navigation drawer");
  await page.click("#closeAppDrawer");
  assert.equal(await page.locator("#appDrawer").isVisible(), false, "navigation drawer closes again");

  await page.click("#vNewChat");
  await page.waitForFunction(() => currentConversationId === "global-new-1");
  assert.equal(created, 1, "New chat persists a separate conversation");
  assert.equal(conversations.some(item => item.id === "global-existing"), true, "New chat preserves the prior conversation");
  assert.equal(await page.locator("#vContextChip").isVisible(), true, "system-wide context chip is available in chat");
  await page.fill("#message", "Hello from Home");
  await page.press("#message", "Enter");
  await page.getByText("Vishnu reply from the system-wide conversation.").waitFor({ state: "visible", timeout: 10000 });
  assert.equal(active.conversation.id, "global-new-1", "Home message stays on the new system-wide thread");
  assert.deepEqual(errors, [], "Home renders without uncaught JavaScript errors");
  console.log("Vishnu Home responsive and general conversation checks passed at 320, 390, 768, and 1440 CSS px.");
} finally {
  await browser.close();
}
