import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        bg:      '#080812',
        surface: '#0d0d1a',
        card:    '#111122',
        border:  '#1e1e35',
        green:   '#00c853',
        red:     '#ef4444',
        amber:   '#f59e0b',
        blue:    '#3b82f6',
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};

export default config;
