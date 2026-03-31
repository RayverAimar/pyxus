import { useState } from "react";
import { ChevronDown, ChevronRight, AlertTriangle, Eye, EyeOff, Layers, Network, GitBranch, Zap, LayoutGrid, Folder, FolderOpen } from "lucide-react";
import { NODE_COLORS, EDGE_COLORS } from "../../utils/colors";
import type { SymbolKind, RelationKind } from "../../types/graph";

export type ViewPreset = "all" | "imports" | "classes" | "calls";

interface ViewConfig {
  nodeKinds: Set<SymbolKind>;
  edgeKinds: Set<RelationKind>;
}

export const VIEW_PRESETS: Record<ViewPreset, ViewConfig> = {
  all: {
    nodeKinds: new Set<SymbolKind>(["module", "class", "function", "method", "property", "classmethod", "staticmethod"]),
    edgeKinds: new Set<RelationKind>(["defines", "has_method", "calls", "imports", "extends"]),
  },
  imports: {
    nodeKinds: new Set<SymbolKind>(["module"]),
    edgeKinds: new Set<RelationKind>(["imports"]),
  },
  classes: {
    nodeKinds: new Set<SymbolKind>(["class", "method", "property", "classmethod", "staticmethod"]),
    edgeKinds: new Set<RelationKind>(["has_method", "extends"]),
  },
  calls: {
    nodeKinds: new Set<SymbolKind>(["function", "method", "classmethod", "staticmethod"]),
    edgeKinds: new Set<RelationKind>(["calls"]),
  },
};

const NODE_KINDS: SymbolKind[] = [
  "module", "class", "function", "method", "property", "classmethod", "staticmethod",
];

const EDGE_KINDS: RelationKind[] = [
  "defines", "has_method", "calls", "imports", "extends",
];

const EDGE_LABELS: Record<RelationKind, string> = {
  defines: "Defines",
  has_method: "Has Method",
  calls: "Calls",
  imports: "Imports",
  extends: "Extends",
};

/** A node in the folder tree. */
export interface FolderNode {
  name: string;
  path: string;
  count: number;
  children: FolderNode[];
}

/** Build a folder tree from file paths with node counts per file. */
export function buildFolderTreeSimple(fileCounts: Record<string, number>): FolderNode[] {
  // Collect all unique directory paths with their total node counts
  const dirCounts: Record<string, number> = {};

  for (const [filePath, count] of Object.entries(fileCounts)) {
    const parts = filePath.split("/");
    // Accumulate counts at each directory level
    for (let i = 1; i <= parts.length - 1; i++) {
      const dir = parts.slice(0, i).join("/");
      dirCounts[dir] = (dirCounts[dir] ?? 0) + count;
    }
  }

  // Build tree from flat directory list
  const allDirs = Object.keys(dirCounts).sort();
  const rootNodes: FolderNode[] = [];

  function getOrCreate(path: string): FolderNode {
    const parts = path.split("/");
    const name = parts[parts.length - 1]!;
    const parentPath = parts.slice(0, -1).join("/");

    const node: FolderNode = {
      name,
      path,
      count: dirCounts[path] ?? 0,
      children: [],
    };

    if (parentPath && allDirs.includes(parentPath)) {
      // Find or create parent
      const parent = nodeMap.get(parentPath);
      if (parent) {
        parent.children.push(node);
      }
    } else {
      rootNodes.push(node);
    }

    return node;
  }

  const nodeMap = new Map<string, FolderNode>();
  for (const dir of allDirs) {
    nodeMap.set(dir, getOrCreate(dir));
  }

  return rootNodes;
}

interface SidebarProps {
  enabledNodeKinds: Set<SymbolKind>;
  enabledEdgeKinds: Set<RelationKind>;
  onToggleNodeKind: (kind: SymbolKind) => void;
  onToggleEdgeKind: (kind: RelationKind) => void;
  nodeCounts: Record<string, number>;
  edgeCounts: Record<string, number>;
  circularDepsCount: number;
  onShowCircularDeps: () => void;
  activeView: ViewPreset;
  onApplyView: (view: ViewPreset) => void;
  folderTree: FolderNode[];
  disabledFolders: Set<string>;
  onToggleFolder: (folderPath: string) => void;
}

const VIEW_ITEMS: { id: ViewPreset; label: string; icon: typeof Layers }[] = [
  { id: "all", label: "All", icon: LayoutGrid },
  { id: "imports", label: "Imports Only", icon: Network },
  { id: "classes", label: "Classes", icon: GitBranch },
  { id: "calls", label: "Calls", icon: Zap },
];

function Section({
  title,
  defaultOpen = true,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-gray-800/60">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-1.5 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500 hover:text-gray-400 transition-colors"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        {title}
      </button>
      {open && <div className="px-3 pb-3">{children}</div>}
    </div>
  );
}

