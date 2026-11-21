<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NTree, NSelect, NDataTable, NButton, NDropdown, NModal, NSteps, NStep, NSpin, useMessage } from 'naive-ui'
import type { TreeOption, DataTableColumns } from 'naive-ui'
import { api } from '../api/client'
import { useResourceStore, DEVICE_TYPE_LABEL } from '../stores/resource'
import { useSessionStore } from '../stores/session'
import { roomSelectOptions, roomPath } from '../utils/rooms'
import type { Device, Slot, Tray } from '../stores/resource'
import DialogForm from '../components/ui/DialogForm.vue'
import type { FormField } from '../components/ui/DialogForm.vue'
import StatusTag from '../components/ui/StatusTag.vue'
import Icon from '../components/ui/Icon.vue'

const router = useRouter()
const message = useMessage()
const store = useResourceStore()
const session = useSessionStore()

const selRoom = ref<number | null>(null)
const selKey = ref<string>('')
const loadingTree = ref(false)

/* ---------- 树数据 ---------- */
interface Node { key: string; label: string; kind: string; id: number; children?: Node[] }
const unitMap = ref<Record<number, any[]>>({})
const trayMap = ref<Record<number, any[]>>({})

const treeData = computed<TreeOption[]>(() => {
  const rid = selRoom.value
  if (!rid) return []
  const room = store.rooms.find(r => r.id === rid)
  const rackNodes: Node[] = store.racksOfRoom(rid).map(rk => ({
    key: `rack-${rk.id}`, label: rk.name, kind: 'rack', id: rk.id,
    children: store.devicesOfRack(rk.id).map(d => ({
      key: `dev-${d.id}`, label: d.name, kind: 'device', id: d.id,
    })),
  }))
  const cabNodes: Node[] = store.cabinets.filter(c => c.room_id === rid).map(c => ({
    key: `cab-${c.id}`, label: c.name, kind: 'cabinet', id: c.id,
    children: (unitMap.value[c.id] || []).map(u => ({
      key: `unit-${u.id}`, label: `${u.name} 单元`, kind: 'unit', id: u.id,
      children: (trayMap.value[u.id] || []).map(t => ({
        key: `tray-${t.id}`, label: `${t.name} 盘`, kind: 'tray', id: t.id,
      })),
    })),
  }))
  return [{
    key: `room-${rid}`, label: room?.name || '机房',
    children: [
      { key: 'g-racks', label: '机柜', children: rackNodes },
      { key: 'g-odf', label: 'ODF 配线柜', children: cabNodes },
    ],
  }] as unknown as TreeOption[]
})

function renderLabel({ option }: { option: TreeOption }) {
  const label = String(option.label || '')
  const key = String(option.key || '')
  const isGroup = key.startsWith('g-')
  const icon = key.startsWith('rack-') ? 'server' : key.startsWith('dev-') ? 'box'
    : key.startsWith('cab-') ? 'grid' : key.startsWith('unit-') ? 'box' : key.startsWith('tray-') ? 'cable' : ''
  return h('span', {
    class: ['tree-node', { group: isGroup }],
    title: isGroup ? '' : '双击进入详细视图',
    onDblclick: (e: MouseEvent) => onTreeDblClick(e, option),
  }, [
    icon ? h(Icon, { name: icon, size: 13 }) : null,
    h('span', { class: 'lbl' }, label),
  ])
}

/* ---------- 加载 ---------- */
async function loadTreeExtras(roomId: number) {
  loadingTree.value = true
  try {
    const um: Record<number, any[]> = {}
    const tm: Record<number, any[]> = {}
    for (const c of store.cabinets.filter(c => c.room_id === roomId)) {
      const units = await store.loadUnits(c.id)
      um[c.id] = units
      for (const u of units) {
        const trays = await store.loadTrays(u.id)
        tm[u.id] = trays
      }
    }
    unitMap.value = um
    trayMap.value = tm
  } finally {
    loadingTree.value = false
  }
}

