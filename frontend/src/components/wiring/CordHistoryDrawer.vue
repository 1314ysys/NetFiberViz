<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { NButton, NDrawer, NDrawerContent, NInput, NInputNumber, NSpin, NTimeline, NTimelineItem, useMessage } from 'naive-ui'
import { api } from '../../api/client'
import { useResourceStore } from '../../stores/resource'
import Icon from '../ui/Icon.vue'

const props = defineProps<{ cordId: number | null }>()
const emit = defineEmits<{ (e: 'update:cordId', v: number | null): void; (e: 'changed'): void }>()

const message = useMessage()
const store = useResourceStore()

const show = computed({
  get: () => props.cordId !== null,
  set: (v: boolean) => { if (!v) emit('update:cordId', null) },
})

const loading = ref(false)
const data = ref<any>(null)
const editing = ref(false)
const busy = ref(false)
const form = ref({ cord_type: '', length_m: 0, remark: '' })

const cord = computed(() => data.value?.cord || null)
const timeline = computed(() => data.value?.timeline || [])

async function load() {
  if (!props.cordId) return
  loading.value = true
  try {
    const r = await api.get(`/patch-cords/${props.cordId}/history`)
    data.value = r.data
    form.value = {
      cord_type: r.data.cord.cord_type || '',
      length_m: r.data.cord.length_m || 0,
      remark: r.data.cord.remark || '',
    }
  } catch (e: any) {
    message.error(e.response?.data?.detail || '加载失败')
    emit('update:cordId', null)
  } finally {
    loading.value = false
  }
}

watch(() => props.cordId, (v) => { if (v) { editing.value = false; load() } })

function fmt(ts: string | null | undefined) {
  if (!ts) return '—'
  return ts.replace('T', ' ').slice(0, 19)
}

