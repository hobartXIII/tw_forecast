/** 測試用的假物件與資料產生器：不連網、不連資料庫（對應 Python 的 tests/fakes.py）。 */
import type { SupabaseClient } from "@supabase/supabase-js";

import { CITY_ORDER } from "../src/lib/regions";

type Row = Record<string, unknown>;

/** 台灣時間的 Date，例如 tw(2026, 9, 21, 6) = 2026-09-21 06:00 (+08:00)。 */
export function tw(year: number, month: number, day: number, hour = 0, minute = 0): Date {
  const p = (n: number) => String(n).padStart(2, "0");
  return new Date(`${year}-${p(month)}-${p(day)}T${p(hour)}:${p(minute)}:00+08:00`);
}

const time = (v: unknown) => new Date(String(v)).getTime();

/** 模仿 supabase-js 的查詢串接（select／lte／lt／gte／gt／eq／in／order／limit），await 時回傳 { data, error }。 */
class FakeQuery implements PromiseLike<{ data: Row[] | null; error: { message: string } | null }> {
  private rows: Row[];
  private cols: string[] | null = null;
  private max: number | null = null;

  constructor(rows: Row[], private readonly error: string | null) {
    this.rows = [...rows];
  }

  select(cols = "*") {
    this.cols = cols === "*" ? null : cols.split(",");
    return this;
  }

  private cmp(col: string, value: string, fn: (a: number, b: number) => boolean) {
    this.rows = this.rows.filter((r) => fn(time(r[col]), time(value)));
    return this;
  }

  lte(col: string, v: string) { return this.cmp(col, v, (a, b) => a <= b); }
  lt(col: string, v: string) { return this.cmp(col, v, (a, b) => a < b); }
  gte(col: string, v: string) { return this.cmp(col, v, (a, b) => a >= b); }
  gt(col: string, v: string) { return this.cmp(col, v, (a, b) => a > b); }

  eq(col: string, v: unknown) {
    this.rows = this.rows.filter((r) => r[col] === v);
    return this;
  }

  in(col: string, values: unknown[]) {
    this.rows = this.rows.filter((r) => values.includes(r[col]));
    return this;
  }

  order(col: string, { ascending = true } = {}) {
    this.rows.sort((a, b) => (ascending ? 1 : -1) * (time(a[col]) - time(b[col])));
    return this;
  }

  limit(n: number) {
    this.max = n;
    return this;
  }

  then<A, B>(
    ok?: ((v: { data: Row[] | null; error: { message: string } | null }) => A | PromiseLike<A>) | null,
    fail?: ((reason: unknown) => B | PromiseLike<B>) | null,
  ): PromiseLike<A | B> {
    let rows = this.max === null ? this.rows : this.rows.slice(0, this.max);
    if (this.cols) rows = rows.map((r) => Object.fromEntries(this.cols!.map((c) => [c, r[c]])));
    const result = this.error
      ? { data: null, error: { message: this.error } }
      : { data: rows.map((r) => ({ ...r })), error: null };
    return Promise.resolve(result).then(ok, fail);
  }
}

/** 假 Supabase：tables 為各表的資料；errors 指定某張表的查詢要回傳錯誤。 */
export function fakeClient(tables: Record<string, Row[]>, errors: Record<string, string> = {}): SupabaseClient {
  return { from: (name: string) => new FakeQuery(tables[name] ?? [], errors[name] ?? null) } as unknown as SupabaseClient;
}

/** 假預報資料：每個縣市、每天 06:00~18:00 與 18:00~隔天 06:00 兩個完整時段。溫度隨縣市與時段變化。 */
export function forecastRows(firstDay: Date, days = 4, updatedAt = "2026-09-21T09:30:00+08:00"): Row[] {
  const rows: Row[] = [];
  CITY_ORDER.forEach((city, c) => {
    for (let d = 0; d < days * 2; d++) {
      const start = new Date(firstDay.getTime() + d * 12 * 3600_000);
      rows.push({
        location_name: city,
        forecast_time_start: start.toISOString(),
        forecast_time_end: new Date(start.getTime() + 12 * 3600_000).toISOString(),
        latitude: 22.0 + c * 0.15, longitude: 120.0 + c * 0.08,
        weather_condition: ["晴", "多雲", "陰短暫雨"][d % 3],
        min_temp: 18.0 + c * 0.5, max_temp: 24.0 + c * 0.5 + d, avg_temp: 21.0 + c * 0.5,
        rain_probability: d > 5 ? null : (d * 10 + c) % 100,
        comfort_index: "舒適", updated_at: updatedAt,
      });
    }
  });
  return rows;
}
