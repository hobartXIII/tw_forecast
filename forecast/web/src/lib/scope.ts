/** 目前的篩選範圍（地區與縣市互斥）與依範圍整理資料的純函式。

輸入：使用者選的地區、縣市。輸出：顯示層級、範圍內的縣市清單、依範圍篩過的資料、圖表用的多系列長表。
*/
import type { ForecastRow } from "./repository";
import { ALL_REGIONS, CITY_ORDER, REGION_NAMES, citiesIn, regionOf } from "./regions";
import { displayTemp } from "./temperature";

/** 加上所屬地區與縣市順序的預報列。 */
export interface CityRow extends ForecastRow {
  region: string | null;
  /** 縣市在北 → 離島順序中的位置，查不到為 99。 */
  order: number;
}

/** 再加上平均溫（avg_temp 沒有值時以最高、最低溫的中點代替）。 */
export interface ScopedRow extends CityRow {
  avg: number | null;
}

export type Level = "all" | "region" | "city";
export type SeriesColumn = "max_temp" | "min_temp" | "avg" | "rain_probability";
export type TableColumnKey = "city" | "region";

export interface SeriesPoint {
  series: string;
  start: Date;
  value: number | null;
}

export function addRegion(rows: ForecastRow[]): CityRow[] {
  return rows.map((r) => {
    const i = CITY_ORDER.indexOf(r.location_name);
    return { ...r, region: regionOf(r.location_name), order: i >= 0 ? i : 99 };
  });
}

export function withAvg<T extends CityRow>(rows: T[]): (T & { avg: number | null })[] {
  return rows.map((r) => ({ ...r, avg: displayTemp(r) }));
}

const mean = (values: (number | null)[]): number | null => {
  const nums = values.filter((v): v is number => v !== null && !Number.isNaN(v));
  return nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null;
};

/** 篩選範圍。地區與縣市互斥：選了縣市時 region 應為「全部地區」；city 為 null 代表沒有選縣市。 */
export class Scope {
  constructor(readonly region: string = ALL_REGIONS, readonly city: string | null = null) {}

  /** 顯示層級：city（單一縣市，依時段）、all（全台，依地區平均）、region（單一地區，依縣市）。 */
  get level(): Level {
    if (this.city) return "city";
    return this.region === ALL_REGIONS ? "all" : "region";
  }

  /** 單一縣市時，該縣市所屬的地區（地圖與對照範圍用）；其他層級為 null。 */
  get homeRegion(): string | null {
    return this.city ? regionOf(this.city) : null;
  }

  /** 地圖與「目前時段」範圍內的縣市（單一縣市時是它所屬地區的全部縣市，作為對照）。 */
  get regionCities(): string[] {
    return citiesIn(this.homeRegion ?? this.region);
  }

  /** 趨勢圖、明細與日期查詢實際涵蓋的縣市。 */
  get cities(): string[] {
    return this.city ? [this.city] : this.regionCities;
  }

  /** 說明文字用的範圍名稱。 */
  get label(): string {
    return { all: "全台各地區平均", region: `${this.region}各縣市`, city: this.city ?? "" }[this.level];
  }

  /** 表格要隱藏的欄位：單一縣市不需要「縣市」「地區」，單一地區不需要「地區」，全台全部顯示。 */
  tableDropColumns(): TableColumnKey[] {
    if (this.city) return ["city", "region"];
    return this.region !== ALL_REGIONS ? ["region"] : [];
  }

  /** 「目前時段」資料中屬於地圖範圍的縣市，依縣市順序排序。 */
  filterCurrent<T extends CityRow>(current: T[]): T[] {
    const cities = new Set(this.regionCities);
    return current.filter((r) => cities.has(r.location_name)).sort((a, b) => a.order - b.order);
  }

  /** 趨勢與明細用的預報資料（加上平均溫 avg）；沒有資料（過期或範圍內為空）回傳 null。 */
  filterForecast(forecast: CityRow[]): ScopedRow[] | null {
    const cities = new Set(this.cities);
    const fc = forecast.filter((r) => cities.has(r.location_name));
    return fc.length ? withAvg(fc) : null;
  }

  /** 多系列長表（系列、時段起點、值）與圖例順序。

  全台 → 每地區平均一條線；單一地區 → 每縣市一條線；單一縣市 → 一條線。
  同一系列、同一時段有多列時取平均（忽略沒有值的列）。
  */
  seriesData(forecast: ScopedRow[], column: SeriesColumn): { data: SeriesPoint[]; order: string[] } {
    const keyOf = (r: ScopedRow) => (this.level === "all" ? r.region : r.location_name);
    const groups = new Map<string, { series: string; start: Date; values: (number | null)[] }>();
    for (const r of forecast) {
      const series = keyOf(r);
      if (series === null) continue;
      const id = `${series}|${r.forecast_time_start.getTime()}`;
      const group = groups.get(id) ?? { series, start: r.forecast_time_start, values: [] };
      group.values.push(r[column]);
      groups.set(id, group);
    }
    const present = new Set([...groups.values()].map((g) => g.series));
    const order = (this.level === "all" ? REGION_NAMES : CITY_ORDER).filter((n) => present.has(n));
    const data = [...groups.values()]
      .map((g) => ({ series: g.series, start: g.start, value: mean(g.values) }))
      .sort((a, b) => order.indexOf(a.series) - order.indexOf(b.series) || a.start.getTime() - b.start.getTime());
    return { data, order };
  }
}
