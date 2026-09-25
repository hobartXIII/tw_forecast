/** 四張摘要卡片；內容由 lib/summary.ts 決定，這裡只負責畫出來。 */
import type { CSSProperties } from "react";

import type { CardModel } from "../lib/summary";

export const CARD_STAGGER_MS = 80; // 四張卡片依序淡入的間隔

export function SummaryCards({ cards }: { cards: CardModel[] }) {
  return (
    <div className="cards">
      {cards.map((c, i) => {
        const style = { "--delay": `${i * CARD_STAGGER_MS}ms`, ...(c.accent ? { "--accent": c.accent } : {}) } as CSSProperties;
        const width = c.meter === null || Number.isNaN(c.meter) ? null : Math.min(Math.max(c.meter, 0), 100);
        return (
          <div key={c.label} className="card" style={style}>
            <div className="card-label">{c.label}</div>
            <div className="card-value">
              <span style={c.textColor ? { color: c.textColor } : undefined}>{c.text}</span>
              {c.aside && <span className="card-aside">{c.aside}</span>}
            </div>
            {width !== null && <div className="meter"><span style={{ width: `${width}%` }} /></div>}
          </div>
        );
      })}
    </div>
  );
}
