import { useCallback, useMemo, useState } from "react";
import { SigmaContainer, useSigma } from "@react-sigma/core";
import "@react-sigma/core/lib/style.css";
import Graph from "graphology";
import type { GraphData, SymbolKind, RelationKind } from "../../types/graph";
import { NODE_COLORS, EDGE_COLORS } from "../../utils/colors";
import { GraphEvents } from "./GraphEvents";
import { GraphFilters } from "./GraphFilters";
import { NodeHighlighter } from "./NodeHighlighter";
import { LayoutController } from "./LayoutController";
import { ZoomIn, ZoomOut, Maximize } from "lucide-react";
import type { Settings } from "sigma/settings";
import type { NodeDisplayData, PartialButFor } from "sigma/types";

/** Custom label renderer — dark background instead of white. */
function drawDarkLabel(
  context: CanvasRenderingContext2D,
  data: PartialButFor<NodeDisplayData, "x" | "y" | "size" | "label" | "color">,
  settings: Settings,
): void {
  if (!data.label) return;

  const size = settings.labelSize;
  const font = settings.labelFont;
  const weight = settings.labelWeight;

  context.font = `${weight} ${size}px ${font}`;
  const textWidth = context.measureText(data.label).width;

  const px = 4;
  const py = 2;
  const boxX = data.x + data.size + 3;
  const boxY = data.y - size / 2 - py;

  // Dark background
  context.fillStyle = "rgba(10, 10, 16, 0.85)";
  context.beginPath();
  context.roundRect(boxX - px, boxY, textWidth + px * 2, size + py * 2, 4);
  context.fill();

  // Light text
  context.fillStyle = "#e5e7eb";
  context.fillText(data.label, boxX, data.y + size / 3);
}

/** Custom hover renderer — dark background with colored border. */
function drawDarkHover(
  context: CanvasRenderingContext2D,
  data: PartialButFor<NodeDisplayData, "x" | "y" | "size" | "label" | "color">,
  settings: Settings,
): void {
  if (!data.label) return;

  const size = settings.labelSize + 1;
  const font = settings.labelFont;
  const weight = "600";

  context.font = `${weight} ${size}px ${font}`;
  const textWidth = context.measureText(data.label).width;

  const px = 6;
  const py = 4;
  const boxX = data.x + data.size + 3;
  const boxY = data.y - size / 2 - py;

  // Dark background with subtle border
  context.fillStyle = "rgba(10, 10, 16, 0.92)";
  context.strokeStyle = data.color;
  context.lineWidth = 1;
  context.beginPath();
  context.roundRect(boxX - px, boxY, textWidth + px * 2, size + py * 2, 5);
  context.fill();
  context.stroke();

  // Light text
  context.fillStyle = "#f3f4f6";
  context.fillText(data.label, boxX, data.y + size / 3);
}

interface GraphContainerProps {
  data: GraphData;
  selectedNode: string | null;
  onSelectNode: (nodeId: string | null) => void;
  enabledNodeKinds: Set<SymbolKind>;
  enabledEdgeKinds: Set<RelationKind>;
  highlightedCycle: string[];
  disabledFolders: Set<string>;
}

/** Build a Graphology instance from API data. */
function buildGraph(data: GraphData): Graph {
  const graph = new Graph({ multi: true });

  const nodeCount = data.nodes.length;
  for (let i = 0; i < nodeCount; i++) {
    const node = data.nodes[i]!;
    const baseSize = node.size;
    const degreeBoost = Math.min(node.degree * 0.3, 6);

    const angle = (2 * Math.PI * i) / nodeCount + (Math.random() - 0.5) * 0.5;
    const radius = 50 + Math.random() * 50;

    graph.addNode(node.id, {
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius,
      size: baseSize + degreeBoost,
      label: node.label,
      color: NODE_COLORS[node.kind as SymbolKind] ?? "#999",
      nodeKind: node.kind,
      file: node.file,
      nodeLine: node.line,
    });
  }

  for (const edge of data.edges) {
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue;

    graph.addEdgeWithKey(edge.id, edge.source, edge.target, {
      size: 0.5,
      color: EDGE_COLORS[edge.kind as RelationKind] ?? "#1a1f2e",
      edgeKind: edge.kind,
      confidence: edge.confidence,
    });
  }

  return graph;
}

