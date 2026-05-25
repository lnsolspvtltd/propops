import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        emergency: {
          50: "#fef2f2",
          600: "#dc2626",
          700: "#b91c1c",
          950: "#7f1d1d",
        },
        high: {
          500: "#f97316",
          600: "#ea580c",
        },
        medium: {
          500: "#eab308",
          600: "#ca8a04",
        },
        low: {
          600: "#16a34a",
          700: "#15803d",
        },
      },
      animation: {
        "bounce-slow": "bounce 2s infinite",
      },
      keyframes: {
        bounce: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-8px)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;