import { useEffect, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { searchSymbols } from "../../api/client";
import { NODE_COLORS } from "../../utils/colors";
import type { SearchResult, SymbolKind } from "../../types/graph";

interface SearchBarProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (symbolId: string) => void;
}

/** Command-K search overlay for finding symbols by name. */
export function SearchBar({ isOpen, onClose, onSelect }: SearchBarProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
      setQuery("");
      setResults([]);
      setSelectedIndex(0);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    const currentId = ++requestIdRef.current;

    const timer = setTimeout(() => {
      searchSymbols(query, 10)
        .then((data) => {
          if (currentId === requestIdRef.current) {
            setResults(data.results);
            setSelectedIndex(0);
          }
        })
        .catch(() => {
          if (currentId === requestIdRef.current) {
            setResults([]);
          }
        });
    }, 200);

    return () => clearTimeout(timer);
  }, [query]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && results[selectedIndex]) {
      const r = results[selectedIndex]!;
      onSelect(`${r.kind}:${r.file}:${r.name}:${r.line}`);
      onClose();
    }
  }

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/50"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg border border-gray-700 bg-gray-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Input */}
        <div className="flex items-center gap-2 border-b border-gray-800 px-4 py-3">
          <Search size={16} className="text-gray-500" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search symbols..."
            className="flex-1 bg-transparent text-sm text-gray-100 outline-none placeholder:text-gray-600"
          />
          <button type="button" onClick={onClose} className="text-gray-500 hover:text-gray-300">
            <X size={16} />
          </button>
        </div>

        {/* Results */}
        {results.length > 0 && (
          <ul className="max-h-80 overflow-y-auto py-2">
            {results.map((r, i) => (
              <li
                key={`${r.kind}:${r.file}:${r.name}:${r.line}`}
                className={`flex items-center gap-3 px-4 py-2 cursor-pointer text-sm ${
                  i === selectedIndex ? "bg-gray-800" : "hover:bg-gray-800/50"
                }`}
                onClick={() => {
                  onSelect(`${r.kind}:${r.file}:${r.name}:${r.line}`);
                  onClose();
                }}
              >
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full shrink-0"
                  style={{ backgroundColor: NODE_COLORS[r.kind as SymbolKind] }}
                />
                <span className="text-gray-200 font-medium">{r.name}</span>
                <span className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-500 uppercase">
                  {r.kind}
                </span>
                <span className="ml-auto text-xs text-gray-600 font-mono truncate">
                  {r.file}
                </span>
              </li>
            ))}
          </ul>
        )}

        {query && results.length === 0 && (
          <div className="px-4 py-6 text-center text-sm text-gray-600">
            No symbols found
          </div>
        )}
      </div>
    </div>
  );
}
