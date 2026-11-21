<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import { NSelect, NButton, NInput, NInputNumber, NDataTable, NTabs, NTabPane, NEmpty, useMessage, useDialog } from 'naive-ui'
import type { DataTableColumns, SelectOption } from 'naive-ui'
import { api } from '../api/client'
import { useResourceStore } from '../stores/resource'
import StatusTag from '../components/ui/StatusTag.vue'
import Icon from '../components/ui/Icon.vue'
import CordHistoryDrawer from '../components/wiring/CordHistoryDrawer.vue'

const message = useMessage()
const dialog = useDialog()
const store = useResourceStore()

const tab = ref<'cord' | 'inter' | 'core'>('cord')

/* ---------- 端口选择（跳纤） ---------- */
const cordA = ref<number | null>(null)
const cordB = ref<number | null>(null)
const cordType = ref('LC-LC 单模')
const cordLen = ref<number | null>(null)
const cordBusy = ref(false)

const portOptions = computed<SelectOption[]>(() => {
  const groups: SelectOption[] = []
  // 设备端口
  const byDevice = new Map<number, SelectOption[]>()
  for (const p of store.ports) {
    if (p.owner_type !== 'device') continue
    const d = store.deviceById[p.owner_id]
    if (!d) continue
    if (!byDevice.has(d.id)) byDevice.set(d.id, [])
    byDevice.get(d.id)!.push({
      label: `${p.port_no}  ${p.status === 'free' ? '' : '· ' + p.status}`,
      value: p.id,
      disabled: p.status !== 'free',
    })
  }
  for (const [did, children] of byDevice) {
    groups.push({ type: 'group', key: `d-${did}`, label: store.deviceById[did].name, children })
  }
  // ODF 孔位
  const odf = store.ports.filter(p => p.owner_type === 'odf_slot').map(p => ({
    label: `${p.port_no}  ${p.status === 'free' ? '' : '· ' + p.status}`,
    value: p.id,
    disabled: p.status !== 'free',
  }))
  if (odf.length) groups.push({ type: 'group', key: 'odf', label: 'ODF 孔位', children: odf })
  return groups
})

async function createCord() {
  if (!cordA.value || !cordB.value) return message.warning('请选择两端端口')
  if (cordA.value === cordB.value) return message.warning('两端不能相同')
  cordBusy.value = true
  try {
    await api.post('/patch-cords', {
      port_a_id: cordA.value, port_b_id: cordB.value,
      cord_type: cordType.value, length_m: cordLen.value || 0,
    })
    message.success('跳纤已创建')
    cordA.value = cordB.value = null
    await Promise.all([store.loadBase(), loadCords()])
  } catch (e: any) {
    message.error(e.response?.data?.detail || '创建失败')
  } finally {
    cordBusy.value = false
  }
}

/* ---------- 在用跳纤 ---------- */
const cords = ref<any[]>([])
async function loadCords() {
  cords.value = (await api.get('/patch-cords')).data
}
async function removeCord(id: number) {
  dialog.warning({
    title: '拆除跳纤',
    content: '确认拆除该跳纤？端口将恢复空闲状态，此操作会记入变更历史。',
    positiveText: '确认拆除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.delete(`/patch-cords/${id}`)
        message.success('已拆除')
        await Promise.all([store.loadBase(), loadCords()])
      } catch (e: any) { message.error(e.response?.data?.detail || '拆除失败') }
    },
  })
}

const historyCordId = ref<number | null>(null)

function fmtTime(ts: string | null | undefined) {
  return ts ? ts.replace('T', ' ').slice(0, 16) : '—'
}

const cordCols = computed<DataTableColumns<any>>(() => [
  { title: '#', key: 'id', width: 56, render: (r) => h('span', { class: 'dim mono' }, String(r.id)) },
  { title: 'A 端', key: 'a', minWidth: 175, render: (r) => store.portLabel(store.portById[r.port_a_id]) },
  { title: 'B 端', key: 'b', minWidth: 175, render: (r) => store.portLabel(store.portById[r.port_b_id]) },
  { title: '型号', key: 'cord_type', width: 136 },
  {
    title: '最后更新', key: 'updated_at', width: 132,
    render: (r) => h('span', { class: 'dim mono', style: 'font-size:11px' }, fmtTime(r.updated_at)),
  },
  {
    title: '记录', key: 'hist', width: 62,
    render: (r) => h(NButton, {
      size: 'tiny', quaternary: true, type: 'primary',
      onClick: () => { historyCordId.value = r.id },
    }, { default: () => '明细' }),
  },
  {
    title: '', key: 'act', width: 62,
    render: (r) => h(NButton, { size: 'tiny', quaternary: true, type: 'error', onClick: () => removeCord(r.id) },
      { default: () => '拆除' }),
  },
])

