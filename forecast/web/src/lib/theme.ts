/** 淺色／深色主題的切換：自動（跟著系統）→ 淺色 → 深色 → 自動。

選擇記在 localStorage（只是個人偏好，讀寫失敗時當作「自動」，不影響頁面）。
套用方式：算出實際是淺色或深色，一律寫到 <html data-theme="light"｜"dark">，global.css 只看這個屬性
（深色規則只有一份）；選「自動」時另外監聽系統設定的變化（initTheme）。
index.html 在頁面載入前就先套用一次（同樣的 key 與規則），避免先閃一下另一種顏色。
這裡也放一個很小的共用狀態，讓按鈕與圖表（Vega 讀不到 CSS 變數）同步。
*/
export type ThemeMode = "auto" | "light" | "dark";

export const THEME_KEY = "tw-forecast-theme";
export const THEME_ORDER: ThemeMode[] = ["auto", "light", "dark"];
export const THEME_LABELS: Record<ThemeMode, { icon: string; text: string }> = {
  auto: { icon: "🌓", text: "自動（跟著系統）" }, // 半亮半暗：淺色或深色都有可能
  light: { icon: "☀️", text: "淺色" },
  dark: { icon: "🌙", text: "深色" },
};

/** 按一下之後的主題。 */
export function nextTheme(mode: ThemeMode): ThemeMode {
  return THEME_ORDER[(THEME_ORDER.indexOf(mode) + 1) % THEME_ORDER.length];
}

/** 讀取記住的主題；沒有、值不對或瀏覽器不允許存取（私密模式等）時為「自動」。 */
export function readTheme(storage: Pick<Storage, "getItem"> | undefined = globalThis.localStorage): ThemeMode {
  try {
    const v = storage?.getItem(THEME_KEY);
    return v === "light" || v === "dark" ? v : "auto";
  } catch {
    return "auto";
  }
}

/** 記住主題（「自動」就刪掉紀錄）；寫入失敗時忽略。 */
export function saveTheme(mode: ThemeMode, storage: Pick<Storage, "setItem" | "removeItem"> | undefined = globalThis.localStorage) {
  try {
    if (mode === "auto") storage?.removeItem(THEME_KEY);
    else storage?.setItem(THEME_KEY, mode);
  } catch {
    // 不允許寫入時，這次瀏覽仍然有效，只是下次不會記得
  }
}

/** 實際是否為深色：選了深色，或自動且系統為深色。 */
export const isDark = (mode: ThemeMode, systemDark: boolean) => mode === "dark" || (mode === "auto" && systemDark);

export const DARK_QUERY = "(prefers-color-scheme: dark)";
const systemDark = () => globalThis.matchMedia?.(DARK_QUERY).matches ?? false;

/** 在 <html> 套用主題（寫入實際的淺色或深色）。 */
export function applyTheme(mode: ThemeMode, root: HTMLElement = document.documentElement, dark = systemDark()) {
  root.setAttribute("data-theme", isDark(mode, dark) ? "dark" : "light");
}

// ---- 共用狀態（整頁一份）----
let current: ThemeMode | null = null;
const listeners = new Set<() => void>();

export function getTheme(): ThemeMode {
  current ??= readTheme();
  return current;
}

export function setTheme(mode: ThemeMode) {
  current = mode;
  saveTheme(mode);
  applyTheme(mode);
  listeners.forEach((l) => l());
}

export function subscribeTheme(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** 頁面啟動時呼叫一次：套用記住的主題，並在「自動」時跟著系統設定即時切換。回傳解除監聽的函式。 */
export function initTheme(): () => void {
  applyTheme(getTheme());
  const media = globalThis.matchMedia?.(DARK_QUERY);
  const onChange = () => { if (getTheme() === "auto") applyTheme("auto"); };
  media?.addEventListener("change", onChange);
  return () => media?.removeEventListener("change", onChange);
}
