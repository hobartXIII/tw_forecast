// @vitest-environment jsdom
/** 主題切換：順序、記住選擇（讀寫失敗時不影響）、套用到 <html data-theme>。 */
import { describe, expect, it } from "vitest";

import { THEME_KEY, applyTheme, isDark, nextTheme, readTheme, saveTheme } from "../src/lib/theme";

const memory = (init: Record<string, string> = {}) => {
  const data = { ...init };
  return {
    data,
    getItem: (k: string) => data[k] ?? null,
    setItem: (k: string, v: string) => { data[k] = v; },
    removeItem: (k: string) => { delete data[k]; },
  };
};
const broken = {
  getItem: () => { throw new Error("denied"); },
  setItem: () => { throw new Error("denied"); },
  removeItem: () => { throw new Error("denied"); },
};

describe("theme", () => {
  it("依序切換：自動 → 淺色 → 深色 → 自動", () => {
    expect([nextTheme("auto"), nextTheme("light"), nextTheme("dark")]).toEqual(["light", "dark", "auto"]);
  });

  it("讀取記住的主題；沒有、值不對或不允許存取時為自動", () => {
    expect(readTheme(memory({ [THEME_KEY]: "dark" }))).toBe("dark");
    expect(readTheme(memory())).toBe("auto");
    expect(readTheme(memory({ [THEME_KEY]: "purple" }))).toBe("auto");
    expect(readTheme(broken)).toBe("auto");
  });

  it("記住淺色／深色；自動就刪掉紀錄；寫入失敗不拋錯", () => {
    const s = memory();
    saveTheme("light", s);
    expect(s.data[THEME_KEY]).toBe("light");
    saveTheme("auto", s);
    expect(THEME_KEY in s.data).toBe(false);
    expect(() => saveTheme("dark", broken)).not.toThrow();
  });

  it("<html> 一律寫入實際的淺色或深色", () => {
    const root = document.createElement("html");
    applyTheme("auto", root, true);
    expect(root.dataset.theme).toBe("dark");
    applyTheme("auto", root, false);
    expect(root.dataset.theme).toBe("light");
    applyTheme("light", root, true);
    expect(root.dataset.theme).toBe("light");
    applyTheme("dark", root, false);
    expect(root.dataset.theme).toBe("dark");
    expect([isDark("auto", true), isDark("light", true), isDark("dark", false)]).toEqual([true, false, true]);
  });
});