/* ---------- 盘间连接 ---------- */
const slotOptions = computed<SelectOption[]>(() =>
  store.ports.filter(p => p.owner_type === 'odf_slot')
    .map(p => ({ label: `${p.port_no}`, value: p.owner_id, disabled: false })))

const icA = ref<number | null>(null)
const icB = ref<number | null>(null)
const icKind = ref<'adapter' | 'splice'>('adapter')
const icBusy = ref(false)
const ics = ref<any[]>([])

async function loadIcs() { ics.value = (await api.get('/interconnects')).data }

async function createIc() {
  if (!icA.value || !icB.value) return message.warning('请选择两个孔位')
  if (icA.value === icB.value) return message.warning('两端不能相同')
  icBusy.value = true
  try {
    await api.post('/interconnects', { slot_a_id: icA.value, slot_b_id: icB.value, kind: icKind.value })
    message.success(icKind.value === 'splice' ? '熔接已记录' : '法兰直通已记录')
    icA.value = icB.value = null
    await Promise.all([store.loadBase(), loadIcs()])
  } catch (e: any) {
    message.error(e.response?.data?.detail || '创建失败')
  } finally {
    icBusy.value = false
  }
}

const icCols = computed<DataTableColumns<any>>(() => [
  { title: '#', key: 'id', width: 56, render: (r) => h('span', { class: 'dim mono' }, String(r.id)) },
  { title: '类型', key: 'kind', width: 100, render: (r) => h(StatusTag, { status: r.kind === 'splice' ? 'spliced' : 'reserved' }) },
  { title: 'A 孔位', key: 'a', width: 120, render: (r) => slotLabel(r.slot_a_id) },
  { title: 'B 孔位', key: 'b', width: 120, render: (r) => slotLabel(r.slot_b_id) },
  { title: '备注', key: 'remark', render: (r) => r.remark || h('span', { class: 'dim' }, '—') },
  {
    title: '', key: 'act', width: 70,
    render: (r) => h(NButton, {
      size: 'tiny', quaternary: true, type: 'error',
      onClick: () => dialog.warning({
        title: '删除盘间连接', content: '确认删除该盘间连接记录？',
        positiveText: '删除', negativeText: '取消',
        onPositiveClick: async () => {
          await api.delete(`/interconnects/${r.id}`)
          message.success('已删除')
          await Promise.all([store.loadBase(), loadIcs()])
        },
      }),
    }, { default: () => '删除' }),
  },
])

function slotLabel(slotId: number) {
  const p = store.ports.find(x => x.owner_type === 'odf_slot' && x.owner_id === slotId)
  return p ? p.port_no : `slot#${slotId}`
}

/* ---------- 纤芯熔接 ---------- */
const cables = ref<any[]>([])
const cableA = ref<number | null>(null)
const cableB = ref<number | null>(null)
const coresA = ref<any[]>([])
const coresB = ref<any[]>([])
const selA = ref<Set<number>>(new Set())
const selB = ref<Set<number>>(new Set())
const spliceBusy = ref(false)

/* 映射规则弹窗 */
const ruleShow = ref(false)
const rule = ref<'seq' | 'offset' | 'reverse' | 'manual'>('seq')
const offA = ref(1)
const offB = ref(1)
const pairCount = ref(24)
const manualRows = ref<{ a: number | null; b: number | null }[]>([])
const spliceResult = ref<any>(null)

async function loadCables() {
  cables.value = (await api.get('/cables')).data
}

/* ---------- 快速新建光缆 ---------- */
const cableDlgShow = ref(false)
const cableBusy = ref(false)
const cableForm = ref({
  name: '', core_count: 24, cable_type: 'GYTA 单模',
  direction_from: '', room_id: null as number | null, remark: '',
})

const roomOptions = computed(() => store.rooms.map(r => ({ label: `${r.name}（${r.code}）`, value: r.id })))

function openCableDlg() {
  const next = cables.value.length + 1
  cableForm.value = {
    name: `新光缆-${String(next).padStart(2, '0')}`,
    core_count: 24,
    cable_type: 'GYTA 单模',
    direction_from: '',
    room_id: store.rooms[0]?.id ?? null,
    remark: '',
  }
  cableDlgShow.value = true
}

async function createCable() {
  const f = cableForm.value
  if (!f.name.trim()) return message.warning('请填写光缆名称')
  if (!f.room_id) return message.warning('请选择所属机房')
  if (!f.core_count || f.core_count < 1) return message.warning('芯数至少为 1')
  cableBusy.value = true
  try {
    const r = await api.post('/cables', {
      room_id: f.room_id,
      name: f.name.trim(),
      core_count: Number(f.core_count),
      cable_type: f.cable_type || '',
      direction_from: f.direction_from || '',
      remark: f.remark || '',
    })
    await loadCables()
    const newId = r.data.id as number
    // 自动填入空位的 A/B 槽，并加载纤芯
    if (!cableA.value) {
      cableA.value = newId
    } else if (!cableB.value && newId !== cableA.value) {
      cableB.value = newId
    }
    cableDlgShow.value = false
    message.success(`光缆已创建（${f.core_count} 芯）`)
  } catch (e: any) {
    message.error(e.response?.data?.detail || '创建失败')
  } finally {
    cableBusy.value = false
  }
}

