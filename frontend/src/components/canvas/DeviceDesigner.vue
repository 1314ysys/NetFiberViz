<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { NButton, NInput, NInputNumber, NSelect, useMessage } from 'naive-ui'
import { api } from '../../api/client'
import { useResourceStore } from '../../stores/resource'
import { portTypeOptions, shapeOf, familyColorOf, FAMILY_COLOR, FALLBACK_PORT_TYPES } from '../../utils/portTypes'
import Icon from '../ui/Icon.vue'
import PortShape from '../canvas/PortShape.vue'

const message = useMessage()
const store = useResourceStore()

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void; (e: 'saved', key: string): void }>()

interface DPort {
  id: string
  no: string
  type: string
  group: string
  groupSeq: number
  x: number
  y: number
}
interface DGroup {
  name: string
  prefix: string
  count: number
  type: string
  dir: 'h' | 'v'
}

const PITCH = 22
const PAD = 12
const PAD_TOP = 26
const PORT_SIZE = 18

const name = ref('')
const category = ref('sw')
const uHeight = ref(1)
const ports = ref<DPort[]>([])
const selected = ref<string | null>(null)
const canvasW = ref(480)
const canvasH = ref(44)
const saving = ref(false)

const groupForm = ref<DGroup>({
  name: 'LC 光口', prefix: 'LC/', count: 12, type: 'LC/UPC', dir: 'h',
})

const portTypes = computed(() => store.portTypes.length ? store.portTypes : FALLBACK_PORT_TYPES)
const typeOptions = computed(() => portTypeOptions(portTypes.value))
const categoryOptions = Object.entries(store.categories).map(([v, l]) => ({ label: l, value: v }))

const currentType = computed(() => (ports.value.find(p => p.id === selected.value) || null))

/* ---------- 布局 ---------- */
function groupSeqOf(name: string): number {
  const names = [...new Set(ports.value.map(p => p.group))]
  return Math.max(names.indexOf(name), 0)
}

/** 批量添加一组端口（自动排布） */
function addGroup() {
  const g = groupForm.value
  if (!g.name || g.count < 1) return message.warning('请填写组名与数量')
  const seq = groupSeqOf(g.name)
  const exists = ports.value.filter(p => p.group === g.name).length

  // 组起点：接在已有端口右侧（横排）或下方（竖排）
  let startX = PAD
  let startY = PAD_TOP
  if (ports.value.length) {
    if (g.dir === 'h') {
      startX = Math.max(...ports.value.map(p => p.x)) + PITCH + 8
    } else {
      startY = Math.max(...ports.value.map(p => p.y)) + PITCH + 4
    }
  }

  for (let i = 0; i < g.count; i++) {
    ports.value.push({
      id: `p${Date.now()}-${i}-${Math.random().toString(36).slice(2, 6)}`,
      no: `${g.prefix}${exists + i + 1}`,
      type: g.type,
      group: g.name,
      groupSeq: seq,
      x: g.dir === 'h' ? startX + i * PITCH : startX,
      y: g.dir === 'h' ? startY : startY + i * PITCH,
    })
  }
  recalcCanvas()
}

function recalcCanvas() {
  if (!ports.value.length) { canvasW.value = 480; canvasH.value = 44; return }
  const maxX = Math.max(...ports.value.map(p => p.x))
  const maxY = Math.max(...ports.value.map(p => p.y))
  canvasW.value = Math.max(160, maxX + PAD + 4)
  canvasH.value = Math.max(32, maxY + PAD)
}

/* ---------- 画布交互 ---------- */
const svgEl = ref<SVGSVGElement>()
const dragging = ref<{ id: string; dx: number; dy: number } | null>(null)

function toCanvas(evt: PointerEvent | MouseEvent) {
  const rect = svgEl.value!.getBoundingClientRect()
  const s = viewScale.value
  return { x: (evt.clientX - rect.left) / s, y: (evt.clientY - rect.top) / s }
}

function onPortDown(evt: PointerEvent, p: DPort) {
  evt.stopPropagation()
  selected.value = p.id
  const pt = toCanvas(evt)
  dragging.value = { id: p.id, dx: pt.x - p.x, dy: pt.y - p.y }
}

