<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NModal, NSelect, NButton } from 'naive-ui'
import { useResourceStore } from '../../stores/resource'
import type { Port } from '../../stores/resource'
import { useWiringStore } from '../../stores/wiring'
import Icon from '../ui/Icon.vue'

const store = useResourceStore()
const wiring = useWiringStore()

const show = computed({
  get: () => wiring.pickerOpen,
  set: (v: boolean) => { wiring.pickerOpen = v },
})

const selected = ref<number | null>(null)
const keyword = ref('')

watch(show, (v) => {
  if (v) { selected.value = null; keyword.value = '' }
})

/** 全部空闲端口，按设备分组（组名带机柜），末尾 ODF 孔位 */
const options = computed(() => {
  const out: any[] = []
  const byDevice = new Map<number, any[]>()
  for (const p of store.ports) {
    if (p.status !== 'free') continue
    if (wiring.aPort && p.id === wiring.aPort.id) continue
    if (p.owner_type !== 'device') continue
    const d = store.deviceById[p.owner_id]
    if (!d) continue
    if (!byDevice.has(d.id)) byDevice.set(d.id, [])
    byDevice.get(d.id)!.push({ label: `${p.port_no}  ·  ${p.port_type}`, value: p.id })
  }
  for (const [did, children] of byDevice) {
    const d = store.deviceById[did]
    const rk = store.racks.find(r => r.id === d.rack_id)
    const room = store.rooms.find(r => r.id === rk?.room_id)
    out.push({
      type: 'group' as const,
      key: `d-${did}`,
      label: `${d.name}${rk ? ' · ' + rk.name : ''}${room ? ' · ' + room.name : ''}`,
      children,
    })
  }
  const odf = store.ports
    .filter(p => p.owner_type === 'odf_slot' && p.status === 'free')
    .map(p => ({ label: `${p.port_no}  ·  ${p.port_type}`, value: p.id }))
  if (odf.length) out.push({ type: 'group' as const, key: 'odf', label: 'ODF 孔位', children: odf })
  return out
})

const totalFree = computed(() =>
  options.value.reduce((n: number, g: any) => n + (g.children?.length || 0), 0))

async function confirm() {
  if (!selected.value) return
  const p = store.portById[selected.value]
  if (!p) return
  wiring.pickerOpen = false
  const r = await wiring.pick(p as Port)
  if (r === 'block') {
    // 由全局提示处理，这里静默即可
  }
}
</script>

<template>
  <n-modal v-model:show="show" :mask-closable="true">
    <div class="pp">
      <header class="pp-head">
        <Icon name="link" :size="15" />
        <span class="pp-title">选择对端端口</span>
        <span class="pp-count">{{ totalFree }} 个空闲端口</span>
        <span class="pp-x" @click="show = false">✕</span>
      </header>

      <div class="pp-body">
        <div v-if="wiring.aPort" class="pp-a">
          <span class="dim">A 端</span>
          <b>{{ store.portLabel(wiring.aPort) }}</b>
          <span class="chip">{{ wiring.aPort.port_type }}</span>
        </div>

        <n-select v-model:value="selected" :options="options" filterable clearable
                  size="large" placeholder="搜索端口号 / 设备名 / 接口类型（全部机柜）"
                  :consistent-menu-width="true" />

        <p class="pp-hint">
          列表按设备分组，组名标注所属<b>机柜与机房</b>；共 {{ totalFree }} 个空闲端口可用。
          也可直接关闭此窗，返回上层进入目标机柜后点击端口。
        </p>
      </div>

      <footer class="pp-foot">
        <n-button quaternary @click="show = false">取消</n-button>
        <n-button type="primary" size="large" :disabled="!selected" @click="confirm">
          下一步：填写跳纤信息
        </n-button>
      </footer>
    </div>
  </n-modal>
</template>

<style scoped>
.pp {
  width: 760px; max-width: 94vw; background: var(--bg-panel);
  border: 1px solid var(--border-strong); border-radius: 14px;
  box-shadow: var(--shadow-2); overflow: hidden;
}
.pp-head {
  display: flex; align-items: center; gap: 9px; padding: 15px 20px;
  border-bottom: 1px solid var(--border); color: var(--text-2);
}
.pp-title { font-size: 15px; font-weight: 600; color: var(--text-1); }
.pp-count {
  font-size: 11.5px; color: var(--text-3); background: var(--bg-elevated);
  border: 1px solid var(--border); border-radius: 999px; padding: 1px 10px;
}
.pp-x { margin-left: auto; cursor: pointer; color: var(--text-3); font-size: 14px; }
.pp-body { padding: 20px; display: flex; flex-direction: column; gap: 14px; }
.pp-a {
  display: flex; align-items: center; gap: 10px; font-size: 13px;
  background: var(--bg-elevated); border: 1px solid var(--border);
  border-radius: 9px; padding: 11px 14px;
}
.pp-a b { color: var(--text-1); }
.chip {
  font-size: 10.5px; padding: 1px 8px; border-radius: 999px;
  background: var(--accent-soft); color: var(--accent);
  border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
}
.pp-hint { font-size: 11.5px; color: var(--text-3); margin: 0; line-height: 1.7; }
.pp-hint b { color: var(--text-2); }
.pp-foot {
  display: flex; justify-content: flex-end; gap: 10px; padding: 14px 20px;
  border-top: 1px solid var(--border);
}
</style>
