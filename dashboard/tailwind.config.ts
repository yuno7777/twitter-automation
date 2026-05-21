import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#000000",
        panel: "rgba(255,255,255,0.04)",
        border: "rgba(255,255,255,0.08)",
        lavender: {
          DEFAULT: "#A78BFA",
          deep: "#7C3AED",
        },
        muted: "#8b8b94",
      },
      fontFamily: {
        sans: ['Helvetica', '"Helvetica Neue"', "Arial", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        glass: "0 1px 0 rgba(255,255,255,0.05) inset, 0 8px 24px rgba(124,58,237,0.08)",
      },
    },
  },
  plugins: [],
};
export default config;
