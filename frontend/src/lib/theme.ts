import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "theme";
const listeners = new Set<() => void>();
let current: Theme = readTheme();

function readTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function render(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

/** Apply the saved (or system) theme before the first render. */
export function initTheme() {
  render(current);
}

export function setTheme(theme: Theme) {
  current = theme;
  localStorage.setItem(STORAGE_KEY, theme);
  render(theme);
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme(): [Theme, (theme: Theme) => void] {
  const theme = useSyncExternalStore(subscribe, () => current);
  return [theme, setTheme];
}
