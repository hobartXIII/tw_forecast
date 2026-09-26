/** 摘要卡片輪播的換頁規則（純函式）：頁碼循環、手指滑動方向。 */

/** 自動輪播的間隔（滑鼠移上去、鍵盤焦點在輪播內或手指觸碰時暫停）。 */
export const CAROUSEL_INTERVAL_MS = 4000;
/** 手指水平滑動超過這麼多 px 才算換頁（小於此值視為點擊或誤觸）。 */
export const SWIPE_THRESHOLD_PX = 40;

/** 把頁碼換算到 0～count-1（可為負數，例如第一張再往前是最後一張）；沒有頁時回傳 0。 */
export function wrapIndex(index: number, count: number): number {
  return count > 0 ? ((index % count) + count) % count : 0;
}

/** 手指滑動的水平位移 → 換頁方向：往左滑（dx < 0）看下一張為 1，往右滑為 -1，不夠遠或垂直為主（捲動頁面）為 0。 */
export function swipeStep(dx: number, dy = 0, threshold = SWIPE_THRESHOLD_PX): -1 | 0 | 1 {
  if (Math.abs(dx) < threshold || Math.abs(dy) > Math.abs(dx)) return 0;
  return dx < 0 ? 1 : -1;
}
