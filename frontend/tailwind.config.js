/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#58C4F5',
          50: '#EAF8FF',
          100: '#D9F2FF',
          200: '#B8E7FE',
          300: '#8FD8FC',
          400: '#58C4F5',
          500: '#36AEE8',
          600: '#1B94CB',
          700: '#17779F',
          800: '#155F7F',
          900: '#124C66',
        },
        canvas: '#F7FAFD',
        surface: '#FFFFFF',
        soft: '#E8F1FA',
        line: '#E2EAF2',
        ink: {
          DEFAULT: '#243447',
          muted: '#64748B',
          subtle: '#94A3B8',
        },
        success: {
          50: '#ECFDF3',
          100: '#D1FADF',
          500: '#12B76A',
          600: '#079455',
          700: '#027A48',
        },
        warning: {
          50: '#FFFAEB',
          100: '#FEF0C7',
          500: '#F79009',
          600: '#DC6803',
          700: '#B54708',
        },
        danger: {
          50: '#FEF3F2',
          100: '#FEE4E2',
          500: '#F04438',
          600: '#D92D20',
          700: '#B42318',
        },
      },
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'system-ui', '-apple-system', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'Liberation Mono', 'monospace'],
      },
      spacing: {
        4.5: '1.125rem',
        18: '4.5rem',
      },
      borderRadius: {
        xl: '0.875rem',
        '2xl': '1.125rem',
        '3xl': '1.5rem',
      },
      boxShadow: {
        card: '0 1px 2px rgba(16, 24, 40, 0.04), 0 1px 3px rgba(16, 24, 40, 0.06)',
        cardHover: '0 4px 8px -2px rgba(16, 24, 40, 0.08), 0 2px 4px -2px rgba(16, 24, 40, 0.04)',
        popover: '0 12px 24px -6px rgba(16, 24, 40, 0.12), 0 4px 8px -4px rgba(16, 24, 40, 0.06)',
        drawer: '0 24px 48px -12px rgba(16, 24, 40, 0.18)',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in-right': {
          from: { opacity: '0', transform: 'translateX(16px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 150ms ease-out',
        'slide-up': 'slide-up 200ms ease-out',
        'slide-in-right': 'slide-in-right 200ms ease-out',
        shimmer: 'shimmer 1.6s infinite',
      },
    },
  },
  plugins: [],
};
