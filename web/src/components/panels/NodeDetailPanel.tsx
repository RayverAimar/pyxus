import { useEffect, useState } from "react";
import { X, ArrowDownRight, ArrowUpLeft } from "lucide-react";
import { fetchContext } from "../../api/client";
import { NODE_COLORS } from "../../utils/colors";
import type { SymbolKind } from "../../types/graph";

interface ContextData {
  symbol: {
    name: string;
    kind: string;
    file: string;
    line: number;
    end_line: number;
    decorators: string[];
    exported: boolean;
  };
  methods: { name: string; kind: string; line: number }[];
  incoming: Record<string, { name: string; kind: string; file: string; line: number }[]>;
  outgoing: Record<string, { name: string; kind: string; file: string; line: number }[]>;
}

interface NodeDetailPanelProps {
  selectedNode: string | null;
  onClose: () => void;
  onNavigate: (nodeId: string) => void;
  graphNodes?: { id: string; label: string; kind: string; file: string; line: number }[];
}

/** Extract symbol name from ID. Format: "kind:file_path:name:line" */
function extractName(symbolId: string): string {
  const lastColon = symbolId.lastIndexOf(":");
  const beforeLast = symbolId.lastIndexOf(":", lastColon - 1);
  if (beforeLast > 0) {
    return symbolId.substring(beforeLast + 1, lastColon);
  }
  return symbolId;
}

/** Check if a symbol ID is a MODULE type. */
function isModule(symbolId: string): boolean {
  return symbolId.startsWith("module:");
}

