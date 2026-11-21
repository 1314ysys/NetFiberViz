<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NSelect, NButton, NDropdown, useMessage, useDialog } from 'naive-ui'
import { api } from '../api/client'
import { useResourceStore } from '../stores/resource'
import { useSessionStore } from '../stores/session'
import { roomSelectOptions } from '../utils/rooms'
import { useCanvas } from '../composables/useCanvas'
import Icon from '../components/ui/Icon.vue'
import ContextMenu from '../components/ui/ContextMenu.vue'
import type { MenuItem } from '../components/ui/ContextMenu.vue'
import DialogForm from '../components/ui/DialogForm.vue'
import type { FormField } from '../components/ui/DialogForm.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const store = useResourceStore()
const session = useSessionStore()
const cv = useCanvas()

const roomId = ref(Number(route.params.roomId) || 1)
const showGrid = ref(true)
const svgRef = ref<SVGSVGElement>()
const selected = ref<{ kind: 'rack' | 'cab'; id: number } | null>(null)
const pos = ref<Record<string, { x: number; y: number }>>({})
const dirty = ref(false)
let saveTimer: any = null

const NODE_W = 220
const NODE_H = 96

/* ---------------- 数据 ---------------- */
const racks = computed(() => store.racksOfRoom(roomId.value))
const cabinets = computed(() => store.cabinets.filter(c => c.room_id === roomId.value))

const rackStats = computed(() => {
  const m: Record<number, { devices: number; used: number; total: number; fault: number }> = {}
  for (const rk of racks.value) m[rk.id] = { devices: 0, used: 0, total: 0, fault: 0 }
  for (const d of store.devices) {
    const s = m[d.rack_id]
    if (!s) continue
    s.devices++
    for (const p of store.portsOfDevice(d.id)) {
      s.total++
      if (p.status === 'used') s.used++
      if (p.status === 'fault') s.fault++
    }
  }
  return m
})

interface NodeBox {
  key: string; kind: 'rack' | 'cab'; id: number; name: string; code: string
  x: number; y: number; w: number; h: number
  sub: string; ratio: number; fault: number
}

const nodes = computed<NodeBox[]>(() => {
  const out: NodeBox[] = []
  racks.value.forEach((rk, i) => {
    const st = rackStats.value[rk.id]
    const saved = pos.value[`rack-${rk.id}`]
    out.push({
      key: `rack-${rk.id}`, kind: 'rack', id: rk.id, name: rk.name, code: rk.code,
      x: saved?.x ?? 48 + i * (NODE_W + 56), y: saved?.y ?? 72, w: NODE_W, h: NODE_H,
      sub: `${st.devices} 台设备 · ${rk.u_count}U`,
      ratio: st.total ? st.used / st.total : 0,
      fault: st.fault,
    })
  })
  cabinets.value.forEach((c, i) => {
    const saved = pos.value[`cab-${c.id}`]
    const unitCount = store.units.filter(u => u.cabinet_id === c.id).length
    out.push({
      key: `cab-${c.id}`, kind: 'cab', id: c.id, name: c.name, code: c.code,
      x: saved?.x ?? 48 + (racks.value.length + i) * (NODE_W + 56), y: saved?.y ?? 72,
      w: NODE_W, h: NODE_H,
      sub: `ODF 配线柜 · ${unitCount} 个单元柜`,
      ratio: 0,
      fault: 0,
    })
  })
  return out
})

const nodeByKey = computed(() => Object.fromEntries(nodes.value.map(n => [n.key, n])))

/* ---------------- 机柜间连线（跳纤聚合，密度渲染，只读） ---------------- */
const edgePairs = ref<{ a: string; b: string; n: number }[]>([])

/**
 * 密度规则（与用户确认）：
 *   线数 = round(条数 / 10)，最少 1 条、封顶 50 条
 *   线宽随线数递减：1 条 2.4px → 50 条 0.3px
 *   多条线沿垂直方向等间距平行分布，形成"束"的观感 */
