/** 分頁：頁籤列 + 目前分頁的內容。只渲染目前的分頁（圖表與查詢不會在背景執行）。 */
import { useState, type ReactNode } from "react";

export interface TabItem {
  label: string;
  render: () => ReactNode;
}

export function Tabs({ items }: { items: TabItem[] }) {
  const [active, setActive] = useState(0);
  const index = Math.min(active, items.length - 1); // 分頁數變少（切到單一縣市）時不要超出範圍
  return (
    <div className="tabs">
      <div className="tab-list" role="tablist">
        {items.map((t, i) => (
          <button
            key={t.label}
            role="tab"
            aria-selected={i === index}
            className="tab"
            onClick={() => setActive(i)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="tab-panel">{items[index]?.render()}</div>
    </div>
  );
}
