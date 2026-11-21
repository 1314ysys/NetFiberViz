<script setup lang="ts">
/** 端口外形图标：按 shape 绘制真实接口轮廓，颜色由状态/类型决定。
 *  支持 w/h 非等比拉伸（机柜视图里端口块常是窄条）。 */
const props = withDefaults(defineProps<{
  shape?: string
  fill?: string
  stroke?: string
  size?: number
  w?: number
  h?: number
}>(), { shape: 'lc', fill: 'var(--c-free)', stroke: 'var(--cv-slot-stroke)', size: 12 })

const width = props.w ?? props.size
const height = props.h ?? props.size
</script>

<template>
  <svg :width="width" :height="height" viewBox="0 0 16 16"
       preserveAspectRatio="none" class="pshape">
    <!-- LC：小方 + 双芯槽 -->
    <g v-if="shape === 'lc'">
      <rect x="3" y="3" width="10" height="10" rx="1.6" :fill="fill" :stroke="stroke" stroke-width="0.9" />
      <rect x="5.2" y="6.5" width="2" height="3.2" rx="0.5" fill="#00000055" />
      <rect x="8.8" y="6.5" width="2" height="3.2" rx="0.5" fill="#00000055" />
    </g>
    <!-- SC：大方 + 单芯槽 -->
    <g v-else-if="shape === 'sc'">
      <rect x="2.4" y="2.4" width="11.2" height="11.2" rx="1.2" :fill="fill" :stroke="stroke" stroke-width="0.9" />
      <rect x="6.4" y="5" width="3.2" height="6" rx="0.6" fill="#00000055" />
    </g>
    <!-- FC：圆形 + 螺纹 -->
    <g v-else-if="shape === 'fc'">
      <circle cx="8" cy="8" r="5.6" :fill="fill" :stroke="stroke" stroke-width="0.9" />
      <circle cx="8" cy="8" r="2.2" fill="#00000055" />
    </g>
    <!-- ST：圆形 + 卡口 -->
    <g v-else-if="shape === 'st'">
      <circle cx="8" cy="8" r="5.4" :fill="fill" :stroke="stroke" stroke-width="0.9" />
      <path d="M8 2.6 L8 5.4" :stroke="stroke" stroke-width="1.2" />
      <circle cx="8" cy="8" r="1.6" fill="#00000055" />
    </g>
    <!-- RJ45：梯形 -->
    <g v-else-if="shape === 'rj45'">
      <path d="M3.4 2.6 H12.6 V9.2 H3.4 Z" :fill="fill" :stroke="stroke" stroke-width="0.9" />
      <path d="M5 9.2 V13.4 H11 V9.2" :fill="fill" :stroke="stroke" stroke-width="0.9" />
      <path d="M6 5.5 H10 M6 7.2 H10" :stroke="stroke" stroke-width="0.7" opacity="0.6" />
    </g>
    <!-- 光模块笼位 -->
    <g v-else-if="shape === 'cage'">
      <rect x="1.8" y="4.2" width="12.4" height="7.6" rx="0.9" :fill="fill" :stroke="stroke" stroke-width="0.9" />
      <rect x="4" y="6" width="8" height="4" rx="0.4" fill="#00000055" />
    </g>
    <!-- MPO：宽矩形带定位 -->
    <g v-else-if="shape === 'mpo'">
      <rect x="1" y="4.6" width="14" height="6.8" rx="0.8" :fill="fill" :stroke="stroke" stroke-width="0.9" />
      <rect x="2.6" y="6.2" width="10.8" height="3.6" rx="0.4" fill="#00000055" />
      <circle cx="4" cy="11" r="0.7" fill="#00000055" />
    </g>
    <!-- 兜底 -->
    <rect v-else x="3" y="3" width="10" height="10" rx="2"
          :fill="fill" :stroke="stroke" stroke-width="0.9" />
  </svg>
</template>

<style scoped>
.pshape { display: block; }
</style>
