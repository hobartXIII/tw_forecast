/** Supabase 連線（整個頁面共用一個）。沒有設定時回傳 null。 */
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { readSupabaseConfig } from "./config";

const config = readSupabaseConfig(import.meta.env);

export const supabase: SupabaseClient | null = config
  ? createClient(config.url, config.anonKey, { auth: { persistSession: false } })
  : null;
