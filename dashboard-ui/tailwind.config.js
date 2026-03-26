/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  corePlugins: {
    preflight: false, // prevent Tailwind reset from conflicting with Ant Design
  },
  theme: {
    extend: {},
  },
  plugins: [],
}
