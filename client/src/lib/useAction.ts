import { useState } from 'react';

export function useAction<T>() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<T | null>(null);
  const run = async (action: () => Promise<T>): Promise<T | undefined> => {
    if (busy) return undefined;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const value = await action();
      setResult(value);
      return value;
    } catch (error) {
      setError(error instanceof Error ? error.message : 'No se pudo completar la operación.');
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, result, run, setError };
}
