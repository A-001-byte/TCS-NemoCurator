import { useEffect, useState } from "react";

export function useTheme() {
  const [theme, setTheme] = useState(() => {

    try {
      const saved = localStorage.getItem("theme");
      if (saved) return saved;
    } catch {
      /* storage unavailable: fall back to system preference */
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* non-essential */
    }
  }, [theme]);

  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}
