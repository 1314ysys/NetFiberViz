<script setup lang="ts">
import { useRouter } from 'vue-router'
import Icon from './Icon.vue'

export interface Crumb {
  label: string
  to?: string
}

withDefaults(defineProps<{ items: Crumb[]; back?: boolean }>(), { back: true })

const router = useRouter()

function go(c: Crumb, isLast: boolean) {
  if (isLast) return
  if (c.to) router.push(c.to)
}
</script>

<template>
  <nav class="crumbs">
    <button v-if="back" class="back" title="返回上一层级" @click="router.back()">
      <Icon name="close" :size="12" />
    </button>
    <template v-for="(c, i) in items" :key="i">
      <span v-if="i > 0" class="sep">/</span>
      <span class="crumb" :class="{ last: i === items.length - 1, link: !!c.to && i !== items.length - 1 }"
            @click="go(c, i === items.length - 1)">{{ c.label }}</span>
    </template>
  </nav>
</template>

<style scoped>
.crumbs {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--text-3); min-width: 0;
}
.back {
  width: 22px; height: 22px; display: grid; place-items: center; flex: none;
  background: transparent; border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-2); cursor: pointer; transition: .12s; margin-right: 2px;
}
.back:hover { background: var(--bg-hover); color: var(--accent); border-color: var(--border-strong); }
.sep { color: var(--text-3); opacity: .55; }
.crumb {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 220px;
}
.crumb.link { cursor: pointer; color: var(--text-2); }
.crumb.link:hover { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; }
.crumb.last { color: var(--text-1); font-weight: 600; }
</style>