async function loadCores(which: 'a' | 'b') {
  const cid = which === 'a' ? cableA.value : cableB.value
  if (!cid) {
    if (which === 'a') coresA.value = []
    else coresB.value = []
    return
  }
  const r = await api.get('/cores', { params: { cable_id: cid } })
  if (which === 'a') coresA.value = r.data
  else coresB.value = r.data
}

/** 选中光缆后立即加载（含切换） */
watch(cableA, async (v) => {
  selA.value = new Set()
  await loadCores('a')
}, { immediate: false })
watch(cableB, async (v) => {
  selB.value = new Set()
  await loadCores('b')
}, { immediate: false })

function coreColor(c: any) {
  if (c.status === 'fault') return 'var(--c-fault)'
  if (c.status === 'spliced') return 'var(--c-spliced)'
  if (c.status === 'landed') return 'var(--c-landed)'
  if (c.status === 'spare') return 'var(--c-spare)'
  return 'var(--c-unused)'
}

const CORE_STATUS_LABEL: Record<string, string> = {
  unused: '未成端', landed: '已成端', spliced: '已熔接', spare: '备用', fault: '故障',
}

function statOf(list: any[]) {
  const s = { total: list.length, unused: 0, landed: 0, spliced: 0, spare: 0, fault: 0 } as any
  for (const c of list) s[c.status] = (s[c.status] || 0) + 1
  return s
}
const statA = computed(() => statOf(coresA.value))
const statB = computed(() => statOf(coresB.value))

/* ---------- 多选 ---------- */
let lastIdxA = -1
let lastIdxB = -1

function toggleCore(which: 'a' | 'b', idx: number, evt: MouseEvent) {
  const list = which === 'a' ? coresA.value : coresB.value
  const c = list[idx]
  if (!c) return
  if (c.status === 'spliced' || c.peer_core_id) {
    message.warning(`芯 ${c.core_no} 已熔接，不能重复选择`)
    return
  }
  const sel = which === 'a' ? selA : selB
  const last = which === 'a' ? lastIdxA : lastIdxB
  const next = new Set(sel.value)

  if (evt.shiftKey && last >= 0) {
    const [lo, hi] = last < idx ? [last, idx] : [idx, last]
    for (let i = lo; i <= hi; i++) {
      const it = list[i]
      if (it && it.status !== 'spliced' && !it.peer_core_id) next.add(it.id)
    }
  } else if (next.has(c.id)) {
    next.delete(c.id)
  } else {
    next.add(c.id)
  }
  sel.value = next
  if (which === 'a') lastIdxA = idx
  else lastIdxB = idx
}

function selectAllFree(which: 'a' | 'b', mode: 'free' | 'unspliced') {
  const list = which === 'a' ? coresA.value : coresB.value
  const ids = list
    .filter(c => (mode === 'free' ? c.status === 'unused' || c.status === 'spare' : c.status !== 'spliced'))
    .map(c => c.id)
  if (which === 'a') selA.value = new Set(ids)
  else selB.value = new Set(ids)
}

function clearSel(which: 'a' | 'b') {
  if (which === 'a') selA.value = new Set()
  else selB.value = new Set()
}

const selectedA = computed(() => coresA.value.filter(c => selA.value.has(c.id)))
const selectedB = computed(() => coresB.value.filter(c => selB.value.has(c.id)))

/* ---------- 映射规则 ---------- */
/** 按当前规则计算配对表 */
const pairs = computed<{ a: any | null; b: any | null }[]>(() => {
  if (rule.value === 'offset') {
    const n = Math.max(1, pairCount.value)
    const out: { a: any | null; b: any | null }[] = []
    for (let i = 0; i < n; i++) {
      const ca = coresA.value.find(c => c.core_no === offA.value + i)
      const cb = coresB.value.find(c => c.core_no === offB.value + i)
      out.push({ a: ca || null, b: cb || null })
    }
    return out
  }
  if (rule.value === 'manual') {
    return manualRows.value.map(r => ({
      a: coresA.value.find(c => c.id === r.a) || null,
      b: coresB.value.find(c => c.id === r.b) || null,
    }))
  }
  const A = selectedA.value
  const B = [...selectedB.value]
  if (rule.value === 'reverse') B.reverse()
  const n = Math.max(A.length, B.length)
  const out: { a: any | null; b: any | null }[] = []
  for (let i = 0; i < n; i++) out.push({ a: A[i] || null, b: B[i] || null })
  return out
})

/** 可执行的配对（两端都有且未熔接） */
const validPairs = computed(() =>
  pairs.value.filter(p => p.a && p.b && p.a.status !== 'spliced' && p.b.status !== 'spliced'))

