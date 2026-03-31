import { useEffect, useState } from "react";
import { fetchGraph } from "../api/client";
import type { GraphData } from "../types/graph";

/** Fetch graph data from the API on mount. */
export function useGraphData(level?: "module") {
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchGraph(level)
      .then(setData)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [level]);

  return { data, loading, error };
}
