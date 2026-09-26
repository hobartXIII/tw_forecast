/** 「立即更新」的伺服器端邏輯（只給 api/ 的 Vercel Functions 用，不會打包進瀏覽器）。

對應 Python 的 github_dispatch.py 與 update_gate.py 的 DispatchLog（見 VERCEL_PLAN.md §3）：
- 可否更新 = 距上次成功更新滿 20 分鐘（pipeline_status，沿用 lib/updateGate.evaluate）
  且 GitHub 上沒有尚未完成的手動 run（取代 DispatchLog；F5、新分頁、其他使用者看到的都是同一個狀態）。
- 讀不到 pipeline_status 或 GitHub API 失敗時一律不放行，訊息遮蔽 token。

輸入：環境變數（ServerEnv）、fetch（可注入，測試時不連網）、現在時間。輸出：UpdateStatus／DispatchResult（JSON）。
注意：api/ 由 Vercel 以 Node ESM 執行，相對匯入要寫 .js 副檔名。
*/
import { evaluate } from "../lib/updateGate.js";
import type { StatusRow } from "../lib/repository";

export const WORKFLOW_FILE = "weather_worker.yml";
export const DISPATCH_REF = "main";
/** 建立超過這麼久還沒完成的手動 run 不再算鎖定（run 卡住時不會一直停用，對應原本的 DISPATCH_LOCK_MINUTES）。 */
export const RUN_LOCK_MINUTES = 10;
const TIMEOUT_MS = 10_000;
export const NOT_CONFIGURED = "尚未設定 GH_REPO / GH_DISPATCH_TOKEN，暫不開放手動更新";
export const NO_DATABASE = "尚未設定 SUPABASE_URL / SUPABASE_ANON_KEY，暫不開放手動更新";

export interface ServerEnv {
  SUPABASE_URL?: string;
  SUPABASE_ANON_KEY?: string;
  VITE_SUPABASE_URL?: string;
  VITE_SUPABASE_ANON_KEY?: string;
  GH_REPO?: string;
  GH_DISPATCH_TOKEN?: string;
}

/** 回給瀏覽器的狀態（時間為 ISO 字串）。 */
export interface UpdateStatus {
  allowed: boolean;
  message: string;
  waitSeconds: number | null;
  elapsedMinutes: number | null;
  inProgress: boolean;
  lastSuccess: string | null;
  /** 伺服器判斷時的時間；瀏覽器以它比對「觸發之後是否已有新的成功更新」，不受使用者電腦時鐘影響。 */
  checkedAt: string;
}

export interface DispatchResult {
  ok: boolean;
  message: string;
  status: UpdateStatus;
}

type Fetch = typeof fetch;

/** 遮蔽 token 與金鑰：環境變數裡的值，以及 GitHub token、JWT（Supabase 金鑰）的樣式。 */
export function maskSecrets(text: string, secrets: (string | undefined)[] = []): string {
  let out = text;
  for (const s of secrets) if (s && s.length >= 8) out = out.split(s).join("***");
  return out
    .replace(/\b(gh[pousr]_|github_pat_)[A-Za-z0-9_]+/g, "$1***")
    .replace(/\beyJ[\w-]+\.[\w-]+\.[\w-]+/g, "***");
}

const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));

function supabaseConfig(env: ServerEnv) {
  const url = (env.SUPABASE_URL || env.VITE_SUPABASE_URL)?.trim();
  const key = (env.SUPABASE_ANON_KEY || env.VITE_SUPABASE_ANON_KEY)?.trim();
  return url && key ? { url: url.replace(/\/+$/, ""), key } : null;
}

function githubConfig(env: ServerEnv) {
  const repo = env.GH_REPO?.trim();
  const token = env.GH_DISPATCH_TOKEN?.trim();
  return repo && token ? { repo, token } : null;
}

const githubHeaders = (token: string) => ({
  Authorization: `Bearer ${token}`,
  Accept: "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
});

