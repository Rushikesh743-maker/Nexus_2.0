/** @type {import('tailwindcss').Config} */

/**
 * The palette is a thin naming layer over `src/styles/tokens.css`.
 *
 * The names `navy`, `slate`, `teal` and `white` are kept because ~1,400 class
 * usages across the app already reference them. Pointing them at theme
 * variables is what makes the whole product theme-aware without rewriting
 * those classes — and it keeps one source of truth for colour.
 *
 * Read the scales semantically rather than literally:
 *   navy-*   → ink, 900 loudest → 50 faintest (inverts in dark)
 *   slate-*  → surfaces and rules
 *   teal-*   → the single interactive accent
 *   white    → the current surface
 */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        /* Ink — text and solid ink blocks. */
        navy: {
          50: 'var(--ink-50)',
          100: 'var(--ink-100)',
          200: 'var(--ink-200)',
          300: 'var(--ink-300)',
          400: 'var(--ink-400)',
          500: 'var(--ink-500)',
          600: 'var(--ink-600)',
          700: 'var(--ink-700)',
          800: 'var(--ink-800)',
          900: 'var(--ink-900)',
          950: 'var(--ink-950)',
        },

        /* Surfaces and rules. */
        slate: {
          50: 'var(--surface-sunken)',
          100: 'var(--line-soft)',
          200: 'var(--line)',
          300: 'var(--line-strong)',
          400: 'var(--ink-400)',
          500: 'var(--ink-500)',
          600: 'var(--ink-600)',
          700: 'var(--ink-700)',
          800: 'var(--ink-800)',
          900: 'var(--ink-900)',
          950: 'var(--ink-950)',
        },

        /*
         * The interactive accent. 600/700 are the "primary action" slots the
         * app already uses, and under the design thesis those resolve to ink
         * rather than a hue — the loudest affordance is contrast, not colour.
         */
        teal: {
          50: 'var(--accent-surface)',
          100: 'var(--accent-surface)',
          200: 'var(--accent-line)',
          300: 'var(--accent-line)',
          400: 'var(--accent-muted)',
          500: 'var(--accent)',
          600: 'var(--action)',
          700: 'var(--accent-strong)',
          800: 'var(--accent-strong)',
          900: 'var(--accent-strong)',
        },

        /* Semantic data hues, retuned per theme in tokens.css. */
        emerald: {
          50: 'var(--data-emerald-soft)',
          100: 'var(--data-emerald-soft)',
          200: 'var(--data-emerald-soft)',
          500: 'var(--data-emerald)',
          600: 'var(--data-emerald)',
          700: 'var(--data-emerald)',
        },
        rose: {
          50: 'var(--data-rose-soft)',
          200: 'var(--data-rose-soft)',
          400: 'var(--data-rose)',
          500: 'var(--data-rose)',
          600: 'var(--data-rose)',
          700: 'var(--data-rose)',
        },
        amber: {
          50: 'var(--data-amber-soft)',
          100: 'var(--data-amber-soft)',
          200: 'var(--data-amber-soft)',
          300: 'var(--data-amber)',
          500: 'var(--data-amber)',
          600: 'var(--data-amber)',
          700: 'var(--data-amber)',
          800: 'var(--data-amber)',
          900: 'var(--data-amber)',
        },
        sky: {
          50: 'var(--data-sky-soft)',
          500: 'var(--data-sky)',
          600: 'var(--data-sky)',
          700: 'var(--data-sky)',
        },
        violet: {
          50: 'var(--data-violet-soft)',
          600: 'var(--data-violet)',
          700: 'var(--data-violet)',
        },

        /* `bg-white` means "the current surface"; `text-white` means "on ink". */
        white: 'var(--surface)',

        /* Explicit semantic aliases for new code. */
        ground: 'var(--ground)',
        surface: {
          DEFAULT: 'var(--surface)',
          raised: 'var(--surface-raised)',
          sunken: 'var(--surface-sunken)',
          inverse: 'var(--surface-inverse)',
        },
        line: {
          DEFAULT: 'var(--line)',
          soft: 'var(--line-soft)',
          strong: 'var(--line-strong)',
        },
        action: {
          DEFAULT: 'var(--action)',
          hover: 'var(--action-hover)',
          on: 'var(--action-on)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          strong: 'var(--accent-strong)',
          muted: 'var(--accent-muted)',
          surface: 'var(--accent-surface)',
          line: 'var(--accent-line)',
          on: 'var(--accent-on)',
        },
      },

      fontFamily: {
        /* Instrument Sans: geometric, characterful, and legible at 11–13px. */
        sans: [
          '"Instrument Sans Variable"',
          '"Instrument Sans"',
          '"Noto Sans Devanagari Variable"',
          'system-ui',
          'sans-serif',
        ],
        /* Instrument Serif: editorial display, used only for page titles. */
        display: ['"Instrument Serif"', 'Georgia', 'serif'],
        /* Every figure in this product is evidence — figures get their own face. */
        mono: ['"JetBrains Mono Variable"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },

      fontSize: {
        /* Micro-label: uppercase, wide-tracked, used for field names. */
        micro: ['0.625rem', { lineHeight: '1rem', letterSpacing: '0.08em' }],
      },

      borderRadius: {
        /* Tightened throughout: an instrument, not a toy. */
        DEFAULT: '4px',
        md: '5px',
        lg: '6px',
        xl: '8px',
        '2xl': '10px',
      },

      boxShadow: {
        card: 'var(--shadow-card)',
        dropdown: 'var(--shadow-raised)',
        raised: 'var(--shadow-raised)',
        overlay: 'var(--shadow-overlay)',
      },

      ringOffsetColor: {
        DEFAULT: 'var(--ground)',
        white: 'var(--surface)',
      },

      transitionTimingFunction: {
        instrument: 'cubic-bezier(0.2, 0.6, 0.2, 1)',
      },

      keyframes: {
        'nexus-rise': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'none' },
        },
      },
      animation: {
        rise: 'nexus-rise 0.24s cubic-bezier(0.2, 0.6, 0.2, 1) both',
      },
    },
  },
  plugins: [],
};
