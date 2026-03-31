import type { SymbolKind, RelationKind } from "../types/graph";

/** Node colors by symbol kind — vibrant on dark background. */
export const NODE_COLORS: Record<SymbolKind, string> = {
  module: "#3b82f6",
  class: "#f59e0b",
  function: "#10b981",
  method: "#14b8a6",
  property: "#22c55e",
  classmethod: "#eab308",
  staticmethod: "#a855f7",
};

/**
 * Edge colors — very subtle so they don't overpower the nodes.
 * Semi-transparent to avoid the dense dark blob effect.
 */
export const EDGE_COLORS: Record<RelationKind, string> = {
  defines: "rgba(100, 116, 139, 0.12)",
  has_method: "rgba(14, 116, 144, 0.12)",
  calls: "rgba(124, 58, 237, 0.15)",
  imports: "rgba(59, 130, 246, 0.18)",
  extends: "rgba(194, 65, 12, 0.20)",
};

/** Dimmed color for non-highlighted elements. */
export const DIMMED_NODE_COLOR = "#1a1a2e";
export const DIMMED_EDGE_COLOR = "rgba(30, 30, 50, 0.1)";

/** Highlight color for selected nodes. */
export const HIGHLIGHT_COLOR = "#06b6d4";

/** Circular dependency highlight color. */
export const CYCLE_COLOR = "#ef4444";


