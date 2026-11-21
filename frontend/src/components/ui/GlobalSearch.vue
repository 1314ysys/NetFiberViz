<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api/client'
import { useResourceStore } from '../../stores/resource'
import Icon from './Icon.vue'

const router = useRouter()
const store = useResourceStore()

const show = ref(false)
const kw = ref('')
const inputEl = ref<HTMLInputElement>()
const active = ref(0)

interface Hit {
  kind: 'room' | 'rack' | 'device' | 'cabinet' | 'port' | 'cord'
  label: string
  sub: string
  to: string
}
const hits = ref<Hit[]>([])
const cords = ref<any[]>([])
const searching = ref(false)

const KIND_LABEL: Record<string, string> = {
  room: '机房', rack: '机柜', device: '设备', cabinet: '配线柜', port: '端口', cord: '连接',
}

/** 首次打开时拉一次连线数据（端口/连接搜索需要） */
async function ensureCords() {
  if (cords.value.length) return
  try { cords.value = (await api.get('/patch-cords')).data } catch { cords.value = [] }
}

const GROUPS = ['机房', '机柜', '设备', '配线柜', '端口', '连接']

function search(q: string): Hit[] {
  const k = q.trim().toLowerCase()
  if (!k) return []
  const out: Hit[] = []

  for (const r of store.rooms) {
    if (r.name.toLowerCase().includes(k) || r.code.toLowerCase().includes(k)) {
      out.push({ kind: 'room', label: r.name, sub: r.code, to: `/topology/${r.id}` })
    }
  }
  for (const rk of store.racks) {
    if (rk.name.toLowerCase().includes(k) || rk.code.toLowerCase().includes(k)) {
      const room = store.rooms.find(r => r.id === rk.room_id)
      out.push({ kind: 'rack', label: rk.name, sub: `${room?.name || ''} · ${rk.code}`, to: `/interior/rack/${rk.id}` })
    }
  }
  for (const d of store.devices) {
    const hay = `${d.name} ${d.model || ''} ${d.mgmt_ip || ''}`.toLowerCase()
    if (hay.includes(k)) {
      const rk = store.racks.find(r => r.id === d.rack_id)
      out.push({ kind: 'device', label: d.name, sub: `${rk?.name || ''} · ${d.model || ''}`, to: `/ports/device/${d.id}` })
    }
  }
  for (const c of store.cabinets) {
    if (c.name.toLowerCase().includes(k) || c.code.toLowerCase().includes(k)) {
      out.push({ kind: 'cabinet', label: c.name, sub: c.code, to: `/interior/odf/${c.id}` })
    }
  }
  // 端口：编号 / 备注 / 标签 + 所属设备名
  for (const p of store.ports) {
    const owner = store.deviceById[p.owner_id]
    const ownerName = p.owner_type === 'device' ? (owner?.name || '') : ''
    const hay = `${p.port_no} ${p.label || ''} ${p.remark || ''} ${ownerName}`.toLowerCase()
    if (!hay.includes(k)) continue
    if (p.owner_type === 'device') {
      out.push({
        kind: 'port', label: p.port_no,
        sub: `${ownerName} · ${p.status}`,
        to: `/ports/device/${p.owner_id}?port=${p.id}`,
      })
    } else {
      out.push({
        kind: 'port', label: p.port_no,
        sub: `ODF 孔位 · ${p.status}`,
        to: `/ports/tray/${p.owner_id}?port=${p.id}`,
      })
    }
  }
  // 连接：A端/B端/型号/备注/ID
  for (const c of cords.value) {
    const a = store.portLabel(store.portById[c.port_a_id])
    const b = store.portLabel(store.portById[c.port_b_id])
    const hay = `${a} ${b} ${c.cord_type || ''} ${c.remark || ''} #${c.id}`.toLowerCase()
    if (!hay.includes(k)) continue
    out.push({
      kind: 'cord', label: `#${c.id}  ${a} ↔ ${b}`,
      sub: [c.cord_type, c.remark].filter(Boolean).join(' · '),
      to: `/ports/device/${store.portById[c.port_a_id]?.owner_id || 0}?port=${c.port_a_id}`,
    })
  }
  return out
}

watch(kw, (v) => {
  active.value = 0
  hits.value = search(v)
})

const grouped = computed(() => {
  const m = new Map<string, Hit[]>()
  for (const h of hits.value) {
    const g = KIND_LABEL[h.kind] || '其他'
    if (!m.has(g)) m.set(g, [])
    m.get(g)!.push(h)
  }
  return [...m.entries()]
})

const flat = computed(() => grouped.value.flatMap(([, items]) => items))

function open() {
  show.value = true
  ensureCords()
  nextTick(() => inputEl.value?.focus())
}

function close() {
  show.value = false
  kw.value = ''
  hits.value = []
}

function go(h?: Hit) {
  const target = h || flat.value[active.value]
  if (!target) return
  close()
  router.push(target.to)
}

function onKey(e: KeyboardEvent) {
  if (!show.value) return
  if (e.key === 'Escape') return close()
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    active.value = Math.min(active.value + 1, flat.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    active.value = Math.max(active.value - 1, 0)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    go()
  }
}

