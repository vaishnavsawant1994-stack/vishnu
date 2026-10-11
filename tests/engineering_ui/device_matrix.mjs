export const CANONICAL_DEVICES = Object.freeze([
  { name: "tiny-phone", width: 320, height: 568, mobile: true, touch: true },
  { name: "android-compact", width: 360, height: 800, mobile: true, touch: true },
  { name: "iphone-compact", width: 375, height: 812, mobile: true, touch: true },
  { name: "iphone-standard", width: 390, height: 844, mobile: true, touch: true },
  { name: "large-phone", width: 430, height: 932, mobile: true, touch: true },
  { name: "tablet-portrait", width: 768, height: 1024, mobile: true, touch: true },
  { name: "tablet-landscape", width: 1024, height: 768, mobile: true, touch: true },
  { name: "laptop", width: 1280, height: 720, mobile: false, touch: false },
  { name: "desktop", width: 1440, height: 900, mobile: false, touch: false },
  { name: "reference-desktop", width: 1536, height: 1024, mobile: false, touch: false },
  { name: "full-hd", width: 1920, height: 1080, mobile: false, touch: false },
  { name: "large-desktop", width: 2560, height: 1440, mobile: false, touch: false },
]);

export const STANDALONE_SWEEP_WIDTHS = Object.freeze([320, 360, 375, 390, 430, 600, 768, 820, 1024, 1280, 1440, 1920, 2560]);

export function breakpointNeighbours(widths = STANDALONE_SWEEP_WIDTHS) {
  return [...new Set(widths.flatMap(width => [width - 1, width, width + 1]).filter(width => width >= 240))].sort((a, b) => a - b);
}

export const UI_STATES = Object.freeze([
  "empty", "normal", "large", "loading", "slow", "offline", "partial_failure",
  "unauthorized", "forbidden", "missing", "server_error", "session_expired",
  "blocked", "approval_required", "recovery", "long_content",
]);

export function assertNoViewportOverflow(assert, layout, width, label = "page") {
  assert.ok(layout.document <= width + 1, `${label} overflows ${width}px: ${JSON.stringify(layout)}`);
}