const edges = computed(() => {
  const out: { d: string; w: number; count: number; key: string }[] = []
  for (const { a, b, n } of edgePairs.value) {
    const na = nodeByKey.value[a]
    const nb = nodeByKey.value[b]
    if (!na || !nb) continue
    const lines = Math.min(50, Math.max(1, Math.round(n / 10)))
    const w = lines === 1 ? 2.4 : Math.max(0.3, 2.4 - (lines - 1) * (2.1 / 49))
    const spacing = lines > 1 ? Math.min(1.4, 30 / (lines - 1)) : 0
    const ax = na.x + na.w / 2, ay = na.y + na.h / 2
    const bx = nb.x + nb.w / 2, by = nb.y + nb.h / 2
    const mx = (ax + bx) / 2
    for (let i = 0; i < lines; i++) {
      const off = (i - (lines - 1) / 2) * spacing
      out.push({
        d: `M ${ax} ${ay + off} C ${mx} ${ay + off}, ${mx} ${by + off}, ${bx} ${by + off}`,
        w, count: n, key: `${a}|${b}|${i}`,
      })
    }
  }
  return out
})

async function buildEdges() {
  const [cords, portMap] = await Promise.all([
    api.get('/patch-cords'),
    api.get('/odf/port-map', { params: { room_id: roomId.value } }).catch(() => ({ data: [] })),
  ])
  const devRack: Record<number, number> = {}
  for (const d of store.devices) devRack[d.id] = d.rack_id
  const portOwner: Record<number, { type: 'rack' | 'cab'; id: number }> = {}
  for (const p of store.ports) {
    if (p.owner_type === 'device' && devRack[p.owner_id]) {
      portOwner[p.id] = { type: 'rack', id: devRack[p.owner_id] }
    }
  }
  for (const m of portMap.data as any[]) {
    portOwner[m.port_id] = { type: 'cab', id: m.cabinet_id }
  }

  const counts = new Map<string, { a: string; b: string; n: number }>()
  for (const c of cords.data as any[]) {
    const pa = portOwner[c.port_a_id]
    const pb = portOwner[c.port_b_id]
    if (!pa || !pb) continue
    const ka = `${pa.type}-${pa.id}`
    const kb = `${pb.type}-${pb.id}`
    if (ka === kb) continue
    const [k1, k2] = ka < kb ? [ka, kb] : [kb, ka]
    const key = `${k1}|${k2}`
    if (!counts.has(key)) counts.set(key, { a: k1, b: k2, n: 0 })
    counts.get(key)!.n++
  }
  edgePairs.value = [...counts.values()]
}

/* ---------------- 布局持久化 ---------------- */
async function loadLayout() {
  try {
    const r = await api.get(`/canvas/${roomId.value}`)
    const d = r.data?.data_json
    if (d?.nodes) {
      const m: Record<string, { x: number; y: number }> = {}
      for (const n of d.nodes) m[n.key] = { x: n.x, y: n.y }
      pos.value = m
    } else pos.value = {}
  } catch { pos.value = {} }
}

function scheduleSave() {
  dirty.value = true
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => saveLayout(true), 800)
}

async function saveLayout(silent = false) {
  const list = nodes.value.map(n => ({ key: n.key, x: n.x, y: n.y }))
  await api.put(`/canvas/${roomId.value}`, { data_json: { nodes: list } })
  dirty.value = false
  if (!silent) message.success('布局已保存')
}

/* ---------------- 交互 ---------------- */
function onCanvasDown(evt: PointerEvent) {
  selected.value = null
  cv.startPan(evt)
}

function onNodeDown(evt: PointerEvent, n: NodeBox) {
  evt.stopPropagation()
  selected.value = { kind: n.kind, id: n.id }
  // 传入节点当前真实坐标，避免首次拖拽瞬移
  cv.startDrag(evt, n.key, n.x, n.y)
}

function onPointerMove(evt: PointerEvent) {
  cv.onMove(evt, (key, x, y) => {
    pos.value = {
      ...pos.value,
      [key]: { x: Math.round(x / 10) * 10, y: Math.round(y / 10) * 10 },
    }
  })
}