async function selectRoom(id: number) {
  selRoom.value = id
  selKey.value = ''
  await loadTreeExtras(id)
}

watch(() => store.rooms, (rooms) => {
  if (!selRoom.value && rooms.length) selectRoom(rooms[0].id)
}, { immediate: true })

onMounted(async () => {
  if (!store.rooms.length) await store.loadBase()
})

/* ---------- 选中项 ---------- */
const sel = computed(() => {
  const k = selKey.value
  if (!k) return null
  const [kind, idStr] = k.split('-')
  return { kind, id: Number(idStr) }
})

const selRack = computed(() => sel.value?.kind === 'rack' ? store.racks.find(r => r.id === sel.value!.id) : null)
const selDevice = computed(() => sel.value?.kind === 'device' ? store.devices.find(d => d.id === sel.value!.id) : null)
const selCabinet = computed(() => sel.value?.kind === 'cabinet' ? store.cabinets.find(c => c.id === sel.value!.id) : null)
const selUnit = computed(() => {
  if (sel.value?.kind !== 'unit') return null
  for (const cid in unitMap.value) {
    const u = unitMap.value[cid].find((x: any) => x.id === sel.value!.id)
    if (u) return { unit: u, cabinetId: Number(cid) }
  }
  return null
})
const selTray = computed(() => {
  if (sel.value?.kind !== 'tray') return null
  for (const uid in trayMap.value) {
    const t = trayMap.value[uid].find((x: any) => x.id === sel.value!.id)
    if (t) return t as Tray
  }
  return null
})

/* ---------- 详情数据 ---------- */
const slots = ref<Slot[]>([])
const trayLoading = ref(false)

watch(selTray, async (t) => {
  if (!t) { slots.value = []; return }
  trayLoading.value = true
  try { slots.value = await store.loadSlots(t.id) } finally { trayLoading.value = false }
})

const rackDevices = computed(() => selRack.value ? store.devicesOfRack(selRack.value.id) : [])
const devicePorts = computed(() => selDevice.value ? store.portsOfDevice(selDevice.value.id) : [])
const roomDevices = computed(() => selRoom.value
  ? store.devices.filter(d => store.racksOfRoom(selRoom.value!).some(r => r.id === d.rack_id))
  : [])

/* ---------- 表格列 ---------- */
const deviceCols = computed<DataTableColumns<Device>>(() => [
  { title: '设备名称', key: 'name', minWidth: 150 },
  {
    title: '类型', key: 'device_type', width: 110,
    render: (r: Device) => h('span', { class: 'type-chip' }, DEVICE_TYPE_LABEL[r.device_type] || r.device_type),
  },
  { title: '型号', key: 'model', width: 120 },
  {
    title: 'U 位', key: 'u_position', width: 110,
    render: (r: Device) => {
      const h = r.u_height || 1
      return h > 1 ? `U${r.u_position}–U${r.u_position + h - 1}（${h}U）` : `U${r.u_position}（1U）`
    },
  },
  { title: '管理 IP', key: 'mgmt_ip', width: 130, render: (r: Device) => r.mgmt_ip || h('span', { class: 'dim' }, '—') },
  {
    title: '操作', key: 'act', width: 110,
    render: (r: Device) => h(NButton, {
      size: 'tiny', quaternary: true, type: 'primary',
      onClick: () => enterDevice(r.id),
    }, { default: () => '查看端口' }),
  },
])

/** 进入设备端口视图（与画布双击设备一致） */
function enterDevice(id: number) {
  router.push(`/ports/device/${id}`)
}

/** 树节点双击 → 进入对应视图 */
function onTreeDblClick(_e: MouseEvent, opt: TreeOption) {
  const key = String(opt.key || '')
  if (key.startsWith('rack-')) router.push(`/interior/rack/${key.slice(5)}`)
  else if (key.startsWith('dev-')) router.push(`/ports/device/${key.slice(4)}`)
  else if (key.startsWith('cab-')) router.push(`/interior/odf/${key.slice(4)}`)
  else if (key.startsWith('unit-')) router.push(`/ports/unit/${key.slice(5)}`)
  else if (key.startsWith('tray-')) router.push(`/ports/tray/${key.slice(5)}`)
}

