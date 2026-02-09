/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // Refined typography: Plus Jakarta Sans for UI, JetBrains Mono for code
        sans: ["Plus Jakarta Sans", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
        display: ["Instrument Serif", "Georgia", "serif"],
      },
      fontSize: {
        // Refined type scale with tighter line heights
        "2xs": ["0.625rem", { lineHeight: "1rem" }],
        xs: ["0.75rem", { lineHeight: "1rem", letterSpacing: "0.01em" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem", letterSpacing: "0.005em" }],
        base: ["0.875rem", { lineHeight: "1.5rem" }],
        lg: ["1rem", { lineHeight: "1.5rem", letterSpacing: "-0.01em" }],
        xl: ["1.125rem", { lineHeight: "1.75rem", letterSpacing: "-0.015em" }],
        "2xl": ["1.375rem", { lineHeight: "1.875rem", letterSpacing: "-0.02em" }],
        "3xl": ["1.75rem", { lineHeight: "2.25rem", letterSpacing: "-0.025em" }],
        "4xl": ["2.25rem", { lineHeight: "2.75rem", letterSpacing: "-0.03em" }],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
        neutral: {
          DEFAULT: "hsl(var(--neutral))",
          foreground: "hsl(var(--neutral-foreground))",
        },
        sidebar: {
          DEFAULT: "hsl(var(--sidebar))",
          foreground: "hsl(var(--sidebar-foreground))",
        },
        // Glass surface tokens
        glass: {
          DEFAULT: "hsl(var(--glass) / var(--glass-alpha))",
          muted: "hsl(var(--glass-muted) / var(--glass-muted-alpha))",
          border: "hsl(var(--glass-border) / var(--glass-border-alpha))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      backdropBlur: {
        xs: "4px",
        glass: "12px",
        "glass-heavy": "24px",
      },
      boxShadow: {
        // Refined elevation system
        "elevation-1": "0 1px 2px 0 rgb(0 0 0 / 0.03), 0 1px 3px 0 rgb(0 0 0 / 0.02)",
        "elevation-2": "0 2px 4px -1px rgb(0 0 0 / 0.04), 0 4px 6px -1px rgb(0 0 0 / 0.03)",
        "elevation-3": "0 4px 8px -2px rgb(0 0 0 / 0.05), 0 8px 16px -4px rgb(0 0 0 / 0.04)",
        "glow-sm": "0 0 12px -3px hsl(var(--primary) / 0.25)",
        "glow-md": "0 0 20px -5px hsl(var(--primary) / 0.3)",
        "inner-light": "inset 0 1px 0 0 rgb(255 255 255 / 0.05)",
        // Glass shadow presets
        "glass-sm": "0 2px 8px -2px rgb(0 0 0 / 0.08), 0 0 1px rgb(0 0 0 / 0.05)",
        "glass-md": "0 4px 16px -4px rgb(0 0 0 / 0.1), 0 0 1px rgb(0 0 0 / 0.06)",
        "glass-lg": "0 8px 32px -8px rgb(0 0 0 / 0.12), 0 0 1px rgb(0 0 0 / 0.08)",
        "glass-glow": "0 0 20px -5px hsl(var(--primary) / 0.2), 0 4px 16px -4px rgb(0 0 0 / 0.1)",
        // Status glow shadows
        "glow-success": "0 0 20px -5px hsl(var(--success) / 0.3)",
        "glow-warning": "0 0 20px -5px hsl(var(--warning) / 0.3)",
        "glow-destructive": "0 0 20px -5px hsl(var(--destructive) / 0.3)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.97)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        "pulse-subtle": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.7" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        // Glow animations
        "glow-pulse": {
          "0%, 100%": {
            boxShadow: "0 0 8px -2px hsl(var(--primary) / 0.4), 0 4px 12px -4px rgb(0 0 0 / 0.1)",
          },
          "50%": {
            boxShadow: "0 0 20px -4px hsl(var(--primary) / 0.5), 0 4px 16px -4px rgb(0 0 0 / 0.15)",
          },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-2px)" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "fade-in": "fade-in 0.2s ease-out",
        "fade-up": "fade-up 0.3s ease-out",
        "scale-in": "scale-in 0.2s ease-out",
        "pulse-subtle": "pulse-subtle 2s ease-in-out infinite",
        shimmer: "shimmer 2s linear infinite",
        "glow-pulse": "glow-pulse 2.5s cubic-bezier(0.4, 0, 0.2, 1) infinite",
        float: "float 3s ease-in-out infinite",
      },
      transitionDuration: {
        DEFAULT: "150ms",
      },
      transitionTimingFunction: {
        DEFAULT: "cubic-bezier(0.4, 0, 0.2, 1)",
      },
    },
  },
  plugins: [],
}
