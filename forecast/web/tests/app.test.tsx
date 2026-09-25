// @vitest-environment jsdom
/** 整頁煙霧測試：真的渲染 App，資料庫換成假的、時間固定（對應 tests/frontend/test_app_smoke.py）。
圖表元件換成只記錄規格的假元件（jsdom 不能真的畫 Vega）。 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { forecastRows, tw } from "./fakes";

const NOW = tw(2026, 9, 21, 10);
const STATUS = [
  { trigger_type: "schedule", last_success_at: "2026-09-21T09:30:00+08:00", last_run_at: null },
  { trigger_type: "manual", last_success_at: "2026-09-21T08:00:00+08:00", last_run_at: null },
];

const db = vi.hoisted(() => ({ tables: {} as Record<string, Record<string, unknown>[]>, errors: {} as Record<string, string> }));
vi.mock("../src/lib/supabase", async () => {
  const { fakeClient: make } = await import("./fakes");
  return { supabase: { from: (name: string) => make(db.tables, db.errors).from(name) } };
});
vi.mock("../src/components/VegaChart", () => ({
  VegaChart: ({ spec }: { spec: object }) => <div data-testid="chart">{JSON.stringify(spec)}</div>,
}));

import App from "../src/App";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
  db.tables = { weather_forecasts: forecastRows(tw(2026, 9, 20, 6), 4), pipeline_status: STATUS };
  db.errors = {};
  window.history.replaceState(null, "", "/");
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const tabLabels = () => screen.getAllByRole("tab").map((t) => t.textContent);
const select = (label: string) => screen.getByLabelText(label) as HTMLSelectElement;

describe("App", () => {
  it("預設頁面：更新時間、四張卡片、五個分頁、趨勢圖", async () => {
    render(<App />);
    expect(await screen.findByText(/最近排程更新 09\/21 09:30/)).toBeTruthy();
    expect(screen.getByText(/最近手動更新 09\/21 08:00/)).toBeTruthy();
    expect(document.querySelectorAll(".card")).toHaveLength(4);
    expect(tabLabels()).toEqual(["📈 氣溫趨勢", "🌧️ 降雨機率", "📋 目前時段明細", "🕒 後續時段", "📅 日期查詢"]);
    expect(screen.getAllByTestId("chart")).toHaveLength(1);
    expect(screen.getByText(/預報時段/).textContent).toContain("09/21 06:00 ~ 09/21 18:00");
    expect(screen.queryByText(/目前沒有涵蓋此刻/)).toBeNull();
  });

  it("選縣市：地區顯示「已選縣市」、四個分頁、三條線合併的氣溫圖、網址帶縣市", async () => {
    render(<App />);
    await screen.findAllByRole("tab");
    fireEvent.change(select("縣市"), { target: { value: "臺中市" } });
    expect(select("地區").value).toBe("");
    expect(tabLabels()).toEqual(["📈 氣溫趨勢", "🌧️ 降雨機率", "📋 一週預報", "📅 日期查詢"]);
    expect(screen.queryByRole("radiogroup")).toBeNull(); // 單一縣市不需要指標選項
    const spec = screen.getByTestId("chart").textContent!;
    for (const name of ["最高溫", "平均溫", "最低溫"]) expect(spec).toContain(name);
    expect(window.location.search).toBe(`?city=${encodeURIComponent("臺中市")}`);
  });

  it("地區與縣市互斥", async () => {
    render(<App />);
    await screen.findAllByRole("tab");
    fireEvent.change(select("縣市"), { target: { value: "臺中市" } });
    fireEvent.change(select("地區"), { target: { value: "離島地區" } });
    expect([select("地區").value, select("縣市").value]).toEqual(["離島地區", "全部縣市"]);
    fireEvent.change(select("縣市"), { target: { value: "臺北市" } });
    expect(select("地區").value).toBe("");
  });

  it("網址帶縣市時直接顯示該縣市", async () => {
    window.history.replaceState(null, "", "/?city=臺東縣");
    render(<App />);
    await screen.findAllByRole("tab");
    expect(select("縣市").value).toBe("臺東縣");
    expect(screen.getByText("臺東縣 平均氣溫")).toBeTruthy();
  });

  it("明細與後續時段分頁顯示表格", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("tab", { name: "📋 目前時段明細" }));
    expect(within(document.querySelector("table")!).getAllByRole("row")).toHaveLength(23); // 標題 + 22 縣市
    fireEvent.click(screen.getByRole("tab", { name: "🕒 後續時段" }));
    expect(within(document.querySelector("table")!).getAllByRole("row")).toHaveLength(45); // 標題 + 22 × 2
  });

  it("點欄位標題排序", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("tab", { name: "📋 目前時段明細" }));
    fireEvent.click(screen.getByRole("columnheader", { name: "最高 (°C)" }));
    fireEvent.click(screen.getByRole("columnheader", { name: /最高 \(°C\)/ })); // 再點一次：由高到低
    const firstCity = within(document.querySelectorAll("tbody tr")[0] as HTMLElement).getAllByRole("cell")[0];
    expect(firstCity.textContent).toBe("連江縣");
  });

  it("日期查詢：選日期後列出該日表格", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("tab", { name: "📅 日期查詢" }));
    const picker = (await screen.findByLabelText(/日期（今天前 3 天/)) as HTMLSelectElement;
    expect([...picker.options].map((o) => o.textContent)).toContain("2026-09-21（週一）　今天");
    fireEvent.change(picker, { target: { value: "2026-09-22" } });
    await waitFor(() => expect(document.querySelector("table")).toBeTruthy());
    expect(within(document.querySelector("table")!).getAllByRole("row")).toHaveLength(45); // 22 縣市 × 2 時段
  });

  it("資料過期時顯示警示，趨勢分頁提示沒有未來預報", async () => {
    vi.setSystemTime(tw(2026, 10, 30, 10));
    render(<App />);
    expect(await screen.findByText(/目前沒有涵蓋此刻的預報時段/)).toBeTruthy();
    expect(screen.getByText(/沒有未來預報資料/)).toBeTruthy();
  });

  it("資料庫沒有資料時顯示警示", async () => {
    db.tables = { weather_forecasts: [], pipeline_status: STATUS };
    render(<App />);
    expect(await screen.findByText(/資料庫目前沒有預報資料/)).toBeTruthy();
  });

  it("讀取預報失敗時顯示錯誤", async () => {
    db.errors = { weather_forecasts: "connection refused" };
    render(<App />);
    expect((await screen.findByRole("alert")).textContent).toBe("讀取資料庫失敗：connection refused");
  });

  it("讀不到狀態表不影響其他區塊，只是不顯示更新時間", async () => {
    db.errors = { pipeline_status: "permission denied" };
    render(<App />);
    expect(await screen.findAllByRole("tab")).toHaveLength(5);
    expect(screen.queryByText(/最近排程更新/)).toBeNull();
  });

  it("重新載入資料會重新查詢", async () => {
    render(<App />);
    await screen.findAllByRole("tab");
    db.tables = { weather_forecasts: [], pipeline_status: STATUS };
    fireEvent.click(screen.getByRole("button", { name: "♻️ 重新載入資料" }));
    expect(await screen.findByText(/資料庫目前沒有預報資料/)).toBeTruthy();
  });
});
