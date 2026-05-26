/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['Syne', 'sans-serif'],
        sans: ['DM Sans', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        // Control room design tokens
        ctrl: {
          bg:      'oklch(10% 0.008 245)',
          surface: 'oklch(14% 0.010 245)',
          panel:   'oklch(18% 0.011 245)',
          raised:  'oklch(22% 0.012 245)',
          border:  'oklch(27% 0.013 245)',
          divide:  'oklch(20% 0.010 245)',
          text:    'oklch(92% 0.004 245)',
          muted:   'oklch(55% 0.009 245)',
          dim:     'oklch(38% 0.009 245)',
        },
        status: {
          ok:       'oklch(72% 0.14 164)',
          info:     'oklch(75% 0.12 205)',
          warn:     'oklch(79% 0.15 80)',
          err:      'oklch(66% 0.17 25)',
          'ok-bg':   'oklch(17% 0.04 164)',
          'info-bg': 'oklch(17% 0.04 205)',
          'warn-bg': 'oklch(18% 0.05 80)',
          'err-bg':  'oklch(17% 0.05 25)',
        },
        // Legacy aliases so untouched code still compiles
        'esteps-cyan':   'oklch(75% 0.12 205)',
        'esteps-green':  'oklch(72% 0.14 164)',
        'esteps-orange': 'oklch(79% 0.15 80)',
        'dark-bg':       'oklch(10% 0.008 245)',
        'dark-surface':  'oklch(14% 0.010 245)',
        'dark-card':     'oklch(18% 0.011 245)',
        'dark-border':   'oklch(27% 0.013 245)',
        muted:           'oklch(55% 0.009 245)',
      },
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '0.875rem', letterSpacing: '0.08em' }],
        xs:   ['0.75rem',  { lineHeight: '1rem' }],
        sm:   ['0.875rem', { lineHeight: '1.375rem' }],
        base: ['1rem',     { lineHeight: '1.6rem' }],
        lg:   ['1.125rem', { lineHeight: '1.75rem' }],
        xl:   ['1.25rem',  { lineHeight: '1.75rem' }],
        '2xl':['1.5rem',   { lineHeight: '2rem' }],
      },
      letterSpacing: {
        label: '0.12em',
        wide:  '0.08em',
      },
      boxShadow: {
        panel: '0 1px 3px 0 oklch(0% 0 0 / 0.4)',
        float: '0 8px 24px -4px oklch(0% 0 0 / 0.5)',
        // legacy
        card:        '0 4px 16px -2px oklch(0% 0 0 / 0.3)',
        'card-hover':'0 8px 24px -4px oklch(0% 0 0 / 0.4)',
      },
      borderRadius: {
        none: '0',
        sm:   '0.25rem',
        base: '0.375rem',
        md:   '0.5rem',
        lg:   '0.75rem',
        xl:   '1rem',
      },
      keyframes: {
        slide: {
          '0%':   { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(400%)' },
        },
      },
      animation: {
        slide: 'slide 1s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
