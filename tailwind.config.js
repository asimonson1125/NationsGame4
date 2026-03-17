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
          300: '#c0c6cf',
          400: '#adb2bc',
          500: '#a2a8b5',
          600: '#9ba1ae',
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
  safelist: [
    // Rarity badge backgrounds (defined in app/game/equipment.py, not visible to JIT)
    'bg-slate-700',
    'bg-emerald-900/60',
    'bg-blue-900/60',
    'bg-purple-900/60',
    'bg-amber-900/60',
    // Rarity text colors
    'text-slate-300',
    'text-emerald-300',
    'text-blue-300',
    'text-purple-300',
    'text-amber-300',
    // Rarity borders
    'border-slate-600',
    'border-emerald-700',
    'border-blue-700',
    'border-purple-700',
    'border-amber-600',
    // Rarity accent text (used in card body)
    'text-slate-400',
    'text-emerald-400',
    'text-blue-400',
    'text-purple-400',
    'text-amber-400',
    'text-pink-400',
    'text-pink-500',
  ],
  plugins: [],
}
