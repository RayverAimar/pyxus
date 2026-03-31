import { useEffect } from "react";
import { useSigma } from "@react-sigma/core";
import { EDGE_COLORS, CYCLE_COLOR } from "../../utils/colors";
import { isInDisabledFolder } from "../../utils/folders";
import type { SymbolKind, RelationKind } from "../../types/graph";

interface GraphFiltersProps {
  enabledNodeKinds: Set<SymbolKind>;
  enabledEdgeKinds: Set<RelationKind>;
  highlightedCycle: string[];
  disabledFolders: Set<string>;
}

export function GraphFilters({ enabledNodeKinds, enabledEdgeKinds, highlightedCycle, disabledFolders }: GraphFiltersProps) {
  const sigma = useSigma();

  useEffect(() => {
    const graph = sigma.getGraph();
    const cycleFiles = new Set(highlightedCycle);

    // Filter nodes by kind and folder
    graph.forEachNode((node, attrs) => {
      const kind = attrs.nodeKind as SymbolKind;
      const file = attrs.file as string;
      const hiddenByKind = !enabledNodeKinds.has(kind);
      const hiddenByFolder = disabledFolders.size > 0 && isInDisabledFolder(file, disabledFolders);
      graph.setNodeAttribute(node, "hidden", hiddenByKind || hiddenByFolder);
    });

    // Filter edges + reset any previous cycle highlighting
    graph.forEachEdge((edge, attrs, source, target) => {
      const sourceHidden = graph.getNodeAttribute(source, "hidden") as boolean;
      const targetHidden = graph.getNodeAttribute(target, "hidden") as boolean;
      const edgeKind = attrs.edgeKind as RelationKind;
      const hidden = sourceHidden || targetHidden || !enabledEdgeKinds.has(edgeKind);

      graph.setEdgeAttribute(edge, "hidden", hidden);
      // Always restore original color/size so previous cycle highlights are cleared
      graph.setEdgeAttribute(edge, "color", EDGE_COLORS[edgeKind] ?? "#1a1f2e");
      graph.setEdgeAttribute(edge, "size", 0.5);
    });

    // Apply cycle highlights on top
    if (cycleFiles.size > 0) {
      graph.forEachEdge((edge, _attrs, source, target) => {
        const sourceFile = graph.getNodeAttribute(source, "file") as string;
        const targetFile = graph.getNodeAttribute(target, "file") as string;
        const sourceKind = graph.getNodeAttribute(source, "nodeKind") as string;
        const targetKind = graph.getNodeAttribute(target, "nodeKind") as string;
        if (
          sourceKind === "module" &&
          targetKind === "module" &&
          cycleFiles.has(sourceFile) &&
          cycleFiles.has(targetFile)
        ) {
          graph.setEdgeAttribute(edge, "color", CYCLE_COLOR);
          graph.setEdgeAttribute(edge, "size", 2);
        }
      });
    }

    sigma.refresh();
  }, [enabledNodeKinds, enabledEdgeKinds, highlightedCycle, disabledFolders, sigma]);

  return null;
}
