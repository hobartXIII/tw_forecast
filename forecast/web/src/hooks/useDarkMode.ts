/** 媒體查詢與主題的即時結果（切換時即時更新）：深色模式給圖表選配色，窄螢幕給圖表的圖例換行。 */
import { useCallback, useSyncExternalStore } from "react";

import { DARK_QUERY, getTheme, isDark, setTheme, subscribeTheme, type ThemeMode } from "../lib/theme";

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

/** 目前選的主題（自動／淺色／深色）與切換函式。 */
export function useThemeMode(): [ThemeMode, (mode: ThemeMode) => void] {
  return [useSyncExternalStore(subscribeTheme, getTheme, () => "auto" as ThemeMode), setTheme];
}

/** 目前實際是否為深色：頁面上選了深色，或選「自動」且系統為深色。 */
export function useDarkMode(): boolean {
  const [mode] = useThemeMode();
  return isDark(mode, useMediaQuery(DARK_QUERY));
}

/** 是否為手機寬度。 */
export const useNarrow = () => useMediaQuery(NARROW_QUERY);
