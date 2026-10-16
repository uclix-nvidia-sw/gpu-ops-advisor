import { useState, type SetStateAction } from 'react';
import { useApp } from './store';

// Tab-scoped drafts survive switching comparison modes; successful saves remove them.
export function useNewDraft<T>(key: string, initial: T) {
  const enabled = useApp().mode === 'new';
  const [value, update] = useState<T>(() => {
    try {
      const saved = enabled && sessionStorage.getItem(`new-draft:${key}`);
      return saved ? (JSON.parse(saved) as T) : initial;
    } catch {
      return initial;
    }
  });
  const set = (next: SetStateAction<T>) =>
    update((previous) => {
      const result = typeof next === 'function' ? (next as (v: T) => T)(previous) : next;
      try {
        if (enabled) sessionStorage.setItem(`new-draft:${key}`, JSON.stringify(result));
      } catch {
        /* The form remains usable when storage is unavailable. */
      }
      return result;
    });
  return [value, set] as const;
}
export function clearNewDraft(prefix: string) {
  try {
    Object.keys(sessionStorage)
      .filter((key) => key.startsWith(`new-draft:${prefix}/`))
      .forEach((key) => sessionStorage.removeItem(key));
  } catch {
    /* No persisted draft. */
  }
}
