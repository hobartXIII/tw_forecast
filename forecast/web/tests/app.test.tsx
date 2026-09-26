// @vitest-environment jsdom
/** 整頁煙霧測試：真的渲染 App，資料庫換成假的、時間固定（對應 tests/frontend/test_app_smoke.py）。
圖表元件換成只記錄規格的假元件（jsdom 不能真的畫 Vega）。 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { forecastRows, tw } from "./fakes";

const NOW = tw(2026, 9, 21, 10);
const STATUS = [
  { trigger_type: "schedule", last_success_at: "2026-09-21T09:30:00+08:00", last_run_at: null },
  { trigger_type: "manual", last_success_at: "2026-09-21T08:00:00+08:00", last_run_at: null },
];

/** 假的 /api/update-status 與 /api/dispatch：api.status 為下一次查詢的回應，api.dispatch 為觸發的回應。 */
const api = vi.hoisted(() => ({ status: {} as Record<string, unknown>, dispatch: {} as Record<string, unknown>, calls: [] as string[] }));
const allowed = (extra: Record<string, unknown> = {}) => ({
  allowed: true, message: "", waitSeconds: null, elapsedMinutes: null, inProgress: false,
  lastSuccess: "2026-09-21T09:30:00+08:00", checkedAt: NOW.toISOString(), ...extra,
});

const db = vi.hoisted(() => ({
  tables: {} as Record<string, Record<string, unknown>[]>,
  errors: {} as Record<string, string>,
  /** 假的告警設定 RPC：密碼為 PASSWORD 才通過；saved 記錄最後一次儲存的參數。 */
  alert: { cities: [] as Record<string, unknown>[], slots: [] as Record<string, unknown>[], saved: null as Record<string, unknown> | null },
}));
const PASSWORD = "S3cret-Password!";
vi.mock("../src/lib/supabase", async () => {
  const { fakeClient: make } = await import("./fakes");
  return {
    supabase: {
      from: (name: string) => make(db.tables, db.errors).from(name),
      rpc: async (fn: string, params: Record<string, unknown>) => {
        if (params.p_password !== "S3cret-Password!") return { data: null, error: { message: "invalid_password" } };
        if (fn === "admin_save_alert_settings") {
          db.alert.saved = params;
          db.alert.cities = params.p_cities as Record<string, unknown>[];
          db.alert.slots = params.p_slots as Record<string, unknown>[];
          return { data: {}, error: null };
        }
        return { data: { cities: db.alert.cities, slots: db.alert.slots }, error: null };
      },
    },
  };
});
vi.mock("../src/components/VegaChart", () => ({
  VegaChart: ({ spec }: { spec: object }) => <div data-testid="chart">{JSON.stringify(spec)}</div>,
}));
vi.mock("../src/components/TemperatureMap", () => ({ // jsdom 不能真的畫 Leaflet，只記錄收到的參數
  TemperatureMap: ({ cur, level, highlight }: { cur: { location_name: string }[]; level: string; highlight: string | null }) => (
    <div data-testid="map" data-level={level} data-highlight={highlight ?? ""}>{cur.map((r) => r.location_name).join(",")}</div>
  ),
}));