const unpairedA = computed(() => pairs.value.filter(p => p.a && !p.b).length)
const unpairedB = computed(() => pairs.value.filter(p => !p.a && p.b).length)

const coreOptsA = computed(() => coresA.value.map(c => ({
  label: `芯 ${c.core_no} · ${CORE_STATUS_LABEL[c.status] || c.status}`,
  value: c.id,
  disabled: c.status === 'spliced',
})))
const coreOptsB = computed(() => coresB.value.map(c => ({
  label: `芯 ${c.core_no} · ${CORE_STATUS_LABEL[c.status] || c.status}`,
  value: c.id,
  disabled: c.status === 'spliced',
})))

function openRule() {
  if (!cableA.value || !cableB.value) return message.warning('请先选择两根光缆')
  spliceResult.value = null
  // 默认：按已选数量决定配对数与手动行
  const n = Math.max(selectedA.value.length, selectedB.value.length, 1)
  pairCount.value = n
  manualRows.value = pairsForManual()
  ruleShow.value = true
}

/** 生成手动模式的初始行（用当前选择） */
function pairsForManual() {
  const A = selectedA.value
  const B = selectedB.value
  const n = Math.max(A.length, B.length)
  const rows = []
  for (let i = 0; i < n; i++) rows.push({ a: A[i]?.id ?? null, b: B[i]?.id ?? null })
  return rows
}

watch(rule, (v) => {
  if (v === 'manual') manualRows.value = pairsForManual()
})

function addManualRow() {
  manualRows.value.push({ a: null, b: null })
}
function removeManualRow(i: number) {
  manualRows.value.splice(i, 1)
}

async function doBatchSplice() {
  const list = validPairs.value
  if (!list.length) return message.warning('没有可执行的配对')
  spliceBusy.value = true
  try {
    const r = await api.post('/cores/batch-splice', {
      pairs: list.map(p => ({ core_a_id: p.a!.id, core_b_id: p.b!.id })),
    })
    spliceResult.value = r.data
    if (r.data.succeeded_count) {
      message.success(`已熔接 ${r.data.succeeded_count} 对`)
    }
    if (r.data.failed_count) {
      message.warning(`${r.data.failed_count} 对失败，见下方明细`)
    }
    selA.value = new Set()
    selB.value = new Set()
    await Promise.all([loadCores('a'), loadCores('b')])
  } catch (e: any) {
    message.error(e.response?.data?.detail || '批量熔接失败')
  } finally {
    spliceBusy.value = false
  }
}

onMounted(async () => {
  if (!store.rooms.length) await store.loadBase()
  await Promise.all([loadCords(), loadIcs(), loadCables()])
})
</script>

