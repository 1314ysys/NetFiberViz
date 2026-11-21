import type { GlobalThemeOverrides } from 'naive-ui'

/** 深色（NOC 控制台） */
export const darkOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#38bdf8',
    primaryColorHover: '#7dd3fc',
    primaryColorPressed: '#0ea5e9',
    primaryColorSuppl: '#38bdf8',
    infoColor: '#38bdf8',
    successColor: '#22c55e',
    warningColor: '#f59e0b',
    errorColor: '#ef4444',

    bodyColor: '#080d16',
    cardColor: '#0f1623',
    modalColor: '#0f1623',
    popoverColor: '#16202f',
    tableColor: 'transparent',
    tableHeaderColor: '#131d2b',
    inputColor: '#131d2b',
    actionColor: '#131d2b',
    borderColor: '#1e2a3a',
    dividerColor: '#1e2a3a',
    hoverColor: '#1b2637',

    textColorBase: '#e6edf6',
    textColor1: '#e6edf6',
    textColor2: '#9fb0c4',
    textColor3: '#64748b',

    borderRadius: '10px',
    borderRadiusSmall: '6px',
    fontSize: '13px',
    fontSizeSmall: '12px',
    heightMedium: '34px',
    heightLarge: '38px',
  },
  Card: { borderColor: '#1e2a3a', titleFontSizeMedium: '14px' },
  DataTable: {
    thColor: '#131d2b', thTextColor: '#9fb0c4', tdColor: 'transparent',
    tdColorHover: '#1b2637', borderColor: '#1e2a3a', thFontWeight: '600', fontSizeMedium: '12.5px',
  },
  Tree: {
    nodeTextColor: '#c8d4e3',
    nodeColorActive: 'rgba(56, 189, 248, 0.14)',
    nodeTextColorActive: '#38bdf8',
    nodeColorHover: '#1b2637',
  },
  Input: {
    color: '#131d2b', colorFocus: '#131d2b',
    border: '1px solid #1e2a3a', borderHover: '1px solid #2b3a4d',
    borderFocus: '1px solid #38bdf8',
    boxShadowFocus: '0 0 0 2px rgba(56,189,248,0.15)',
  },
  Select: {
    peers: {
      InternalSelection: {
        color: '#131d2b',
        border: '1px solid #1e2a3a', borderHover: '1px solid #2b3a4d',
        borderActive: '1px solid #38bdf8', borderFocus: '1px solid #38bdf8',
      },
    },
  },
  Tabs: { tabTextColorActiveLine: '#38bdf8', tabTextColorHoverLine: '#7dd3fc', barColor: '#38bdf8', tabBorderColor: '#1e2a3a' },
  Tag: { borderRadius: '999px' },
  Button: { fontWeight: '500' },
  Statistic: { labelFontSize: '12px', valueFontSize: '26px' },
  Message: { borderRadius: '8px' },
}

/** 浅色 */
export const lightOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#0284c7',
    primaryColorHover: '#0ea5e9',
    primaryColorPressed: '#0369a1',
    primaryColorSuppl: '#0284c7',
    infoColor: '#0284c7',
    successColor: '#16a34a',
    warningColor: '#d97706',
    errorColor: '#dc2626',

    bodyColor: '#f3f6fb',
    cardColor: '#ffffff',
    modalColor: '#ffffff',
    popoverColor: '#ffffff',
    tableColor: 'transparent',
    tableHeaderColor: '#f1f5f9',
    inputColor: '#ffffff',
    actionColor: '#f8fafc',
    borderColor: '#e3e9f1',
    dividerColor: '#e9eef5',
    hoverColor: '#eef2f8',

    textColorBase: '#0f172a',
    textColor1: '#0f172a',
    textColor2: '#475569',
    textColor3: '#94a3b8',

    borderRadius: '10px',
    borderRadiusSmall: '6px',
    fontSize: '13px',
    fontSizeSmall: '12px',
    heightMedium: '34px',
    heightLarge: '38px',
    boxShadow1: '0 1px 3px rgba(15,23,42,.08)',
    boxShadow2: '0 8px 24px rgba(15,23,42,.12)',
  },
  Card: { borderColor: '#e3e9f1', titleFontSizeMedium: '14px' },
  DataTable: {
    thColor: '#f1f5f9', thTextColor: '#475569', tdColor: 'transparent',
    tdColorHover: '#eef2f8', borderColor: '#e9eef5', thFontWeight: '600', fontSizeMedium: '12.5px',
  },
  Tree: {
    nodeTextColor: '#334155',
    nodeColorActive: 'rgba(2,132,199,.10)',
    nodeTextColorActive: '#0284c7',
    nodeColorHover: '#eef2f8',
  },
  Input: {
    color: '#ffffff', colorFocus: '#ffffff',
    border: '1px solid #dbe3ee', borderHover: '1px solid #b9c6d8',
    borderFocus: '1px solid #0284c7',
    boxShadowFocus: '0 0 0 2px rgba(2,132,199,0.15)',
  },
  Select: {
    peers: {
      InternalSelection: {
        color: '#ffffff',
        border: '1px solid #dbe3ee', borderHover: '1px solid #b9c6d8',
        borderActive: '1px solid #0284c7', borderFocus: '1px solid #0284c7',
      },
    },
  },
  Tabs: { tabTextColorActiveLine: '#0284c7', tabTextColorHoverLine: '#0ea5e9', barColor: '#0284c7', tabBorderColor: '#e3e9f1' },
  Tag: { borderRadius: '999px' },
  Button: { fontWeight: '500' },
  Statistic: { labelFontSize: '12px', valueFontSize: '26px' },
  Message: { borderRadius: '8px' },
}