import App from "../src/App";
import { CITY_ORDER } from "../src/lib/regions";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
  db.tables = { weather_forecasts: forecastRows(tw(2026, 9, 20, 6), 4), pipeline_status: STATUS };
  db.errors = {};
  db.alert = {
    cities: CITY_ORDER.map((name) => ({
      location_name: name, enabled: name === "臺中市", rain_enabled: true, rain_threshold: 60,
      min_temp_enabled: true, min_temp_threshold: "12.0", max_temp_enabled: true, max_temp_threshold: "35.0",
    })),
    slots: [{ slot: "08:45", enabled: true }, { slot: "14:45", enabled: false }, { slot: "20:45", enabled: true }],
    saved: null,
  };
  window.history.replaceState(null, "", "/");
  api.status = allowed();
  api.dispatch = { ok: true, message: "", status: allowed({ allowed: false, inProgress: true }) };
  api.calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    api.calls.push(`${init?.method ?? "GET"} ${url}`);
    const body = url === "/api/dispatch" ? api.dispatch : api.status;
    return new Response(JSON.stringify(body), { headers: { "content-type": "application/json" } });
  }));
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
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
    expect(screen.getByTestId("map").textContent!.split(",")).toHaveLength(22);
    expect(screen.getByText("🗺️ 平均氣溫地圖")).toBeTruthy();
  });

  it("地圖：選地區只顯示該地區；選縣市時顯示所屬地區並標出被選縣市", async () => {
    render(<App />);
    await screen.findAllByRole("tab");
    fireEvent.change(select("地區"), { target: { value: "東部地區" } });
    expect(screen.getByTestId("map").textContent).toBe("宜蘭縣,花蓮縣,臺東縣");
    expect(screen.getByTestId("map").dataset.level).toBe("region");
    fireEvent.change(select("縣市"), { target: { value: "臺中市" } });
    const map = screen.getByTestId("map");
    expect(map.textContent).toBe("苗栗縣,臺中市,彰化縣,南投縣,雲林縣");
    expect(map.dataset.highlight).toBe("臺中市");
    expect(screen.getByText(/其餘中部地區縣市淡化作為對照/)).toBeTruthy();
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

describe("立即更新", () => {
  const updateButton = () => screen.getByRole("button", { name: /立即更新|更新中/ }) as HTMLButtonElement;

  it("可更新時按鈕可按；狀態列顯示間隔規則", async () => {
    render(<App />);
    await waitFor(() => expect(updateButton().disabled).toBe(false));
    expect(screen.getByText(/手動更新需間隔 20 分鐘/)).toBeTruthy();
  });

  it("不可更新時按鈕停用並顯示原因", async () => {
    api.status = allowed({ allowed: false, inProgress: true, message: "已觸發更新，正在等待完成" });
    render(<App />);
    expect(await screen.findByText("已觸發更新，正在等待完成")).toBeTruthy();
    expect(updateButton().disabled).toBe(true);
  });

  it("讀不到更新狀態（例如本機沒有 api/）時不放行", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>", { headers: { "content-type": "text/html" } })));
    render(<App />);
    expect(await screen.findByText(/無法取得更新狀態/)).toBeTruthy();
    expect(updateButton().disabled).toBe(true);
  });

  it("間隔倒數：兩個數字同步，時間到自動再查一次", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    vi.setSystemTime(NOW);
    api.status = allowed({ allowed: false, waitSeconds: 14 * 60 + 30, elapsedMinutes: 5, message: "間隔不足" });
    render(<App />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByText(/距上次更新僅/).textContent).toBe("距上次更新僅 5 分鐘，需間隔 20 分鐘，還需 14:30 才可更新");
    await act(async () => { await vi.advanceTimersByTimeAsync(31_000); });
    expect(screen.getByText(/距上次更新僅/).textContent).toContain("6 分鐘，需間隔 20 分鐘，還需 13:59");
    api.status = allowed();
    const before = api.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(14 * 60_000); });
    expect(api.calls.length).toBe(before + 1);
    expect(screen.queryByText(/距上次更新僅/)).toBeNull();
    expect(updateButton().disabled).toBe(false);
  });

  it("觸發成功：按鈕改為更新中並倒數，60 秒後重新載入並確認已完成", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    vi.setSystemTime(NOW);
    render(<App />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    fireEvent.click(updateButton());
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(api.calls).toContain("POST /api/dispatch");
    expect(updateButton().textContent).toBe("⏳ 更新中…");
    expect(updateButton().disabled).toBe(true);
    expect(screen.getByText(/已觸發更新，60 秒後自動重新載入資料/)).toBeTruthy();
    api.status = allowed({ allowed: false, lastSuccess: new Date(NOW.getTime() + 50_000).toISOString() });
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(screen.getByText("資料已更新完成")).toBeTruthy();
    expect(updateButton().textContent).toBe("🔄 立即更新");
  });

  it("倒數結束時還沒有新的成功紀錄：提示尚未完成", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    vi.setSystemTime(NOW);
    render(<App />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    fireEvent.click(updateButton());
    await act(async () => { await vi.advanceTimersByTimeAsync(0); }); // 讓觸發的回應先回來、排好 60 秒的計時
    api.status = allowed({ allowed: false, inProgress: true, message: "已觸發更新，正在等待完成" });
    await act(async () => { await vi.advanceTimersByTimeAsync(61_000); });
    expect(screen.getByText("更新尚未完成，請稍後按「重新載入資料」")).toBeTruthy();
  });

  it("伺服器拒絕觸發：顯示原因", async () => {
    api.dispatch = { ok: false, message: "觸發失敗（HTTP 403）", status: allowed({ allowed: false }) };
    render(<App />);
    await waitFor(() => expect(updateButton().disabled).toBe(false));
    fireEvent.click(updateButton());
    expect(await screen.findByText("觸發失敗（HTTP 403）")).toBeTruthy();
  });
});

