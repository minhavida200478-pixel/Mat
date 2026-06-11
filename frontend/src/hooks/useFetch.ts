// Shared data-fetching hook: de-dupes the loading / error / refetch / focus-refresh
// boilerplate that was copy-pasted across screens. Safe against state updates after
// unmount, and (via the API client's ensureSession) auth-token-ready by construction.
//
// Usage:
//   const { data, loading, error, refetch } = useFetch(() => api.get("/dashboard"));
//   // refetch silently when the screen regains focus:
//   const { data, refetch } = useFetch(() => api.get("/partner/links"), { refetchOnFocus: true });
import { useFocusEffect } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";

type RunOpts = { silent?: boolean };
type UseFetchOpts = { deps?: any[]; refetchOnFocus?: boolean };

export function useFetch<T>(fetcher: () => Promise<T>, opts: UseFetchOpts = {}) {
  const { deps = [], refetchOnFocus = false } = opts;

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const mounted = useRef(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refetch = useCallback(async (o?: RunOpts) => {
    if (!o?.silent) setLoading(true);
    setError(null);
    try {
      const result = await fetcherRef.current();
      if (mounted.current) setData(result);
      return result;
    } catch (e: any) {
      if (mounted.current) setError(e?.message || "Something went wrong");
      return undefined;
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  // Initial load + reload when deps change.
  useEffect(() => {
    mounted.current = true;
    refetch();
    return () => {
      mounted.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  // Silently refetch when the screen regains focus. The first focus (mount) is
  // skipped so we don't double-fetch alongside the initial load above.
  const skipFirstFocus = useRef(true);
  useFocusEffect(
    useCallback(() => {
      if (!refetchOnFocus) return;
      if (skipFirstFocus.current) {
        skipFirstFocus.current = false;
        return;
      }
      refetch({ silent: true });
    }, [refetchOnFocus, refetch]),
  );

  return { data, loading, error, refetch, setData };
}
