<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { NSelect, NButton, NDataTable, NEmpty, useMessage } from 'naive-ui'
import type { DataTableColumns, SelectOption } from 'naive-ui'
import { api } from '../api/client'
import { useResourceStore } from '../stores/resource'
import Icon from '../components/ui/Icon.vue'

const message = useMessage()
const store = useResourceStore()

const fromPort = ref<number | null>(null)
const toPort = ref<number | null>(null)
const busy = ref(false)
const result = ref<any>(null)
const links = ref<any[]>([])

const portOptions = computed<SelectOption[]>(() => {
  const groups: SelectOption[] = []
  const byDevice = new Map<number, SelectOption[]>()
  for (const p of store.ports) {
    if (p.owner_type !== 'device') continue
    const d = store.deviceById[p.owner_id]
    if (!d) continue
    if (!byDevice.has(d.id)) byDevice.set(d.id, [])
    byDevice.get(d.id)!.push({ label: p.port_no, value: p.id })
  }
  for (const [did, children] of byDevice) {
    groups.push({ type: 'group', key: `d-${did}`, label: store.deviceById[did].name, children })
  }
  const odf = store.ports.filter(p => p.owner_type === 'odf_slot')
    .map(p => ({ label: p.port_no, value: p.id }))
  if (odf.length) groups.push({ type: 'group', key: 'odf', label: 'ODF 孔位', children: odf })
  return groups
})

async function trace() {
  if (!fromPort.value || !toPort.value) return message.warning('请选择起端与末端')
  busy.value = true
  result.value = null
  try {
    const r = await api.get('/links/trace', { params: { from_port: fromPort.value, to_port: toPort.value } })
    result.value = r.data
  } catch (e: any) {
    message.error(e.response?.data?.detail || '未找到物理路径')
  } finally {
    busy.value = false
  }
}

/** 把 hops 展开成节点序列：A端 → 中间 → Z端 */
const pathNodes = computed(() => {
  if (!result.value) return []
  const nodes: { port: number; label: string }[] = []
  const hops = result.value.hops as any[]
  if (!hops.length) return []
  nodes.push({ port: hops[0].from_port, label: store.portLabel(store.portById[hops[0].from_port]) })
  for (const hp of hops) {
    nodes.push({ port: hp.to_port, label: store.portLabel(store.portById[hp.to_port]) })
  }
  return nodes
})
const pathVias = computed(() => (result.value?.hops || []).map((h: any) => h.via))

const NODE_W = 168
const GAP = 92
const diagramW = computed(() => Math.max(pathNodes.value.length * (NODE_W + GAP) + 40, 640))

async function loadLinks() {
  links.value = (await api.get('/links')).data
}

const linkCols = computed<DataTableColumns<any>>(() => [
  { title: '#', key: 'id', width: 56, render: (r) => h('span', { class: 'dim mono' }, String(r.id)) },
  { title: '名称', key: 'name', minWidth: 160 },
  { title: 'A 端', key: 'a', minWidth: 190, render: (r) => store.portLabel(store.portById[r.a_port_id]) },
  { title: 'Z 端', key: 'z', minWidth: 190, render: (r) => store.portLabel(store.portById[r.z_port_id]) },
])

onMounted(async () => {
  if (!store.rooms.length) await store.loadBase()
  await loadLinks()
})
</script>