function onPointerUp() {
  const moved = cv.endDrag()
  if (moved) scheduleSave()
}

function enterNode(n: NodeBox) {
  router.push(n.kind === 'rack' ? `/interior/rack/${n.id}` : `/interior/odf/${n.id}`)
}

/* ---------------- 右键菜单 ---------------- */
const menu = ref<{ show: boolean; x: number; y: number; title: string; items: MenuItem[]; target: NodeBox | null }>(
  { show: false, x: 0, y: 0, title: '', items: [], target: null })

function openNodeMenu(evt: MouseEvent, n: NodeBox) {
  evt.preventDefault()
  evt.stopPropagation()
  selected.value = { kind: n.kind, id: n.id }
  const items: MenuItem[] = n.kind === 'rack'
    ? [
      { key: 'enter', label: '进入机柜视图', hint: '双击' },
      { key: 'edit', label: '修改机柜…', disabled: !canWrite.value },
      { key: 'div1', label: '', divider: true },
      { key: 'delete', label: '删除机柜', danger: true, disabled: !canWrite.value },
    ]
    : [
      { key: 'enter', label: '进入配线柜视图', hint: '双击' },
      { key: 'edit', label: '修改配线柜…', disabled: !canWrite.value },
      { key: 'div1', label: '', divider: true },
      { key: 'delete', label: '删除配线柜', danger: true, disabled: !canWrite.value },
    ]
  menu.value = { show: true, x: evt.clientX, y: evt.clientY, title: `${n.name} (${n.code})`, items, target: n }
}

function openCanvasMenu(evt: MouseEvent) {
  evt.preventDefault()
  menu.value = {
    show: true, x: evt.clientX, y: evt.clientY, title: '新建', target: null,
    items: [
      { key: 'new-rack', label: '新建机柜', disabled: !canWrite.value },
      { key: 'new-cab', label: '新建 ODF 配线柜', disabled: !canWrite.value },
      { key: 'div1', label: '', divider: true },
      { key: 'fit', label: '适应窗口' },
    ],
  }
}

function onMenuSelect(key: string) {
  const t = menu.value.target
  if (key === 'fit') return fitAll()
  if (key === 'new-rack') return newRack()
  if (key === 'new-cab') return newCabinet()
  if (!t) return
  if (key === 'enter') return enterNode(t)
  if (key === 'edit') return t.kind === 'rack' ? editRack(t.id) : editCabinet(t.id)
  if (key === 'delete') return t.kind === 'rack' ? deleteRack(t.id, t.name) : deleteCabinet(t.id, t.name)
}

/* ---------------- 弹窗 ---------------- */
const dlg = ref<{ show: boolean; title: string; fields: FormField[]; initial: any; submit: (v: any) => Promise<void> }>(
  { show: false, title: '', fields: [], initial: {}, submit: async () => {} })

function openDlg(title: string, fields: FormField[], initial: any, submit: (v: any) => Promise<void>) {
  dlg.value = { show: true, title, fields, initial, submit }
}

async function afterChange(msg: string) {
  message.success(msg)
  dlg.value.show = false
  await store.loadBase()
  await buildEdges()
}

function newRack() {
  openDlg('新建机柜', [
    { key: 'name', label: '机柜名称', required: true, placeholder: '如 01架' },
    { key: 'code', label: '机柜编码', required: true, placeholder: '如 R01' },
    { key: 'u_count', label: 'U 数', type: 'number', default: 42, min: 1 },
  ], {}, async (v) => {
    await api.post('/racks', { ...v, room_id: roomId.value })
    await afterChange('机柜已创建')
  })
}

function editRack(id: number) {
  const rk = racks.value.find(r => r.id === id)
  if (!rk) return
  openDlg('修改机柜', [
    { key: 'name', label: '机柜名称', required: true },
    { key: 'code', label: '机柜编码', required: true },
    { key: 'u_count', label: 'U 数', type: 'number', default: 42, min: 1 },
  ], { name: rk.name, code: rk.code, u_count: rk.u_count }, async (v) => {
    await api.put(`/racks/${id}`, { ...v, room_id: roomId.value })
    await afterChange('机柜已更新')
  })
}

