# Vishnu Navigation Blueprint

**Baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`

## Finished owner mental model

```text
Vishnu
├── Talk with me             → Home / Conversation
├── What I remember          → Memory
├── What I know              → Knowledge
├── What I am doing          → Today / Inbox / Activity / Live Work / Projects
├── What I can access        → Apps & Tools / Capabilities
├── Where I can operate      → Devices / Computer Control / Sensorium
├── Where your data lives    → Data & Storage
└── What you control         → Settings / Security / Recovery / Providers
```

## Desktop

Recommended persistent navigation, derived from the active `CanonicalMainWindow` but simplified around frequency:

**Primary**
- Home
- Conversation
- Memory
- Knowledge
- Activities

**Work / secondary**
- Projects
- Live Work
- Apps & Tools

**Product-building advanced**
- Our Products

**Owner**
- Dashboard
- Settings

Desktop should use a persistent sidebar plus central workspace; detail can use a side panel/dialog where the task is contextual. The current canonical desktop nav already exposes Home, Conversation, Memory, Knowledge, Activities, Dashboard, Apps & Tools, Our Products and Settings. Projects/Live Work are meaningful parity gaps rather than reasons to overload Home.

## PWA desktop

Preserve the source grouping with one correction to semantic duplication:

**Workspace**
- Home
- Projects
- Today
- Inbox

**Personal**
- Conversations
- Memory
- Knowledge

**Work & access**
- Live Work
- Activity
- Apps & Tools
- Automations

**Owner account**
- Settings
- Trusted Devices
- System Status

**Advanced**
- Agents
- Our Products
- Capability Forge only after it becomes a supported web owner surface

`Live Work` and `Automations/Workflows` must have distinct route/module identifiers if they represent different concepts. The current duplicate `workflows` key must be confirmed and reconciled.

## Mobile PWA

Use a shallow five-entry bottom navigation for frequent tasks:

- Home
- Memory
- Knowledge
- Activity
- More

`More` contains Projects, Inbox, Live Work, Automations, Apps & Tools, Devices and Settings. Security-sensitive and technical surfaces remain under Settings/Advanced. Conversation History is a drawer/sheet from Home rather than a bottom-tab destination.

## Android companion

Native navigation should stay intentionally narrow:

- Connect / Join Vishnu
- This Device / Trust
- Universal Capabilities (where configured)
- Sensorium Privacy/Permissions (required parity gap)
- Recovery (required parity gap)
- Open Vishnu (trusted PWA) for Home/conversation/work/settings

Do not duplicate every web owner screen natively without an OS-bound reason.

## iPhone / iPad companion

Native navigation should preserve current OS-bound strengths:

- Create / Join / Restore
- Connection / This Device
- Universal Capabilities
- Sensorium Privacy & Sensors
- Recovery / Passkey / Provisioning
- Capability Forge V3 under Advanced/testing only
- Open trusted PWA for broad owner product

On iPad, navigation may use split view/sidebar instead of phone stacks; functionality remains equivalent.

## Exact goal paths

| Goal | Preferred path |
|---|---|
| Start conversation | Home → composer |
| Find old conversation | Home/Conversation → History → thread |
| Find a memory | Home → Memory → Search → Memory Detail |
| Inspect knowledge source | Home → Knowledge → source |
| Add knowledge | Knowledge → Add Source/Upload |
| See what needs attention | Home → Inbox/Attention |
| Inspect running work | Home → Live Work → Work Detail |
| Continue a project | Home → Projects → Project Workspace |
| Create automation | Home → More/System → Automations → Create |
| Connect service | Apps & Tools → Add/Connected Service → authenticate/configure |
| Import OpenAPI | Apps & Tools → Capabilities → Add → OpenAPI |
| Add MCP | Apps & Tools → Capabilities → Add → MCP |
| Revoke capability | Apps & Tools → Capabilities → Capability Detail → Disconnect/Revoke |
| Add device | Settings/More → Devices → Add Device → QR/code |
| Revoke lost phone | Settings → Devices → Device Detail → Mark Lost/Revoke |
| Check data location | Settings → Data & Storage |
| Change data policy | Settings → Data & Storage → Policy → confirmation |
| Add AI provider | Settings → AI Models & Providers → Add Provider |
| Change voice | Settings → Voice |
| Stop sensing | Native companion → Sensorium Privacy → STOP ALL SENSING |
| Review sign-in methods | Settings → Security → Sign-in Methods & Sessions |
| Review security event | Settings → Security → Audit History |
| Recover Vishnu | Welcome/Sign In → Restore Vishnu → verify → trusted device → review → Home |
| Check runtime problem | Settings/Account → System Status |
| Check version | Settings → About / Updates |

## Maximum navigation depth

- Frequent everyday goals should normally be reachable in **≤2 navigation transitions** from Home.
- Detail inspection may add one more transition (for example Devices → Device Detail).
- Security-sensitive actions may intentionally add reauthentication/confirmation rather than flattening the hierarchy.
- Advanced diagnostics may use Settings → Advanced → detail.

Flag any everyday task requiring more than three product-navigation levels, excluding security prompts.

## Deep links

Any deep-linked screen must:

1. validate/normalize the route;
2. authenticate first;
3. check owner/device scope;
4. route to safe parent if target is unavailable;
5. show expired/invalid-link state without leaking data;
6. never bypass fresh reauthentication/approval requirements.

## Universal search / command access

A universal owner search/command palette is useful **only after** its results are authority-backed. It may search conversations, Memory, Knowledge, Projects, Apps & Tools, Devices and Settings. It should not become a hidden bypass around security-gated actions; action commands must still enter the canonical confirmation/approval flow.
