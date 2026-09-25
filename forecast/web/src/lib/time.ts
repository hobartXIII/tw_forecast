/** 台灣時間（UTC+8，沒有日光節約時間）的換算與格式化。

時間一律以 Date（絕對時間點）傳遞，只在顯示或需要「台灣日期」時才換算；不依賴瀏覽器所在時區。
台灣日期以 "YYYY-MM-DD" 字串表示。
*/

const OFFSET_MS = 8 * 3600_000;
export const DAY_MS = 24 * 3600_000;

export interface TaipeiParts {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
}

/** 某個時間點在台灣的年月日時分。 */
export function taipeiParts(d: Date): TaipeiParts {
  const t = new Date(d.getTime() + OFFSET_MS);
  return {
    year: t.getUTCFullYear(), month: t.getUTCMonth() + 1, day: t.getUTCDate(),
    hour: t.getUTCHours(), minute: t.getUTCMinutes(),
  };
}

const pad = (n: number) => String(n).padStart(2, "0");

/** 「09/21」 */
export function formatMD(d: Date): string {
  const p = taipeiParts(d);
  return `${pad(p.month)}/${pad(p.day)}`;
}

/** 「06:00」 */
export function formatHM(d: Date): string {
  const p = taipeiParts(d);
  return `${pad(p.hour)}:${pad(p.minute)}`;
}

/** 「09/21 06:00」 */
export function formatMDHM(d: Date): string {
  return `${formatMD(d)} ${formatHM(d)}`;
}

/** 台灣日期 "YYYY-MM-DD"。 */
export function dateKey(d: Date): string {
  const p = taipeiParts(d);
  return `${p.year}-${pad(p.month)}-${pad(p.day)}`;
}

/** 台灣日期當天 00:00 的時間點。 */
export function dayStart(key: string): Date {
  return new Date(`${key}T00:00:00+08:00`);
}

/** 台灣日期加減天數。 */
export function addDays(key: string, days: number): string {
  return dateKey(new Date(dayStart(key).getTime() + days * DAY_MS));
}
