import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ThemeMode = 'dark' | 'light'

function initial(): ThemeMode {
  const saved = localStorage.getItem('theme') as ThemeMode | null
  if (saved === 'dark' || saved === 'light') return saved
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

export const useUiStore = defineStore('ui', () => {
  const theme = ref<ThemeMode>(initial())

  function apply() {
    document.documentElement.dataset.theme = theme.value
  }

  function toggle() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    localStorage.setItem('theme', theme.value)
    apply()
  }

  function set(t: ThemeMode) {
    theme.value = t
    localStorage.setItem('theme', t)
    apply()
  }

  return { theme, toggle, set, apply }
})
