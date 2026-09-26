/** 告警設定的資料層（對應 Python 的 frontend/admin.py；SPECIFICATION.md §8.1 第 8 點）。

輸入：管理者密碼、縣市設定與發送時段。輸出：資料庫函式的回傳值、驗證結果。

- 密碼只在呼叫時當作參數送給資料庫驗證（admin_get_alert_settings／admin_save_alert_settings）；
  這裡不儲存密碼，錯誤訊息一律遮蔽密碼。前端的 anon 金鑰無法直接讀寫設定表。
- 轉換與驗證是純函式；AlertSettingsService 負責呼叫資料庫。
*/
import type { SupabaseClient } from "@supabase/supabase-js";

import { CITY_ORDER } from "./regions";

/** 可選的發送時段（與資料庫 CHECK、後端 config.SEND_SLOTS 一致）。 */
export const SLOTS = ["08:45", "14:45", "20:45"] as const;
export const IDLE_TIMEOUT_MS = 15 * 60_000; // 閒置多久自動登出

export interface CitySetting {
  location_name: string;
  enabled: boolean;
  rain_enabled: boolean;
  rain_threshold: number;
  min_temp_enabled: boolean;
  min_temp_threshold: number;
  max_temp_enabled: boolean;
  max_temp_threshold: number;
}

export type SlotSettings = Record<string, boolean>;

export type BoolField = "enabled" | "rain_enabled" | "min_temp_enabled" | "max_temp_enabled";
export type NumberField = "rain_threshold" | "min_temp_threshold" | "max_temp_threshold";

/** 表格欄位（顯示名稱）。 */
export const BOOL_LABELS: Record<BoolField, string> = { enabled: "啟用", rain_enabled: "降雨", min_temp_enabled: "低溫", max_temp_enabled: "高溫" };
export const NUMBER_LABELS: Record<NumberField, string> = {
  rain_threshold: "降雨門檻 (%)", min_temp_threshold: "低溫門檻 (°C)", max_temp_threshold: "高溫門檻 (°C)",
};
/** 門檻範圍與輸入間距（與資料庫 CHECK 一致）。 */
export const LIMITS: Record<NumberField, { min: number; max: number; step: number }> = {
  rain_threshold: { min: 0, max: 100, step: 1 },
  min_temp_threshold: { min: -20, max: 50, step: 0.5 },
  max_temp_threshold: { min: -20, max: 50, step: 0.5 },
};

export class AdminError extends Error {} // 訊息保證不含密碼
export class WrongPassword extends AdminError {}
export class NotConfigured extends AdminError {}

interface DbError { code?: string; message?: string; details?: string; hint?: string }

/** 資料庫（PostgREST）的錯誤 → 不含密碼的 AdminError。 */
export function translateError(err: DbError | Error, password: string | null): AdminError {
  const e = err as DbError;
  const code = String(e.code ?? "");
  let text = [e.message, e.details, e.hint].filter(Boolean).join(" ").trim() || String(err);
  if (text.includes("invalid_password")) return new WrongPassword("密碼錯誤");
  if (code === "PGRST202" || code === "42883" || text.includes("Could not find the function")) {
    return new NotConfigured("設定功能尚未啟用：資料庫函式不存在，請先在 Supabase 執行 sql/init_supabase.sql");
  }
  if (password) text = text.split(password).join("***");
  return new AdminError(text.slice(0, 200));
}

const bool = (v: unknown) => v === true || v === "true";

/** 資料庫列 → 縣市設定；依縣市順序（北→中→南→東→離島）排序，NUMERIC 欄位可能是字串，一律轉成數字。 */
export function toCitySettings(rows: Record<string, unknown>[]): CitySetting[] {
  const order = new Map(CITY_ORDER.map((c, i) => [c, i]));
  return (rows ?? [])
    .map((r) => ({
      location_name: String(r.location_name),
      enabled: bool(r.enabled),
      rain_enabled: bool(r.rain_enabled),
      rain_threshold: Math.trunc(Number(r.rain_threshold)),
      min_temp_enabled: bool(r.min_temp_enabled),
      min_temp_threshold: Number(r.min_temp_threshold),
      max_temp_enabled: bool(r.max_temp_enabled),
      max_temp_threshold: Number(r.max_temp_threshold),
    }))
    .sort((a, b) => (order.get(a.location_name) ?? 999) - (order.get(b.location_name) ?? 999)
      || a.location_name.localeCompare(b.location_name, "zh-Hant"));
}

