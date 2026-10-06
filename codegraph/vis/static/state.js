// View state <-> URL hash. Pure (no DOM): the URL is the source of truth for view state.
// Other views add their own keys here (mode, kinds, group-by, ...); unknown keys are ignored.

export const DEFAULTS = Object.freeze({ depth: 2, direction: "both", mode: "both", view: "focus" });
export const MAX_UI_DEPTH = 5;
export const ALL_DEPTH = 10; // "all" in the UI: the server's maximum depth
export const DIRECTIONS = ["both", "in", "out"];
export const VIEWS = ["focus", "type", "declaration"]; // focus = neighborhood/reach; type|declaration = hierarchies
export const MODES = ["both", "impact", "dependencies"]; // Impact set / Dependencies / union

/** "#focus=Shape&depth=3&mode=impact" -> {focus, depth, direction, mode}. Invalid values fall back to defaults. */
export function parseHash(hash) {
  const p = new URLSearchParams((hash || "").replace(/^#/, ""));
  const rawDepth = p.get("depth");
  const depth = rawDepth === "all" ? ALL_DEPTH : Number.parseInt(rawDepth, 10);
  const direction = p.get("direction");
  const mode = p.get("mode");
  return {
    focus: p.get("focus") || null,
    depth: (depth >= 1 && depth <= MAX_UI_DEPTH) || depth === ALL_DEPTH ? depth : DEFAULTS.depth,
    direction: DIRECTIONS.includes(direction) ? direction : DEFAULTS.direction,
    mode: MODES.includes(mode) ? mode : DEFAULTS.mode,
    view: VIEWS.includes(p.get("view")) ? p.get("view") : DEFAULTS.view,
  };
}

/** Inverse of parseHash; values equal to the defaults are omitted to keep URLs short. */
export function formatHash(state) {
  const p = new URLSearchParams();
  if (state.focus) p.set("focus", state.focus);
  if (state.depth !== DEFAULTS.depth) p.set("depth", state.depth === ALL_DEPTH ? "all" : String(state.depth));
  if (state.direction !== DEFAULTS.direction) p.set("direction", state.direction);
  if (state.mode !== DEFAULTS.mode) p.set("mode", state.mode);
  if (state.view && state.view !== DEFAULTS.view) p.set("view", state.view);
  const s = p.toString();
  return s ? "#" + s : "";
}