function globalKey(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    show.value ? close() : open()
  }
}

onMounted(() => window.addEventListener('keydown', globalKey))
onBeforeUnmount(() => window.removeEventListener('keydown', globalKey))
</script>

<template>
  <!-- 顶栏触发按钮 -->
  <button class="search-trigger" title="搜索（Ctrl+K）" @click="open">
    <Icon name="search" :size="13" />
    <span class="ph">搜索端口 / 连接…</span>
    <kbd>Ctrl K</kbd>
  </button>

  <Teleport to="body">
    <div v-if="show" class="ss-mask" @pointerdown="close">
      <div class="ss" @pointerdown.stop>
        <div class="ss-input">
          <Icon name="search" :size="15" />
          <input ref="inputEl" v-model="kw" placeholder="搜索机房 / 机柜 / 设备 / 端口 / 连接…"
                 @keydown="onKey" />
          <button class="ss-esc" @click="close">ESC</button>
        </div>

        <div class="ss-body">
          <div v-if="!kw.trim()" class="ss-hint">
            <div class="hint-title">可搜索</div>
            <div class="hint-grid">
              <span>机房名 / 编码</span><span>机柜名 / 编码</span>
              <span>设备名 / 型号 / IP</span><span>端口编号 / 标签 / 备注</span>
              <span>跳纤两端端口 / 型号</span><span>配线柜名 / 编码</span>
            </div>
          </div>

          <div v-else-if="!hits.length" class="ss-empty">没有匹配结果</div>

          <template v-else>
            <div v-for="[group, items] in grouped" :key="group" class="ss-group">
              <div class="g-name">{{ group }} <span class="g-count">{{ items.length }}</span></div>
              <button v-for="h in items" :key="h.kind + h.to + h.label"
                      class="ss-item" :class="{ active: flat[active] === h }"
                      @click="go(h)" @mouseenter="active = flat.indexOf(h)">
                <span class="it-label">{{ h.label }}</span>
                <span class="it-sub">{{ h.sub }}</span>
              </button>
            </div>
          </template>
        </div>

        <div class="ss-foot">
          <span>↑↓ 选择</span><span>Enter 打开</span><span>Esc 关闭</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.search-trigger {
  display: flex; align-items: center; gap: 7px; height: 30px; padding: 0 10px;
  background: var(--bg-elevated); border: 1px solid var(--border); border-radius: 8px;
  color: var(--text-3); font-size: 12px; cursor: pointer; transition: .12s; min-width: 210px;
}
.search-trigger:hover { border-color: var(--border-strong); color: var(--text-2); }
.ph { flex: 1; text-align: left; }
kbd {
  font-size: 9.5px; padding: 1px 5px; border-radius: 4px;
  background: var(--bg-panel); border: 1px solid var(--border); color: var(--text-3);
}

.ss-mask {
  position: fixed; inset: 0; z-index: 5000; background: rgba(0, 0, 0, .45);
  backdrop-filter: blur(2px); display: flex; justify-content: center; padding-top: 12vh;
}
.ss {
  width: 620px; max-width: 92vw; max-height: 66vh; display: flex; flex-direction: column;
  background: var(--bg-panel); border: 1px solid var(--border-strong);
  border-radius: 12px; box-shadow: var(--shadow-2); overflow: hidden;
}
.ss-input {
  display: flex; align-items: center; gap: 10px; padding: 12px 16px;
  border-bottom: 1px solid var(--border); color: var(--text-3);
}
.ss-input input {
  flex: 1; background: transparent; border: none; outline: none;
  color: var(--text-1); font-size: 14px;
}
.ss-esc {
  font-size: 10px; padding: 2px 7px; border-radius: 5px; cursor: pointer;
  background: var(--bg-elevated); border: 1px solid var(--border); color: var(--text-3);
}
.ss-body { overflow: auto; padding: 8px; }
.ss-hint { padding: 14px 12px; }
.hint-title { font-size: 11px; color: var(--text-3); margin-bottom: 8px; }
.hint-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 14px;
  font-size: 11.5px; color: var(--text-2); }
.ss-empty { padding: 26px; text-align: center; color: var(--text-3); font-size: 12.5px; }
.ss-group { margin-bottom: 6px; }
.g-name {
  font-size: 10.5px; color: var(--text-3); padding: 6px 10px 4px;
  letter-spacing: .4px; display: flex; gap: 6px;
}
.g-count { opacity: .7; }
.ss-item {
  width: 100%; display: flex; align-items: baseline; gap: 10px; text-align: left;
  padding: 6px 10px; border: none; border-radius: 7px; background: transparent;
  cursor: pointer; color: var(--text-1);
}
.ss-item.active { background: var(--accent-soft); }
.it-label { font-size: 12.5px; font-family: monospace; flex: none; max-width: 300px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.it-sub { font-size: 11px; color: var(--text-3); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.ss-foot {
  display: flex; gap: 16px; padding: 8px 16px; border-top: 1px solid var(--border);
  font-size: 10.5px; color: var(--text-3);
}
</style>
