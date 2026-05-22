import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Deep, slightly-blue black background
        bg: "#05060a",
        bg2: "#0b0d14",
        // Glass panel base
        glass: "rgba(255, 255, 255, 0.04)",
        glassHi: "rgba(255, 255, 255, 0.08)",
        border: "rgba(255, 255, 255, 0.08)",
        borderHi: "rgba(255, 255, 255, 0.16)",
        // Text
        text: "#f5f7fa",
        muted: "#8c93a3",
        mutedDim: "#5a606e",
        // Accent — indigo-cyan gradient
        accent: "#6366f1",
        accent2: "#22d3ee",
        // Status
        good: "#10b981",
        goodDim: "rgba(16, 185, 129, 0.15)",
        bad: "#f43f5e",
        badDim: "rgba(244, 63, 94, 0.15)",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        floaty: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        glow: {
          "0%, 100%": { boxShadow: "0 0 16px rgba(99, 102, 241, 0.3)" },
          "50%": { boxShadow: "0 0 28px rgba(34, 211, 238, 0.55)" },
        },
      },
      animation: {
        shimmer: "shimmer 2.5s linear infinite",
        floaty: "floaty 5s ease-in-out infinite",
        glow: "glow 4s ease-in-out infinite",
      },
      backdropBlur: { xs: "2px" },
    },
  },
  plugins: [],
};
export default config;
