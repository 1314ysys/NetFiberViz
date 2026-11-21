<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { NSelect, NButton, NDataTable, NEmpty } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { api } from '../api/client'
import StatusTag from '../components/ui/StatusTag.vue'
import Icon from '../components/ui/Icon.vue'

const logs = ref<any[]>([])
const entityType = ref<string>('')
const limit = ref(300)
const loading = ref(false)

const ENTITY_OPTIONS = [
  { label: '全部对象', value: '' },
  { label: '机房', value: 'room' },
  { label: '机柜', value: 'rack' },
  { label: '设备', value: 'device' },
  { label: '端口', value: 'port' },
  { label: '跳纤', value: 'patch_cord' },
  { label: '盘间连接', value: 'interconnect' },
  { label: '光缆', value: 'cable' },
  { label: '纤芯', value: 'core' },
  { label: 'ODF 配线柜', value: 'odf_cabinet' },
  { label: '单元柜', value: 'odf_unit' },
  { label: '盘', value: 'odf_tray' },
  { label: '链路', value: 'link' },
]

async function load() {
  loading.value = true
  try {
    const params: any = { limit: limit.value }
    if (entityType.value) params.entity_type = entityType.value
    logs.value = (await api.get('/changelog', { params })).data
  } finally {
    loading.value = false
  }
}

function fmtTime(t: string) {
  return t.replace('T', ' ').slice(0, 19)
}

const columns = computed<DataTableColumns<any>>(() => [
  {
    type: 'expand',
    renderExpand: (row: any) => h('div', { class: 'expand' }, [
      h('div', { class: 'ex-col' }, [
        h('div', { class: 'ex-title' }, '变更前'),
        h('pre', { class: 'ex-json' }, row.before ? JSON.stringify(row.before, null, 2) : '—'),
      ]),
      h('div', { class: 'ex-col' }, [
        h('div', { class: 'ex-title' }, '变更后'),
        h('pre', { class: 'ex-json' }, row.after ? JSON.stringify(row.after, null, 2) : '—'),
      ]),
    ]),
  },
  { title: '时间', key: 'ts', width: 170, render: (r) => h('span', { class: 'mono dim' }, fmtTime(r.ts)) },
  { title: '用户', key: 'user_id', width: 80, render: (r) => `#${r.user_id}` },
  { title: '对象', key: 'entity', width: 190,
    render: (r) => h('span', { class: 'mono' }, `${r.entity_type}#${r.entity_id}`) },
  { title: '动作', key: 'action', width: 90, render: (r) => h(StatusTag, { status: r.action }) },
  { title: '备注', key: 'remark', minWidth: 180, render: (r) => r.remark || h('span', { class: 'dim' }, '—') },
])

function exportChanges() { window.open('/fiber/api/v1/export/changes', '_blank') }

onMounted(load)
</script>

<template>
  <div class="chg">
    <section class="panel">
      <div class="panel-head">
        <Icon name="history" :size="14" />
        <span class="grow">操作审计流水</span>
        <n-select v-model:value="entityType" :options="ENTITY_OPTIONS" size="small" style="width: 150px"
                  @update:value="load" />
        <n-button size="small" quaternary @click="load">
          <template #icon><Icon name="refresh" :size="12" /></template>刷新
        </n-button>
        <n-button size="small" quaternary @click="exportChanges">
          <template #icon><Icon name="download" :size="12" /></template>导出
        </n-button>
      </div>
      <div class="panel-body no-pad">
        <n-data-table :columns="columns" :data="logs" :loading="loading" size="small"
                      :bordered="false" :max-height="620" :row-key="(r: any) => r.id">
          <template #empty><n-empty description="暂无变更记录" size="small" /></template>
        </n-data-table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.chg { height: 100%; }
.panel-body.no-pad { padding: 0; }
:deep(.expand) { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 8px 12px 12px; }
:deep(.ex-title) { font-size: 11px; color: var(--text-3); margin-bottom: 5px; }
:deep(.ex-json) {
  margin: 0; padding: 10px 12px; background: var(--bg-app); border: 1px solid var(--border);
  border-radius: 8px; font-size: 11px; color: var(--text-2);
  max-height: 220px; overflow: auto; white-space: pre-wrap; word-break: break-all;
}
</style>
