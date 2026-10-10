import { useEffect, useState } from 'react';
import { api, ApiError } from '../services/api';
import type { ConfigStatus } from '../types/api';

interface ConfigState {
  status: ConfigStatus | null;
  loading: boolean;
  error: string | null;
}

/**
 * Loads backend configuration status once per session (with a light refresh
 * on mount) so the UI can show demo/live and AI availability honestly.
 */
export function useConfigStatus(): ConfigState & { reload: () => void } {
  const [state, setState] = useState<ConfigState>({ status: null, loading: true, error: null });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    api
      .configStatus()
      .then((status) => {
        if (!cancelled) setState({ status, loading: false, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError ? err.message : 'Could not load configuration status.';
        setState({ status: null, loading: false, error: message });
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  return { ...state, reload: () => setTick((t) => t + 1) };
}
