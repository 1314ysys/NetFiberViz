<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, useMessage, useDialog } from 'naive-ui'
import { api } from '../api/client'
import { useResourceStore, DEVICE_TYPE_LABEL } from '../stores/resource'
import { useSessionStore } from '../stores/session'
import { familyColorOf, shapeOf } from '../utils/portTypes'
import { useCanvas } from '../composables/useCanvas'
import { useLongPress } from '../composables/useLongPress'
import Icon from '../components/ui/Icon.vue'
import PortShape from '../components/canvas/PortShape.vue'
import DeviceDesigner from '../components/canvas/DeviceDesigner.vue'
import ContextMenu from '../components/ui/ContextMenu.vue'
import type { MenuItem } from '../components/ui/ContextMenu.vue'
import DialogForm from '../components/ui/DialogForm.vue'
import type { FormField } from '../components/ui/DialogForm.vue'
import Breadcrumb from '../components/ui/Breadcrumb.vue'
import type { Crumb } from '../components/ui/Breadcrumb.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const store = useResourceStore()
const session = useSessionStore()
const cv = useCanvas()

const mode = computed<'rack' | 'odf'>(() => (route.path.includes('/odf/') ? 'odf' : 'rack'))
const nodeId = computed(() => Number(route.params.id))

/* ============ 网络机柜 ============ */
const U_H = 20
const RACK_W = 320

const rack = computed(() => store.racks.find(r => r.id === nodeId.value))
const cabinet = computed(() => store.cabinets.find(c => c.id === nodeId.value))
const currentRoomId = computed<number | null>(() =>
  mode.value === 'rack' ? (rack.value?.room_id ?? null) : (cabinet.value?.room_id ?? null))
const canWrite = computed(() => session.canWriteRoom(currentRoomId.value))
const rackDevices = computed(() => store.devicesOfRack(nodeId.value))
const uCount = computed(() => rack.value?.u_count || 42)
const rackH = computed(() => uCount.value * U_H + 36)
const svgRef = ref<SVGSVGElement>()

/** 拖拽期间的 U 位覆盖值（computed 快照不可变，需独立响应式状态） */
const devU = ref<Record<number, number>>({})

interface DevPortGroup {
  name: string
  seq: number
  typeColor: string
  ports: { no: string; status: string; type: string; remark: string }[]
}
interface DevBox {
  id: number; name: string; type: string; ports: number; used: number
  y: number; u: number; uHeight: number; height: number; uTop: number
  portStatus: string[]
  groups: DevPortGroup[]
  stats: { total: number; free: number; used: number; reserved: number; fault: number }
  hasFault: boolean
  layout: string
  /** 渲染辅助：文字基线 / 字号 / 名称与右侧信息 */
  textY: number
  nameFont: number
  metaFont: number
  displayName: string
  metaText: string
}

function summarize(ports: { status: string }[]) {
  const s = { total: ports.length, free: 0, used: 0, reserved: 0, fault: 0 } as
    { total: number; free: number; used: number; reserved: number; fault: number }
  for (const p of ports) {
    if (p.status === 'used') s.used++
    else if (p.status === 'reserved') s.reserved++
    else if (p.status === 'fault') s.fault++
    else s.free++
  }
  return s
}

const devBoxes = computed<DevBox[]>(() => rackDevices.value.map(d => {
  const ps = store.portsOfDevice(d.id)
  const raw = devU.value[d.id] ?? d.u_position
  const uh = Math.min(Math.max(d.u_height || 1, 1), uCount.value)
  const u = Math.min(Math.max(raw, 1), Math.max(uCount.value - uh + 1, 1))
  const stats = summarize(ps)

  // 设备占据 U(u) .. U(u+uh-1)，矩形顶部必须对齐最高的那个 U，
  // 否则多 U 设备会被整体下移，压住相邻设备（文字/色条重叠的根因）。
  const topU = u + uh - 1

  // 按端口组归并（保持组序），用于分排渲染
  const byGroup = new Map<string, DevPortGroup>()
  for (const p of ps) {
    const gname = p.group_name || '端口'
    const gseq = p.group_seq ?? 0
    const key = `${gseq}::${gname}`
    if (!byGroup.has(key)) {
      byGroup.set(key, {
        name: gname, seq: gseq,
        typeColor: familyColorOf(store.portTypes, p.port_type),
        ports: [],
      })
    }
    byGroup.get(key)!.ports.push({
      no: p.port_no, status: p.status, type: p.port_type, remark: p.remark || '',
    })
  }
  const groups = [...byGroup.values()].sort((a, b) => a.seq - b.seq || a.name.localeCompare(b.name))

  return {
    id: d.id, name: d.name, type: d.category || d.device_type,
    ports: ps.length, used: stats.used,
    y: (uCount.value - topU) * U_H + 18,
    u,
    uHeight: uh,
    height: uh * U_H - 2,
    uTop: topU,
    portStatus: ps.map(p => p.status),
    groups,
    stats,
    hasFault: stats.fault > 0,
    layout: d.port_layout || 'horizontal',
    // 文字区：1U 用 8.5/7.5，2U 用 9.5/8.5，更高用 10/9
    textY: uh === 1 ? 10 : uh === 2 ? 12 : 14,
    nameFont: uh === 1 ? 8.5 : uh === 2 ? 9.5 : 10,
    metaFont: uh === 1 ? 7.5 : uh === 2 ? 8.5 : 9,
    displayName: d.name.length > 16 ? d.name.slice(0, 15) + '…' : d.name,
    metaText: [
      DEVICE_TYPE_LABEL[d.category || d.device_type] || d.category || d.device_type,
      `${stats.used}/${stats.total}P`,
      `${uh}U`,
      stats.fault ? `⚠${stats.fault}` : '',
    ].filter(Boolean).join(' · '),
  }
}))

/** 机柜内故障端口总数（用于顶部强提示） */
const rackFaultCount = computed(() =>
  devBoxes.value.reduce((n, d) => n + d.stats.fault, 0))

/**
 * 端口分排布局（严格避开文字区）：
 * - 端口带固定贴在设备条底部，高度按 U 数分配：1U=4px / 2U=6px / ≥4U=8px
 * - 每行至少 4px 高，行数受带高限制
 * - 端口块宽度有上限（9px），端口少时整排居中，不再被拉成超宽条
 * - port_layout = vertical 时组内每行最多 6 口换行
 */
