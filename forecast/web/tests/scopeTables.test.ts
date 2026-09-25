/** 篩選範圍（Scope）與明細表格整理。對應 tests/frontend/test_scope_and_tables.py。 */
import { describe, expect, it } from "vitest";

import { ALL_REGIONS, CITY_ORDER } from "../src/lib/regions";
import { toForecastRow } from "../src/lib/repository";
import { Scope, addRegion, withAvg, type CityRow } from "../src/lib/scope";
import { makeTable, nextPeriods, visibleColumns } from "../src/lib/tables";
import { forecastRows, tw } from "./fakes";

const FIRST = tw(2026, 9, 21, 6);
const forecast = (): CityRow[] => addRegion(forecastRows(FIRST, 2).map(toForecastRow));

describe("addRegion", () => {
  it("加上地區與縣市順序，查不到的縣市順序為 99", () => {
    const row = forecast().find((r) => r.location_name === "臺中市")!;
    expect(row.region).toBe("中部地區");
    expect(row.order).toBe(CITY_ORDER.indexOf("臺中市"));
    const [unknown] = addRegion([{ ...toForecastRow(forecastRows(FIRST, 1)[0]), location_name: "火星市" }]);
    expect(unknown.order).toBe(99);
    expect(unknown.region).toBeNull();
  });
});

describe("Scope", () => {
  it.each([
    [new Scope(), "all", CITY_ORDER, "全台各地區平均", []],
    [new Scope("離島地區"), "region", ["澎湖縣", "金門縣", "連江縣"], "離島地區各縣市", ["region"]],
    [new Scope(ALL_REGIONS, "臺中市"), "city", ["臺中市"], "臺中市", ["city", "region"]],
  ])("層級、縣市、標籤、隱藏欄位 %#", (scope, level, cities, label, drop) => {
    expect([scope.level, scope.cities, scope.label, scope.tableDropColumns()]).toEqual([level, cities, label, drop]);
  });

  it("單一縣市時地圖範圍是它所屬的地區", () => {
    const scope = new Scope(ALL_REGIONS, "臺中市");
    expect(scope.homeRegion).toBe("中部地區");
    expect(scope.regionCities).toEqual(["苗栗縣", "臺中市", "彰化縣", "南投縣", "雲林縣"]);
    expect(new Scope().homeRegion).toBeNull();
  });

  it("filterCurrent 只留範圍內的縣市並依順序排序", () => {
    const fc = forecast();
    const first = Math.min(...fc.map((r) => r.forecast_time_start.getTime()));
    const current = fc.filter((r) => r.forecast_time_start.getTime() === first).reverse();
    expect(new Scope("東部地區").filterCurrent(current).map((r) => r.location_name)).toEqual(["宜蘭縣", "花蓮縣", "臺東縣"]);
  });

  it("filterForecast 加上 avg，沒有資料回傳 null", () => {
    const fc = forecast();
    const taipei = new Scope(ALL_REGIONS, "臺北市").filterForecast(fc)!;
    expect(new Set(taipei.map((r) => r.location_name))).toEqual(new Set(["臺北市"]));
    expect(taipei.every((r) => "avg" in r)).toBe(true);
    expect(new Scope().filterForecast([])).toBeNull();
    expect(new Scope(ALL_REGIONS, "臺北市").filterForecast(fc.filter((r) => r.location_name === "臺中市"))).toBeNull();
  });

  it("seriesData 全台時依地區平均", () => {
    const scope = new Scope();
    const fc = scope.filterForecast(forecast())!;
    const { data, order } = scope.seriesData(fc, "max_temp");
    expect(order).toEqual(["北部地區", "中部地區", "南部地區", "東部地區", "離島地區"]);
    const first = Math.min(...fc.map((r) => r.forecast_time_start.getTime()));
    const north = data.find((p) => p.series === "北部地區" && p.start.getTime() === first)!;
    const expected = fc.filter((r) => r.region === "北部地區" && r.forecast_time_start.getTime() === first);
    expect(north.value).toBeCloseTo(expected.reduce((s, r) => s + r.max_temp!, 0) / expected.length);
  });

  it("seriesData 地區與縣市時每縣市一條線", () => {
    const islands = new Scope("離島地區");
    expect(islands.seriesData(islands.filterForecast(forecast())!, "avg").order).toEqual(["澎湖縣", "金門縣", "連江縣"]);
    const taipei = new Scope(ALL_REGIONS, "臺北市");
    const { data, order } = taipei.seriesData(taipei.filterForecast(forecast())!, "avg");
    expect(order).toEqual(["臺北市"]);
    expect(data).toHaveLength(4);
  });

  it("seriesData 全部沒有值的時段為 null", () => {
    const scope = new Scope(ALL_REGIONS, "臺北市");
    const fc = scope.filterForecast(forecast())!.map((r) => ({ ...r, rain_probability: null }));
    expect(scope.seriesData(fc, "rain_probability").data.every((p) => p.value === null)).toBe(true);
  });
});

describe("tables", () => {
  it("makeTable 的欄位與格式", () => {
    const src = withAvg(forecast().filter((r) => r.location_name === "臺北市").slice(0, 2));
    const table = makeTable(src, true);
    expect(table[0].period).toBe("09/21 06:00~18:00");
    expect(makeTable(src, false)[0].period).toBe("06:00~18:00");
    expect(table[0].weather).toBe("☀️ 晴"); // 日間晴
    expect(table[1].weather.startsWith("☁️")).toBe(true); // 夜間多雲
  });

  it("makeTable 缺值顯示「—」，平均溫四捨五入到一位", () => {
    const [row] = withAvg(forecast().slice(0, 1)).map((r) => ({ ...r, weather_condition: null, comfort_index: null, avg: 21.26 }));
    const [t] = makeTable([row], false);
    expect([t.weather, t.comfort, t.avg]).toEqual(["—", "—", 21.3]);
  });

  it("visibleColumns 依範圍隱藏欄位", () => {
    expect(visibleColumns(["city", "region"]).map((c) => c.label))
      .toEqual(["時段", "天氣現象", "最低 (°C)", "最高 (°C)", "平均 (°C)", "降雨機率", "舒適度"]);
  });

  it("nextPeriods 每縣市取 n 個、依縣市再依時間排序", () => {
    const later = nextPeriods(forecast(), FIRST, 2);
    expect(later.every((r) => r.forecast_time_start > FIRST)).toBe(true);
    const counts = new Map<string, number>();
    later.forEach((r) => counts.set(r.location_name, (counts.get(r.location_name) ?? 0) + 1));
    expect([...counts.values()].every((n) => n === 2)).toBe(true);
    expect([...new Set(later.map((r) => r.location_name))]).toEqual(CITY_ORDER);
    const first = later.filter((r) => r.location_name === CITY_ORDER[0]).map((r) => r.forecast_time_start.getTime());
    expect(first).toEqual([...first].sort((a, b) => a - b));
  });
});
