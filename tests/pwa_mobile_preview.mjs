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
      recentRowHeights:[...document.querySelectorAll(".home-recent-row")].map(node=>node.getBoundingClientRect().height),
      scrollWidth:document.documentElement.scrollWidth,innerWidth,innerHeight
    };
  });
  assert.equal(await page.locator("#chatMenuButton").isVisible(), false, "three-dot conversation menu must be absent on Home");
  assert.equal(await page.locator("#messageStream .message").count(), 0, "Home must clear the resumed chat from the new-chat draft surface");
  assert.equal(homeState.quickActions.length,4,"Home should render its four current action cards");
  assert.deepEqual(homeState.actionTitles,["Projects","Assign work","Today","Memory"],"Home actions must use the current Projects, work, Today and Memory destinations");
  assert.ok(homeState.cardRects.every(card=>Math.abs(card.height-homeState.cardRects[0].height)<1&&Math.abs(card.width-homeState.cardRects[0].width)<1),"the four current Home action cards should be equal sized");
  assert.ok(homeState.cardRects.every(card=>card.height>=58&&card.height<=100),"Home action cards should remain compact");
  assert.ok(homeState.menuButton.width>=44&&homeState.menuButton.height>=44,"Home hamburger must preserve an accessible touch target");
  assert.ok(homeState.timelineButton.width>=44&&homeState.timelineButton.height>=44,"Home timeline control must preserve an accessible touch target");
  assertSharedComposerBottomInset(homeState.composer.bottom,homeState.innerHeight,"Home composer");
  const recentSectionVisible=await page.locator("#homeRecentSection").isVisible();
  if(recentSectionVisible){
    assert.deepEqual(homeState.recentTitles,conversations.map(item=>item.title),"visible Home Recent must use canonical conversation data");
    assert.deepEqual(homeState.recentDateTimes,conversations.map(item=>new Date(item.updated_at).toISOString()),"visible Home Recent timestamps must derive from canonical conversation times");
    assert.equal(await page.locator(".home-recent-menu").count(),conversations.length,"every visible Recent row should expose its conversation options");
  }else{
    assert.equal(await page.locator("#homeRecentSection").evaluate(node=>getComputedStyle(node).display),"none","the reference Home layout intentionally hides the legacy Recent section");
  }
  assert.equal(homeState.todayTitle,"Today");
  assert.deepEqual(homeState.timeline,["Finish daily review","Team planning meeting"],"Today should show canonical plan items");
  assert.ok((await page.locator(".calendar-status-copy").innerText()).includes("External calendars not connected"),"calendar row should report the disconnected state");
  assert.equal(await page.locator("#homeCalendarConnect").getAttribute("aria-label"),"Open Tools to connect an external calendar");
  for(const section of [homeState.header,homeState.quick,homeState.recent,homeState.today,homeState.calendar,homeState.composer]){
    assert.ok(section.left>=-1&&section.right<=homeState.innerWidth+1,"Home section should remain inside the viewport");
  }
  assert.ok(homeState.scrollWidth<=homeState.innerWidth,"Home must not scroll horizontally");
  await page.screenshot({ path: "artifacts/personal-ai-home-390x844.png", fullPage: true });

  // The current reference Home hides the legacy Recent section. Exercise its old
  // conversation controls only in layouts where the section is intentionally shown.
  if(recentSectionVisible){
    await page.click("#homeRecentSeeAll");
    await page.waitForFunction(()=>!document.querySelector("#conversationDrawer").classList.contains("hidden"));
    assert.equal(await page.locator("#appDrawer").isVisible(),false,"Home See all must use the existing right-side conversation destination");
    await page.click("#closeDrawer");
    await page.locator(".home-recent-open").first().click();
    await page.waitForFunction(()=>!document.body.classList.contains("home-landing")&&document.querySelectorAll("#messageStream .message").length===2);
    assert.equal(await page.evaluate(()=>currentConversationId),"c1","Home Recent row must open the actual persisted conversation");
    await page.evaluate(()=>enterHomeLanding());
    await page.waitForFunction(()=>document.body.classList.contains("home-landing"));
    await page.locator(".home-recent-menu").first().click();
    await page.waitForFunction(()=>!document.querySelector("#chatActionMenu").classList.contains("hidden"));
    assert.equal(await page.evaluate(()=>currentConversationId),"c1","Home Recent overflow must route to the selected real conversation before exposing existing actions");
    await page.keyboard.press("Escape");
    await page.evaluate(()=>enterHomeLanding());
    await page.evaluate(()=>renderHomeRecent([]));
    assert.ok((await page.locator("#homeRecentList").innerText()).includes("No recent conversations yet."));
    await page.screenshot({ path: "artifacts/personal-ai-home-recent-empty-390x844.png", fullPage: true });
    await page.evaluate(()=>renderHomeRecent(conversationCache));
  }
  // This legacy Home Today widget is absent from the current reference Home layout.
  // Keep its CRUD coverage when a layout exposes it; the dedicated Today screen
  // below still exercises real and preview flows plus its mobile footer.
  if(await page.locator("#todayAdd").isVisible()){
  // Today timeline is real: add a meeting, mark a task complete, verify empty-state.
  await page.click("#todayAdd");
  assert.ok(await page.locator("#todayDialog").isVisible(), "Add control must open the accessible creation dialog");
  assert.ok(await page.locator("#todayForm").isVisible(), "creation form must remain visible inside its dialog");
  await page.waitForFunction(() => {
    const dialog=document.querySelector("#todayDialog"),date=document.querySelector("#todayScheduledDate"),time=document.querySelector("#todayTime");
    if(!dialog?.open||!date||!time)return false;
    const container=dialog.getBoundingClientRect(),dateBox=date.getBoundingClientRect(),timeBox=time.getBoundingClientRect();
    return container.width>0&&dateBox.width>0&&timeBox.width>0&&dateBox.x>=container.x&&timeBox.x>=container.x&&
      dateBox.right<=container.right&&timeBox.right<=container.right&&timeBox.top>=dateBox.bottom-1;
  });
  const initialDialogBox=await page.locator("#todayDialog").boundingBox();
  const dateBox=await page.locator("#todayScheduledDate").boundingBox(),timeBox=await page.locator("#todayTime").boundingBox();
  assert.ok(dateBox.x>=initialDialogBox.x&&timeBox.x>=initialDialogBox.x&&dateBox.x+dateBox.width<=initialDialogBox.x+initialDialogBox.width&&timeBox.x+timeBox.width<=initialDialogBox.x+initialDialogBox.width,"date and time fields must fit inside the dialog on a phone viewport");
  assert.ok(timeBox.y>=dateBox.y+dateBox.height-1,"date and time fields must not overlap on a phone viewport");
  const touch=await page.context().newCDPSession(page),startX=initialDialogBox.x+initialDialogBox.width/2,startY=initialDialogBox.y+12;
  await touch.send("Input.dispatchTouchEvent",{type:"touchStart",touchPoints:[{x:startX,y:startY}]});
  for(let step=1;step<=4;step++)await touch.send("Input.dispatchTouchEvent",{type:"touchMove",touchPoints:[{x:startX+36*step/4,y:startY+24*step/4}]});
  await touch.send("Input.dispatchTouchEvent",{type:"touchEnd",touchPoints:[]});await touch.detach();
  const movedDialogBox=await page.locator("#todayDialog").boundingBox();
  assert.ok(Math.abs(movedDialogBox.x-initialDialogBox.x)>20||Math.abs(movedDialogBox.y-initialDialogBox.y)>20,"touch-dragging the dialog header must move the popup");
  assert.ok(movedDialogBox.x>=0&&movedDialogBox.y>=0&&movedDialogBox.x+movedDialogBox.width<=390&&movedDialogBox.y+movedDialogBox.height<=844,"dragged dialog must stay within the phone viewport");
  await page.click('[data-today-kind="meeting"]');
  await page.fill("#todayTitle", "Afternoon planning review");
  await page.fill("#todayTime", "15:30");
  await page.click("#todaySave");
  await page.waitForFunction(() => document.querySelectorAll("#todayTimeline .today-item").length === 3);
  assert.deepEqual(await page.locator("#todayTimeline .today-item strong").allTextContents(),
    ["Finish daily review","Team planning meeting","Afternoon planning review"], "Today items must be sorted chronologically");
  await page.click("#todayAdd");await page.click('[data-today-kind="note"]');
  assert.equal(await page.locator("#todayContentWrap").isVisible(),true,"Note selection must reveal the note content field");
  assert.equal(await page.locator("#todayScheduledDate").isVisible(),false,"Notes do not require a task date");
  await page.fill("#todayTitle","Popup note smoke test");await page.fill("#todayContent","Saved through the Vishnu creation dialog.");await page.click("#todaySave");
  assert.equal(createdMemories.length,1,"saving a note must call the memory creation API once");
  assert.equal(createdMemories[0].subject,"Popup note smoke test");
  assert.equal(createdMemories[0].content,"Saved through the Vishnu creation dialog.");
  failNextTaskComplete=true;
  await page.locator("#todayTimeline .today-check").first().click();
  await page.waitForFunction(() => document.querySelector("#toast")?.textContent === "body.task_id: Task could not be completed");
  assert.equal(await page.locator("#toast").textContent(),"body.task_id: Task could not be completed","structured API validation errors must be shown as readable text");
  assert.ok(!(await page.locator("#toast").textContent()).includes("[object Object]"),"toast must never expose JavaScript object coercion");
  assert.equal(await page.locator("#todayTimeline .today-item").count(),3,"a failed completion must leave the item pending");
  await page.evaluate(()=>showToast({message:{unexpected:true}}));
  assert.equal(await page.locator("#toast").textContent(),"Something went wrong. Please try again.","unrenderable toast objects must use a readable fallback");
  await page.locator("#todayTimeline .today-check").first().click();
  await page.waitForFunction(() => document.querySelectorAll("#todayTimeline .today-item").length === 2);
  assert.ok(!((await page.locator("#todayTimeline").innerText()).includes("Finish daily review")), "completing a task must remove it from today's pending list");
  await page.evaluate(() => renderToday([]));
  assert.ok((await page.locator("#todayTimeline").innerText()).includes("Nothing planned yet"), "empty Today card must not invent calendar meetings");
  assert.ok((await page.locator("#todayTimeline").innerText()).includes("Add a task, work item or meeting."), "empty Today card must preserve the approved supporting copy");
  assert.ok(await page.locator(".today-empty-icon").isVisible(), "empty Today card must include the compact calendar visual");
  assert.ok(await page.locator(".today-empty-add").isVisible(), "empty Today card must expose the real add flow");
  await page.evaluate(()=>{
    if(document.activeElement&&document.activeElement.blur)document.activeElement.blur();
    window.scrollTo(0,0);
    const home=document.querySelector("#voicePanel"),intro=document.querySelector("#homeIntro");
    if(home)home.scrollTop=0;if(intro)intro.scrollTop=0;
  });
  await page.waitForTimeout(120);
  await page.evaluate(()=>document.querySelector("#toast")?.classList.add("hidden"));
  const approvedEmptyLayout=await page.evaluate(()=>({
    composer:document.querySelector("#composer").getBoundingClientRect(),
    header:document.querySelector(".topbar").getBoundingClientRect(),
    greeting:document.querySelector(".home-greeting").getBoundingClientRect(),
    viewport:innerHeight,
    viewportWidth:innerWidth,
    scrollWidth:document.documentElement.scrollWidth,
    calendar:{scrollWidth:document.querySelector(".calendar-status-copy").scrollWidth,clientWidth:document.querySelector(".calendar-status-copy").clientWidth},
  }));
  assert.ok(approvedEmptyLayout.greeting.top>=approvedEmptyLayout.header.bottom+6,"approved Home capture must keep the greeting clear of the floating Home controls");
  assert.ok(approvedEmptyLayout.composer.bottom<=approvedEmptyLayout.viewport+1,"approved empty-Today Home composition must keep the composer visible in the primary iPhone viewport");
  assertSharedComposerBottomInset(approvedEmptyLayout.composer.bottom,approvedEmptyLayout.viewport,"approved Home composer");
  assert.ok(approvedEmptyLayout.scrollWidth<=approvedEmptyLayout.viewportWidth,"approved empty-Today Home must not overflow horizontally");
  assert.ok(approvedEmptyLayout.calendar.scrollWidth<=approvedEmptyLayout.calendar.clientWidth+2,"calendar disconnected status must remain fully readable at the primary iPhone width");
  await page.screenshot({ path: "artifacts/personal-ai-home-today-empty-390x844.png", fullPage: true });
  await page.screenshot({ path: "artifacts/personal-ai-home-approved-390x844.png", fullPage: true });
  await page.click(".today-empty-add");
  assert.ok(await page.locator("#todayDialog").isVisible(), "empty Today Add to Today must open the shared creation dialog");
  await page.click("#todayCancel");
  await page.evaluate(() => refreshToday());
  await page.click("#homeCalendarConnect");
  await page.waitForFunction(()=>document.querySelector("#modulePanel").classList.contains("open"));
  assert.equal(await page.evaluate(()=>activeModule),"tools","calendar Connect must lead to the existing Tools surface rather than faking a connection");
  await page.evaluate(()=>openModule("home"));
  await page.waitForFunction(()=>document.body.classList.contains("home-landing"));
  }

  // The conversation-first sidebar keeps owner security behind its anchored account footer.
  await page.click("#historyButton");
  await page.waitForFunction(() => document.querySelectorAll("#sidebarChatList .sidebar-chat-row").length === 3);
  assert.ok(await page.locator("#sidebarAccountButton").isVisible(), "account controls must be anchored to bottom");
  await page.waitForTimeout(300);
  await page.screenshot({ path: "artifacts/personal-ai-sidebar-approved-390x844.png", fullPage: true });
  await page.click("#sidebarAccountButton");
  assert.equal(await page.locator("#sidebarAccountButton").getAttribute("aria-expanded"), "true", "account popover must advertise expanded state");
  for (const label of ["Owner controls","Settings","Trusted devices","System status","Sign out"]) {
    assert.ok((await page.locator("#sidebarAccountMenu").innerText()).includes(label), "account controls missing " + label);
  }
  await page.screenshot({ path: "artifacts/personal-ai-sidebar-account-390x844.png", fullPage: true });
  await page.click("#appOwnerControls");
  await page.waitForFunction(() => document.querySelector("#modulePanel")?.classList.contains("open") && document.querySelector("#moduleTitle")?.textContent === "Owner Controls" && document.querySelector("#moduleBody")?.innerText.includes("Owner Controls"));
  const ownerPageText = (await page.locator("#moduleBody").innerText()).toLowerCase();
  for (const item of ["overview", "ai providers", "connected services", "permissions", "security", "data & backups", "audit log", "quick actions"]) {
    assert.ok(ownerPageText.includes(item), "Owner Controls Overview missing " + item);
  }
  await page.screenshot({ path: "artifacts/personal-ai-owner-controls-390x844.png", fullPage: true });
  await page.locator('.oc-tabs [data-oc-section="providers"]').click();
  await page.waitForFunction(()=>document.querySelector('#moduleBody')?.innerText.includes('Your AI providers'));
  await page.locator('[data-oc-action="provider-add"]').first().click();
  assert.equal(await page.locator('.oc-provider-dialog').isVisible(),true,'Add provider must open the secure connection flow');
  await page.locator('.oc-provider-dialog [name="apiKey"]').fill('sk-browser-test-credential');
  await page.locator('.oc-provider-dialog [data-provider-test]').click();
  await page.waitForFunction(()=>!document.querySelector('.oc-provider-dialog [name="model"]')?.disabled);
  await page.selectOption('.oc-provider-dialog [name="model"]','model-b');
  await page.locator('.oc-provider-dialog [type="submit"]').click();
  await page.waitForFunction(()=>document.querySelector('#moduleBody')?.innerText.includes('Owner configured'));
  await page.locator('[data-oc-provider-model="openai"]').click();
  await page.waitForFunction(()=>!document.querySelector('.oc-provider-dialog [name="model"]')?.disabled);
  await page.selectOption('.oc-provider-dialog [name="model"]','model-a');
  await page.locator('.oc-provider-dialog [type="submit"]').click();
  await page.waitForFunction(()=>document.querySelector('#moduleBody')?.innerText.includes('model-a'));
  assert.ok(!(await page.evaluate(()=>Array.from({length:localStorage.length},(_,i)=>localStorage.getItem(localStorage.key(i))).join('\n'))).includes('sk-browser-test-credential'),'provider credential must never be stored in browser local storage');
  assert.ok(!(await page.locator('#moduleBody').innerText()).includes('sk-browser-test-credential'),'provider credential must never render after save');

  // Reload the app shell before checking its Home-only Timeline control.
  await page.reload();
  await page.waitForFunction(() => document.querySelector("#ownerButton") && !document.body.classList.contains("focused-module"));
  await page.click("#historyButton");
  await page.click("#sidebarAccountButton");
  await page.locator("#sidebarAccountMenu [data-app-module=\"settings\"]").click();
  await page.waitForFunction(() => document.querySelector("#modulePanel")?.classList.contains("open") && document.querySelector("#moduleTitle")?.textContent === "Settings" && document.querySelector("#moduleBody")?.innerText.toLowerCase().includes("ai & intelligence"));
  assert.ok(await page.locator("[data-settings-home-back]").isVisible(), "Settings hub must expose its Back control");
  assert.ok((await page.locator("#moduleBody").innerText()).includes("Language & region"), "Language & region must be reachable from the Settings hub");
  await page.screenshot({ path: "artifacts/personal-ai-settings-390x844.png", fullPage: true });
  await page.locator('[data-settings-section="personal"]').first().click();
  await page.waitForFunction(() => document.querySelector("#localePreviewDate")?.textContent.length > 0);
  assert.ok((await page.locator("#moduleBody").innerText()).includes("App language changes interface labels"), "Language & region must explain its boundary from chat response language");
  await page.screenshot({path:"artifacts/personal-ai-language-region-390x844.png",fullPage:true});
  await page.setViewportSize({width:1504,height:1045});
  await page.waitForTimeout(250);
  const localeDesktopLayout=await page.evaluate(()=>({width:innerWidth,documentWidth:document.documentElement.scrollWidth,preview:document.querySelector('.locale-preview-card')?.getBoundingClientRect().width,settings:document.querySelector('.locale-settings-card')?.getBoundingClientRect().width}));
  assert.ok(localeDesktopLayout.documentWidth<=localeDesktopLayout.width,"Language & region must not overflow at desktop width");
  assert.ok(localeDesktopLayout.preview>0&&localeDesktopLayout.settings>0,"Desktop must show both the settings card and format preview");
  await page.screenshot({path:"artifacts/personal-ai-language-region-1504x1045.png",fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.locator('#settingsBack').click();
  await page.locator('[data-settings-section="appearance"]').click();
  await page.waitForFunction(() => document.querySelector('#moduleBody')?.innerText.includes('Interface density'));
  await page.locator('[data-pref-key="appearance_accent"][data-pref-value="teal"]').click();
  await page.waitForFunction(() => document.documentElement.dataset.accent==='teal');
  assert.equal(uiPreferenceState.appearance_accent,'teal','Appearance preference must persist via the authenticated preferences endpoint');
  await page.screenshot({path:'artifacts/personal-ai-appearance-390x844.png',fullPage:true});
  await page.locator('#settingsBack').click();
  await page.locator('[data-settings-section="chat"]').click();
  await page.waitForFunction(() => document.querySelector('#moduleBody')?.innerText.includes('Chat preview'));
  await page.locator('[data-pref-key="chat_message_spacing"][data-pref-value="compact"]').click();
  await page.waitForFunction(() => document.body.classList.contains('chat-compact'));
  assert.equal(uiPreferenceState.chat_message_spacing,'compact','Chat preference must persist and affect conversation layout');
  await page.screenshot({path:'artifacts/personal-ai-chat-preferences-390x844.png',fullPage:true});
  await page.locator('#settingsBack').click();
  await page.locator('[data-settings-section="notifications"]').click();
  await page.waitForFunction(() => document.querySelector('#moduleBody')?.innerText.includes('Event preferences'));
  assert.equal(await page.locator('.notification-event').count(),6,'Notifications must show all event categories');
  assert.equal(await page.locator('.notification-event input[type="checkbox"]').first().isEnabled(),false,'Unavailable delivery channels must be disabled');
  await page.locator('[data-notify-master][data-notify-event="work_completed"]').click();
  await page.waitForFunction(() => document.querySelector('[data-notify-master][data-notify-event="work_completed"]')?.getAttribute('aria-checked')==='false');
  assert.equal(notificationState.events.work_completed.enabled,false,'Notification event switches must persist through the authenticated preferences API');
  await page.screenshot({path:'artifacts/personal-ai-notifications-390x844.png',fullPage:true});
  await page.locator('#settingsBack').click();
  await page.locator('[data-settings-section="profile"]').click();
  await page.waitForFunction(() => document.querySelector('#moduleBody')?.innerText.includes('Email address verified'));
  await page.fill('#profileFirstName','Taylor');
  assert.match(await page.locator('#moduleBody').innerText(),/Unsaved changes/,'Profile edits must expose a dirty state');
  await page.locator('#profileSave').click();
  await page.waitForFunction(() => document.querySelector('#profileDirty')?.textContent==='');
  assert.equal(profileState.first_name,'Taylor','Profile name changes must persist through the authenticated profile API');
  await page.screenshot({path:'artifacts/personal-ai-profile-390x844.png',fullPage:true});
  await page.locator('#settingsBack').click();
  await page.locator('[data-settings-section="data"]').click();
  await page.waitForFunction(() => document.querySelector('#moduleBody')?.innerText.includes('Privacy & data') && document.querySelector('#manageSavedMemories'));
  assert.ok((await page.locator('#moduleBody').innerText()).includes('Your privacy at a glance'));
  assert.ok((await page.locator('#moduleBody').innerText()).includes('Project context is not available in this installation.'));
  await page.screenshot({path:"artifacts/personal-ai-privacy-data-390x844.png",fullPage:true});
  const memorySwitch=page.locator('[data-privacy-key="privacy_memory_enabled"]');
  assert.equal(await memorySwitch.getAttribute('aria-checked'),'true');
  await memorySwitch.click();
  await page.waitForFunction(()=>document.querySelector('#privacySaveStatus')?.innerText.includes('Changes save automatically'));
  assert.equal(uiPreferenceState.privacy_memory_enabled,false,"Privacy memory choice must persist through the authenticated preference route");
  await page.reload();
  await page.waitForFunction(() => document.querySelector("#ownerButton") && !document.body.classList.contains("focused-module"));

  // Approved Timeline is a premium RIGHT-side contextual drawer and must not regress Home or Conversations.
  await page.click("#ownerButton");
  await page.waitForFunction(() => {
    const drawer = document.querySelector("#conversationDrawer");
    const rect=drawer.getBoundingClientRect();
    return drawer.dataset.mode==="timeline" && !drawer.classList.contains("hidden") && rect.left>=-1 && Math.abs(rect.right-innerWidth)<=1;
  });
  assert.equal(await page.locator("#appDrawer").isVisible(),false,"direct Timeline must not open the main hamburger sidebar");
  assert.equal(await page.locator("#timelineCloseDrawer").getAttribute("aria-label"),"Close timeline");
  assert.equal((await page.locator("#timelineDrawerTitle").innerText()).trim(),"Timeline");
  assert.equal((await page.locator(".timeline-title-block p").innerText()).trim(),"Chats, plans and activity");
  const approvedTimelineHeader=await page.evaluate(()=>({
    drawer:document.querySelector('#conversationDrawer').getBoundingClientRect(),
    viewport:innerWidth,
    back:document.querySelector('#timelineBackDrawer').getBoundingClientRect(),
    close:document.querySelector('#timelineCloseDrawer').getBoundingClientRect(),
    add:document.querySelector('#timelineAddPlan').getBoundingClientRect(),
    search:document.querySelector('.timeline-search-wrap').getBoundingClientRect(),
    background:getComputedStyle(document.querySelector('#conversationDrawer')).backgroundImage,
    border:getComputedStyle(document.querySelector('#conversationDrawer')).borderLeftWidth,
    bodyOverflow:getComputedStyle(document.body).overflow,
    activeElementId:document.activeElement&&document.activeElement.id,
    filterRow:document.querySelector(".conversation-filters").getBoundingClientRect(),
    filterButtons:[...document.querySelectorAll(".conversation-filter")].map(node=>node.getBoundingClientRect())
  }));
  assert.ok(approvedTimelineHeader.drawer.width>=350&&approvedTimelineHeader.drawer.width<=390,"390px Timeline must preserve the approved contextual width");
  assert.ok(approvedTimelineHeader.drawer.left>=-1&&Math.abs(approvedTimelineHeader.drawer.right-approvedTimelineHeader.viewport)<=1,"mobile Timeline must fill the viewport as its own drawer view");
  assert.ok(approvedTimelineHeader.back.width>=44&&approvedTimelineHeader.close.width>=44,"Timeline back and close controls must preserve circular touch targets");
  assert.ok(approvedTimelineHeader.add.height>=46&&approvedTimelineHeader.add.height<=52,"Add to plan must use the approved compact outlined geometry");
  assert.ok(approvedTimelineHeader.search.height>=50&&approvedTimelineHeader.search.height<=56,"Timeline search must match approved compact geometry");
  assert.ok(approvedTimelineHeader.background.includes("linear-gradient"),"Timeline must use premium dark-glass gradient");
  assert.equal(approvedTimelineHeader.border,"0px","full-width mobile Timeline must not add a left seam at the viewport edge");
  assert.equal(approvedTimelineHeader.bodyOverflow,"hidden","underlying app scroll must lock while Timeline is open");
  assert.equal(approvedTimelineHeader.activeElementId,"timelineBackDrawer","opening Timeline must not summon the mobile keyboard by auto-focusing search");
  assert.equal(await page.locator('.conversation-filter.active').getAttribute("data-conversation-filter"),"all","Timeline must always open on the approved All view rather than preserving a stale filter");
  assert.ok(approvedTimelineHeader.filterRow.width>0,"Timeline filters must have a visible horizontal scroll region at the primary 390px viewport");
  await page.screenshot({ path: "artifacts/personal-ai-timeline-approved-direct-390x844.png", fullPage: true });
  await page.click("#timelineCloseDrawer");
  await page.waitForFunction(() => document.querySelector("#conversationDrawer").classList.contains("hidden"));
  assert.equal(await page.locator("#appDrawer").isVisible(),false,"closing directly-opened Timeline must not show the main sidebar");

  await page.click("#historyButton");
  await page.waitForFunction(() => !document.querySelector("#appDrawer").classList.contains("hidden"));
  await page.waitForFunction(() => document.querySelectorAll("#sidebarChatList .sidebar-chat-row").length === 3);
  await page.waitForFunction(() => document.querySelector("#appDrawer").getBoundingClientRect().left >= -1);
  const drawerState = await page.evaluate(() => ({
    labels: [...document.querySelectorAll("#appDrawer .sidebar-nav-row span")].map(node => node.textContent.trim()),
    chatTitles: [...document.querySelectorAll("#sidebarChatList .sidebar-chat-title")].map(node => node.textContent.trim()),
    rect: document.querySelector("#appDrawer").getBoundingClientRect(),
    footer: document.querySelector("#sidebarAccountButton").getBoundingClientRect(),
    expanded: document.querySelector("#historyButton").getAttribute("aria-expanded"),
  }));
  for (const expected of ["Home","Projects","Today","Inbox","Conversations","Memory","Knowledge","Live work","Activity","Tools","Workflows"]) {
    assert.ok(drawerState.labels.includes(expected), "missing functional sidebar section: " + expected);
  }
  assert.deepEqual(drawerState.chatTitles, conversations.map(item=>item.title), "main sidebar must display real canonical conversation history");
  assert.equal(drawerState.expanded, "true", "hamburger aria-expanded must track the sidebar");
  assert.ok(drawerState.rect.width <= 390 && drawerState.rect.left >= -1, "sidebar must fit mobile viewport");
  assert.ok(drawerState.footer.bottom <= 845 && drawerState.footer.height >= 44, "account actions must remain visible and touchable");
  assert.ok(await page.locator("#sidebarNewChat").isVisible(), "new chat must be a primary action");
  assert.ok(await page.locator("#sidebarSearchToggle").isVisible(), "chat search must be a primary action");
  await page.click("#sidebarPinCurrent");
  await page.waitForFunction(()=>document.querySelector("#sidebarPinnedList")?.textContent.includes("Project Planning"));
  assert.deepEqual(sidebarPreferences.pinned_sidebar_items,["chat:c1"],"Pin current must persist the active conversation in trusted-browser preferences");
  await page.locator("#sidebarPinnedList .sidebar-unpin").click();
  await page.waitForFunction(()=>document.querySelector("#sidebarPinnedList")?.textContent.includes("Pin the current chat"));
  await page.screenshot({ path: "artifacts/personal-ai-menu-390x844.png", fullPage: true });
  await page.click("#sidebarSearchToggle");
  assert.equal(await page.locator("#sidebarSearchToggle").getAttribute("aria-expanded"), "true");
  await page.evaluate(() => document.documentElement.style.setProperty("--sidebar-visible-height","540px"));
  const keyboardSidebar = await page.evaluate(() => ({
    pane: document.querySelector("#appDrawer").getBoundingClientRect(),
    account: document.querySelector("#sidebarAccountButton").getBoundingClientRect(),
  }));
  assert.ok(keyboardSidebar.pane.height <= 541 && keyboardSidebar.account.bottom <= 541,
    "sidebar footer must remain within reduced keyboard-height viewport");
  await page.evaluate(() => syncSidebarViewport());
  await page.fill("#sidebarSearch", "Onion");
  await page.waitForFunction(() => document.querySelectorAll("#sidebarChatList .sidebar-chat-row").length === 1 && document.querySelector("#sidebarChatList").textContent.includes("Onion"));
  await page.fill("#sidebarSearch", "not-a-real-chat");
  await page.waitForFunction(() => document.querySelector("#sidebarChatList")?.textContent.includes("No matching conversations"));
  await page.click("#sidebarSearchClear");
  await page.waitForFunction(() => document.querySelectorAll("#sidebarChatList .sidebar-chat-row").length === 3);
  await page.click("#sidebarSearchToggle");
  assert.equal(await page.locator("#sidebarSearchPanel").isVisible(), false, "search must collapse cleanly");

  await page.evaluate(()=>{const open=openConversationsDrawer;window.__conversationOpenTrace={called:false,error:null};window.openConversationsDrawer=function(){window.__conversationOpenTrace.called=true;try{return open()}catch(error){window.__conversationOpenTrace.error=error?.message||String(error);throw error}}});
  await page.click("#appConversations");
  await page.waitForTimeout(500);
  const conversationsOpenState=await page.evaluate(()=>{const panel=document.querySelector("#conversationDrawer"),rect=panel.getBoundingClientRect();return{mode:panel.dataset.mode,hidden:panel.classList.contains("hidden"),rect:{left:rect.left,right:rect.right,width:rect.width},viewport:innerWidth,appDrawerHidden:document.querySelector("#appDrawer").classList.contains("hidden")}});
  const conversationOpenTrace=await page.evaluate(()=>window.__conversationOpenTrace);
  assert.ok(conversationOpenTrace.called&&!conversationOpenTrace.error,"Conversations navigation must invoke its drawer action");
  assert.ok(conversationsOpenState.mode==="conversations"&&!conversationsOpenState.hidden,"Conversations navigation must open its drawer");
  assert.ok(conversationsOpenState.rect.left>=-1&&conversationsOpenState.rect.right<conversationsOpenState.viewport-20,"Conversations drawer must open on the left and leave a visible strip on the right");
  await page.waitForFunction(expected => document.querySelectorAll(".conversations-row").length === expected, conversations.length);
  assert.equal(await page.locator("#appDrawer").isVisible(),false,"Conversations must replace the open main drawer on mobile");
  assert.equal(await page.locator("#closeDrawer").getAttribute("aria-label"),"Close conversations");
  assert.equal((await page.locator("#conversationsDrawerTitle").innerText()).trim(),"Conversations");

  const conversationsState=await page.evaluate(()=>({
    rect:document.querySelector("#conversationDrawer").getBoundingClientRect(),
    viewport:innerWidth,
    title:document.querySelector("#conversationsDrawerTitle").getBoundingClientRect(),
    close:document.querySelector("#closeDrawer").getBoundingClientRect(),
    newChat:document.querySelector("#newConversation").getBoundingClientRect(),
    newChatStyle:{sidebarButton:document.querySelector("#newConversation").classList.contains("sidebar-new-compact"),bottomButton:document.querySelector("#newConversation").classList.contains("conversations-bottom-new-chat")},
    conversationList:document.querySelector("#conversationManagerList").getBoundingClientRect(),
    search:document.querySelector("#conversationManagerSearch").closest(".conversations-search-wrap").getBoundingClientRect(),
    groups:[...document.querySelectorAll(".conversations-group-title")].map(node=>node.textContent.trim()),
    titles:[...document.querySelectorAll(".conversations-row-copy strong")].map(node=>node.textContent.trim()),
    previews:[...document.querySelectorAll(".conversations-row-preview")].map(node=>node.textContent.trim()),
    times:[...document.querySelectorAll(".conversations-row-time")].map(node=>({text:node.textContent,dateTime:node.dateTime})),
    rows:[...document.querySelectorAll(".conversations-row")].map(node=>node.getBoundingClientRect()),
    background:getComputedStyle(document.querySelector("#conversationDrawer")).backgroundImage,
    bodyOverflow:getComputedStyle(document.body).overflow,
  }));
  assert.ok(conversationsState.rect.width>=330&&conversationsState.rect.width<=370,"390px Conversations drawer must preserve the approved ~88% mobile width");
  assert.ok(conversationsState.rect.left>=-1&&conversationsState.rect.right<=conversationsState.viewport-20,"Conversations drawer must leave a visible strip of the underlying app on the right");
  assert.ok(conversationsState.close.width>=44&&conversationsState.close.height>=44,"close control must preserve touch target");
  assert.ok(conversationsState.newChat.height>=46&&conversationsState.newChat.height<=50,"bottom New chat action must match the left sidebar control height");
  assert.equal(conversationsState.newChatStyle.sidebarButton,true,"Conversations New chat must reuse left sidebar button styling");
  assert.equal(conversationsState.newChatStyle.bottomButton,true,"Conversations must use the bottom-pinned New chat action");
  assert.ok(conversationsState.conversationList.bottom<=conversationsState.newChat.top,"conversation list must scroll above the bottom New chat button");
  assert.ok(conversationsState.newChat.bottom<=conversationsState.rect.bottom&&conversationsState.newChat.bottom>=conversationsState.rect.bottom-90,"New chat must stay at the bottom of the iPhone drawer");
  assert.ok(conversationsState.newChat.left>=conversationsState.rect.left&&conversationsState.newChat.right<=conversationsState.rect.right,"bottom New chat button must fit within the drawer");
  assert.ok(conversationsState.search.height>=48&&conversationsState.search.height<=54,"search field must match approved compact geometry");
  assert.deepEqual(conversationsState.groups,["Today","Yesterday","Previous 7 days"],"real local conversation dates must drive approved group headings");
  assert.deepEqual(conversationsState.titles,conversations.map(item=>item.title),"drawer titles must use real canonical conversations");
  assert.deepEqual(conversationsState.previews,conversations.map(item=>item.preview),"drawer previews must use real API data rather than fabricated summaries");
  assert.deepEqual(conversationsState.times.map(item=>item.dateTime),conversations.map(item=>new Date(item.updated_at).toISOString()),"drawer timestamps must preserve canonical updated_at values");
  assert.ok(conversationsState.rows.every(row=>row.height>=66&&row.height<=82),"conversation rows must stay compact and information-dense");
  assert.ok(conversationsState.background.includes("linear-gradient"),"approved Conversations drawer must use the premium glass gradient");
  assert.equal(conversationsState.bodyOverflow,"hidden","background page must be scroll-locked while Conversations drawer is open");
  const forbiddenReferenceSamples=["Project update discussion","Marketing strategy plan","Ideas for mobile app","Weekly meeting notes","Content creation plan","UI/UX improvements","Product roadmap","Research on AI tools","Client meeting","Travel itinerary","Team retrospective"];
  assert.ok(forbiddenReferenceSamples.every(title=>!conversationsState.titles.includes(title)),"reference-image sample conversations must never be hardcoded");

  await page.screenshot({path:"artifacts/personal-ai-conversations-approved-390x844.png",fullPage:true});

  // Context actions stay inside the drawer and expose only existing real capabilities.
  const beforeMenuConversation=await page.evaluate(()=>currentConversationId);
  await page.locator(".conversation-row-menu-button").first().click();
  await page.waitForFunction(()=>!document.querySelector("#conversationRowMenu").classList.contains("hidden"));
  assert.deepEqual(await page.locator("#conversationRowMenu [role=menuitem]").allTextContents(),
    ["✎Rename","⧉Copy transcript","↗Share transcript","↓Download JSON","⌫Delete conversation"]);
  assert.equal(await page.evaluate(()=>currentConversationId),beforeMenuConversation,"opening row actions must not navigate to another conversation");
  await page.screenshot({path:"artifacts/personal-ai-conversations-context-menu-390x844.png",fullPage:true});
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#conversationRowMenu").isVisible(),false,"Escape must close row context menu before closing the drawer");
  assert.equal(await page.locator("#conversationDrawer").isVisible(),true,"closing row context menu must leave Conversations drawer open");

  // Search uses the real conversations endpoint and has a polished empty state.
  await page.fill("#conversationManagerSearch","Onion");
  await page.waitForFunction(()=>document.querySelectorAll(".conversations-row").length===1&&document.querySelector(".conversations-row-copy strong")?.textContent.includes("Onion"));
  assert.equal((await page.locator(".conversations-row-copy strong").innerText()).trim(),"Onion Cultivation Guide");
  await page.screenshot({path:"artifacts/personal-ai-conversations-search-390x844.png",fullPage:true});
  await page.fill("#conversationManagerSearch","not-a-real-chat");
  await page.waitForFunction(()=>document.querySelector(".conversations-empty-state")?.textContent.includes("No matching conversations"));
  await page.screenshot({path:"artifacts/personal-ai-conversations-search-empty-390x844.png",fullPage:true});
  await page.fill("#conversationManagerSearch","");
  await page.waitForFunction(expected=>document.querySelectorAll(".conversations-row").length===expected,conversations.length);

  // X closes the layered Conversations drawer; it does not reopen the hamburger menu.
  await page.click("#closeDrawer");
  await page.waitForFunction(()=>document.querySelector("#conversationDrawer").classList.contains("hidden"));
  assert.equal(await page.locator("#appDrawer").isVisible(),false,"closing Conversations must leave the underlying app directly visible");

  // Backdrop dismissal uses the same close semantics.
  await page.evaluate(()=>openConversationsDrawer());
  await page.waitForFunction(()=>!document.querySelector("#conversationDrawer").classList.contains("hidden"));
  await page.click("#drawerOverlay",{position:{x:388,y:420}});
  await page.waitForFunction(()=>document.querySelector("#conversationDrawer").classList.contains("hidden"));

  // New chat from this drawer resets historical binding and closes the overlay.
  await page.evaluate(()=>openConversationsDrawer());
  await page.waitForFunction(expected=>document.querySelectorAll(".conversations-row").length===expected,conversations.length);
  await page.click("#newConversation");
  await page.waitForFunction(()=>document.querySelector("#conversationDrawer").classList.contains("hidden")&&document.body.classList.contains("chat-new-empty"));
  assert.equal(await page.evaluate(()=>currentConversationId),"new","Conversations New chat must bind the fresh conversation before its first message");
  assert.equal(await page.locator("#messageStream .message").count(),0,"Conversations New chat must start with an empty message history");
  await page.evaluate(()=>enterHomeLanding());
  await page.waitForFunction(()=>document.body.classList.contains("home-landing"));

  // Existing Timeline remains a separate right-side surface opened by the clock control.
  await page.click("#ownerButton");
  await page.waitForFunction(() => {
    const panel=document.querySelector("#conversationDrawer"),rect=panel.getBoundingClientRect();
    return panel.dataset.mode==="timeline"&&!panel.classList.contains("hidden")&&Math.abs(rect.right-innerWidth)<=1&&rect.left>=-1;
  });
  await page.waitForFunction(() => document.querySelectorAll(".timeline-entry").length >= 10);
  const timelineState=await page.evaluate(()=>({
    filters:[...document.querySelectorAll(".conversation-filter")].map(n=>n.textContent.trim()),
    titles:[...document.querySelectorAll(".timeline-title")].map(n=>n.textContent.trim()),
    categories:[...document.querySelectorAll(".timeline-entry")].map(n=>n.dataset.category),
    clocks:[...document.querySelectorAll(".timeline-clock")].map(n=>new Date(n.dateTime).getTime()),
    rect:document.querySelector("#conversationDrawer").getBoundingClientRect(),
    width:innerWidth,cssRight:getComputedStyle(document.querySelector("#conversationDrawer")).right,
    dateHeaders:[...document.querySelectorAll(".timeline-day")].map(n=>({text:n.textContent.trim(),rect:n.getBoundingClientRect()})),
    cards:[...document.querySelectorAll(".timeline-content")].map(n=>n.getBoundingClientRect()),
    icons:[...document.querySelectorAll(".timeline-event-icon")].map(n=>n.getBoundingClientRect()),
    nodes:[...document.querySelectorAll(".timeline-dot")].map(n=>n.getBoundingClientRect()),
    statuses:[...document.querySelectorAll(".timeline-status")].map(n=>n.textContent.trim()),
    summaryParts:document.querySelectorAll(".timeline-count-part").length,
    activeFilterBackground:getComputedStyle(document.querySelector(".conversation-filter.active")).backgroundImage,
    railBackground:getComputedStyle(document.querySelector(".timeline-entry"),"::before").backgroundImage,
  }));
  assert.deepEqual(timelineState.filters,["All","Recent","Chats","Meetings","Tasks","Activity","Needs attention"],"Timeline must expose all seven working filter tabs");
  assert.ok(timelineState.titles.includes("Complete weekly report"),"completed work must show recorded completion time");
  assert.ok(timelineState.titles.includes("Team planning meeting"),"real saved meetings must appear");
  assert.ok(timelineState.titles.includes("Prepare client proposal"),"work/plan events must remain visible in All without a separate legacy filter");
  assert.ok(timelineState.titles.includes("Send follow-up"),"reminder events must remain visible in All without a separate legacy filter");
  assert.ok(timelineState.titles.includes("Morning operations"),"workflow events must remain visible in All without a separate legacy filter");
  assert.ok(timelineState.titles.includes("Workflow Run Finished"),"audited activity must remain visible in All without a separate legacy filter");
  assert.ok(timelineState.categories.includes("activity"),"authorized audit events must appear without fabrication");
  assert.ok(timelineState.clocks.every((stamp,i,a)=>i===0||a[i-1]>=stamp),"mixed records must sort chronologically");
  assert.ok(Math.abs(timelineState.rect.right-timelineState.width)<=1&&timelineState.rect.left>=-1,"mobile Timeline must fill the right-aligned viewport");
  assert.equal(timelineState.cssRight,"0px");
  assert.ok((await page.locator("#conversationCount").innerText()).includes("pending"));
  assert.equal(timelineState.summaryParts,3,"Timeline summary must expose entries, pending and done semantic groups");
  assert.ok(timelineState.activeFilterBackground.includes("linear-gradient"),"active Timeline filter must use the approved blue pill");
  assert.ok(timelineState.railBackground.includes("linear-gradient"),"Timeline rail must use the approved subtle blue gradient");
  assert.ok(timelineState.dateHeaders.length>=1&&timelineState.dateHeaders.every(item=>item.rect.height>=38&&item.rect.height<=50),"date headers must stay slim and rounded");
  assert.ok(timelineState.cards.every(card=>card.height>=100&&card.height<=150),"event cards must stay premium but information-dense");
  assert.ok(timelineState.icons.every(icon=>icon.width>=40&&icon.width<=48&&icon.height>=40&&icon.height<=48),"event icons must use the shared compact visual scale");
  assert.ok(timelineState.nodes.every(node=>node.width>=8&&node.width<=12),"timeline nodes must remain subtle and precisely sized");
  assert.ok(timelineState.statuses.includes("Completed")&&timelineState.statuses.includes("Updated"),"Timeline must render human-readable semantic status chips");
  assert.ok((await page.locator('.timeline-entry[data-status="done"]').count())>=2);
  assert.ok(await page.locator("#timelineAddPlan").isVisible(),"right Timeline must keep existing planning functionality");
  assert.deepEqual(await page.evaluate(()=>auditTimelinePresentation({label:"Model",kind:"model",action:"selected"})),{title:"Model selected",preview:"Vishnu model selection updated"},"generic Model selected audit events must be humanized without fabricating hidden data");
  await page.screenshot({path:"artifacts/personal-ai-timeline-approved-all-390x844.png",fullPage:true});
  const yesterdayHeading=page.locator(".timeline-day",{hasText:"Yesterday"}).first();
  assert.ok(await yesterdayHeading.count(),"Timeline fixture must expose a Yesterday section for date-group qualification");
  await yesterdayHeading.scrollIntoViewIfNeeded();
  await page.screenshot({path:"artifacts/personal-ai-timeline-today-yesterday-390x844.png",fullPage:true});
  await page.locator("#conversationList").evaluate(node=>{node.scrollTop=0});

  await page.locator('[data-conversation-filter="recent"]').click();
  await page.screenshot({path:"artifacts/personal-ai-timeline-filter-recent-390x844.png",fullPage:true});
  await page.locator('[data-conversation-filter="meeting"]').click();
  assert.ok((await page.locator(".timeline-title").allTextContents()).includes("Team planning meeting"),"meeting filter must retain canonical persisted meeting records");
  await page.locator('.timeline-entry[data-category="meeting"] .timeline-title').last().click();
  assert.equal(await page.locator('#timelineRecordTitle').innerText(),"Team planning meeting","meeting rows must open their saved details in the Timeline detail view");
  assert.match(new URL(page.url()).hash,/^#meeting\//,"meeting details must have an addressable in-app detail route");
  assert.ok((await page.locator('#timelineRecordContent').innerText()).includes("Scheduled"),"meeting details must show their saved scheduled time");
  await page.locator('#timelineRecordClose').click();
  await page.waitForFunction(()=>location.hash==='');
  await page.screenshot({path:"artifacts/personal-ai-timeline-filter-meetings-390x844.png",fullPage:true});
  await page.locator('[data-conversation-filter="task"]').click();
  assert.ok((await page.locator(".timeline-title").allTextContents()).includes("Finish daily review"),"Tasks filter must isolate actual task events");
  await page.locator('.timeline-entry[data-category="task"] .timeline-title').first().click();
  assert.equal(await page.locator('#timelineRecordTitle').innerText(),"Complete weekly report","task rows must open the currently saved task details in the Timeline detail view");
  assert.match(new URL(page.url()).hash,/^#task\//,"task details must have an addressable in-app detail route");
  await page.locator('#timelineRecordClose').click();
  await page.waitForFunction(()=>location.hash==='');
  await page.screenshot({path:"artifacts/personal-ai-timeline-filter-tasks-390x844.png",fullPage:true});
  await page.locator('[data-conversation-filter="conversation"]').click();
  assert.deepEqual(await page.locator(".timeline-title").allTextContents(),conversations.map(x=>x.title));
  await page.screenshot({path:"artifacts/personal-ai-timeline-filter-chats-390x844.png",fullPage:true});
  await page.locator('[data-conversation-filter="all"]').click();
  await page.fill("#conversationSearch","Onion");
  await page.waitForFunction(()=>document.querySelectorAll(".timeline-entry").length===1&&document.querySelector(".timeline-title").textContent.includes("Onion"));
  assert.match(await page.locator("#conversationCount").innerText(),/\d+ entries/,"Timeline summary must retain its overall entry count while search narrows visible results");
  await page.screenshot({path:"artifacts/personal-ai-timeline-search-results-390x844.png",fullPage:true});
  await page.locator('[data-conversation-filter="recent"]').click();
  assert.equal(await page.locator('[data-conversation-filter="recent"]').getAttribute("aria-pressed"),"true");
  assert.ok((await page.locator(".timeline-title").allTextContents()).includes("Onion Cultivation Guide"),"Recent must preserve cross-category search results");
  await page.locator('[data-conversation-filter="attention"]').click();
  assert.equal(await page.locator('[data-conversation-filter="attention"]').getAttribute("aria-pressed"),"true");
  assert.equal(await page.locator('.timeline-entry').evaluateAll(nodes=>nodes.every(node=>['pending','overdue','error','running'].includes(node.dataset.status))),true,"Needs attention must exclude completed and informational entries");
  await page.locator('[data-conversation-filter="all"]').click();
  await page.fill("#conversationSearch","weekly report");
  await page.waitForFunction(()=>document.querySelectorAll(".timeline-entry").length===1&&document.querySelector(".timeline-title").textContent.includes("Complete weekly report"));
  await page.fill("#conversationSearch","nonexistent title");
  await page.waitForFunction(()=>document.querySelectorAll(".timeline-entry").length===0&&document.querySelector(".timeline-empty")?.textContent.includes("No results for"));
  await page.screenshot({path:"artifacts/personal-ai-timeline-search-empty-390x844.png",fullPage:true});

  await page.fill("#conversationSearch","");
  await page.waitForFunction(()=>document.querySelectorAll(".timeline-entry").length>=10);

  await page.evaluate(()=>{timelineLoaded=false;renderUnifiedTimeline()});
  assert.ok(await page.locator(".timeline-loading-entry").count()>=4,"Timeline loading state must use structured skeleton rows");
  await page.screenshot({path:"artifacts/personal-ai-timeline-loading-390x844.png",fullPage:true});
  await page.evaluate(()=>refreshUnifiedTimeline(''));
  await page.waitForFunction(()=>document.querySelectorAll(".timeline-entry").length>=10);

  await page.evaluate(()=>{timelineLoaded=true;timelineAvailable={conversations:false,plans:false,activity:false,workflows:false};conversationManagerResults=[];timelineItems=[];timelineAudit=[];timelineRuns=[];renderUnifiedTimeline()});
  assert.ok((await page.locator(".timeline-empty").innerText()).includes("Unable to load timeline"),"Timeline full-source failure must render an explicit retryable error state");
  await page.screenshot({path:"artifacts/personal-ai-timeline-error-390x844.png",fullPage:true});
  await page.evaluate(()=>refreshUnifiedTimeline(''));
  await page.waitForFunction(()=>document.querySelectorAll(".timeline-entry").length>=10);

  await page.evaluate(()=>{conversationManagerResults=[];timelineItems=[];timelineAudit=[];timelineRuns=[];timelineAvailable={conversations:true,plans:true,activity:true,workflows:true};timelineLoaded=true;conversationFilter='all';renderUnifiedTimeline()});
  assert.ok((await page.locator(".timeline-empty").innerText()).includes("No timeline activity yet"),"Timeline must render a calm true-empty state without mock events");
  await page.screenshot({path:"artifacts/personal-ai-timeline-empty-390x844.png",fullPage:true});
  await page.evaluate(()=>refreshUnifiedTimeline(''));
  await page.waitForFunction(()=>document.querySelectorAll(".timeline-entry").length>=10);

  await page.locator('[data-conversation-filter="meeting"]').click();
  await page.evaluate(()=>{timelineItems=timelineItems.filter(item=>!String(item.context||'').includes(':meeting'));renderUnifiedTimeline()});
  assert.ok((await page.locator(".timeline-empty").innerText()).includes("No meetings found"),"empty category state must name the active filter");
  await page.screenshot({path:"artifacts/personal-ai-timeline-filter-empty-390x844.png",fullPage:true});
  await page.evaluate(()=>refreshUnifiedTimeline(''));
  await page.locator('[data-conversation-filter="all"]').click();
  await page.waitForFunction(()=>document.querySelectorAll(".timeline-entry").length>=10);

  await page.evaluate(()=>{
    window.__timelineVisualBackup={title:conversationCache[0].title,preview:conversationCache[0].preview};
    conversationCache[0].title='A very long Vishnu conversation title that must truncate cleanly inside the approved premium Timeline card';
    conversationCache[0].preview='This is an intentionally long real-data-style preview used only by the browser acceptance fixture to verify single-line truncation without changing production content.';
    renderUnifiedTimeline();
  });
  await page.screenshot({path:"artifacts/personal-ai-timeline-long-title-preview-390x844.png",fullPage:true});
  await page.evaluate(()=>{conversationCache[0].title=window.__timelineVisualBackup.title;conversationCache[0].preview=window.__timelineVisualBackup.preview;delete window.__timelineVisualBackup;renderUnifiedTimeline()});
  await page.locator('[data-conversation-filter="all"]').click();
  await page.locator('.timeline-entry[data-category="work"] .timeline-event-menu-button').click();
  await page.waitForFunction(()=>!document.querySelector("#timelineEventMenu").classList.contains("hidden"));
  assert.ok((await page.locator("#timelineEventMenu").innerText()).includes("Mark complete"),"pending work menu must expose the existing completion action");
  await page.screenshot({path:"artifacts/personal-ai-timeline-context-menu-390x844.png",fullPage:true});
  await page.getByRole('menuitem',{name:'Mark complete'}).click();
  await page.waitForFunction(()=>document.querySelector('.timeline-entry[data-category="work"]')?.dataset.status==="done");
  assert.ok((await page.locator(".timeline-title").allTextContents()).includes("Prepare client proposal"),"Mark complete must preserve the plan event in the approved All view");
  allowActivity=false;
  await page.evaluate(()=>refreshUnifiedTimeline(''));
  await page.waitForFunction(()=>document.querySelector(".timeline-notice")?.textContent.includes("not permitted"));
  assert.equal(await page.locator('.timeline-entry[data-category="activity"]').count(),0,"restricted audited activity must not leak");
  allowActivity=true;
  await page.evaluate(()=>refreshUnifiedTimeline(''));
  await page.waitForFunction(()=>document.querySelector('.timeline-entry[data-category="activity"]'));
  await page.screenshot({path:"artifacts/personal-ai-unified-timeline-filtered-390x844.png",fullPage:true});

  await page.click("#timelineAddPlan");
  await page.waitForFunction(()=>document.querySelector("#todayDialog")?.open===true);
  await page.screenshot({path:"artifacts/personal-ai-timeline-add-to-plan-390x844.png",fullPage:true});
  await page.click("#todayCancel");
  await page.click("#ownerButton");
  await page.waitForFunction(()=>document.querySelector("#conversationDrawer").dataset.mode==="timeline"&&!document.querySelector("#conversationDrawer").classList.contains("hidden"));
  await page.waitForFunction(()=>document.querySelectorAll(".timeline-entry").length>=10);

  // Open a real persisted conversation from the preserved Timeline to continue chat qualification.
  await page.locator('[data-conversation-filter="conversation"]').click();
  const actualTimelineConversation=page.locator(".timeline-entry[data-category=conversation] .timeline-title").first();
  await actualTimelineConversation.evaluate(button=>button.click());
  await page.waitForFunction(() => !document.body.classList.contains("home-landing"));
  await page.waitForFunction(() => document.querySelectorAll("#messageStream .message").length >= 2);
  await page.click("#ownerButton");
  await page.waitForFunction(()=>document.querySelector("#conversationDrawer").dataset.mode==="timeline"&&!document.querySelector("#conversationDrawer").classList.contains("hidden"));
  await page.screenshot({path:"artifacts/personal-ai-timeline-from-chat-390x844.png",fullPage:true});
  await page.click("#timelineCloseDrawer");
  await page.waitForFunction(()=>document.querySelector("#conversationDrawer").classList.contains("hidden"));
  const chatState = await page.evaluate(() => ({
    coreVisibility: getComputedStyle(document.querySelector(".core-stage")).visibility,
    messageCount: document.querySelectorAll("#messageStream .message").length,
    messages: document.querySelector("#messageStream").getBoundingClientRect(),
    composer: document.querySelector("#composer").getBoundingClientRect(),
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth,
    innerHeight,
  }));
  assert.equal(chatState.coreVisibility, "visible", "compact original sphere remains visible in the header while chatting");
  assert.equal(await page.locator(".state").isVisible(), false, "the approved Chat header has no ACTIVE status label");
  
  assert.equal(await page.locator("#status").isVisible(),false,"idle ACTIVE status must stay visually minimal without redundant helper copy");
  assert.equal(chatState.messageCount, 2);
  assert.equal(await page.locator(".message-time").count(),2,"every persisted message must render its canonical timestamp");
  assert.deepEqual(await page.locator(".message-time").evaluateAll(nodes=>nodes.map(node=>node.dateTime)),activeConversation.events.map(event=>event.created_at),"DOM timestamps must come from persisted event creation time");
  assert.equal(await page.locator(".date-separator").count(),2,"calendar-date changes must create one subtle separator per day");
  assert.equal(await page.locator(".message-entry.assistant .message-avatar").count(),0,"assistant messages stay open without avatar circles");
  assert.equal(await page.locator(".message-entry.assistant ol li").count(),3,"numbered Markdown must render structurally");
  assert.equal(await page.locator(".message-entry.assistant code").count(),1,"inline code must render structurally");
  const messageVisual=await page.evaluate(()=>({
    assistantBackground:getComputedStyle(document.querySelector(".message.assistant")).backgroundColor,
    assistantBorder:getComputedStyle(document.querySelector(".message.assistant")).borderTopWidth,
    user:document.querySelector(".message.user").getBoundingClientRect(),
    stream:document.querySelector("#messageStream").getBoundingClientRect(),
  }));
  assert.equal(messageVisual.assistantBackground,"rgba(0, 0, 0, 0)","AI responses must use an open transparent surface instead of a boxed card");
  assert.equal(messageVisual.assistantBorder,"0px","AI responses must not retain the old card border");
  assert.ok(messageVisual.user.right>=messageVisual.stream.right-8,"owner bubble must align to the right edge");
  assert.ok(messageVisual.user.width<=messageVisual.stream.width*.83,"owner bubble must remain compact rather than becoming a full-width card");
  assert.equal(await page.locator(".message-entry.user .message-actions button").count(),2,"user messages expose copy and edit");
  assert.equal(await page.locator(".message-entry.assistant .message-actions button").count(),7,"assistant actions show copy, like, dislike, read, share, minimize and maximize");
  assert.equal(await page.locator('.message-entry.assistant [aria-label="Like response"]').getAttribute("aria-pressed"),"false");
  await page.locator('.message-entry.assistant [aria-label="Like response"]').click();
  assert.equal(await page.locator('.message-entry.assistant [aria-label="Like response"]').getAttribute("aria-pressed"),"true","positive feedback has selected visual state");
  await page.locator('.message-entry.assistant [aria-label="Dislike response"]').click();
  assert.equal(await page.locator('.message-entry.assistant [aria-label="Like response"]').getAttribute("aria-pressed"),"false","negative feedback deselects positive feedback");
  assert.equal(await page.locator('.message-entry.assistant [aria-label="Dislike response"]').getAttribute("aria-pressed"),"true");

  assert.ok(chatState.messages.height > 0, "active conversation needs a real scroll viewport");
  assert.ok(chatState.composer.bottom <= chatState.innerHeight + 1, "chat composer must remain visible");
  assert.ok(chatState.scrollWidth <= chatState.innerWidth, "active conversation must not overflow horizontally");
  assert.equal(await page.locator("#chatMenuButton").isVisible(), true, "three-dot menu must appear after loading a real conversation");
  const headerButtons=await page.evaluate(()=>({
    more:document.querySelector("#chatMenuButton").getBoundingClientRect(),
    timeline:document.querySelector("#ownerButton").getBoundingClientRect(),
  }));
  assert.ok(headerButtons.more.right <= headerButtons.timeline.left+1, "conversation menu must sit LEFT of the right-side timeline button");
  assert.ok(headerButtons.more.width>=44&&headerButtons.more.height>=44, "conversation menu must retain accessible touch target");
  await page.click("#chatMenuButton");
  assert.equal(await page.locator("#chatActionMenu").isVisible(),true,"three-dot menu must open");
  assert.deepEqual(await page.locator("#chatActionMenu [role=menuitem]").allTextContents(),
    ["ⓘChat details","✎Rename","↗Share transcript","⧉Copy transcript","↓Download JSON","⌫Delete conversation"],"conversation menu must expose only connected actions");
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#chatActionMenu").isVisible(),false,"Escape must close the conversation menu");
  await page.click("#chatMenuButton");
  await page.click("#chatRename");
  await page.fill("#actionDialogInput","Mushroom Session Notes");await page.click("#actionDialogSubmit");
  await page.waitForFunction(()=>document.querySelector("#conversationTitle").textContent==="Mushroom Session Notes");
  assert.equal(conversations[0].title,"Mushroom Session Notes","rename must call the real conversation API");
  await page.evaluate(()=>{
    Object.defineProperty(navigator,"clipboard",{configurable:true,value:{writeText:async text=>{window.__copiedTranscript=text}}});
    Object.defineProperty(navigator,"share",{configurable:true,value:async data=>{window.__sharedTranscript=data}});
  });
  await page.click("#chatMenuButton");
  await page.click("#chatCopy");
  await page.waitForFunction(()=>Boolean(window.__copiedTranscript));
  assert.ok((await page.evaluate(()=>window.__copiedTranscript)).includes("Plan mushroom farm shed"),"copy must use the real transcript");
  await page.click("#chatMenuButton");
  await page.click("#chatShare");
  await page.waitForFunction(()=>Boolean(window.__sharedTranscript));
  assert.ok((await page.evaluate(()=>window.__sharedTranscript.text)).includes("Plan mushroom farm shed"),"share must send transcript text, not manufacture a public link");
  await page.click("#chatMenuButton");
  const exportDownload=page.waitForEvent("download");
  await page.click("#chatExport");
  await exportDownload;
  assert.deepEqual(exportedConversationIds,["c1"],"download must request the authenticated canonical export");
  await page.evaluate(()=>{messageReactions.clear();renderMessages();setState('idle');document.querySelector('#toast')?.classList.add('hidden')});
  await page.screenshot({ path: "artifacts/personal-ai-chat-390x844.png", fullPage: true });
  await page.screenshot({ path: "artifacts/personal-ai-chat-date-separated-390x844.png", fullPage: true });

  const assistantCountBeforeLongResponse=await page.locator(".message-entry.assistant").count();
  await page.evaluate(()=>{
    conversationEvents.push({
      event_id:"visual-long-response",kind:"assistant_message",created_at:new Date().toISOString(),
      payload:{text:"## Detailed plan\n\nThis is a deliberately long Vishnu response used to verify that open assistant content stays readable and wide without being forced into a phone-chat bubble.\n\n- Preserve the original neural sphere\n- Keep the composer visible above the safe area\n- Keep actions close to the response\n\n```text\nLong content remains inside the same response block.\nNo token-sized bubbles are created.\n```\n\n| Check | Result |\n| --- | --- |\n| Wrapping | Correct |\n| Overflow | None |"}
    });renderMessages();
  });
  await page.waitForFunction(expected=>document.querySelectorAll(".message-entry.assistant").length===expected,assistantCountBeforeLongResponse+1);
  assert.ok(await page.locator(".message-entry.assistant").last().locator("pre code").isVisible(),"long response code block must remain readable");
  assert.ok(await page.locator(".message-entry.assistant").last().locator("table").isVisible(),"long response Markdown table must render");
  await page.evaluate(()=>{setState('idle');document.querySelector('#toast')?.classList.add('hidden')});
  await page.screenshot({ path: "artifacts/personal-ai-chat-long-response-390x844.png", fullPage: true });

  await page.evaluate(()=>openConversation("c1"));
  await page.waitForFunction(()=>document.querySelectorAll("#messageStream .message").length===2);
  const persistedTimesBeforeRefresh=await page.locator(".message-time").evaluateAll(nodes=>nodes.map(node=>({dateTime:node.dateTime,text:node.textContent})));
  await page.reload({waitUntil:"domcontentloaded"});
  await page.waitForFunction(()=>document.body.classList.contains("home-landing"));
  assert.equal(await page.evaluate(()=>currentConversationId),"c1","refresh should preserve the canonical conversation binding while returning to Home");
  await page.evaluate(()=>openConversation("c1"));
  await page.waitForFunction(()=>document.querySelectorAll("#messageStream .message").length===2);
  const persistedTimesAfterRefresh=await page.locator(".message-time").evaluateAll(nodes=>nodes.map(node=>({dateTime:node.dateTime,text:node.textContent})));
  assert.deepEqual(persistedTimesAfterRefresh,persistedTimesBeforeRefresh,"refresh must preserve original canonical message timestamps");
  await page.screenshot({ path: "artifacts/personal-ai-chat-after-refresh-390x844.png", fullPage: true });

  const viewports = [
    [320, 568], [360, 780], [375, 812], [390, 844],
    [393, 852], [402, 874], [414, 896], [430, 932], [600, 900],
    [768, 1024], [820, 1180], [1024, 768],
  ];
  const responsiveScreenshots = new Map([
    [320, "personal-ai-phone-small-320x568.png"],
    [390, "personal-ai-phone-standard-390x844.png"],
    [768, "personal-ai-tablet-portrait-768x1024.png"],
    [1024, "personal-ai-tablet-landscape-1024x768.png"],
    [1366, "personal-ai-desktop-1366x768.png"],
    [1920, "personal-ai-wide-desktop-1920x1080.png"],
  ]);
  for (const [width, height] of viewports) {
    await page.setViewportSize({ width, height });
    await page.evaluate(() => enterHomeLanding());
    await page.waitForTimeout(180);
    const layout = await page.evaluate(() => {
      const rect = selector => {
        const node = document.querySelector(selector);
        const r = node.getBoundingClientRect();
        return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, width: r.width, height: r.height };
      };
      const canvas = document.querySelector("#neuralCanvas");
      const pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
      let sphereInk = 0;
      for (let i = 0; i < pixels.length; i += 4) {
        if (pixels[i + 3] > 12 && (pixels[i] > 80 || pixels[i + 1] > 100 || pixels[i + 2] > 150)) sphereInk++;
      }
      return {
        sphereInk,
        viewportWidth: innerWidth,
        viewportHeight: innerHeight,
        documentWidth: document.documentElement.scrollWidth,
        core: rect(".core-stage"),
        composer: rect("#composer"),
        header: rect(".topbar"),
        quick: rect(".v-shortcuts"),
        home: rect(".home-intro"),
        cards: [...document.querySelectorAll(".v-shortcuts .v-card")].map(node => {const r=node.getBoundingClientRect();return {width:r.width,height:r.height,scrollHeight:node.scrollHeight,clientHeight:node.clientHeight}}),
        controls: ["#attachmentButton","#sendButton","#micButton"].map(selector => rect(selector)),
      };
    });
    assert.ok(layout.documentWidth <= layout.viewportWidth, "horizontal overflow at " + width + "x" + height);
    assert.ok(layout.core.width > 0 && layout.core.height > 0, "sphere missing at " + width + "x" + height);
    assert.ok(layout.sphereInk > 90, "mini sphere animation did not repaint after chat at " + width + "x" + height);
    assert.ok(layout.composer.bottom <= layout.viewportHeight + 1, "composer clipped at " + width + "x" + height);
    assertSharedComposerBottomInset(layout.composer.bottom,layout.viewportHeight,"Home composer at "+width+"x"+height);
    const fixedPositions=await page.evaluate(()=>({
      header:getComputedStyle(document.querySelector(".topbar")).position,
      composer:getComputedStyle(document.querySelector("#composer")).position
    }));
    assert.equal(fixedPositions.header,"fixed","Home topbar must stay fixed at "+width+"x"+height);
    assert.equal(fixedPositions.composer,"fixed","Home composer must stay fixed at "+width+"x"+height);
    assert.ok(layout.header.left >= -1 && layout.header.right <= layout.viewportWidth + 1, "header clipped at " + width + "x" + height);
    const edgeControls=await page.evaluate(()=>({
      header:document.querySelector(".topbar").getBoundingClientRect(),
      left:document.querySelector("#historyButton").getBoundingClientRect(),
      right:document.querySelector("#ownerButton").getBoundingClientRect()
    }));
    if(width<=600){
      assert.ok(Math.abs(edgeControls.left.left-edgeControls.header.left)<=1,"hamburger gained extra left inset at "+width+"x"+height);
      assert.ok(Math.abs(edgeControls.right.right-edgeControls.header.right)<=1,"Timeline control gained extra right inset at "+width+"x"+height);
    }else{
      assert.ok(edgeControls.left.left>=edgeControls.header.left-1&&edgeControls.right.right<=edgeControls.header.right+1,"header controls must stay inside the tablet/desktop header at "+width+"x"+height);
    }
    if (responsiveScreenshots.has(width)) {
      await page.screenshot({ path: "artifacts/" + responsiveScreenshots.get(width), fullPage: true });
    }
    assert.ok(layout.quick.left >= -1 && layout.quick.right <= layout.viewportWidth + 1, "quick actions clipped at " + width + "x" + height);
    assert.ok(layout.cards.length === 4, "four Home cards required");
    assert.ok(layout.cards.every(card => Math.abs(card.height-layout.cards[0].height)<1 && Math.abs(card.width-layout.cards[0].width)<1), "Home card dimensions mismatch at " + width + "x" + height);
    assert.ok(layout.cards.every(card => card.scrollHeight<=card.clientHeight+2), "Home card content clipped at " + width + "x" + height);
    assert.ok(layout.cards.every(card => card.height>=58&&card.height<=Math.max(240,layout.viewportHeight*.5)), "Home cards lost approved responsive proportions at " + width + "x" + height);
    if(width<=600)assert.ok(Math.abs(layout.composer.width-layout.home.width)<=4, "Home composer must share the same outer grid at " + width + "x" + height);
    assert.ok(layout.composer.left>=-1 && layout.composer.right<=layout.viewportWidth+1, "composer clips horizontally at " + width + "x" + height);
    assert.ok(layout.controls.filter(control => control.width>0).every(control => control.width>=43 && control.height>=43), "composer action hit targets too small at " + width + "x" + height);
    assert.ok(layout.composer.height>=52 && layout.composer.height<=60, "idle Home composer height drifted from the approved design at " + width + "x" + height);
    if (width === 320) {
      await page.screenshot({ path: "artifacts/personal-ai-home-320x568.png", fullPage: true });
      await page.click("#historyButton");
      await page.waitForFunction(() => document.querySelector("#appDrawer").getBoundingClientRect().left >= -1);
      const narrowSidebar = await page.evaluate(() => ({
        screenWidth:innerWidth, screenHeight:innerHeight,
        aside:document.querySelector("#appDrawer").getBoundingClientRect(),
        footer:document.querySelector("#sidebarAccountButton").getBoundingClientRect(),
        newChat:document.querySelector("#sidebarNewChat").getBoundingClientRect(),
      }));
      assert.ok(narrowSidebar.aside.left >= -1 && narrowSidebar.aside.right <= narrowSidebar.screenWidth + 1, "sidebar must not clip at 320px");
      assert.ok(narrowSidebar.footer.bottom <= narrowSidebar.screenHeight + 1, "account footer must remain accessible at 320x568");
      assert.ok(narrowSidebar.newChat.height >= 44, "new chat must preserve touch target on narrow screens");
      await page.screenshot({ path: "artifacts/personal-ai-sidebar-320x568.png", fullPage: true });
      await page.click("#closeAppDrawer");
      await page.evaluate(()=>openConversationsDrawer());
      await page.waitForFunction(expected=>document.querySelectorAll(".conversations-row").length===expected,conversations.length);
      await page.waitForFunction(()=>document.querySelector("#conversationDrawer").getBoundingClientRect().left>=-1);
      const conversations320=await page.evaluate(()=>({
        width:innerWidth,
        drawer:document.querySelector("#conversationDrawer").getBoundingClientRect(),
        close:document.querySelector("#closeDrawer").getBoundingClientRect(),
        search:document.querySelector("#conversationManagerSearch").closest(".conversations-search-wrap").getBoundingClientRect(),
        rows:[...document.querySelectorAll(".conversations-row")].map(node=>node.getBoundingClientRect())
      }));
      assert.ok(conversations320.drawer.left>=-1&&conversations320.drawer.right<conversations320.width,"320px Conversations drawer must leave a visible backdrop strip on the right");
      assert.ok(conversations320.close.width>=44&&conversations320.search.width>220,"320px Conversations controls must remain usable");
      assert.ok(conversations320.rows.every(row=>row.right<=conversations320.drawer.right+1),"320px conversation rows must not clip horizontally");
      await page.screenshot({ path: "artifacts/personal-ai-conversations-approved-320x568.png", fullPage: true });
      await page.click("#closeDrawer");
      await page.click("#ownerButton");
      await page.waitForFunction(() => {
        const r=document.querySelector("#conversationDrawer").getBoundingClientRect();
        return document.querySelector("#conversationDrawer").dataset.mode==="timeline"&&r.left>=0&&Math.abs(r.right-innerWidth)<=1;
      });
      const right320=await page.evaluate(()=>({
        width:innerWidth,
        drawer:document.querySelector("#conversationDrawer").getBoundingClientRect(),
        back:document.querySelector("#timelineBackDrawer").getBoundingClientRect(),
        close:document.querySelector("#timelineCloseDrawer").getBoundingClientRect(),
        search:document.querySelector("#conversationSearch").getBoundingClientRect(),
        cards:[...document.querySelectorAll(".timeline-content")].map(node=>node.getBoundingClientRect())
      }));
      assert.ok(right320.drawer.left>=0&&right320.drawer.right<=right320.width+1,"right Timeline must not clip at 320px");
      assert.ok(right320.back.width>=42&&right320.close.width>=42&&right320.search.width>180,"right Timeline controls must remain usable at 320px");
      await page.waitForFunction(()=>document.querySelectorAll(".timeline-entry").length>=10);
      assert.ok(right320.cards.every(card=>card.right<=right320.drawer.right+1),"Timeline cards must never clip horizontally at 320px");
      const filters320=await page.locator(".conversation-filters").evaluate(node=>({scroll:node.scrollWidth,width:node.clientWidth,overflow:getComputedStyle(node).overflowX}));
      assert.ok(filters320.scroll>=filters320.width&&filters320.overflow==="auto","approved Timeline filters must stay in one horizontal, scroll-safe row at 320px");
      await page.screenshot({ path: "artifacts/personal-ai-timeline-right-320x568.png", fullPage: true });
      await page.click("#timelineCloseDrawer");
    }
    if (![320,430].includes(width) && await page.locator("#ownerButton").isVisible()) {
      await page.click("#ownerButton");
      await page.waitForFunction(()=>document.querySelector("#conversationDrawer").dataset.mode==="timeline"&&!document.querySelector("#conversationDrawer").classList.contains("hidden"));
      await page.waitForFunction(()=>{const r=document.querySelector("#conversationDrawer").getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1});
      const timelineViewport=await page.evaluate(()=>({drawer:document.querySelector("#conversationDrawer").getBoundingClientRect(),width:innerWidth,doc:document.documentElement.scrollWidth}));
      assert.ok(timelineViewport.drawer.left>=0&&timelineViewport.drawer.right<=timelineViewport.width+1,"Timeline must fit viewport at "+width+"x"+height);
      assert.ok(timelineViewport.doc<=timelineViewport.width,"Timeline must not introduce horizontal overflow at "+width+"x"+height);
      await page.click("#timelineCloseDrawer");
      await page.waitForFunction(()=>document.querySelector("#conversationDrawer").classList.contains("hidden"));
    }
    if (width === 430) {
      await page.screenshot({ path: "artifacts/personal-ai-home-430x932.png", fullPage: true });
      await page.click("#ownerButton");
      await page.waitForFunction(()=>document.querySelector("#conversationDrawer").dataset.mode==="timeline"&&!document.querySelector("#conversationDrawer").classList.contains("hidden"));
      await page.screenshot({path:"artifacts/personal-ai-timeline-approved-large-iphone-430x932.png",fullPage:true});
      await page.click("#timelineCloseDrawer");
      await page.waitForFunction(()=>document.querySelector("#conversationDrawer").classList.contains("hidden"));
      await page.click("#historyButton");
      assert.ok(await page.locator("#sidebarAccountButton").isVisible());
      await page.screenshot({ path: "artifacts/personal-ai-sidebar-430x932.png", fullPage: true });
      await page.click("#closeAppDrawer");
    }
  }

  // Tablet and desktop must keep the approved Home composition centered rather than stretching edge-to-edge.
  const wideViewports=[[768,1024],[820,1180],[1024,768],[1024,900],[1280,900],[1366,768],[1440,1000],[1920,1080],[2560,1440]];
  for(const [width,height] of wideViewports){
    await page.setViewportSize({width,height});
    await page.evaluate(()=>enterHomeLanding());
    await page.waitForTimeout(150);
    const wide=await page.evaluate(()=>({
      doc:document.documentElement.scrollWidth,
      inner:innerWidth,
      home:document.querySelector(".home-intro").getBoundingClientRect(),
      header:document.querySelector(".topbar").getBoundingClientRect(),
      composer:document.querySelector("#composer").getBoundingClientRect(),
      quick:[...document.querySelectorAll(".v-shortcuts .v-card")].map(node=>node.getBoundingClientRect()),
    }));
    assert.ok(wide.doc<=wide.inner,"wide Home must not horizontally overflow at "+width+"x"+height);
    assertSharedComposerBottomInset(wide.composer.bottom,height,"wide Home composer at "+width+"x"+height);
    const wideFixed=await page.evaluate(()=>({
      header:getComputedStyle(document.querySelector(".topbar")).position,
      composer:getComputedStyle(document.querySelector("#composer")).position
    }));
    assert.equal(wideFixed.header,"fixed","wide Home topbar must remain fixed at "+width+"x"+height);
    assert.equal(wideFixed.composer,"fixed","wide Home composer must remain fixed at "+width+"x"+height);
    if(width>=1024){
      assert.ok(wide.home.width<=1000&&wide.header.width<=1000&&wide.composer.width<=1000,"Desktop Home content must remain within its 1000px design max width at "+width+"x"+height);
      assert.ok(Math.abs(wide.home.left-(wide.inner-wide.home.width)/2)<=2,"Desktop Home content must remain centered at "+width+"x"+height);
    } else {
      assert.ok(wide.home.left>=0&&wide.home.right<=wide.inner+1&&wide.header.left>=0&&wide.header.right<=wide.inner+1&&wide.composer.left>=0&&wide.composer.right<=wide.inner+1,"Tablet Home regions must remain inside the viewport at "+width+"x"+height);
    }
    assert.ok(wide.quick.every(card=>card.width<wide.home.width*.52),"2x2 shortcut grid must stay proportionate at "+width+"x"+height);
    if(width===768)await page.screenshot({path:"artifacts/personal-ai-home-tablet-768x1024.png",fullPage:true});
    if(width===1440)await page.screenshot({path:"artifacts/personal-ai-home-desktop-1440x1000.png",fullPage:true});
    if(width===2560)await page.screenshot({path:"artifacts/personal-ai-home-wide-2560x1440.png",fullPage:true});
    if (await page.locator("#ownerButton").isVisible()) {
      await page.click("#ownerButton");
      await page.waitForFunction(()=>document.querySelector("#conversationDrawer").dataset.mode==="timeline"&&!document.querySelector("#conversationDrawer").classList.contains("hidden"));
      await page.waitForFunction(()=>{const r=document.querySelector("#conversationDrawer").getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1});
      const timelineWide=await page.evaluate(()=>({drawer:document.querySelector("#conversationDrawer").getBoundingClientRect(),width:innerWidth,doc:document.documentElement.scrollWidth}));
      assert.ok(timelineWide.drawer.width>=400&&timelineWide.drawer.width<=480,"wide Timeline must remain a contextual panel instead of stretching at "+width+"x"+height);
      assert.ok(timelineWide.drawer.left>=0&&timelineWide.drawer.right<=timelineWide.width+1&&timelineWide.doc<=timelineWide.width,"wide Timeline must fit without horizontal overflow at "+width+"x"+height);
      const wideRailAlignment=await page.evaluate(()=>[...document.querySelectorAll("#conversationList .timeline-entry")].map(entry=>{const r=entry.getBoundingClientRect(),d=entry.querySelector(".timeline-dot").getBoundingClientRect(),p=getComputedStyle(entry,"::before");return Math.abs(r.left+parseFloat(p.left)+parseFloat(p.width)/2-(d.left+d.width/2))}));
      assert.ok(wideRailAlignment.length>0&&wideRailAlignment.every(delta=>delta<=1),"Timeline rail must pass through every node center at "+width+"x"+height+": "+wideRailAlignment.join(","));
      const wideTimelineCards=await page.locator("#conversationList .timeline-content").evaluateAll(cards=>cards.map(card=>card.getBoundingClientRect().width));
      assert.ok(wideTimelineCards.length>0&&wideTimelineCards.every(cardWidth=>cardWidth>=200),"Timeline cards must remain in the content column at "+width+"x"+height+": "+wideTimelineCards.join(","));
      if(width===768)await page.screenshot({path:"artifacts/personal-ai-timeline-approved-tablet-768x1024.png",fullPage:true});
      if(width===820)await page.screenshot({path:"artifacts/personal-ai-timeline-approved-tablet-820x1180.png",fullPage:true});
      if(width===1440)await page.screenshot({path:"artifacts/personal-ai-timeline-approved-desktop-1440x1000.png",fullPage:true});
  
      await page.click("#timelineCloseDrawer");
    }
  }

  // Sweep intermediate widths as well as the named device checkpoints. This
  // catches breakpoint gaps without tying the layout to specific device sizes.
  const sweepWidths=new Set([320,360,375,390,430,600,768,820,900,1024,1280,1440,1920,2560]);
  for(let width=320;width<=2560;width+=32)sweepWidths.add(width);
  for(const width of [...sweepWidths].sort((a,b)=>a-b)){
    await page.setViewportSize({width,height:844});
    await page.evaluate(()=>enterHomeLanding());
    const sweep=await page.evaluate(()=>{
      const box=selector=>{const r=document.querySelector(selector).getBoundingClientRect();return {left:r.left,right:r.right,width:r.width,height:r.height,bottom:r.bottom}};
      return {viewport:innerWidth,document:document.documentElement.scrollWidth,composer:box('#composer'),home:box('.home-intro'),header:box('.topbar'),quick:box('.v-shortcuts')};
    });
    assert.ok(sweep.document<=width,"intermediate width introduced page overflow at "+width+"px: "+JSON.stringify(sweep));
    for(const name of ["composer","home","header","quick"]){
      assert.ok(sweep[name].width>0&&sweep[name].left>=-1&&sweep[name].right<=width+1,
        name+" moved off-screen at intermediate width "+width+"px: "+JSON.stringify(sweep[name]));
    }
    assert.ok(sweep.composer.bottom<=844+1,"composer moved below the screen at intermediate width "+width+"px");
  }
  for(const [width,height] of [[320,480],[390,480],[390,1100],[844,390]]){
    await page.setViewportSize({width,height});
    await page.evaluate(()=>enterHomeLanding());
    await page.evaluate(()=>{
      const home=document.querySelector('.home-intro');
      home.scrollTop=home.scrollHeight;
    });
    await page.waitForTimeout(60);
    const shortOrTall=await page.evaluate(()=>{
      const last=document.querySelector('.v-shortcuts .v-card:last-child');
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