describe("告警設定", () => {
  const openAdmin = async () => {
    render(<App />);
    await screen.findAllByRole("tab");
    fireEvent.click(screen.getByRole("button", { name: "⚙️ 告警設定" }));
  };
  const loginWith = async (password: string) => {
    const dialog = await screen.findByRole("dialog", { name: "🔒 管理者登入" });
    fireEvent.change(within(dialog).getByLabelText("管理者密碼"), { target: { value: password } });
    fireEvent.click(within(dialog).getByRole("button", { name: "登入" }));
  };
  const settingsDialog = () => screen.findByRole("dialog", { name: "⚙️ 告警設定" });
  const checkbox = (root: HTMLElement, label: string) => within(root).getByLabelText(label) as HTMLInputElement;

  it("未登入先開登入視窗；密碼錯誤顯示錯誤、輸入框清空", async () => {
    await openAdmin();
    await loginWith("wrong-password");
    const dialog = screen.getByRole("dialog", { name: "🔒 管理者登入" });
    expect(await within(dialog).findByText("密碼錯誤")).toBeTruthy();
    expect(checkbox(dialog, "管理者密碼").value).toBe("");
  });

  it("空白密碼不送出", async () => {
    await openAdmin();
    await loginWith("");
    expect(await screen.findByText("請輸入密碼")).toBeTruthy();
  });

  it("登入後開設定視窗：時段、22 縣市、依資料庫的值勾選", async () => {
    await openAdmin();
    await loginWith(PASSWORD);
    const dialog = await settingsDialog();
    expect(screen.queryByRole("dialog", { name: "🔒 管理者登入" })).toBeNull();
    expect(checkbox(dialog, "08:45").checked).toBe(true);
    expect(checkbox(dialog, "14:45").checked).toBe(false);
    expect(within(dialog).getAllByRole("row")).toHaveLength(23); // 標題列 + 22 縣市
    expect(checkbox(dialog, "臺中市 啟用").checked).toBe(true);
    expect(checkbox(dialog, "臺北市 低溫門檻 (°C)").value).toBe("12");
  });

  it("修改後儲存：送出密碼與修改後的值，顯示已儲存", async () => {
    await openAdmin();
    await loginWith(PASSWORD);
    const dialog = await settingsDialog();
    fireEvent.click(checkbox(dialog, "臺北市 啟用"));
    fireEvent.change(checkbox(dialog, "臺北市 降雨門檻 (%)"), { target: { value: "70" } });
    fireEvent.click(checkbox(dialog, "14:45"));
    fireEvent.click(within(dialog).getByRole("button", { name: "💾 儲存" }));
    expect(await within(dialog).findByText("已儲存，設定會在下一個發送時段生效")).toBeTruthy();
    const saved = db.alert.saved as { p_password: string; p_cities: Record<string, unknown>[]; p_slots: unknown[] };
    expect(saved.p_password).toBe(PASSWORD);
    expect(saved.p_cities.find((c) => c.location_name === "臺北市")).toMatchObject({ enabled: true, rain_threshold: 70 });
    expect(saved.p_slots).toContainEqual({ slot: "14:45", enabled: true });
  });

  it("門檻超出範圍：不送出並顯示原因", async () => {
    await openAdmin();
    await loginWith(PASSWORD);
    const dialog = await settingsDialog();
    fireEvent.change(checkbox(dialog, "臺北市 降雨門檻 (%)"), { target: { value: "150" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "💾 儲存" }));
    expect(await within(dialog).findByText(/儲存失敗：臺北市：「降雨門檻 \(%\)」必須介於 0 到 100/)).toBeTruthy();
    expect(db.alert.saved).toBeNull();
  });

  it("全部關閉只改畫面（尚未儲存），並提示沒有啟用任何縣市", async () => {
    await openAdmin();
    await loginWith(PASSWORD);
    const dialog = await settingsDialog();
    fireEvent.click(within(dialog).getByRole("button", { name: "全部關閉（尚未儲存）" }));
    expect(within(dialog).getByText("尚未啟用任何縣市，不會發送告警")).toBeTruthy();
    expect(db.alert.saved).toBeNull();
  });

  it("關閉視窗放棄未儲存的修改；再按按鈕不用重新登入，並從資料庫重讀", async () => {
    await openAdmin();
    await loginWith(PASSWORD);
    let dialog = await settingsDialog();
    fireEvent.click(checkbox(dialog, "臺北市 啟用"));
    fireEvent.click(within(dialog).getByRole("button", { name: "關閉" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "⚙️ 告警設定" }));
    dialog = await settingsDialog();
    expect(checkbox(dialog, "臺北市 啟用").checked).toBe(false);
  });

  it("登出後關閉視窗並提示；再按按鈕要重新登入", async () => {
    await openAdmin();
    await loginWith(PASSWORD);
    const dialog = await settingsDialog();
    fireEvent.click(within(dialog).getByRole("button", { name: "登出" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("已登出")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "⚙️ 告警設定" }));
    expect(await screen.findByRole("dialog", { name: "🔒 管理者登入" })).toBeTruthy();
  });

  it("閒置超過 15 分鐘自動登出", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    vi.setSystemTime(NOW);
    render(<App />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    fireEvent.click(screen.getByRole("button", { name: "⚙️ 告警設定" }));
    const login = screen.getByRole("dialog", { name: "🔒 管理者登入" });
    fireEvent.change(checkbox(login, "管理者密碼"), { target: { value: PASSWORD } });
    fireEvent.click(within(login).getByRole("button", { name: "登入" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByRole("dialog", { name: "⚙️ 告警設定" })).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(16 * 60_000); });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("已因閒置超過 15 分鐘登出，請重新登入")).toBeTruthy();
  });

  it("手機選單：按「☰ 選單」展開，按其中的按鈕後收起", async () => {
    render(<App />);
    await screen.findAllByRole("tab");
    const toggle = screen.getByRole("button", { name: "☰ 選單" });
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "⚙️ 告警設定" }));
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });
});
