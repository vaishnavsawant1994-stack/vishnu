# Current vs Required Screen Matrix

**Baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`

Legend: `P` partial/source-present, `E` experimental, `M` missing, `N/A` not required as a native implementation, `NV` not visually/a11y verified. `Connected=P` means meaningful backend/API/runtime wiring exists but the complete interaction/persistence/failure journey has not been accepted by this campaign.

| ID | Screen | Required | Exists | Reachable | Connected | Desktop | PWA | Android | iOS | Visual | A11Y | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ONB-001 | Welcome / Create-Join-Restore | Yes | Yes | Yes | P | P | P | M | P | NV | NV | PARTIAL |
| ONB-002 | Owner Identity | Yes | Yes | Yes | P | P | P | M | P | NV | NV | PARTIAL |
| ONB-003 | Security Setup | Yes | Yes | Yes | P | P | P | M | P | NV | NV | PARTIAL |
| ONB-004 | Privacy & Autonomy | Yes | Yes | Yes | P | P | P | M | P | NV | NV | PARTIAL |
| ONB-005 | Data Placement Policy | Yes | No | No | No | M | M | M | M | NV | NV | MISSING |
| ONB-006 | AI Provider Setup | Yes | Yes | Yes | P | P | P | M | P | NV | NV | PARTIAL |
| ONB-007 | Recovery Code Setup | Yes | Yes | Yes | P | P | P | M | P | NV | NV | PARTIAL |
| ONB-008 | Setup Review & Completion | Yes | No | No | No | M | M | M | M | NV | NV | MISSING |
| AUTH-001 | Sign In / Unlock | Yes | Yes | Yes | P | M | P | M | P | NV | NV | PARTIAL |
| AUTH-002 | Join Existing Vishnu / Device Enrollment | Yes | Yes | Yes | P | P | P | P | P | NV | NV | PARTIAL |
| AUTH-003 | Restore Access | Yes | Yes | Yes | P | P | P | M | P | NV | NV | PARTIAL |
| HOME-001 | Home | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| CHAT-001 | Conversation Workspace | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| CHAT-002 | Conversation History | Yes | Yes | Yes | P | M | P | N/A | N/A | NV | NV | PARTIAL |
| MEM-001 | Memory Overview & Search | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| MEM-002 | Memory Detail / Why Retrieved | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| KNW-001 | Knowledge Overview / Sources | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| KNW-002 | Knowledge Source Detail | Yes | Yes | Yes | P | M | P | N/A | N/A | NV | NV | PARTIAL |
| ACT-001 | Today | Yes | Yes | Yes | P | M | P | N/A | N/A | NV | NV | PARTIAL |
| ATT-001 | Inbox / Attention Center | Yes | Yes | Yes | P | M | P | N/A | N/A | NV | NV | PARTIAL |
| ACT-002 | Activity Timeline | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| WRK-001 | Live Work Overview | Yes | Yes | Yes | P | M | P | N/A | N/A | NV | NV | PARTIAL |
| WRK-002 | Work Detail | Yes | Yes | Yes | P | M | P | N/A | N/A | NV | NV | PARTIAL |
| WRK-003 | Agent Workforce | Yes | Yes | Yes | P | M | E | N/A | N/A | NV | NV | EXPERIMENTAL |
| AUT-001 | Automations / Workflows Overview | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| AUT-002 | Automation Detail & Run History | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| PRJ-001 | Projects Overview | Yes | Yes | Yes | P | M | P | N/A | N/A | NV | NV | PARTIAL |
| PRJ-002 | Project Workspace | Yes | Yes | Yes | P | M | P | N/A | N/A | NV | NV | PARTIAL |
| PRD-001 | Our Products Overview | Yes | Yes | Yes | P | E | E | N/A | N/A | NV | NV | EXPERIMENTAL |
| PRD-002 | Product Detail / Build Lifecycle | Yes | Yes | Yes | P | E | E | N/A | N/A | NV | NV | EXPERIMENTAL |
| APP-001 | Apps & Tools Overview | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| APP-002 | Connected Service / Integration Detail | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| CAP-001 | Capabilities Overview | Yes | Yes | Yes | P | P | P | P | P | NV | NV | PARTIAL |
| CAP-002 | Capability Detail | Yes | Yes | Yes | P | P | P | P | P | NV | NV | PARTIAL |
| CAP-003 | Capability Forge V3 | Yes | Yes | Yes | P | N/A | N/A | N/A | E | NV | NV | EXPERIMENTAL |
| DEV-001 | Trusted Devices Overview | Yes | Yes | Yes | P | P | P | P | P | NV | NV | PARTIAL |
| DEV-002 | Device Detail | Yes | Yes | Yes | P | M | P | M | P | NV | NV | PARTIAL |
| DAT-001 | Data & Storage Overview / Policy | Yes | Yes | Yes | P | P | P | M | N/A | NV | NV | PARTIAL |
| DAT-002 | Connected Storage Provider Detail | Yes | No | No | No | M | M | N/A | N/A | NV | NV | MISSING |
| MOD-001 | AI Models & Providers Overview | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| MOD-002 | Provider Detail / Credentials | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| VOC-001 | Voice Settings | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| VOC-002 | Voice Studio | Yes | Yes | Yes | P | P | N/A | N/A | N/A | NV | NV | PARTIAL |
| VOC-003 | Voice Lab | Yes | Yes | Yes | P | E | N/A | N/A | N/A | NV | NV | EXPERIMENTAL |
| SEN-001 | Sensorium Privacy & Permissions | Yes | Yes | Yes | P | N/A | N/A | M | P | NV | NV | PARTIAL |
| SEN-002 | Sensorium Status & Providers | Yes | No | No | No | M | M | N/A | N/A | NV | NV | MISSING |
| CTL-001 | Computer & Browser Control | Yes | Yes | Yes | P | P | M | N/A | N/A | NV | NV | PARTIAL |
| SEC-001 | Security Overview | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| SEC-002 | Sign-in Methods & Sessions | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| SEC-003 | Security Events / Audit History | Yes | Yes | Yes | P | M | P | N/A | N/A | NV | NV | PARTIAL |
| APR-001 | Approvals Center | Yes | Yes | Yes | P | M | P | N/A | N/A | NV | NV | PARTIAL |
| PRI-001 | Privacy Controls | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| REC-001 | Recovery Overview | Yes | Yes | Yes | P | P | P | M | P | NV | NV | PARTIAL |
| NOT-001 | Notification Settings | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| SYS-001 | Dashboard / Operational Status | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| SYS-002 | System Status / Diagnostics | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| SYS-003 | Updates & Release | Yes | No | No | No | M | M | N/A | N/A | NV | NV | MISSING |
| SYS-004 | About / Version / Notices | Yes | No | No | No | M | M | N/A | N/A | NV | NV | MISSING |
| SET-001 | Settings Hub | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| SET-002 | General & Profile | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| SET-003 | Appearance | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| SET-004 | Language & Region | Yes | Yes | Yes | P | P | P | N/A | N/A | NV | NV | PARTIAL |
| SET-005 | Accessibility | Yes | Yes | Yes | P | P | M | N/A | N/A | NV | NV | PARTIAL |

## Notes

- `M` in a platform column does **not** automatically mean the whole canonical screen is missing. It means that platform implementation is absent where the blueprint expects one.
- Android/iOS `N/A` is intentional where the trusted PWA is the declared owner product and a native duplicate would add no OS-bound value.
- SET-005 is source-present on Desktop through persisted Reduce Motion and High Contrast controls; cross-platform organization and acceptance remain incomplete.
- No screen is marked COMPLETE because visual/runtime acceptance evidence is absent for this exact audit SHA.
