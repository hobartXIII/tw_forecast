/** ForecastQuery：目前時段、預報、更新狀態、日期查詢（假的資料庫）。對應 tests/frontend/test_frontend_repository.py。 */
import { describe, expect, it } from "vitest";

import { ForecastQuery, latestBatch, onlyFullPeriods, toForecastRow } from "../src/lib/repository";
import { fakeClient, forecastRows, tw } from "./fakes";

const NOW = tw(2026, 9, 21, 10);
const FIRST = tw(2026, 9, 20, 6); // 昨天 06:00 起，共 4 天

const query = (rows = forecastRows(FIRST), status: Record<string, unknown>[] = [], errors = {}) =>
  new ForecastQuery(fakeClient({ weather_forecasts: rows, pipeline_status: status }, errors));

describe("current", () => {
  it("回傳涵蓋現在的時段，22 個縣市", async () => {
    const rows = await query().current(NOW);
    expect(rows).toHaveLength(22);
    expect(rows.every((r) => r.forecast_time_start <= NOW && r.forecast_time_end > NOW)).toBe(true);
  });

  it("資料過期時退回最近一個已開始的時段", async () => {
    const rows = await query().current(tw(2026, 10, 30, 10)); // 所有時段都已結束
    expect(rows).toHaveLength(22);
    expect(new Set(rows.map((r) => r.forecast_time_start.getTime())).size).toBe(1);
    const latest = Math.max(...forecastRows(FIRST).map((r) => new Date(String(r.forecast_time_start)).getTime()));
    expect(rows[0].forecast_time_start.getTime()).toBe(latest);
  });

  it("還沒有任何時段開始時取最早的未來時段", async () => {
    const rows = await query().current(tw(2026, 9, 1, 10));
    expect(rows[0].forecast_time_start).toEqual(FIRST);
  });

  it("沒有資料時回傳空陣列", async () => {
    expect(await query([]).current(NOW)).toEqual([]);
  });

  it("資料庫回傳錯誤時拋出例外", async () => {
    await expect(query(undefined, [], { weather_forecasts: "boom" }).current(NOW)).rejects.toThrow("boom");
  });
});

describe("forecast", () => {
  it("回傳尚未結束的時段並依時間排序", async () => {
    const rows = await query().forecast(NOW);
    expect(rows.every((r) => r.forecast_time_end > NOW)).toBe(true);
    const starts = rows.map((r) => r.forecast_time_start.getTime());
    expect(starts).toEqual([...starts].sort((a, b) => a - b));
  });

  it("只保留最新一批", async () => {
    const old = forecastRows(FIRST, 4, "2026-09-21T06:30:00+08:00");
    const fresh = forecastRows(FIRST, 4, "2026-09-21T09:30:00+08:00");
    const rows = await query([...old, ...fresh]).forecast(NOW);
    expect(new Set(rows.map((r) => r.updated_at.getTime())).size).toBe(1);
    expect(rows).toHaveLength((await query(fresh).forecast(NOW)).length);
  });
});

describe("latestBatch / onlyFullPeriods / toForecastRow", () => {
  it("latestBatch 處理空陣列", () => {
    expect(latestBatch([])).toEqual([]);
  });

  it("onlyFullPeriods 去掉被縮短的時段", () => {
    const rows = forecastRows(FIRST, 1).slice(0, 2).map(toForecastRow);
    rows[0].forecast_time_start = new Date(rows[0].forecast_time_start.getTime() + 6 * 3600_000);
    expect(onlyFullPeriods(rows)).toHaveLength(1);
  });

  it("NUMERIC 欄位是字串時轉成數字，空值維持 null", () => {
    const row = toForecastRow({ ...forecastRows(FIRST, 1)[0], min_temp: "18.5", rain_probability: null });
    expect(row.min_temp).toBe(18.5);
    expect(row.rain_probability).toBeNull();
  });
});

describe("updateStatus", () => {
  it("時間轉成 Date，沒有值維持 null", async () => {
    const status = [{ trigger_type: "schedule", last_success_at: "2026-09-21T01:30:00+00:00", last_run_at: null }];
    const [row] = await query(undefined, status).updateStatus();
    expect(row.last_success_at).toEqual(tw(2026, 9, 21, 9, 30));
    expect(row.last_run_at).toBeNull();
  });
});

describe("availableDates", () => {
  it("列出視窗內有完整時段的台灣日期", async () => {
    expect(await query().availableDates(NOW, "臺北市"))
      .toEqual(["2026-09-20", "2026-09-21", "2026-09-22", "2026-09-23"]);
  });

  it("忽略被縮短的時段與視窗外的日期", async () => {
    const short = forecastRows(FIRST, 1)
      .filter((r) => r.location_name === "臺北市").slice(0, 1)
      .map((r) => ({ ...r, forecast_time_start: new Date(new Date(String(r.forecast_time_start)).getTime() + 6 * 3600_000).toISOString() }));
    expect(await query(short).availableDates(NOW, "臺北市")).toEqual([]);
    expect(await query(forecastRows(tw(2026, 12, 1, 6), 1)).availableDates(NOW, "臺北市")).toEqual([]);
  });
});

describe("day", () => {
  it("只回傳該日、指定縣市的完整時段", async () => {
    const rows = await query().day("2026-09-21", ["臺北市", "臺中市"]);
    expect(new Set(rows.map((r) => r.location_name))).toEqual(new Set(["臺北市", "臺中市"]));
    expect(rows).toHaveLength(4);
    expect(await query().day("2030-01-01", ["臺北市"])).toEqual([]);
  });
});