function portRows(d: DevBox) {
  const usableW = RACK_W - 28
  const groups = d.groups
  if (!groups.length) return []

  const vertical = d.layout === 'vertical'
  const wrapAt = vertical ? 6 : 99999
  const GAP_PORTS = 2
  const MAX_PORT_W = 9

  // 端口带高度：1U 只有 4px，2U 6px，多 U 8px
  const bandH = d.height <= 20 ? 4 : d.height <= 40 ? 6 : 8
  const baseY = d.height - bandH - 1.5

  // 展开成逻辑行
  const logical: { g: DevPortGroup; slice: DevPortGroup['ports']; first: boolean }[] = []
  for (const g of groups) {
    for (let s = 0; s < g.ports.length; s += wrapAt) {
      logical.push({ g, slice: g.ports.slice(s, s + wrapAt), first: s === 0 })
    }
  }

  // 每行至少 4px
  const maxRows = Math.max(1, Math.floor(bandH / 4))
  const shown = logical.slice(0, maxRows)
  const rowCount = Math.max(shown.length, 1)
  const rowH = Math.max(2.4, bandH / rowCount)

  const out: {
    y: number; h: number; barX: number; typeColor: string; short: string
    segs: { x: number; w: number; status: string; shape: string; type: string }[]
  }[] = []

  shown.forEach((L, ri) => {
    const n = L.slice.length
    // 宽度上限 + 居中
    const portW = Math.min(Math.max(usableW / (n + GAP_PORTS) * 0.82, 1.2), MAX_PORT_W)
    const step = portW + 0.8
    const totalW = n * step - 0.8
    const startX = 10 + Math.max((usableW - totalW) / 2, 4)

    const segs = L.slice.map((p, i) => ({
      x: startX + i * step,
      w: portW,
      status: p.status,
      shape: shapeOf(store.portTypes, p.type),
      type: p.type,
    }))

    out.push({
      y: baseY + ri * rowH,
      h: Math.max(rowH - 0.6, 1.8),
      barX: 6,
      typeColor: L.g.typeColor,
      short: L.first
        ? (L.g.name.replace(/[^A-Za-z0-9]/g, '').slice(0, 4).toUpperCase() || 'PORT')
        : '',
      segs,
    })
  })
  return out
}

/** 查找最近的可放置 U 位（本地实时计算，用于拖拽吸附） */
function findFreeU(selfId: number, wantU: number, uh: number): number | null {
  const occ = rackDevices.value
    .filter(d => d.id !== selfId)
    .map(d => [d.u_position, d.u_position + (d.u_height || 1) - 1] as [number, number])
  const maxU = Math.max(uCount.value - uh + 1, 1)
  const free = (u: number) => {
    if (u < 1 || u > maxU) return false
    const hi = u + uh - 1
    return !occ.some(([a, b]) => u <= b && a <= hi)
  }
  const w = Math.min(Math.max(wantU, 1), maxU)
  if (free(w)) return w
  for (let dlt = 1; dlt <= uCount.value; dlt++) {
    for (const c of [w + dlt, w - dlt]) if (free(c)) return c
  }
  return null
}

/* ============ ODF 配线柜 ============ */
interface UnitBox { id: number; name: string; pos_x: number; pos_y: number }
interface TrayBox {
  id: number; unit_id: number; name: string; pos_x: number; pos_y: number
  slots: number; used: number; rows: number; perRow: number
  /** 逐孔位状态（顺序与孔位一致，用于逐格色块） */
  portStatus: string[]
  slotLabels: string[]
  slotRemarks: string[]
  /** 逐孔位对应的 port.id（用于查对端） */
  portIds: number[]
}
const units = ref<UnitBox[]>([])
const trays = ref<TrayBox[]>([])
const pendingUnitId = ref<number | null>(null)

const ROW_H = 56
const TRAY_W = 300
const TRAY_H = 40

async function loadOdf() {
  const r = await api.get(`/odf/cabinets/${nodeId.value}/layout`)
  units.value = r.data.units
  pendingUnitId.value = r.data.pending_unit_id
  const t = r.data.trays as any[]

  // 兜底布局：历史数据可能没有坐标（0,0），按单元柜序号与盘序号自动排布
  const unitIdx = new Map<number, number>()
  units.value.forEach((u, i) => unitIdx.set(u.id, i))
  const perUnitCount = new Map<number, number>()

  const withStats: TrayBox[] = []
  for (const tr of t) {
    const slots = await api.get('/odf/slots', { params: { tray_id: tr.id } })
    const list = slots.data as any[]
    let px = tr.pos_x ?? 0
    let py = tr.pos_y ?? 0
    if (px === 0 && py === 0) {
      const ui = unitIdx.get(tr.unit_id) ?? 0
      const seq = perUnitCount.get(tr.unit_id) ?? 0
      perUnitCount.set(tr.unit_id, seq + 1)
      px = 60 + ui * (TRAY_W + 60)
      py = 60 + seq * ROW_H
    }
    withStats.push({
      id: tr.id, unit_id: tr.unit_id, name: tr.name,
      pos_x: px, pos_y: py,
      slots: list.length,
      used: list.filter(s => s.port?.status === 'used').length,
      rows: tr.rows, perRow: tr.slots_per_row,
      portStatus: list.map(s => s.port?.status || 'free'),
      slotLabels: list.map(s => s.label || ''),
      slotRemarks: list.map(s => s.port?.remark || ''),
      portIds: list.map(s => s.port?.id ?? 0),
    })
  }
  trays.value = withStats

  // 单元柜自身坐标若未设置，取其首个盘的左上角
  for (const u of units.value) {
    const first = withStats.find(x => x.unit_id === u.id)
    if (first && u.pos_x === 0 && u.pos_y === 0) {
      u.pos_x = first.pos_x
      u.pos_y = first.pos_y
    }
  }
}

/** 单元柜包围盒（由其内部盘推导） */
function unitBox(u: UnitBox) {
  const ts = trays.value.filter(t => t.unit_id === u.id)
  if (!ts.length) return { x: u.pos_x, y: u.pos_y, w: TRAY_W, h: TRAY_H + 26 }
  const minX = Math.min(...ts.map(t => t.pos_x))
  const minY = Math.min(...ts.map(t => t.pos_y))
  const maxX = Math.max(...ts.map(t => t.pos_x + TRAY_W))
  const maxY = Math.max(...ts.map(t => t.pos_y + TRAY_H))
  return { x: minX - 8, y: minY - 26, w: maxX - minX + 16, h: maxY - minY + 34 }
}

const looseTrays = computed(() => trays.value.filter(t => t.unit_id === pendingUnitId.value))

/* ============ 选择 / 拖拽 ============ */
type Sel = { kind: 'device' | 'unit' | 'tray'; id: number }
const selected = ref<Sel | null>(null)
const multiTrays = ref<Set<number>>(new Set())
const dirty = ref(false)
let saveTimer: any = null

/* ============ 悬停详情浮层 ============ */
interface TipRow { name: string; status: string; remark?: string }
const tip = ref<{
  show: boolean; x: number; y: number
  title: string; sub: string
  stats?: { total: number; free: number; used: number; reserved: number; fault: number }
  rows: TipRow[]
  hasFault?: boolean
}>({ show: false, x: 0, y: 0, title: '', sub: '', rows: [] })
let tipTimer: any = null

function showTip(evt: MouseEvent, payload: Omit<typeof tip.value, 'show' | 'x' | 'y'>) {
  clearTimeout(tipTimer)
  const x = evt.clientX
  const y = evt.clientY
  tipTimer = setTimeout(() => {
    tip.value = { ...payload, show: true, x, y }
  }, 150)
}

function hideTip() {
  clearTimeout(tipTimer)
  tip.value.show = false
}

