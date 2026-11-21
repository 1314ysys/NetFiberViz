import { ref } from 'vue'

export interface Point { x: number; y: number }

/**
 * 画布视口 + 拖拽。
 *
 * 拖拽偏移 BUG 修复要点：
 * startDrag 必须传入节点**当前真实坐标**（nodeX/nodeY），据此计算指针与节点的偏移量；
 * 旧实现用 `pos[key] || {x:0,y:0}` 兜底，导致自动排布但未持久化的节点首次拖拽瞬移到原点。
 */
export function useCanvas(opts: { min?: number; max?: number } = {}) {
  const minS = opts.min ?? 0.2
  const maxS = opts.max ?? 2.5

  const scale = ref(1)
  const pan = ref<Point>({ x: 48, y: 48 })
  const svgEl = ref<SVGSVGElement>()
  const dragging = ref<string | null>(null)

  let dragState: { key: string; offX: number; offY: number } | null = null
  let panState: { sx: number; sy: number; px: number; py: number } | null = null

  function toWorld(evt: { clientX: number; clientY: number }): Point {
    const rect = svgEl.value!.getBoundingClientRect()
    return {
      x: (evt.clientX - rect.left - pan.value.x) / scale.value,
      y: (evt.clientY - rect.top - pan.value.y) / scale.value,
    }
  }

  function onWheel(evt: WheelEvent) {
    const p = toWorld(evt)
    const k = evt.deltaY < 0 ? 1.12 : 1 / 1.12
    const ns = Math.min(maxS, Math.max(minS, scale.value * k))
    pan.value = {
      x: pan.value.x - p.x * (ns - scale.value),
      y: pan.value.y - p.y * (ns - scale.value),
    }
    scale.value = ns
  }

  function startPan(evt: { clientX: number; clientY: number }) {
    const p = toWorld(evt)
    panState = { sx: p.x, sy: p.y, px: pan.value.x, py: pan.value.y }
  }

  /** nodeX / nodeY：节点当前真实坐标（不是缓存坐标） */
  function startDrag(evt: { clientX: number; clientY: number }, key: string, nodeX: number, nodeY: number) {
    const p = toWorld(evt)
    dragState = { key, offX: p.x - nodeX, offY: p.y - nodeY }
    dragging.value = key
  }

  /** apply(key, worldX, worldY) —— 调用方据此更新节点坐标 */
  function onMove(evt: { clientX: number; clientY: number }, apply?: (key: string, x: number, y: number) => void) {
    if (dragState && apply) {
      const p = toWorld(evt)
      apply(dragState.key, p.x - dragState.offX, p.y - dragState.offY)
    } else if (panState) {
      const p = toWorld(evt)
      pan.value = {
        x: panState.px + (p.x - panState.sx) * scale.value,
        y: panState.py + (p.y - panState.sy) * scale.value,
      }
    }
  }

  function endDrag(): string | null {
    const key = dragState?.key ?? null
    dragState = null
    panState = null
    dragging.value = null
    return key
  }

  function zoom(k: number) {
    scale.value = Math.min(maxS, Math.max(minS, scale.value * k))
  }

  function setZoom(z: number) {
    scale.value = Math.min(maxS, Math.max(minS, z))
  }

  /** 适应窗口：传入内容包围盒 */
  function fit(box: { minX: number; minY: number; maxX: number; maxY: number }, pad = 60) {
    const rect = svgEl.value?.getBoundingClientRect()
    if (!rect) return
    const w = Math.max(box.maxX - box.minX, 1)
    const h = Math.max(box.maxY - box.minY, 1)
    const s = Math.min((rect.width - pad * 2) / w, (rect.height - pad * 2) / h, 1.5)
    scale.value = Math.max(minS, s)
    pan.value = { x: pad - box.minX * scale.value, y: pad - box.minY * scale.value }
  }

  return { scale, pan, svgEl, dragging, toWorld, onWheel, startPan, startDrag, onMove, endDrag, zoom, setZoom, fit }
}