/** 儲存前檢查（資料庫另有 CHECK 把關）。回傳錯誤訊息清單，空清單代表通過。 */
export function validate(cities: CitySetting[], slots: SlotSettings): string[] {
  const errors: string[] = [];
  if (new Set(cities.map((c) => c.location_name)).size !== cities.length) errors.push("縣市重複");
  for (const c of cities) {
    for (const [field, label] of Object.entries(NUMBER_LABELS) as [NumberField, string][]) {
      const v = c[field];
      const { min, max } = LIMITS[field];
      if (v === null || v === undefined || Number.isNaN(v)) errors.push(`${c.location_name}：「${label}」不可空白`);
      else if (!(min <= v && v <= max)) errors.push(`${c.location_name}：「${label}」必須介於 ${min} 到 ${max}`);
      else if (field === "rain_threshold" && !Number.isInteger(v)) errors.push(`${c.location_name}：「${label}」必須是整數`);
    }
  }
  const known = new Set<string>(SLOTS);
  if (Object.keys(slots).some((s) => !known.has(s)) || Object.values(slots).some((v) => typeof v !== "boolean")) {
    errors.push("發送時段設定不合法");
  }
  return errors;
}

/** 最多列出 5 項錯誤，其餘以「另有 N 項」帶過。 */
export function summarizeErrors(errors: string[]): string {
  return errors.slice(0, 5).join("；") + (errors.length > 5 ? `（另有 ${errors.length - 5} 項）` : "");
}

/** 縣市設定與時段 → 資料庫函式的參數。 */
export function buildPayload(cities: CitySetting[], slots: SlotSettings) {
  return {
    p_cities: cities.map((c) => ({ ...c })),
    p_slots: Object.entries(slots).map(([slot, enabled]) => ({ slot, enabled })),
  };
}

/** 「全部啟用／全部關閉」：只改「啟用」，其他設定不動。 */
export const setAllEnabled = (cities: CitySetting[], enabled: boolean): CitySetting[] =>
  cities.map((c) => ({ ...c, enabled }));

export interface AlertSettings {
  cities: CitySetting[];
  slots: SlotSettings;
}

/** 經由資料庫函式讀寫告警設定（密碼在資料庫驗證）。 */
export class AlertSettingsService {
  constructor(private readonly sb: Pick<SupabaseClient, "rpc">) {}

  private async rpc(fn: string, params: Record<string, unknown>): Promise<unknown> {
    let result: { data: unknown; error: DbError | null };
    try {
      result = await this.sb.rpc(fn, params);
    } catch (e) {
      throw translateError(e as Error, params.p_password as string);
    }
    if (result.error) throw translateError(result.error, params.p_password as string);
    return result.data;
  }

  /** 讀取告警設定；密碼錯誤拋 WrongPassword。三個發送時段都會有值（資料庫沒有的視為關閉）。 */
  async getSettings(password: string): Promise<AlertSettings> {
    const data = (await this.rpc("admin_get_alert_settings", { p_password: password })) as {
      cities: Record<string, unknown>[]; slots: { slot: string; enabled: unknown }[];
    };
    const stored = new Map((data.slots ?? []).map((s) => [s.slot, bool(s.enabled)]));
    return {
      cities: toCitySettings(data.cities),
      slots: Object.fromEntries(SLOTS.map((s) => [s, stored.get(s) ?? false])),
    };
  }

  /** 儲存告警設定；驗證不過拋 AdminError（不呼叫資料庫），密碼錯誤拋 WrongPassword。 */
  async saveSettings(password: string, settings: AlertSettings): Promise<void> {
    const errors = validate(settings.cities, settings.slots);
    if (errors.length) throw new AdminError(summarizeErrors(errors));
    await this.rpc("admin_save_alert_settings", { p_password: password, ...buildPayload(settings.cities, settings.slots) });
  }
}
