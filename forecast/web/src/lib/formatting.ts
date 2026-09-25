/** 顯示用的小工具：日夜判斷、天氣圖示、時間文字。 */
import type { StatusRow } from "./repository";
import { isMissing } from "./temperature";
import { formatMDHM, taipeiParts } from "./time";

/** 依時段中點判斷日夜：中點在 06:00～18:00（台灣時間）為日間，其餘為夜間。

氣象署時段以 06 時與 18 時為日夜分界；第一個時段可能被截短（如 00:00–06:00、12:00–18:00），
用中點判斷仍然正確。
*/
export function isNight(start: Date, end: Date): boolean {
  const mid = new Date((start.getTime() + end.getTime()) / 2);
  const hour = taipeiParts(mid).hour;
  return !(hour >= 6 && hour < 18);
}

/** 依「天氣現象」文字與日夜回傳對應 emoji（無法判斷時回傳空字串）。

有太陽的圖示夜間不可出現，晴改月亮、其餘改雲；雨／雷／雪／霧沒有太陽，日夜相同。
*/
export function weatherIcon(text: string | null | undefined, night = false): string {
  if (!text) return "";
  for (const [keyword, icon] of [["雷", "⛈️"], ["雨", "🌧️"], ["雪", "❄️"], ["霧", "🌫️"]]) {
    if (text.includes(keyword)) return icon;
  }
  if (text.startsWith("晴")) {
    if (text.includes("多雲")) return night ? "🌙☁️" : "🌤️"; // 晴時多雲
    return night ? "🌙" : "☀️";
  }
  if (text.includes("陰")) return "☁️"; // 陰、陰時多雲、多雲時陰 … 以陰天為主
  if (text.includes("多雲")) return night ? "☁️" : "⛅"; // 多雲、多雲時晴
  return "🌡️";
}

/** 預報時段文字，如「09/21 18:00 ~ 09/22 06:00」。 */
export function formatRange(start: Date, end: Date): string {
  return `${formatMDHM(start)} ~ ${formatMDHM(end)}`;
}

/** 某來源（schedule / manual）最後一次成功更新的時間文字；沒有紀錄回傳「—」。 */
export function formatLastUpdate(rows: StatusRow[] | null, trigger: string): string {
  const row = (rows ?? []).find((r) => r.trigger_type === trigger && r.last_success_at !== null);
  return row?.last_success_at ? formatMDHM(row.last_success_at) : "—";
}

/** 數值加單位；沒有值顯示「—」。digits 為小數位數。 */
export function formatValue(value: number | null | undefined, unit: string, digits = 0): string {
  return isMissing(value) ? "—" : `${value.toFixed(digits)} ${unit}`;
}
