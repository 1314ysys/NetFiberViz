import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '../api/client'
import { FALLBACK_PORT_TYPES } from '../utils/portTypes'
import type { PortTypeDef } from '../utils/portTypes'

export interface Room { id: number; name: string; code: string; address?: string }
export interface Rack { id: number; room_id: number; name: string; code: string; u_count: number; pos_x: number; pos_y: number }
export interface Device { id: number; rack_id: number; name: string; model: string; device_type: string; category?: string; template_key?: string; svg_key: string; u_position: number; u_height?: number; port_layout?: string; panel_width?: number; mgmt_ip?: string; remark?: string }
export interface Port { id: number; owner_type: string; owner_id: number; port_no: string; port_type: string; status: string; label: string; remark?: string; group_name?: string; group_seq?: number }
export interface Cabinet { id: number; room_id: number; name: string; code: string; pos_x: number; pos_y: number }
export interface Unit { id: number; cabinet_id: number; name: string; seq: number }
export interface Tray { id: number; unit_id: number; name: string; slots_per_row: number; rows: number; seq: number }
export interface Slot { id: number; tray_id: number; row_label: string; col_no: number; label: string; port?: Port }
export interface Tray { id: number; unit_id: number; name: string; slots_per_row: number; rows: number; seq: number; pos_x?: number; pos_y?: number; slot_count?: number; used_count?: number }

export interface PortGroupDef { name: string; prefix: string; count: number; type: string }
export interface DeviceTemplate {
  key: string; name: string; category: string; device_type: string; groups: PortGroupDef[]
  u_height?: number; width?: number; layout?: string
  builtin?: boolean; id?: number; layout_json?: any; remark?: string
}

export const DEVICE_TYPE_LABEL: Record<string, string> = {
  sw: '交换机', olt: 'OLT', oadm: '光分插复用', amp: '光放大器',
  tx: '光发射机', rx: '光接收机', media_conv: '光纤收发器', custom: '自定义',
  router: '路由器', firewall: '防火墙', otp: '光传送平台', osw: '光切换器',
  mux: '合波器', demux: '分波器', splitter: '分光器', patch_panel: '配线面板', dwdm: '波分设备',
}

export const PORT_STATUS_LABEL: Record<string, string> = {
  free: '空闲', used: '在用', reserved: '预留', fault: '故障',
}

/** 资源缓存：机房/机柜/设备/端口/ODF，供各页面共享 */
export const useResourceStore = defineStore('resource', () => {
  const rooms = ref<Room[]>([])
  const racks = ref<Rack[]>([])
  const devices = ref<Device[]>([])
  const ports = ref<Port[]>([])
  const cabinets = ref<Cabinet[]>([])
  const units = ref<Unit[]>([])
  const trays = ref<Tray[]>([])
  const templates = ref<DeviceTemplate[]>([])
  const categories = ref<Record<string, string>>({})
  const portTypes = ref<PortTypeDef[]>([])
  const loading = ref(false)

  const deviceById = computed(() => Object.fromEntries(devices.value.map(d => [d.id, d])))
  const portById = computed(() => Object.fromEntries(ports.value.map(p => [p.id, p])))

  async function loadBase() {
    loading.value = true
    try {
      const [rm, rk, dv, pt, cb] = await Promise.all([
        api.get('/rooms'), api.get('/racks'), api.get('/devices'),
        api.get('/ports'), api.get('/odf/cabinets'),
      ])
      rooms.value = rm.data
      racks.value = rk.data
      devices.value = dv.data
      ports.value = pt.data
      cabinets.value = cb.data
    } finally {
      loading.value = false
    }
  }

  async function loadUnits(cabinetId: number) {
    const r = await api.get('/odf/units', { params: { cabinet_id: cabinetId } })
    const list = r.data as Unit[]
    // 合并语义：避免多柜加载时互相覆盖
    units.value = [...units.value.filter(u => u.cabinet_id !== cabinetId), ...list]
    return list
  }

  async function loadTrays(unitId: number) {
    const r = await api.get('/odf/trays', { params: { unit_id: unitId } })
    const list = r.data as Tray[]
    trays.value = [...trays.value.filter(t => t.unit_id !== unitId), ...list]
    return list
  }

  /** 切换机房时清空 ODF 缓存 */
  function resetOdf() {
    units.value = []
    trays.value = []
  }

  async function loadSlots(trayId: number) {
    const r = await api.get('/odf/slots', { params: { tray_id: trayId } })
    return r.data as Slot[]
  }

  /** 端口标签（含归属设备名） */
  function portLabel(p?: Port | null): string {
    if (!p) return '—'
    if (p.owner_type === 'device') {
      const d = deviceById.value[p.owner_id]
      return d ? `${d.name} / ${p.port_no}` : p.port_no
    }
    return p.port_no
  }

  function racksOfRoom(roomId: number) {
    return racks.value.filter(r => r.room_id === roomId)
  }
  function devicesOfRack(rackId: number) {
    return devices.value.filter(d => d.rack_id === rackId)
  }
  function portsOfDevice(deviceId: number) {
    return ports.value.filter(p => p.owner_type === 'device' && p.owner_id === deviceId)
  }

  /** 端口按组归并（保持组序），用于"分组成排"渲染 */
  function groupPorts(ports: Port[]): { name: string; seq: number; ports: Port[] }[] {
    const m = new Map<string, { name: string; seq: number; ports: Port[] }>()
    for (const p of ports) {
      const name = p.group_name || '端口'
      const seq = p.group_seq ?? 0
      const key = `${seq}::${name}`
      if (!m.has(key)) m.set(key, { name, seq, ports: [] })
      m.get(key)!.ports.push(p)
    }
    return [...m.values()].sort((a, b) => a.seq - b.seq || a.name.localeCompare(b.name))
  }

  async function loadTemplates(force = false) {
    if (templates.value.length && !force) return templates.value
    const r = await api.get('/device-templates')
    templates.value = r.data.templates || []
    categories.value = r.data.categories || {}
    portTypes.value = r.data.port_types?.length ? r.data.port_types : FALLBACK_PORT_TYPES
    return templates.value
  }

  return {
    rooms, racks, devices, ports, cabinets, units, trays, templates, categories, portTypes, loading,
    deviceById, portById,
    loadBase, loadUnits, loadTrays, loadSlots, resetOdf, loadTemplates,
    portLabel, racksOfRoom, devicesOfRack, portsOfDevice, groupPorts,
  }
})
