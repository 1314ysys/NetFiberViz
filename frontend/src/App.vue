<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NConfigProvider, NMessageProvider, NDialogProvider, darkTheme, zhCN, dateZhCN } from 'naive-ui'
import AppShell from './components/layout/AppShell.vue'
import { darkOverrides, lightOverrides } from './styles/naive-theme'
import { useUiStore } from './stores/ui'

const route = useRoute()
const ui = useUiStore()

/** login 与大屏不套用侧边栏外壳 */
const useShell = computed(() => route.meta.chrome !== false)
const naiveTheme = computed(() => (ui.theme === 'dark' ? darkTheme : null))
const overrides = computed(() => (ui.theme === 'dark' ? darkOverrides : lightOverrides))

onMounted(() => ui.apply())
watch(() => ui.theme, () => ui.apply())
</script>

<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="overrides" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-dialog-provider>
        <AppShell v-if="useShell">
          <router-view />
        </AppShell>
        <router-view v-else />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>
