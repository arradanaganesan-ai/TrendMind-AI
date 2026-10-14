/**
 * Design tokens — TrendMind AI intelligence palette.
 *
 * Every custom ramp maps to a CSS variable declared in src/styles/index.css
 * (`:root` = dark theme, `[data-theme='light']` = light theme). Values are
 * space-separated RGB channels so Tailwind can apply opacity modifiers
 * (`bg-midnight-800/60`) via `<alpha-value>`.
 *
 * The RAMP SEMANTICS stay identical in both themes:
 *   midnight  — page/surface backgrounds (950 = page, 800 = panel, 700 = raised)
 *   slateui   — text & borders (100 = primary text, 400 = muted, 700 = border)
 *   violetui  — primary accent (600 = solid button, 300 = accent text)
 *   blueui / cyanui — secondary accents
 * Only the underlying values change per theme.
 *
 * Status colors (amber/emerald/red) used by the app are overridden here so the
 * light theme can darken them for readable contrast on pale surfaces.
 * @type {import('tailwindcss').Config}
 */
const v = (name) => `rgb(var(${name}) / <alpha-value>)`;

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        midnight: {
          950: v('--tm-midnight-950'),
          900: v('--tm-midnight-900'),
          850: v('--tm-midnight-850'),
          800: v('--tm-midnight-800'),
          700: v('--tm-midnight-700'),
          600: v('--tm-midnight-600'),
        },
        slateui: {
          700: v('--tm-slateui-700'),
          600: v('--tm-slateui-600'),
          500: v('--tm-slateui-500'),
          400: v('--tm-slateui-400'),
          300: v('--tm-slateui-300'),
          200: v('--tm-slateui-200'),
          100: v('--tm-slateui-100'),
        },
        violetui: {
          600: v('--tm-violetui-600'),
          500: v('--tm-violetui-500'),
          400: v('--tm-violetui-400'),
          300: v('--tm-violetui-300'),
        },
        blueui: {
          500: v('--tm-blueui-500'),
          400: v('--tm-blueui-400'),
          300: v('--tm-blueui-300'),
        },
        cyanui: {
          500: v('--tm-cyanui-500'),
          400: v('--tm-cyanui-400'),
        },
        // --- Status colors (var-backed overrides of the default scales) ---
        amber: {
          300: v('--tm-amber-300'),
          400: v('--tm-amber-400'),
        },
        emerald: {
          400: v('--tm-emerald-400'),
        },
        red: {
          300: v('--tm-red-300'),
          400: v('--tm-red-400'),
          500: v('--tm-red-500'),
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
        panel: '0 1px 0 0 var(--tm-shadow-inset) , 0 8px 30px -12px var(--tm-shadow-panel)',
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
