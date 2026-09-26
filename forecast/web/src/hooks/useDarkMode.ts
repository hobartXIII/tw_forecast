/** 媒體查詢的即時結果（切換時即時更新）：深色模式給圖表選配色，窄螢幕給圖表的圖例換行。 */
import { useCallback, useSyncExternalStore } from "react";

/** 與 global.css 手機版的斷點相同。 */
export const NARROW_QUERY = "(max-width: 640px)";

export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback((onChange: () => void) => {
    const media = window.matchMedia?.(query);
    media?.addEventListener("change", onChange);
    return () => media?.removeEventListener("change", onChange);
  }, [query]);
  return useSyncExternalStore(subscribe, () => window.matchMedia?.(query).matches ?? false, () => false);
}

/** 目前是否為深色模式（跟著作業系統／瀏覽器設定）。 */
export const useDarkMode = () => useMediaQuery("(prefers-color-scheme: dark)");

/** 是否為手機寬度。 */
export const useNarrow = () => useMediaQuery(NARROW_QUERY);