/** Right panel showing detailed information about the selected node. */
export function NodeDetailPanel({ selectedNode, onClose, onNavigate, graphNodes }: NodeDetailPanelProps) {
  const [data, setData] = useState<ContextData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedNode) {
      setData(null);
      setError(null);
      return;
    }

    // MODULE nodes are filtered by context() — show file contents instead
    if (isModule(selectedNode)) {
      const name = extractName(selectedNode);
      // Find symbols in this file from the graph data
      const fileSymbols = (graphNodes ?? [])
        .filter((n) => n.file === name && n.kind !== "module")
        .sort((a, b) => a.line - b.line);

      setData({
        symbol: {
          name,
          kind: "module",
          file: name,
          line: 0,
          end_line: 0,
          decorators: [],
          exported: true,
        },
        methods: fileSymbols.map((s) => ({ name: s.label, kind: s.kind, line: s.line })),
        incoming: {},
        outgoing: {},
      });
      setLoading(false);
      setError(null);
      return;
    }

    const name = extractName(selectedNode);

    setLoading(true);
    setError(null);
    fetchContext(name)
      .then((result) => {
        if (result.error) {
          setError(result.error as string);
          setData(null);
        } else if (result.disambiguation) {
          setError(null);
          setData(null);
        } else {
          setData(result as ContextData);
          setError(null);
        }
      })
      .catch(() => {
        setError("Failed to load symbol data");
        setData(null);
      })
      .finally(() => setLoading(false));
  }, [selectedNode, graphNodes]);

  if (!selectedNode) return null;

  const displayName = extractName(selectedNode);

  return (
    <div className="flex h-full w-80 flex-col border-l border-gray-800/60 bg-[#0a0a10]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-800/60 px-4 py-3">
        <h2 className="text-sm font-semibold text-white truncate">
          {data?.symbol.name ?? displayName}
        </h2>
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-gray-300 transition-colors"
        >
          <X size={16} />
        </button>
      </div>

      {loading && (
        <div className="p-4 text-sm text-gray-500">Loading...</div>
      )}

      {error && (
        <div className="p-4 text-sm text-gray-600">{error}</div>
      )}

      {data && (
        <div className="flex-1 overflow-y-auto">
          {/* Symbol info */}
          <div className="border-b border-gray-800/60 p-4">
            <div className="flex items-center gap-2 mb-2">
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ backgroundColor: NODE_COLORS[data.symbol.kind as SymbolKind] }}
              />
              <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400 uppercase">
                {data.symbol.kind}
              </span>
            </div>
            <p className="text-xs text-gray-500 font-mono">
              {data.symbol.file}:{data.symbol.line}
            </p>
            {data.symbol.decorators.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {data.symbol.decorators.map((d) => (
                  <span key={d} className="rounded bg-gray-800 px-1.5 py-0.5 text-xs text-gray-500">
                    @{d}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Symbols grouped by kind (for modules) or methods (for classes) */}
          {data.methods.length > 0 && data.symbol.kind === "module" && (
            <div className="border-b border-gray-800/60 p-4">
              <h3 className="mb-3 text-xs font-semibold uppercase text-gray-500">
                Symbols ({data.methods.length})
              </h3>
              {Object.entries(
                data.methods.reduce<Record<string, typeof data.methods>>((acc, m) => {
                  const group = acc[m.kind] ?? [];
                  group.push(m);
                  acc[m.kind] = group;
                  return acc;
                }, {})
              ).map(([kind, items]) => (
                <div key={kind} className="mb-3">
                  <span className="text-[10px] text-gray-600 uppercase tracking-wider">{kind} ({items.length})</span>
                  <ul className="mt-1 space-y-0.5">
                    {items.map((m) => (
                      <li key={`${m.name}:${m.line}`} className="flex items-center gap-2 text-xs text-gray-400">
                        <span
                          className="inline-block h-2 w-2 rounded-full shrink-0"
                          style={{ backgroundColor: NODE_COLORS[m.kind as SymbolKind] }}
                        />
                        <span className="truncate">{m.name}</span>
                        <span className="text-gray-700 text-[10px] ml-auto shrink-0">:{m.line}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
          {data.methods.length > 0 && data.symbol.kind !== "module" && (
            <div className="border-b border-gray-800/60 p-4">
              <h3 className="mb-2 text-xs font-semibold uppercase text-gray-500">
                Methods ({data.methods.length})
              </h3>
              <ul className="space-y-1">
                {data.methods.map((m) => (
                  <li key={`${m.name}:${m.line}`} className="flex items-center gap-2 text-xs text-gray-400">
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ backgroundColor: NODE_COLORS[m.kind as SymbolKind] }}
                    />
                    {m.name}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Incoming connections */}
          {Object.keys(data.incoming).length > 0 && (
            <div className="border-b border-gray-800/60 p-4">
              <h3 className="mb-2 flex items-center gap-1 text-xs font-semibold uppercase text-gray-500">
                <ArrowUpLeft size={12} /> Incoming
              </h3>
              {Object.entries(data.incoming).map(([kind, items]) => (
                <div key={kind} className="mb-2">
                  <span className="text-xs text-gray-600 uppercase">{kind}</span>
                  <ul className="mt-1 space-y-1">
                    {items.map((item) => (
                      <li
                        key={`${item.file}:${item.name}:${item.line}`}
                        onClick={() => onNavigate(`${item.kind}:${item.file}:${item.name}:${item.line}`)}
                        className="flex items-center gap-2 text-xs text-gray-400 hover:text-gray-200 hover:bg-gray-800/50 cursor-pointer rounded px-1 py-0.5"
                      >
                        <span
                          className="inline-block h-2 w-2 rounded-full shrink-0"
                          style={{ backgroundColor: NODE_COLORS[item.kind as SymbolKind] }}
                        />
                        <span>{item.name}</span>
                        <span className="text-gray-600 font-mono text-[10px] truncate">
                          {item.file}:{item.line}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}

          {/* Outgoing connections */}
          {Object.keys(data.outgoing).length > 0 && (
            <div className="p-4">
              <h3 className="mb-2 flex items-center gap-1 text-xs font-semibold uppercase text-gray-500">
                <ArrowDownRight size={12} /> Outgoing
              </h3>
              {Object.entries(data.outgoing).map(([kind, items]) => (
                <div key={kind} className="mb-2">
                  <span className="text-xs text-gray-600 uppercase">{kind}</span>
                  <ul className="mt-1 space-y-1">
                    {items.map((item) => (
                      <li
                        key={`${item.file}:${item.name}:${item.line}`}
                        onClick={() => onNavigate(`${item.kind}:${item.file}:${item.name}:${item.line}`)}
                        className="flex items-center gap-2 text-xs text-gray-400 hover:text-gray-200 hover:bg-gray-800/50 cursor-pointer rounded px-1 py-0.5"
                      >
                        <span
                          className="inline-block h-2 w-2 rounded-full shrink-0"
                          style={{ backgroundColor: NODE_COLORS[item.kind as SymbolKind] }}
                        />
                        <span>{item.name}</span>
                        <span className="text-gray-600 font-mono text-[10px] truncate">
                          {item.file}:{item.line}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
