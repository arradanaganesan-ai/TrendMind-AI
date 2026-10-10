/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Design tokens — deep midnight intelligence palette
        midnight: {
          950: '#05070f',
          900: '#080b16',
          850: '#0a0e1c',
          800: '#0d1224',
          700: '#131a33',
          600: '#1a2242',
        },
        slateui: {
          700: '#1e2740',
          600: '#2a3352',
          500: '#3d4870',
          400: '#5b6790',
          300: '#8892b3',
          200: '#b3bcd6',
          100: '#dde3f2',
        },
        violetui: {
          600: '#6d4aff',
          500: '#8b6cff',
          400: '#a78bff',
          300: '#c4b1ff',
        },
        blueui: {
          500: '#3b82f6',
          400: '#60a5fa',
          300: '#93c5fd',
        },
        cyanui: {
          500: '#22d3ee',
          400: '#5ee7f7',
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'sans-serif',
        ],
        display: ['"Space Grotesk"', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      spacing: {
        18: '4.5rem',
        112: '28rem',
        128: '32rem',
      },
      boxShadow: {
        panel: '0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 30px -12px rgba(0,0,0,0.7)',
        glow: '0 0 0 1px rgba(109,74,255,0.25), 0 8px 40px -16px rgba(109,74,255,0.45)',
      },
      transitionTimingFunction: {
        smooth: 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-400px 0' },
          '100%': { backgroundPosition: '400px 0' },
        },
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.4s ease-in-out infinite',
        fadeUp: 'fadeUp 0.45s cubic-bezier(0.22, 1, 0.36, 1) both',
      },
    },
  },
  plugins: [],
};
