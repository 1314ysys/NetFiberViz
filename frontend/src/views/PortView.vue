<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NDataTable, useMessage, useDialog } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { api } from '../api/client'
import { useResourceStore, DEVICE_TYPE_LABEL } from '../stores/resource'
import type { Port } from '../stores/resource'
import { useSessionStore } from '../stores/session'
import { useWiringStore } from '../stores/wiring'
import { shapeOf, familyColorOf } from '../utils/portTypes'
import Icon from '../components/ui/Icon.vue'
import StatusTag from '../components/ui/StatusTag.vue'
import PortShape from '../components/canvas/PortShape.vue'
import ContextMenu from '../components/ui/ContextMenu.vue'
import type { MenuItem } from '../components/ui/ContextMenu.vue'
import Breadcrumb from '../components/ui/Breadcrumb.vue'
import type { Crumb } from '../components/ui/Breadcrumb.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const store = useResourceStore()
const session = useSessionStore()
const wiring = useWiringStore()

const kind = computed(() => String(route.params.kind || 'device') as 'device' | 'unit' | 'tray')
const targetId = computed(() => Number(route.params.id))

/* ---------------- 数据 ---------------- */
const device = computed(() => (kind.value === 'device'
  ? store.devices.find(d => d.id === targetId.value) : null))
const unitInfo = ref<any>(null)
const trayName = ref('')
const trayCabinetId = ref<number | null>(null)

const groups = computed(() => {
  if (kind.value !== 'device') return []
  return store.groupPorts(store.portsOfDevice(targetId.value))
})

interface TrayBlock { id: number; name: string; rows: { rowLabel: string; slots: any[] }[] }
const trayBlocks = ref<TrayBlock[]>([])

const cords = ref<any[]>([])
const cordByPort = computed(() => {
  const m: Record<number, any> = {}
  for (const c of cords.value) {
    m[c.port_a_id] = c
    m[c.port_b_id] = c
  }
  return m
})

const scopePortIds = computed<Set<number>>(() => {
  const s = new Set<number>()
  if (kind.value === 'device') {
    for (const p of store.portsOfDevice(targetId.value)) s.add(p.id)
  } else {
    for (const b of trayBlocks.value)
      for (const r of b.rows)
        for (const sl of r.slots) if (sl.port) s.add(sl.port.id)
  }
  return s
})

const scopeCords = computed(() =>
  cords.value.filter(c => scopePortIds.value.has(c.port_a_id) || scopePortIds.value.has(c.port_b_id)))

/* ---------------- 权限 ---------------- */
const currentRoomId = computed<number | null>(() => {
  if (kind.value === 'device') {
    const d = device.value
    if (!d) return null
    return store.racks.find(r => r.id === d.rack_id)?.room_id ?? null
  }
  const cabId = kind.value === 'unit' ? unitInfo.value?.cabinet_id : trayCabinetId.value
  if (!cabId) return null
  return store.cabinets.find(c => c.id === cabId)?.room_id ?? null
})
const canWrite = computed(() => session.canWriteRoom(currentRoomId.value))

/* ---------------- 加载 ---------------- */
async function loadSlotsForTrays(trays: any[]) {
  const blocks: TrayBlock[] = []
  for (const t of trays) {
    const r = await api.get('/odf/slots', { params: { tray_id: t.id } })
    const slots = r.data as any[]
    const rowsMap = new Map<string, any[]>()
    for (const s of slots) {
      const key = s.row_label || ''
      if (!rowsMap.has(key)) rowsMap.set(key, [])
      rowsMap.get(key)!.push(s)
    }
    blocks.push({
      id: t.id, name: t.name,
      rows: [...rowsMap.entries()].map(([rowLabel, list]) => ({ rowLabel, slots: list })),
    })
  }
  trayBlocks.value = blocks
}

async function reload() {
  await store.loadBase()
  await store.loadTemplates()
  cords.value = (await api.get('/patch-cords')).data
  if (kind.value === 'unit') {
    unitInfo.value = (await api.get(`/odf/units/${targetId.value}`)).data
    const r = await api.get('/odf/trays', { params: { unit_id: targetId.value } })
    await loadSlotsForTrays(r.data)
  } else if (kind.value === 'tray') {
    const r = await api.get(`/odf/trays/${targetId.value}`)
    trayName.value = r.data?.name || `盘 #${targetId.value}`
    trayCabinetId.value = r.data?.cabinet_id ?? null
    await loadSlotsForTrays([{ id: targetId.value, name: trayName.value }])
  }
}

