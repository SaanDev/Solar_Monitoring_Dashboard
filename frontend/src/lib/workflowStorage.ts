"use client";

/**
 * Per-tab persistence for a feature's in-progress workflow, so a refresh or a
 * back/forward navigation reopens the same view instead of resetting to blank.
 *
 * Uses sessionStorage (scoped to the browser tab): it survives reloads and
 * history navigation but clears when the tab closes, so two tabs keep
 * independent workflows and nothing lingers forever. Backend sessions are
 * referenced by id and outlive a client reload, so persisting the id-bearing
 * session objects here is enough for the render URLs to resolve again.
 *
 * All access is best-effort — any storage/serialization error degrades to "no
 * cache" rather than breaking the page.
 */

export function loadWorkflow<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function saveWorkflow(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota / serialization errors are non-fatal for a UI cache */
  }
}

export function clearWorkflow(key: string): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}
