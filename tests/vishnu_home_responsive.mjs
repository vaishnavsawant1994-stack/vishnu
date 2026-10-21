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
  await page.waitForFunction(() => document.body.classList.contains("home-landing") && document.querySelector("#homeProjectList .v-project") && window.__vishnuP201);
  assert.match(await page.locator("#homeGreeting").innerText(), /^Good (Morning|Afternoon|Evening), Vaishnav$/, "greeting should use the saved preferred name and local time");
  assert.equal(await page.locator("#homeProjectList").textContent().then(text => text.includes("Responsive workspace")), true, "recent project row should render live project data");
  assert.equal(await page.locator("#appDrawer").isVisible(), false, "navigation drawer starts collapsed");
  assert.equal(await page.locator("#homeSphereStage #neuralCanvas").count(), 1, "Home should reuse the existing particle sphere canvas");
  assert.equal(await page.evaluate(() => currentConversationId), "global-existing", "Home should preserve the active general conversation binding");

  // The approved P2-01 layout changes the old 4-card grid to six cards and
  // turns the mobile Home into a normal scrollable screen. Keep the older
  // owner, project, navigation and conversation behavioral assertions below.
  for(const [width,height,columns] of [[320,568,2],[390,844,2],[393,852,2],[768,960,2],[1024,768,3],[1440,900,6]]){
    await page.setViewportSize({width,height});
    const layout=await page.evaluate(()=>{
      const box=node=>{const r=node.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,height:r.height}};
      return {pageWidth:document.documentElement.scrollWidth,
        columns:getComputedStyle(document.querySelector('.v-shortcuts')).gridTemplateColumns.split(' ').length,
        cards:[...document.querySelectorAll('.p2-tile')].map(box),
        sphere:box(document.getElementById('homeSphereStage')),
        greeting:box(document.querySelector('.p2-greeting')),
        composer:box(document.getElementById('composer'))};
    });
    assert.ok(layout.pageWidth<=width+1,'no horizontal overflow at '+width);
    assert.equal(layout.columns,columns,'approved responsive grid at '+width);
    assert.equal(layout.cards.length,6,'all approved Home actions at '+width);
    assert.ok(layout.cards.every(card=>card.left>=0&&card.right<=width+1&&card.height>=44),'unclipped Home actions at '+width);
    assert.ok(layout.composer.left>=0&&layout.composer.right<=width+1,'canonical composer visible at '+width);
    if(width<=900)assert.ok(layout.sphere.bottom<=layout.greeting.top+5,'mobile Core precedes greeting at '+width);
    if([320,390,1440].includes(width))await page.screenshot({path:'artifacts/vishnu-home-'+width+'.png',fullPage:true});
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.click("#historyButton");
  assert.equal(await page.locator("#appDrawer").isVisible(), true, "hamburger opens the existing navigation drawer");
  await page.click("#closeAppDrawer");
  assert.equal(await page.locator("#appDrawer").isVisible(), false, "navigation drawer closes again");

  await page.locator(".p2-mobile-chat").click();
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
  console.log("Vishnu P2-01 Home responsive and canonical conversation regression checks passed.");
} finally {
  await browser.close();
}
