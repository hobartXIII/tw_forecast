/** 「立即更新」的伺服器端邏輯（api/ 用）：fetch 換成假的，不連網。對應 test_github_dispatch.py 與 update_gate 的鎖定案例。 */
import { describe, expect, it, vi } from "vitest";

import {
  NOT_CONFIGURED, NO_DATABASE, RUN_LOCK_MINUTES, dispatchUpdate, getUpdateStatus, maskSecrets, type ServerEnv,
} from "../src/server/updateService";
import { IN_PROGRESS_MESSAGE, UNKNOWN_MESSAGE } from "../src/lib/updateGate";
import { tw } from "./fakes";

const NOW = tw(2026, 9, 21, 10);
const TOKEN = "github_pat_SECRET1234567890";
const ENV: ServerEnv = { SUPABASE_URL: "https://x.supabase.co/", SUPABASE_ANON_KEY: "anon-key-123", GH_REPO: "o/r", GH_DISPATCH_TOKEN: TOKEN };

const minutesAgo = (m: number) => new Date(NOW.getTime() - m * 60_000).toISOString();

interface Fake {
  status?: Record<string, unknown>[] | number; // 列或 HTTP 錯誤碼
  runs?: { status: string; created_at: string }[] | number;
  dispatch?: number | Error;
}

function fakeFetch({ status = [{ trigger_type: "schedule", last_success_at: minutesAgo(60), last_run_at: null }], runs = [], dispatch = 204 }: Fake = {}) {
  return vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const json = (body: unknown, code = 200) => new Response(JSON.stringify(body), { status: code });
    if (url.includes("/rest/v1/pipeline_status")) {
      expect((init?.headers as Record<string, string>).apikey).toBe("anon-key-123");
      return typeof status === "number" ? json({}, status) : json(status);
    }
    if (url.includes("/runs?")) {
      expect(url).toContain("event=workflow_dispatch");
      return typeof runs === "number" ? json({ message: `bad ${TOKEN}` }, runs) : json({ workflow_runs: runs });
    }
    if (url.endsWith("/dispatches")) {
      expect(init?.method).toBe("POST");
      expect(JSON.parse(String(init?.body))).toEqual({ ref: "main" });
      if (dispatch instanceof Error) throw dispatch;
      return new Response(dispatch === 204 ? null : `denied ${TOKEN}`, { status: dispatch });
    }
    throw new Error(`unexpected ${url}`);
  });
}