/** 盘上单个孔位悬停：显示该孔位详情 */
function slotTipPayload(t: TrayBox, idx: number) {
  const status = t.portStatus[idx] || 'free'
  const label = t.slotLabels[idx] || `#${idx + 1}`
  const remark = t.slotRemarks[idx] || ''
  let peer = ''
  try {
    const cord = cordByPortId.value[Number(t.portIds?.[idx])]
    if (cord) {
      const otherId = cord.port_a_id === Number(t.portIds?.[idx]) ? cord.port_b_id : cord.port_a_id
      peer = store.portLabel(store.portById[otherId])
    }
  } catch { /* 忽略 */ }
  return {
    title: label,
    sub: [statusLabel(status), t.name + ' 盘', peer ? `对端 ${peer}` : ''].filter(Boolean).join(' · '),
    stats: undefined as any,
    rows: remark ? [{ name: '备注', status, remark }] : [],
    hasFault: false,
    single: true,
    singleStatus: status,
  }
}

const cordByPortId = ref<Record<number, any>>({})

async function loadCords() {
  try {
    const r = await api.get('/patch-cords')
    const m: Record<number, any> = {}
    for (const c of r.data as any[]) {
      m[c.port_a_id] = c
      m[c.port_b_id] = c
    }
    cordByPortId.value = m
  } catch { /* 忽略 */ }
}

function statusLabel(s: string) {
  return ({ free: '空闲', used: '在用', reserved: '预留', fault: '故障' } as Record<string, string>)[s] || s
}

/** 设备悬停：端口统计 + 故障/预留端口清单（含备注） */
function deviceTipPayload(d: DevBox) {
  const ps = store.portsOfDevice(d.id)
  const abnormal = ps
    .filter(p => p.status === 'fault' || p.status === 'reserved')
    .map(p => ({ name: p.port_no, status: p.status, remark: p.remark }))
  // 故障优先，其次预留
  abnormal.sort((a, b) => (a.status === b.status ? 0 : a.status === 'fault' ? -1 : 1))
  return {
    title: d.name,
    sub: `${DEVICE_TYPE_LABEL[d.type] || d.type} · ${d.uHeight}U · U${d.u}–U${d.uTop}`,
    stats: d.stats,
    rows: abnormal.slice(0, 8),
    hasFault: d.hasFault,
  }
}

/** 盘悬停：孔位统计 + 异常孔位清单 */
function trayTipPayload(t: TrayBox) {
  const stats = summarize(t.portStatus.map(s => ({ status: s })))
  const abnormal = t.portStatus
    .map((s, i) => ({ name: t.slotLabels[i], status: s, remark: t.slotRemarks[i] }))
    .filter(x => x.status === 'fault' || x.status === 'reserved')
  return {
    title: `${t.name} 盘`,
    sub: `${t.rows}×${t.perRow} · 共 ${t.slots} 孔位`,
    stats,
    rows: abnormal.slice(0, 8),
    hasFault: false,   // ODF 孔位故障不做强提示（可能是不值得检修的纤芯）
  }
}

const tipStyle = computed(() => {
  const w = 290
  const vw = window.innerWidth
  const left = Math.min(tip.value.x + 14, vw - w - 12)
  return { left: left + 'px', top: tip.value.y + 14 + 'px', width: w + 'px' }
})

/* ============ 面包屑 ============ */
const crumbs = computed<Crumb[]>(() => {
  const roomId = mode.value === 'rack' ? rack.value?.room_id : cabinet.value?.room_id
  const room = store.rooms.find(r => r.id === roomId)
  const items: Crumb[] = []
  if (roomId) items.push({ label: room?.name || '机房', to: `/topology/${roomId}` })
  if (mode.value === 'rack') {
    items.push({ label: rack.value?.name || '机柜' })
  } else {
    items.push({ label: cabinet.value?.name || '配线柜' })
  }
  return items
})

/* ============ 状态自动刷新（供外部平台推送后前端及时呈现） ============ */
const autoRefresh = ref(true)
let pollTimer: any = null

async function silentRefresh() {
  // 拖拽中或弹窗打开时跳过，避免打断操作
  if (!autoRefresh.value || dragCtx || dlg.value.show) return
  try {
    await store.loadBase()
    if (mode.value === 'odf') await loadOdf()
  } catch { /* 静默失败，等下个周期 */ }
}

let dragCtx: null | {
  kind: 'device' | 'tray' | 'unit'
  id: number
  origin: { x: number; y: number }
  trays?: { id: number; x: number; y: number }[]
} = null

/** 移动端长按 = 右键菜单（对象 / 画布各一个实例） */
const lpItem = useLongPress()
const lpCanvas = useLongPress()

function onCanvasDown(evt: PointerEvent) {
  if (cv.trackPointerDown(evt)) return
  selected.value = null
  cv.startPan(evt)
  lpCanvas.start(evt, (pos) => {
    cv.endDrag()
    openCanvasMenu({ clientX: pos.x, clientY: pos.y, preventDefault() {}, stopPropagation() {} } as any)
  })
}

/** 空白处双击 → 放大 / 还原 */
function onCanvasDblClick(evt: MouseEvent) {
  cv.handleDoubleTap(evt)
}

function startDeviceDrag(evt: PointerEvent, d: DevBox) {
  evt.stopPropagation()
  if (cv.trackPointerDown(evt)) return
  selected.value = { kind: 'device', id: d.id }
  cv.startDrag(evt, `dev-${d.id}`, 0, d.y)
  dragCtx = { kind: 'device', id: d.id, origin: { x: 0, y: d.y } }
  lpItem.start(evt, (pos) => {
    cv.endDrag(); dragCtx = null
    openDeviceMenu({ clientX: pos.x, clientY: pos.y, preventDefault() {}, stopPropagation() {} } as any, d)
  })
}

function startTrayDrag(evt: PointerEvent, t: TrayBox) {
  evt.stopPropagation()
  if (evt.ctrlKey || evt.metaKey) {
    const s = new Set(multiTrays.value)
    s.has(t.id) ? s.delete(t.id) : s.add(t.id)
    multiTrays.value = s
  } else if (!multiTrays.value.has(t.id)) {
    multiTrays.value = new Set()
  }
  if (cv.trackPointerDown(evt)) return
  selected.value = { kind: 'tray', id: t.id }
  cv.startDrag(evt, `tray-${t.id}`, t.pos_x, t.pos_y)
  dragCtx = { kind: 'tray', id: t.id, origin: { x: t.pos_x, y: t.pos_y } }
  lpItem.start(evt, (pos) => {
    cv.endDrag(); dragCtx = null
    openTrayMenu({ clientX: pos.x, clientY: pos.y, preventDefault() {}, stopPropagation() {} } as any, t)
  })
}

function startUnitDrag(evt: PointerEvent, u: UnitBox) {
  evt.stopPropagation()
  if (cv.trackPointerDown(evt)) return
  selected.value = { kind: 'unit', id: u.id }
  cv.startDrag(evt, `unit-${u.id}`, u.pos_x, u.pos_y)
  dragCtx = {
    kind: 'unit', id: u.id, origin: { x: u.pos_x, y: u.pos_y },
    trays: trays.value.filter(t => t.unit_id === u.id).map(t => ({ id: t.id, x: t.pos_x, y: t.pos_y })),
  }
}