/** 讀 pipeline_status（Supabase REST，anon key，RLS 允許讀取）。 */
export async function readPipelineStatus(fetchFn: Fetch, url: string, key: string): Promise<StatusRow[]> {
  const resp = await fetchFn(`${url}/rest/v1/pipeline_status?select=trigger_type,last_success_at,last_run_at`, {
    headers: { apikey: key, Authorization: `Bearer ${key}` }, signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!resp.ok) throw new Error(`讀取 pipeline_status 失敗（HTTP ${resp.status}）`);
  const rows = (await resp.json()) as Record<string, unknown>[];
  const time = (v: unknown) => (v ? new Date(String(v)) : null);
  return rows.map((r) => ({
    trigger_type: String(r.trigger_type), last_success_at: time(r.last_success_at), last_run_at: time(r.last_run_at),
  }));
}

/** GitHub 上是否有建立不到 RUN_LOCK_MINUTES 分鐘、尚未完成的手動（workflow_dispatch）run。 */
export async function hasPendingManualRun(fetchFn: Fetch, repo: string, token: string, now: Date): Promise<boolean> {
  const resp = await fetchFn(
    `https://api.github.com/repos/${repo}/actions/workflows/${WORKFLOW_FILE}/runs?event=workflow_dispatch&per_page=10`,
    { headers: githubHeaders(token), signal: AbortSignal.timeout(TIMEOUT_MS) });
  if (!resp.ok) throw new Error(`查詢 GitHub workflow runs 失敗（HTTP ${resp.status}）`);
  const body = (await resp.json()) as { workflow_runs?: { status?: string; created_at?: string }[] };
  const since = now.getTime() - RUN_LOCK_MINUTES * 60_000;
  return (body.workflow_runs ?? []).some((r) =>
    r.status !== "completed" && !!r.created_at && new Date(r.created_at).getTime() >= since);
}

const blocked = (message: string, now: Date): UpdateStatus => ({
  allowed: false, message, waitSeconds: null, elapsedMinutes: null, inProgress: false, lastSuccess: null,
  checkedAt: now.toISOString(),
});

/** 目前可否手動更新。任何一步失敗都不放行，並附上（遮蔽過的）原因。 */
export async function getUpdateStatus(env: ServerEnv, fetchFn: Fetch = fetch, now = new Date()): Promise<UpdateStatus> {
  const db = supabaseConfig(env);
  if (!db) return blocked(NO_DATABASE, now);
  const gh = githubConfig(env);
  if (!gh) return blocked(NOT_CONFIGURED, now);
  try {
    const [rows, inProgress] = await Promise.all([
      readPipelineStatus(fetchFn, db.url, db.key).catch(() => null), // 讀不到由 evaluate 回「無法確認」
      hasPendingManualRun(fetchFn, gh.repo, gh.token, now),
    ]);
    const gate = evaluate(rows, now, { inProgress });
    return {
      allowed: gate.allowed, message: gate.message, waitSeconds: gate.waitSeconds, elapsedMinutes: gate.elapsedMinutes,
      inProgress, lastSuccess: gate.lastSuccess?.toISOString() ?? null, checkedAt: now.toISOString(),
    };
  } catch (e) {
    return blocked(`無法確認更新狀態，暫不開放手動更新：${maskSecrets(errorText(e), [gh.token, db.key])}`, now);
  }
}

/** 伺服器端重新判斷一次（不信任瀏覽器），通過才觸發 workflow_dispatch（main 分支）。 */
export async function dispatchUpdate(env: ServerEnv, fetchFn: Fetch = fetch, now = new Date()): Promise<DispatchResult> {
  const status = await getUpdateStatus(env, fetchFn, now);
  if (!status.allowed) return { ok: false, message: status.message, status };
  const gh = githubConfig(env)!; // allowed 代表已設定
  try {
    const resp = await fetchFn(`https://api.github.com/repos/${gh.repo}/actions/workflows/${WORKFLOW_FILE}/dispatches`, {
      method: "POST", headers: { ...githubHeaders(gh.token), "Content-Type": "application/json" },
      body: JSON.stringify({ ref: DISPATCH_REF }), signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (resp.status === 200 || resp.status === 204) { // 官方文件現列 200、實測為 204，兩者都算成功
      return { ok: true, message: "", status: { ...status, allowed: false, inProgress: true } };
    }
    const text = (await resp.text()).slice(0, 200);
    return { ok: false, message: maskSecrets(`觸發失敗（HTTP ${resp.status}）：${text}`, [gh.token]), status };
  } catch (e) {
    return { ok: false, message: maskSecrets(`無法連線至 GitHub：${errorText(e)}`, [gh.token]), status };
  }
}