/* ---------------- 端口点击（走全局布线 store） ---------------- */
async function onPortClick(p: Port | null) {
  if (!p) return
  if (!canWrite.value) {
    message.warning('无该机房写权限，仅可查看')
    return
  }
  if (p.status === 'used') {
    const c = cordByPort.value[p.id]
    message.info(c ? `该端口已连接跳纤 #${c.id}` : '该端口已占用')
    return
  }
  const r = await wiring.pick(p)
  if (r === 'setA') {
    message.info(`已选 A 端：${store.portLabel(p)}，可在右下悬浮窗选择对端，或进入其他机柜点击端口`)
  } else if (r === 'block') {
    message.error('光口与电口不能互连，请选择同类型端口')
  } else if (r === 'same') {
    message.info('已取消选择')
  }
}

watch(() => wiring.refreshTick, () => { reload() })

/* ---------------- 悬停详情 ---------------- */
const hover = ref<{ show: boolean; x: number; y: number; port: Port | null }>(
  { show: false, x: 0, y: 0, port: null })
let hoverTimer: any = null

function onPortEnter(evt: MouseEvent, p: Port | null) {
  if (!p) return
  clearTimeout(hoverTimer)
  const x = evt.clientX
  const y = evt.clientY
  hoverTimer = setTimeout(() => { hover.value = { show: true, x, y, port: p } }, 150)
}
function onPortLeave() {
  clearTimeout(hoverTimer)
  hover.value.show = false
}

const hoverInfo = computed(() => {
  const p = hover.value.port
  if (!p) return null
  const cord = cordByPort.value[p.id]
  const peer = cord
    ? store.portById[cord.port_a_id === p.id ? cord.port_b_id : cord.port_a_id]
    : null
  return {
    label: store.portLabel(p),
    status: p.status,
    type: p.port_type || '',
    peerLabel: peer ? store.portLabel(peer) : '',
    peerType: peer?.port_type || '',
    cord: cord || null,
    remark: p.remark || '',
  }
})

const tipStyle = computed(() => {
  const w = 290
  const vw = window.innerWidth
  const left = Math.min(hover.value.x + 14, vw - w - 12)
  return { left: left + 'px', top: hover.value.y + 14 + 'px', width: w + 'px' }
})

/* ---------------- 右键菜单 ---------------- */
const menu = ref<{ show: boolean; x: number; y: number; title: string; items: MenuItem[]; port: Port | null }>(
  { show: false, x: 0, y: 0, title: '', items: [], port: null })

function openPortMenu(evt: MouseEvent, p: Port | null) {
  evt.preventDefault(); evt.stopPropagation()
  if (!p) return
  const used = p.status === 'used'
  const items: MenuItem[] = [
    { key: 'wire', label: '用它作为 A 端布线', disabled: used || !canWrite.value },
    { key: 'div1', label: '', divider: true },
    { key: 'reserve', label: '标记为预留', disabled: p.status === 'reserved' || !canWrite.value },
    { key: 'fault', label: '标记为故障', disabled: p.status === 'fault' || !canWrite.value },
    { key: 'normal', label: '恢复正常', disabled: p.status === 'free' || !canWrite.value },
  ]
  if (used) {
    items.push({ key: 'div2', label: '', divider: true })
    items.push({ key: 'unlink', label: '解除连接', danger: true, disabled: !canWrite.value })
  }
  menu.value = {
    show: true, x: evt.clientX, y: evt.clientY,
    title: `${store.portLabel(p)} · ${p.port_type} · ${statusLabel(p.status)}`,
    items, port: p,
  }
}

function statusLabel(s: string) {
  return ({ free: '空闲', used: '在用', reserved: '预留', fault: '故障' } as Record<string, string>)[s] || s
}

async function setPortStatus(p: Port, status: string) {
  try {
    await api.put(`/ports/${p.id}`, {
      port_no: p.port_no, port_type: p.port_type, status,
      group_name: p.group_name, group_seq: p.group_seq, label: p.label, remark: p.remark,
    })
    message.success('端口状态已更新')
    await reload()
  } catch (e: any) { message.error(e.response?.data?.detail || '更新失败') }
}

async function unlink(p: Port) {
  const c = cordByPort.value[p.id]
  if (!c) return
  dialog.warning({
    title: '解除连接', content: `确认拆除跳纤 #${c.id}？`,
    positiveText: '拆除', negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.delete(`/patch-cords/${c.id}`)
        message.success('已拆除')
        await reload()
      } catch (e: any) { message.error(e.response?.data?.detail || '拆除失败') }
    },
  })
}

