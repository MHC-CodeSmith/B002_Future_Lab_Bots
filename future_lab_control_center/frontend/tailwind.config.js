/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx}",
    "./src/components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          dark: '#0f172a',
          card: '#1e293b',
          accent: '#3b82f6',
          danger: '#ef4444',
          success: '#10b981',
          warning: '#f59e0b'
        }
      }
    },
  },
  plugins: [],
}
