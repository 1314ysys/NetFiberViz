import { ref } from 'vue'

export interface Point { x: number; y: number }

/**
 * 画布视口 + 拖拽 + 多点触控。
 *
 * 拖拽偏移 BUG 修复要点：
 * startDrag 必须传入节点**当前真实坐标**（nodeX/nodeY），据此计算指针与节点的偏移量；
 * 旧实现用 `pos[key] || {x:0,y:0}` 兜底，导致自动排布但未持久化的节点首次拖拽瞬移到原点。
 *
 * 移动端：
 * - 双指捏合缩放（以两指中心为锚点，缩放时内容不漂移）
 * - 双指期间自动中止单指拖拽/平移，避免冲突
 * - 双击空白处放大，再次双击还原
 */
export function useCanvas(opts: { min?: number; max?: number } = {}) {
  const minS = opts.min ?? 0.2
  const maxS = opts.max ?? 2.5

  const scale = ref(1)
  const pan = ref<Point>({ x: 48, y: 48 })
  const svgEl = ref<SVGSVGElement>()
  const dragging = ref<string | null>(null)

  /** 是否正在双指缩放（供视图跳过单指逻辑） */
  const pinching = ref(false)

  let dragState: { key: string; offX: number; offY: number } | null = null
  let panState: { sx: number; sy: number; px: number; py: number } | null = null

  /* ---------- 多点触控状态 ---------- */
  const pointers = new Map<number, Point>()
  let pinchBase: { dist: number; scale: number; worldX: number; worldY: number } | null = null
  let lastTapAt = 0
  let lastTapPos: Point | null = null

  function clamp(s: number) {
    return Math.min(maxS, Math.max(minS, s))
  }

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
    const ns = clamp(scale.value * k)
    pan.value = {
      x: pan.value.x - p.x * (ns - scale.value),
      y: pan.value.y - p.y * (ns - scale.value),
    }
    scale.value = ns
  }

  /* ---------- 双指缩放 ---------- */
  /** 记录触点；返回是否进入双指状态 */
  function trackPointerDown(evt: PointerEvent): boolean {
    if (evt.pointerType === 'touch') {
      pointers.set(evt.pointerId, { x: evt.clientX, y: evt.clientY })
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()]
        const rect = svgEl.value!.getBoundingClientRect()
        const mx = (a.x + b.x) / 2 - rect.left
        const my = (a.y + b.y) / 2 - rect.top
        // 记录两指中心对应的世界坐标，缩放时保持该点不动
        pinchBase = {
          dist: Math.max(Math.hypot(a.x - b.x, a.y - b.y), 1),
          scale: scale.value,
          worldX: (mx - pan.value.x) / scale.value,
          worldY: (my - pan.value.y) / scale.value,
        }
        pinching.value = true
        // 中止单指拖拽/平移
        dragState = null
        panState = null
        dragging.value = null
        return true
      }
    }
    return false
  }

  /** 处理触点移动；返回 true 表示已被捏合消费 */
  function trackPointerMove(evt: PointerEvent): boolean {
    if (evt.pointerType !== 'touch') return false
    if (!pointers.has(evt.pointerId)) return false
    pointers.set(evt.pointerId, { x: evt.clientX, y: evt.clientY })

    if (pointers.size === 2 && pinchBase) {
      const [a, b] = [...pointers.values()]
      const rect = svgEl.value!.getBoundingClientRect()
      const dist = Math.hypot(a.x - b.x, a.y - b.y)
      const ns = clamp(pinchBase.scale * (dist / pinchBase.dist))
      const mx = (a.x + b.x) / 2 - rect.left
      const my = (a.y + b.y) / 2 - rect.top
      pan.value = {
        x: mx - pinchBase.worldX * ns,
        y: my - pinchBase.worldY * ns,
      }
      scale.value = ns
      return true
    }
    return false
  }

  function trackPointerUp(evt: PointerEvent) {
    if (evt.pointerType !== 'touch') return
    pointers.delete(evt.pointerId)
    if (pointers.size < 2) {
      pinchBase = null
      pinching.value = false
    }
  }

  /** 双击触屏：放大 / 还原 */
  function handleDoubleTap(evt: PointerEvent | MouseEvent, zoomIn = 1.6): boolean {
    const now = Date.now()
    const p = { x: evt.clientX, y: evt.clientY }
    const isDouble = lastTapPos
      && now - lastTapAt < 320
      && Math.hypot(p.x - lastTapPos.x, p.y - lastTapPos.y) < 40
    lastTapAt = now
    lastTapPos = p
    if (!isDouble) return false

    if (scale.value > (opts.min ?? 0.2) * 1.8) {
      // 已放大 → 还原
      setZoom(1)
    } else {
      const w = toWorld(evt)
      const ns = clamp(scale.value * zoomIn)
      const rect = svgEl.value!.getBoundingClientRect()
      const cx = evt.clientX - rect.left
      const cy = evt.clientY - rect.top
      pan.value = { x: cx - w.x * ns, y: cy - w.y * ns }
      scale.value = ns
    }
    return true
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
    if (pinching.value) return
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
    scale.value = clamp(scale.value * k)
  }

  function setZoom(z: number) {
    scale.value = clamp(z)
  }

  /** 适应窗口：传入内容包围盒 */
  function fit(box: { minX: number; minY: number; maxX: number; maxY: number }, pad = 60) {
    const rect = svgEl.value?.getBoundingClientRect()
    if (!rect) return
    const w = Math.max(box.maxX - box.minX, 1)
    const h = Math.max(box.maxY - box.minY, 1)
    const s = Math.min((rect.width - pad * 2) / w, (rect.height - pad * 2) / h, 1.5)
    scale.value = clamp(s)
    pan.value = { x: pad - box.minX * scale.value, y: pad - box.minY * scale.value }
  }

  return {
    scale, pan, svgEl, dragging, pinching,
    toWorld, onWheel, startPan, startDrag, onMove, endDrag, zoom, setZoom, fit,
    trackPointerDown, trackPointerMove, trackPointerUp, handleDoubleTap,
  }
}