<template>
  <div class="wiring">
    <n-tabs v-model:value="tab" type="line" animated>
      <!-- 跳纤 -->
      <n-tab-pane name="cord" tab="跳纤">
        <div class="grid2">
          <section class="panel">
            <div class="panel-head"><Icon name="cable" :size="14" /><span class="grow">新建跳纤</span></div>
            <div class="panel-body form">
              <label>A 端端口</label>
              <n-select v-model:value="cordA" :options="portOptions" filterable clearable
                        placeholder="搜索设备名或端口号" />
              <div class="swap"><span>⇅</span></div>
              <label>B 端端口</label>
              <n-select v-model:value="cordB" :options="portOptions" filterable clearable
                        placeholder="搜索设备名或端口号" />
              <div class="two">
                <div><label>型号</label><n-input v-model:value="cordType" /></div>
                <div><label>长度 (m)</label><n-input-number v-model:value="cordLen" :min="0" style="width:100%" /></div>
              </div>
              <n-button type="primary" block :loading="cordBusy" @click="createCord">
                创建跳纤
              </n-button>
              <p class="tip">仅可选空闲端口；创建后两端端口自动置为「在用」并记入变更历史。</p>
            </div>
          </section>

          <section class="panel">
            <div class="panel-head"><span class="grow">在用跳纤</span><span class="dim">{{ cords.length }} 条</span></div>
            <div class="panel-body no-pad">
              <n-data-table :columns="cordCols" :data="cords" size="small" :bordered="false"
                            :max-height="480" :row-key="(r: any) => r.id">
                <template #empty><n-empty description="暂无在用跳纤" size="small" /></template>
              </n-data-table>
            </div>
          </section>
        </div>
      </n-tab-pane>

      <!-- 盘间连接 -->
      <n-tab-pane name="inter" tab="盘间连接">
        <div class="grid2">
          <section class="panel">
            <div class="panel-head"><Icon name="box" :size="14" /><span class="grow">新建盘间连接</span></div>
            <div class="panel-body form">
              <label>孔位 A</label>
              <n-select v-model:value="icA" :options="slotOptions" filterable clearable placeholder="搜索孔位编址" />
              <label>孔位 B</label>
              <n-select v-model:value="icB" :options="slotOptions" filterable clearable placeholder="搜索孔位编址" />
              <label>连接类型</label>
              <n-select v-model:value="icKind" :options="[
                { label: '法兰直通（适配器）', value: 'adapter' },
                { label: '熔接（splice）', value: 'splice' },
              ]" />
              <n-button type="primary" block :loading="icBusy" @click="createIc">记录盘间连接</n-button>
              <p class="tip">用于 ODF 盘内/盘间的物理连通关系，参与端到端链路计算。</p>
            </div>
          </section>
          <section class="panel">
            <div class="panel-head"><span class="grow">盘间连接记录</span><span class="dim">{{ ics.length }} 条</span></div>
            <div class="panel-body no-pad">
              <n-data-table :columns="icCols" :data="ics" size="small" :bordered="false"
                            :max-height="480" :row-key="(r: any) => r.id">
                <template #empty><n-empty description="暂无盘间连接" size="small" /></template>
              </n-data-table>
            </div>
          </section>
        </div>
      </n-tab-pane>

      <!-- 纤芯熔接 -->
      <n-tab-pane name="core" tab="纤芯熔接">
        <!-- 光缆选择 -->
        <div class="splice-cables">
          <div class="sc-item">
            <span class="sc-tag a">A</span>
            <n-select v-model:value="cableA" :options="cables.map(c => ({ label: `${c.name}（${c.core_count}芯）`, value: c.id }))"
                      filterable clearable size="small" placeholder="选择光缆 A" style="width: 240px" />
          </div>
          <span class="sc-arrow">↔</span>
          <div class="sc-item">
            <span class="sc-tag b">B</span>
            <n-select v-model:value="cableB" :options="cables.map(c => ({ label: `${c.name}（${c.core_count}芯）`, value: c.id }))"
                      filterable clearable size="small" placeholder="选择光缆 B" style="width: 240px" />
          </div>
          <n-button size="small" quaternary @click="openCableDlg">
            <template #icon><Icon name="plus" :size="12" /></template>新建光缆
          </n-button>
          <div class="grow"></div>
          <n-button type="primary" size="small"
                    :disabled="!cableA || !cableB" @click="openRule">
            批量熔接（已选 A{{ selA.size }} / B{{ selB.size }}）
          </n-button>
        </div>

        <!-- 双侧纤芯网格 -->
        <div class="splice-grid2">
          <section class="panel core-panel">
            <div class="panel-head">
              <span class="grow">
                {{ cables.find(c => c.id === cableA)?.name || '光缆 A' }}
              </span>
              <span v-if="coresA.length" class="core-stat">
                <i style="background: var(--c-landed)"></i>成端 {{ statA.landed }}
                <i style="background: var(--c-spliced)"></i>熔接 {{ statA.spliced }}
                <i style="background: var(--c-unused)"></i>未用 {{ statA.unused }}
                <i v-if="statA.fault" style="background: var(--c-fault)"></i>
                <span v-if="statA.fault">{{ statA.fault }}</span>
              </span>
            </div>
            <div class="core-tools">
              <button class="mini" @click="selectAllFree('a', 'free')">全选空闲</button>
              <button class="mini" @click="selectAllFree('a', 'unspliced')">全选未熔接</button>
              <button class="mini" @click="clearSel('a')">清空</button>
              <span class="sel-count">已选 {{ selA.size }}</span>
            </div>
            <div class="panel-body core-body">
              <div v-if="!cableA" class="dim empty">请选择光缆 A</div>
              <div v-else class="core-grid">
                <button v-for="(c, i) in coresA" :key="c.id"
                        class="core-chip"
                        :class="{ sel: selA.has(c.id), spliced: c.status === 'spliced' }"
                        :style="{ '--cc': coreColor(c) }"
                        :title="`芯 ${c.core_no} · ${CORE_STATUS_LABEL[c.status] || c.status}`"
                        @click="toggleCore('a', i, $event)">
                  {{ c.core_no }}
                </button>
              </div>
            </div>
          </section>

          <section class="panel core-panel">
            <div class="panel-head">
              <span class="grow">
                {{ cables.find(c => c.id === cableB)?.name || '光缆 B' }}
              </span>
              <span v-if="coresB.length" class="core-stat">
                <i style="background: var(--c-landed)"></i>成端 {{ statB.landed }}
                <i style="background: var(--c-spliced)"></i>熔接 {{ statB.spliced }}
                <i style="background: var(--c-unused)"></i>未用 {{ statB.unused }}
                <i v-if="statB.fault" style="background: var(--c-fault)"></i>
                <span v-if="statB.fault">{{ statB.fault }}</span>
              </span>
            </div>
            <div class="core-tools">
              <button class="mini" @click="selectAllFree('b', 'free')">全选空闲</button>
              <button class="mini" @click="selectAllFree('b', 'unspliced')">全选未熔接</button>
              <button class="mini" @click="clearSel('b')">清空</button>
              <span class="sel-count">已选 {{ selB.size }}</span>
            </div>
            <div class="panel-body core-body">
              <div v-if="!cableB" class="dim empty">请选择光缆 B</div>
              <div v-else class="core-grid">
                <button v-for="(c, i) in coresB" :key="c.id"
                        class="core-chip"
                        :class="{ sel: selB.has(c.id), spliced: c.status === 'spliced' }"
                        :style="{ '--cc': coreColor(c) }"
                        :title="`芯 ${c.core_no} · ${CORE_STATUS_LABEL[c.status] || c.status}`"
                        @click="toggleCore('b', i, $event)">
                  {{ c.core_no }}
                </button>
              </div>
            </div>
          </section>
        </div>

        <p class="splice-tip">
          单击选中 / 再次单击取消，Shift + 单击可连选范围；已熔接的芯不可选。
          选好后点右上「批量熔接」定义映射规则。
        </p>

        <!-- 新建光缆 -->
        <n-modal v-model:show="cableDlgShow">
          <div class="cable-modal">
            <header class="cm-head">
              <span>新建光缆</span>
              <span class="cm-x" @click="cableDlgShow = false">✕</span>
            </header>
            <div class="cm-body">
              <div class="cm-row">
                <label>光缆名称</label>
                <n-input v-model:value="cableForm.name" size="small" placeholder="如 进局光缆-03" />
              </div>
              <div class="cm-row2">
                <div>
                  <label>芯数</label>
                  <n-input-number v-model:value="cableForm.core_count" size="small"
                                  :min="1" :max="288" style="width: 100%" />
                </div>
                <div>
                  <label>所属机房</label>
                  <n-select v-model:value="cableForm.room_id" :options="roomOptions"
                            size="small" placeholder="选择机房" />
                </div>
              </div>
              <div class="cm-row2">
                <div>
                  <label>型号</label>
                  <n-input v-model:value="cableForm.cable_type" size="small" placeholder="如 GYTA 单模" />
                </div>
                <div>
                  <label>来向</label>
                  <n-input v-model:value="cableForm.direction_from" size="small" placeholder="如 东侧管道" />
                </div>
              </div>
              <div class="cm-row">
                <label>备注</label>
                <n-input v-model:value="cableForm.remark" size="small" placeholder="选填" />
              </div>
              <p class="cm-tip">
                创建后会自动加入上方光缆下拉，芯数决定生成的纤芯数量（后续可成端/熔接）。
              </p>
            </div>
            <footer class="cm-foot">
              <n-button quaternary size="small" @click="cableDlgShow = false">取消</n-button>
              <n-button type="primary" size="small" :loading="cableBusy" @click="createCable">
                创建
              </n-button>
            </footer>
          </div>
        </n-modal>

        <!-- 映射规则弹窗 -->
        <n-modal v-model:show="ruleShow">
          <div class="rule-modal">
            <header class="rm-head">
              <span>批量熔接 · 映射规则</span>
              <span class="rm-x" @click="ruleShow = false">✕</span>
            </header>

            <div class="rm-body">
              <div class="rm-rule">
                <label>配对规则</label>
                <n-select v-model:value="rule" size="small" :options="[
                  { label: '顺序对应（选中列表依次配对）', value: 'seq' },
                  { label: '起始偏移（按芯号起点自动取 N 对）', value: 'offset' },
                  { label: '反向对应（A 正序 ↔ B 倒序）', value: 'reverse' },
                  { label: '手动逐行指定', value: 'manual' },
                ]" style="width: 320px" />

                <template v-if="rule === 'offset'">
                  <span class="rm-inline">
                    A 从芯
                    <n-input-number v-model:value="offA" size="small" :min="1" style="width: 76px" />
                    B 从芯
                    <n-input-number v-model:value="offB" size="small" :min="1" style="width: 76px" />
                    对数量
                    <n-input-number v-model:value="pairCount" size="small" :min="1" style="width: 76px" />
                  </span>
                </template>
              </div>

              <div class="rm-summary">
                可执行 <b>{{ validPairs.length }}</b> 对
                <span v-if="unpairedA" class="rm-warn">· A 侧剩余 {{ unpairedA }} 芯未配对</span>
                <span v-if="unpairedB" class="rm-warn">· B 侧剩余 {{ unpairedB }} 芯未配对</span>
              </div>

              <div class="rm-table">
                <div class="rm-th">
                  <span>#</span><span>A 端纤芯</span><span>B 端纤芯</span>
                  <span v-if="rule === 'manual'"></span>
                </div>
                <div v-for="(p, i) in pairs" :key="i" class="rm-tr">
                  <span class="rm-idx">{{ i + 1 }}</span>
                  <template v-if="rule === 'manual'">
                    <n-select v-model:value="manualRows[i].a" :options="coreOptsA" size="tiny"
                              filterable clearable placeholder="选 A 芯" />
                    <n-select v-model:value="manualRows[i].b" :options="coreOptsB" size="tiny"
                              filterable clearable placeholder="选 B 芯" />
                    <button class="rm-del" @click="removeManualRow(i)">✕</button>
                  </template>
                  <template v-else>
                    <span class="rm-core" :style="{ color: p.a ? coreColor(p.a) : 'var(--text-3)' }">
                      {{ p.a ? `芯 ${p.a.core_no}` : '—' }}
                    </span>
                    <span class="rm-core" :style="{ color: p.b ? coreColor(p.b) : 'var(--text-3)' }">
                      {{ p.b ? `芯 ${p.b.core_no}` : '—' }}
                    </span>
                    <span class="rm-ok" v-if="p.a && p.b">✓</span>
                    <span class="rm-miss" v-else>未配对</span>
                  </template>
                </div>
                <button v-if="rule === 'manual'" class="rm-add" @click="addManualRow">
                  + 添加一行
                </button>
              </div>

              <div v-if="spliceResult" class="rm-result">
                <div class="r-ok">成功 {{ spliceResult.succeeded_count }} 对</div>
                <div v-if="spliceResult.failed_count" class="r-fail">
                  失败 {{ spliceResult.failed_count }} 对：
                  <div v-for="(f, i) in spliceResult.failed" :key="i" class="r-fail-row">
                    芯 {{ f.a }} ↔ 芯 {{ f.b }}：{{ f.reason }}
                  </div>
                </div>
              </div>
            </div>

            <footer class="rm-foot">
              <n-button quaternary @click="ruleShow = false">关闭</n-button>
              <n-button type="primary" :loading="spliceBusy"
                        :disabled="!validPairs.length" @click="doBatchSplice">
                执行熔接（{{ validPairs.length }} 对）
              </n-button>
            </footer>
          </div>
        </n-modal>
      </n-tab-pane>
    </n-tabs>

    <CordHistoryDrawer v-model:cord-id="historyCordId" @changed="loadCords" />
  </div>
