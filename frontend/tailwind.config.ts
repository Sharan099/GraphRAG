import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          900: "#050e1a",
          800: "#071628",
          700: "#0a1e35",
          600: "#0b2240",
          500: "#0e2a45",
          400: "#163d6b",
        },
        accent: {
          DEFAULT: "#3b82f6",
          soft: "#60a5fa",
          muted: "#4d7fa8",
        },
        haze: "#5a8bb0",
        frost: "#c8ddf5",
      },
      fontFamily: {
        mono: ["var(--font-mono)", "JetBrains Mono", "monospace"],
        sans: ["var(--font-sans)", "IBM Plex Sans", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(59,130,246,0.25), 0 12px 40px -12px rgba(59,130,246,0.35)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulse_dot: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.3" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.35s ease-out",
        "pulse-dot": "pulse_dot 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
