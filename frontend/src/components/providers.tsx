"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type Theme = "dark" | "light" | "system";
type Resolved = "dark" | "light";

interface AppState {
  theme: Theme;
  resolved: Resolved;
  setTheme: (t: Theme) => void;
  sidebarOpen: boolean;
  toggleSidebar: () => void;
}

const AppCtx = createContext<AppState | null>(null);

function systemPrefersDark(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

function apply(theme: Theme): Resolved {
  const dark = theme === "dark" || (theme === "system" && systemPrefersDark());
  document.documentElement.classList.toggle("dark", dark);
  return dark ? "dark" : "light";
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("dark");
  const [resolved, setResolved] = useState<Resolved>("dark");
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Sync from storage on mount (the inline script already set the class).
  useEffect(() => {
    const stored = (localStorage.getItem("theme") as Theme | null) ?? "dark";
    setThemeState(stored);
    setResolved(apply(stored));
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    localStorage.setItem("theme", t);
    setResolved(apply(t));
  }, []);

  // Follow OS changes while in "system" mode.
  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setResolved(apply("system"));
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  const toggleSidebar = useCallback(() => setSidebarOpen((o) => !o), []);

  return (
    <AppCtx.Provider value={{ theme, resolved, setTheme, sidebarOpen, toggleSidebar }}>
      {children}
    </AppCtx.Provider>
  );
}

export function useApp(): AppState {
  const ctx = useContext(AppCtx);
  if (!ctx) throw new Error("useApp must be used within <AppProvider>");
  return ctx;
}