</template>

<style scoped>
.wiring { height: 100%; }
.grid2 { display: grid; grid-template-columns: 380px 1fr; gap: 14px; align-items: start; }
.panel { min-height: 0; }
.panel-body.no-pad { padding: 0; }
.form { display: flex; flex-direction: column; gap: 6px; }
.form label { font-size: 11.5px; color: var(--text-2); margin-top: 8px; }
.form label:first-child { margin-top: 0; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 4px; }
.two > div { display: flex; flex-direction: column; gap: 6px; }
.swap { text-align: center; color: var(--text-3); font-size: 15px; margin: 2px 0; }
.splice-line { text-align: center; color: var(--c-inter); font-size: 12px; margin: 10px 0; }
.tip { font-size: 11px; color: var(--text-3); margin: 12px 0 0; line-height: 1.6; }
.empty-hint { color: var(--text-3); font-size: 12px; text-align: center; padding: 30px 0; }
.core-lists { display: flex; flex-direction: column; gap: 16px; }
.cl-title { font-size: 12.5px; font-weight: 600; margin-bottom: 8px; }
.chips { display: flex; flex-wrap: wrap; gap: 5px; }
.chip {
  width: 30px; height: 24px; display: grid; place-items: center;
  border: 1px solid var(--border); border-radius: 5px;
  font-size: 11px; color: var(--text-2); background: var(--bg-elevated);
}