/** 当前选中对象的"进入详细视图"目标 */
const enterTarget = computed(() => {
  const s = sel.value
  if (!s) return null
  if (s.kind === 'rack') return { label: '进入机柜视图', to: `/interior/rack/${s.id}` }
  if (s.kind === 'device') return { label: '进入端口视图', to: `/ports/device/${s.id}` }
  if (s.kind === 'cabinet') return { label: '进入配线柜视图', to: `/interior/odf/${s.id}` }
  if (s.kind === 'unit') return { label: '进入单元柜端口', to: `/ports/unit/${s.id}` }
  if (s.kind === 'tray') return { label: '进入盘端口', to: `/ports/tray/${s.id}` }
  return null
})

const portCols = computed<DataTableColumns<any>>(() => [
  { title: '端口号', key: 'port_no', minWidth: 130, render: (r) => h('span', { class: 'mono' }, r.port_no) },
  { title: '类型', key: 'port_type', width: 100 },
  { title: '状态', key: 'status', width: 100, render: (r) => h(StatusTag, { status: r.status }) },
  { title: '标签', key: 'label', minWidth: 120, render: (r) => r.label || h('span', { class: 'dim' }, '—') },
])

/* ---------- 弹窗 ---------- */
const dlg = ref<{ show: boolean; title: string; fields: FormField[]; initial: any; submit: (v: any) => Promise<void> }>(
  { show: false, title: '', fields: [], initial: {}, submit: async () => {} })

function openDialog(title: string, fields: FormField[], initial: any, submit: (v: any) => Promise<void>) {
  dlg.value = { show: true, title, fields, initial, submit }
}

async function afterMutate(msg: string) {
  message.success(msg)
  dlg.value.show = false
  await store.loadBase()
  if (selRoom.value) await loadTreeExtras(selRoom.value)
}

function newRoom() {
  const fields: FormField[] = [
    { key: 'name', label: '机房名称', required: true, placeholder: '如 核心机房 / 一号前端机房' },
    { key: 'code', label: '机房编码', required: true, placeholder: '如 CR-01 / FR-01' },
    {
      key: 'parent_id', label: '上级机房', type: 'select', options: roomOptions.value,
      hint: session.isCore
        ? '留空 = 顶层核心机房；选择上级 = 其子机房'
        : '前端机房管理员只能在被授权机房下新建子机房',
    },
    { key: 'address', label: '位置', placeholder: '如 A栋2楼' },
  ]
  openDialog('新建机房', fields, { parent_id: session.isCore ? null : selRoom.value }, async (v) => {
    try {
      await api.post('/rooms', {
        name: v.name, code: v.code, address: v.address || '',
        parent_id: v.parent_id ?? null,
      })
      await afterMutate('机房已创建')
    } catch (e: any) { message.error(e.response?.data?.detail || '创建失败') }
  })
}

function newRack() {
  if (!selRoom.value) return message.warning('请先选择机房')
  if (!canWrite.value) return message.warning('无该机房写权限')
  openDialog('新建机柜', [
    { key: 'name', label: '机柜名称', required: true, placeholder: '如 01架' },
    { key: 'code', label: '机柜编码', required: true, placeholder: '如 R01' },
    { key: 'u_count', label: 'U 数', type: 'number', default: 42, min: 1 },
  ], {}, async (v) => {
    await api.post('/racks', { ...v, room_id: selRoom.value })
    await afterMutate('机柜已创建')
  })
}

