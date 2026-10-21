# P2-01 Home — implementation and qualification ledger

Baseline: `main` at `63cc4bf7485b602d725c89a400008925560591f4` (2026-10-22).
Reference: owner-supplied 1536 × 1024 desktop/mobile design board.
Scope: bounded PWA Home adaptation; **not** production deployment, universal native parity or final visual acceptance.

## Source-to-screen mapping

| Approved element | Source and integration | State |
| --- | --- | --- |
| Navy/cyan responsive shell | `pwa/p2-home.css`, loaded by `reference-home.js` | Implemented; pixel comparison pending |
| Reused neural Core | existing `#neuralCanvas` / `.core-stage`, retained by `p2-home.js` | Reused; detailed sphere-match pending |
| Authenticated greeting | `/iphone/api/status` owner fields | Read-only; no demonstration name |
| Live clock/date | local `Intl.DateTimeFormat` | Implemented; locale/DST device proof pending |
| AI status | `/iphone/api/status` model state | Only `available` becomes “AI Ready” |
| System health | navigation to canonical `system` module | No unconditional “All Systems Operational” |
| Meetings and tasks | `/iphone/api/everyday/active` | Owner's Vishnu plan only; no external calendar claims |
| Approvals | `/iphone/api/work/attention` | Work approvals only; no authority changes |
| Active Work | `/iphone/api/work/summary` | Owner-scoped, verified authority marker; no fake percentages |
| Six Home shortcuts | existing chat bridge and canonical module router | New UI; browser qualification pending |
| Recent Activity | existing `#homeRecentSection`, canonical conversation cache | Existing behavior reused |
| Six Quick Tools | draft seeding in existing composer | Guided requests, not invented execution |
| Main composer, attachments, voice | existing `#composer`, send/attachment/microphone logic | Existing implementation retained; end-to-end requalification pending |
| Desktop sidebar and mobile tabs | existing Vishnu module router/Chat bridge | New P2-01 navigation adaptation |
| Offline shell | `pwa/sw.js` cache v61 | Assets added; offline device test pending |

## Runtime truth / failure behavior

- Frontend reads only owner-scoped existing APIs with same-origin credentials.
- Each unavailable API section reports an unavailable state, not a false zero count.
- Weather is **not** displayed: no configured, authorized weather source was established.
- Meeting count describes the Vishnu plan, **not** connected Google/Apple calendar events.
- Quick Tools prefill the canonical composer; they do **not** claim that every specialized tool or model capability is installed.
- Work controls do **not** execute, pause, resume or approve WorkOrders. Existing protected modules remain the authority.
- Production Home requires active owner authentication; CSS explicitly preserves `#voicePanel.hidden`.
- No new Home-only conversation store, service authority, approval bypass, credential store or fake agent run is introduced.

## Qualification

- JavaScript source/loader, test module and service-worker parsed by V8 during authored validation.
- P2 stylesheet passed a structural bracket-balance check.
- `tests/vishnu_home_responsive.mjs` has been updated with P2-01 assertions for 6 cards, local clock, populated real API projections, responsive layouts (320, 390, 768, 1024, 1440, 1920 widths), existing conversation continuity, outage truth and locked visibility.
- `.github/workflows/pwa-mobile-preview.yml` runs this test. **Its result remains unverified until an exact-head PR workflow succeeds.**
- Browser screenshots from this test are qualification artifacts, **not** a pixel-difference comparison against cropped owner reference images.

## Required before completion

1. Review the exact-head PWA browser run and fix any regressions.
2. Capture desktop/mobile rendered screenshots; compare against separately cropped/scale-matched sections of the approved board. Do not claim 100% pixel accuracy without this.
3. Audit additional inherited mobile layout overrides and ensure keyboard/safe-area behavior on actual platforms.
4. Verify actual owner login, passkey/recovery continuity and no leakage after session revocation.
5. Test voice permissions, attachments, model failure and live conversation delivery in real configured environments.
6. Confirm calendar integration, optional weather provider and tool-capability support before activating their UI claims.
7. Implement genuinely editable/persisted Quick Tools if required; current screen intentionally omits a nonfunctional Edit button.
8. Qualify Windows/macOS/Linux native shells, Android Emulator and iOS Simulator; physical-platform acceptance is deferred.
9. Obtain independent visual, accessibility, performance and security acceptance before requesting merge.

## Changed paths

- `pwa/p2-home.js` — P2-01 presentation adapter and read projections.
- `pwa/p2-home.css` — screenshot-led design tokens, desktop/mobile/tablet layout.
- `pwa/reference-home.js` — loader attached to existing Home.
- `pwa/sw.js` — offline shell asset registration.
- `tests/vishnu_home_responsive.mjs` — P2-01 browser qualification.
- `.github/workflows/pwa-mobile-preview.yml` — CI test registration.
- This ledger.

No production deployment or merge to main has been performed as part of this feature branch.
