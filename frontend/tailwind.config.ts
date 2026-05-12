import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}", "./store/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#07111f",
        panel: "rgba(15, 23, 42, 0.72)",
        line: "rgba(148, 163, 184, 0.18)"
      },
      boxShadow: {
        glow: "0 24px 80px rgba(20, 184, 166, 0.14)"
      }
    }
  },
  plugins: []
};

export default config;