function newDevice(rackId?: number) {
  if (!canWrite.value) return message.warning('无该机房写权限')
  const rid = rackId ?? selRack.value?.id ?? store.racksOfRoom(selRoom.value!)[0]?.id
  if (!rid) return message.warning('请先创建机柜')
  openDialog('新建设备', [
    { key: 'name', label: '设备名称', required: true, placeholder: '如 汇聚交换机-01' },
    {
      key: 'device_type', label: '设备类型', type: 'select', required: true,
      default: 'sw',
      options: Object.entries(DEVICE_TYPE_LABEL).map(([v, l]) => ({ label: l, value: v })),
    },
    { key: 'model', label: '型号', placeholder: '如 S5730' },
    { key: 'u_position', label: 'U 位', type: 'number', default: 1, min: 1 },
    { key: 'mgmt_ip', label: '管理 IP', placeholder: '选填' },
  ], {}, async (v) => {
    await api.post('/devices', { ...v, rack_id: rid })
    await afterMutate('设备已创建（已按型号生成端口）')
  })
}

function newCabinet() {
  if (!selRoom.value) return message.warning('请先选择机房')
  if (!canWrite.value) return message.warning('无该机房写权限')
  openDialog('新建 ODF 配线柜', [
    { key: 'name', label: '配线柜名称', required: true, placeholder: '如 ODF-1' },
    { key: 'code', label: '编码', required: true, placeholder: '如 ODF01' },
  ], {}, async (v) => {
    const cab = (await api.post('/odf/cabinets', { ...v, room_id: selRoom.value })).data
    for (const [i, u] of ['A', 'B', 'C', 'D', 'E'].entries()) {
      await api.post('/odf/units', { cabinet_id: cab.id, name: u, seq: i + 1 })
    }
    await afterMutate('ODF 配线柜已创建（默认生成 A–E 单元柜）')
  })
}

function newUnit(cabinetId: number) {
  openDialog('新建单元柜', [
    { key: 'name', label: '单元柜标识', required: true, placeholder: '如 F' },
    { key: 'seq', label: '顺序', type: 'number', default: 1, min: 1 },
  ], {}, async (v) => {
    await api.post('/odf/units', { ...v, cabinet_id: cabinetId })
    await afterMutate('单元柜已创建')
  })
}

function newTray(unitId: number) {
  openDialog('新建盘', [
    { key: 'name', label: '盘号', required: true, placeholder: '如 3' },
    {
      key: 'spec', label: '规格', type: 'select', default: '1x12',
      options: [{ label: '1 行 × 12 孔', value: '1x12' }, { label: '2 行 × 6 孔', value: '2x6' }],
    },
    { key: 'seq', label: '顺序', type: 'number', default: 1, min: 1 },
  ], {}, async (v) => {
    const [rows, spr] = String(v.spec).split('x').map(Number)
    await api.post('/odf/trays', {
      unit_id: unitId, name: v.name, rows, slots_per_row: spr, seq: v.seq,
    })
    await afterMutate('盘已创建（孔位自动生成）')
  })
}

/* ---------- Excel 导入 ---------- */
const importShow = ref(false)
const importStep = ref(1)
const importFile = ref<File | null>(null)
const importBusy = ref(false)
const importResult = ref<any>(null)

function pickImportFile(e: Event) {
  const el = e.target as HTMLInputElement
  importFile.value = el.files?.[0] || null
  importResult.value = null
  if (importFile.value) importStep.value = 1
}

async function previewImport() {
  if (!importFile.value) return
  importBusy.value = true
  try {
    const fd = new FormData()
    fd.append('file', importFile.value)
    const r = await api.post('/import/excel', fd)
    importResult.value = r.data
    importStep.value = 2
  } catch (e: any) {
    message.error(e.response?.data?.detail || '解析失败')
  } finally {
    importBusy.value = false
  }
}

async function applyImport() {
  if (!importResult.value?.plan) return
  importBusy.value = true
  try {
    const r = await api.post('/import/excel/apply', { plan: importResult.value.plan })
    message.success(`导入完成：机房 ${r.data.created.rooms} / 机柜 ${r.data.created.racks} / 设备 ${r.data.created.devices}`)
    importShow.value = false
    importStep.value = 1
    importFile.value = null
    importResult.value = null
    await store.loadBase()
    if (selRoom.value) await loadTreeExtras(selRoom.value)
  } catch (e: any) {
    message.error(e.response?.data?.detail || '导入失败')
  } finally {
    importBusy.value = false
  }
}

