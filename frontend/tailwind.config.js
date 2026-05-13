/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './broadcast.html',
    './src/**/*.{vue,ts,tsx,js,jsx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: 'var(--color-bg)',
        foreground: 'var(--color-fg)',
        muted: {
          DEFAULT: 'var(--color-muted)',
          foreground: 'var(--muted-foreground)',
        },
        card: {
          DEFAULT: 'var(--color-card)',
          foreground: 'var(--color-fg)',
        },
        border: 'var(--color-border)',
        input: 'var(--color-border)',
        ring: 'var(--theme-primary)',
        primary: {
          DEFAULT: 'var(--theme-primary)',
          foreground: 'var(--theme-on-primary)',
        },
        secondary: {
          DEFAULT: 'var(--theme-secondary)',
          foreground: 'var(--theme-on-primary)',
        },
        accent: {
          DEFAULT: 'var(--theme-accent)',
          foreground: 'var(--theme-on-primary)',
        },
        destructive: {
          DEFAULT: '#dc2626',
          foreground: '#ffffff',
        },
      },
      borderRadius: {
        lg: '8px',
        md: '6px',
        sm: '4px',
      },
    },
  },
  plugins: [],
}
