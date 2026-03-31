import { useEffect } from "react";
import { useSigma } from "@react-sigma/core";
import { DIMMED_NODE_COLOR, DIMMED_EDGE_COLOR, HIGHLIGHT_COLOR } from "../../utils/colors";

interface NodeHighlighterProps {
  selectedNode: string | null;
  hoveredNode: string | null;
}

/** Hover: show only hovered node label. Click: highlight neighbors + show their labels. */
export function NodeHighlighter({ selectedNode, hoveredNode }: NodeHighlighterProps) {
  const sigma = useSigma();

  useEffect(() => {
    // Nothing active — reset everything
    if (!selectedNode && !hoveredNode) {
      sigma.setSetting("nodeReducer", null);
      sigma.setSetting("edgeReducer", null);
      return;
    }

    const graph = sigma.getGraph();

    // HOVER only (no selection) — just show the hovered node's label
    if (hoveredNode && !selectedNode) {
      sigma.setSetting("nodeReducer", (node, data) => {
        if (node === hoveredNode) {
          return { ...data, forceLabel: true, size: (data.size as number) * 1.2, zIndex: 2 };
        }
        return data;
      });
      sigma.setSetting("edgeReducer", null);
      return;
    }

    // CLICK (selection) — highlight neighbors, dim the rest.
    // Only show label on the selected node, NOT on all neighbors.
    if (selectedNode) {
      const neighbors = new Set(graph.neighbors(selectedNode));

      sigma.setSetting("nodeReducer", (node, data) => {
        if (node === selectedNode) {
          return {
            ...data,
            highlighted: true,
            forceLabel: true,
            color: HIGHLIGHT_COLOR,
            size: (data.size as number) * 1.3,
            zIndex: 2,
          };
        }
        if (neighbors.has(node)) {
          return { ...data, size: (data.size as number) * 1.1, zIndex: 1 };
        }
        return {
          ...data,
          color: DIMMED_NODE_COLOR,
          size: (data.size as number) * 0.6,
          zIndex: -1,
        };
      });

      sigma.setSetting("edgeReducer", (edge, data) => {
        const [source, target] = graph.extremities(edge);
        if (source === selectedNode || target === selectedNode) {
          // Keep original edge color but make it more visible
          return { ...data, size: 1.5, zIndex: 1 };
        }
        return { ...data, color: DIMMED_EDGE_COLOR, size: 0.2, zIndex: -1 };
      });
    }
  }, [selectedNode, hoveredNode, sigma]);

  return null;
}