describe("getUpdateStatus", () => {
  it("滿 20 分鐘且沒有進行中的手動 run：放行", async () => {
    const s = await getUpdateStatus(ENV, fakeFetch(), NOW);
    expect([s.allowed, s.inProgress, s.lastSuccess, s.checkedAt]).toEqual([true, false, minutesAgo(60), NOW.toISOString()]);
  });

  it("不滿間隔：不放行並附等待秒數", async () => {
    const s = await getUpdateStatus(ENV, fakeFetch({ status: [{ trigger_type: "manual", last_success_at: minutesAgo(5) }] }), NOW);
    expect(s.allowed).toBe(false);
    expect(s.waitSeconds).toBeCloseTo(15 * 60);
    expect(s.elapsedMinutes).toBe(5);
  });

  it("GitHub 上有未完成的手動 run：不放行（排隊中、執行中都算）", async () => {
    for (const status of ["queued", "in_progress", "waiting"]) {
      const s = await getUpdateStatus(ENV, fakeFetch({ runs: [{ status, created_at: minutesAgo(1) }] }), NOW);
      expect([s.allowed, s.inProgress, s.message]).toEqual([false, true, IN_PROGRESS_MESSAGE]);
    }
  });

  it(`已完成的 run、或建立超過 ${RUN_LOCK_MINUTES} 分鐘仍未完成的 run 不算鎖定`, async () => {
    const runs = [{ status: "completed", created_at: minutesAgo(1) }, { status: "in_progress", created_at: minutesAgo(RUN_LOCK_MINUTES + 1) }];
    expect((await getUpdateStatus(ENV, fakeFetch({ runs }), NOW)).allowed).toBe(true);
  });

  it("讀不到 pipeline_status：不放行（無法確認）", async () => {
    const s = await getUpdateStatus(ENV, fakeFetch({ status: 500 }), NOW);
    expect([s.allowed, s.message]).toEqual([false, UNKNOWN_MESSAGE]);
  });

  it("GitHub API 失敗：不放行，訊息不含 token", async () => {
    const s = await getUpdateStatus(ENV, fakeFetch({ runs: 401 }), NOW);
    expect(s.allowed).toBe(false);
    expect(s.message).toContain("HTTP 401");
    expect(s.message).not.toContain("SECRET");
  });

  it("未設定 GitHub 或資料庫：不放行，也不連網", async () => {
    const f = fakeFetch();
    expect((await getUpdateStatus({ ...ENV, GH_DISPATCH_TOKEN: "" }, f, NOW)).message).toBe(NOT_CONFIGURED);
    expect((await getUpdateStatus({ GH_REPO: "o/r", GH_DISPATCH_TOKEN: TOKEN }, f, NOW)).message).toBe(NO_DATABASE);
    expect(f).not.toHaveBeenCalled();
  });

  it("資料庫設定可沿用 VITE_ 開頭的變數", async () => {
    const env = { VITE_SUPABASE_URL: "https://x.supabase.co", VITE_SUPABASE_ANON_KEY: "anon-key-123", GH_REPO: "o/r", GH_DISPATCH_TOKEN: TOKEN };
    expect((await getUpdateStatus(env, fakeFetch(), NOW)).allowed).toBe(true);
  });
});

describe("dispatchUpdate", () => {
  it("通過判斷才觸發；成功後狀態改為更新中", async () => {
    const f = fakeFetch();
    const r = await dispatchUpdate(ENV, f, NOW);
    expect(r.ok).toBe(true);
    expect([r.status.allowed, r.status.inProgress]).toEqual([false, true]);
    expect(f.mock.calls.some(([u]) => String(u).endsWith("/dispatches"))).toBe(true);
  });

  it("HTTP 200 也算成功", async () => {
    expect((await dispatchUpdate(ENV, fakeFetch({ dispatch: 200 }), NOW)).ok).toBe(true);
  });

  it("伺服器端判斷不通過就不觸發（不信任瀏覽器）", async () => {
    const f = fakeFetch({ runs: [{ status: "queued", created_at: minutesAgo(1) }] });
    const r = await dispatchUpdate(ENV, f, NOW);
    expect([r.ok, r.message]).toEqual([false, IN_PROGRESS_MESSAGE]);
    expect(f.mock.calls.some(([u]) => String(u).endsWith("/dispatches"))).toBe(false);
  });

  it("GitHub 拒絕或連不上：回傳原因，不含 token", async () => {
    const denied = await dispatchUpdate(ENV, fakeFetch({ dispatch: 403 }), NOW);
    expect([denied.ok, denied.message.includes("HTTP 403"), denied.message.includes("SECRET")]).toEqual([false, true, false]);
    const down = await dispatchUpdate(ENV, fakeFetch({ dispatch: new Error(`connect failed ${TOKEN}`) }), NOW);
    expect(down.message).toContain("無法連線至 GitHub");
    expect(down.message).not.toContain("SECRET");
  });
});

describe("maskSecrets", () => {
  it("遮蔽指定的值與 GitHub token、JWT 樣式", () => {
    expect(maskSecrets("a my-secret-value b", ["my-secret-value"])).toBe("a *** b");
    expect(maskSecrets("t=ghp_abcDEF123 x")).toBe("t=ghp_*** x");
    expect(maskSecrets("key eyJhbGc.eyJzdWI.sig-_1")).toBe("key ***");
  });
});