function onPointerMove(evt: PointerEvent) {
  if (cv.trackPointerMove(evt)) return
  lpItem.move(evt)
  lpCanvas.move(evt)
  cv.onMove(evt, (_key, x, y) => {
    const ctx = dragCtx
    if (!ctx) return
    if (ctx.kind === 'device') {
      // y 是设备矩形顶部 → 对应最高 U（topU）；起始 U = topU - uh + 1
      const topU = Math.round(uCount.value - (y - 18) / U_H)
      const box = devBoxes.value.find(b => b.id === ctx.id)
      const uh = box?.uHeight ?? 1
      const wantU = topU - uh + 1
      // 实时吸附到最近空闲 U 区，拖拽过程中不会出现重叠
      const snapped = findFreeU(ctx.id, wantU, uh)
      if (snapped !== null) {
        devU.value = { ...devU.value, [ctx.id]: snapped }
      }
      return
    }
    if (ctx.kind === 'tray') {
      const t = trays.value.find(v => v.id === ctx.id)
      if (t) { t.pos_x = Math.round(x / 10) * 10; t.pos_y = Math.round(y / 10) * 10 }
      return
    }
    // unit：整体平移
    const dx = Math.round((x - ctx.origin.x) / 10) * 10
    const dy = Math.round((y - ctx.origin.y) / 10) * 10
    const u = units.value.find(v => v.id === ctx.id)
    if (u) { u.pos_x = ctx.origin.x + dx; u.pos_y = ctx.origin.y + dy }
    for (const ot of ctx.trays || []) {
      const t = trays.value.find(v => v.id === ot.id)
      if (t) { t.pos_x = ot.x + dx; t.pos_y = ot.y + dy }
    }
  })
}

function onPointerUp(evt?: PointerEvent) {
  lpItem.cancel(); lpCanvas.cancel()
  if (evt) cv.trackPointerUp(evt)
  const key = cv.endDrag()
  const ctx = dragCtx
  dragCtx = null
  if (!key || !ctx) return
  if (ctx.kind === 'device') return saveDeviceU(ctx.id)
  if (ctx.kind === 'tray') return saveTray(ctx.id)
  return saveUnit(ctx.id)
}

async function saveDeviceU(deviceId: number) {
  const u = devU.value[deviceId]
  if (!u) return
  try {
    await api.put(`/devices/${deviceId}`, { u_position: u })
    await store.loadBase()
    devU.value = {}
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败（U 位可能已冲突）')
    await store.loadBase()
    devU.value = {}
  }
}

async function saveTray(trayId: number) {
  const t = trays.value.find(v => v.id === trayId)
  if (!t) return
  dirty.value = true
  try {
    await api.put(`/odf/trays/${trayId}`, { pos_x: t.pos_x, pos_y: t.pos_y })
    dirty.value = false
  } catch (e: any) { message.error(e.response?.data?.detail || '保存失败') }
}

async function saveUnit(unitId: number) {
  const u = units.value.find(v => v.id === unitId)
  if (!u) return
  try {
    await api.put(`/odf/units/${unitId}`, { pos_x: u.pos_x, pos_y: u.pos_y })
    for (const t of trays.value.filter(v => v.unit_id === unitId)) {
      await api.put(`/odf/trays/${t.id}`, { pos_x: t.pos_x, pos_y: t.pos_y })
    }
    dirty.value = false
  } catch (e: any) { message.error(e.response?.data?.detail || '保存失败') }
}

/* ============ 右键菜单 ============ */
const menu = ref<{ show: boolean; x: number; y: number; title: string; items: MenuItem[]; target: Sel | null }>(
  { show: false, x: 0, y: 0, title: '', items: [], target: null })

function openDeviceMenu(evt: MouseEvent, d: DevBox) {
  evt.preventDefault(); evt.stopPropagation()
  selected.value = { kind: 'device', id: d.id }
  menu.value = {
    show: true, x: evt.clientX, y: evt.clientY, title: d.name, target: { kind: 'device', id: d.id },
    items: [
      { key: 'enter', label: '进入端口视图', hint: '双击' },
      { key: 'edit', label: '修改设备…', disabled: !canWrite.value },
      { key: 'div', label: '', divider: true },
      { key: 'delete', label: '删除设备', danger: true, disabled: !canWrite.value },
    ],
  }
}

function openUnitMenu(evt: MouseEvent, u: UnitBox) {
  evt.preventDefault(); evt.stopPropagation()
  selected.value = { kind: 'unit', id: u.id }
  menu.value = {
    show: true, x: evt.clientX, y: evt.clientY, title: `${u.name} 单元柜`, target: { kind: 'unit', id: u.id },
    items: [
      { key: 'enter', label: '进入端口视图', hint: '双击' },
      { key: 'add-tray', label: '在此单元柜新建盘', disabled: !canWrite.value },
      { key: 'rename', label: '重命名单元柜…', disabled: !canWrite.value },
      { key: 'div', label: '', divider: true },
      { key: 'ungroup', label: '解散单元柜', danger: true, disabled: !canWrite.value },
    ],
  }
}

function openTrayMenu(evt: MouseEvent, t: TrayBox) {
  evt.preventDefault(); evt.stopPropagation()
  if (!multiTrays.value.has(t.id)) {
    multiTrays.value = new Set([t.id])
  }
  selected.value = { kind: 'tray', id: t.id }
  const n = multiTrays.value.size
  menu.value = {
    show: true, x: evt.clientX, y: evt.clientY,
    title: n > 1 ? `已选 ${n} 个盘` : `${t.name} 盘`,
    target: { kind: 'tray', id: t.id },
    items: [
      { key: 'enter', label: '进入端口视图', hint: '双击' },
      { key: 'group', label: n > 1 ? `组合为单元柜（${n} 个盘）` : '组合为单元柜…', disabled: !canWrite.value },
      { key: 'rename', label: '重命名盘…', disabled: !canWrite.value },
      { key: 'div', label: '', divider: true },
      { key: 'delete', label: '删除盘', danger: true, disabled: !canWrite.value },
    ],
  }
}

function openCanvasMenu(evt: MouseEvent) {
  evt.preventDefault()
  menu.value = {
    show: true, x: evt.clientX, y: evt.clientY, title: '新建', target: null,
    items: mode.value === 'rack'
      ? [
        { key: 'new-device', label: '新建设备', disabled: !canWrite.value },
        { key: 'div', label: '', divider: true },
        { key: 'fit', label: '适应窗口' },
      ]
      : [
        { key: 'new-tray', label: '新建盘（12 孔）', disabled: !canWrite.value },
        { key: 'new-unit', label: '新建单元柜', disabled: !canWrite.value },
        { key: 'div', label: '', divider: true },
        { key: 'fit', label: '适应窗口' },
      ],
  }
}

function onMenuSelect(key: string) {
  const t = menu.value.target
  if (key === 'fit') return fitAll()
  if (key === 'new-device') return newDevice()
  if (key === 'new-tray') return newTray()
  if (key === 'new-unit') return newUnit()
  if (!t) return

  if (key === 'enter') {
    if (t.kind === 'device') router.push(`/ports/device/${t.id}`)
    else if (t.kind === 'unit') router.push(`/ports/unit/${t.id}`)
    else router.push(`/ports/tray/${t.id}`)
    return
  }
  if (key === 'edit' && t.kind === 'device') return editDevice(t.id)
  if (key === 'delete' && t.kind === 'device') return deleteDevice(t.id)
  if (key === 'rename' && t.kind === 'unit') return renameUnit(t.id)
  if (key === 'rename' && t.kind === 'tray') return renameTray(t.id)
  if (key === 'add-tray' && t.kind === 'unit') return newTray(t.id)
  if (key === 'ungroup' && t.kind === 'unit') return ungroupUnit(t.id)
  if (key === 'group') return groupTrays()
  if (key === 'delete' && t.kind === 'tray') return deleteTray(t.id)
}

