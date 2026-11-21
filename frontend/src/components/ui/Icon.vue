<script setup lang="ts">
import { computed } from 'vue'
/** 轻量线性图标集（内联 SVG，无外部依赖，内网可用） */
const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 16 })

const PATHS: Record<string, string> = {
  grid: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  cable: 'M4 4v6a4 4 0 004 4h8a4 4 0 014 4v2M4 20v-2',
  radar: 'M12 3a9 9 0 109 9M12 12l6-6M12 12h.01',
  link: 'M10 13a5 5 0 007 0l2-2a5 5 0 00-7-7l-1 1M14 11a5 5 0 00-7 0l-2 2a5 5 0 007 7l1-1',
  history: 'M3 12a9 9 0 109-9 9 9 0 00-7.5 4M3 4v4h4M12 8v4l3 2',
  screen: 'M3 4h18v12H3zM8 20h8M12 16v4',
  topology: 'M12 3v6M12 15v6M6 12H3M21 12h-3M7.5 7.5L5 5M19 19l-2.5-2.5M16.5 7.5L19 5M5 19l2.5-2.5M12 9a3 3 0 100 6 3 3 0 000-6z',
  logout: 'M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9',
  refresh: 'M21 12a9 9 0 11-3-6.7M21 3v6h-6',
  plus: 'M12 5v14M5 12h14',
  search: 'M11 4a7 7 0 104.9 12L21 21M11 4a7 7 0 00-7 7',
  zoomIn: 'M11 4a7 7 0 104.9 12L21 21M11 8v6M8 11h6',
  zoomOut: 'M11 4a7 7 0 104.9 12L21 21M8 11h6',
  fit: 'M3 9V3h6M21 9V3h-6M3 15v6h6M21 15v6h-6',
  save: 'M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2zM7 3v6h8V3M7 21v-8h10v8',
  trash: 'M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6',
  edit: 'M11 4H4v16h16v-7M18.5 2.5a2.1 2.1 0 013 3L12 15l-4 1 1-4z',
  check: 'M20 6L9 17l-5-5',
  close: 'M18 6L6 18M6 6l12 12',
  upload: 'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12',
  download: 'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3',
  server: 'M3 4h18v6H3zM3 14h18v6H3zM7 7h.01M7 17h.01',
  box: 'M21 8l-9-5-9 5 9 5 9-5zM3 8v8l9 5 9-5V8',
  filter: 'M3 4h18l-7 8v7l-4 2v-9z',
  warn: 'M12 3L2 21h20L12 3zM12 9v5M12 17h.01',
  sun: 'M12 8a4 4 0 100 8 4 4 0 000-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
  moon: 'M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z',
  users: 'M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75',
  shield: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
}

const p = computed(() => PATHS[props.name] ?? PATHS.grid)
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none"
       stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"
       class="ico" aria-hidden="true">
    <path :d="p" />
  </svg>
</template>

<style scoped>
.ico { display: block; flex: none; }
</style>
