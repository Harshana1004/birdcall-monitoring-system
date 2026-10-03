import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { errorMessage } from "../api/client";


/**
 * Run `loader` now and whenever `deps` change. Returns
 * { data, error, isLoading, reload }. Responses from superseded
 * calls are ignored, so fast filter changes cannot show stale data.
 * reload({ silent: true }) refreshes without toggling isLoading
 * (for background polling).
 */
export function useApi(loader, deps) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const callId = useRef(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(loader, deps);


  const reload = useCallback(async ({ silent = false } = {}) => {
    const id = ++callId.current;

    if (!silent) {
      setIsLoading(true);
      setError(null);
    }

    try {
      const result = await load();

      if (id === callId.current) {
        setData(result);
        setError(null);
      }
    } catch (requestError) {
      if (id === callId.current && !silent) {
        setError(errorMessage(requestError, "Could not load data."));
      }
    } finally {
      if (id === callId.current) {
        setIsLoading(false);
      }
    }
  }, [load]);


  useEffect(() => {
    reload();
  }, [reload]);


  return { data, error, isLoading, reload, setData };
}
