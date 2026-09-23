/** 工单18 · 设计令牌（暖色体系：宣纸暖白 / 琥珀 / 陶土） */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // 透明度刻度补充。
      // Tailwind v3 默认刻度为 0/5/10/15/20/25/30/35/40/45/50/55/60/65/70/75/80/85/90/95/100，
      // **不含 12**。因此 `bg-clay/12`、`bg-steel/12`、`bg-amber/12` 不会生成任何 CSS，
      // 且 Tailwind 不报错、静默丢弃 —— 表现为导航高亮与状态标签"少了底色"。
      // 这里把 12 补进刻度，一次修复全部既有与新增用法（含迁入 apps/toc/pages/GuidePage.tsx 的 bg-clay/12）。
      opacity: {
        12: '0.12',
      },
      colors: {
        paper: '#FBF3E7',
        surface: '#FFFCF6',
        'surface-2': '#F8EEE1',
        ink: '#33251A',
        'ink-2': '#513C28',
        'ink-3': '#806A55',
        'ink-4': '#A8937C',
        amber: '#C0801F',
        'amber-deep': '#8A5510',
        'amber-soft': '#E8C06A',
        clay: '#B4532F',
        'clay-deep': '#8A3A1E',
        'clay-soft': '#E0A183',
        sand: '#E7D3B4',

        // —— 工单16-20 延伸：ToB 运营控制台冷色体系 ——
        // 命名用 cool 而非 slate：slate 是 Tailwind 内置调色板（slate-50..900），
        // 同名扩展会与内置键混在同一个命名空间里，容易误用。
        cool: {
          bg: '#F4F6F8',
          surface: '#FFFFFF',
          'surface-2': '#EDF1F5',
          line: '#D8E0E8',
          ink: '#1B2733',
          'ink-2': '#405265',
          'ink-3': '#6B7C8F',
          'ink-4': '#9AA9B8',
        },
        steel: '#2F6F8F',
        'steel-deep': '#1F4E66',
        'steel-soft': '#BBD5E2',
      },
      fontFamily: {
        display: ['Songti SC', 'STSong', 'Noto Serif SC', 'Georgia', 'serif'],
        ui: ['PingFang SC', 'Microsoft YaHei', 'Hiragino Sans GB', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        panel: '0 1px 2px rgba(51,37,26,.05), 0 16px 34px -22px rgba(51,37,26,.34)',
        console: '0 1px 2px rgba(27,39,51,.06), 0 10px 24px -18px rgba(27,39,51,.28)',
      },
      keyframes: {
        rise: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'none' },
        },
      },
      animation: {
        rise: 'rise .35s cubic-bezier(.22,.8,.28,1) both',
      },
    },
  },
  plugins: [],
}
