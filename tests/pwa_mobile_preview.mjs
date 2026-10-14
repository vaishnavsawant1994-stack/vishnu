Warning: truncated output (original token count: 37724)
Total output lines: 1704

import assert from "node:assert/strict";
import { chromium } from "playwright";

const browser = await chromium.launch({
  headless: true,
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}),
  ...(process.env.PLAYWRIGHT_CHROMIUM_ARGS ? { args: process.env.PLAYWRIGHT_CHROMIUM_ARGS.split(" ").filter(Boolean) } : {}),
});

const appTimeZone = "Asia/Kolkata";
const appDateParts = new Intl.DateTimeFormat("en-CA", {
  timeZone: appTimeZone, year: "numeric", month: "2-digit", day: "2-digit",
}).formatToParts(new Date());
const appToday = Object.fromEntries(appDateParts.map(part => [part.type, part.value]));
const atAppDay = (dayOffset, hour, minute = 0) => {
  const date = new Date(Date.UTC(Number(appToday.year), Number(appToday.month) - 1, Number(appToday.day) + dayOffset));
  // India Standard Time is UTC+05:30; test fixtures should follow the same
  // calendar day the app uses, regardless of the GitHub runner's UTC locale.
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), hour - 5, minute - 30)).toISOString();
};
const atToday = (hour, minute = 0) => atAppDay(0, hour, minute);
const atDayOffset = (days, hour = 10) => atAppDay(days, hour);
const assertSharedComposerBottomInset=(bottom,viewport,label)=>{
  const gap=viewport-bottom;
  assert.ok(gap>=23&&gap<=25,`${label} must keep the shared 24px bottom inset: ${gap}px`);
};

const conversations = [
  { id: "c1", title: "Project Planning", preview: "Continue planning the project", updated_at: atToday(10,33) },
  { id: "c2", title: "Mushroom Farm Plan", preview: "Shed layout and capacity", updated_at: atDayOffset(-1,14) },
  { id: "c3", title: "Onion Cultivation Guide", preview: "Irrigation and fertilizer plan", updated_at: atDayOffset(-4,9) },
];
const everydayItems = [
  { id:"task-1",kind:"task",context:"personal-ai:today:task",title:"Finish daily review",due_at:atToday(9),created_at:atToday(7),updated_at:atToday(8),status:"scheduled" },
  { id:"meeting-1",kind:"commitment",context:"personal-ai:today:meeting",title:"Team planning meeting",due_at:atToday(14),created_at:atToday(8),updated_at:atToday(8),status:"scheduled" },
  { id:"work-1",kind:"task",context:"personal-ai:today:work",title:"Prepare client proposal",due_at:atDayOffset(-1,16),created_at:atDayOffset(-2,9),updated_at:atDayOffset(-1,9),status:"scheduled" },
  { id:"done-1",kind:"task",context:"personal-ai:today:task",title:"Complete weekly report",due_at:atToday(11),created_at:atToday(8),updated_at:atToday(12,20),completed_at:atToday(12,20),status:"completed" },
  { id:"reminder-1",kind:"reminder",context:"personal-ai:today:reminder",title:"Send follow-up",due_at:atDayOffset(1,10),created_at:atToday(7),updated_at:atToday(7),status:"scheduled" },
];
const auditedEvents=[{id:"audit-1",category:"workflow",kind:"workflow",label:"Workflow",action:"workflow_run_finished",status:"completed",created_at:atToday(8,15),details:{workflow_title:"Morning operations"}}];
const workflowRuns=[{id:'run-1',workflow_title:'Morning operations',status:'completed',created_at:atToday(7),updated_at:atToday(9,30),current_step:3}];
let allowActivity=true;
let revokeSession=false;
let failNextTaskComplete=false;
let sidebarPreferences={continuous_voice:true,voice_rate:1,quiet_hours:true,pinned_sidebar_items:[]};
const deletedConversationIds=[];
const createdMemories=[];
const exportedConversationIds=[];
const turnConversationIds=[];
let conversationCreateCount=0;
let ambientCandidate={id:"candidate-qa",source:"chat-conversation",status:"pending",created_at:atToday(8),candidate:{subject:"Suggested preference",content:"The owner prefers concise responses.",type:"preference",confidence:0.82,source:"chat-conversation"}};
let ambientCandidateEdits=[];
let ambientSavedMemories=[{id:"memory-qa",subject:"Project context",type:"note",content:"Browser qualification fixture with source evidence",source:"owner",created_at:atToday(8),metadata_json:"{}"}];
let ambientSettings={enabled:true,memory_enabled:true,capture_active:true,sources:{chats:true,projects:false,files:false},capabilities:{chats:true,projects:true,files:true},unavailable_sources:{},excluded_conversation_ids:[],pause_until:null,retention:"forever"};
let ambientScanRequests=0;
let turnClock=Date.now();
let uiPreferenceState={continuous_voice:true,voice_rate:1,quiet_hours:true,privacy_memory_enabled:true,privacy_review_before_saving:true,privacy_allow_project_context_general:false,privacy_save_conversations:true,privacy_retention:'until_deleted',privacy_share_anonymous_usage_data:false,appearance_theme:'dark',appearance_accent:'blue',appearance_density:'comfortable',appearance_motion:'standard',appearance_text_size:'default',chat_enter_sends:true,chat_keep_composer_visible:true,chat_response_detail:'detailed',chat_response_style:'clear_step_by_step',chat_show_sources:true,chat_show_timestamps:true,chat_show_actions:true,chat_message_spacing:'comfortable',chat_new_context:'general',chat_project_context_enabled:false};
let profileState={first_name:'Vishnu',last_name:'Owner',display_name:'Vishnu',email:'owner@example.test',email_verified:true,account_created_at:'2025-01-15T00:00:00Z',account_id_masked:'•••• 4821',avatar_available:false};
let systemStatus={model:{state:'not_configured',primary_provider:'self_hosted',providers:[]},integrations:[],emergency_stop:false};
let notificationState={events:{task_reminders:{enabled:false,channels:[]},work_completed:{enabled:true,channels:['in_app']},needs_review:{enabled:true,channels:['in_app']},blocked_work:{enabled:true,channels:['in_app']},workflow_updates:{enabled:false,channels:[]},product_updates:{enabled:false,channels:[]}},quiet_hours:{enabled:true,start:'22:00',end:'08:00',timezone:'Asia/Kolkata'},allow_urgent_reviews:true,daily_summary:{enabled:true,time:'08:00'},weekly_summary:{enabled:false,weekday:0,time:'08:00'}};
const notificationAvailability={in_app:true,push:false,email:false,scheduler:true,supported_events:['work_completed','needs_review','blocked_work','workflow_updates']};

const activeConversation = {
  thread: { id: "c1", title: "Project Planning", created_at: atDayOffset(-1,23), updated_at: conversations[0].updated_at },
  events: [
    { event_id:"c1-user-1", kind: "user_message", created_at: atDayOffset(-1,23), payload: { text: "Plan mushroom farm shed layout with complete details" } },
    { event_id:"c1-assistant-1", kind: "assistant_message", created_at: atToday(0,5), payload: { text: "I can help with the shed layout, rack design, climate control, and cost planning.\n\n1. Start with rack spacing\n2. Confirm ventilation\n3. Keep `humidity` monitored" } },
  ],
};
let newConversation = {
  thread: { id:"new", title:"New conversation", created_at:new Date(turnClock).toISOString(), updated_at:new Date(turnClock).toISOString() },
  events: [],
};

