import { describe, expect, it } from "vitest";

import { readSupabaseConfig } from "../src/lib/config";

describe("readSupabaseConfig", () => {
  it("兩個變數都有值才回傳設定，並去掉前後空白", () => {
    expect(readSupabaseConfig({ VITE_SUPABASE_URL: " https://x.supabase.co ", VITE_SUPABASE_ANON_KEY: "k" }))
      .toEqual({ url: "https://x.supabase.co", anonKey: "k" });
  });

  it("缺任何一個或為空白時回傳 null", () => {
    expect(readSupabaseConfig({})).toBeNull();
    expect(readSupabaseConfig({ VITE_SUPABASE_URL: "https://x.supabase.co" })).toBeNull();
    expect(readSupabaseConfig({ VITE_SUPABASE_URL: "https://x.supabase.co", VITE_SUPABASE_ANON_KEY: "  " })).toBeNull();
  });
});