/* ============ 弹窗 ============ */
const dlg = ref<{ show: boolean; title: string; fields: FormField[]; initial: any; submit: (v: any) => Promise<void> }>(
  { show: false, title: '', fields: [], initial: {}, submit: async () => {} })

function openDlg(title: string, fields: FormField[], initial: any, submit: (v: any) => Promise<void>) {
  dlg.value = { show: true, title, fields, initial, submit }
}

const templateOptions = computed(() => {
  const cats = store.categories
  return store.templates.map(t => ({
    label: `${cats[t.category] || t.category} · ${t.name} · ${t.u_height ?? 1}U${t.builtin === false ? '（自绘）' : ''}`,
    value: t.key,
  }))
})

/* ============ 设备面板设计器 ============ */
const designerShow = ref(false)
const designerRef = ref<any>()

function openDesigner() {
  designerShow.value = true
  nextTick(() => designerRef.value?.open())
}

/** 设计器保存后，直接把新模板选进新建设备表单 */
function onDesignerSaved(key: string) {
  lastCustomKey.value = key
  message.success('模板已保存，可在「设备模板」中选择使用')
  if (dlg.value.show) {
    dlg.value.initial = { ...dlg.value.initial, template_key: key }
  }
}
const lastCustomKey = ref('')

function newDevice() {
  if (!rack.value) return
  openDlg('新建设备', [
    {
      key: 'template_key', label: '设备模板', type: 'select', required: true,
      default: 'sw-24ge-4sfp', options: templateOptions.value,
      hint: '模板决定端口分组、类型与数量；需要新面板布局请用工具栏「绘制模板」',
    },
    { key: 'name', label: '设备名称', required: true, placeholder: '如 汇聚交换机-01' },
    { key: 'model', label: '型号', placeholder: '选填' },
    { key: 'u_position', label: '起始 U 位', type: 'number', default: 1, min: 1 },
    {
      key: 'u_height', label: '占用 U 数', type: 'number', min: 1,
      hint: '留空则按模板默认（交换机 1U / OLT 2U / 光传送平台 2U）',
    },
    {
      key: 'port_layout', label: '端口排列', type: 'select', default: 'horizontal',
      options: [{ label: '横向', value: 'horizontal' }, { label: '纵向', value: 'vertical' }],
    },
    { key: 'remark', label: '备注', type: 'textarea' },
  ], { template_key: lastCustomKey.value || 'sw-24ge-4sfp' }, async (v) => {
    try {
      await api.post('/devices', {
        rack_id: rack.value!.id, name: v.name, model: v.model || '',
        template_key: v.template_key, u_position: Number(v.u_position || 1),
        u_height: v.u_height ? Number(v.u_height) : null,
        port_layout: v.port_layout || 'horizontal',
        remark: v.remark || '',
      })
      message.success('设备已创建')
      dlg.value.show = false
      await store.loadBase()
    } catch (e: any) { message.error(e.response?.data?.detail || '创建失败') }
  })
}

function editDevice(id: number) {
  const d = store.devices.find(x => x.id === id)
  if (!d) return
  openDlg('修改设备', [
    { key: 'name', label: '设备名称', required: true },
    { key: 'model', label: '型号' },
    { key: 'u_position', label: 'U 位', type: 'number', default: 1, min: 1 },
    { key: 'u_height', label: '占用 U 数', type: 'number', default: 1, min: 1,
      hint: '多 U 设备（如 OLT / 光传送平台）请按实际填写' },
    { key: 'mgmt_ip', label: '管理 IP' },
    { key: 'remark', label: '备注', type: 'textarea' },
  ], {
    name: d.name, model: d.model, u_position: d.u_position,
    u_height: d.u_height ?? 1, mgmt_ip: d.mgmt_ip, remark: d.remark,
  },
    async (v) => {
      await api.put(`/devices/${id}`, {
        name: v.name, model: v.model || '', u_position: Number(v.u_position || 1),
        u_height: Number(v.u_height || 1),
        mgmt_ip: v.mgmt_ip || '', remark: v.remark || '',
      })
      message.success('设备已更新'); dlg.value.show = false
      await store.loadBase()
    })
}

function deleteDevice(id: number) {
  const d = store.devices.find(x => x.id === id)
  dialog.warning({
    title: '删除设备', content: `确认删除「${d?.name}」？存在在用端口时会被拒绝。`,
    positiveText: '删除', negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.delete(`/devices/${id}`)
        message.success('设备已删除'); await store.loadBase()
      } catch (e: any) { message.error(e.response?.data?.detail || '删除失败') }
    },
  })
}

function newTray(unitId?: number) {
  if (mode.value !== 'odf') return
  const maxY = trays.value.length ? Math.max(...trays.value.map(t => t.pos_y)) + ROW_H : 60
  openDlg('新建盘', [
    { key: 'name', label: '盘号', required: true, placeholder: '如 1' },
    {
      key: 'spec', label: '规格', type: 'select', default: '1x12',
      options: [{ label: '1 行 × 12 孔（标准）', value: '1x12' }, { label: '2 行 × 6 孔', value: '2x6' }],
    },
  ], {}, async (v) => {
    const [rows, spr] = String(v.spec).split('x').map(Number)
    const body: any = { name: v.name, rows, slots_per_row: spr, seq: 1, pos_x: 60, pos_y: maxY }
    if (unitId) body.unit_id = unitId
    else body.cabinet_id = nodeId.value
    try {
      await api.post('/odf/trays', body)
      message.success('盘已创建'); dlg.value.show = false
      await loadOdf()
    } catch (e: any) { message.error(e.response?.data?.detail || '创建失败') }
  })
}

function newUnit() {
  if (mode.value !== 'odf') return
  const nextName = String.fromCharCode(65 + units.value.length)
  openDlg('新建单元柜', [
    { key: 'name', label: '单元柜标识', required: true, default: nextName, placeholder: '如 D' },
    { key: 'tray_count', label: '内含盘数', type: 'number', default: 2, min: 0 },
  ], {}, async (v) => {
    const maxX = units.value.length ? Math.max(...units.value.map(u => u.pos_x)) + 340 : 60
    try {
      await api.post('/odf/units', {
        cabinet_id: nodeId.value, name: v.name, seq: units.value.length + 1,
        tray_count: Number(v.tray_count || 0), pos_x: maxX, pos_y: 60,
      })
      message.success('单元柜已创建'); dlg.value.show = false
      await loadOdf()
    } catch (e: any) { message.error(e.response?.data?.detail || '创建失败') }
  })
}

function renameUnit(unitId: number) {
  const u = units.value.find(x => x.id === unitId)
  if (!u) return
  openDlg('重命名单元柜', [
    { key: 'name', label: '单元柜标识', required: true },
  ], { name: u.name }, async (v) => {
    try {
      await api.put(`/odf/units/${unitId}`, { name: v.name })
      message.success('已重命名（孔位编址同步更新）'); dlg.value.show = false
      await loadOdf()
    } catch (e: any) { message.error(e.response?.data?.detail || '重命名失败') }
  })
}

