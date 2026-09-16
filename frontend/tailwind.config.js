/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eefcfa",
          100: "#d3f5ef",
          200: "#a9e8de",
          300: "#75d3c6",
          400: "#43b3a5",
          500: "#25948a",
          600: "#19766f",
          700: "#175f5a",
          800: "#164c49",
          900: "#153f3d",
        },
      },
    },
  },
  plugins: [],
};
