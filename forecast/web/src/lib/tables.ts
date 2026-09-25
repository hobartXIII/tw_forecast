/** 明細表格的資料整理（純函式）。 */
import { isNight, weatherIcon } from "./formatting";
import type { CityRow, ScopedRow, TableColumnKey } from "./scope";
import { formatHM, formatMDHM } from "./time";

export interface TableRow {
  city: string;
  region: string | null;
  period: string;
  weather: string;
  min: number | null;
  max: number | null;
  avg: number | null;
  rain: number | null;
  comfort: string;
}

/** 表格欄位與中文標題（顯示順序）。 */
export const TABLE_COLUMNS: { key: keyof TableRow; label: string }[] = [
  { key: "city", label: "縣市" },
  { key: "region", label: "地區" },
  { key: "period", label: "時段" },
  { key: "weather", label: "天氣現象" },
  { key: "min", label: "最低 (°C)" },
  { key: "max", label: "最高 (°C)" },
  { key: "avg", label: "平均 (°C)" },
  { key: "rain", label: "降雨機率" },
  { key: "comfort", label: "舒適度" },
];

/** 依範圍隱藏欄位後的表格欄位。 */
export function visibleColumns(drop: TableColumnKey[]) {
  return TABLE_COLUMNS.filter((c) => !(drop as string[]).includes(c.key));
}

const round1 = (v: number | null) => (v === null ? null : Math.round(v * 10) / 10);

/** 預報列 → 明細表格列。天氣圖示依每列自己的時段判斷日夜；dated=true 時時段文字含日期（跨日的表格用）。 */
export function makeTable(src: ScopedRow[], dated: boolean): TableRow[] {
  return src.map((r) => {
    const s = r.forecast_time_start;
    const e = r.forecast_time_end;
    const w = r.weather_condition;
    return {
      city: r.location_name,
      region: r.region,
      period: `${dated ? formatMDHM(s) : formatHM(s)}~${formatHM(e)}`,
      weather: w ? `${weatherIcon(w, isNight(s, e))} ${w}`.trim() : "—",
      min: r.min_temp,
      max: r.max_temp,
      avg: round1(r.avg),
      rain: r.rain_probability,
      comfort: r.comfort_index ?? "—",
    };
  });
}

/** 每個縣市在 after 之後的 n 個時段，依縣市（地區順序）→ 時間排序。 */
export function nextPeriods<T extends CityRow>(forecast: T[], after: Date, n = 2): T[] {
  const later = forecast
    .filter((r) => r.forecast_time_start.getTime() > after.getTime())
    .sort((a, b) => a.order - b.order || a.forecast_time_start.getTime() - b.forecast_time_start.getTime());
  const taken = new Map<string, number>();
  return later.filter((r) => {
    const count = taken.get(r.location_name) ?? 0;
    taken.set(r.location_name, count + 1);
    return count < n;
  });
}
