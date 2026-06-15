import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#0f1117",
          card: "#161b27",
          border: "#1e2535",
          muted: "#1a2030",
        },
        accent: {
          blue: "#3b82f6",
          cyan: "#06b6d4",
          orange: "#f97316",
          red: "#ef4444",
          yellow: "#eab308",
          green: "#22c55e",
          purple: "#a855f7",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
