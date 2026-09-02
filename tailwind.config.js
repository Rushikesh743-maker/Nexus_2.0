/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Deep desaturated navy used for text, headers and sidebar accents.
        navy: {
          50: '#f0f4f8',
          100: '#d9e2ec',
          200: '#bcccdc',
          300: '#9fb3c8',
          400: '#829ab1',
          500: '#627d98',
          600: '#486581',
          700: '#334e68',
          800: '#243b53',
          900: '#102a43',
          950: '#0b1c2c',
        },
      },
      fontFamily: {
        sans: ['"Inter Variable"', 'Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px 0 rgb(16 42 67 / 0.05), 0 1px 3px 0 rgb(16 42 67 / 0.07)',
        dropdown: '0 4px 6px -1px rgb(16 42 67 / 0.08), 0 10px 15px -3px rgb(16 42 67 / 0.10)',
      },
    },
  },
  plugins: [],
};
