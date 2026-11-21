<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ status?: string; kind?: 'port' | 'core' | 'action' }>()

/** 颜色走 CSS 变量，随主题（深/浅）自动切换 */
const MAP: Record<string, { label: string; color: string; bg: string }> = {
  // 端口 / 孔位
  free: { label: '空闲', color: 'var(--c-free)', bg: 'rgba(148,163,184,.16)' },
  used: { label: '在用', color: 'var(--c-used)', bg: 'rgba(34,197,94,.14)' },
  reserved: { label: '预留', color: 'var(--c-reserved)', bg: 'rgba(59,130,246,.14)' },
  fault: { label: '故障', color: 'var(--c-fault)', bg: 'rgba(239,68,68,.14)' },
  // 纤芯
  unused: { label: '未成端', color: 'var(--c-free)', bg: 'rgba(100,116,139,.16)' },
  landed: { label: '已成端', color: 'var(--c-used)', bg: 'rgba(34,197,94,.14)' },
  spliced: { label: '已熔接', color: 'var(--c-inter)', bg: 'rgba(168,85,247,.14)' },
  spare: { label: '备用', color: '#f59e0b', bg: 'rgba(245,158,11,.14)' },
  // 动作
  create: { label: '新增', color: 'var(--c-used)', bg: 'rgba(34,197,94,.14)' },
  update: { label: '修改', color: '#f59e0b', bg: 'rgba(245,158,11,.14)' },
  delete: { label: '删除', color: 'var(--c-fault)', bg: 'rgba(239,68,68,.14)' },
  active: { label: '在用', color: 'var(--c-used)', bg: 'rgba(34,197,94,.14)' },
  removed: { label: '已拆除', color: 'var(--c-free)', bg: 'rgba(100,116,139,.16)' },
}

const meta = computed(() => MAP[props.status || ''] ?? {
  label: props.status || '—', color: 'var(--c-free)', bg: 'rgba(148,163,184,.16)',
})
</script>

<template>
  <span class="tag" :style="{ color: meta.color, background: meta.bg }">
    <i class="dot" :style="{ background: meta.color }"></i>{{ meta.label }}
  </span>
</template>

<style scoped>
.tag {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 1px 9px; border-radius: 999px;
  border: 1px solid color-mix(in srgb, currentColor 32%, transparent);
  font-size: 11.5px; line-height: 18px; white-space: nowrap;
}
.dot { width: 5px; height: 5px; border-radius: 50%; }
</style>