function downloadTemplate() {
  window.open('/fiber/api/v1/import/template', '_blank')
}

function exportInventory() {
  window.open('/fiber/api/v1/export/inventory', '_blank')
}

const createOptions = [
  { label: '机房', key: 'room' },
  { label: '机柜', key: 'rack' },
  { label: '设备', key: 'device' },
  { label: 'ODF 配线柜', key: 'cabinet' },
]
function onCreateSelect(key: string) {
  ({ room: newRoom, rack: newRack, device: () => newDevice(), cabinet: newCabinet } as any)[key]()
}

/* ---------- 孔位网格 ---------- */
const slotRows = computed(() => {
  if (!selTray.value) return []
  const rows = selTray.value.rows
  const spr = selTray.value.slots_per_row
  const out: Slot[][] = []
  for (let r = 0; r < rows; r++) out.push(slots.value.slice(r * spr, (r + 1) * spr))
  return out
})

function gotoTopology() {
  if (selRoom.value) router.push(`/topology/${selRoom.value}`)
}

const roomOptions = computed(() => roomSelectOptions(store.rooms as any))
const canWrite = computed(() => session.canWriteRoom(selRoom.value))
const roomLabel = computed(() => roomPath(store.rooms as any, selRoom.value))
</script>

<template>
  <div class="inv">
    <!-- 左：资源树 -->
    <section class="panel tree-panel">
      <div class="panel-head">
        <Icon name="grid" :size="14" />
        <span class="grow">资源导航</span>
        <n-dropdown trigger="click" :options="createOptions" @select="onCreateSelect">
          <n-button size="tiny" type="primary" secondary>
            <template #icon><Icon name="plus" :size="12" /></template>
            新建
          </n-button>
        </n-dropdown>
      </div>
      <div class="room-pick">
        <n-select v-model:value="selRoom" :options="roomOptions" size="small"
                  placeholder="选择机房" @update:value="selectRoom" />
        <div class="room-meta">
          <span class="dim">{{ roomLabel }}</span>
          <span v-if="selRoom && !canWrite" class="ro-tag">只读</span>
        </div>
      </div>
      <div class="tree-wrap">
        <n-spin :show="loadingTree">
          <n-tree v-if="treeData.length" :data="treeData" block-line :selectable="true"
                  :selected-keys="selKey ? [selKey] : []" :render-label="renderLabel"
                  :default-expanded-keys="[`room-${selRoom}`, 'g-racks', 'g-odf']"
                  @update:selected-keys="(k: any) => selKey = String(k[0] || '')" />
          <div v-else class="empty">暂无资源，点击「新建」开始</div>
        </n-spin>
      </div>
      <div class="tree-foot">
        <n-button size="tiny" quaternary block @click="importShow = true">
          <template #icon><Icon name="upload" :size="12" /></template>
          Excel 批量导入
        </n-button>
        <n-button size="tiny" quaternary block @click="exportInventory">
          <template #icon><Icon name="download" :size="12" /></template>
          导出台账
        </n-button>
        <n-button size="tiny" quaternary block @click="gotoTopology">
          <template #icon><Icon name="topology" :size="12" /></template>
          打开拓扑画布
        </n-button>
      </div>
    </section>

    <!-- 右：下钻详情 -->
    <section class="panel detail">
      <div class="panel-head">
        <span class="grow detail-title">
          <template v-if="selTray">盘 {{ selTray.name }} · 孔位</template>
          <template v-else-if="selUnit">单元柜 {{ selUnit.unit.name }}</template>
          <template v-else-if="selCabinet">{{ selCabinet.name }} · 单元柜</template>
          <template v-else-if="selDevice">{{ selDevice.name }} · 端口</template>
          <template v-else-if="selRack">{{ selRack.name }} · 设备</template>
          <template v-else>机房设备总览</template>
        </span>
        <n-button v-if="selRack" size="tiny" type="primary" secondary @click="newDevice(selRack.id)">
          <template #icon><Icon name="plus" :size="12" /></template>设备
        </n-button>
        <n-button v-if="selCabinet" size="tiny" type="primary" secondary @click="newUnit(selCabinet.id)">
          <template #icon><Icon name="plus" :size="12" /></template>单元柜
        </n-button>
        <n-button v-if="selUnit" size="tiny" type="primary" secondary @click="newTray(selUnit.unit.id)">
          <template #icon><Icon name="plus" :size="12" /></template>盘
        </n-button>
        <n-button v-if="enterTarget" size="tiny" tertiary @click="router.push(enterTarget.to)">
          {{ enterTarget.label }} ›
        </n-button>
      </div>

      <div class="detail-body">
        <!-- 盘：孔位网格 -->
        <template v-if="selTray">
          <n-spin :show="trayLoading">
            <div class="slot-legend">
              <span><i class="sw" style="background: var(--c-free)"></i>空闲</span>
              <span><i class="sw" style="background: var(--c-used)"></i>在用</span>
              <span><i class="sw" style="background: var(--c-reserved)"></i>预留</span>
              <span><i class="sw" style="background: var(--c-fault)"></i>故障</span>
              <span class="dim">共 {{ slots.length }} 孔位</span>
            </div>
            <div class="slot-rows">
              <div v-for="(row, ri) in slotRows" :key="ri" class="slot-row">
                <span class="row-idx">{{ selTray.rows > 1 ? String.fromCharCode(65 + ri) : '' }}</span>
                <div v-for="s in row" :key="s.id" class="slot"
                     :style="{ borderColor: `var(--c-${s.port?.status || 'free'})` }"
                     :title="`${s.label} · ${s.port?.status || 'free'}`">
                  <i class="fill" :style="{ background: `var(--c-${s.port?.status || 'free'})` }"></i>
                  <span>{{ s.label }}</span>
                </div>
              </div>
            </div>
          </n-spin>
        </template>

        <!-- 单元柜：盘列表 -->
        <template v-else-if="selUnit">
          <div class="cards">
            <div v-for="t in (trayMap[selUnit.unit.id] || [])" :key="t.id" class="mini-card"
                 @click="selKey = `tray-${t.id}`">
              <div class="mc-title">{{ t.name }} 盘</div>
              <div class="mc-sub">{{ t.rows }}×{{ t.slots_per_row }} = {{ t.rows * t.slots_per_row }} 孔</div>
            </div>
            <div v-if="!(trayMap[selUnit.unit.id] || []).length" class="empty">该单元柜暂无盘</div>
          </div>
        </template>

        <!-- 配线柜：单元柜列表 -->
        <template v-else-if="selCabinet">
          <div class="cards">
            <div v-for="u in (unitMap[selCabinet.id] || [])" :key="u.id" class="mini-card"
                 @click="selKey = `unit-${u.id}`">
              <div class="mc-title">{{ u.name }} 单元</div>
              <div class="mc-sub">{{ (trayMap[u.id] || []).length }} 个盘</div>
            </div>
            <div v-if="!(unitMap[selCabinet.id] || []).length" class="empty">暂无单元柜</div>
          </div>
        </template>

        <!-- 设备：端口表 -->
        <template v-else-if="selDevice">
          <div class="dev-meta">
            <div><span class="dim">类型</span><b>{{ DEVICE_TYPE_LABEL[selDevice.device_type] }}</b></div>
            <div><span class="dim">型号</span><b>{{ selDevice.model || '—' }}</b></div>
            <div><span class="dim">U 位</span><b>U{{ selDevice.u_position }}–U{{ selDevice.u_position + (selDevice.u_height || 1) - 1 }}（{{ selDevice.u_height || 1 }}U）</b></div>
            <div><span class="dim">管理 IP</span><b class="mono">{{ selDevice.mgmt_ip || '—' }}</b></div>
            <div><span class="dim">端口数</span><b>{{ devicePorts.length }}</b></div>
          </div>
          <n-data-table :columns="portCols" :data="devicePorts" :max-height="420" size="small"
                        :bordered="false" :row-key="(r: any) => r.id" />
        </template>

        <!-- 机柜：设备表 -->
        <template v-else-if="selRack">
          <n-data-table :columns="deviceCols" :data="rackDevices" size="small"
                        :bordered="false" :row-key="(r: any) => r.id" />
        </template>

        <!-- 默认：本机房全部设备 -->
        <template v-else>
          <n-data-table :columns="deviceCols" :data="roomDevices" size="small"
                        :bordered="false" :row-key="(r: any) => r.id" />
        </template>
      </div>
    </section>

    <!-- 通用表单弹窗 -->
    <DialogForm v-model:show="dlg.show" :title="dlg.title" :fields="dlg.fields" :initial="dlg.initial"
                @submit="dlg.submit" />

    <!-- Excel 导入 -->
    <n-modal v-model:show="importShow">
      <div class="import-modal">
        <header class="im-head">Excel 批量导入<span class="x" @click="importShow = false">✕</span></header>
        <div class="im-body">
          <n-steps :current="importStep" size="small">
            <n-step title="选择文件" />
            <n-step title="校验预览" />
            <n-step title="完成" />
          </n-steps>

          <div v-if="importStep === 1" class="im-block">
            <p class="dim">支持 机房 / 机柜 / 设备 三个工作表，按模板填写后上传。</p>
            <div class="row">
              <input type="file" accept=".xlsx" @change="pickImportFile" />
              <n-button size="small" quaternary @click="downloadTemplate">
                <template #icon><Icon name="download" :size="12" /></template>下载模板
              </n-button>
            </div>
          </div>

          <div v-if="importStep === 2 && importResult" class="im-block">
            <div v-if="importResult.error_count" class="im-errors">
              <b>发现 {{ importResult.error_count }} 处错误，整体拒绝导入：</b>
              <ul>
                <li v-for="(e, i) in importResult.errors" :key="i">
                  {{ e.sheet }} 第 {{ e.row }} 行：{{ e.error }}
                </li>
              </ul>
            </div>
            <div v-else class="im-ok">
              <Icon name="check" :size="14" />
              校验通过：机房 {{ importResult.counts.rooms }} · 机柜 {{ importResult.counts.racks }} · 设备 {{ importResult.counts.devices }}
            </div>
          </div>
        </div>
        <footer class="im-foot">
          <n-button quaternary size="small" @click="importShow = false">取消</n-button>
          <n-button v-if="importStep === 1" size="small" type="primary" :loading="importBusy"
                    :disabled="!importFile" @click="previewImport">解析校验</n-button>
          <n-button v-if="importStep === 2 && importResult?.valid" size="small" type="primary"
                    :loading="importBusy" @click="applyImport">确认导入</n-button>
          <n-button v-if="importStep === 2 && !importResult?.valid" size="small" @click="importStep = 1">重新选择</n-button>
        </footer>
      </div>
    </n-modal>
  </div>