function deleteRack(id: number, name: string) {
  dialog.warning({
    title: '删除机柜', content: `确认删除「${name}」？机柜内若有设备将拒绝删除。`,
    positiveText: '删除', negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.delete(`/racks/${id}`)
        message.success('机柜已删除')
        pos.value = Object.fromEntries(Object.entries(pos.value).filter(([k]) => k !== `rack-${id}`))
        await store.loadBase(); await buildEdges()
      } catch (e: any) { message.error(e.response?.data?.detail || '删除失败') }
    },
  })
}

function newCabinet() {
  openDlg('新建 ODF 配线柜', [
    { key: 'name', label: '配线柜名称', required: true, placeholder: '如 ODF-1' },
    { key: 'code', label: '编码', required: true, placeholder: '如 ODF01' },
    { key: 'unit_count', label: '单元柜数量', type: 'number', default: 3, min: 0,
      hint: '自动生成 A/B/C… 单元柜，稍后可在配线柜视图内调整' },
  ], {}, async (v) => {
    const cab = (await api.post('/odf/cabinets', {
      name: v.name, code: v.code, room_id: roomId.value,
    })).data
    for (let i = 0; i < Number(v.unit_count || 0); i++) {
      await api.post('/odf/units', {
        cabinet_id: cab.id, name: String.fromCharCode(65 + i), seq: i + 1,
        pos_x: 40 + i * 240, pos_y: 60,
      })
    }
    await afterChange('配线柜已创建')
  })
}

function editCabinet(id: number) {
  const c = cabinets.value.find(x => x.id === id)
  if (!c) return
  openDlg('修改配线柜', [
    { key: 'name', label: '配线柜名称', required: true },
    { key: 'code', label: '编码', required: true },
  ], { name: c.name, code: c.code }, async (v) => {
    await api.put(`/odf/cabinets/${id}`, v)
    await afterChange('配线柜已更新')
  })
}

function deleteCabinet(id: number, name: string) {
  dialog.warning({
    title: '删除配线柜', content: `确认删除「${name}」及其全部单元柜与盘？孔位在用时会拒绝删除。`,
    positiveText: '删除', negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.delete(`/odf/cabinets/${id}`)
        message.success('配线柜已删除')
        await store.loadBase(); await buildEdges()
      } catch (e: any) { message.error(e.response?.data?.detail || '删除失败') }
    },
  })
}

/* ---------------- 工具栏 ---------------- */
const roomOptions = computed(() => roomSelectOptions(store.rooms as any))
const canWrite = computed(() => session.canWriteRoom(roomId.value))
const createOptions = [
  { label: '新建机柜', key: 'new-rack' },
  { label: '新建 ODF 配线柜', key: 'new-cab' },
]

function fitAll() {
  if (!nodes.value.length) return
  cv.fit({
    minX: Math.min(...nodes.value.map(n => n.x)),
    minY: Math.min(...nodes.value.map(n => n.y)),
    maxX: Math.max(...nodes.value.map(n => n.x + n.w)),
    maxY: Math.max(...nodes.value.map(n => n.y + n.h)),
  })
}

/* ---------------- 生命周期 ---------------- */
async function reload() {
  await store.loadBase()
  store.resetOdf()
  for (const c of store.cabinets.filter(x => x.room_id === roomId.value)) {
    const units = await store.loadUnits(c.id)
    for (const u of units) await store.loadTrays(u.id)
  }
  await loadLayout()
  await buildEdges()
}

watch(roomId, reload)
watch(() => nodes.value.length, () => { if (nodes.value.length) buildEdges() })

onMounted(async () => {
  cv.svgEl.value = svgRef.value
  await reload()
  if (nodes.value.length) fitAll()
})
onBeforeUnmount(() => clearTimeout(saveTimer))
</script>

