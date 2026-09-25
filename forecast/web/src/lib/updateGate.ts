/** 手動更新的門檻判斷（瀏覽器與 api/ 的 Function 共用）。

輸入：pipeline_status 的列、現在時間、GitHub 上是否有尚未完成的手動更新。
輸出：Gate（可否更新與提示文字）。

依據是資料庫 pipeline_status 表記錄的「最後一次成功更新時間」（排程與手動取較新者），與使用者人數、
瀏覽器狀態無關；讀不到（null 或空表）一律不放行。排程不受此限制。
觸發後到資料庫出現新的成功紀錄之間，改以 GitHub 上是否有排隊中／執行中的手動 run 判斷（見 VERCEL_PLAN.md §3）。
*/
import type { StatusRow } from "./repository";

export const MIN_INTERVAL_MINUTES = 20;
export const UNKNOWN_MESSAGE = "無法確認最後更新時間，暫不開放手動更新";
export const IN_PROGRESS_MESSAGE = "已觸發更新，正在等待完成，請稍後按「重新載入資料」";

/** 判斷結果。只有「距上次成功更新不滿間隔」才有 waitSeconds（還要等幾秒）與 elapsedMinutes（已過幾分鐘）。 */
export interface Gate {
  allowed: boolean;
  message: string;
  lastSuccess: Date | null;
  waitSeconds: number | null;
  elapsedMinutes: number | null;
}

const gate = (allowed: boolean, message = "", lastSuccess: Date | null = null, extra: Partial<Gate> = {}): Gate => ({
  allowed, message, lastSuccess, waitSeconds: null, elapsedMinutes: null, ...extra,
});

/** rows 為 pipeline_status 的列（讀取失敗傳 null）；inProgress 為 GitHub 上是否有尚未完成的手動更新。 */
export function evaluate(
  rows: StatusRow[] | null, now: Date, { minMinutes = MIN_INTERVAL_MINUTES, inProgress = false } = {},
): Gate {
  if (!rows?.length) return gate(false, UNKNOWN_MESSAGE);
  const times = rows.map((r) => r.last_success_at).filter((t): t is Date => t !== null);
  const last = times.length ? new Date(Math.max(...times.map((t) => t.getTime()))) : null;
  if (inProgress) return gate(false, IN_PROGRESS_MESSAGE, last);
  if (last === null) return gate(true); // 有紀錄表但從未成功更新過：沒有東西需要保護，放行
  const elapsedMs = now.getTime() - last.getTime();
  const waitMs = minMinutes * 60_000 - elapsedMs;
  if (waitMs > 0) {
    const elapsedMinutes = Math.max(Math.floor(elapsedMs / 60_000), 0);
    const waitMinutes = Math.ceil(waitMs / 60_000);
    return gate(false, `距上次更新僅 ${elapsedMinutes} 分鐘，手動更新需間隔至少 ${minMinutes} 分鐘，`
      + `請約 ${waitMinutes} 分鐘後再試`, last, { waitSeconds: waitMs / 1000, elapsedMinutes });
  }
  return gate(true, "", last);
}
