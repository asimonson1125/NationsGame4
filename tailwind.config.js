/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./app/templates/**/*.html'],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: '#f59e0b', light: '#fbbf24', dark: '#d97706' },
        slate: {
          50:  '#f4f5f7',
          100: '#e7e9ed',
          200: '#ced1d8',
          300: '#adb2bc',
          400: '#8a919f',
          500: '#6b7486',
          600: '#545d70',
          700: '#404a5c',
          800: '#2f3848',
          900: '#252d3c',
          950: '#1c2332',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
