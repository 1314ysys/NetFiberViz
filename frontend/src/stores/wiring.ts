import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '../api/client'
import type { Port } from './resource'

/**
 * 全局布线状态：A 端选中后跨页面/跨机柜保持，
 * 由悬浮窗展示，可在任意机柜视图点选 B 端。
 */
export const useWiringStore = defineStore('wiring', () => {
  const aPort = ref<Port | null>(null)
  const bPort = ref<Port | null>(null)
  const pickerOpen = ref(false)
  const cordOpen = ref(false)
  const busy = ref(false)
  const compat = ref<{ level: string; message: string } | null>(null)
  /** 创建成功后自增，页面据此刷新数据 */
  const refreshTick = ref(0)

  const active = computed(() => !!aPort.value)

  function clear() {
    aPort.value = null
    bPort.value = null
    compat.value = null
    cordOpen.value = false
  }

  function setA(p: Port) {
    aPort.value = p
    bPort.value = null
    compat.value = null
  }

  /** 选中一个端口：无 A 则设 A，有 A 则作为 B 并做兼容性预检 */
  async function pick(p: Port): Promise<'setA' | 'same' | 'block' | 'warn' | 'ok'> {
    if (!aPort.value) {
      setA(p)
      return 'setA'
    }
    if (aPort.value.id === p.id) {
      clear()
      return 'same'
    }
    bPort.value = p
    compat.value = null
    try {
      const r = await api.get('/ports/compat', { params: { a: aPort.value.id, b: p.id } })
      if (r.data.level === 'block') {
        bPort.value = null
        return 'block'
      }
      if (r.data.level === 'warn') {
        compat.value = { level: 'warn', message: r.data.message }
        cordOpen.value = true
        return 'warn'
      }
    } catch { /* 预检失败按放行处理 */ }
    cordOpen.value = true
    return 'ok'
  }

  /** 兼容性预检结果，供 UI 显示 */
  async function checkCompat() {
    if (!aPort.value || !bPort.value) return null
    try {
      const r = await api.get('/ports/compat', {
        params: { a: aPort.value.id, b: bPort.value.id },
      })
      compat.value = r.data
      return r.data
    } catch {
      return null
    }
  }

  async function createCord(v: {
    cord_type?: string; length_m?: number; remark?: string; force?: boolean
  }) {
    if (!aPort.value || !bPort.value) return false
    busy.value = true
    try {
      await api.post('/patch-cords', {
        port_a_id: aPort.value.id,
        port_b_id: bPort.value.id,
        cord_type: v.cord_type || 'LC-LC 单模',
        length_m: Number(v.length_m || 0),
        remark: v.remark || '',
        force: !!v.force,
      })
      refreshTick.value++
      clear()
      return true
    } finally {
      busy.value = false
    }
  }

  return {
    aPort, bPort, pickerOpen, cordOpen, busy, compat, refreshTick, active,
    setA, pick, checkCompat, createCord, clear,
  }
})
