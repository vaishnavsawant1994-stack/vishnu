# UI Screen Inventory

Baseline: `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

## Desktop / PyQt

Source-verified primary navigation in `ui/main_window.py`:

1. Home — conversation entry, voice trigger, summary/status links.
2. Conversation — text/voice conversation surface.
3. Memory — memory overview plus Ambient/Graph/Tree/Detail entry points.
4. Knowledge — Knowledge product surface.
5. Activities — owner activity history.
6. Dashboard — status/overview surface.
7. Apps & Tools — integration/capability entry surface.
8. Settings — owner configuration/progressive disclosure.

Additional focused modules discovered under `ui/` include capability management, control panel, first-run wizard, memory panel, mobile-pairing dialog, native authentication and Products UI. These focused surfaces count as product UI only where invoked by the primary shell or a verified context flow; file existence alone is not treated as reachability.

## PWA/Web

The `pwa/` tree contains chat/context ownership, adaptive composer, Agents/Workforce/Work Mode and broader progressive-disclosure UI assets. A complete component/control census is `NOT VERIFIED` in this first audit head because a framework-aware route/control generator has not yet been run. The audit does not label these files unreachable merely from static naming, nor reachable merely from existence.

## Android

`android-companion/` provides native companion screens/activities for first-run/device trust/session and merged capability/Sensorium/data-plane work. Emulator qualification is evidence for emulator scope only. Physical Android phone/tablet rendering, permissions/background behavior and every screen path remain separately bounded.

## iOS

`ios-companion/` provides Swift native companion/session/capability/Sensorium/data-plane surfaces. Simulator build/test evidence does not equal physical iPhone/iPad evidence.

## Reachability classifications used

- Directly reachable
- Progressive disclosure / Settings / Advanced
- Contextual/agent-launched
- Deep-link/native enrollment
- Qualification/developer-only
- Orphaned/unreachable
- NOT VERIFIED

The canonical desktop eight-page navigation is directly source-verified. Dialog-by-dialog PWA/native reachability remains `NOT VERIFIED` unless specifically proven in `BACKEND_UI_TRACEABILITY.md` or the Product Truth Map.

## UI implementation rule

A UI is implemented only when it renders, is reachable, loads real data, invokes real backend/runtime functionality, handles success/failure, persists state where required, and is governed by the applicable security boundary. Static `.py`, `.html`, `.js`, `.kt` or `.swift` files do not satisfy that rule by themselves.
