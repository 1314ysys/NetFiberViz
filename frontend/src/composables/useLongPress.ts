import { onBeforeUnmount } from 'vue'

/**
 * 长按手势（移动端替代右键菜单）。
 *
 * 用法：
 *   const lp = useLongPress()
 *   <div @pointerdown="lp.start($event, () => openMenu(x, y))"
 *        @pointerup="lp.cancel" @pointermove="lp.cancel" @pointercancel="lp.cancel" />
 *
 * - 仅对 touch / pen 生效，鼠标不受影响（桌面仍用 contextmenu）
 * - 移动超过 10px 判定为滑动，取消长按
 */
export function useLongPress(delay = 480, moveTolerance = 10) {
  let timer: ReturnType<typeof setTimeout> | null = null
  let startPt: { x: number; y: number } | null = null

  function clear() {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    startPt = null
  }

  function start(evt: PointerEvent, cb: (pos: { x: number; y: number }) => void) {
    if (evt.pointerType === 'mouse') return
    clear()
    startPt = { x: evt.clientX, y: evt.clientY }
    const { clientX, clientY } = evt
    timer = setTimeout(() => {
      timer = null
      // 轻微震动反馈（支持的设备）
      try { navigator.vibrate?.(12) } catch { /* 忽略 */ }
      cb({ x: clientX, y: clientY })
    }, delay)
  }

  function move(evt: PointerEvent) {
    if (!startPt || !timer) return
    const d = Math.hypot(evt.clientX - startPt.x, evt.clientY - startPt.y)
    if (d > moveTolerance) clear()
  }

  onBeforeUnmount(clear)

  return { start, cancel: clear, move }
}
