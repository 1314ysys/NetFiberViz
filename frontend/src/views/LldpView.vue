<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { NSteps, NStep, NButton, NDataTable, NResult, useMessage } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { api } from '../api/client'
import Icon from '../components/ui/Icon.vue'

const message = useMessage()

const step = ref(1)
const file = ref<File | null>(null)
const busy = ref(false)
const report = ref<any>(null)
const selected = ref<Set<number>>(new Set())
const applied = ref(0)
const dragOver = ref(false)

function onPick(e: Event) {
  const el = e.target as HTMLInputElement
  file.value = el.files?.[0] || null
}
function onDrop(e: DragEvent) {
  dragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) file.value = f
}

async function parse() {
  if (!file.value) return message.warning('请先选择文件')
  busy.value = true
  try {
    const fd = new FormData()
    fd.append('file', file.value)
    const r = await api.post('/lldp/import', fd)
    report.value = r.data
    selected.value = new Set(r.data.conflict.map((_: any, i: number) => i))
    step.value = 2
  } catch (e: any) {
    message.error(e.response?.data?.detail || '解析失败')
  } finally {
    busy.value = false
  }
}

async function apply() {
  if (!report.value) return
  const items = report.value.conflict.filter((_: any, i: number) => selected.value.has(i))
  if (!items.length) return message.warning('请至少勾选一条待生成跳纤')
  busy.value = true
  try {
    const r = await api.post('/lldp/apply', { conflict: items })
    applied.value = r.data.count
    step.value = 3
    message.success(`已生成 ${r.data.count} 条跳纤`)
  } catch (e: any) {
    message.error(e.response?.data?.detail || '应用失败')
  } finally {
    busy.value = false
  }
}

function reset() {
  step.value = 1; file.value = null; report.value = null
  selected.value = new Set(); applied.value = 0
}

function toggle(i: number) {
  const s = new Set(selected.value)
  s.has(i) ? s.delete(i) : s.add(i)
  selected.value = s
}

const conflictCols = computed<DataTableColumns<any>>(() => [
  {
    title: '', key: 'sel', width: 48,
    render: (_r, i) => h('input', {
      type: 'checkbox',
      checked: selected.value.has(i),
      onChange: () => toggle(i),
      style: 'accent-color:var(--accent);width:14px;height:14px;cursor:pointer',
    }),
  },
  { title: '本端端口', key: 'local_port', minWidth: 160, render: (r) => h('span', { class: 'mono' }, r.local_port) },
  { title: '对端端口', key: 'neighbor_port', minWidth: 160, render: (r) => h('span', { class: 'mono' }, r.neighbor_port) },
  { title: '对端设备', key: 'neighbor_name', minWidth: 140, render: (r) => r.neighbor_name || h('span', { class: 'dim' }, '—') },
])

const missingCols = computed<DataTableColumns<any>>(() => [
  { title: '本端端口', key: 'local_port', minWidth: 150, render: (r) => h('span', { class: 'mono' }, r.local_port) },
  { title: '对端端口', key: 'neighbor_port', minWidth: 150, render: (r) => h('span', { class: 'mono' }, r.neighbor_port) },
  { title: '对端设备', key: 'neighbor_name', width: 130 },
  { title: '原因', key: 'reason', minWidth: 180, render: (r) => h('span', { class: 'err-txt' }, r.reason) },
])
</script>

