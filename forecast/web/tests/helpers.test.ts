/** 小型純函式：時間、地區、格式化、溫度級距、降雨色階、更新門檻、倒數。對應 test_pure_helpers.py 與 test_countdown.py。 */
import { describe, expect, it } from "vitest";

import { elapsedMinutes, formatMmss } from "../src/lib/countdown";
import { formatLastUpdate, formatRange, formatValue, isNight, weatherIcon } from "../src/lib/formatting";
import { RAIN_ALERT, RAIN_BANDS, rainColor } from "../src/lib/rain";
import { ALL_REGIONS, CITY_ORDER, CITY_TO_REGION, citiesIn, regionOf } from "../src/lib/regions";
import type { StatusRow } from "../src/lib/repository";
import { BANDS, TEXT_COLORS, bandIndex, displayTemp, tempColor, tempText, textColor } from "../src/lib/temperature";
import { addDays, dateKey, dayStart, formatMDHM } from "../src/lib/time";
import { IN_PROGRESS_MESSAGE, UNKNOWN_MESSAGE, evaluate } from "../src/lib/updateGate";
import { tw } from "./fakes";

describe("time", () => {
  it("測試確實在非台灣時區執行（見 tests/setup.ts）", () => {
    expect(new Date("2026-09-20T22:30:00Z").getHours()).toBe(18); // 紐約 18:30，台灣是隔天 06:30
  });

  it("以台灣時間格式化，不受執行環境時區影響", () => {
    const d = new Date("2026-09-20T22:30:00Z"); // 台灣 09/21 06:30
    expect(formatMDHM(d)).toBe("09/21 06:30");
    expect(dateKey(d)).toBe("2026-09-21");
  });

  it("日期加減與當日起點", () => {
    expect(addDays("2026-09-30", 1)).toBe("2026-10-01");
    expect(addDays("2026-01-01", -1)).toBe("2025-12-31");
    expect(dayStart("2026-09-21")).toEqual(tw(2026, 9, 21, 0));
  });
});

describe("regions", () => {
  it("每個縣市恰屬一個地區", () => {
    expect(CITY_ORDER).toHaveLength(22);
    expect(new Set(CITY_ORDER).size).toBe(22);
    expect(new Set(Object.keys(CITY_TO_REGION))).toEqual(new Set(CITY_ORDER));
  });

  it("「台」統一成「臺」；查不到回傳 null", () => {
    expect(regionOf("台北市")).toBe("北部地區");
    expect(regionOf("臺北市")).toBe("北部地區");
    expect(regionOf("不存在")).toBeNull();
  });

  it("citiesIn", () => {
    expect(citiesIn(ALL_REGIONS)).toEqual(CITY_ORDER);
    expect(citiesIn("離島地區")).toEqual(["澎湖縣", "金門縣", "連江縣"]);
  });
});

describe("formatting", () => {
  it.each([[6, 18, false], [18, 30, true], [0, 6, true], [12, 18, false]])(
    "isNight 用時段中點判斷：%i~%i 時 → %s", (start, end, night) => {
      const base = tw(2026, 9, 21).getTime();
      expect(isNight(new Date(base + start * 3600_000), new Date(base + end * 3600_000))).toBe(night);
    });

  it.each([
    ["晴", false, "☀️"], ["晴", true, "🌙"], ["晴時多雲", false, "🌤️"], ["晴時多雲", true, "🌙☁️"],
    ["多雲", false, "⛅"], ["多雲", true, "☁️"], ["陰", false, "☁️"],
    ["短暫陣雨", true, "🌧️"], ["雷陣雨", false, "⛈️"], ["有霧", false, "🌫️"], ["未知", false, "🌡️"],
    [null, false, ""], ["", false, ""],
  ] as const)("weatherIcon(%s, %s) = %s", (text, night, icon) => {
    expect(weatherIcon(text, night)).toBe(icon);
  });

  it("時間與數值文字", () => {
    expect(formatRange(tw(2026, 9, 21, 6), tw(2026, 9, 22, 18))).toBe("09/21 06:00 ~ 09/22 18:00");
    const rows: StatusRow[] = [
      { trigger_type: "schedule", last_success_at: tw(2026, 9, 21, 9), last_run_at: null },
      { trigger_type: "manual", last_success_at: null, last_run_at: null },
    ];
    expect(formatLastUpdate(rows, "schedule")).toBe("09/21 09:00");
    expect(formatLastUpdate(rows, "manual")).toBe("—");
    expect(formatLastUpdate(null, "schedule")).toBe("—");
    expect(formatValue(23.456, "°C", 1)).toBe("23.5 °C");
    expect(formatValue(null, "%")).toBe("—");
    expect(formatValue(NaN, "%")).toBe("—");
  });
});

