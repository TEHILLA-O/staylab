import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#F7F7F5",
        surface: "#FFFFFF",
        ink: "#181818",
        mute: "#70706C",
        line: "#E4E4DF",
        accent: "#C45C3E",
        "accent-soft": "#F3E4DE",
        up: "#3F6F58",
        "up-soft": "#E4EFE8",
        down: "#A14B45",
        "down-soft": "#F6E6E4",
        warm: "#8A8680",
      },
      fontFamily: {
        serif: ["var(--font-serif)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      letterSpacing: {
        label: "0.14em",
      },
    },
  },
  plugins: [],
};

export default config;