</template>

<style scoped>
.inv { display: grid; grid-template-columns: 300px 1fr; gap: 14px; height: 100%; }

/* 树面板 */
.tree-panel { display: flex; flex-direction: column; min-height: 0; }
.room-pick { padding: 10px 12px; border-bottom: 1px solid var(--border); }
.room-meta {
  display: flex; align-items: center; gap: 8px; margin-top: 6px;
  font-size: 10.5px; color: var(--text-3); overflow: hidden;
}
.room-meta .dim { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ro-tag {
  flex: none; color: var(--warn); background: var(--warn-soft);
  border: 1px solid var(--warn-border); border-radius: 999px; padding: 0 7px; font-size: 10px;
}
.tree-wrap { flex: 1; overflow: auto; padding: 8px 6px; min-height: 0; }
.tree-foot { padding: 8px; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 2px; }
.empty { color: var(--text-3); font-size: 12px; text-align: center; padding: 24px 8px; }
:deep(.tree-node) { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; }
:deep(.tree-node.group) { color: var(--text-3); font-size: 11px; letter-spacing: .5px; }

/* 详情 */
.detail { display: flex; flex-direction: column; min-height: 0; }
.detail-title { font-size: 13px; font-weight: 600; }
.detail-body { flex: 1; overflow: auto; padding: 14px 16px; min-height: 0; }

.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
.mini-card {
  border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 14px;
  cursor: pointer; transition: .14s; background: var(--bg-elevated);
}
.mini-card:hover { border-color: var(--accent); background: var(--bg-hover); transform: translateY(-1px); }
.mc-title { font-size: 13px; font-weight: 600; }
.mc-sub { font-size: 11.5px; color: var(--text-3); margin-top: 3px; }

.dev-meta { display: flex; gap: 28px; flex-wrap: wrap; margin-bottom: 14px; }
.dev-meta > div { display: flex; flex-direction: column; gap: 2px; }
.dev-meta .dim { font-size: 11px; }
.dev-meta b { font-size: 13px; }
:deep(.type-chip) {
  font-size: 11.5px; padding: 1px 8px; border-radius: 999px;
  background: rgba(56,189,248,.12); color: var(--accent); border: 1px solid rgba(56,189,248,.25);
}

/* 孔位 */
.slot-legend { display: flex; gap: 16px; align-items: center; font-size: 11.5px; color: var(--text-2); margin-bottom: 14px; }
.slot-legend span { display: inline-flex; align-items: center; gap: 5px; }
.sw { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
.slot-rows { display: flex; flex-direction: column; gap: 8px; }
.slot-row { display: flex; gap: 6px; align-items: center; }
.row-idx { width: 14px; font-size: 11px; color: var(--text-3); text-align: center; }
.slot {
  width: 62px; height: 40px; border-radius: 6px; border: 1px solid;
  background: var(--bg-elevated); display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 3px;
  font-size: 10.5px; color: var(--text-2); cursor: default;
  transition: transform .12s, box-shadow .12s;
}
.slot:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0,0,0,.22); }
.slot .fill { width: 16px; height: 3px; border-radius: 2px; }

