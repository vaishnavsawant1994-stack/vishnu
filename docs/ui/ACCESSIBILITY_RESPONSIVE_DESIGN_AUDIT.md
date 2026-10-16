# Accessibility, Responsive & Design-System Audit

**Baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`

## 1. Accessibility has two meanings

### Product reachability
A screen is accessible only when the owner can reach it through normal navigation or a valid authenticated deep link. Source existence is not enough.

### A11Y
A reachable screen must also support disabled users through platform-appropriate keyboard, focus, semantic, screen-reader, text-scaling and touch behavior.

These dimensions are reported separately in `ui_truth.json`.

## 2. Existing evidence

Current tests/source prove several important contracts:

- chat message/send/microphone/attachment controls have accessible labels;
- approval dialog semantics and focus return are tested;
- live/error announcements are represented;
- PWA has `:focus-visible` behavior;
- PWA contains reduced-motion handling;
- responsive breakpoint CSS is under automated layout tests;
- shared desktop design tokens set 44px control/touch targets and explicit focus borders;
- Desktop `SettingsPanel` exposes and persists **Reduce motion** and **High contrast**;
- reduced motion is applied to the active desktop pulse immediately, while high-contrast state is persisted for full application after restart;
- iOS Sensorium and companion surfaces use native SwiftUI labels/navigation semantics;
- PWA project and WorkOrder surfaces contain explicit mobile adaptations.

This is meaningful evidence, but it is not full WCAG/platform accessibility acceptance.

## 3. NOT VERIFIED accessibility work

- complete Tab/Shift+Tab order on every desktop/web screen;
- Escape/Enter behavior for every custom dialog/drawer;
- focus trapping for every modal and restoration to invoker;
- screen-reader journey through onboarding, chat, approval, device revoke and data policy;
- VoiceOver on physical iPhone/iPad;
- TalkBack on physical Android;
- Dynamic Type / OS font scaling through all native surfaces;
- zoom/text reflow at desktop/browser accessibility zoom levels;
- contrast measurements for all status/error/disabled states;
- touch-target acceptance on real devices;
- non-swipe alternatives for any gesture-only action.

## 4. Accessibility settings truth

`SET-005 Accessibility` is **PARTIAL**, not missing. Desktop already provides working owner controls for **Reduce motion** and **High contrast** inside `SettingsPanel`, backed by persisted preferences. What is missing is a coherent/discoverable Accessibility subsection and appropriate parity/OS-following behavior outside Desktop.

Recommended finished contents:

- Follow system appearance/contrast where applicable;
- Reduce motion;
- High contrast;
- supported text-density/text-size behavior only if Vishnu can genuinely implement it;
- explanation when an accommodation is managed by the operating system rather than by Vishnu.

Do not create custom accessibility toggles that fight platform-level accessibility settings, and do not replace the already-working Desktop preferences with a duplicate persistence path.

## 5. Keyboard contract

Desktop/Web core actions must be operable without a mouse where platform convention expects it:

- logical Tab and Shift+Tab;
- Enter activates primary button/form submit;
- Escape closes dismissible dialog/drawer without committing changes;
- visible focus at all times for keyboard navigation;
- destructive actions not adjacent to default/primary focus without clear labels;
- keyboard shortcuts, if added, must have discoverable alternatives and not conflict with text entry.

## 6. Screen reader contract

- one meaningful screen/page heading;
- explicit names for icon-only buttons;
- form label association;
- status/streaming/error announcement only when meaningful, avoiding repetitive noise;
- selected/expanded/pressed states expressed semantically;
- approval dialogs describe target/risk/impact before buttons;
- decorative Vishnu orb/art hidden from accessibility tree unless it conveys state; if it conveys state, an equivalent text status is mandatory.

## 7. Touch contract

- minimum target approximately 44×44 CSS/native points for primary controls;
- destructive actions separated from common controls;
- one-handed access to Home composer, send, voice and attachment on phones;
- drawers/sheets remain scrollable with safe-area padding;
- no required hover-only information;
- any swipe shortcut has a visible button/menu alternative.

## 8. Responsive acceptance widths

The follow-up renderer must test actual layouts, not only resize screenshots:

| Class | Representative target |
|---|---|
| Narrow phone | 320–360 CSS px |
| Standard phone | 390–430 CSS px |
| Large phone | 440–480 CSS px |
| Tablet portrait | ~768–834 CSS px |
| Tablet landscape | ~1024–1194 CSS px |
| Laptop | ~1280×800 |
| Desktop | ~1440×900 |
| Wide desktop | 1728–1920+ |

For each, verify no clipped primary controls, inaccessible drawer exits, hidden form labels, horizontal-scroll-only tables, overlapping dialogs or fixed-width detail panes.

## 9. Local-first offline/degraded UX

Offline is not synonymous with broken Vishnu.

Every relevant screen must distinguish:

- **Local available:** conversation/local model/data still usable;
- **Remote unavailable:** provider/cloud/device connection unavailable;
- **Queued/sync later:** state saved locally and pending permitted synchronization;
- **Degraded:** local fallback works but one provider/service does not;
- **Unavailable:** the requested action genuinely cannot proceed.

Examples:

- cloud AI down + local model available → degraded/fallback, not total failure;
- remote storage down + local copy healthy → local available + sync pending;
- remote device offline → device shown offline, not deleted;
- voice unavailable → text remains available.

## 10. Canonical Vishnu visual system

### Desktop source tokens

Shared `ui/design_tokens.py` defines:

- background `#030405`;
- surface `#0b1115`;
- raised surface `#101b21`;
- primary text `#edf3f6`;
- secondary `#9badb7`;
- muted `#71818b`;
- border `#2b4350`;
- accent `#67b7ff`;
- danger `#ff929f`;
- selection `#244656`;
- 4/8/12/16/20/24/32/40 spacing;
- body 16px, supporting/control 14px, metadata 12px, section 19px, page 23px, display 30px;
- 44px control/touch target;
- 10px common control radius;
- 2px accent focus border.