/* ---------- 纤芯熔接 ---------- */
.splice-cables {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 10px 14px; margin-bottom: 12px;
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius);
}
.sc-item { display: flex; align-items: center; gap: 8px; }
.sc-tag {
  font-size: 10px; font-weight: 700; width: 18px; height: 18px; flex: none;
  display: grid; place-items: center; border-radius: 4px;
}
.sc-tag.a { background: rgba(34,197,94,.18); color: var(--c-used); }
.sc-tag.b { background: rgba(59,130,246,.18); color: var(--c-reserved); }
.sc-arrow { color: var(--text-3); font-size: 14px; }

.splice-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.core-panel { display: flex; flex-direction: column; min-height: 0; }
.core-stat {
  display: flex; align-items: center; gap: 5px; font-size: 10.5px; color: var(--text-3);
}
.core-stat i { width: 7px; height: 7px; border-radius: 2px; display: inline-block; margin-left: 6px; }
.core-tools {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 14px; border-bottom: 1px solid var(--border);
}
.mini {
  font-size: 10.5px; padding: 2px 8px; cursor: pointer;
  background: var(--bg-elevated); border: 1px solid var(--border);
  border-radius: 5px; color: var(--text-2);
}
.mini:hover { border-color: var(--border-strong); color: var(--text-1); }
.sel-count { margin-left: auto; font-size: 10.5px; color: var(--accent); font-family: monospace; }

