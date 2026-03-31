import { useEffect } from "react";
import { useSigma } from "@react-sigma/core";
import type { GraphData } from "../../types/graph";
import { NODE_COLORS, EDGE_COLORS } from "../../utils/colors";
import type { SymbolKind, RelationKind } from "../../types/graph";

interface GraphLoaderProps {
  data: GraphData;
}

/** Load graph data from the API into the Sigma.js instance. */
export function GraphLoader({ data }: GraphLoaderProps) {
  const sigma = useSigma();

  useEffect(() => {
    const graph = sigma.getGraph();
    graph.clear();

    for (const node of data.nodes) {
      const baseSize = node.size;
      const degreeBoost = Math.min(node.degree * 0.3, 6);
      const finalSize = baseSize + degreeBoost;

      graph.addNode(node.id, {
        x: Math.random() * 100,
        y: Math.random() * 100,
        size: finalSize,
        label: node.label,
        color: NODE_COLORS[node.kind as SymbolKind] ?? "#999",
        nodeKind: node.kind,
        file: node.file,
        nodeLine: node.line,
      });
    }

    for (const edge of data.edges) {
      if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue;
      if (graph.hasEdge(edge.source, edge.target)) continue;

      graph.addEdge(edge.source, edge.target, {
        size: 0.5,
        color: EDGE_COLORS[edge.kind as RelationKind] ?? "#1a1f2e",
        edgeKind: edge.kind,
        confidence: edge.confidence,
      });
    }

    // Force sigma to re-render and center the camera
    sigma.refresh();
    sigma.getCamera().animatedReset({ duration: 0 });
  }, [data, sigma]);

  return null;
}