function renameTray(trayId: number) {
  const t = trays.value.find(x => x.id === trayId)
  if (!t) return
  openDlg('重命名盘', [{ key: 'name', label: '盘号', required: true }], { name: t.name },
    async (v) => {
      try {
        await api.put(`/odf/trays/${trayId}`, { name: v.name })
        message.success('已重命名'); dlg.value.show = false
        await loadOdf()
      } catch (e: any) { message.error(e.response?.data?.detail || '重命名失败') }
    })
}

function groupTrays() {
  const ids = [...multiTrays.value]
  if (!ids.length) return message.warning('请先选择要组合的盘（Ctrl+鍗曞嚮澶氶€夛級')
  const sel = trays.value.filter(t => ids.includes(t.id))
  const minX = Math.min(...sel.map(t => t.pos_x))
  const minY = Math.min(...sel.map(t => t.pos_y))
  openDlg('组合为单元柜', [
    { key: 'name', label: '单元柜标识', required: true, placeholder: '如 A' },
  ], { name: String.fromCharCode(65 + units.value.length) }, async (v) => {
    try {
      await api.post('/odf/trays/group', {
        cabinet_id: nodeId.value, tray_ids: ids, name: v.name, pos_x: minX, pos_y: minY,
      })
      message.success(`已组合 ${ids.length} 个盘为单元柜 ${v.name}`)
      dlg.value.show = false
      multiTrays.value = new Set()
      await loadOdf()
    } catch (e: any) { message.error(e.response?.data?.detail || '组合失败') }
  })
}

function ungroupUnit(unitId: number) {
  const u = units.value.find(x => x.id === unitId)
  dialog.warning({
    title: '解散单元柜', content: `确认解散「${u?.name}」？内部盘将回到未分组并保留位置。`,
    positiveText: '解散', negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.post(`/odf/units/${unitId}/ungroup`)
        message.success('已解散'); await loadOdf()
      } catch (e: any) { message.error(e.response?.data?.detail || '解散失败') }
    },
  })
}

function deleteTray(trayId: number) {
  dialog.warning({
    title: '删除盘', content: '确认删除该盘及其全部孔位？孔位在用时会拒绝删除。',
    positiveText: '删除', negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.delete(`/odf/trays/${trayId}`)
        message.success('已删除'); await loadOdf()
      } catch (e: any) { message.error(e.response?.data?.detail || '删除失败') }
    },
  })
}

/* ============ 工具栏 ============ */
function fitAll() {
  if (mode.value === 'rack') {
    // 按设备实际分布取景：设备集中在顶部时放大该区域，而不是整柜留白
    const boxes = devBoxes.value
    if (boxes.length) {
      const minY = Math.min(...boxes.map(b => b.y)) - 24
      const maxY = Math.max(...boxes.map(b => b.y + b.height)) + 20
      cv.fit({ minX: -50, minY, maxX: RACK_W + 60, maxY }, 45)
    } else {
      cv.fit({ minX: -50, minY: -10, maxX: RACK_W + 60, maxY: rackH.value + 20 }, 45)
    }
    return
  }
  const all = trays.value
  if (!all.length) return
  cv.fit({
    minX: Math.min(...all.map(t => t.pos_x)) - 40,
    minY: Math.min(...all.map(t => t.pos_y)) - 50,
    maxX: Math.max(...all.map(t => t.pos_x + TRAY_W)) + 40,
    maxY: Math.max(...all.map(t => t.pos_y + TRAY_H)) + 40,
  }, 50)
}

function back() {
  let roomId = 1
  if (mode.value === 'rack') roomId = rack.value?.room_id ?? 1
  else roomId = store.cabinets.find(c => c.id === nodeId.value)?.room_id ?? 1
  router.push(`/topology/${roomId}`)
}

const crumb = computed(() => {
  if (mode.value === 'rack') return rack.value?.name || '机柜'
  return store.cabinets.find(c => c.id === nodeId.value)?.name || '配线柜'
})

/* ============ 生命周期 ============ */
async function reload() {
  await store.loadBase()
  // 模板与端口类型是设计器/新建表单的前提，必须一并加载（此前漏调导致模板下拉为空）
  await store.loadTemplates()
  await loadCords()
  store.resetOdf()
  if (mode.value === 'odf') await loadOdf()
  multiTrays.value = new Set()
  selected.value = null
}

watch(() => route.fullPath, reload)

onMounted(async () => {
  cv.svgEl.value = svgRef.value
  await reload()
  setTimeout(fitAll, 60)
  pollTimer = setInterval(silentRefresh, 30000)
})
onBeforeUnmount(() => {
  clearTimeout(saveTimer)
  clearInterval(pollTimer)
})
</script>

