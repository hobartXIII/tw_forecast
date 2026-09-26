/** 告警設定的資料層：錯誤轉換（不洩漏密碼）、驗證與轉換、經由資料庫函式讀寫。對應 tests/frontend/test_admin.py。 */
import { describe, expect, it, vi } from "vitest";

import {
  AdminError, AlertSettingsService, NotConfigured, WrongPassword, buildPayload, setAllEnabled, toCitySettings,
  translateError, validate, type CitySetting,
} from "../src/lib/admin";

const PASSWORD = "S3cret-Password!";

function dbCity(name = "臺北市", extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    location_name: name, enabled: true, rain_enabled: true, rain_threshold: 60,
    min_temp_enabled: true, min_temp_threshold: 12, max_temp_enabled: true, max_temp_threshold: 35, ...extra,
  };
}

const rpcData = (cities = [dbCity("臺中市"), dbCity("臺北市")]) => ({
  cities, slots: [{ slot: "08:45", enabled: true }, { slot: "14:45", enabled: false }],
});

/** 假的 supabase.rpc：results[函式名稱] 為回傳資料，或 { error } 表示資料庫錯誤。 */
function fakeRpc(results: Record<string, unknown> = {}) {
  return vi.fn(async (fn: string) => {
    const r = results[fn] as { error?: unknown } | undefined;
    return r && typeof r === "object" && "error" in r ? { data: null, error: r.error } : { data: r ?? null, error: null };
  });
}

const sample = (): CitySetting[] => toCitySettings([dbCity("臺北市"), dbCity("新北市")]);

describe("translateError", () => {
  it("密碼錯誤", () => {
    expect(translateError({ message: "invalid_password" }, PASSWORD)).toBeInstanceOf(WrongPassword);
  });

  it.each([{ code: "PGRST202" }, { code: "42883" }, { message: "Could not find the function public.x" }])(
    "資料庫函式不存在：%o", (err) => {
      expect(translateError(err, PASSWORD)).toBeInstanceOf(NotConfigured);
    });

  it("其他錯誤遮蔽密碼並截斷", () => {
    const err = translateError({ message: `boom ${PASSWORD} ${"x".repeat(400)}` }, PASSWORD);
    expect(err.message).not.toContain(PASSWORD);
    expect(err.message).toContain("***");
    expect(err.message.length).toBeLessThanOrEqual(200);
  });
});

describe("轉換與驗證", () => {
  it("依縣市順序排序，NUMERIC 字串轉成數字", () => {
    const c = toCitySettings([dbCity("臺中市"), dbCity("臺北市", { min_temp_threshold: "12.5" }), dbCity("澎湖縣")]);
    expect(c.map((x) => x.location_name)).toEqual(["臺北市", "臺中市", "澎湖縣"]);
    expect(c[0].min_temp_threshold).toBe(12.5);
    expect(c[0].enabled).toBe(true);
  });

  it("預設值通過驗證", () => {
    expect(validate(sample(), { "08:45": true })).toEqual([]);
  });

  it.each([
    ["rain_threshold", 101, "必須介於 0 到 100"],
    ["min_temp_threshold", -21, "必須介於 -20 到 50"],
    ["max_temp_threshold", NaN, "不可空白"],
    ["rain_threshold", 60.5, "必須是整數"],
  ] as const)("%s = %s → %s", (field, value, fragment) => {
    const c = sample();
    c[0] = { ...c[0], [field]: value };
    expect(validate(c, {}).some((e) => e.includes(fragment))).toBe(true);
  });

  it("縣市重複、時段不合法", () => {
    const c = sample();
    c[1] = { ...c[1], location_name: "臺北市" };
    expect(validate(c, {})).toContain("縣市重複");
    expect(validate(sample(), { "09:00": true })).toEqual(["發送時段設定不合法"]);
  });

  it("參數格式", () => {
    const { p_cities, p_slots } = buildPayload(sample(), { "08:45": true, "14:45": false });
    expect(p_cities[0]).toEqual(dbCity("臺北市"));
    expect(p_slots).toEqual([{ slot: "08:45", enabled: true }, { slot: "14:45", enabled: false }]);
  });

  it("全部關閉只改「啟用」，不改動原資料", () => {
    const c = sample();
    const off = setAllEnabled(c, false);
    expect(off.every((x) => !x.enabled)).toBe(true);
    expect(off.map(({ enabled: _, ...rest }) => rest)).toEqual(c.map(({ enabled: _, ...rest }) => rest));
    expect(c.every((x) => x.enabled)).toBe(true);
  });
});

describe("AlertSettingsService", () => {
  it("讀取：回傳排序後的縣市與三個時段（沒列出的視為關閉）", async () => {
    const rpc = fakeRpc({ admin_get_alert_settings: rpcData() });
    const s = await new AlertSettingsService({ rpc } as never).getSettings(PASSWORD);
    expect(s.cities.map((c) => c.location_name)).toEqual(["臺北市", "臺中市"]);
    expect(s.slots).toEqual({ "08:45": true, "14:45": false, "20:45": false });
    expect(rpc).toHaveBeenCalledWith("admin_get_alert_settings", { p_password: PASSWORD });
  });

  it("讀取：密碼錯誤拋 WrongPassword，訊息不含密碼", async () => {
    const rpc = fakeRpc({ admin_get_alert_settings: { error: { message: "invalid_password" } } });
    const err = await new AlertSettingsService({ rpc } as never).getSettings(PASSWORD).catch((e) => e);
    expect(err).toBeInstanceOf(WrongPassword);
    expect(err.message).not.toContain(PASSWORD);
  });

  it("連線例外也轉成不含密碼的 AdminError", async () => {
    const rpc = vi.fn(async () => { throw new Error(`network down ${PASSWORD}`); });
    const err = await new AlertSettingsService({ rpc } as never).getSettings(PASSWORD).catch((e) => e);
    expect(err).toBeInstanceOf(AdminError);
    expect(err.message).not.toContain(PASSWORD);
  });

  it("儲存：驗證不過就不呼叫資料庫", async () => {
    const rpc = fakeRpc();
    const c = sample();
    c[0] = { ...c[0], rain_threshold: 999 };
    await expect(new AlertSettingsService({ rpc } as never).saveSettings(PASSWORD, { cities: c, slots: { "08:45": true } }))
      .rejects.toThrow("必須介於");
    expect(rpc).not.toHaveBeenCalled();
  });

  it("儲存：送出密碼、縣市與時段", async () => {
    const rpc = fakeRpc({ admin_save_alert_settings: { ok: true } });
    await new AlertSettingsService({ rpc } as never).saveSettings(PASSWORD, { cities: sample(), slots: { "08:45": true } });
    const [name, params] = rpc.mock.calls[0] as unknown as [string, Record<string, { slot: string }[]>];
    expect(name).toBe("admin_save_alert_settings");
    expect(params.p_password).toBe(PASSWORD);
    expect(params.p_cities).toHaveLength(2);
    expect(params.p_slots[0].slot).toBe("08:45");
  });

  it("錯誤很多時只列前 5 項", async () => {
    const cities = Array.from({ length: 8 }, (_, i) => ({ ...sample()[0], location_name: `縣市${i}`, rain_threshold: 999 }));
    await expect(new AlertSettingsService({ rpc: fakeRpc() } as never).saveSettings(PASSWORD, { cities, slots: {} }))
      .rejects.toThrow("另有 3 項");
  });
});