<template>
  <div class="links">
    <section class="panel">
      <div class="panel-head"><Icon name="link" :size="14" /><span class="grow">端到端物理路径追踪</span></div>
      <div class="panel-body">
        <div class="trace-bar">
          <div class="field"><label>起端端口</label>
            <n-select v-model:value="fromPort" :options="portOptions" filterable clearable placeholder="搜索设备/端口" />
          </div>
          <span class="arrow">→</span>
          <div class="field"><label>末端端口</label>
            <n-select v-model:value="toPort" :options="portOptions" filterable clearable placeholder="搜索设备/端口" />
          </div>
          <n-button type="primary" :loading="busy" @click="trace">追踪</n-button>
        </div>

        <div v-if="result" class="diagram-wrap">
          <div class="diagram-head">
            <span>路径长度：<b>{{ result.hop_count }}</b> 段</span>
            <span class="dim">{{ pathNodes[0]?.label }} → {{ pathNodes[pathNodes.length - 1]?.label }}</span>
          </div>
          <div class="diagram-scroll">
            <svg :width="diagramW" height="150" :viewBox="`0 0 ${diagramW} 150`">
              <defs>
                <marker id="arr" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                  <path d="M0,0 L8,4 L0,8 z" fill="var(--c-cord)" />
                </marker>
              </defs>
              <g v-for="(n, i) in pathNodes" :key="i">
                <!-- 节点卡片 -->
                <rect :x="20 + i * (NODE_W + GAP)" y="46" :width="NODE_W" height="52" rx="9"
                      :fill="i === 0 ? 'rgba(34,197,94,.12)' : i === pathNodes.length - 1 ? 'rgba(239,68,68,.12)' : 'var(--cv-node)'"
                      :stroke="i === 0 ? 'var(--c-used)' : i === pathNodes.length - 1 ? 'var(--c-fault)' : 'var(--cv-node-stroke)'" />
                <text :x="20 + i * (NODE_W + GAP) + NODE_W / 2" y="70" text-anchor="middle"
                      fill="var(--cv-text)" font-size="11.5">{{ n.label.length > 22 ? n.label.slice(0, 21) + '…' : n.label }}</text>
                <text :x="20 + i * (NODE_W + GAP) + NODE_W / 2" y="87" text-anchor="middle"
                      fill="var(--cv-dim)" font-size="10">
                  {{ i === 0 ? '起端' : i === pathNodes.length - 1 ? '末端' : '中间节点' }}
                </text>
                <!-- 连线 -->
                <g v-if="i < pathNodes.length - 1">
                  <line :x1="20 + i * (NODE_W + GAP) + NODE_W" y1="72"
                        :x2="20 + (i + 1) * (NODE_W + GAP) - 4" y2="72"
                        stroke="var(--c-cord)" stroke-width="1.6" marker-end="url(#arr)" opacity="0.85" />
                  <text :x="20 + i * (NODE_W + GAP) + NODE_W + GAP / 2" y="62" text-anchor="middle"
                        fill="var(--c-cord)" font-size="9.5">{{ pathVias[i] }}</text>
                </g>
              </g>
            </svg>
          </div>
        </div>
        <div v-else class="empty-hint">选择两端端口后点击「追踪」，系统将跨跳纤 / 盘间连接 / 纤芯熔接自动串联路径</div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head"><span class="grow">已保存链路</span><span class="dim">{{ links.length }} 条</span></div>
      <div class="panel-body no-pad">
        <n-data-table :columns="linkCols" :data="links" size="small" :bordered="false"
                      :max-height="360" :row-key="(r: any) => r.id">
          <template #empty><n-empty description="暂无已保存链路" size="small" /></template>
        </n-data-table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.links { display: flex; flex-direction: column; gap: 14px; }
.trace-bar { display: flex; align-items: flex-end; gap: 12px; flex-wrap: wrap; }
.field { display: flex; flex-direction: column; gap: 6px; min-width: 260px; flex: 1; }
.field label { font-size: 11.5px; color: var(--text-2); }
.arrow { color: var(--text-3); padding-bottom: 8px; }
.diagram-wrap { margin-top: 20px; border-top: 1px solid var(--border); padding-top: 16px; }
.diagram-head { display: flex; gap: 16px; align-items: baseline; font-size: 12.5px; margin-bottom: 10px; }
.diagram-head b { color: var(--accent); }
.diagram-scroll { overflow-x: auto; padding-bottom: 6px; }
.empty-hint { color: var(--text-3); font-size: 12px; text-align: center; padding: 28px 0; }
.panel-body.no-pad { padding: 0; }

/* ============ 响应式 ============ */
@media (max-width: 900px) {
  .trace-bar { flex-direction: column; align-items: stretch; }
  .field { min-width: 0; }
  .arrow { display: none; }
}
</style>
