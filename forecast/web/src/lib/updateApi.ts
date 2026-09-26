/** 瀏覽器呼叫 api/ 的「立即更新」Functions：GET /api/update-status、POST /api/dispatch。

回應的時間欄位轉成 Date；連不上或回應不是 JSON（例如本機只跑 `npm run dev` 而沒有 api/）時，
一律回傳「不放行」並附上原因，畫面照常顯示。
*/
import type { DispatchResult, UpdateStatus } from "../server/updateService";

export interface ClientUpdateStatus extends Omit<UpdateStatus, "lastSuccess" | "checkedAt"> {
  lastSuccess: Date | null;
  checkedAt: Date;
}

export interface ClientDispatchResult {
  ok: boolean;
  message: string;
  status: ClientUpdateStatus | null;
}

export const STATUS_URL = "/api/update-status";
export const DISPATCH_URL = "/api/dispatch";

const toClient = (s: UpdateStatus): ClientUpdateStatus => ({
  ...s, lastSuccess: s.lastSuccess ? new Date(s.lastSuccess) : null, checkedAt: new Date(s.checkedAt),
});

const reason = (e: unknown) => (e instanceof Error ? e.message : String(e));

async function readJson<T>(resp: Response): Promise<T> {
  if (!(resp.headers.get("content-type") ?? "").includes("application/json")) {
    throw new Error(`HTTP ${resp.status}，回應不是 JSON`);
  }
  return (await resp.json()) as T;
}

export async function fetchUpdateStatus(fetchFn: typeof fetch = fetch): Promise<ClientUpdateStatus> {
  try {
    return toClient(await readJson<UpdateStatus>(await fetchFn(STATUS_URL, { cache: "no-store" })));
  } catch (e) {
    return {
      allowed: false, message: `無法取得更新狀態，暫不開放手動更新（${reason(e)}）`, waitSeconds: null,
      elapsedMinutes: null, inProgress: false, lastSuccess: null, checkedAt: new Date(),
    };
  }
}

export async function requestDispatch(fetchFn: typeof fetch = fetch): Promise<ClientDispatchResult> {
  try {
    const r = await readJson<DispatchResult>(await fetchFn(DISPATCH_URL, { method: "POST" }));
    return { ok: r.ok, message: r.message, status: toClient(r.status) };
  } catch (e) {
    return { ok: false, message: `觸發更新失敗（${reason(e)}）`, status: null };
  }
}
