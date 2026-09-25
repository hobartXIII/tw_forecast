/** 摘要卡片內容、網址參數、日期選單文字。 */
import { describe, expect, it } from "vitest";

import { rainColor } from "../src/lib/rain";
import { ALL_REGIONS } from "../src/lib/regions";
import { toForecastRow } from "../src/lib/repository";
import { Scope, addRegion, withAvg } from "../src/lib/scope";
import { extreme, summaryCards } from "../src/lib/summary";
import { tempColor } from "../src/lib/temperature";
import { dateLabel } from "../src/lib/time";
import { scopeFromSearch, searchFromScope } from "../src/lib/urlState";
import { forecastRows, tw } from "./fakes";

const cur = () => {
  const rows = withAvg(addRegion(forecastRows(tw(2026, 9, 21, 6), 1).map(toForecastRow)));
  const first = rows[0].forecast_time_start.getTime();
  return rows.filter((r) => r.forecast_time_start.getTime() === first);
};

describe("summaryCards", () => {
  it("全台：平均與極值，標出縣市", () => {
    const cards = summaryCards(cur(), new Scope());
    expect(cards.map((c) => c.label)).toEqual(["平均氣溫", "最高溫　連江縣", "最低溫　臺北市", "最高降雨機率　連江縣"]);
    expect(cards[1].accent).toBe(tempColor(24 + 21 * 0.5));
    expect(cards[3].meter).toBe(21);
    expect(cards[3].accent).toBe(rainColor(21));
    expect(cards[3].textColor).toBe(""); // 降雨數字不上色
  });

  it("單一縣市：該縣市的數值，平均氣溫旁顯示天氣", () => {
    const cards = summaryCards(cur(), new Scope(ALL_REGIONS, "臺北市"));
    expect(cards[0].label).toBe("臺北市 平均氣溫");
    expect(cards[0].text).toBe("21.0 °C");
    expect(cards[0].aside).toBe("☀️ 晴");
    expect(cards.slice(1).map((c) => c.label)).toEqual(["最高溫", "最低溫", "降雨機率"]);
  });

  it("沒有值時顯示「—」且不發光", () => {
    const rows = cur().map((r) => ({ ...r, max_temp: null, rain_probability: null }));
    const cards = summaryCards(rows, new Scope());
    expect([cards[1].label, cards[1].text, cards[1].accent]).toEqual(["最高溫", "—", ""]);
    expect(cards[3].meter).toBeNull();
  });

  it("extreme 同值取先出現的一筆", () => {
    const rows = cur().map((r) => ({ ...r, max_temp: 30 }));
    expect(extreme(rows, "max_temp", true)).toEqual({ value: 30, city: "臺北市" });
  });
});

describe("urlState", () => {
  it.each([
    ["", new Scope()],
    ["?region=離島地區", new Scope("離島地區")],
    ["?city=臺中市", new Scope(ALL_REGIONS, "臺中市")],
    ["?city=台中市&region=離島地區", new Scope(ALL_REGIONS, "臺中市")], // 縣市優先，台 → 臺
    ["?region=火星&city=火星市", new Scope()], // 不認得的值退回全台
  ])("scopeFromSearch(%s)", (search, expected) => {
    expect(scopeFromSearch(search)).toEqual(expected);
  });

  it("searchFromScope 與 scopeFromSearch 互為反向", () => {
    for (const scope of [new Scope(), new Scope("中部地區"), new Scope(ALL_REGIONS, "臺北市")]) {
      expect(scopeFromSearch(searchFromScope(scope))).toEqual(scope);
    }
    expect(searchFromScope(new Scope())).toBe("");
  });
});

describe("dateLabel", () => {
  it("加上星期，今天另外標示", () => {
    expect(dateLabel("2026-09-21")).toBe("2026-09-21（週一）");
    expect(dateLabel("2026-09-27", "2026-09-27")).toBe("2026-09-27（週日）　今天");
  });
});
