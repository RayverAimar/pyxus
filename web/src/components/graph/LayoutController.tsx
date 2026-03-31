import { useLayoutForceAtlas2 } from "@react-sigma/layout-forceatlas2";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Graph from "graphology";
import { useCallback, useEffect, useState } from "react";
import { useSigma } from "@react-sigma/core";
import { Play, Loader } from "lucide-react";

const FA2_SETTINGS = {
  gravity: 5,
  scalingRatio: 10,
  slowDown: 5,
  barnesHutOptimize: true,
  strongGravityMode: true,
};

interface LayoutControllerProps {
  iterations?: number;
  onLayoutReady?: () => void;
}

/** Runs ForceAtlas2 synchronously and assigns positions to the graph. */
export function LayoutController({ iterations = 200, onLayoutReady }: LayoutControllerProps) {
  const sigma = useSigma();
  const { assign } = useLayoutForceAtlas2({
    iterations,
    settings: FA2_SETTINGS,
  });
  const [hasRun, setHasRun] = useState(false);
  const [computing, setComputing] = useState(false);

  useEffect(() => {
    assign();
    setHasRun(true);
    onLayoutReady?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRelayout = useCallback(() => {
    setComputing(true);

    // Use setTimeout to let React render the loading state before blocking
    setTimeout(() => {
      const graph = sigma.getGraph();

      // Check if any nodes are hidden
      let hasHidden = false;
      graph.forEachNode((_node, attrs) => {
        if (attrs.hidden) hasHidden = true;
      });

      if (!hasHidden) {
        assign();
        setComputing(false);
        return;
      }

      // Build a subgraph with only visible nodes and edges
      const sub = new Graph({ multi: true });
      const visibleNodes: string[] = [];

      graph.forEachNode((node, attrs) => {
        if (!attrs.hidden) {
          visibleNodes.push(node);
          // Randomize positions so FA2 starts fresh without the old layout shape
          const angle = Math.random() * 2 * Math.PI;
          const radius = 50 + Math.random() * 50;
          sub.addNode(node, {
            ...attrs,
            x: Math.cos(angle) * radius,
            y: Math.sin(angle) * radius,
          });
        }
      });

      graph.forEachEdge((_edge, attrs, source, target) => {
        if (sub.hasNode(source) && sub.hasNode(target) && !attrs.hidden) {
          sub.addEdge(source, target, { ...attrs });
        }
      });

      // Run ForceAtlas2 on the clean subgraph
      forceAtlas2.assign(sub, { iterations, settings: FA2_SETTINGS });

      // Copy positions back to the main graph
      sub.forEachNode((node, attrs) => {
        graph.setNodeAttribute(node, "x", attrs.x);
        graph.setNodeAttribute(node, "y", attrs.y);
      });

      sigma.refresh();
      setComputing(false);
    }, 50);
  }, [assign, iterations, sigma]);

  if (!hasRun) return null;

  return (
    <div style={{ position: "absolute", bottom: 16, left: 16, zIndex: 10 }}>
      <button
        onClick={handleRelayout}
        disabled={computing}
        className="flex items-center gap-1.5 rounded-lg bg-gray-800/60 px-3 py-1.5 text-xs text-gray-400 border border-gray-700/50 hover:bg-gray-700/60 hover:text-gray-300 transition-colors backdrop-blur-sm disabled:opacity-50"
      >
        {computing ? (
          <Loader size={12} className="animate-spin" />
        ) : (
          <Play size={12} />
        )}
        {computing ? "Optimizing..." : "Re-layout"}
      </button>
    </div>
  );
}