<template>
  <div class="l2">
    <div class="toolbar">
      <Breadcrumb :items="crumbs" />
      <span class="dim sep-dot">·</span>
      <span class="dim">{{ mode === 'rack' ? '设备按 U 位排列' : '盘自由拖拽组合' }}</span>
      <div class="grow"></div>
      <span v-if="mode === 'rack' && rackFaultCount" class="fault-badge">
        <Icon name="warn" :size="12" />{{ rackFaultCount }} 个故障端口
      </span>
      <button class="tb" :class="{ on: autoRefresh }" @click="autoRefresh = !autoRefresh"
              :title="autoRefresh ? '自动刷新已开启（30 秒）' : '自动刷新已关闭'">
        <Icon name="refresh" :size="14" />
      </button>
      <button class="tb" title="缩小" @click="cv.zoom(1 / 1.15)"><Icon name="zoomOut" :size="14" /></button>
      <span class="zoom-val">{{ Math.round(cv.scale.value * 100) }}%</span>
      <button class="tb" title="放大" @click="cv.zoom(1.15)"><Icon name="zoomIn" :size="14" /></button>
      <button class="tb" title="适应窗口" @click="fitAll"><Icon name="fit" :size="14" /></button>
      <n-button v-if="mode === 'rack'" size="small" quaternary @click="openDesigner">
        <template #icon><Icon name="edit" :size="12" /></template>绘制模板
      </n-button>
      <n-button size="small" type="primary" secondary :disabled="!canWrite"
                @click="mode === 'rack' ? newDevice() : newTray()">
        <template #icon><Icon name="plus" :size="12" /></template>
        {{ mode === 'rack' ? '新建设备' : '新建盘' }}
      </n-button>
      <span v-if="!canWrite" class="ro-tag">只读</span>
    </div>

    <svg ref="svgRef" class="canvas"
         @wheel.prevent="cv.onWheel"
         @pointerdown="onCanvasDown"
         @pointermove="onPointerMove" @pointerup="onPointerUp" @pointerleave="onPointerUp"
         @pointercancel="onPointerUp" @dblclick="onCanvasDblClick"
         @contextmenu.prevent="openCanvasMenu">
      <g :transform="`translate(${cv.pan.value.x} ${cv.pan.value.y}) scale(${cv.scale.value})`">
        <!-- ============ 网络机柜 ============ -->
        <template v-if="mode === 'rack'">
          <g>
            <rect :width="RACK_W" :height="rackH" rx="12" fill="var(--cv-node-2)" stroke="var(--cv-node-stroke)" />
            <rect :width="RACK_W" height="4" rx="2" fill="var(--accent)" opacity="0.85" />
            <text x="14" y="24" fill="var(--cv-text)" font-size="13" font-weight="600">{{ rack?.name }}</text>
            <text :x="RACK_W - 14" y="24" text-anchor="end" fill="var(--cv-dim)" font-size="10">
              {{ rack?.code }} · {{ uCount }}U
            </text>
          </g>

          <!-- U 位标尺：左右两侧，U1 在底部，每 5U 标注数字 -->
          <g class="u-ruler">
            <g v-for="u in uCount" :key="'u' + u">
              <line :x1="-16" :y1="18 + (uCount - u) * U_H + U_H / 2"
                    :x2="-4" :y2="18 + (uCount - u) * U_H + U_H / 2"
                    stroke="var(--cv-dim)" stroke-width="1" opacity="0.55" />
              <line :x1="RACK_W + 4" :y1="18 + (uCount - u) * U_H + U_H / 2"
                    :x2="RACK_W + 16" :y2="18 + (uCount - u) * U_H + U_H / 2"
                    stroke="var(--cv-dim)" stroke-width="1" opacity="0.55" />
              <template v-if="u === 1 || u % 5 === 0 || u === uCount">
                <text :x="-20" :y="18 + (uCount - u) * U_H + U_H / 2 + 3.5"
                      text-anchor="end" fill="var(--cv-dim)" font-size="9">{{ u }}U</text>
                <text :x="RACK_W + 20" :y="18 + (uCount - u) * U_H + U_H / 2 + 3.5"
                      text-anchor="start" fill="var(--cv-dim)" font-size="9">{{ u }}U</text>
              </template>
            </g>
          </g>

          <g v-for="d in devBoxes" :key="d.id"
             :transform="`translate(12 ${d.y})`"
             class="dev" :class="{ sel: selected?.kind === 'device' && selected?.id === d.id, fault: d.hasFault }"
             @pointerdown="startDeviceDrag($event, d)"
             @dblclick.stop="router.push(`/ports/device/${d.id}`)"
             @mouseenter="showTip($event, deviceTipPayload(d))"
             @mouseleave="hideTip"
             @contextmenu.prevent.stop="openDeviceMenu($event, d)">
            <rect :width="RACK_W - 24" :height="d.height" rx="4"
                  fill="var(--cv-node)" :stroke="d.hasFault ? 'var(--c-fault)' : 'var(--cv-slot-stroke)'"
                  :stroke-width="d.hasFault ? 1.4 : 1" />
            <rect x="4" :y="3" width="3" :height="d.height - 6" rx="1.5"
                  :fill="d.hasFault ? 'var(--c-fault)' : 'var(--c-used)'" />

            <!-- 文字区：固定在端口带上方，右侧信息右对齐，互不重叠 -->
            <text x="14" :y="d.textY" fill="var(--cv-text)" :font-size="d.nameFont">
              {{ d.displayName }}
            </text>
            <text :x="RACK_W - 12" :y="d.textY" text-anchor="end"
                  :fill="d.hasFault ? 'var(--c-fault)' : 'var(--cv-dim)'" :font-size="d.metaFont">
              {{ d.metaText }}
            </text>
            <!-- 多 U 设备：在空闲区显示 U 范围 -->
            <text v-if="d.uHeight > 1" x="14" :y="d.height - 12"
                  fill="var(--cv-dim)" font-size="8">
              U{{ d.u }}–U{{ d.uTop }}
            </text>

            <!-- 端口带（贴底，不与文字重叠） -->
            <g v-if="d.groups.length">
              <g v-for="(row, ri) in portRows(d)" :key="'row' + ri">
                <rect :x="row.barX" :y="row.y" width="2" :height="row.h"
                      :fill="row.typeColor" rx="0.8" />
                <g v-for="(seg, si) in row.segs" :key="'s' + si"
                   :transform="`translate(${seg.x} ${row.y})`">
                  <PortShape v-if="row.h >= 5" :shape="seg.shape" :w="seg.w" :h="row.h"
                             :fill="`var(--c-${seg.status})`" stroke="rgba(0,0,0,.35)" />
                  <rect v-else :width="seg.w" :height="row.h" rx="0.6"
                        :fill="`var(--c-${seg.status})`" opacity="0.95" />
                </g>
              </g>
            </g>
          </g>

          <text v-if="!devBoxes.length" x="24" y="90" fill="var(--cv-dim)" font-size="12">
            空机柜 · 右键空白处或点击「新建设备」
          </text>
        </template>

        <!-- ============ ODF 配线柜 ============ -->
        <template v-else>
          <!-- 单元柜容器 -->
          <g v-for="u in units" :key="u.id">
            <g v-for="b in [unitBox(u)]" :key="b.x">
              <rect :x="b.x" :y="b.y" :width="b.w" :height="b.h" rx="10"
                    fill="var(--cv-odf)" stroke="var(--cv-odf-stroke)" stroke-width="2"
                    class="unit-bg" :class="{ sel: selected?.kind === 'unit' && selected?.id === u.id }"
                    @pointerdown="startUnitDrag($event, u)"
                    @dblclick.stop="router.push(`/ports/unit/${u.id}`)"
                    @contextmenu.prevent.stop="openUnitMenu($event, u)" />
              <!-- 单元柜标题条，强化边界 -->
              <rect :x="b.x" :y="b.y" :width="b.w" height="21" rx="10"
                    fill="var(--cv-odf-stroke)" opacity="0.28" pointer-events="none" />
              <text :x="b.x + 10" :y="b.y + 15" fill="var(--c-inter)" font-size="11" font-weight="700"
                    pointer-events="none">
                单元柜 {{ u.name }}
              </text>
              <text :x="b.x + b.w - 10" :y="b.y + 15" text-anchor="end" fill="var(--cv-dim)"
                    font-size="9.5" pointer-events="none">
                {{ trays.filter(t => t.unit_id === u.id).length }} 盘
              </text>
            </g>
          </g>

          <!-- 盘 -->
          <g v-for="t in trays" :key="t.id" :transform="`translate(${t.pos_x} ${t.pos_y})`"
             class="tray"
             :class="{
               sel: selected?.kind === 'tray' && selected?.id === t.id,
               multi: multiTrays.has(t.id),
             }"
             @pointerdown="startTrayDrag($event, t)"
             @dblclick.stop="router.push(`/ports/tray/${t.id}`)"
             @mouseenter="showTip($event, trayTipPayload(t))"
             @mouseleave="hideTip"
             @contextmenu.prevent.stop="openTrayMenu($event, t)">
            <rect :width="TRAY_W" :height="TRAY_H" rx="6" fill="var(--cv-node)" stroke="var(--cv-slot-stroke)" />
            <text x="10" y="16" fill="var(--cv-text)" font-size="10.5" font-weight="600">{{ t.name }} 盘</text>
            <text :x="TRAY_W - 10" y="16" text-anchor="end" fill="var(--cv-dim)" font-size="9">
              {{ t.rows }}×{{ t.perRow }} · {{ t.used }}/{{ t.slots }} 在用
            </text>
            <!-- 逐孔位状态色块（每格可独立悬停） -->
            <g>
              <rect v-for="(st, si) in t.portStatus" :key="'s' + si"
                    :x="10 + si * ((TRAY_W - 24) / Math.max(t.portStatus.length, 1))" y="23"
                    :width="Math.max((TRAY_W - 24) / Math.max(t.portStatus.length, 1) - 1.6, 2)"
                    height="10" rx="1.6" :fill="`var(--c-${st})`" opacity="0.9"
                    @mouseenter.stop="showTip($event, slotTipPayload(t, si))"
                    @mouseleave="hideTip" />
            </g>
          </g>

          <text v-if="!trays.length" x="60" y="120" fill="var(--cv-dim)" font-size="12">
            暂无盘 · 右键空白处新建盘或单元柜
          </text>
        </template>
      </g>
    </svg>

    <ContextMenu v-model:show="menu.show" :x="menu.x" :y="menu.y" :title="menu.title"
                 :items="menu.items" @select="onMenuSelect" />
    <DialogForm v-model:show="dlg.show" :title="dlg.title" :fields="dlg.fields"
                :initial="dlg.initial" @submit="dlg.submit" />

    <DeviceDesigner ref="designerRef" v-model:show="designerShow" @saved="onDesignerSaved" />

    <!-- 悬停详情浮层 -->
    <Teleport to="body">
      <div v-if="tip.show" class="obj-tip" :style="tipStyle">
        <div class="tip-head">
          <span class="tip-title">{{ tip.title }}</span>
          <span v-if="tip.hasFault" class="tip-fault">故障</span>
        </div>
        <div class="tip-sub">{{ tip.sub }}</div>

        <div v-if="(tip as any).single" class="tip-single">
          <span class="st-pill" :style="{
            color: `var(--c-${(tip as any).singleStatus})`,
            background: `color-mix(in srgb, var(--c-${(tip as any).singleStatus}) 16%, transparent)`,
            borderColor: `color-mix(in srgb, var(--c-${(tip as any).singleStatus}) 40%, transparent)`,
          }">{{ statusLabel((tip as any).singleStatus) }}</span>
          <span v-if="tip.rows.length" class="tip-remark">{{ tip.rows[0].remark }}</span>
        </div>

        <div v-if="tip.stats" class="tip-stats">
          <span class="ts"><i style="background: var(--c-used)"></i>在用 {{ tip.stats.used }}</span>
          <span class="ts"><i style="background: var(--c-free)"></i>空闲 {{ tip.stats.free }}</span>
          <span class="ts"><i style="background: var(--c-reserved)"></i>预留 {{ tip.stats.reserved }}</span>
          <span class="ts"><i style="background: var(--c-fault)"></i>故障 {{ tip.stats.fault }}</span>
        </div>

        <div v-if="tip.rows.length" class="tip-rows">
          <div class="tr-head">异常端口</div>
          <div v-for="(r, i) in tip.rows" :key="i" class="tr-row">
            <span class="tr-name">{{ r.name }}</span>
            <span class="tr-st" :style="{ color: `var(--c-${r.status})` }">
              {{ r.status === 'fault' ? '故障' : r.status === 'reserved' ? '预留' : r.status }}
            </span>
            <span v-if="r.remark" class="tr-remark" :title="r.remark">{{ r.remark }}</span>
          </div>
        </div>
        <div v-else-if="tip.stats" class="tip-ok">无异常端口</div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.l2 { display: flex; flex-direction: column; height: 100%; gap: 10px; }