function onMove(evt: PointerEvent) {
  if (!dragging.value) return
  const pt = toCanvas(evt)
  const p = ports.value.find(v => v.id === dragging.value!.id)
  if (!p) return
  p.x = Math.max(0, Math.round((pt.x - dragging.value.dx) / 4) * 4)
  p.y = Math.max(PAD_TOP - 8, Math.round((pt.y - dragging.value.dy) / 4) * 4)
  recalcCanvas()
}

function onUp() { dragging.value = null }

/** 点击空白：在当前位置加一个端口（用表单里的类型） */
function onCanvasClick(evt: MouseEvent) {
  if (dragging.value) return
  const pt = toCanvas(evt)
  const g = groupForm.value
  const exists = ports.value.filter(p => p.group === g.name).length
  ports.value.push({
    id: `p${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    no: `${g.prefix}${exists + 1}`,
    type: g.type,
    group: g.name,
    groupSeq: groupSeqOf(g.name),
    x: Math.round(pt.x / 4) * 4,
    y: Math.max(PAD_TOP - 8, Math.round(pt.y / 4) * 4),
  })
  recalcCanvas()
}

function removeSelected() {
  if (!selected.value) return
  ports.value = ports.value.filter(p => p.id !== selected.value)
  selected.value = null
  recalcCanvas()
}

function clearAll() {
  ports.value = []
  selected.value = null
  recalcCanvas()
}

/* ---------- 预览缩放 ---------- */
const viewScale = ref(1)
const wrapW = ref(600)
function fitView(w: number) {
  wrapW.value = w
  viewScale.value = Math.min(1.6, Math.max(0.35, (w - 24) / canvasW.value))
}

/* ---------- 保存 ---------- */
async function save() {
  if (!name.value.trim()) return message.warning('请填写模板名称')
  if (!ports.value.length) return message.warning('请至少添加一个端口')
  if (ports.value.some(p => !p.no.trim())) return message.warning('存在未编号的端口')

  saving.value = true
  try {
    const r = await api.post('/custom-templates', {
      name: name.value.trim(),
      category: category.value,
      device_type: category.value === 'olt' ? 'olt' : 'custom',
      width: Math.round(canvasW.value),
      height: Math.round(canvasH.value),
      u_height: Number(uHeight.value) || 1,
      ports: ports.value.map(p => ({
        no: p.no, type: p.type, group: p.group, group_seq: p.groupSeq,
        x: p.x, y: p.y,
      })),
    })
    message.success('模板已保存')
    await store.loadTemplates(true)
    emit('saved', r.data.key)
    emit('update:show', false)
    reset()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function reset() {
  name.value = ''
  ports.value = []
  selected.value = null
  recalcCanvas()
}

function open() {
  nextTick(() => {
    const el = document.querySelector('.designer-wrap') as HTMLElement
    if (el) fitView(el.clientWidth)
  })
}

const typeColor = computed(() => {
  const t = portTypes.value.find(x => x.key === groupForm.value.type)
  return t ? (FAMILY_COLOR[t.family] || '#64748b') : '#64748b'
})

defineExpose({ open })
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="ds-mask" @pointerdown="emit('update:show', false)">
      <div class="ds" @pointerdown.stop>
        <header class="ds-head">
          <Icon name="grid" :size="15" />
          <span class="title">设备面板设计器</span>
          <input v-model="name" class="tname" placeholder="模板名称，如 华为 24GE+4SFP" />
          <n-select v-model:value="category" :options="categoryOptions" size="small"
                    style="width: 130px" placeholder="类别" />
          <div class="uh">占<input type="number" v-model.number="uHeight" min="1" max="10" class="uh-in" />U</div>
          <div class="grow"></div>
          <n-button size="small" quaternary @click="reset">清空</n-button>
          <n-button size="small" type="primary" :loading="saving" @click="save">保存模板</n-button>
          <button class="x" @click="emit('update:show', false)">✕</button>
        </header>

        <div class="ds-body">
          <!-- 左：端口类型 -->
          <aside class="ds-left">
            <div class="sec">端口类型</div>
            <n-select v-model:value="groupForm.type" :options="typeOptions" size="small" filterable />
            <div class="type-preview">
              <PortShape :shape="shapeOf(portTypes, groupForm.type)" :size="34"
                         fill="var(--bg-elevated)" :stroke="typeColor" />
              <div class="tp-text">
                <b>{{ portTypes.find(t => t.key === groupForm.type)?.label }}</b>
                <span>{{ portTypes.find(t => t.key === groupForm.type)?.familyLabel }}</span>
              </div>
            </div>

            <div class="sec">批量添加</div>
            <label>组名</label>
            <n-input v-model:value="groupForm.name" size="small" placeholder="如 LC 光口" />
            <label>端口前缀</label>
            <n-input v-model:value="groupForm.prefix" size="small" placeholder="如 LC/" />
            <div class="row2">
              <div>
                <label>数量</label>
                <n-input-number v-model:value="groupForm.count" size="small" :min="1" :max="96"
                                style="width: 100%" />
              </div>
              <div>
                <label>排列</label>
                <n-select v-model:value="groupForm.dir" size="small" :options="[
                  { label: '横向', value: 'h' }, { label: '纵向', value: 'v' }]" />
              </div>
            </div>
            <n-button size="small" type="primary" secondary block @click="addGroup">
              + 添加 {{ groupForm.count }} 个
              <span :style="{ color: typeColor }">{{ portTypes.find(t => t.key === groupForm.type)?.label }}</span>
            </n-button>
            <p class="hint">也可直接在右侧画布点击空白处，逐个放置端口</p>
          </aside>

          <!-- 中：画布 -->
          <section class="designer-wrap">
            <div class="canvas-meta">
              面板 {{ Math.round(canvasW) }} × {{ Math.round(canvasH) }} ·
              {{ ports.length }} 端口
              <span v-if="selected">· 已选 {{ currentType?.no }}</span>
            </div>
            <div class="canvas-scroll">
              <svg ref="svgEl" :width="canvasW * viewScale" :height="canvasH * viewScale"
                   :viewBox="`0 0 ${canvasW} ${canvasH}`"
                   class="ds-canvas"
                   @pointermove="onMove" @pointerup="onUp" @pointerleave="onUp"
                   @click="onCanvasClick">
                <defs>
                  <pattern :id="'dgrid'" width="8" height="8" patternUnits="userSpaceOnUse">
                    <path d="M 8 0 L 0 0 0 8" fill="none" stroke="var(--cv-grid)" stroke-width="0.4" />
                  </pattern>
                </defs>
                <rect :width="canvasW" :height="canvasH" fill="var(--cv-bg)" />
                <rect :width="canvasW" :height="canvasH" fill="url(#dgrid)" />

                <!-- 设备外框 -->
                <rect x="2" y="14" :width="canvasW - 4" :height="canvasH - 18" rx="4"
                      fill="var(--cv-node)" stroke="var(--cv-node-stroke)" stroke-width="1" />

                <!-- 端口块 -->
                <g v-for="p in ports" :key="p.id"
                   :transform="`translate(${p.x} ${p.y})`"
                   class="dport" :class="{ sel: selected === p.id }"
                   @pointerdown="onPortDown($event, p)">
                  <PortShape :shape="shapeOf(portTypes, p.type)" :size="PORT_SIZE"
                             :fill="selected === p.id ? 'var(--accent)' : 'var(--bg-elevated)'"
                             :stroke="familyColorOf(portTypes, p.type)" />
                  <text v-if="ports.length <= 40" :x="PORT_SIZE / 2" :y="PORT_SIZE + 5"
                        text-anchor="middle" fill="var(--cv-dim)" font-size="5">
                    {{ p.no.replace(/^[A-Za-z]+\/?[0-9/]*\//, '') }}
                  </text>
                </g>

                <text v-if="!ports.length" :x="canvasW / 2" :y="canvasH / 2 + 2"
                      text-anchor="middle" fill="var(--cv-dim)" font-size="7">
                  在左侧「批量添加」或点击此处放置端口
                </text>
              </svg>
            </div>
            <div class="canvas-ops">
              <n-button size="tiny" quaternary :disabled="!selected" @click="removeSelected">
                删除选中
              </n-button>
              <n-button size="tiny" quaternary @click="clearAll">清空端口</n-button>
            </div>
          </section>

          <!-- 右：选中属性 -->
          <aside class="ds-right">
            <div class="sec">属性</div>
            <template v-if="currentType">
              <label>端口编号</label>
              <n-input v-model:value="currentType.no" size="small" />
              <label>端口类型</label>
              <n-select v-model:value="currentType.type" :options="typeOptions" size="small" filterable />
              <label>所属组</label>
              <n-input v-model:value="currentType.group" size="small" />
              <label>组序</label>
              <n-input-number v-model:value="currentType.groupSeq" size="small" :min="0"
                              style="width: 100%" />
            </template>
            <div v-else class="empty">点击画布上的端口以编辑属性</div>

            <div class="sec" style="margin-top: 16px">已添加的组</div>
            <div class="glist">
              <div v-for="g in [...new Set(ports.map(p => p.group))]" :key="g" class="gitem">
                <span class="gi-name">{{ g }}</span>
                <span class="gi-count">{{ ports.filter(p => p.group === g).length }} 口</span>
              </div>
              <div v-if="!ports.length" class="empty">暂无</div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ds-mask {
  position: fixed; inset: 0; z-index: 5200; background: rgba(0,0,0,.5);
  backdrop-filter: blur(2px); display: flex; align-items: center; justify-content: center;
}
.ds {
  width: 1120px; max-width: 96vw; height: 76vh; display: flex; flex-direction: column;
  background: var(--bg-panel); border: 1px solid var(--border-strong);
  border-radius: 12px; box-shadow: var(--shadow-2); overflow: hidden;
}
.ds-head {
  display: flex; align-items: center; gap: 10px; padding: 10px 14px;
  border-bottom: 1px solid var(--border); flex: none;
}
.title { font-size: 13.5px; font-weight: 600; }
.tname {
  width: 240px; padding: 5px 10px; font-size: 12px;
  background: var(--bg-elevated); color: var(--text-1);
  border: 1px solid var(--border); border-radius: 7px; outline: none;
}
.tname:focus { border-color: var(--accent); }
.uh { display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--text-2); }
.uh-in {
  width: 44px; padding: 4px 6px; font-size: 12px; text-align: center;
  background: var(--bg-elevated); color: var(--text-1);
  border: 1px solid var(--border); border-radius: 6px; outline: none;
}
.grow { flex: 1; }
.x { background: none; border: none; color: var(--text-3); cursor: pointer; font-size: 14px; }

.ds-body { flex: 1; display: grid; grid-template-columns: 210px 1fr 210px; min-height: 0; }
.ds-left, .ds-right { padding: 12px; overflow: auto; }
.ds-left { border-right: 1px solid var(--border); display: flex; flex-direction: column; gap: 6px; }
.ds-right { border-left: 1px solid var(--border); display: flex; flex-direction: column; gap: 6px; }
.sec { font-size: 10.5px; color: var(--text-3); letter-spacing: .5px;
  margin: 8px 0 4px; text-transform: uppercase; }
.sec:first-child { margin-top: 0; }
label { font-size: 11px; color: var(--text-2); margin-top: 4px; }
.row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.hint { font-size: 10.5px; color: var(--text-3); line-height: 1.6; margin: 6px 0 0; }
.type-preview { display: flex; align-items: center; gap: 10px; padding: 8px 0; }
.tp-text { display: flex; flex-direction: column; line-height: 1.3; }
.tp-text b { font-size: 12px; color: var(--text-1); }
.tp-text span { font-size: 10.5px; color: var(--text-3); }

.designer-wrap { display: flex; flex-direction: column; min-width: 0; padding: 10px 12px; }
.canvas-meta { font-size: 11px; color: var(--text-3); margin-bottom: 6px; }
.canvas-scroll { flex: 1; overflow: auto; min-height: 0;
  border: 1px solid var(--border); border-radius: 8px; }
.ds-canvas { display: block; cursor: crosshair; }
.dport { cursor: move; }
.dport.sel { filter: drop-shadow(0 0 3px var(--accent)); }
.canvas-ops { display: flex; gap: 8px; margin-top: 8px; }

.empty { font-size: 11px; color: var(--text-3); padding: 8px 0; }
.glist { display: flex; flex-direction: column; gap: 3px; }
.gitem { display: flex; justify-content: space-between; font-size: 11px;
  padding: 4px 7px; border-radius: 5px; background: var(--bg-elevated); }
.gi-name { color: var(--text-2); }
.gi-count { color: var(--text-3); font-family: monospace; }
</style>
