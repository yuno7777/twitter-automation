import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Soft charcoal foundation — not pure black (premium dark trend)
        bg: "#0A0A0F",
        surface: "#15161D",
        surface2: "#1C1E27",
        panel: "rgba(255,255,255,0.04)",
        border: "rgba(255,255,255,0.07)",
        "border-strong": "rgba(255,255,255,0.12)",
        lavender: {
          DEFAULT: "#A78BFA",
          deep: "#7C3AED",
          soft: "rgba(167,139,250,0.14)",
        },
        muted: "#8A8B97",
      },
      fontFamily: {
        sans: ["Geist", "Helvetica", "Arial", "system-ui", "sans-serif"],
        mono: ['"Geist Mono"', "IBM Plex Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        xl: "16px",
        "2xl": "20px",
        "3xl": "26px",
      },
      boxShadow: {
        glass: "0 1px 0 rgba(255,255,255,0.06) inset, 0 10px 30px rgba(0,0,0,0.35)",
        lift: "0 1px 0 rgba(255,255,255,0.07) inset, 0 16px 40px rgba(0,0,0,0.45)",
        "glow-lavender": "0 0 0 1px rgba(167,139,250,0.3), 0 12px 40px rgba(124,58,237,0.25)",
      },
    },
  },
  plugins: [],
};
export default config;