/* Excel 弹窗 */
.import-modal {
  width: 560px; max-width: 92vw; background: var(--bg-panel);
  border: 1px solid var(--border-strong); border-radius: var(--radius-lg);
  box-shadow: var(--shadow-2); overflow: hidden;
}
.im-head { display: flex; justify-content: space-between; align-items: center;
  padding: 14px 18px; border-bottom: 1px solid var(--border); font-weight: 600; font-size: 14px; }
.im-head .x { cursor: pointer; color: var(--text-3); font-size: 13px; }
.im-body { padding: 18px; }
.im-block { margin-top: 18px; }
.im-block input[type=file] { color: var(--text-2); font-size: 12px; }
.im-errors { color: var(--c-fault); font-size: 12.5px; background: rgba(239,68,68,.08);
  border: 1px solid rgba(239,68,68,.28); border-radius: 8px; padding: 10px 14px; }
.im-errors ul { margin: 8px 0 0; padding-left: 18px; max-height: 180px; overflow: auto; }
.im-ok { display: flex; align-items: center; gap: 8px; color: var(--c-used); font-size: 12.5px;
  background: rgba(34,197,94,.08); border: 1px solid rgba(34,197,94,.28);
  border-radius: 8px; padding: 10px 14px; }
.im-foot { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 18px;
  border-top: 1px solid var(--border); }

/* ============ 响应式 ============ */
@media (max-width: 900px) {
  .inv { grid-template-columns: 1fr; height: auto; }
  .tree-panel { max-height: 42vh; }
  .detail { min-height: 40vh; }
  .cards { grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); }
  .slot { width: 52px; height: 36px; }
}
</style>
