import { useEffect, useState } from "react";
import { X, AlertTriangle, ArrowRight } from "lucide-react";
import { fetchImports } from "../../api/client";
import type { ImportsResponse } from "../../types/graph";

interface CircularDepsPanelProps {
  onClose: () => void;
  onHighlightCycle: (cycle: string[]) => void;
}

/** Right panel showing detected circular import chains. */
export function CircularDepsPanel({ onClose, onHighlightCycle }: CircularDepsPanelProps) {
  const [data, setData] = useState<ImportsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeCycle, setActiveCycle] = useState<number | null>(null);

  useEffect(() => {
    fetchImports()
      .then(setData)
      .catch(() => setError("Failed to load import data"))
      .finally(() => setLoading(false));
  }, []);

  const handleCycleClick = (cycle: string[], index: number) => {
    if (activeCycle === index) {
      setActiveCycle(null);
      onHighlightCycle([]);
    } else {
      setActiveCycle(index);
      onHighlightCycle(cycle);
    }
  };

  return (
    <div className="flex h-full w-80 flex-col border-l border-gray-800/60 bg-[#0a0a10]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-800/60 px-4 py-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
          <AlertTriangle size={14} className="text-amber-500" />
          Circular Dependencies
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
          {/* Summary */}
          <div className="border-b border-gray-800/60 p-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="text-center">
                <div className={`text-lg font-semibold ${data.circular_imports.length > 0 ? "text-amber-400" : "text-emerald-400"}`}>
                  {data.circular_imports.length}
                </div>
                <div className="text-[10px] text-gray-500 uppercase">Cycles</div>
              </div>
              <div className="text-center">
                <div className="text-lg font-semibold text-white">{data.total_modules}</div>
                <div className="text-[10px] text-gray-500 uppercase">Modules</div>
              </div>
            </div>
          </div>

          {data.circular_imports.length === 0 ? (
            <div className="p-4 text-center">
              <div className="text-sm text-emerald-400 mb-1">No circular dependencies</div>
              <div className="text-xs text-gray-600">Your import graph is clean.</div>
            </div>
          ) : (
            <div className="p-3 space-y-2">
              {data.circular_imports.map((cycle, i) => (
                <button
                  key={i}
                  onClick={() => handleCycleClick(cycle, i)}
                  className={`w-full rounded-lg border p-3 text-left transition-colors ${
                    activeCycle === i
                      ? "border-amber-500/50 bg-amber-500/5"
                      : "border-gray-800/60 bg-gray-900/30 hover:border-gray-700/60"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] font-medium uppercase text-gray-500">
                      Cycle {i + 1}
                    </span>
                    <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-400">
                      {cycle.length} modules
                    </span>
                  </div>
                  <div className="space-y-1">
                    {cycle.map((mod, j) => (
                      <div key={j} className="flex items-center gap-1.5">
                        {j > 0 && (
                          <ArrowRight size={10} className="shrink-0 text-amber-500/50" />
                        )}
                        <span className="text-xs text-gray-400 font-mono truncate">
                          {mod}
                        </span>
                      </div>
                    ))}
                    {/* Show the loop back */}
                    <div className="flex items-center gap-1.5">
                      <ArrowRight size={10} className="shrink-0 text-amber-500/50" />
                      <span className="text-xs text-amber-400/70 font-mono truncate">
                        {cycle[0]}
                      </span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
