// postcss.config.js (Tailwind v4 방식)
export default {
    plugins: {
      '@tailwindcss/postcss': {},   // ← 핵심! 기존 tailwindcss: {} 아님
      autoprefixer: {},
    },
  }