/** 端口类型常量与工具（与后端 services/port_types.py 对齐）。 */

export interface PortTypeDef {
  key: string
  label: string
  family: string      // fiber | optic | pon | copper
  familyLabel: string
  shape: string       // 外形：lc/sc/fc/st/rj45/cage/mpo
  polish: string      // UPC | APC
}

/** 类型族颜色（用于组首色条 / 类型标注） */
export const FAMILY_COLOR: Record<string, string> = {
  fiber: '#a855f7',
  optic: '#06b6d4',
  pon: '#ec4899',
  copper: '#f59e0b',
}

export const FAMILY_LABEL: Record<string, string> = {
  fiber: '光纤',
  optic: '光模块',
  pon: 'PON',
  copper: '电口',
}

/** 后端未返回时的兜底清单 */
export const FALLBACK_PORT_TYPES: PortTypeDef[] = [
  { key: 'LC/UPC', label: 'LC/UPC', family: 'fiber', familyLabel: '光纤', shape: 'lc', polish: 'UPC' },
  { key: 'LC/APC', label: 'LC/APC', family: 'fiber', familyLabel: '光纤', shape: 'lc', polish: 'APC' },
  { key: 'SC/UPC', label: 'SC/UPC', family: 'fiber', familyLabel: '光纤', shape: 'sc', polish: 'UPC' },
  { key: 'SC/APC', label: 'SC/APC', family: 'fiber', familyLabel: '光纤', shape: 'sc', polish: 'APC' },
  { key: 'FC/UPC', label: 'FC/UPC', family: 'fiber', familyLabel: '光纤', shape: 'fc', polish: 'UPC' },
  { key: 'FC/APC', label: 'FC/APC', family: 'fiber', familyLabel: '光纤', shape: 'fc', polish: 'APC' },
  { key: 'ST/UPC', label: 'ST/UPC', family: 'fiber', familyLabel: '光纤', shape: 'st', polish: 'UPC' },
  { key: 'ST/APC', label: 'ST/APC', family: 'fiber', familyLabel: '光纤', shape: 'st', polish: 'APC' },
  { key: 'E2000/APC', label: 'E2000/APC', family: 'fiber', familyLabel: '光纤', shape: 'sc', polish: 'APC' },
  { key: 'MPO/UPC', label: 'MPO/UPC', family: 'fiber', familyLabel: '光纤', shape: 'mpo', polish: 'UPC' },
  { key: 'MPO/APC', label: 'MPO/APC', family: 'fiber', familyLabel: '光纤', shape: 'mpo', polish: 'APC' },
  { key: 'SFP', label: 'SFP', family: 'optic', familyLabel: '光模块', shape: 'cage', polish: '' },
  { key: 'SFP+', label: 'SFP+', family: 'optic', familyLabel: '光模块', shape: 'cage', polish: '' },
  { key: 'SFP28', label: 'SFP28', family: 'optic', familyLabel: '光模块', shape: 'cage', polish: '' },
  { key: 'QSFP+', label: 'QSFP+', family: 'optic', familyLabel: '光模块', shape: 'cage', polish: '' },
  { key: 'QSFP28', label: 'QSFP28', family: 'optic', familyLabel: '光模块', shape: 'cage', polish: '' },
  { key: 'CFP', label: 'CFP', family: 'optic', familyLabel: '光模块', shape: 'cage', polish: '' },
  { key: 'PON/UPC', label: 'PON (SC/UPC)', family: 'pon', familyLabel: 'PON', shape: 'sc', polish: 'UPC' },
  { key: 'PON/APC', label: 'PON (SC/APC)', family: 'pon', familyLabel: 'PON', shape: 'sc', polish: 'APC' },
  { key: 'RJ45/CAT5e', label: 'RJ45 超五类', family: 'copper', familyLabel: '电口', shape: 'rj45', polish: '' },
  { key: 'RJ45/CAT6', label: 'RJ45 六类', family: 'copper', familyLabel: '电口', shape: 'rj45', polish: '' },
  { key: 'RJ45/CAT6A', label: 'RJ45 超六类', family: 'copper', familyLabel: '电口', shape: 'rj45', polish: '' },
  { key: 'RJ45/CAT7', label: 'RJ45 七类', family: 'copper', familyLabel: '电口', shape: 'rj45', polish: '' },
]

export function shapeOf(portTypes: PortTypeDef[], key: string): string {
  return portTypes.find(t => t.key === key)?.shape || 'lc'
}

export function familyColorOf(portTypes: PortTypeDef[], key: string): string {
  const fam = portTypes.find(t => t.key === key)?.family
  return fam ? (FAMILY_COLOR[fam] || '#64748b') : '#64748b'
}

/** 分组下拉选项（按族分组） */
export function portTypeOptions(portTypes: PortTypeDef[]) {
  const byFam = new Map<string, { label: string; value: string }[]>()
  for (const t of portTypes) {
    if (!byFam.has(t.family)) byFam.set(t.family, [])
    byFam.get(t.family)!.push({ label: t.label, value: t.key })
  }
  return [...byFam.entries()].map(([fam, children]) => ({
    type: 'group' as const,
    key: fam,
    label: FAMILY_LABEL[fam] || fam,
    children,
  }))
}
