/** 間隔倒數的文字（純函式）：「距上次更新僅 N 分鐘」與「還需 mm:ss」都由同一個剩餘秒數推導，兩者保證同步。 */

/** 剩餘秒數轉 mm:ss（無條件進位到整秒；小於等於 0 顯示 00:00）。 */
export function formatMmss(seconds: number): string {
  const total = Math.max(0, Math.ceil(seconds));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

/** 需間隔 minIntervalMinutes 分鐘、還剩 leftSeconds 秒時，已過幾分鐘（整數，不小於 0）。 */
export function elapsedMinutes(minIntervalMinutes: number, leftSeconds: number): number {
  return Math.max(0, Math.floor((minIntervalMinutes * 60 - Math.max(0, leftSeconds)) / 60));
}