.toolbar {
  display: flex; align-items: center; gap: 10px; padding: 8px 12px;
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius);
}
.tb {
  height: 28px; display: inline-flex; align-items: center; gap: 5px; padding: 0 9px;
  background: transparent; border: 1px solid var(--border); border-radius: 7px;
  color: var(--text-2); cursor: pointer; font-size: 12px; transition: .12s;
}
.tb:hover { background: var(--bg-hover); color: var(--accent); }
.crumb { font-size: 13px; font-weight: 600; }
.sep-dot { padding: 0 2px; }
.fault-badge {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11.5px; color: var(--c-fault);
  background: rgba(239,68,68,.12); border: 1px solid rgba(239,68,68,.32);
  border-radius: 999px; padding: 1px 10px; font-weight: 500;
}
.ro-tag {
  font-size: 11px; color: var(--warn); background: var(--warn-soft);
  border: 1px solid var(--warn-border); border-radius: 999px; padding: 1px 9px;
}
.zoom-val { font-size: 11.5px; color: var(--text-3); width: 42px; text-align: center; }

.canvas {
  flex: 1; background: var(--cv-bg); border: 1px solid var(--border);
  border-radius: var(--radius); display: block; cursor: grab; min-height: 0;
}
.canvas:active { cursor: grabbing; }

.dev { cursor: pointer; }
.dev.sel > rect:first-child { stroke: var(--accent); stroke-width: 1.5; }
.dev.fault > rect:first-child { filter: drop-shadow(0 0 5px rgba(239,68,68,.45)); }

.unit-bg { cursor: move; }
.unit-bg.sel { stroke: var(--c-inter); stroke-width: 1.6; }

.tray { cursor: pointer; }
.tray.sel > rect:first-child { stroke: var(--accent); stroke-width: 1.5; }
.tray.multi > rect:first-child { stroke: var(--c-inter); stroke-width: 1.5; stroke-dasharray: 5 3; }

/* 悬停详情浮层 */
.obj-tip {
  position: fixed; z-index: 4000; pointer-events: none;
  background: var(--bg-panel); border: 1px solid var(--border-strong);
  border-radius: 9px; box-shadow: var(--shadow-2); padding: 10px 12px;
  font-size: 12px; color: var(--text-1);
}
.tip-head { display: flex; align-items: center; gap: 8px; }
.tip-title { font-weight: 600; font-size: 12.5px; flex: 1;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tip-fault {
  font-size: 10px; color: #fff; background: var(--c-fault);
  border-radius: 999px; padding: 0 7px; line-height: 15px; flex: none;
}
.tip-sub { font-size: 11px; color: var(--text-3); margin-top: 2px; }
.tip-single { display: flex; align-items: center; gap: 8px; margin-top: 8px;
  padding-top: 8px; border-top: 1px solid var(--border); }
.st-pill { font-size: 11px; padding: 1px 9px; border-radius: 999px; border: 1px solid; }
.tip-remark { font-size: 11px; color: var(--text-2); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.tip-stats {
  display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 8px;
  padding-top: 8px; border-top: 1px solid var(--border);
}
.ts { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--text-2); }
.ts i { width: 7px; height: 7px; border-radius: 2px; display: inline-block; }
.tip-rows { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
.tr-head { font-size: 10.5px; color: var(--text-3); margin-bottom: 4px; }
.tr-row { display: flex; align-items: baseline; gap: 8px; line-height: 1.7; font-size: 11px; }
.tr-name { font-family: monospace; color: var(--text-1); flex: none; }
.tr-st { flex: none; font-size: 10.5px; }
.tr-remark { color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tip-ok { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border);
  font-size: 11px; color: var(--c-used); }

/* ============ 响应式 ============ */
@media (max-width: 767px) {
  .toolbar { flex-wrap: wrap; height: auto; padding: 8px 10px; gap: 6px; }
  .sep-dot { display: none; }
  .zoom-val { width: 36px; }
  .obj-tip { max-width: 76vw; }
}
</style>
