import { Search } from "lucide-react";
import type { GraphStats } from "../../types/graph";

interface HeaderProps {
  stats: GraphStats | null;
  onSearchFocus: () => void;
}

/** Top header bar with project name, search trigger, and stats. */
export function Header({ stats, onSearchFocus }: HeaderProps) {
  return (
    <header className="flex h-11 items-center justify-between border-b border-gray-800/60 bg-[#0a0a10] px-4">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="h-5 w-5 rounded bg-gradient-to-br from-cyan-400 to-blue-600 flex items-center justify-center">
            <span className="text-[10px] font-bold text-white">P</span>
          </div>
          <span className="text-sm font-semibold text-white tracking-tight">
            Pyxus
          </span>
        </div>
        {stats && (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span>{stats.nodeCount.toLocaleString()} nodes</span>
            <span className="text-gray-700">|</span>
            <span>{stats.edgeCount.toLocaleString()} edges</span>
          </div>
        )}
      </div>

      <button
        onClick={onSearchFocus}
        className="flex items-center gap-2 rounded-lg border border-gray-800 bg-gray-900/50 px-3 py-1.5 text-sm text-gray-500 hover:border-gray-700 hover:text-gray-400 transition-colors"
      >
        <Search size={14} />
        <span>Search nodes...</span>
        <kbd className="ml-6 rounded border border-gray-800 bg-[#0a0a10] px-1.5 py-0.5 text-[10px] text-gray-600">
          ⌘K
        </kbd>
      </button>

      <div className="w-24" />
    </header>
  );
}
