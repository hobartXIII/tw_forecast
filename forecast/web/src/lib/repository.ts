/** Supabase 唯讀查詢（使用 anon key，權限由 RLS 控制）。

輸入：Supabase 連線與查詢條件。輸出：時間欄位已轉成 Date 的資料列。
查詢結果不快取，每次載入都重新查詢（見 SPECIFICATION.md §8.1）。
*/
import type { SupabaseClient } from "@supabase/supabase-js";

import { FORECAST_TABLE, STATUS_TABLE } from "./config";
import { addDays, dateKey, dayStart } from "./time";

export const MAX_ROWS = 1000; // Supabase 單次查詢上限
const FULL_PERIOD_MS = 12 * 3600_000;

export interface ForecastRow {
  location_name: string;
  forecast_time_start: Date;
  forecast_time_end: Date;
  updated_at: Date;
  latitude: number | null;
  longitude: number | null;
  weather_condition: string | null;
  min_temp: number | null;
  max_temp: number | null;
  avg_temp: number | null;
  rain_probability: number | null;
  comfort_index: string | null;
}

export interface StatusRow {
  trigger_type: string;
  last_success_at: Date | null;
  last_run_at: Date | null;
}

type Raw = Record<string, unknown>;

const num = (v: unknown): number | null => (v === null || v === undefined || v === "" ? null : Number(v));
const str = (v: unknown): string | null => (v === null || v === undefined ? null : String(v));
const time = (v: unknown): Date | null => (v ? new Date(String(v)) : null);

/** 資料庫列 → ForecastRow（NUMERIC 欄位可能是字串，一律轉成數字）。 */
export function toForecastRow(r: Raw): ForecastRow {
  return {
    location_name: String(r.location_name),
    forecast_time_start: new Date(String(r.forecast_time_start)),
    forecast_time_end: new Date(String(r.forecast_time_end)),
    updated_at: new Date(String(r.updated_at)),
    latitude: num(r.latitude),
    longitude: num(r.longitude),
    weather_condition: str(r.weather_condition),
    min_temp: num(r.min_temp),
    max_temp: num(r.max_temp),
    avg_temp: num(r.avg_temp),
    rain_probability: num(r.rain_probability),
    comfort_index: str(r.comfort_index),
  };
}

/** 只保留最新一批寫入的資料。

每次流程一都以同一個 updated_at 寫入整批預報；但 CWA 第一個時段會隨時間縮短
（如 06:00~18:00 → 12:00~18:00），主鍵含 end，舊列會留在表中並與新列重疊。
資料表作為歷史存檔保留舊列，前端則只取最新批次以避免重複。
*/
export function latestBatch<T extends { updated_at: Date }>(rows: T[]): T[] {
  if (!rows.length) return rows;
  const latest = Math.max(...rows.map((r) => r.updated_at.getTime()));
  return rows.filter((r) => r.updated_at.getTime() === latest);
}

/** 只留完整的 12 小時時段（06:00~18:00、18:00~隔天 06:00）。

氣象署的第一個時段會隨時間被縮短，縮短後是不同主鍵的另一列，日期查詢不提供這些被縮短的資料；
完整時段的那一列是縮短之前寫入的，不會被覆蓋。
*/
export function onlyFullPeriods<T extends { forecast_time_start: Date; forecast_time_end: Date }>(rows: T[]): T[] {
  return rows.filter((r) => r.forecast_time_end.getTime() - r.forecast_time_start.getTime() === FULL_PERIOD_MS);
}

/** Supabase 回傳 { data, error }；有 error 就拋出，讓畫面顯示「讀取資料庫失敗」。 */
function rowsOf(result: { data: unknown; error: { message: string } | null }): Raw[] {
  if (result.error) throw new Error(result.error.message);
  return (result.data as Raw[] | null) ?? [];
}

/** 儀表板需要的所有讀取查詢。 */
export class ForecastQuery {
  constructor(private readonly sb: SupabaseClient) {}

