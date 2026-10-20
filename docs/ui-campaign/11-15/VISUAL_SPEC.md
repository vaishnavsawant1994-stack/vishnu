# Visual specification — Screens 11–15

Reference set: owner-provided `11-home.jpeg` through `15-global-search.jpeg` in the implementation pack. Each is a desktop+phone composite, not a usable UI background. Names, dates, percentages, workspaces, files, and counts shown are illustrative and must never be seeded as production data.

## Frozen visual cues

- Deep black-blue canvas and navigation; restrained cyan/cyan-white accent; high-contrast pale text; fine translucent blue borders; rounded dark surfaces; consistent outline icon family.
- Desktop shell: persistent left rail, compact global header, content canvas and optional context inspector. Owner/profile is at the foot of the rail.
- Mobile shell: centered Vishnu identity, safe-area-aware top controls, stacked content, bottom navigation with Home / Spaces / Create / Work / More.
- One recognizable neural Core asset/geometry across Home, Conversation and Voice. The PWA preview reuses `pwa/assets/genesis/vishnu-core.png` plus the existing desktop/mobile cosmic backgrounds instead of drawing a separate sphere or stretching a reference composite. It scales and shows the owner glyph only where appropriate.
- Home: Core, real owner greeting, composer, quick actions, truthful Continue and Activity.
- Conversation: readable transcript, resource tabs, anchored composer, optional desktop inspector and mobile context sheet.
- History: search/filter row, grouped conversation list and inspector on desktop; list-first mobile layout.
- Live Voice: same Core, transcript, explicit real sensor state and usable Mute/End/Keyboard controls.
- Search: input and scopes, grouped real results, optional desktop details and mobile list/detail behavior.

## Token baseline

The implementation pack specifies `#02060B` background, `#030A12` deep background, `#04101B` navigation, `#071522` surface, `#091A28` raised surface, `#20B8FF` cyan, `#4DDCFF` bright cyan, `#A4E2FF` soft blue, `#F5FAFF` text and `#A7BACB` secondary text. Existing older screens are not yet proven to consume a single canonical token source. The new Search stylesheet references these values without importing the reference composites.

No measured image overlays or approved device-specific golden captures have been produced in this campaign yet. Pixel-level fidelity is therefore unverified.
