import { useCallback, useEffect, useState } from 'react';
import { api, ApiError } from '../services/api';
import type { ConfigStatus } from '../types/api';

interface ConfigState {
  status: ConfigStatus | null;
  loading: boolean;
  error: string | null;
}

/**
 * Loads backend configuration status once per session and shares the result
 * across every component that calls this hook (Header, Dashboard, Settings…).
 *
 * Without the module-level cache, each mounted component fired its own
 * `/api/config/status` request (the dashboard alone triggered two). Concurrent
 * callers are deduplicated into a single in-flight request; `reload()` forces
 * a fresh fetch and updates every subscriber.
 */

// --- Module-level shared cache --------------------------------------------
let cached: ConfigStatus | null = null;
let inFlight: Promise<void> | null = null;
const listeners = new Set<(state: ConfigState) => void>();

function notify(state: ConfigState) {
  for (const listener of listeners) listener(state);
}

async function loadShared(): Promise<void> {
  if (inFlight) return; // another caller already started the fetch
  inFlight = api
    .configStatus()
    .then((status) => {
      cached = status;
      notify({ status, loading: false, error: null });
    })
    .catch((err: unknown) => {
      const message =
        err instanceof ApiError ? err.message : 'Could not load configuration status.';
      notify({ status: cached, loading: false, error: message });
    })
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

export function useConfigStatus(): ConfigState & { reload: () => void } {
  const [state, setState] = useState<ConfigState>({
    status: cached,
    loading: cached === null,
    error: null,
  });

  useEffect(() => {
    const listener = (s: ConfigState) => setState(s);
    listeners.add(listener);
    if (cached === null && !inFlight) {
      setState((s) => ({ ...s, loading: true }));
      void loadShared();
    }
    return () => {
      listeners.delete(listener);
    };
  }, []);

  const reload = useCallback(() => {
    void loadShared();
  }, []);

  return { ...state, reload };
}