function onMenuSelect(key: string) {
  const p = menu.value.port
  if (!p) return
  if (key === 'wire') return onPortClick(p)
  if (key === 'reserve') return setPortStatus(p, 'reserved')
  if (key === 'fault') return setPortStatus(p, 'fault')
  if (key === 'normal') return setPortStatus(p, 'free')
  if (key === 'unlink') return unlink(p)
}

/* ---------------- 连接表 ---------------- */
const cordCols = computed<DataTableColumns<any>>(() => [
  { title: '#', key: 'id', width: 60, render: (r) => h('span', { class: 'mono dim' }, String(r.id)) },
  { title: 'A 端', key: 'a', minWidth: 190, render: (r) => store.portLabel(store.portById[r.port_a_id]) },
  { title: 'B 端', key: 'b', minWidth: 190, render: (r) => store.portLabel(store.portById[r.port_b_id]) },
  { title: '型号', key: 'cord_type', width: 140 },
  {
    title: '', key: 'act', width: 76,
    render: (r) => h(NButton, {
      size: 'tiny', quaternary: true, type: 'error',
      onClick: () => dialog.warning({
        title: '拆除跳纤', content: `确认拆除 #${r.id}？`,
        positiveText: '拆除', negativeText: '取消',
        onPositiveClick: async () => {
          await api.delete(`/patch-cords/${r.id}`)
          message.success('已拆除')
          await reload()
        },
      }),
    }, { default: () => '拆除' }),
  },
])

/* ---------------- 面包屑 ---------------- */
const crumbs = computed<Crumb[]>(() => {
  const items: Crumb[] = []
  if (kind.value === 'device') {
    const d = device.value
    if (!d) return items
    const rk = store.racks.find(r => r.id === d.rack_id)
    const room = store.rooms.find(r => r.id === rk?.room_id)
    if (rk?.room_id) items.push({ label: room?.name || '机房', to: `/topology/${rk.room_id}` })
    items.push({ label: rk?.name || '机柜', to: `/interior/rack/${d.rack_id}` })
    items.push({ label: d.name })
    return items
  }
  const cabId = kind.value === 'unit' ? unitInfo.value?.cabinet_id : trayCabinetId.value
  const cab = store.cabinets.find(c => c.id === cabId)
  const room = store.rooms.find(r => r.id === cab?.room_id)
  if (cab?.room_id) items.push({ label: room?.name || '机房', to: `/topology/${cab.room_id}` })
  if (cabId) items.push({ label: cab?.name || '配线柜', to: `/interior/odf/${cabId}` })
  items.push({ label: kind.value === 'unit' ? `${unitInfo.value?.name || ''} 单元柜` : trayName.value })
  return items
})

/* ---------------- 自动刷新 ---------------- */
const autoRefresh = ref(true)
let pollTimer: any = null

async function silentRefresh() {
  if (!autoRefresh.value || wiring.cordOpen) return
  try { await reload() } catch { /* 静默 */ }
}

watch(() => route.fullPath, reload)
onMounted(async () => {
  await reload()
  pollTimer = setInterval(silentRefresh, 30000)
})
onBeforeUnmount(() => {
  clearInterval(pollTimer)
  clearTimeout(hoverTimer)
})

function shortNo(no: string) {
  const m = no.match(/(\d+)$/)
  return m ? m[1] : no
}
function portOf(slot: any): Port | null { return slot.port || null }
</script>

