// View state <-> URL hash. Pure (no DOM): the URL is the source of truth for view state.
// Other views add their own keys here (mode, kinds, group-by, ...); unknown keys are ignored.
//
// `view` picks the screen. With a focus node it defaults to "focus"; with none it is "overview", the
// landing view. (DEFAULTS.view is the focus-side default; `derivedView` applies the landing rule.)
// Overview-only keys: `expanded` (repeated `expanded=<group id>`), `okinds` (edge kinds; absent = server
// default, which leaves `calls` off), `groupby` ("directory"; ticket 25 appends "package" to GROUP_BYS).

import { BUDGET, clampLimit } from "./scale.js";

export const DEFAULTS = Object.freeze({
  depth: 2, direction: "both", mode: "both", view: "focus", limit: BUDGET.defaultLimit,
  expanded: Object.freeze([]), okinds: null, groupBy: "directory",
});
export const MAX_UI_DEPTH = 5;
export const ALL_DEPTH = 10; // "all" in the UI: the server's maximum depth
export const DIRECTIONS = ["both", "in", "out"];
// overview = Groups + Aggregate edges; focus = neighborhood/reach; type|declaration = hierarchies
export const VIEWS = ["overview", "focus", "type", "declaration"];
export const MODES = ["both", "impact", "dependencies"]; // Impact set / Dependencies / union
export const GROUP_BYS = ["directory"]; // ticket 25 appends "package"

/** The view implied by the hash when `view` is absent: focus when a Focus node is given, else the overview. */
export const derivedView = (focus) => (focus ? DEFAULTS.view : "overview");

/** "#focus=Shape&depth=3&mode=impact" -> full state. Invalid values fall back to defaults. */
export function parseHash(hash) {
  const p = new URLSearchParams((hash || "").replace(/^#/, ""));
  const rawDepth = p.get("depth");
  const depth = rawDepth === "all" ? ALL_DEPTH : Number.parseInt(rawDepth, 10);
  const direction = p.get("direction");
  const limit = p.has("limit") ? clampLimit(Number.parseInt(p.get("limit"), 10)) : DEFAULTS.limit;
  const mode = p.get("mode");
  const groupBy = p.get("groupby");
  const focus = p.get("focus") || null;
  return {
    focus,
    depth: (depth >= 1 && depth <= MAX_UI_DEPTH) || depth === ALL_DEPTH ? depth : DEFAULTS.depth,
    direction: DIRECTIONS.includes(direction) ? direction : DEFAULTS.direction,
    limit,
    mode: MODES.includes(mode) ? mode : DEFAULTS.mode,
    view: VIEWS.includes(p.get("view")) ? p.get("view") : derivedView(focus),
    expanded: p.getAll("expanded"),
    okinds: p.has("okinds") ? p.get("okinds").split(",").filter(Boolean) : null,
    groupBy: GROUP_BYS.includes(groupBy) ? groupBy : DEFAULTS.groupBy,
  };
}

/** Inverse of parseHash; values equal to the defaults are omitted to keep URLs short. */
export function formatHash(state) {
  const p = new URLSearchParams();
  if (state.focus) p.set("focus", state.focus);
  if (state.depth !== DEFAULTS.depth) p.set("depth", state.depth === ALL_DEPTH ? "all" : String(state.depth));
  if (state.direction !== DEFAULTS.direction) p.set("direction", state.direction);
  if (state.limit != null && state.limit !== DEFAULTS.limit) p.set("limit", String(clampLimit(state.limit)));
  if (state.mode !== DEFAULTS.mode) p.set("mode", state.mode);
  if (state.view && state.view !== derivedView(state.focus)) p.set("view", state.view);
  for (const id of state.expanded || []) p.append("expanded", id);
  if (state.okinds) p.set("okinds", state.okinds.join(","));
  if (state.groupBy && state.groupBy !== DEFAULTS.groupBy) p.set("groupby", state.groupBy);
  const s = p.toString();
  return s ? "#" + s : "";
}
