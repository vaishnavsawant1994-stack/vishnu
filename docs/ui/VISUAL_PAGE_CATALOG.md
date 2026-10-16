# Vishnu Visual Page Catalog

**Baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`

## Evidence boundary

This connected-GitHub environment can inspect and modify source but cannot clone/launch the repository runtime, browser, Android Emulator or iOS Simulator. No exact-SHA rendered screenshot artifact was found during this campaign. Therefore **no screenshot is fabricated and every canonical screen remains `Visual: NOT VERIFIED`**.

The catalog still records the expected visual purpose, route/location, actions and backend so the follow-up renderer can attach evidence without changing screen IDs.

| ID | Screen | Primary implementation/location | Major actions | Backend/runtime | Visual evidence | Status |
|---|---|---|---|---|---|---|
| ONB-001 | Welcome / Create-Join-Restore | Desktop wizard / PWA first-run / iOS onboarding | Create, Join, Restore | FirstRun/identity/provisioning | NOT VERIFIED | PARTIAL |
| ONB-002 | Owner Identity | onboarding step | Save owner profile | identity/preferences | NOT VERIFIED | PARTIAL |
| ONB-003 | Security Setup | onboarding step | passkey/password setup | owner auth/WebAuthn | NOT VERIFIED | PARTIAL |
| ONB-004 | Privacy & Autonomy | onboarding step | set privacy/autonomy | preferences/ToolRegistry policy | NOT VERIFIED | PARTIAL |
| ONB-005 | Data Placement Policy | required onboarding step | choose 4 data policies | Data Plane | NOT AVAILABLE | MISSING |
| ONB-006 | AI Provider Setup | onboarding step | provider/model/configure later | model/provider/vault | NOT VERIFIED | PARTIAL |
| ONB-007 | Recovery Code Setup | onboarding step | copy/save/acknowledge | recovery authority | NOT VERIFIED | PARTIAL |
| ONB-008 | Setup Review & Completion | required onboarding step | review, finish | identity/device/data/model/recovery | NOT AVAILABLE | MISSING |
| AUTH-001 | Sign In / Unlock | PWA/iOS auth | authenticate/recover | owner sessions/passkeys | NOT VERIFIED | PARTIAL |
| AUTH-002 | Join Existing / Device Enrollment | onboarding/native pairing | approve/enroll | DeviceRegistry/session exchange | NOT VERIFIED | PARTIAL |
| AUTH-003 | Restore Access | restore flow | verify/restore/re-enroll | recovery/backup | NOT VERIFIED | PARTIAL |
| HOME-001 | Home | Desktop/PWA Home | talk, continue, open attention | runtime state/conversation | NOT VERIFIED | PARTIAL |
| CHAT-001 | Conversation Workspace | Desktop/PWA | send, attach, voice, cancel, approve | turn runtime/model/tools | NOT VERIFIED | PARTIAL |
| CHAT-002 | Conversation History | PWA drawer/page | search/open/continue | conversation continuity/history | NOT VERIFIED | PARTIAL |
| MEM-001 | Memory Overview & Search | Desktop Second Brain / PWA Memory | search/filter | Memory/SecondBrain | NOT VERIFIED | PARTIAL |
| MEM-002 | Memory Detail / Why Retrieved | Memory workspace/detail | inspect explanation/source | Memory/SecondBrain | NOT VERIFIED | PARTIAL |
| KNW-001 | Knowledge Overview / Sources | Desktop/PWA Knowledge | add/search/open | Knowledge/content intelligence | NOT VERIFIED | PARTIAL |
| KNW-002 | Knowledge Source Detail | PWA detail | refresh/remove/ask | Knowledge/content intelligence | NOT VERIFIED | PARTIAL |
| ACT-001 | Today | PWA Workspace | open/continue | activities/work/notifications | NOT VERIFIED | PARTIAL |
| ATT-001 | Inbox / Attention | PWA Workspace | open/acknowledge/approve | notifications/approvals/work | NOT VERIFIED | PARTIAL |
| ACT-002 | Activity Timeline | Desktop/PWA | filter/open | activities/audit projections | NOT VERIFIED | PARTIAL |
| WRK-001 | Live Work Overview | PWA | inspect/cancel where allowed | Work runtime | NOT VERIFIED | PARTIAL |
| WRK-002 | Work Detail | PWA responsive detail shell | inspect evidence/claims/recovery | WorkOrder aggregate | NOT VERIFIED | PARTIAL |
| WRK-003 | Agent Workforce | PWA `/iphone/agents` | inspect workforce/governed controls | workforce APIs | NOT VERIFIED | EXPERIMENTAL |
| AUT-001 | Automations / Workflows | Desktop/PWA | create/pause/open | AutomationEngine | NOT VERIFIED | PARTIAL |
| AUT-002 | Automation Detail | Desktop/PWA | edit/run/pause/delete | AutomationEngine/history | NOT VERIFIED | PARTIAL |
| PRJ-001 | Projects Overview | PWA | new/search/filter/open | project APIs | NOT VERIFIED | PARTIAL |
| PRJ-002 | Project Workspace | PWA | chat/plan/files/approvals/discuss | projects/work/knowledge | NOT VERIFIED | PARTIAL |
| PRD-001 | Our Products Overview | Desktop canonical nav / PWA injected nav | open/create/inspect | product authority | NOT VERIFIED | EXPERIMENTAL |
| PRD-002 | Product Detail / Build Lifecycle | Products workspace | inspect/build/qualify | product/build/release | NOT VERIFIED | EXPERIMENTAL |
| APP-001 | Apps & Tools Overview | Desktop/PWA | connect/open/revoke | integrations/tools | NOT VERIFIED | PARTIAL |
| APP-002 | Connected Service Detail | Desktop/PWA | test/reconnect/revoke | integrations/OAuth/vault | NOT VERIFIED | PARTIAL |
| CAP-001 | Capabilities Overview | Desktop/PWA/native managers | search/import/add/open | capability catalog | NOT VERIFIED | PARTIAL |
| CAP-002 | Capability Detail | Desktop/PWA/native managers | approve/test/rotate/revoke | ToolRegistry/ApprovalManager/vault | NOT VERIFIED | PARTIAL |
| CAP-003 | Capability Forge V3 | iOS NavigationLink | readiness/OAuth/canary | Forge V3 owner APIs | NOT VERIFIED | EXPERIMENTAL |
| DEV-001 | Trusted Devices Overview | PWA/account/Desktop status/native | pair/open | DeviceRegistry/Gateway | NOT VERIFIED | PARTIAL |
| DEV-002 | Device Detail | PWA/iOS status | inspect/revoke/permissions | DeviceRegistry/Gateway | NOT VERIFIED | PARTIAL |
| DAT-001 | Data & Storage Overview | Desktop storage dialog / PWA settings | set policy/check sync | Data Plane | NOT VERIFIED | PARTIAL |
| DAT-002 | Storage Provider Detail | required | connect/test/transfer/disconnect | storage fabric | NOT AVAILABLE | MISSING |
| MOD-001 | Models & Providers Overview | Desktop/PWA settings | select/add/test | model router/provider APIs | NOT VERIFIED | PARTIAL |
| MOD-002 | Provider Detail / Credentials | Desktop/PWA | save/test/rotate/revoke | SecretVault/provider APIs | NOT VERIFIED | PARTIAL |
| VOC-001 | Voice Settings | Desktop/PWA settings | mic/output/listening | voice runtime/preferences | NOT VERIFIED | PARTIAL |
| VOC-002 | Voice Studio | Desktop Owner Control Center | personas/authorized voices | Voice Intelligence/VoiceStudio | NOT VERIFIED | PARTIAL |
| VOC-003 | Voice Lab | Desktop Owner Control Center | benchmark/qualify/telephony lab | Voice Lab/release authority | NOT VERIFIED | EXPERIMENTAL |
| SEN-001 | Sensorium Privacy | iOS NavigationLink | allow session/stop/STOP ALL | native Sensorium consent | NOT VERIFIED | PARTIAL |
| SEN-002 | Sensorium Status & Providers | required Advanced | inspect provider/evidence | Sensorium provider/evidence APIs | NOT AVAILABLE | MISSING |
| CTL-001 | Computer & Browser Control | Desktop Settings | enable/disable/status | computer/browser policy | NOT VERIFIED | PARTIAL |
| SEC-001 | Security Overview | Desktop/PWA Settings/Owner Controls | navigate/fix warnings | owner security/device/vault | NOT VERIFIED | PARTIAL |
| SEC-002 | Sign-in Methods & Sessions | fragmented Desktop/PWA/native | passkey/session revoke/rotate | owner sessions/WebAuthn | NOT VERIFIED | PARTIAL |
| SEC-003 | Security Events / Audit | PWA Owner Controls | filter/inspect | audit/security events | NOT VERIFIED | PARTIAL |
| APR-001 | Approvals Center | PWA Inbox/approval surfaces | allow/deny/cancel | ApprovalManager | NOT VERIFIED | PARTIAL |
| PRI-001 | Privacy Controls | Desktop/PWA settings | memory/external-data controls | preferences/data policy | NOT VERIFIED | PARTIAL |
| REC-001 | Recovery Overview | Desktop/PWA/iOS fragments | codes/package/restore | recovery/backup | NOT VERIFIED | PARTIAL |
| NOT-001 | Notification Settings | Desktop/PWA | categories/channels/quiet | NotificationService | NOT VERIFIED | PARTIAL |
| SYS-001 | Dashboard | Desktop/PWA operational status | refresh/open issue | runtime projections | NOT VERIFIED | PARTIAL |
| SYS-002 | System Status / Diagnostics | PWA account/Desktop control center | refresh/diagnose | health/evidence/runtime | NOT VERIFIED | PARTIAL |
| SYS-003 | Updates & Release | required Settings | check/update/restart | updates/release authority | NOT AVAILABLE | MISSING |
| SYS-004 | About / Version / Notices | required Settings | copy/open notices | build/license metadata | NOT AVAILABLE | MISSING |
| SET-001 | Settings Hub | Desktop/PWA | navigate settings | preferences/domain settings | NOT VERIFIED | PARTIAL |
| SET-002 | General & Profile | Desktop/PWA | edit/save profile | preferences/profile APIs | NOT VERIFIED | PARTIAL |
| SET-003 | Appearance | Desktop/PWA | theme/presentation | UI preferences | NOT VERIFIED | PARTIAL |
| SET-004 | Language & Region | Desktop/PWA | locale preference | UI preferences | NOT VERIFIED | PARTIAL |
| SET-005 | Accessibility | Desktop SettingsPanel; broader settings organization required | reduce motion/high contrast | preferences/design system | NOT VERIFIED | PARTIAL |

## Screenshot acceptance plan

For each P0/P1/core screen capture at minimum:

1. normal populated desktop/web state;
2. phone state where responsive/mobile web is intended;
3. empty state for collection screens;
4. one meaningful error/offline/permission state for critical screens;
5. Android/iOS emulator/simulator screen for every native-required implementation;
6. exact commit SHA, viewport/device, route and test identity in screenshot metadata.

Never accept a design mock or `uiDemo=1` preview as proof that the real owner API path rendered correctly.
