import { useCallback, useEffect, useMemo, useState } from "react";
import { useGraphData } from "./hooks/useGraphData";
import { GraphContainer } from "./components/graph/GraphContainer";
import { Header } from "./components/layout/Header";
import { Sidebar, VIEW_PRESETS, buildFolderTreeSimple } from "./components/layout/Sidebar";
import type { ViewPreset } from "./components/layout/Sidebar";
import { StatusBar } from "./components/layout/StatusBar";
import { NodeDetailPanel } from "./components/panels/NodeDetailPanel";
import { CircularDepsPanel } from "./components/panels/CircularDepsPanel";
import { SearchBar } from "./components/search/SearchBar";
import { fetchImports } from "./api/client";
import { isInDisabledFolder } from "./utils/folders";
import type { SymbolKind, RelationKind } from "./types/graph";

const ALL_NODE_KINDS = new Set<SymbolKind>([
  "module", "class", "function", "method", "property", "classmethod", "staticmethod",
]);

const ALL_EDGE_KINDS = new Set<RelationKind>([
  "defines", "has_method", "calls", "imports", "extends",
]);

type ActivePanel = "node" | "circulardeps" | null;

export function App() {
  const { data, loading, error } = useGraphData();
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [activePanel, setActivePanel] = useState<ActivePanel>(null);
  const [highlightedCycle, setHighlightedCycle] = useState<string[]>([]);

  // Filters & views
  const [enabledNodeKinds, setEnabledNodeKinds] = useState<Set<SymbolKind>>(ALL_NODE_KINDS);
  const [enabledEdgeKinds, setEnabledEdgeKinds] = useState<Set<RelationKind>>(ALL_EDGE_KINDS);
  const [activeView, setActiveView] = useState<ViewPreset>("all");
  const [disabledFolders, setDisabledFolders] = useState<Set<string>>(new Set());

  // Issue counts (fetched once)
  const [circularDepsCount, setCircularDepsCount] = useState(0);

  useEffect(() => {
    fetchImports()
      .then((r) => setCircularDepsCount(r.circular_imports.length))
      .catch((err: Error) => console.warn("Failed to load imports:", err.message));
  }, []);

  // Compute node/edge counts from data
  const nodeCounts = useMemo(() => {
    if (!data) return {};
    const counts: Record<string, number> = {};
    for (const node of data.nodes) {
      counts[node.kind] = (counts[node.kind] ?? 0) + 1;
    }
    return counts;
  }, [data]);

  const edgeCounts = useMemo(() => {
    if (!data) return {};
    const counts: Record<string, number> = {};
    for (const edge of data.edges) {
      counts[edge.kind] = (counts[edge.kind] ?? 0) + 1;
    }
    return counts;
  }, [data]);

  // Build folder tree from node file paths
  const folderTree = useMemo(() => {
    if (!data) return [];
    const fileCounts: Record<string, number> = {};
    for (const node of data.nodes) {
      fileCounts[node.file] = (fileCounts[node.file] ?? 0) + 1;
    }
    return buildFolderTreeSimple(fileCounts);
  }, [data]);

  // Compute visible node/edge counts based on active filters
  const visibleStats = useMemo(() => {
    if (!data) return null;
    const visibleNodeIds = new Set<string>();
    for (const node of data.nodes) {
      if (enabledNodeKinds.has(node.kind) && !isInDisabledFolder(node.file, disabledFolders)) {
        visibleNodeIds.add(node.id);
      }
    }
    let visibleEdges = 0;
    for (const edge of data.edges) {
      if (enabledEdgeKinds.has(edge.kind) && visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)) {
        visibleEdges++;
      }
    }
    return { ...data.stats, nodeCount: visibleNodeIds.size, edgeCount: visibleEdges };
  }, [data, enabledNodeKinds, enabledEdgeKinds, disabledFolders]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
      if (e.key === "Escape" && !searchOpen) {
        setSelectedNode(null);
        setActivePanel(null);
        setHighlightedCycle([]);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [searchOpen]);

  const handleSelectNode = useCallback((nodeId: string | null) => {
    setSelectedNode(nodeId);
    if (nodeId) {
      setActivePanel("node");
      setHighlightedCycle([]);
    } else {
      setActivePanel(null);
    }
  }, []);

  const handleSearchSelect = useCallback((symbolId: string) => {
    setSelectedNode(symbolId);
    setActivePanel("node");
  }, []);

  const handleToggleNodeKind = useCallback((kind: SymbolKind) => {
    setEnabledNodeKinds((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) {
        next.delete(kind);
      } else {
        next.add(kind);
      }
      return next;
    });
  }, []);

  const handleToggleEdgeKind = useCallback((kind: RelationKind) => {
    setEnabledEdgeKinds((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) {
        next.delete(kind);
      } else {
        next.add(kind);
      }
      return next;
    });
  }, []);

  const handleApplyView = useCallback((view: ViewPreset) => {
    const config = VIEW_PRESETS[view];
    setEnabledNodeKinds(new Set(config.nodeKinds));
    setEnabledEdgeKinds(new Set(config.edgeKinds));
    setActiveView(view);
  }, []);

  const handleToggleFolder = useCallback((folderPath: string) => {
    setDisabledFolders((prev) => {
      const next = new Set(prev);
      if (next.has(folderPath)) {
        // Re-enable: remove this folder and any child folders
        for (const f of next) {
          if (f === folderPath || f.startsWith(folderPath + "/")) {
            next.delete(f);
          }
        }
      } else {
        next.add(folderPath);
      }
      return next;
    });
  }, []);

  const handleShowCircularDeps = useCallback(() => {
    setActivePanel("circulardeps");
    setSelectedNode(null);
  }, []);

  const handleClosePanel = useCallback(() => {
    setActivePanel(null);
    setSelectedNode(null);
    setHighlightedCycle([]);
  }, []);

  const handleHighlightCycle = setHighlightedCycle;

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#06060a]">
        <div className="text-center">
          <div className="mb-3 text-lg font-semibold text-white">Pyxus</div>
          <div className="text-sm text-gray-600">Loading graph...</div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#06060a]">
        <div className="text-center">
          <div className="mb-3 text-lg font-semibold text-white">Pyxus</div>
          <div className="text-sm text-red-400">
            {error ?? "No graph data available. Run `pyxus analyze` first."}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-[#06060a] text-gray-100">
      <Header
        stats={visibleStats}
        onSearchFocus={() => setSearchOpen(true)}
      />

      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          enabledNodeKinds={enabledNodeKinds}
          enabledEdgeKinds={enabledEdgeKinds}
          onToggleNodeKind={handleToggleNodeKind}
          onToggleEdgeKind={handleToggleEdgeKind}
          nodeCounts={nodeCounts}
          edgeCounts={edgeCounts}
          circularDepsCount={circularDepsCount}
          onShowCircularDeps={handleShowCircularDeps}
          activeView={activeView}
          onApplyView={handleApplyView}
          folderTree={folderTree}
          disabledFolders={disabledFolders}
          onToggleFolder={handleToggleFolder}
        />

        <div className="relative flex-1">
          <GraphContainer
            data={data}
            selectedNode={selectedNode}
            onSelectNode={handleSelectNode}
            enabledNodeKinds={enabledNodeKinds}
            enabledEdgeKinds={enabledEdgeKinds}
            highlightedCycle={highlightedCycle}
            disabledFolders={disabledFolders}
          />

          {/* Panels overlay the graph — absolute positioned, not in flex flow */}
          {activePanel === "node" && selectedNode && (
            <div className="absolute top-0 right-0 h-full z-10">
              <NodeDetailPanel
                selectedNode={selectedNode}
                onClose={handleClosePanel}
                onNavigate={handleSelectNode}
                graphNodes={data.nodes}
              />
            </div>
          )}

          {activePanel === "circulardeps" && (
            <div className="absolute top-0 right-0 h-full z-10">
              <CircularDepsPanel
                onClose={handleClosePanel}
                onHighlightCycle={handleHighlightCycle}
              />
            </div>
          )}
        </div>
      </div>

      <StatusBar stats={visibleStats} />

      <SearchBar
        isOpen={searchOpen}
        onClose={() => setSearchOpen(false)}
        onSelect={handleSearchSelect}
      />
    </div>
  );
}
