import { useCallback, useEffect, useState } from "react";

/**
 * Load a value from the API, with the three states a screen actually has.
 *
 * `loading` starts true so a page never renders zeros before the first response
 * lands. A dashboard that flashes "$0.00" and then corrects itself teaches an
 * operator to distrust it, and the distinction between "no spend" and "not
 * loaded yet" is exactly what a billing screen must not blur.
 *
 * The fetch is aborted on unmount so a slow response cannot set state on a
 * page the operator has already navigated away from.
 */
export function useResource(loader, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    let live = true;

    setLoading(true);
    setError(null);

    Promise.resolve(loader(controller.signal))
      .then((payload) => {
        if (live) setData(payload);
      })
      .catch((cause) => {
        if (live && cause?.name !== "AbortError") setError(cause);
      })
      .finally(() => {
        if (live) setLoading(false);
      });

    return () => {
      live = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { data, error, loading, reload };
}
