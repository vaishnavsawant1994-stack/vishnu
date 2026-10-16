# Backend capabilities without a verified owner UI

**Baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`

| Capability | Evidence / backend | Owner need | Recommended location | Full page? | Priority |
|---|---|---|---|---|---|
| Update status and recovery | `updates/`, `packaging/`, `installer/`; active PWA module registry lacks About/Updates | Check version, signature, availability and recovery | Settings → About & Updates | Small settings page only if updater is active | P2 |
| Unified Data Plane policy/status | Data Plane APIs/stores and native MobileDataPlaneStore exist; complete owner controls not established on all surfaces | See location, choose sync policy, inspect conflicts | Settings → Data & Storage | Yes, grouped page | P1 |
| Searchable security/audit history | Audit and approval services exist; Activities provides broader activity sources | Inspect sign-in, device, approval, revoke history safely | Settings → Security → Recent security activity; link into Activities | Section, not separate primary page | P1 |
| Cross-platform device approval/revocation | DeviceRegistry/owner APIs and companion enrollment exist; complete owner workflow not verified per platform | Approve and revoke trusted devices | Apps & Tools / Settings → Devices | Yes, devices overview/detail | P1 |
| Recovery status overview | Recovery services and Android/iOS package views exist; cross-platform owner recovery management is not verified | Know recovery readiness before device loss | Settings → Security → Recovery | Section plus restore flow | P1 |
| Provider data-routing status | Model/provider runtime exists; settings screens exist but live provider route is not exercised here | Understand local vs remote processing and active fallback | Settings → AI & Models | No separate page beyond settings/model detail | P1 |

This report means **not verified as a complete owner experience**, not that no component exists. Internal registries, event buses, cryptographic stores and migration engines remain correctly internal.
