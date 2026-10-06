// Impact / Dependencies controls: pure helpers (no DOM).
import { ALL_DEPTH, MAX_UI_DEPTH } from "./state.js";

export const MODES = [
  { value: "neighborhood", label: "Neighborhood (all edges)" },
  { value: "both", label: "Impact + dependencies" },
  { value: "impact", label: "Impact set (what breaks)" },
  { value: "dependencies", label: "Dependencies (what it needs)" },
];

/** Depth select options: 1..5 then "all" (the server maximum). */
export function depthOptions() {
  const opts = [];
  for (let d = 1; d <= MAX_UI_DEPTH; d++) opts.push({ value: d, label: String(d) });
  opts.push({ value: ALL_DEPTH, label: "all" });
  return opts;
}

/**
 * "1: 3 · 2: 12" per-ring node counts. Zero-fills up to the chosen depth; for "all" stops at the last non-empty ring.
 * When the server truncated the walk it never counted the rings past the last one present, so those are not
 * zero-filled (that would claim they are empty).
 */
export function ringText(ringCounts, depth, truncated = false) {
  if (!ringCounts) return "";
  const present = Object.keys(ringCounts).map(Number);
  const last = truncated || depth > MAX_UI_DEPTH ? Math.max(0, ...present) : depth;
  const parts = [];
  for (let d = 1; d <= last; d++) parts.push(`${d}: ${ringCounts[d] || 0}`);
  if (truncated && last < depth) parts.push("deeper rings not counted");
  return parts.join(" · ");
}

/** The direction control only means something in the plain neighborhood mode (reach modes fix their own). */
export const directionEnabled = (mode) => mode === "neighborhood";