/** Zoom control buttons — must be inside SigmaContainer to access useSigma(). */
function ZoomControls() {
  const sigma = useSigma();

  return (
    <div
      style={{ position: "absolute", bottom: 16, right: 16, zIndex: 50, pointerEvents: "auto" }}
      className="flex flex-col gap-1"
    >
      <button
        onClick={(e) => { e.stopPropagation(); sigma.getCamera().animatedZoom({ duration: 200 }); }}
        className="flex items-center justify-center w-8 h-8 rounded-md bg-gray-800/80 text-gray-400 hover:bg-gray-700 hover:text-gray-200 transition-colors backdrop-blur-sm cursor-pointer"
        title="Zoom in"
      >
        <ZoomIn size={16} />
      </button>
      <button
        onClick={(e) => { e.stopPropagation(); sigma.getCamera().animatedUnzoom({ duration: 200 }); }}
        className="flex items-center justify-center w-8 h-8 rounded-md bg-gray-800/80 text-gray-400 hover:bg-gray-700 hover:text-gray-200 transition-colors backdrop-blur-sm cursor-pointer"
        title="Zoom out"
      >
        <ZoomOut size={16} />
      </button>
      <button
        onClick={(e) => { e.stopPropagation(); sigma.getCamera().animatedReset({ duration: 200 }); }}
        className="flex items-center justify-center w-8 h-8 rounded-md bg-gray-800/80 text-gray-400 hover:bg-gray-700 hover:text-gray-200 transition-colors backdrop-blur-sm cursor-pointer"
        title="Fit to screen"
      >
        <Maximize size={16} />
      </button>
    </div>
  );
}

/** Loading overlay shown while layout is computing. */
function LoadingOverlay() {
  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-[#06060a]">
      <div className="text-center">
        <div className="mb-3 relative flex h-5 w-5 mx-auto">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-75" />
          <span className="relative inline-flex h-5 w-5 rounded-full bg-cyan-500" />
        </div>
        <div className="text-sm text-gray-400">Optimizing layout...</div>
      </div>
    </div>
  );
}

/** Main graph visualization container with Sigma.js. */
export function GraphContainer({
  data,
  selectedNode,
  onSelectNode,
  enabledNodeKinds,
  enabledEdgeKinds,
  highlightedCycle,
  disabledFolders,
}: GraphContainerProps) {
  const graph = useMemo(() => buildGraph(data), [data]);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [layoutReady, setLayoutReady] = useState(false);
  const handleHover = useCallback((nodeId: string | null) => setHoveredNode(nodeId), []);
  const handleLayoutReady = useCallback(() => setLayoutReady(true), []);

  return (
    <div className="graph-wrapper">
      {!layoutReady && <LoadingOverlay />}
      <SigmaContainer
        graph={graph}
        style={{ width: "100%", height: "100%", opacity: layoutReady ? 1 : 0, transition: "opacity 0.5s ease-in" }}
        settings={{
          defaultNodeColor: "#999",
          defaultEdgeColor: "#1a1f2e",
          defaultEdgeType: "line",
          labelColor: { color: "#e5e7eb" },
          labelFont: "'Inter', 'SF Pro', system-ui, sans-serif",
          labelSize: 12,
          labelWeight: "500",
          labelRenderedSizeThreshold: 100,
          defaultDrawNodeLabel: drawDarkLabel,
          defaultDrawNodeHover: drawDarkHover,
          renderEdgeLabels: false,
          enableEdgeEvents: false,
          zIndex: true,
          minCameraRatio: 0.02,
          maxCameraRatio: 10,
        }}
      >
        <GraphEvents onSelectNode={onSelectNode} onHoverNode={handleHover} />
        <GraphFilters enabledNodeKinds={enabledNodeKinds} enabledEdgeKinds={enabledEdgeKinds} highlightedCycle={highlightedCycle} disabledFolders={disabledFolders} />
        <NodeHighlighter selectedNode={selectedNode} hoveredNode={hoveredNode} />
        <LayoutController iterations={200} onLayoutReady={handleLayoutReady} />
        {layoutReady && <ZoomControls />}
      </SigmaContainer>
    </div>
  );
}