<template>
  <div class="l3">
    <div class="head">
      <Breadcrumb :items="crumbs" />
      <div class="grow"></div>
      <button class="poll-btn" :class="{ on: autoRefresh }" @click="autoRefresh = !autoRefresh"
              :title="autoRefresh ? '自动刷新已开启（30 秒）' : '自动刷新已关闭'">
        <Icon name="refresh" :size="12" />{{ autoRefresh ? '实时' : '已暂停' }}
      </button>
      <span v-if="!canWrite" class="ro-tag">只读 · 无该机房写权限</span>
      <span v-else-if="!wiring.aPort" class="tip">点击空闲端口选为 A 端</span>
      <span v-else class="tip">A 端已选，点击本页端口或右下悬浮窗选对端</span>
    </div>

    <div class="body">
      <section class="panel ports-panel">
        <div class="panel-head">
          <Icon name="cable" :size="14" /><span class="grow">端口</span>
          <span class="dim">{{ scopePortIds.size }} 个</span>
        </div>
        <div class="panel-body">
          <!-- 设备：按端口组分行 -->
          <template v-if="kind === 'device'">
            <div v-for="g in groups" :key="g.seq + g.name" class="group">
              <div class="g-head">
                <span class="g-bar"
                      :style="{ background: familyColorOf(store.portTypes, g.ports[0]?.port_type || '') }"></span>
                <span class="g-name">{{ g.name }}</span>
                <span class="g-type">{{ g.ports[0]?.port_type }}</span>
                <span class="g-count">{{ g.ports.filter(p => p.status === 'used').length }}/{{ g.ports.length }}</span>
              </div>
              <div class="port-row">
                <button v-for="p in g.ports" :key="p.id" class="port"
                        :class="[p.status, { picked: wiring.aPort?.id === p.id }]"
                        :title="`${p.port_no} · ${p.port_type} · ${statusLabel(p.status)}`"
                        @click="onPortClick(p)"
                        @mouseenter="onPortEnter($event, p)"
                        @mouseleave="onPortLeave"
                        @contextmenu.prevent="openPortMenu($event, p)">
                  <PortShape :shape="shapeOf(store.portTypes, p.port_type)" :size="15"
                             :fill="`var(--c-${p.status})`"
                             :stroke="familyColorOf(store.portTypes, p.port_type)" />
                  <span class="pno">{{ shortNo(p.port_no) }}</span>
                </button>
              </div>
            </div>
            <div v-if="!groups.length" class="dim empty">该设备暂无端口</div>
          </template>

          <!-- 单元柜 / 盘 -->
          <template v-else>
            <div v-for="b in trayBlocks" :key="b.id" class="tray-block">
              <div class="tray-head">
                <span class="t-name">{{ b.name }} 盘</span>
                <span class="dim">{{ b.rows.reduce((n, r) => n + r.slots.length, 0) }} 孔位</span>
              </div>
              <div v-for="r in b.rows" :key="r.rowLabel" class="slot-row">
                <span class="row-label">{{ r.rowLabel }}</span>
                <button v-for="s in r.slots" :key="s.id" class="port slot"
                        :class="[s.port?.status || 'free', { picked: wiring.aPort?.id === s.port?.id }]"
                        :title="`${s.label} · ${s.port?.port_type || ''} · ${statusLabel(s.port?.status || 'free')}`"
                        @click="onPortClick(portOf(s))"
                        @mouseenter="onPortEnter($event, portOf(s))"
                        @mouseleave="onPortLeave"
                        @contextmenu.prevent="openPortMenu($event, portOf(s))">
                  <PortShape :shape="shapeOf(store.portTypes, s.port?.port_type || 'LC/UPC')" :size="14"
                             :fill="`var(--c-${s.port?.status || 'free'})`"
                             :stroke="familyColorOf(store.portTypes, s.port?.port_type || 'LC/UPC')" />
                  <span class="pno">{{ shortNo(s.label) }}</span>
                </button>
              </div>
            </div>
            <div v-if="!trayBlocks.length" class="dim empty">暂无孔位</div>
          </template>
        </div>
      </section>

      <section class="panel cords-panel">
        <div class="panel-head">
          <Icon name="link" :size="14" /><span class="grow">本范围在用连接</span>
          <span class="dim">{{ scopeCords.length }} 条</span>
        </div>
        <div class="panel-body no-pad">
          <n-data-table :columns="cordCols" :data="scopeCords" size="small" :bordered="false"
                        :max-height="560" :row-key="(r: any) => r.id" />
        </div>
      </section>
    </div>

    <ContextMenu v-model:show="menu.show" :x="menu.x" :y="menu.y" :title="menu.title"
                 :items="menu.items" @select="onMenuSelect" />

    <!-- 端口悬停详情 -->
    <Teleport to="body">
      <div v-if="hover.show && hoverInfo" class="port-tip" :style="tipStyle">
        <div class="tip-head">
          <span class="tip-name">{{ hoverInfo.label }}</span>
          <StatusTag :status="hoverInfo.status" />
        </div>
        <div v-if="hoverInfo.type" class="tip-row">
          <span>接口类型</span><b>{{ hoverInfo.type }}</b>
        </div>
        <div v-if="hoverInfo.cord" class="tip-row">
          <span>对端</span><b>{{ hoverInfo.peerLabel }}</b>
        </div>
        <div v-if="hoverInfo.cord" class="tip-row">
          <span>对端类型</span><b>{{ hoverInfo.peerType }}</b>
        </div>
        <div v-if="hoverInfo.cord" class="tip-row">
          <span>跳纤</span>
          <b>{{ hoverInfo.cord.cord_type }}<template v-if="hoverInfo.cord.length_m"> · {{ hoverInfo.cord.length_m }} m</template></b>
        </div>
        <div v-if="hoverInfo.cord?.remark" class="tip-row">
          <span>跳纤备注</span><b>{{ hoverInfo.cord.remark }}</b>
        </div>
        <div v-if="hoverInfo.remark" class="tip-row">
          <span>端口备注</span><b>{{ hoverInfo.remark }}</b>
        </div>
        <div v-if="!hoverInfo.cord && !hoverInfo.remark" class="tip-empty">空闲端口 · 可点击开始布线</div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.l3 { display: flex; flex-direction: column; height: 100%; gap: 10px; }
