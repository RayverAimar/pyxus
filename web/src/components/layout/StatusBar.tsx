import type { GraphStats } from "../../types/graph";

interface StatusBarProps {
  stats: GraphStats | null;
}

/** Bottom status bar showing graph statistics. */
export function StatusBar({ stats }: StatusBarProps) {
  if (!stats) return null;

  const resolution = stats.callResolutionRate
    ? `${(stats.callResolutionRate * 100).toFixed(0)}%`
    : null;

  return (
    <footer className="flex h-6 items-center gap-4 border-t border-gray-800/60 bg-[#0a0a10] px-4 text-[11px] text-gray-600">
      <div className="flex items-center gap-1.5">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
        <span>Ready</span>
      </div>
      <span className="text-gray-800">|</span>
      <span>{stats.nodeCount.toLocaleString()} nodes</span>
      <span className="text-gray-800">|</span>
      <span>{stats.edgeCount.toLocaleString()} edges</span>
      {resolution && (
        <>
          <span className="text-gray-800">|</span>
          <span>Resolution: {resolution}</span>
        </>
      )}
    </footer>
  );
}
