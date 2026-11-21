export interface RoomLite { id: number; name: string; code: string; parent_id?: number | null }

export interface RoomNode extends RoomLite { children: RoomNode[]; depth: number }

/** 扁平机房列表 → 树（保持原顺序） */
export function buildRoomTree(rooms: RoomLite[]): RoomNode[] {
  const map = new Map<number, RoomNode>()
  for (const r of rooms) map.set(r.id, { ...r, children: [], depth: 0 })
  const roots: RoomNode[] = []
  for (const r of rooms) {
    const node = map.get(r.id)!
    const pid = r.parent_id ?? null
    if (pid != null && map.has(pid)) {
      const parent = map.get(pid)!
      parent.children.push(node)
    } else {
      roots.push(node)
    }
  }
  const walk = (list: RoomNode[], depth: number) => {
    for (const n of list) {
      n.depth = depth
      walk(n.children, depth + 1)
    }
  }
  walk(roots, 0)
  return roots
}

/** 深度优先展平（用于缩进显示） */
export function flattenRoomTree(nodes: RoomNode[]): RoomNode[] {
  const out: RoomNode[] = []
  const walk = (list: RoomNode[]) => {
    for (const n of list) {
      out.push(n)
      walk(n.children)
    }
  }
  walk(nodes)
  return out
}

/** 生成带层级缩进的下拉选项 */
export function roomSelectOptions(rooms: RoomLite[]) {
  const tree = buildRoomTree(rooms)
  return flattenRoomTree(tree).map(n => ({
    label: `${'　'.repeat(n.depth)}${n.depth ? '└ ' : ''}${n.name}（${n.code}）`,
    value: n.id,
  }))
}

/** 机房路径，如 "核心机房 / 一号前端机房" */
export function roomPath(rooms: RoomLite[], id: number | null | undefined): string {
  if (!id) return ''
  const byId = new Map(rooms.map(r => [r.id, r]))
  const parts: string[] = []
  let cur = byId.get(id)
  let guard = 0
  while (cur && guard++ < 20) {
    parts.unshift(cur.name)
    cur = cur.parent_id != null ? byId.get(cur.parent_id) : undefined
  }
  return parts.join(' / ')
}

/** 判断 candidate 是否在 rootId 的子树内（含自身） */
export function isDescendant(rooms: RoomLite[], rootId: number, candidateId: number): boolean {
  if (rootId === candidateId) return true
  const byId = new Map(rooms.map(r => [r.id, r]))
  let cur = byId.get(candidateId)
  let guard = 0
  while (cur && cur.parent_id != null && guard++ < 20) {
    if (cur.parent_id === rootId) return true
    cur = byId.get(cur.parent_id)
  }
  return false
}