describe("temperature", () => {
  it.each([[19.9, 0], [20, 1], [25, 1], [25.1, 2], [30, 2], [30.1, 3]])("級距邊界 %f → %i", (temp, band) => {
    expect(bandIndex(temp)).toBe(band);
    expect(tempColor(temp)).toBe(BANDS[band][0]);
    expect(textColor(temp)).toBe(TEXT_COLORS[band]);
  });

  it("沒有值不上色、顯示「—」", () => {
    expect(textColor(NaN)).toBe("");
    expect(textColor(null)).toBe("");
    expect(tempText(NaN)).toBe("—");
    expect(tempText(23.6)).toBe("24°C");
  });

  it("平均溫沒有值時退回最高、最低溫的中點", () => {
    expect(displayTemp({ avg_temp: 20, min_temp: 10, max_temp: 30 })).toBe(20);
    expect(displayTemp({ avg_temp: null, min_temp: 10, max_temp: 20 })).toBe(15);
    expect(displayTemp({ avg_temp: null, min_temp: null, max_temp: 20 })).toBeNull();
  });
});

describe("rain", () => {
  it.each([[0, 0], [29, 0], [30, 1], [59, 1], [60, 2], [100, 2]])("降雨 %i%% → 色階 %i", (prob, band) => {
    expect(rainColor(prob)).toBe(RAIN_BANDS[band][1]);
  });

  it("最深色階從告警門檻開始；沒有值不上色", () => {
    expect(RAIN_BANDS.at(-1)![0]).toBe(RAIN_ALERT);
    expect(rainColor(null)).toBe("");
    expect(rainColor(NaN)).toBe("");
  });
});

describe("updateGate", () => {
  const NOW = tw(2026, 9, 21, 10);
  const status = (minutesAgo: number): StatusRow => ({
    trigger_type: "schedule", last_success_at: new Date(NOW.getTime() - minutesAgo * 60_000), last_run_at: null,
  });

  it("讀不到狀態不放行", () => {
    for (const rows of [null, []]) {
      const gate = evaluate(rows, NOW);
      expect([gate.allowed, gate.message]).toEqual([false, UNKNOWN_MESSAGE]);
    }
  });

  it("從未成功更新過則放行", () => {
    expect(evaluate([{ trigger_type: "schedule", last_success_at: null, last_run_at: null }], NOW).allowed).toBe(true);
  });

  it("不滿 20 分鐘不放行並提示等待分鐘數", () => {
    const gate = evaluate([status(5)], NOW);
    expect(gate.allowed).toBe(false);
    expect(gate.message).toContain("僅 5 分鐘");
    expect(gate.message).toContain("約 15 分鐘");
  });

  it("剛好滿間隔放行；多來源取較新的一筆", () => {
    expect(evaluate([status(20)], NOW).allowed).toBe(true);
    expect(evaluate([status(90), status(3)], NOW).allowed).toBe(false);
    expect(evaluate([status(90), status(30)], NOW).allowed).toBe(true);
  });

  it("GitHub 上有未完成的手動更新時不放行（即使已滿間隔或從未成功過）", () => {
    const gate = evaluate([status(60)], NOW, { inProgress: true });
    expect([gate.allowed, gate.message]).toEqual([false, IN_PROGRESS_MESSAGE]);
    expect(evaluate([{ trigger_type: "manual", last_success_at: null, last_run_at: null }], NOW, { inProgress: true }).allowed)
      .toBe(false);
  });

  it("讀不到狀態時仍顯示「無法確認」而不是「更新中」", () => {
    expect(evaluate(null, NOW, { inProgress: true }).message).toBe(UNKNOWN_MESSAGE);
  });

  it("被間隔擋住時提供等待秒數與已過分鐘數", () => {
    const gate = evaluate([status(6)], NOW);
    expect(gate.elapsedMinutes).toBe(6);
    expect(gate.waitSeconds).toBeCloseTo(14 * 60);
    expect(evaluate([status(19.5)], NOW).waitSeconds).toBeCloseTo(30);
  });

  it("只有被間隔擋住才有等待秒數", () => {
    for (const gate of [evaluate(null, NOW), evaluate([status(60)], NOW, { inProgress: true }), evaluate([status(60)], NOW)]) {
      expect([gate.waitSeconds, gate.elapsedMinutes]).toEqual([null, null]);
    }
  });
});

describe("countdown", () => {
  it.each([[0, "00:00"], [-5, "00:00"], [0.2, "00:01"], [59.01, "01:00"], [60, "01:00"], [822.4, "13:43"], [1200, "20:00"]])(
    "formatMmss(%f) = %s", (seconds, text) => {
      expect(formatMmss(seconds)).toBe(text);
    });

  it("已過分鐘數由剩餘秒數推導", () => {
    expect(elapsedMinutes(20, 90)).toBe(18);
    expect(elapsedMinutes(20, -3)).toBe(20);
    expect(elapsedMinutes(20, 1200)).toBe(0);
  });
});