/** Recursive folder tree row. */
function FolderRow({
  node,
  depth,
  disabledFolders,
  onToggle,
}: {
  node: FolderNode;
  depth: number;
  disabledFolders: Set<string>;
  onToggle: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  // A folder is effectively disabled if it or any ancestor is in the disabled set
  const selfDisabled = disabledFolders.has(node.path);
  let ancestorDisabled = false;
  if (!selfDisabled) {
    for (const f of disabledFolders) {
      if (node.path.startsWith(f + "/")) { ancestorDisabled = true; break; }
    }
  }
  const disabled = selfDisabled || ancestorDisabled;
  const hasChildren = node.children.length > 0;

  return (
    <>
      <div
        className={`flex items-center gap-1 rounded px-1 py-0.5 text-xs transition-colors ${
          disabled ? "text-gray-600" : "text-gray-300"
        } hover:bg-gray-800/50`}
        style={{ paddingLeft: `${depth * 12 + 4}px` }}
      >
        {hasChildren ? (
          <button
            onClick={() => setExpanded(!expanded)}
            className="shrink-0 text-gray-600 hover:text-gray-400"
          >
            {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          </button>
        ) : (
          <span className="w-[10px] shrink-0" />
        )}
        <button
          onClick={() => onToggle(node.path)}
          className="flex flex-1 items-center gap-1.5 min-w-0"
        >
          {disabled ? (
            <Folder size={11} className="shrink-0 text-gray-700" />
          ) : (
            <FolderOpen size={11} className="shrink-0 text-blue-400/70" />
          )}
          <span className="truncate">{node.name}</span>
          <span className="ml-auto text-[10px] text-gray-600 shrink-0">{node.count}</span>
          {disabled ? (
            <EyeOff size={9} className="shrink-0 text-gray-700" />
          ) : (
            <Eye size={9} className="shrink-0 text-gray-600" />
          )}
        </button>
      </div>
      {expanded && hasChildren && node.children.map((child) => (
        <FolderRow
          key={child.path}
          node={child}
          depth={depth + 1}
          disabledFolders={disabledFolders}
          onToggle={onToggle}
        />
      ))}
    </>
  );
}

/** Left sidebar with filters, folder tree, and issue shortcuts. */
export function Sidebar({
  enabledNodeKinds,
  enabledEdgeKinds,
  onToggleNodeKind,
  onToggleEdgeKind,
  nodeCounts,
  edgeCounts,
  circularDepsCount,
  onShowCircularDeps,
  activeView,
  onApplyView,
  folderTree,
  disabledFolders,
  onToggleFolder,
}: SidebarProps) {
  return (
    <div className="flex h-full w-52 flex-col border-r border-gray-800/60 bg-[#0a0a10] overflow-y-auto">
      <Section title="Views">
        <div className="space-y-0.5">
          {VIEW_ITEMS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => onApplyView(id)}
              className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs transition-colors ${
                activeView === id
                  ? "bg-cyan-500/10 text-cyan-400"
                  : "text-gray-400 hover:bg-gray-800/50 hover:text-gray-200"
              }`}
            >
              <Icon size={12} className="shrink-0" />
              <span>{label}</span>
            </button>
          ))}
        </div>
      </Section>

      <Section title="Folders" defaultOpen={false}>
        <div className="space-y-0">
          {folderTree.map((node) => (
            <FolderRow
              key={node.path}
              node={node}
              depth={0}
              disabledFolders={disabledFolders}
              onToggle={onToggleFolder}
            />
          ))}
        </div>
      </Section>

      <Section title="Node Types">
        <div className="space-y-0.5">
          {NODE_KINDS.map((kind) => {
            const enabled = enabledNodeKinds.has(kind);
            const count = nodeCounts[kind] ?? 0;
            return (
              <button
                key={kind}
                onClick={() => onToggleNodeKind(kind)}
                className={`flex w-full items-center gap-2 rounded px-2 py-1 text-xs transition-colors ${
                  enabled
                    ? "text-gray-300 hover:bg-gray-800/50"
                    : "text-gray-600 hover:bg-gray-800/30"
                }`}
              >
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full shrink-0 transition-opacity"
                  style={{
                    backgroundColor: NODE_COLORS[kind],
                    opacity: enabled ? 1 : 0.25,
                  }}
                />
                <span className="capitalize truncate">{kind}</span>
                <span className="ml-auto text-[10px] text-gray-600">{count}</span>
                {enabled ? (
                  <Eye size={10} className="shrink-0 text-gray-600" />
                ) : (
                  <EyeOff size={10} className="shrink-0 text-gray-700" />
                )}
              </button>
            );
          })}
        </div>
      </Section>

      <Section title="Edge Types">
        <div className="space-y-0.5">
          {EDGE_KINDS.map((kind) => {
            const enabled = enabledEdgeKinds.has(kind);
            const count = edgeCounts[kind] ?? 0;
            return (
              <button
                key={kind}
                onClick={() => onToggleEdgeKind(kind)}
                className={`flex w-full items-center gap-2 rounded px-2 py-1 text-xs transition-colors ${
                  enabled
                    ? "text-gray-300 hover:bg-gray-800/50"
                    : "text-gray-600 hover:bg-gray-800/30"
                }`}
              >
                <span
                  className="inline-block h-1 w-4 rounded-full shrink-0 transition-opacity"
                  style={{
                    backgroundColor: EDGE_COLORS[kind]?.replace(/[\d.]+\)$/, "0.8)") ?? "#666",
                    opacity: enabled ? 1 : 0.25,
                  }}
                />
                <span className="truncate">{EDGE_LABELS[kind]}</span>
                <span className="ml-auto text-[10px] text-gray-600">{count}</span>
                {enabled ? (
                  <Eye size={10} className="shrink-0 text-gray-600" />
                ) : (
                  <EyeOff size={10} className="shrink-0 text-gray-700" />
                )}
              </button>
            );
          })}
        </div>
      </Section>

      <Section title="Issues">
        <div className="space-y-1">
          <button
            onClick={onShowCircularDeps}
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs text-gray-400 hover:bg-gray-800/50 hover:text-gray-200 transition-colors"
          >
            <AlertTriangle size={12} className="shrink-0 text-amber-500" />
            <span>Circular Deps</span>
            {circularDepsCount > 0 && (
              <span className="ml-auto rounded-full bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-400">
                {circularDepsCount}
              </span>
            )}
          </button>
        </div>
      </Section>
    </div>
  );
}