### PWA direction

PWA source uses matching dark translucent/surface language, cyan/blue status accents, rounded cards, safe-area-aware mobile chrome, focus-visible and reduced-motion rules. Some feature modules contain their own hardcoded colors/radii; these should be normalized to semantic tokens over time rather than visually redesigned wholesale.

### Native direction

iOS/Android should use native navigation/forms/permissions while sharing Vishnu terminology, semantic state labels and risk/destructive color meaning. Do not force web glass effects onto native controls when that harms platform accessibility.

## 11. Required semantic component set

- AppShell / adaptive navigation
- TopBar / account menu
- Composer
- Message bubble / citation / attachment
- Vishnu status/presence indicator with text equivalent
- SearchField
- SectionHeader
- Card/list row
- StatusBadge
- DeviceRow
- CapabilityRow
- ProviderRow
- MemoryRow
- KnowledgeSourceRow
- Work/Project row
- ApprovalCard
- EmptyState
- LoadingState/Skeleton
- Error/Offline/Degraded state
- PermissionPrompt
- ConfirmationDialog
- CredentialField (never redisplays stored secret)
- Detail panel / responsive sheet

Duplicate local components should migrate toward these semantic primitives where it reduces inconsistency without destabilizing working screens.

## 12. Status/destructive language

Use the same owner vocabulary across platforms:

- `Trusted`, `Pending`, `Revoked`, `Offline` for devices;
- `Connected`, `Needs attention`, `Revoked` for integrations;
- `Read`, `Write`, `Destructive` for capability risk;
- `Waiting for approval`, `Running`, `Completed`, `Failed`, `Recovery required` for work;
- `Local`, `Sync pending`, `Synced`, `Remote unavailable`, `Conflict` for data.

Destructive buttons must state the object/action: `Revoke iPhone`, `Disconnect capability`, `Delete memory`, not generic `Confirm`.

## 13. Visual acceptance definition

A screenshot is accepted only when it records:

- exact commit SHA;
- platform/browser/device/viewport;
- real route/navigation path;
- real API/runtime data or an explicitly named empty/error fixture;
- no production secrets/PII;
- screenshot filename/metadata referenced by the Visual Page Catalog.

Design mocks and `uiDemo=1` pages are useful design references but do not satisfy `visual_verified=true`.