  /** 「目前時段」：start <= now < end；沒有則取最接近現在的最新時段。 */
  async current(now: Date): Promise<ForecastRow[]> {
    const iso = now.toISOString();
    const table = () => this.sb.from(FORECAST_TABLE).select("*");
    let rows = rowsOf(await table().lte("forecast_time_start", iso).gt("forecast_time_end", iso).limit(MAX_ROWS));
    if (!rows.length) {
      // 先找最近一個已開始的時段，再找最近一個未開始的
      const fallbacks = [
        () => table().lte("forecast_time_start", iso).order("forecast_time_start", { ascending: false }),
        () => table().gt("forecast_time_start", iso).order("forecast_time_start"),
      ];
      for (const query of fallbacks) {
        rows = rowsOf(await query().limit(100));
        if (rows.length) {
          const first = rows[0].forecast_time_start;
          rows = rows.filter((r) => r.forecast_time_start === first);
          break;
        }
      }
    }
    return latestBatch(rows.map(toForecastRow));
  }

  /** 尚未結束的所有時段（未來約 7 天，全臺約 330 列），依時段排序。 */
  async forecast(now: Date): Promise<ForecastRow[]> {
    const rows = rowsOf(await this.sb.from(FORECAST_TABLE).select("*")
      .gt("forecast_time_end", now.toISOString())
      .order("forecast_time_start").limit(MAX_ROWS));
    return latestBatch(rows.map(toForecastRow));
  }

  /** 讀 pipeline_status（排程、手動各一列）；讀取失敗會拋例外。 */
  async updateStatus(): Promise<StatusRow[]> {
    const rows = rowsOf(await this.sb.from(STATUS_TABLE).select("*"));
    return rows.map((r) => ({
      trigger_type: String(r.trigger_type),
      last_success_at: time(r.last_success_at),
      last_run_at: time(r.last_run_at),
    }));
  }

  /** 日期查詢的可選日期：今天前 back 天到後 ahead 天之間，資料庫裡有完整 12 小時時段的台灣日期（由小到大）。

  所有縣市在同一批寫入，所以只查一個縣市（probeCity）就能得到日期清單，筆數約 30 而不是數百。
  夜間時段（18:00～隔天 06:00）以「起點」的日期歸屬。
  */
  async availableDates(now: Date, probeCity: string, back = 3, ahead = 7): Promise<string[]> {
    const today = dateKey(now);
    const lo = dayStart(addDays(today, -back));
    const hi = dayStart(addDays(today, ahead + 1));
    const rows = rowsOf(await this.sb.from(FORECAST_TABLE).select("forecast_time_start,forecast_time_end")
      .eq("location_name", probeCity)
      .gte("forecast_time_start", lo.toISOString()).lt("forecast_time_start", hi.toISOString())
      .limit(MAX_ROWS));
    const periods = rows.map((r) => ({
      forecast_time_start: new Date(String(r.forecast_time_start)),
      forecast_time_end: new Date(String(r.forecast_time_end)),
    }));
    return [...new Set(onlyFullPeriods(periods).map((p) => dateKey(p.forecast_time_start)))].sort();
  }

  /** 指定台灣日期（起點落在該日）、指定縣市的完整 12 小時時段，約 22 縣市 × 2 個時段。

  完整時段的主鍵（縣市、起、迄）唯一，不會有重複列，所以不需要另外去重，也不能用 latestBatch
  （歷史列的 updated_at 不是全表最大值）。
  */
  async day(key: string, cities: string[]): Promise<ForecastRow[]> {
    const lo = dayStart(key);
    const rows = rowsOf(await this.sb.from(FORECAST_TABLE).select("*").in("location_name", cities)
      .gte("forecast_time_start", lo.toISOString())
      .lt("forecast_time_start", dayStart(addDays(key, 1)).toISOString())
      .limit(MAX_ROWS));
    return onlyFullPeriods(rows.map(toForecastRow));
  }
}