.head {
  display: flex; align-items: center; gap: 12px; padding: 10px 14px;
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius);
}
.grow { flex: 1; }
.tip { font-size: 11.5px; color: var(--text-3); }
.ro-tag {
  font-size: 11.5px; color: var(--warn); background: var(--warn-soft);
  border: 1px solid var(--warn-border); border-radius: 999px; padding: 1px 10px;
}
.poll-btn {
  display: inline-flex; align-items: center; gap: 4px; flex: none;
  height: 24px; padding: 0 9px; font-size: 11px; cursor: pointer;
  background: transparent; border: 1px solid var(--border); border-radius: 999px;
  color: var(--text-3); transition: .12s;
}
.poll-btn.on { color: var(--c-used); border-color: rgba(34,197,94,.35); background: rgba(34,197,94,.10); }
.poll-btn:hover { border-color: var(--border-strong); }

.body { flex: 1; display: grid; grid-template-columns: 1fr 420px; gap: 12px; min-height: 0; }
.panel { display: flex; flex-direction: column; min-height: 0; }
.panel-body { overflow: auto; }
.panel-body.no-pad { padding: 0; }

.group { margin-bottom: 18px; }
.g-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.g-bar { width: 3px; height: 13px; border-radius: 2px; }
.g-name { font-size: 12px; font-weight: 600; color: var(--text-2); }
.g-type { font-size: 10.5px; color: var(--text-3); font-family: monospace; }
.g-count { font-size: 11px; color: var(--text-3); font-family: monospace; margin-left: auto; }
.port-row { display: flex; flex-wrap: wrap; gap: 6px; }

.port {
  width: 40px; height: 46px; border-radius: 6px; border: 1px solid;
  background: var(--cv-slot-bg); color: var(--text-2); font-size: 9.5px; font-family: monospace;
  cursor: pointer; transition: .12s;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px;
}
.port .pno { line-height: 1; }
.port:hover { transform: translateY(-2px); box-shadow: 0 5px 14px rgba(0,0,0,.22); }
.port.free { border-color: var(--border-strong); }
.port.used { border-color: var(--c-used); color: var(--c-used); background: rgba(34,197,94,.10); }
.port.reserved { border-color: var(--c-reserved); color: var(--c-reserved); background: rgba(59,130,246,.10); }
.port.fault { border-color: var(--c-fault); color: var(--c-fault); background: rgba(239,68,68,.10); }
.port.picked { outline: 2px solid var(--accent); outline-offset: 1px; }

.tray-block { margin-bottom: 16px; }
.tray-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 7px; }
.t-name { font-size: 12px; font-weight: 600; }
.slot-row { display: flex; align-items: center; gap: 5px; margin-bottom: 6px; flex-wrap: wrap; }
.row-label { width: 14px; font-size: 10.5px; color: var(--text-3); }
.port.slot { width: 44px; height: 44px; }

.empty { padding: 24px 0; text-align: center; }

/* 端口悬停浮层 */
.port-tip {
  position: fixed; z-index: 4000; pointer-events: none;
  background: var(--bg-panel); border: 1px solid var(--border-strong);
  border-radius: 9px; box-shadow: var(--shadow-2); padding: 10px 12px;
  font-size: 12px; color: var(--text-1);
}
.tip-head {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding-bottom: 7px; margin-bottom: 7px; border-bottom: 1px solid var(--border);
}
.tip-name { font-family: monospace; font-size: 12px; font-weight: 600; }
.tip-row { display: flex; gap: 10px; padding: 2px 0; line-height: 1.6; }
.tip-row span { color: var(--text-3); flex: none; min-width: 62px; }
.tip-row b { font-weight: 500; color: var(--text-1); word-break: break-all; }
.tip-empty { color: var(--text-3); font-size: 11.5px; }
</style>
