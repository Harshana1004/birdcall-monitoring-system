import {
  useEffect,
  useRef,
  useState,
} from "react";


/**
 * Call `callback` every `intervalMs` while the tab is visible, and
 * once straight away when the tab becomes visible again. Pair it with
 * useApi's reload({ silent: true }) for live pages.
 */
export function usePolling(callback, intervalMs, enabled = true) {
  const saved = useRef(callback);

  useEffect(() => {
    saved.current = callback;
  });

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    function tick() {
      if (!document.hidden) {
        saved.current();
      }
    }

    const timer = setInterval(tick, intervalMs);
    document.addEventListener("visibilitychange", tick);

    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [intervalMs, enabled]);
}


/**
 * Ids in `items` that were not there on an earlier render, so newly
 * arrived rows can be highlighted. The first load (and the first load
 * after `resetKey` changes, e.g. new filters) counts as nothing new.
 */
export function useNewIds(items, resetKey = "") {
  const seen = useRef(null);
  const seenKey = useRef(resetKey);
  const [fresh, setFresh] = useState(() => new Set());

  useEffect(() => {
    if (!items) {
      return;
    }

    const ids = items.map((item) => item.id);

    if (seen.current === null || seenKey.current !== resetKey) {
      seen.current = new Set(ids);
      seenKey.current = resetKey;
      setFresh(new Set());
      return;
    }

    const added = ids.filter((id) => !seen.current.has(id));
    ids.forEach((id) => seen.current.add(id));

    if (added.length > 0) {
      setFresh(new Set(added));
    }
  }, [items, resetKey]);

  return fresh;
}