<template>
  <div class="l1">
    <div class="toolbar">
      <n-select v-model:value="roomId" :options="roomOptions" size="small" style="width: 150px" />
      <div class="sep"></div>
      <button class="tb" title="缩小" @click="cv.zoom(1 / 1.15)"><Icon name="zoomOut" :size="14" /></button>
      <span class="zoom-val">{{ Math.round(cv.scale.value * 100) }}%</span>
      <button class="tb" title="放大" @click="cv.zoom(1.15)"><Icon name="zoomIn" :size="14" /></button>
      <button class="tb" title="适应窗口" @click="fitAll"><Icon name="fit" :size="14" /></button>
      <button class="tb" :class="{ on: showGrid }" title="网格" @click="showGrid = !showGrid">
        <Icon name="grid" :size="14" />
      </button>
      <div class="sep"></div>
      <n-dropdown trigger="click" :options="createOptions" :disabled="!canWrite" @select="onMenuSelect">
        <n-button size="small" type="primary" secondary :disabled="!canWrite">
          <template #icon><Icon name="plus" :size="12" /></template>新建
        </n-button>
      </n-dropdown>
      <div class="grow"></div>
      <span v-if="!canWrite" class="ro-tag">只读 · 无该机房写权限</span>
      <span class="hint">单击选中 · 双击进入 · 右键菜单</span>
      <span v-if="dirty" class="dirty">保存中…</span>
      <n-button size="small" quaternary @click="saveLayout()">
        <template #icon><Icon name="save" :size="12" /></template>保存
      </n-button>
    </div>

    <svg ref="svgRef" class="canvas"
         @wheel.prevent="cv.onWheel" @pointerdown="onCanvasDown" @pointermove="onPointerMove"
         @pointerup="onPointerUp" @pointerleave="onPointerUp" @contextmenu.prevent="openCanvasMenu">
      <defs>
        <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="var(--cv-grid)" stroke-width="1" />
        </pattern>
        <linearGradient id="rackG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="var(--cv-node)" /><stop offset="1" stop-color="var(--cv-node-2)" />
        </linearGradient>
        <linearGradient id="cabG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="var(--cv-odf)" /><stop offset="1" stop-color="var(--cv-node-2)" />
        </linearGradient>
      </defs>

      <g :transform="`translate(${cv.pan.value.x} ${cv.pan.value.y}) scale(${cv.scale.value})`">
        <rect v-if="showGrid" x="-3000" y="-3000" width="9000" height="6000" fill="url(#grid)" />

        <!-- 机柜间连线（跳纤聚合，密度渲染，只读） -->
        <g class="edges">
          <path v-for="e in edges" :key="e.key" :d="e.d" fill="none" stroke="var(--c-cord)"
                :stroke-width="e.w" opacity="0.45">
            <title>{{ e.count }} 条跳纤</title>
          </path>
        </g>

        <!-- 节点 -->
        <g v-for="n in nodes" :key="n.key" :transform="`translate(${n.x} ${n.y})`"
           class="node" :class="{ sel: selected?.kind === n.kind && selected?.id === n.id }"
           @pointerdown="onNodeDown($event, n)"
           @dblclick.stop="enterNode(n)"
           @contextmenu.prevent.stop="openNodeMenu($event, n)">
          <rect :width="n.w" :height="n.h" rx="11"
                :fill="n.kind === 'rack' ? 'url(#rackG)' : 'url(#cabG)'"
                :stroke="n.fault > 0 ? 'var(--c-fault)' : (n.kind === 'rack' ? 'var(--cv-node-stroke)' : 'var(--cv-odf-stroke)')"
                :stroke-width="n.fault > 0 ? 2 : 1" />
          <rect :width="n.w" height="4" rx="2"
                :fill="n.fault > 0 ? 'var(--c-fault)' : (n.kind === 'rack' ? 'var(--accent)' : 'var(--c-inter)')"
                opacity="0.9" />
          <text x="14" y="30" fill="var(--cv-text)" font-size="13" font-weight="600">{{ n.name }}</text>
          <text :x="n.w - 14" y="30" text-anchor="end" fill="var(--cv-dim)" font-size="10">{{ n.code }}</text>
          <text x="14" y="50" fill="var(--cv-sub)" font-size="10.5">{{ n.sub }}</text>

          <!-- 故障强提示徽标 -->
          <g v-if="n.fault > 0" :transform="`translate(${n.w - 14 - 54} 8)`">
            <rect width="54" height="15" rx="7.5" fill="var(--c-fault)" opacity="0.92" />
            <text x="27" y="10.8" text-anchor="middle" fill="#fff" font-size="9.5" font-weight="600">
              ⚠ {{ n.fault }} 故障
            </text>
          </g>

          <!-- 端口占用条 -->
          <template v-if="n.kind === 'rack'">
            <rect x="14" y="62" :width="n.w - 28" height="6" rx="3" fill="var(--cv-slot-bg)" />
            <rect x="14" y="62" :width="(n.w - 28) * n.ratio" height="6" rx="3" fill="var(--c-used)" opacity="0.85" />
            <text x="14" y="84" fill="var(--cv-dim)" font-size="9.5">
              端口占用 {{ Math.round(n.ratio * 100) }}%
            </text>
          </template>
          <template v-else>
            <g>
              <rect x="14" y="62" width="26" height="16" rx="4" fill="var(--cv-slot-bg)" stroke="var(--cv-slot-stroke)" />
              <text x="27" y="74" text-anchor="middle" fill="var(--c-inter)" font-size="9">A</text>
              <rect x="44" y="62" width="26" height="16" rx="4" fill="var(--cv-slot-bg)" stroke="var(--cv-slot-stroke)" />
              <text x="57" y="74" text-anchor="middle" fill="var(--c-inter)" font-size="9">B</text>
              <text x="78" y="74" fill="var(--cv-dim)" font-size="9.5">…</text>
            </g>
          </template>

          <text :x="n.w - 14" y="84" text-anchor="end" fill="var(--cv-dim)" font-size="9.5">双击进入 ›</text>
        </g>

        <text v-if="!nodes.length" x="60" y="140" fill="var(--cv-dim)" font-size="13">
          暂无资源 · 右键空白处或点击「新建」创建机柜 / ODF 配线柜
        </text>
      </g>
    </svg>

    <ContextMenu v-model:show="menu.show" :x="menu.x" :y="menu.y" :title="menu.title"
                 :items="menu.items" @select="onMenuSelect" />
    <DialogForm v-model:show="dlg.show" :title="dlg.title" :fields="dlg.fields"
                :initial="dlg.initial" @submit="dlg.submit" />
  </div>
