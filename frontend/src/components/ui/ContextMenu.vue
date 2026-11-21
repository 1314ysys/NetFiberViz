<script setup lang="ts">
import { computed } from 'vue'

export interface MenuItem {
  key: string
  label: string
  danger?: boolean
  divider?: boolean
  disabled?: boolean
  hint?: string
}

const props = defineProps<{ show: boolean; x: number; y: number; items: MenuItem[]; title?: string }>()
const emit = defineEmits<{
  (e: 'select', key: string): void
  (e: 'update:show', v: boolean): void
}>()

/** 避免菜单超出视口 */
const style = computed(() => {
  const w = 190
  const h = props.items.length * 32 + (props.title ? 30 : 8)
  const vw = window.innerWidth
  const vh = window.innerHeight
  return {
    left: Math.min(props.x, vw - w - 8) + 'px',
    top: Math.min(props.y, vh - h - 8) + 'px',
    width: w + 'px',
  }
})

function pick(it: MenuItem) {
  if (it.disabled) return
  emit('select', it.key)
  emit('update:show', false)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="cm-mask" @pointerdown="emit('update:show', false)" @contextmenu.prevent>
      <div class="cm" :style="style" @pointerdown.stop @contextmenu.prevent>
        <div v-if="title" class="cm-title">{{ title }}</div>
        <template v-for="it in items" :key="it.key">
          <div v-if="it.divider" class="cm-div"></div>
          <button v-else class="cm-item" :class="{ danger: it.danger, disabled: it.disabled }"
                  :disabled="it.disabled" @click="pick(it)">
            <span>{{ it.label }}</span>
            <span v-if="it.hint" class="cm-hint">{{ it.hint }}</span>
          </button>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.cm-mask { position: fixed; inset: 0; z-index: 3000; }
.cm {
  position: absolute; background: var(--menu-bg); border: 1px solid var(--border-strong);
  border-radius: 9px; padding: 5px; box-shadow: 0 12px 34px rgba(0, 0, 0, .35);
  animation: pop .1s ease-out;
}
@keyframes pop { from { opacity: 0; transform: scale(.97) } to { opacity: 1; transform: scale(1) } }
.cm-title {
  font-size: 10.5px; color: var(--text-3); padding: 5px 9px 6px;
  border-bottom: 1px solid var(--border); margin-bottom: 4px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cm-item {
  width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 6px 9px; border: none; border-radius: 6px; background: transparent;
  color: var(--text-1); font-size: 12.5px; cursor: pointer; text-align: left;
}
.cm-item:hover:not(.disabled) { background: var(--bg-hover); }
.cm-item.danger { color: #ef4444; }
.cm-item.danger:hover { background: rgba(239, 68, 68, .12); }
.cm-item.disabled { opacity: .4; cursor: default; }
.cm-hint { font-size: 10.5px; color: var(--text-3); }
.cm-div { height: 1px; background: var(--border); margin: 4px 6px; }
</style>
