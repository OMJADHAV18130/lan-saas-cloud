/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef4ff',
          100: '#dbe6ff',
          200: '#bed1ff',
          300: '#92b2ff',
          400: '#5f88fc',
          500: '#3b63f6',
          600: '#2547eb',
          700: '#1d36d8',
          800: '#1e2faf',
          900: '#1e2c8a',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