</template>

<style scoped>
.l1 { display: flex; flex-direction: column; height: 100%; gap: 10px; }
.toolbar {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius);
}
.sep { width: 1px; height: 18px; background: var(--border); }
.tb {
  width: 28px; height: 28px; display: grid; place-items: center;
  background: transparent; border: 1px solid var(--border); border-radius: 7px;
  color: var(--text-2); cursor: pointer; transition: .12s;
}
.tb:hover { background: var(--bg-hover); color: var(--accent); }
.tb.on { background: var(--accent-soft); color: var(--accent); border-color: color-mix(in srgb, var(--accent) 40%, transparent); }
.zoom-val { font-size: 11.5px; color: var(--text-3); width: 42px; text-align: center; }
.hint { font-size: 11.5px; color: var(--text-3); }
.ro-tag {
  font-size: 11.5px; color: var(--warn); background: var(--warn-soft);
  border: 1px solid var(--warn-border); border-radius: 999px; padding: 1px 10px;
}
.dirty { font-size: 11.5px; color: var(--warn); }

.canvas {
  flex: 1; background: var(--cv-bg); border: 1px solid var(--border);
  border-radius: var(--radius); display: block; cursor: grab; min-height: 0;
}
.canvas:active { cursor: grabbing; }
.node { cursor: pointer; }
.node.sel > rect:first-child { stroke: var(--accent); stroke-width: 1.6; filter: drop-shadow(0 0 10px var(--accent-soft)); }</style>
