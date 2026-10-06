// View state <-> URL hash. Pure (no DOM): the URL is the source of truth for view state.
// Other views add their own keys here (mode, kinds, group-by, ...); unknown keys are ignored.

import { BUDGET, clampLimit } from "./scale.js";

export const DEFAULTS = Object.freeze({ depth: 2, direction: "both", limit: BUDGET.defaultLimit });
export const MAX_UI_DEPTH = 5;
export const DIRECTIONS = ["both", "in", "out"];

/** "#focus=Shape&depth=3" -> {focus, depth, direction}. Invalid values fall back to defaults. */
export function parseHash(hash) {
  const p = new URLSearchParams((hash || "").replace(/^#/, ""));
  const depth = Number.parseInt(p.get("depth"), 10);
  const direction = p.get("direction");
  const limit = p.has("limit") ? clampLimit(Number.parseInt(p.get("limit"), 10)) : DEFAULTS.limit;
  return {
    focus: p.get("focus") || null,
    depth: depth >= 1 && depth <= MAX_UI_DEPTH ? depth : DEFAULTS.depth,
    direction: DIRECTIONS.includes(direction) ? direction : DEFAULTS.direction,
    limit,
  };
}

/** Inverse of parseHash; values equal to the defaults are omitted to keep URLs short. */
export function formatHash(state) {
  const p = new URLSearchParams();
  if (state.focus) p.set("focus", state.focus);
  if (state.depth !== DEFAULTS.depth) p.set("depth", String(state.depth));
  if (state.direction !== DEFAULTS.direction) p.set("direction", state.direction);
  if (state.limit != null && state.limit !== DEFAULTS.limit) p.set("limit", String(clampLimit(state.limit)));
  const s = p.toString();
  return s ? "#" + s : "";
}
