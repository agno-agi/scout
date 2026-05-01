"use client";

import { useCallback, useEffect, useState } from "react";

type Theme = "light" | "dark";
const STORAGE_KEY = "scout:theme";

function readClientTheme(): Theme {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "dark" || stored === "light") return stored;
  } catch {
    /* fine */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function applyTheme(theme: Theme) {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.style.colorScheme = theme;
}

// Returns null until the component mounts on the client — that way the
// server renders a stable shell (no theme-specific UI) and we don't trip
// hydration warnings. The inline bootstrap script in app/layout.tsx
// already set the dark class on <html> before React hydrated, so the
// background colors are correct from the very first paint.
export function useTheme(): {
  theme: Theme | null;
  toggle: () => void;
} {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    setTheme(readClientTheme());
  }, []);

  useEffect(() => {
    if (theme === null) return;
    applyTheme(theme);
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* fine */
    }
  }, [theme]);

  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (e.key !== STORAGE_KEY || e.newValue == null) return;
      if (e.newValue === "dark" || e.newValue === "light") setTheme(e.newValue);
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const toggle = useCallback(() => {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }, []);

  return { theme, toggle };
}
