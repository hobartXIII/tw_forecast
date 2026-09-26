/** 主題切換按鈕：點一下依序換成 自動 → 淺色 → 深色 → 自動（lib/theme.ts）。

電腦版是只有圖示的小按鈕（滑鼠移上去顯示目前主題與下一個）；手機版收在「☰ 選單」裡，
顯示「圖示 + 主題：文字」（CSS 依寬度切換顯示）。
*/
import { useThemeMode } from "../hooks/useDarkMode";
import { THEME_LABELS, nextTheme } from "../lib/theme";

export function ThemeToggle() {
  const [mode, setMode] = useThemeMode();
  const now = THEME_LABELS[mode];
  const next = THEME_LABELS[nextTheme(mode)];
  const hint = `主題：${now.text}（點一下切換為${next.text}）`;
  return (
    <button type="button" className="theme-toggle" aria-label={hint} title={hint} onClick={() => setMode(nextTheme(mode))}>
      <span aria-hidden="true">{now.icon}</span>
      <span className="theme-toggle-text" aria-hidden="true">主題：{now.text}</span>
    </button>
  );
}
