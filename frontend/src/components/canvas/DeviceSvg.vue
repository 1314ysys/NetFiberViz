<script setup lang="ts">
/** 拟真设备 SVG 组件：按 device_type 参数化渲染正面板（渐变+阴影+端口栅格）。 */
const props = defineProps<{ deviceType: string; name: string; svgKey?: string; width?: number }>()
const W = props.width ?? 180

const META: Record<string, { h: number; ports: number; perRow: number; label: string; color: string }> = {
  sw:         { h: 60,  ports: 28, perRow: 14, label: 'SW',   color: '#1d4ed8' },
  olt:        { h: 60,  ports: 24, perRow: 12, label: 'OLT',  color: '#0e7490' },
  oadm:       { h: 60,  ports: 8,  perRow: 8,  label: 'OAD',  color: '#7c3aed' },
  amp:        { h: 60,  ports: 2,  perRow: 2,  label: 'EDFA', color: '#b45309' },
  tx:         { h: 60,  ports: 1,  perRow: 1,  label: 'OT',   color: '#15803d' },
  rx:         { h: 60,  ports: 1,  perRow: 1,  label: 'RX',   color: '#166534' },
  media_conv: { h: 60,  ports: 2,  perRow: 2,  label: 'MC',   color: '#4b5563' },
  custom:     { h: 60,  ports: 0,  perRow: 1,  label: 'DEV',  color: '#6b7280' },
}
const m = META[props.deviceType] ?? META.custom
const portW = 8, portGap = 4, portY = 34
const startX = (W - (Math.min(m.ports, m.perRow) * portW + (Math.min(m.ports, m.perRow) - 1) * portGap)) / 2
const uid = `g${Math.random().toString(36).slice(2, 8)}`
</script>

<template>
  <svg :viewBox="`0 0 ${W} ${m.h}`" :width="W" :height="m.h" class="device-svg">
    <defs>
      <linearGradient :id="`${uid}-body`" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#3a4252" />
        <stop offset="0.5" stop-color="#22293a" />
        <stop offset="1" stop-color="#141923" />
      </linearGradient>
    </defs>
    <rect x="1" y="1" :width="W - 2" :height="m.h - 2" rx="4" :fill="`url(#${uid}-body)`" stroke="#0b0f17" />
    <rect x="1" y="1" :width="W - 2" height="6" rx="4" :fill="m.color" opacity="0.85" />
    <!-- 状态灯排 -->
    <template v-if="m.ports > 0">
      <circle v-for="i in Math.min(m.ports, m.perRow)" :key="'l' + i"
              :cx="startX + (i - 1) * (portW + portGap) + portW / 2" cy="14" r="1.6" fill="#22c55e" opacity="0.9" />
      <!-- 端口栅格（锚点元素带 data-port） -->
      <g v-for="i in Math.min(m.ports, m.perRow)" :key="'p' + i">
        <rect :data-port="i" :x="startX + (i - 1) * (portW + portGap)" :y="portY"
              :width="portW" :height="m.h - portY - 10" rx="1.5" fill="#0b0f17" stroke="#4b5563" stroke-width="0.8" />
        <rect :x="startX + (i - 1) * (portW + portGap) + 1" :y="portY + 2"
              :width="portW - 2" height="3" rx="1" fill="#334155" />
      </g>
    </template>
    <text :x="6" :y="m.h - 4" font-size="9" fill="#94a3b8">{{ m.label }}</text>
    <text :x="W - 6" :y="m.h - 4" font-size="9" fill="#cbd5e1" text-anchor="end">{{ name }}</text>
  </svg>
</template>

<style scoped>
.device-svg { display: block; filter: drop-shadow(0 1px 3px rgba(0,0,0,0.28)); }
</style>
