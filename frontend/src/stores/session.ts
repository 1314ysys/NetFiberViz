import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '../api/client'
import { useResourceStore } from './resource'

export interface SessionUser {
  id: number
  username: string
  display_name: string
  role: 'core_admin' | 'site_admin' | string
  room_ids: number[]
}

/** 会话：token + 当前用户 + 写权限判定 */
export const useSessionStore = defineStore('session', () => {
  const token = ref<string>(localStorage.getItem('token') || '')
  const user = ref<SessionUser | null>(null)

  const isCore = computed(() => user.value?.role === 'core_admin')
  const grantedRooms = computed<number[]>(() => user.value?.room_ids || [])

  /** 可写机房集合；null 表示全量 */
  const scopeSet = computed<Set<number> | null>(() => {
    if (!user.value) return new Set()
    if (isCore.value) return null
    const rooms = useResourceStore().rooms as any[]
    const children = new Map<number, number[]>()
    for (const r of rooms) {
      const p = r.parent_id
      if (p != null) {
        if (!children.has(p)) children.set(p, [])
        children.get(p)!.push(r.id)
      }
    }
    const out = new Set<number>()
    const stack = [...grantedRooms.value]
    while (stack.length) {
      const cur = stack.pop()!
      if (out.has(cur)) continue
      out.add(cur)
      for (const c of children.get(cur) || []) stack.push(c)
    }
    return out
  })

  function canWriteRoom(roomId: number | null | undefined): boolean {
    if (!roomId) return false
    const s = scopeSet.value
    return s === null ? true : s.has(roomId)
  }

  function setToken(t: string) {
    token.value = t
    localStorage.setItem('token', t)
  }

  async function login(username: string, password: string) {
    const form = new URLSearchParams({ username, password })
    const r = await api.post('/auth/login', form)
    setToken(r.data.access_token)
    await fetchMe()
  }

  async function fetchMe() {
    try {
      const r = await api.get('/auth/me')
      user.value = r.data
    } catch {
      user.value = null
    }
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    location.hash = '#/login'
  }

  return { token, user, isCore, grantedRooms, scopeSet, canWriteRoom, login, fetchMe, logout, setToken }
})
