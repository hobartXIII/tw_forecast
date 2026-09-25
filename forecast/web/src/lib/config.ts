/** 前端設定：從 Vite 環境變數讀取 Supabase 連線資訊（只能是 anon key，權限由 RLS 控制）。 */

export const FORECAST_TABLE = "weather_forecasts";
export const STATUS_TABLE = "pipeline_status";

export interface SupabaseConfig {
  url: string;
  anonKey: string;
}

/** 兩個變數都有值才回傳設定，缺任何一個回傳 null（畫面據此顯示「尚未設定」）。 */
export function readSupabaseConfig(env: Record<string, string | undefined>): SupabaseConfig | null {
  const url = env.VITE_SUPABASE_URL?.trim();
  const anonKey = env.VITE_SUPABASE_ANON_KEY?.trim();
  return url && anonKey ? { url, anonKey } : null;
}
