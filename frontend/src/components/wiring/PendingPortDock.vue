<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useResourceStore } from '../../stores/resource'
import { useWiringStore } from '../../stores/wiring'
import Icon from '../ui/Icon.vue'
import PortShape from '../canvas/PortShape.vue'
import { shapeOf, familyColorOf } from '../../utils/portTypes'

const store = useResourceStore()
const wiring = useWiringStore()
const router = useRouter()

/** 定位 A 端所在机柜/机房，便于“返回该层级” */
const ctx = computed(() => {
  const p = wiring.aPort
  if (!p) return null
  if (p.owner_type === 'device') {
    const d = store.deviceById[p.owner_id]
    const rk = store.racks.find(r => r.id === d?.rack_id)
    const room = store.rooms.find(r => r.id === rk?.room_id)
    return {
      device: d?.name || '',
      rack: rk?.name || '',
      room: room?.name || '',
      to: rk ? `/interior/rack/${rk.id}` : '',
    }
  }
  return { device: 'ODF 孔位', rack: '', room: '', to: '' }
})

function backToRack() {
  if (ctx.value?.to) router.push(ctx.value.to)
}
</script>

<template>
  <Teleport to="body">
    <Transition name="dock">
      <div v-if="wiring.aPort" class="dock">
        <div class="dock-head">
          <Icon name="link" :size="13" />
          <span>待连接 · A 端已选</span>
          <button class="x" title="取消" @click="wiring.clear()">✕</button>
        </div>

        <div class="dock-body">
          <div class="port-line">
            <PortShape :shape="shapeOf(store.portTypes, wiring.aPort.port_type)"
                       :size="22" fill="var(--c-used)"
                       :stroke="familyColorOf(store.portTypes, wiring.aPort.port_type)" />
            <div class="port-txt">
              <b>{{ store.portLabel(wiring.aPort) }}</b>
              <span>{{ wiring.aPort.port_type }}</span>
            </div>
          </div>

          <div v-if="ctx" class="ctx-line">
            <span v-if="ctx.room">{{ ctx.room }}</span>
            <span v-if="ctx.rack">/ {{ ctx.rack }}</span>
            <button v-if="ctx.to" class="lnk" @click="backToRack">回到该机柜</button>
          </div>
        </div>

        <div class="dock-actions">
          <button class="btn primary" @click="wiring.pickerOpen = true">
            选择对端（可跨机柜）
          </button>
        </div>

        <p class="dock-tip">
          也可返回上层，进入其他机柜后直接点击目标端口
        </p>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.dock {
  position: fixed; right: 20px; bottom: 20px; z-index: 4600;
  width: 320px; background: var(--bg-panel);
  border: 1px solid var(--border-strong); border-radius: 12px;
  box-shadow: var(--shadow-2); overflow: hidden;
}
.dock-head {
  display: flex; align-items: center; gap: 7px; padding: 9px 13px;
  background: linear-gradient(90deg, var(--accent-soft), transparent);
  border-bottom: 1px solid var(--border);
  font-size: 12px; font-weight: 600; color: var(--accent);
}
.x {
  margin-left: auto; background: none; border: none;
  color: var(--text-3); cursor: pointer; font-size: 12px;
}
.x:hover { color: var(--text-1); }
.dock-body { padding: 12px 13px 6px; }
.port-line { display: flex; align-items: center; gap: 10px; }
.port-txt { display: flex; flex-direction: column; line-height: 1.35; min-width: 0; }
.port-txt b {
  font-size: 12.5px; color: var(--text-1);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.port-txt span { font-size: 11px; color: var(--text-3); }
.ctx-line {
  display: flex; align-items: center; gap: 5px; flex-wrap: wrap;
  font-size: 10.5px; color: var(--text-3); margin-top: 8px;
}
.lnk {
  background: none; border: none; color: var(--accent);
  font-size: 10.5px; cursor: pointer; padding: 0; text-decoration: underline;
  text-underline-offset: 2px;
}
.dock-actions { padding: 8px 13px 4px; }
.btn {
  width: 100%; border-radius: 8px; padding: 8px; font-size: 12px;
  cursor: pointer; border: 1px solid var(--border);
  background: var(--bg-elevated); color: var(--text-1);
}
.btn.primary {
  background: var(--accent); color: #fff; border-color: transparent; font-weight: 500;
}
.btn.primary:hover { filter: brightness(1.08); }
.dock-tip {
  margin: 0; padding: 4px 13px 12px; font-size: 10.5px;
  color: var(--text-3); line-height: 1.6;
}
.dock-enter-active, .dock-leave-active { transition: all .18s ease; }
.dock-enter-from, .dock-leave-to { opacity: 0; transform: translateY(10px); }
</style>