function relTime(ts: string | null | undefined) {
  if (!ts) return ''
  const d = new Date(ts)
  const diff = (Date.now() - d.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)} 天前`
  return ''
}

const ACTION_LABEL: Record<string, string> = { create: '创建', update: '修改', delete: '删除' }
const FIELD_LABEL: Record<string, string> = {
  cord_type: '型号', length_m: '长度', remark: '备注', status: '状态',
}

async function save() {
  if (!cord.value) return
  busy.value = true
  try {
    await api.put(`/patch-cords/${cord.value.id}`, {
      cord_type: form.value.cord_type,
      length_m: Number(form.value.length_m || 0),
      remark: form.value.remark || '',
    })
    message.success('已保存')
    editing.value = false
    await load()
    emit('changed')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    busy.value = false
  }
}

async function verify() {
  if (!cord.value) return
  busy.value = true
  try {
    await api.post(`/patch-cords/${cord.value.id}/verify`)
    message.success('已标记为已复核')
    await load()
    emit('changed')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '操作失败')
  } finally {
    busy.value = false
  }
}

function diffOf(item: any) {
  const out: string[] = []
  for (const k of item.changed || []) {
    const b = item.before?.[k]
    const a = item.after?.[k]
    if (item.action === 'create') out.push(`${FIELD_LABEL[k] || k}: ${a ?? '—'}`)
    else if (b !== a) out.push(`${FIELD_LABEL[k] || k}: ${b ?? '—'} → ${a ?? '—'}`)
  }
  return out
}
</script>

<template>
  <n-drawer v-model:show="show" :width="480" placement="right">
    <n-drawer-content closable>
      <template #header>
        <div class="dh">
          <Icon name="cable" :size="15" />
          <span>跳纤 #{{ cordId }}</span>
          <span v-if="cord" class="dh-sub">{{ store.portLabel(store.portById[cord.port_a_id]) }} ↔
            {{ store.portLabel(store.portById[cord.port_b_id]) }}</span>
        </div>
      </template>

      <n-spin :show="loading">
        <div v-if="cord" class="body">
          <!-- 时间概览 -->
          <div class="times">
            <div class="t-item">
              <span>创建</span><b>{{ fmt(cord.created_at) }}</b>
            </div>
            <div class="t-item">
              <span>最后更新</span>
              <b>{{ fmt(cord.updated_at) }}<em v-if="relTime(cord.updated_at)"> · {{ relTime(cord.updated_at) }}</em></b>
            </div>
            <div class="t-item">
              <span>现场复核</span>
              <b :class="{ dim: !cord.verified_at }">{{ fmt(cord.verified_at) }}</b>
            </div>
          </div>

          <!-- 属性 / 编辑 -->
          <div class="sec">
            <span class="sec-title">跳纤属性</span>
            <n-button v-if="!editing" size="tiny" quaternary type="primary" @click="editing = true">编辑</n-button>
            <template v-else>
              <n-button size="tiny" quaternary @click="editing = false">取消</n-button>
              <n-button size="tiny" type="primary" :loading="busy" @click="save">保存</n-button>
            </template>
          </div>

          <div v-if="!editing" class="props">
            <div class="p-row"><span>型号</span><b>{{ cord.cord_type || '—' }}</b></div>
            <div class="p-row"><span>长度</span><b>{{ cord.length_m ? cord.length_m + ' m' : '—' }}</b></div>
            <div class="p-row"><span>备注</span><b>{{ cord.remark || '—' }}</b></div>
            <div class="p-row"><span>状态</span><b>{{ cord.status === 'active' ? '在用' : '已拆除' }}</b></div>
          </div>
          <div v-else class="props edit">
            <div class="p-row"><span>型号</span><n-input v-model:value="form.cord_type" size="small" /></div>
            <div class="p-row"><span>长度(m)</span>
              <n-input-number v-model:value="form.length_m" size="small" :min="0" style="width: 100%" />
            </div>
            <div class="p-row"><span>备注</span>
              <n-input v-model:value="form.remark" size="small" type="textarea" :autosize="{ minRows: 2, maxRows: 3 }" />
            </div>
          </div>

          <n-button size="small" secondary block :loading="busy" style="margin-top: 10px" @click="verify">
            <template #icon><Icon name="check" :size="12" /></template>
            标记为已现场复核
          </n-button>

          <!-- 更新记录 -->
          <div class="sec" style="margin-top: 20px">
            <span class="sec-title">更新记录</span>
            <span class="dim">{{ timeline.length }} 条</span>
          </div>

          <div v-if="!timeline.length" class="dim empty">暂无记录</div>
          <n-timeline v-else>
            <n-timeline-item
              v-for="it in timeline"
              :key="it.id"
              :type="it.action === 'create' ? 'success' : 'info'"
              :title="`${ACTION_LABEL[it.action] || it.action} · 用户#${it.user_id}`"
              :time="fmt(it.ts)"
            >
              <div v-if="it.remark" class="tl-remark">{{ it.remark }}</div>
              <div v-for="(d, i) in diffOf(it)" :key="i" class="tl-diff">{{ d }}</div>
            </n-timeline-item>
          </n-timeline>
        </div>
      </n-spin>
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
.dh { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.dh-sub { font-size: 11.5px; color: var(--text-3); font-weight: 400; }
.body { display: flex; flex-direction: column; }

.times {
  display: grid; gap: 6px; padding: 12px 14px; margin-bottom: 14px;
  background: var(--bg-elevated); border: 1px solid var(--border); border-radius: 9px;
}
.t-item { display: flex; justify-content: space-between; gap: 10px; font-size: 12px; }
.t-item span { color: var(--text-3); }
.t-item b { color: var(--text-1); font-weight: 500; font-family: monospace; font-size: 11.5px; }
.t-item em { font-style: normal; color: var(--accent); }

.sec {
  display: flex; align-items: center; gap: 8px; margin-bottom: 10px;
}
.sec-title { font-size: 12.5px; font-weight: 600; color: var(--text-2); flex: none; }
.sec .dim { font-size: 11px; }

.props { display: flex; flex-direction: column; gap: 8px; }
.p-row { display: flex; align-items: center; gap: 10px; font-size: 12px; }
.p-row span { width: 62px; flex: none; color: var(--text-3); }
.p-row b { color: var(--text-1); font-weight: 500; }
.props.edit .p-row { align-items: flex-start; }
.props.edit .p-row > :last-child { flex: 1; }

.empty { font-size: 11.5px; padding: 12px 0; }

:deep(.n-timeline-item-content) { font-size: 12px; }
.tl-remark { color: var(--text-2); font-size: 11.5px; margin-bottom: 3px; }
.tl-diff {
  font-family: monospace; font-size: 11px; color: var(--accent);
  background: var(--accent-soft); border-radius: 4px; padding: 1px 6px;
  display: inline-block; margin: 2px 4px 2px 0;
}
</style>
