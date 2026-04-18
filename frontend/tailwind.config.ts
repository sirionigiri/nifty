import type { Config } from "tailwindcss"

const config: Config = {
darkMode: ["class", ".dark"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        foreground: "var(--foreground)",
        background: "var(--background)",
        border: "var(--border)",
      },
    },
  },
}

export default config