.core-body { max-height: 420px; overflow: auto; }
.core-grid { display: flex; flex-wrap: wrap; gap: 5px; }
.core-chip {
  width: 30px; height: 26px; border-radius: 5px; cursor: pointer;
  font-size: 10.5px; font-family: monospace;
  color: var(--cc); background: color-mix(in srgb, var(--cc) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--cc) 45%, transparent);
  transition: .12s;
}
.core-chip:hover { transform: translateY(-1px); }
.core-chip.spliced { opacity: .55; cursor: not-allowed; }
.core-chip.sel {
  outline: 2px solid var(--accent); outline-offset: 1px;
  background: color-mix(in srgb, var(--cc) 28%, transparent);
}
.splice-tip {
  font-size: 11px; color: var(--text-3); margin: 10px 0 0; line-height: 1.7;
}

/* 新建光缆弹窗 */
.cable-modal {
  width: 460px; max-width: 92vw; background: var(--bg-panel);
  border: 1px solid var(--border-strong); border-radius: 12px;
  box-shadow: var(--shadow-2); overflow: hidden;
}
.cm-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 13px 18px; border-bottom: 1px solid var(--border);
  font-size: 14px; font-weight: 600;
}
.cm-x { cursor: pointer; color: var(--text-3); font-size: 13px; }
.cm-body { padding: 16px 18px; display: flex; flex-direction: column; gap: 11px; }
.cm-row label, .cm-row2 label { display: block; font-size: 11px; color: var(--text-2); margin-bottom: 4px; }
.cm-row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.cm-tip { font-size: 10.5px; color: var(--text-3); margin: 2px 0 0; line-height: 1.6; }
.cm-foot {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 11px 18px; border-top: 1px solid var(--border);
}

/* 规则弹窗 */
.rule-modal {
  width: 720px; max-width: 94vw; max-height: 84vh; display: flex; flex-direction: column;
  background: var(--bg-panel); border: 1px solid var(--border-strong);
  border-radius: 14px; box-shadow: var(--shadow-2); overflow: hidden;
}
.rm-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px; border-bottom: 1px solid var(--border);
  font-size: 14.5px; font-weight: 600;
}
.rm-x { cursor: pointer; color: var(--text-3); font-size: 14px; }
.rm-body { padding: 16px 20px; overflow: auto; }
.rm-rule { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.rm-rule label { font-size: 11.5px; color: var(--text-2); }
.rm-inline { display: flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--text-2); }
.rm-summary {
  margin: 12px 0 8px; font-size: 12px; color: var(--text-2);
  padding: 8px 12px; background: var(--bg-elevated); border-radius: 7px;
}
.rm-summary b { color: var(--accent); }
.rm-warn { color: var(--warn); }
.rm-table { max-height: 320px; overflow: auto; border: 1px solid var(--border); border-radius: 8px; }
.rm-th, .rm-tr {
  display: grid; grid-template-columns: 42px 1fr 1fr 60px;
  align-items: center; gap: 8px; padding: 6px 12px; font-size: 11.5px;
}
.rm-th { background: var(--bg-elevated); color: var(--text-3); position: sticky; top: 0; }
.rm-tr { border-top: 1px solid var(--border); }
.rm-idx { color: var(--text-3); font-family: monospace; }
.rm-core { font-family: monospace; }
.rm-ok { color: var(--c-used); text-align: center; }
.rm-miss { color: var(--text-3); text-align: center; font-size: 10.5px; }
.rm-del {
  background: none; border: none; color: var(--text-3); cursor: pointer; font-size: 12px;
}
.rm-del:hover { color: var(--c-fault); }
.rm-add {
  width: 100%; padding: 7px; background: none; border: none;
  border-top: 1px dashed var(--border); color: var(--accent);
  font-size: 11.5px; cursor: pointer;
}
.rm-result {
  margin-top: 12px; padding: 10px 14px; border-radius: 8px;
  background: var(--bg-elevated); border: 1px solid var(--border); font-size: 12px;
}
.r-ok { color: var(--c-used); }
.r-fail { color: var(--c-fault); margin-top: 6px; }
.r-fail-row { font-size: 11px; color: var(--text-2); margin-top: 3px; }
.rm-foot {
  display: flex; justify-content: flex-end; gap: 10px; padding: 12px 20px;
  border-top: 1px solid var(--border);
}

/* ============ 响应式 ============ */
@media (max-width: 900px) {
  .grid2 { grid-template-columns: 1fr; }
  .splice-grid2 { grid-template-columns: 1fr; }
  .splice-cables { gap: 8px; }
  .splice-cables .sc-item { flex: 1 1 45%; }
  .splice-cables .sc-item :deep(.n-select) { width: 100% !important; }
  .core-body { max-height: 34vh; }
  .rule-modal { width: 94vw; }
  .rm-th, .rm-tr { grid-template-columns: 30px 1fr 1fr 46px; padding: 6px 8px; }
}
</style>