try {
  const page = await browser.newPage({
    timezoneId: "Asia/Kolkata",
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    serviceWorkers: "block",
    hasTouch: true,
  });

  const pageErrors = [];
  const appRequests = [];
  page.on("request", request => { if (request.url().includes("/iphone/api/")) appRequests.push(request.url()); });
  const uploadedDocuments = [];
  page.on("pageerror", error => pageErrors.push(error.message));

  await page.route("**/iphone/api/**", route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/iphone/api", "");
    const method = request.method();

    let body = {};
    if (path === "/status") {
      if(revokeSession)return route.fulfill({status:401,contentType:"application/json",body:JSON.stringify({detail:"Owner verification required"})});
      body = { model: { state: "ready" }, conversations, conversation: activeConversation, memory_count: 3, active_qualification: true };
    } else if (path === "/system/status" && method === "GET") {
      body=systemStatus;
    } else if (path === "/owner/ai-providers/test" && method === "POST") {
      const input=JSON.parse(request.postData()||"{}");assert.equal(input.provider_id,"openai");assert.equal(input.api_key,"sk-browser-test-credential");
      body={provider:"openai",models:["model-a","model-b"],credential_stored:false};
    } else if (path === "/owner/ai-providers" && method === "POST") {
      const input=JSON.parse(request.postData()||"{}");assert.equal(input.api_key,"sk-browser-test-credential");assert.equal(input.model,"model-b");
      systemStatus.model={state:"configured",primary_provider:"self_hosted",providers:[{id:"openai",model:"model-b",configured:true,owner_managed:true,private:false,health:{state:"not_checked"}}]};
      body={ok:true,provider:"openai",model:"model-b",credential_stored:true,model_status:systemStatus.model};
    } else if (path === "/owner/ai-providers/openai/models" && method === "GET") {
      body={provider:"openai",models:["model-a","model-b"]};
    } else if (path === "/owner/ai-providers/openai/model" && method === "PATCH") {
      const model=JSON.parse(request.postData()||"{}").model;systemStatus.model.providers[0].model=model;body={ok:true,provider:"openai",model,model_status:systemStatus.model};
    } else if (path === "/everyday/active" && method === "GET") {
      body = { items: everydayItems.filter(item => !['completed','cancelled','dismissed'].includes(item.status)) };
    } else if (path === "/everyday/timeline" && method === "GET") {
      body = { items: everydayItems };
    } else if (path.startsWith("/everyday/items/") && method === "GET") {
      const id=decodeURIComponent(path.split("/").at(-1));
      const item=everydayItems.find(value=>value.id===id);
      if(!item)return route.fulfill({status:404,contentType:"application/json",body:JSON.stringify({detail:"Everyday item not found"})});
      body={item};
    } else if (path === "/memory" && method === "POST") {
      const input=JSON.parse(request.postData()||"{}");createdMemories.push(input);
      return route.fulfill({status:201,contentType:"application/json",body:JSON.stringify({memory:{id:"created-memory-"+createdMemories.length,...input}})});
    } else if (path === "/memory/ambient" && method === "GET") {
      body={settings:ambientSettings,candidates:ambientCandidate?[ambientCandidate]:[],memories:ambientSavedMemories,activity:[]};
    } else if (path === "/memory/ambient/scan" && method === "POST") {
      ambientScanRequests++;body={candidates_created:0,projects_scanned:1,files_scanned:1,requires_owner_review:true};
    } else if (path.startsWith("/memory/candidates/") && method === "PATCH") {
      const edits=JSON.parse(request.postData()||"{}");ambientCandidate={...ambientCandidate,candidate:{...ambientCandidate.candidate,...edits}};ambientCandidateEdits.push(edits);body=ambientCandidate;
    } else if (path.startsWith("/memory/candidates/") && path.endsWith("/approve") && method === "POST") {
      ambientSavedMemories.push({id:"memory-approved",...ambientCandidate.candidate,source:"owner-confirmed:chat-conversation",created_at:atToday(9),metadata_json:"{}"});ambientCandidate=null;body={ok:true,memory_id:"memory-approved"};
    } else if (path.startsWith("/memory/candidates/") && method === "DELETE") {
      ambientCandidate=null;body={ok:true};
    } else if (path === "/memory/ambient/settings" && method === "PATCH") {
      const changes=JSON.parse(request.postData()||"{}");ambientSettings={...ambientSettings,...changes,sources:{...ambientSettings.sources,...(changes.sources||{})}};body=ambientSettings;
    } else if (path === "/memory/graph" && method === "GET") {
      body={nodes:[{id:"memory-qa",subject:"Project context",type:"note"},{id:"memory-related",subject:"Responsive review details",type:"note"}],edges:[{source_id:"memory-qa",target_id:"memory-related"}]};
    } else if (path === "/memory/tree" && method === "GET") {
      body={roots:[{id:"memory-qa",subject:"Project context",content:"Browser qualification fixture with source evidence",children:[{id:"memory-child",subject:"Responsive review details that need to wrap safely on a narrow viewport",content:"Long tree details stay readable without widening the whole screen.",children:[]}]}]};
    } else if (path === "/memory" && method === "GET") {
      const query=(url.searchParams.get("q")||"").toLowerCase();
      const memories=[{id:"memory-qa",subject:"Project context",type:"note",content:"Browser qualification fixture with source evidence",source:"owner",tags_json:'["QA"]',created_at:atToday(8),confidence:1}];
      body={memories:memories.filter(item=>!query||`${item.subject} ${item.content}`.toLowerCase().includes(query))};
    } else if (path === "/knowledge" && method === "GET") {
      body={documents:[{id:"knowledge-qa",title:"Project notes",filename:"notes.md",media_type:"text/markdown",source:"owner-upload:iphone",access_class:"private",size_bytes:1024,indexed_chunk_count:2,updated_at:atToday(8)}]};
    } else if (path === "/operations" && method === "GET") {
      body={operations:[{id:"op-1",status:"executing",plan:{title:"Synchronize project notes"},created_at:atToday(8)}]};
    } else if (path === "/activities" && method === "GET") {
      if(!allowActivity)return route.fulfill({status:403,contentType:"application/json",body:JSON.stringify({detail:"Not authorized"})});
      body={activities:auditedEvents};
    } else if (path === "/workflows" && method === "GET") {
      body={runs:workflowRuns,workflows:[]};
    } else if (path === "/apps-tools/tools" && method === "GET") {
      body={tools:[{tool_id:"search_memory",name:"Search memory",description:"Search approved owner memories",availability:"AVAILABLE",approval_policy:"READ ONLY"}]};
    } else if (path === "/connectors" && method === "GET") {
      body={connectors:[{id:"drive",name:"Google Drive",state:"healthy",read_only:true,capabilities:["Search and reference Drive files"],granted_scopes:["Drive files read-only"]},{id:"gmail",name:"Gmail",state:"disconnected",capabilities:["Email"]}]};
    } else if (path === "/everyday/items" && method === "POST") {
      const input = JSON.parse(request.postData() || "{}");
      const item = { id: "created-" + everydayItems.length, title: input.title, kind: input.category === "meeting" ? "commitment" : input.category === "reminder" ? "reminder" : "task",
        context: "personal-ai:today:" + input.category, due_at: input.due_at, status: "scheduled" };
      everydayItems.push(item);
      return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ item }) });
    } else if (path.startsWith("/everyday/") && path.endsWith("/complete") && method === "POST") {
      if(failNextTaskComplete){failNextTaskComplete=false;return route.fulfill({status:422,contentType:"application/json",body:JSON.stringify({detail:[{loc:["body","task_id"],msg:"Task could not be completed"}]})})}
      const id = decodeURIComponent(path.split("/")[2]);
      const item = everydayItems.find(item => item.id === id);
      if(item){item.status="completed";item.completed_at=new Date().toISOString();item.updated_at=item.completed_at}
      body = item || {};
    } else if (path === "/profile/metadata" && method === "GET") {
      body=profileState;
    } else if (path === "/profile" && method === "PUT") {
      const input=JSON.parse(request.postData()||"{}");profileState={...profileState,...input};body={saved:true,...input};
    } else if (path === "/profile/account-id/copy" && method === "POST") {
      body={account_id:"owner-real-id-4821"};
    } else if (path === "/notifications/preferences" && method === "GET") {
      body={preferences:notificationState,availability:notificationAvailability};
    } else if (path === "/notifications/preferences" && method === "PUT") {
      notificationState=JSON.parse(request.postData()||"{}");body={preferences:notificationState,availability:notificationAvailability};
    } else if (path === "/notifications/inbox" && method === "GET") {
      body={notifications:[],unread_count:0};
    } else if (path === "/preferences" && method === "PUT") {
      uiPreferenceState=JSON.parse(request.postData()||"{}");
      sidebarPreferences={...sidebarPreferences,...uiPreferenceState};
      body={...sidebarPreferences,...uiPreferenceState};
    } else if (path === "/preferences") {
      body = uiPreferenceState;
    } else if (path === "/privacy/export" && method === "GET") {
      body={format:"vishnu-account-data-v1",memories:[],knowledge:[],conversations:[],preferences:uiPreferenceState};
    } else if (path === "/conversations/" && method === "DELETE") {
      if(url.searchParams.get("confirm")!=="true")return route.fulfill({status:422,contentType:"application/json",body:JSON.stringify({detail:"Confirmation required"})});
      body={ok:true,deleted_count:conversations.length};
    } else if (path.startsWith("/conversations/c1/activate")) {
      body = activeConversation;
    } else if (path === "/conversations/c1" && method === "PATCH") {
      const title = JSON.parse(request.postData() || "{}").title;
      activeConversation.thread.title = title;
      conversations[0].title = title;
      body = { conversation: { ...activeConversation.thread } };
    } else if (path === "/conversations/c1/export" && method === "GET") {
      exportedConversationIds.push("c1");
      body = { version: 1, conversation: activeConversation.thread, events: activeConversation.events };
    } else if (path === "/conversations/new" && method === "DELETE") {
      if(url.searchParams.get("confirm") !== "true")return route.fulfill({ status: 422, contentType:"application/json",body:JSON.stringify({detail:"Confirmation required"})});
      deletedConversationIds.push("new");
      body = { deleted:true, conversation_id:"new" };
    } else if (path === "/conversations/new" && method === "GET") {
      body = newConversation;
    } else if (path === "/conversations/new/activate" && method === "POST") {
      body = newConversation;
    } else if (path.startsWith("/conversations/c1")) {
      body = activeConversation;
    } else if (path.startsWith("/conversations") && method === "GET") {
      const q = (url.searchParams.get("q") || "").toLowerCase();
      body = { conversations: conversations.filter(item => item.title.toLowerCase().includes(q)) };
    } else if (path === "/conversations" && method === "POST") {
      conversationCreateCount++;
      const createdAt=new Date(++turnClock).toISOString();
      newConversation={thread:{id:"new",title:"New conversation",created_at:createdAt,updated_at:createdAt},events:[]};
      body = { conversation: { ...newConversation.thread }, events: [] };
    } else if (path === "/voice/turn" && method === "POST") {
      assert.match(request.headers()["content-type"] || "", /^application\/json(?:;|$)/i, "voice turns must preserve the JSON content type when adding transport headers");
      const input = JSON.parse(request.postData() || "{}");
      assert.match(input.request_id || "", /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i, "voice turns must carry a canonical logical request ID");
      const text = input.transcript;
      turnConversationIds.push(input.conversation_id);
      const userAt=new Date(turnClock+=60000).toISOString(),assistantAt=new Date(turnClock+=60000).toISOString();
      const reply="Received: "+text;
      newConversation.events.push(
        {event_id:"new-"+newConversation.events.length+"-u",kind:"user_message",created_at:userAt,payload:{text}},
        {event_id:"new-"+newConversation.events.length+"-a",kind:"assistant_message",created_at:assistantAt,payload:{text:reply}}
      );
      newConversation.thread.title=newConversation.events.length===2?text.slice(0,72):newConversation.thread.title;
      newConversation.thread.updated_at=assistantAt;
      body = { status: "ok", conversation_id: "new", conversation_title: newConversation.thread.title, reply };
    } else if (path === "/knowledge" && method === "POST") {
      uploadedDocuments.push(JSON.parse(request.postData() || "{}"));
      body = { id: "browser-test-document", filename: uploadedDocuments.at(-1).filename };
    } else if (path === "/logout") {
      body = { ok: true };
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });

  await page.route("https://accounts.google.com/**", route => route.abort());
  await page.goto("http://127.0.0.1:4173/iphone/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => !document.querySelector("#voicePanel").classList.contains("hidden"));
  await page.waitForFunction(() => document.body.classList.contains("home-landing"));
  await page.waitForFunction(() => {
    const canvas = document.querySelector("#neuralCanvas");
    return canvas.width > 0 && canvas.height > 0;
  });
  await page.waitForFunction(() => document.querySelectorAll("#todayTimeline .today-item").length === 2, { timeout: 10000 }).catch(async error => { const state = await page.evaluate(() => ({ date: document.querySelector("#todayDate")?.textContent, timeline: document.querySelector("#todayTimeline")?.innerHTML, startupError: document.querySelector("#voiceAlert")?.dataset.startupError, alert: document.querySelector("#voiceAlert")?.textContent, refreshing: typeof refreshToday })); throw new Error(error.message + "\\nToday state: " + JSON.stringify(state) + "\\nAPI requests: " + appRequests.join(", ") + "\\nPage errors: " + pageErrors.join("\\n")); });
  await page.waitForTimeout(500);
  const semanticTokens=await page.evaluate(()=>{
    const css=getComputedStyle(document.documentElement);
    return {body:css.getPropertyValue('--pa-type-body').trim(),page:css.getPropertyValue('--pa-type-page').trim(),
      spacing:css.getPropertyValue('--pa-space-4').trim(),touch:css.getPropertyValue('--pa-touch-target').trim(),
      cardRadius:css.getPropertyValue('--ui-card-radius').trim()};
  });
  assert.equal(semanticTokens.body,'1rem','PWA body role must use the semantic type scale');
  assert.equal(semanticTokens.spacing,'1rem','PWA spacing must expose the shared 4-unit token');
  assert.equal(semanticTokens.touch,'2.75rem','PWA touch target must be 44px');
  assert.ok(semanticTokens.page&&semanticTokens.cardRadius,'PWA page heading and Home card surface tokens must resolve');

  // The explicit demo mode shows realistic sample records without calling mutation APIs.
  await page.evaluate(async()=>{todayScreenDemo=true;await openTodayScreen()});
  await page.waitForFunction(()=>document.querySelectorAll("#todayTasksList .today-row").length===4);
  await page.locator(".today-screen:not(.hidden)").evaluate(async element=>{
    await Promise.all(element.getAnimations({subtree:true}).map(animation=>animation.finished.catch(()=>{})));
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  });
  assert.equal(await page.locator("#todayMeetingsList .today-row").count(),2,"Today demo must show two sample meetings");
  assert.equal(await page.locator("#todayPlansList .today-row").count(),1,"Today demo must show one sample plan");
  assert.equal(await page.locator("#todayDemoNotice").isVisible(),true,"sample data must be clearly labeled as preview-only");
  assert.equal(await page.locator("#todayScreenNewChat").isVisible(),true,"Today must keep New chat available in its bottom action row");
  const todayFooterLayout=await page.evaluate(()=>{const chat=document.querySelector("#todayScreenNewChat").getBoundingClientRect(),add=document.querySelector("#todayScreenAdd").getBoundingClientRect();return{chatBottom:chat.bottom,addBottom:add.bottom,viewport:innerHeight,left:chat.left,right:add.right,width:innerWidth}});
  assert.ok(Math.abs(todayFooterLayout.chatBottom-todayFooterLayout.addBottom)<=1,"Today footer buttons must share one bottom baseline");
  assert.ok(todayFooterLayout.left>=-1&&todayFooterLayout.right<=todayFooterLayout.width+1,"Today footer buttons must stay within the mobile viewport");
  assertSharedComposerBottomInset(todayFooterLayout.chatBottom,todayFooterLayout.viewport,"Today footer actions");
  const todayDemoConversationCount=conversationCreateCount;
  await page.click("#todayScreenNewChat");
  assert.equal(conversationCreateCount,todayDemoConversationCount,"Today demo New chat must not create a real conversation");
  await page.evaluate(()=>document.querySelector("#toast")?.classList.add("hidden"));
  assert.equal(await page.locator("#todayTasksList .today-chip.priority-high").textContent(),"High");
  assert.equal(await page.locator("#todayTasksList .today-chip.priority-medium").textContent(),"Medium");
  assert.equal(await page.locator("#todayTasksList .today-chip.priority-low").textContent(),"Low");
  assert.equal(await page.locator("#todayTasksList .today-task-check:not([disabled])").count(),0,"demo tasks must not persist sample completions");
  assert.equal(await page.locator("#todayPlanCount").textContent(),"1");
  const demoItemsBeforeAdd=everydayItems.length;
  await page.click("#todayScreenAdd");
  assert.equal(await page.locator("#todayDialog").isVisible(),true,"Today Add must open the movable creation dialog, including in preview mode");
  assert.equal(everydayItems.length,demoItemsBeforeAdd,"opening the preview add dialog must not create real records");
  assert.equal(await page.locator("#todayTasksList .today-task-check:disabled").count(),4,"preview sample task controls must remain disabled");
  await page.click("#todayCancel");
  assert.equal(await page.locator("#todayDialog").isVisible(),false,"cancel must close an untouched creation dialog without an unnecessary discard prompt");
  await page.screenshot({path:"artifacts/personal-ai-today-demo-390x844.png",fullPage:true});
  await page.evaluate(()=>{closeTodayScreen();todayScreenDemo=false});

  // All three approved surfaces share one explicitly enabled, non-persistent preview dataset.
  await page.evaluate(async()=>{personalAiDemoMode=true;await openConversationsDrawer()});
  await page.waitForFunction(()=>document.querySelectorAll(".conversations-row").length===11);
  assert.equal(await page.locator("#conversationsDemoNote").isVisible(),true,"Conversations sample data must be labeled preview-only");
  assert.equal(await page.locator(".conversations-group-title").allTextContents().then(x=>[...new Set(x)]).then(x=>x.join("|")),"Today|Yesterday|Previous 7 days");
  await page.fill("#conversationManagerSearch","retrospective");
  await page.waitForFunction(()=>document.querySelectorAll(".conversations-row").length===1);
  assert.match(await page.locator("#conversationManagerList").innerText(),/Team retrospective/,"conversation search must filter preview data");
  await page.fill("#conversationManagerSearch","");
  await page.waitForFunction(()=>document.querySelectorAll(".conversations-row").length===11);
  await page.screenshot({path:"artifacts/personal-ai-conversations-demo-390x844.png",fullPage:true});
  const demoCreateCount=conversationCreateCount;
  await page.click("#newConversation");
  assert.equal(conversationCreateCount,demoCreateCount,"Conversations demo New chat must not create a real conversation");
  await page.click("#closeDrawer");
  await page.evaluate(()=>openTimelineDrawer());
  await page.waitForFunction(()=>document.querySelectorAll("#conversationList .timeline-entry").length>=15);
  assert.equal(await page.locator("#timelineDemoNote").isVisible(),true,"Timeline sample data must be labeled preview-only");
  const mobileRailAlignment=await page.evaluate(()=>[...document.querySelectorAll("#conversationList .timeline-entry")].map(entry=>{const r=entry.getBoundingClientRect(),d=entry.querySelector(".timeline-dot").getBoundingClientRect(),p=getComputedStyle(entry,"::before");return Math.abs(r.left+parseFloat(p.left)+parseFloat(p.width)/2-(d.left+d.width/2))}));
  assert.ok(mobileRailAlignment.length>0&&mobileRailAlignment.every(delta=>delta<=1),"Timeline rail must pass through every node center on iPhone: "+mobileRailAlignment.join(","));
  const mobileTimelineCards=await page.locator("#conversationList .timeline-content").evaluateAll(cards=>cards.map(card=>card.getBoundingClientRect().width));
  assert.ok(mobileTimelineCards.length>0&&mobileTimelineCards.every(width=>width>=200),"Timeline cards must stay in the content column on iPhone: "+mobileTimelineCards.join(","));
  const previewTimeline=await page.locator("#conversationList").innerText();
  assert.match(previewTimeline,/Project update discussion/,"Timeline preview must include sample conversation history");
  assert.match(previewTimeline,/Weekly team sync/,"Timeline preview must include sample meetings");
  assert.match(previewTimeline,/Review design feedback/,"Timeline preview must include sample task history");
  await page.screenshot({path:"artifacts/personal-ai-timeline-demo-390x844.png",fullPage:true});
  const demoEverydayBeforePlan=everydayItems.length;
  const demoConversationBeforeOpen=await page.evaluate(()=>currentConversationId);
  await page.click("#timelineAddPlan");
  assert.equal(await page.locator("#todayDialog").isVisible(),true,"Timeline Add to plan must open the shared creation dialog");
  await page.click("#todayCancel");
  assert.equal(everydayItems.length,demoEverydayBeforePlan,"Timeline demo Add to plan must not create real data");
  const demoConversationTitle=page.locator('#conversationList .timeline-entry[data-category="conversation"] .timeline-title').first();
  await demoConversationTitle.evaluate(button=>button.click());
  assert.equal(await page.evaluate(()=>currentConversationId),demoConversationBeforeOpen,"Timeline demo conversation rows must not navigate to a real record");
  await page.evaluate(()=>closeDrawer(false));
  await page.evaluate(async()=>{personalAiDemoMode=false;await refreshConversationsDrawer('')});
  await page.waitForFunction(()=>document.querySelectorAll(".conversations-row").length===3);

  const canvasInk = await page.evaluate(() => {
    const canvas = document.querySelector("#neuralCanvas");
    const pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    let ink = 0;
    for (let i = 0; i < pixels.length; i += 4) {
      if (pixels[i + 3] > 12 && (pixels[i] > 80 || pixels[i + 1] > 100 || pixels[i + 2] > 150)) ink++;
    }
    return ink;
  });
  assert.ok(canvasInk > 90, "original mini neural sphere renderer did not paint");

  const homeState = await page.evaluate(() => {
    const rect = selector => {
      const node=document.querySelector(selector);
      if(!node)throw new Error(`Missing Home layout node: ${selector}`);
      const r=node.getBoundingClientRect();
      return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};
    };
    return {
      quickActions:[...document.querySelectorAll(".v-card")].map(node=>node.textContent.replace(/\s+/g," ").trim()),
      actionTitles:[...document.querySelectorAll(".v-card strong")].map(node=>node.textContent),
      cardRects:[...document.querySelectorAll(".v-card")].map(node=>{const r=node.getBoundingClientRect();return {width:r.width,height:r.height}}),
      menuButton:rect("#historyButton"),timelineButton:rect("#ownerButton"),header:rect(".topbar"),
      composer:rect("#composer"),quick:rect(".v-shortcuts"),recent:rect("#homeRecentSection"),
      recentList:rect("#homeRecentList"),today:rect(".today-panel"),calendar:rect(".calendar-status-row"),
      timeline:[...document.querySelectorAll("#todayTimeline .today-item strong")].map(node=>node.textContent),
      todayTitle:document.querySelector("#todayHeading").textContent,
      recentTitles:[...document.querySelectorAll(".home-recent-copy strong")].map(node=>node.textContent),
      recentDateTimes:[...document.querySelectorAll(".home-recent-time")].map(node=>node.dateTime),
      recentRowHeights:[...document.querySelectorAll(".home-recent-row")].map(node=>node.getBo…21724 tokens truncated…hild');
      return {
        viewport:{width:innerWidth,height:innerHeight},
        documentWidth:document.documentElement.scrollWidth,
        composer:document.querySelector('#composer').getBoundingClientRect(),
        lastAction:last?.getBoundingClientRect(),
        home:document.querySelector('.home-intro').getBoundingClientRect(),
      };
    });
    assert.ok(shortOrTall.documentWidth<=width,"short, tall or landscape viewport must not create horizontal page overflow: "+JSON.stringify(shortOrTall));
    assert.ok(shortOrTall.composer.left>=-1&&shortOrTall.composer.right<=width+1&&shortOrTall.composer.bottom<=height+1,
      "composer must remain in view in short, tall and landscape layouts: "+JSON.stringify(shortOrTall));
    assert.ok(shortOrTall.lastAction&&shortOrTall.lastAction.bottom<=shortOrTall.composer.top+1,
      "The final Home action must remain reachable above the composer in short, tall and landscape layouts: "+JSON.stringify(shortOrTall));
  }
  const responsiveModuleWidths=[320,360,375,390,430,600,768,820,1024,1280,1440,1920,2560];
  const responsiveModules=["memory","knowledge","activities","tools","workflows","devices","dashboard","settings","owner","system"];
  for(const width of responsiveModuleWidths){
    await page.setViewportSize({width,height:844});
    for(const moduleName of responsiveModules){
      await page.evaluate(name=>openModule(name),moduleName);
      const moduleLayout=await page.evaluate(()=>{
        const panel=document.querySelector('#modulePanel').getBoundingClientRect();
        const content=document.querySelector('#moduleBody').getBoundingClientRect();
        return {viewport:innerWidth,document:document.documentElement.scrollWidth,
          panel:{left:panel.left,right:panel.right,width:panel.width,height:panel.height},
          content:{left:content.left,right:content.right,width:content.width,height:content.height},
          focused:document.body.classList.contains('focused-module')};
      });
      assert.ok(moduleLayout.document<=width,
        moduleName+" page introduced document overflow at "+width+"px: "+JSON.stringify(moduleLayout));
      assert.ok(moduleLayout.panel.width>0&&moduleLayout.panel.left>=-1&&moduleLayout.panel.right<=width+1,
        moduleName+" panel moved beyond the viewport at "+width+"px: "+JSON.stringify(moduleLayout));
      assert.ok(moduleLayout.content.left>=-1&&moduleLayout.content.right<=width+1,
        moduleName+" content moved beyond the viewport at "+width+"px: "+JSON.stringify(moduleLayout));
      assert.equal(moduleLayout.focused,true,moduleName+" should use the focused product page layout");
    }
  }
  for(const width of [320,390,768,1440]){
    await page.setViewportSize({width,height:844});
    await page.evaluate(()=>openModule('memory'));
    await page.waitForSelector('#moduleBody .rp-page[data-rp-page="memory"]');
    const memoryLayout=await page.evaluate(()=>({
      documentWidth:document.documentElement.scrollWidth,
      page:document.querySelector('#moduleBody .rp-page[data-rp-page="memory"]').getBoundingClientRect(),
      items:[...document.querySelectorAll('#moduleBody .mx-saved')].map(node=>node.getBoundingClientRect()),
    }));
    assert.ok(memoryLayout.documentWidth<=width,"Memory page must not introduce horizontal overflow at "+width+"px");
    assert.ok(memoryLayout.page.left>=-1&&memoryLayout.page.right<=width+1,"Memory page must remain within the viewport at "+width+"px");
    assert.ok(memoryLayout.items.length>0,"Preview Memory page must show its isolated browser fixture");
    assert.ok(memoryLayout.items.every(rect=>rect.left>=-1&&rect.right<=width+1),"Memory items must remain within the viewport at "+width+"px");
  }
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>openModule('home'));

  // Keyboard and creation controls use the existing application bindings.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.click("#historyButton");
  await page.click("#sidebarNewChat");
  await page.waitForFunction(() => document.querySelector("#appDrawer").classList.contains("hidden") && !document.body.classList.contains("home-landing") && document.querySelectorAll("#messageStream .message").length === 0);
  await page.click("#historyButton");
  await page.click("#appConversations");
  await page.click("#newConversation");
  await page.waitForFunction(() => !document.body.classList.contains("home-landing") && document.querySelectorAll("#messageStream .message").length === 0);
  const sharedChatChrome=await page.evaluate(()=>({
    header:document.querySelector(".topbar").getBoundingClientRect(),
    menu:document.querySelector("#historyButton").getBoundingClientRect(),
    timeline:document.querySelector("#ownerButton").getBoundingClientRect(),
    headerPosition:getComputedStyle(document.querySelector(".topbar")).position,
    headerBackground:getComputedStyle(document.querySelector(".topbar")).backgroundColor,
    headerBorder:getComputedStyle(document.querySelector(".topbar")).borderTopWidth,
    sphere:document.querySelector(".topbar .core-stage").getBoundingClientRect(),
    composer:document.querySelector("#composer").getBoundingClientRect(),
    composerPosition:getComputedStyle(document.querySelector("#composer")).position
  }));
  assert.equal(sharedChatChrome.headerPosition,"fixed","conversation topbar must use the same fixed shared topbar");
  assert.equal(sharedChatChrome.headerBackground,"rgba(0, 0, 0, 0)","conversation topbar must use the same transparent format");
  assert.equal(sharedChatChrome.headerBorder,"0px","conversation topbar must not add a panel border");
  assert.ok(Math.abs(sharedChatChrome.menu.left-sharedChatChrome.header.left)<=1,"conversation hamburger must keep the shared left-edge alignment");
  assert.ok(Math.abs(sharedChatChrome.timeline.right-sharedChatChrome.header.right)<=1,"conversation Timeline control must keep the shared right-edge alignment");
  assert.ok(sharedChatChrome.sphere.width>=40&&sharedChatChrome.sphere.width<=66,"conversation sphere must keep the shared compact topbar scale");
  assert.equal(sharedChatChrome.composerPosition,"fixed","conversation SMS composer must use the same fixed bottom format");
  assert.ok(sharedChatChrome.composer.height>=52&&sharedChatChrome.composer.height<=56,"conversation SMS composer must match the Home compact pill height");

  // Shared composer contract: focus and a single line stay in the same compact SMS pill everywhere.
  await page.locator("#message").focus();
  const emptyFocused = await page.evaluate(() => ({
    composer: document.querySelector("#composer").getBoundingClientRect(),
    editor: document.querySelector("#message").getBoundingClientRect(),
    expanded: document.querySelector("#composer").classList.contains("is-expanded"),
    position: getComputedStyle(document.querySelector("#composer")).position,
    viewportHeight: innerHeight,
  }));
  assert.equal(emptyFocused.expanded,false,"focus alone must not enlarge the shared SMS composer");
  assert.equal(emptyFocused.position,"fixed","shared SMS composer must be fixed to the viewport");
  assert.ok(emptyFocused.composer.height>=52&&emptyFocused.composer.height<=56,"focused empty shared composer must keep the compact pill height");
  assertSharedComposerBottomInset(emptyFocused.composer.bottom,emptyFocused.viewportHeight,"shared focused composer");
  await page.fill("#message", "Hello from browser QA");
  assert.ok(await page.locator("#composer").evaluate(node => node.classList.contains("has-text")), "text input must show send state");
  assert.equal(await page.locator("#composer").evaluate(node => node.classList.contains("is-expanded")),false,"single-line text must keep the same compact SMS box");
  assert.ok(await page.locator("#sendButton").isVisible(), "send control must appear when typing");
  assert.equal(await page.locator("#micButton").isVisible(), false, "mic icon must yield to send while typing");
  const typedLayout = await page.evaluate(() => ({
    viewportHeight: innerHeight,
    form: document.querySelector("#composer").getBoundingClientRect(),
    editor: document.querySelector("#message").getBoundingClientRect(),
    plus: document.querySelector("#attachmentButton").getBoundingClientRect(),
    send: document.querySelector("#sendButton").getBoundingClientRect(),
  }));
  assert.ok(typedLayout.form.height>=52&&typedLayout.form.height<=56,"single-line typed composer must remain the compact shared pill");
  assert.ok(typedLayout.form.bottom <= typedLayout.viewportHeight + 1, "shared composer must remain visible while focused");
  const singleLineEditorHeight = typedLayout.editor.height;
  await page.fill("#message", "First line\nSecond line\nThird line\nFourth line");
  const multiline = await page.evaluate(() => ({
    viewportHeight: innerHeight,
    form: document.querySelector("#composer").getBoundingClientRect(),
    editor: document.querySelector("#message").getBoundingClientRect(),
    text: document.querySelector("#message").value,
    plus: document.querySelector("#attachmentButton").getBoundingClientRect(),
    send: document.querySelector("#sendButton").getBoundingClientRect(),
  }));
  assert.ok(multiline.editor.height > singleLineEditorHeight + 20, "multiline text must expand the editor vertically");
  assert.ok(multiline.form.height>=105,"only multiline content may expand the shared composer");
  assert.ok(multiline.plus.top >= multiline.editor.bottom - 3 && multiline.send.top >= multiline.editor.bottom - 3, "icons must remain in the bottom row with multiple lines");
  assert.ok(multiline.form.bottom <= multiline.viewportHeight + 1, "multiline editor must not push the composer off-screen");
  await page.locator("#message").press("Shift+Enter");
  assert.ok((await page.locator("#message").inputValue()).endsWith("\n"), "Shift+Enter must insert a new line instead of submitting");
  await page.setViewportSize({ width: 320, height: 568 });
  await page.waitForTimeout(100);
  const narrowTyping = await page.evaluate(() => ({
    width: innerWidth,viewportHeight:innerHeight,
    scrollWidth: document.documentElement.scrollWidth,
    form: document.querySelector("#composer").getBoundingClientRect(),
    editor: document.querySelector("#message").getBoundingClientRect(),
    plus: document.querySelector("#attachmentButton").getBoundingClientRect(),
    send: document.querySelector("#sendButton").getBoundingClientRect(),
  }));
  assert.ok(narrowTyping.scrollWidth <= narrowTyping.width, "expanded 320px composer must not overflow horizontally");
  assert.ok(narrowTyping.form.bottom <= narrowTyping.viewportHeight + 1 && narrowTyping.form.left >= -1 && narrowTyping.form.right <= narrowTyping.width + 1, "expanded 320px composer must remain inside viewport");
  assert.ok(narrowTyping.plus.top >= narrowTyping.editor.bottom - 3 && narrowTyping.send.top >= narrowTyping.editor.bottom - 3, "320px toolbar buttons must stay under the editor");
  await page.screenshot({ path: "artifacts/personal-ai-expanded-composer-320x568.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.fill("#message", "Hello from browser QA");
  assert.equal(await page.locator(".v-shortcuts").isVisible(), false, "new empty chat must not duplicate Home quick actions");
  assert.equal(await page.locator(".topbar .header-core .core-stage").evaluate(node => getComputedStyle(node).visibility), "visible", "new empty chat retains mini header sphere");
  await page.screenshot({ path: "artifacts/personal-ai-new-chat-390x844.png", fullPage: true });
  await page.locator("#message").focus();
  assert.equal(await page.locator("#message").evaluate(node => document.activeElement === node), true, "composer input must receive keyboard focus");
  await page.locator("#attachmentInput").setInputFiles({ name: "browser-qa.txt", mimeType: "text/plain", buffer: Buffer.from("Browser attachment test") });
  await page.waitForFunction(() => document.querySelector("#toast")?.textContent.includes("Document added to Knowledge"));
  assert.equal(uploadedDocuments.length, 1, "attachment must use the existing Knowledge ingestion endpoint");
  assert.equal(uploadedDocuments[0].filename, "browser-qa.txt");
  assert.ok(uploadedDocuments[0].content_base64, "attachment bytes must be sent to Knowledge");
  const conversationsBeforeFirstSend = conversationCreateCount;
  const turnsBeforeFirstSend = turnConversationIds.length;
  await page.click("#sendButton");
  await page.waitForFunction(() => document.querySelectorAll("#messageStream .message").length >= 2);
  assert.ok((await page.locator("#messageStream").innerText()).includes("Hello from browser QA"), "user message must render");
  assert.ok((await page.locator("#messageStream").innerText()).includes("Received: Hello from browser QA"), "assistant response must render");
  assert.equal(conversationCreateCount,conversationsBeforeFirstSend,"the first message must reuse the blank conversation created by New chat, without creating a duplicate");
  assert.deepEqual(turnConversationIds.slice(turnsBeforeFirstSend),["new"],"the first message must be sent to the newly created conversation, never the old active chat");
  assert.equal(await page.evaluate(() => currentConversationId),"new","the UI must remain inside the newly created conversation");
  assert.equal(await page.locator(".message-time").count(),2,"canonical timestamps must render for both sides of the first turn");
  assert.equal(await page.locator(".message-time.pending").count(),0,"canonical sync must replace optimistic Syncing timestamps");
  await page.waitForFunction(() => document.querySelector("#composer").getBoundingClientRect().height <= 54);
  await page.fill("#message", "Keyboard submit");
  await page.locator("#message").press("Enter");
  await page.waitForFunction(() => document.querySelectorAll("#messageStream .message").length === 4);
  assert.ok((await page.locator("#messageStream").innerText()).includes("Received: Keyboard submit"), "Enter must submit the multiline editor without requiring a click");
  assert.equal(conversationCreateCount,conversationsBeforeFirstSend,"subsequent messages must reuse the same fresh conversation");
  assert.deepEqual(turnConversationIds.slice(turnsBeforeFirstSend),["new","new"],"every later turn must stay in that newly created conversation");
  assert.equal(await page.evaluate(() => currentConversationId),"new");
  assert.equal(await page.locator(".message-time").count(),4,"every canonical user and AI message must keep an individual timestamp");
  assert.equal(await page.locator(".message-time.pending").count(),0);
  // Let the headless browser's synthetic TTS attempt settle, then capture the
  // stable text-chat state rather than a transient autoplay-voice warning.
  await page.waitForTimeout(3500);
  await page.evaluate(()=>{
    if(document.activeElement&&document.activeElement.blur)document.activeElement.blur();
    $('voiceAlert').textContent='';setState('idle');document.querySelector('#toast')?.classList.add('hidden');
  });
  await page.waitForFunction(()=>document.querySelector("#composer").getBoundingClientRect().height<=54);
  await page.screenshot({ path: "artifacts/personal-ai-chat-short-390x844.png", fullPage: true });

  await page.setViewportSize({ width: 844, height: 390 });
  await page.evaluate(() => enterHomeLanding());
  await page.waitForTimeout(250);
  const landscape = await page.evaluate(() => ({
    innerWidth, innerHeight,
    scrollWidth: document.documentElement.scrollWidth,
    composerBottom: document.querySelector("#composer").getBoundingClientRect().bottom,
    headerLeft: document.querySelector(".topbar").getBoundingClientRect().left,
    headerRight: document.querySelector(".topbar").getBoundingClientRect().right,
  }));
  assert.ok(landscape.scrollWidth <= landscape.innerWidth, "landscape must not scroll horizontally");
  assert.ok(landscape.composerBottom <= landscape.innerHeight + 1, "landscape composer must stay in viewport");
  assertSharedComposerBottomInset(landscape.composerBottom,landscape.innerHeight,"landscape Home composer");
  assert.equal(await page.locator(".topbar").evaluate(node=>getComputedStyle(node).position),"fixed","landscape Home topbar must remain fixed");
  assert.equal(await page.locator("#composer").evaluate(node=>getComputedStyle(node).position),"fixed","landscape Home composer must remain fixed");
  assert.ok(landscape.headerLeft >= 0 && landscape.headerRight <= landscape.innerWidth + 1, "landscape header must fit");
  await page.screenshot({ path: "artifacts/personal-ai-home-landscape-844x390.png", fullPage: true });
  assert.equal(await page.locator("#chatMenuButton").isVisible(),false,"conversation actions must disappear on Home even when old chat exists");
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>openConversation("new"));
  await page.waitForFunction(()=>!document.querySelector("#chatMenuButton").classList.contains("hidden"));
  await page.click("#chatDetailsTop");
  await page.click("#chatDelete");await page.click("#actionDialogCancel");
  assert.deepEqual(deletedConversationIds,[],"cancel must leave conversation untouched");
  await page.click("#chatDetailsTop");
  await page.click("#chatDelete");await page.click("#actionDialogSubmit");
  await page.waitForFunction(()=>document.body.classList.contains("home-landing")&&document.querySelector("#chatMenuButton").classList.contains("hidden"));
  assert.deepEqual(deletedConversationIds,["new"],"confirmed delete must call the secured conversation endpoint exactly once");

  // Current reference pages use the shared rp-* UI contract and selectors.
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>openModule('activities'));
  await page.waitForFunction(()=>document.querySelector('.rp-page[data-rp-page="activities"]'));
  assert.equal(await page.locator('[data-rp-activity]').count(),1,'Activity must render the persisted event');
  assert.match(await page.locator('[data-rp-activity]').first().innerText(),/Workflow Run Finished/i,'Activity event has a readable title');
  await page.locator('[data-rp-activity]').first().click();
  assert.equal(await page.locator('.rp-desktop-detail.rp-selected-detail').count(),1,'Activity selection opens its details panel');
  await page.fill('#rp-activity-search','Morning operations');
  await page.waitForFunction(()=>document.querySelectorAll('[data-rp-activity]').length===1);
  await page.fill('#rp-activity-search','no matching title');
  await page.waitForFunction(()=>document.querySelector('.rp-list .rp-empty'));
  assert.match(await page.locator('.rp-list').innerText(),/No activity matches your search/,'Activity search has an honest empty state');
  await page.fill('#rp-activity-search','');
  await page.screenshot({path:'artifacts/personal-ai-activities-390x844.png',fullPage:true});

  await page.evaluate(()=>openModule('tools'));
  await page.waitForFunction(()=>document.querySelector('.rp-page[data-rp-page="tools"]'));
  assert.ok(await page.locator('.rp-tool-card').count()>0,'Tools lists the supported capabilities');
  assert.match(await page.locator('.rp-service-list').innerText(),/Google Drive/,'Tools shows the connected service from the API');
  await page.fill('#rp-tools-search','Google Drive');
  await page.waitForFunction(()=>document.querySelector('.rp-service-card'));
  assert.match(await page.locator('.rp-service-card').innerText(),/Google Drive/,'Tools search filters connected services');
  await page.fill('#rp-tools-search','');
  await page.screenshot({path:'artifacts/personal-ai-apps-tools-390x844.png',fullPage:true});

  await page.evaluate(()=>openModule('workflows'));
  await page.waitForFunction(()=>document.querySelector('.rp-page[data-rp-page="workflows"]'));
  assert.equal(await page.locator('#rp-workflows-search').isVisible(),true,'Workflows search is available');
  assert.equal(await page.locator('[data-rp-run-history]').isVisible(),true,'Workflow run history is an available action');
  assert.match(await page.locator('.rp-workflow-list').innerText(),/No workflows yet/,'Workflows reports the real empty state');
  await page.screenshot({path:'artifacts/personal-ai-workflows-390x844.png',fullPage:true});

  await page.evaluate(()=>openModule('knowledge'));
  await page.waitForFunction(()=>document.querySelector('.rp-page[data-rp-page="knowledge"]'));
  assert.equal(await page.locator('.rp-knowledge-item').count(),1,'Knowledge renders the current account item');
  assert.match(await page.locator('.rp-knowledge-item').innerText(),/Indexed/,'Knowledge shows the available indexing status');
  assert.equal(await page.locator('#knowledgeNoteCreate').isVisible(),true,'Knowledge offers a dedicated Markdown note editor');
  assert.equal(await page.locator('#knowledgePortableImport').isVisible(),true,'Knowledge offers Markdown and archive import');
  assert.equal(await page.locator('#knowledgePortableExport').isVisible(),true,'Knowledge offers a portable archive export');
  await page.fill('#rp-knowledge-search','notes');
  await page.waitForTimeout(360);
  assert.equal(await page.evaluate(()=>document.activeElement?.id),'rp-knowledge-search','Knowledge search retains focus after refreshed results');
  await page.screenshot({path:'artifacts/personal-ai-knowledge-390x844.png',fullPage:true});

  await page.evaluate(()=>openModule('home'));
  assert.equal(await page.locator('#modulePanel').isVisible(),false,'section Close returns to Home');
  await page.evaluate(()=>openModule('memory'));
  await page.waitForFunction(()=>document.querySelector('.rp-page[data-rp-page="memory"] .mx-main-toggle'));
  assert.equal(await page.locator('.rp-page[data-rp-page="memory"] .mx-saved').count(),1,'Ambient Memory renders a real-record browser fixture');
  assert.equal(await page.locator('.rp-page[data-rp-page="memory"] .mx-review-callout').isVisible(),true,'Ambient Memory explains approval before save');
  await page.locator('[data-mx-source="projects"]').click();
  assert.equal(ambientSettings.sources.projects,true,'Ambient source permissions persist');
  await page.locator('[data-mx-scan]').click();
  assert.equal(ambientScanRequests,1,'Enabled project and file sources can be scanned');
  await page.locator('[data-mx-retention]').selectOption('6_months');
  assert.equal(ambientSettings.retention,'6_months','Ambient retention selection persists');
  assert.equal(await page.locator('.rp-page[data-rp-page="memory"] .mx-candidate').count(),1,'Pending candidate comes from the owner review queue');
  await page.locator('[data-mx-review]').click();
  await page.locator('dialog input[name="subject"]').fill('Owner-edited browser candidate');
  assert.equal(await page.locator('.rp-page[data-rp-page="memory"] .mx-saved').count(),1,'Reviewing a candidate does not save it');
  await page.locator('dialog [data-approve]').click();
  await page.waitForFunction(()=>document.querySelectorAll('.rp-page[data-rp-page="memory"] .mx-candidate').length===0);
  assert.equal(await page.locator('.rp-page[data-rp-page="memory"] .mx-saved').count(),2,'Explicit approval persists the reviewed candidate');
  assert.equal(ambientCandidateEdits[0].subject,'Owner-edited browser candidate','Review can edit the candidate before approval');
  await page.getByRole('button',{name:'Tree',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.rp-page[data-rp-page="memory"] .mx-node'));
  await page.locator('[data-mx-search]:visible').first().fill('project');
  assert.equal(await page.locator('.rp-page[data-rp-page="memory"] .mx-node').count(),1,'Tree search filters actual memory nodes');
  await page.getByRole('button',{name:'2D',exact:true}).first().click();
  assert.equal(await page.locator('.mx-mode button[aria-pressed="true"]').innerText(),'2D','2D mode can be selected');
  await page.getByRole('button',{name:'Graph',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.rp-page[data-rp-page="memory"] .mx-node'));
  await page.getByRole('button',{name:'Filter',exact:true}).click();
  assert.equal(await page.getByRole('heading',{name:'Legend & Filters'}).isVisible(),true,'Graph filter and legend sheet opens');
  await page.keyboard.press('Escape');
  await page.screenshot({path:'artifacts/personal-ai-memory-390x844.png',fullPage:true});
  await page.evaluate(()=>openModule('home'));
  assert.equal(await page.locator('#modulePanel').isVisible(),false,'section navigation returns to Home');

  // Verify the global reduced-motion contract and a 200%-zoom-equivalent CSS viewport.
  // Playwright cannot change browser chrome zoom; the reduced CSS viewport exercises its reflow outcome.
  await page.emulateMedia({ reducedMotion: "reduce" });
  const reducedMotion = await page.evaluate(() => ({
    requested: matchMedia("(prefers-reduced-motion: reduce)").matches,
    scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
  }));
  assert.equal(reducedMotion.requested, true, "reduced-motion preference must reach the application");
  assert.equal(reducedMotion.scrollBehavior, "auto", "reduced-motion mode must disable smooth page scrolling");
  await page.emulateMedia({ reducedMotion: "no-preference" });
  const openDrawers = await page.evaluate(() => ({
    app: !document.querySelector("#appDrawer").classList.contains("hidden"),
    conversation: !document.querySelector("#conversationDrawer").classList.contains("hidden"),
    mode: document.querySelector("#conversationDrawer").dataset.mode,
  }));
  if (openDrawers.app) await page.click("#closeAppDrawer");
  if (openDrawers.conversation) {
    await page.click(openDrawers.mode === "timeline" ? "#timelineCloseDrawer" : "#closeDrawer");
  }
  await page.waitForFunction(() =>
    document.querySelector("#appDrawer").classList.contains("hidden") &&
    document.querySelector("#conversationDrawer").classList.contains("hidden"));
  await page.setViewportSize({ width: 195, height: 422 });
  await page.evaluate(() => enterHomeLanding());
  const zoomEquivalent = await page.evaluate(() => {
    const composer = document.querySelector("#composer");
    const rect = composer.getBoundingClientRect();
    return {
      viewport: innerWidth,
      document: document.documentElement.scrollWidth,
      composer: { left: rect.left, right: rect.right, width: rect.width, height: rect.height,
        display: getComputedStyle(composer).display, visibility: getComputedStyle(composer).visibility,
        classes: composer.className, bodyClasses: document.body.className },
    };
  });
  await page.screenshot({ path: "artifacts/personal-ai-home-zoom-equivalent-195x422.png", fullPage: true });
  assert.ok(zoomEquivalent.document <= zoomEquivalent.viewport, "200%-zoom-equivalent layout must not overflow horizontally: " + JSON.stringify(zoomEquivalent));
  assert.ok(zoomEquivalent.composer.left >= -1 && zoomEquivalent.composer.right <= zoomEquivalent.viewport + 1,
    "composer must remain inside the zoom-equivalent viewport: " + JSON.stringify(zoomEquivalent));
  assert.ok(zoomEquivalent.composer.height > 0, "composer must remain visible at the 200%-zoom-equivalent viewport: " + JSON.stringify(zoomEquivalent));
  // A 320 CSS-pixel viewport is the standard 400%-reflow equivalent for a
  // 1280px desktop viewport; browser chrome zoom itself is not controllable here.
  await page.setViewportSize({ width: 320, height: 568 });
  await page.evaluate(() => enterHomeLanding());
  const fourHundredPercentReflow=await page.evaluate(()=>({
    viewport:innerWidth,document:document.documentElement.scrollWidth,
    composer:document.querySelector('#composer').getBoundingClientRect(),
    quick:document.querySelector('.v-shortcuts').getBoundingClientRect(),
  }));
  assert.ok(fourHundredPercentReflow.document<=320,"400%-equivalent reflow must not create page overflow: "+JSON.stringify(fourHundredPercentReflow));
  assert.ok(fourHundredPercentReflow.composer.left>=-1&&fourHundredPercentReflow.composer.right<=321,"composer must remain visible in 400%-equivalent reflow");
  assert.ok(fourHundredPercentReflow.quick.left>=-1&&fourHundredPercentReflow.quick.right<=321,"Home actions must remain visible in 400%-equivalent reflow");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator("#historyButton").focus();
  await page.keyboard.press("Tab");
  const keyboardFocus = await page.evaluate(() => {
    const node = document.activeElement;
    return node !== document.body && !!node && node.id !== "historyButton" &&
      node.getClientRects().length > 0 && node.tabIndex >= 0 && node.matches(":focus-visible") &&
      getComputedStyle(node).outlineStyle === "solid";
  });
  assert.ok(keyboardFocus, "Tab must move focus to a visible keyboard-operable control with a focus ring");

  assert.deepEqual(pageErrors, [], "page must render without uncaught JavaScript errors");
  console.log("Responsive PWA qualification passed Home, chat, mobile keyboard, timeline, conversations, content pages, reduced motion and keyboard focus; "+(responsiveModules.length*responsiveModuleWidths.length)+" module/viewport combinations and "+sweepWidths.size+" intermediate Home widths from 320px through 2560px.");

  // Signing out clears previously loaded private rows, and the drawer must not
  // leave an unauthorized request stuck in its loading state.
  revokeSession=true;
  await page.click("#historyButton");
  await page.click("#sidebarAccountButton");
  await page.click("#drawerSignOut");await page.click("#actionDialogSubmit");
  await page.waitForFunction(()=>!document.querySelector("#enrollPanel").classList.contains("hidden"));
  await page.click("#ownerButton");
  await page.waitForFunction(()=>document.querySelector("#conversationCount").textContent==="Sign in required");
  assert.match(await page.locator("#conversationList").innerText(),/Sign in to view timeline\s+Your chats, plans and activity will appear here after authentication\./);
  assert.doesNotMatch(await page.locator("#conversationList").innerText(),/Project Planning|Team planning meeting|Finish daily review/,
    "signed-out timeline must not retain authenticated conversation or activity rows");
  assert.doesNotMatch(await page.locator("#conversationList").innerText(),/Loading your timeline|Loading real Vishnu activity/,
    "signed-out timeline must not spin indefinitely");
  await page.screenshot({path:"artifacts/personal-ai-signed-out-timeline-390x844.png",fullPage:true});

  // Authentication presentation only: real password, Google and passkey authority
  // are exercised separately by the server integration/security suite.
  const locked = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await locked.route("https://accounts.google.com/**", route => route.abort());
  await locked.route("**/iphone/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/status")) {
      return route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Owner verification required" }) });
    }
    return route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ password_available: true, passkey_available: false, google_available: false }),
    });
  });
  await locked.goto("http://127.0.0.1:4173/iphone/", { waitUntil: "domcontentloaded" });
  await locked.waitForFunction(() => !document.querySelector("#enrollPanel").classList.contains("hidden"));
  assert.ok(await locked.locator("#passwordChoice").isVisible(), "real owner password option must remain accessible");
  await locked.click("#passwordChoice");
  assert.ok(await locked.locator("#ownerPassword").isVisible(), "owner password form must open");
  await locked.screenshot({ path: "artifacts/personal-ai-login-390x844.png", fullPage: true });
  await locked.close();


} finally {
  await browser.close();
}