<template>
  <div class="lldp">
    <section class="panel steps-bar">
      <n-steps :current="step" size="small">
        <n-step title="上传邻居表" description="CSV / TXT / XLSX" />
        <n-step title="匹配预览" description="三类结果确认" />
        <n-step title="应用生成" description="写入跳纤台账" />
      </n-steps>
    </section>

    <!-- 步骤 1 -->
    <section v-if="step === 1" class="panel">
      <div class="panel-head"><Icon name="upload" :size="14" /><span class="grow">选择 LLDP 邻居表文件</span></div>
      <div class="panel-body">
        <label class="drop" :class="{ over: dragOver }"
               @dragover.prevent="dragOver = true" @dragleave="dragOver = false" @drop.prevent="onDrop">
          <input type="file" accept=".csv,.txt,.xlsx" hidden @change="onPick" />
          <Icon name="upload" :size="26" />
          <b>{{ file ? file.name : '点击选择或拖拽文件到此处' }}</b>
          <span class="dim">每行格式：本端端口, 对端端口[, 对端设备名]</span>
        </label>
        <div class="fmt">
          <div class="fmt-title">端口名自动归一化</div>
          <div class="fmt-body">
            <code>Ten-GigabitEthernet1/0/3</code> → <code>XGE1/0/3</code><br />
            <code>GigabitEthernet0/0/5</code> → <code>GE0/0/5</code>
          </div>
        </div>
        <n-button type="primary" block :loading="busy" :disabled="!file" @click="parse">
          解析并预览
        </n-button>
      </div>
    </section>

    <!-- 步骤 2 -->
    <template v-if="step === 2 && report">
      <div class="stats">
        <div class="stat">
          <span class="s-label">总记录</span><b>{{ report.total }}</b>
        </div>
        <div class="stat ok">
          <span class="s-label">已吻合</span><b>{{ report.match.length }}</b>
        </div>
        <div class="stat miss">
          <span class="s-label">端口缺失</span><b>{{ report.missing.length }}</b>
        </div>
        <div class="stat conf">
          <span class="s-label">待生成</span><b>{{ report.conflict.length }}</b>
        </div>
      </div>

      <section v-if="report.conflict.length" class="panel">
        <div class="panel-head">
          <Icon name="cable" :size="14" />
          <span class="grow">可自动生成的跳纤（勾选后应用）</span>
          <n-button size="tiny" quaternary @click="selected = new Set(report.conflict.map((_: any, i: number) => i))">全选</n-button>
          <n-button size="tiny" quaternary @click="selected = new Set()">全不选</n-button>
        </div>
        <div class="panel-body no-pad">
          <n-data-table :columns="conflictCols" :data="report.conflict" size="small"
                        :bordered="false" :max-height="320" />
        </div>
        <div class="panel-foot">
          <span class="dim">已选 {{ selected.size }} / {{ report.conflict.length }}</span>
          <n-button type="primary" :loading="busy" @click="apply">应用所选（生成跳纤）</n-button>
        </div>
      </section>

      <section v-if="report.missing.length" class="panel">
        <div class="panel-head"><Icon name="warn" :size="14" /><span class="grow">端口未匹配</span>
          <span class="dim">需先在资源台账中创建对应端口</span></div>
        <div class="panel-body no-pad">
          <n-data-table :columns="missingCols" :data="report.missing" size="small"
                        :bordered="false" :max-height="260" />
        </div>
      </section>

      <div class="actions">
        <n-button quaternary @click="reset">重新上传</n-button>
      </div>
    </template>

    <!-- 步骤 3 -->
    <section v-if="step === 3" class="panel">
      <div class="panel-body">
        <n-result status="success" title="LLDP 自动布线完成"
                  :description="`已根据邻居表生成 ${applied} 条跳纤，端口状态已同步为「在用」并记入变更历史。`">
          <template #footer>
            <n-button type="primary" @click="reset">继续导入</n-button>
          </template>
        </n-result>
      </div>
    </section>
  </div>
</template>

<style scoped>
.lldp { display: flex; flex-direction: column; gap: 14px; max-width: 1080px; }
.steps-bar { padding: 16px 24px; }
.drop {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  border: 1.5px dashed var(--border-strong); border-radius: var(--radius);
  padding: 34px 20px; cursor: pointer; color: var(--text-2);
  transition: .15s; background: var(--bg-elevated);
}
.drop:hover, .drop.over { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
.drop b { font-size: 13px; color: var(--text-1); }
.fmt { margin: 14px 0; padding: 12px 14px; background: var(--bg-elevated);
  border: 1px solid var(--border); border-radius: var(--radius); }
.fmt-title { font-size: 11.5px; color: var(--text-3); margin-bottom: 6px; }
.fmt-body { font-size: 12px; color: var(--text-2); line-height: 1.9; }
.fmt-body code { background: rgba(56,189,248,.1); color: var(--accent);
  padding: 1px 6px; border-radius: 4px; font-size: 11.5px; }

.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.stat { background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 14px 16px; display: flex; flex-direction: column; gap: 4px; }
.s-label { font-size: 11.5px; color: var(--text-3); }
.stat b { font-size: 24px; font-weight: 600; }
.stat.ok b { color: var(--c-used); }
.stat.miss b { color: var(--c-fault); }
.stat.conf b { color: var(--warn); }

.panel-body.no-pad { padding: 0; }
.panel-foot { display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px; border-top: 1px solid var(--border); }
.actions { display: flex; justify-content: flex-end; }
:deep(.err-txt) { color: var(--c-fault); font-size: 12px; }
</style>
