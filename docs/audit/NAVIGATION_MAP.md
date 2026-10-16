# Navigation Map

Baseline: `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

## Desktop

```mermaid
flowchart TD
  L[Launch] --> FR{Initialized?}
  FR -->|No| W[First-run / Create / Existing / Restore]
  FR -->|Yes| H[Home]
  W --> H
  H --> C[Conversation]
  H --> M[Memory]
  H --> K[Knowledge]
  H --> A[Activities]
  H --> D[Dashboard]
  H --> AT[Apps & Tools]
  H --> S[Settings]
  AT --> CM[Capability management]
  S --> MP[Mobile pairing / device controls]
  S --> ADV[Advanced/security/storage controls]
  M --> MD[Ambient / Graph / Tree / Detail]
```

The eight primary destinations are directly instantiated/wired in `ui/main_window.py`. Focused dialogs/panels are contextual/settings/progressive disclosure rather than automatically new top-level routes.

## PWA/Web

```mermaid
flowchart TD
  P[Launch/PWA] --> AUTH[Session / onboarding]
  AUTH --> HOME[Home/conversation]
  HOME --> CHAT[Conversation/context]
  HOME --> WORK[Agents / Work]
  HOME --> MORE[More / Settings / Advanced]
  MORE --> DEV[Devices]
  MORE --> CAP[Apps & Tools / capabilities]
  MORE --> ST[Storage/security/owner controls]
```

Exact DOM route/link reachability for every PWA component is `NOT VERIFIED` until generated from current assets/runtime wiring. Progressive disclosure is treated as valid architecture when intentional.

## Android / iOS

```mermaid
flowchart TD
  N[Native launch] --> E{Enrolled?}
  E -->|No| PAIR[Create/join/restore or pairing/session flow]
  E -->|Yes| NH[Companion home]
  PAIR --> NH
  NH --> DS[Device/Sensorium functions]
  NH --> CA[Capability management where enabled]
  NH --> DP[Data/continuity controls where enabled]
  NH --> VO[Voice/notification/context features where enabled]
```

Emulator/simulator reachability does not establish physical-device behavior.

## Reachability risks to keep visible

- Source files are not counted as screens unless instantiated/linked.
- Deep links require handlers and authentication/scopes.
- Advanced/qualification surfaces may be intentionally hidden from ordinary users.
- Internal registries, crypto, migrations, queues and conflict resolvers do not need direct screens.
- Exhaustive orphan-page/dialog detection remains `NOT VERIFIED` pending automated route/control inventory.
