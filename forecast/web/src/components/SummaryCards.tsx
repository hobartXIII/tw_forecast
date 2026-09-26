/** 重點摘要的輪播：四張卡片（內容由 lib/summary.ts 決定）一次顯示一張。

- 每 CAROUSEL_INTERVAL_MS 自動換下一張；滑鼠移上去、以鍵盤（Tab）把焦點移進輪播或手指觸碰時暫停。
  滑鼠點擊箭頭後焦點會留在按鈕上，這不算暫停（只看 :focus-visible），否則按過一次就再也不會自動換頁。
  系統設定「減少動態效果」時照樣換頁，只是取消淡入與滑動動畫（CSS）；Windows 關閉「動畫效果」也會被瀏覽器視為減少動態效果。
- 左右箭頭與圓點疊在卡片裡（左右兩側、底部）；手機可左右滑動（垂直滑動照常捲動頁面）。
- 四張卡片都留在頁面上、疊在同一格，切換時淡入並從換頁方向輕微滑入；看不到的卡片對螢幕閱讀器隱藏。
- 呼叫端以範圍當 key（見 App.tsx），切換地區／縣市時回到第一張。
*/
import { useEffect, useRef, useState, type CSSProperties } from "react";

import { CAROUSEL_INTERVAL_MS, swipeStep, wrapIndex } from "../lib/carousel";
import type { CardModel } from "../lib/summary";

function Card({ card, title }: { card: CardModel; title: string }) {
  const style = (card.accent ? { "--accent": card.accent } : {}) as CSSProperties;
  const width = card.meter === null || Number.isNaN(card.meter) ? null : Math.min(Math.max(card.meter, 0), 100);
  return (
    <div className="card" style={style}>
      {title && <div className="card-scope">{title}</div>}
      <div className="card-label">{card.label}</div>
      <div className={card.parts ? "card-value card-value-multi" : "card-value"}>
        {card.parts ? (
          card.parts.map((p, i) => (
            <span key={i}>
              {i > 0 && <span className="card-sep"> / </span>}
              <span style={p.color ? { color: p.color } : undefined}>{p.text}</span>
            </span>
          ))
        ) : (
          <span style={card.textColor ? { color: card.textColor } : undefined}>{card.text}</span>
        )}
        {card.aside && <span className="card-aside">{card.aside}</span>}
      </div>
      {card.sub && <div className="card-sub">{card.sub}</div>}
      {/* 沒有進度條的卡片也保留同樣的位置（不顯示），四張卡片的版型與高度才會和降雨卡片一致 */}
      {width !== null
        ? <div className="meter"><span style={{ width: `${width}%` }} /></div>
        : <div className="meter meter-placeholder" aria-hidden="true" />}
    </div>
  );
}

/** 焦點是鍵盤造成的（:focus-visible）才算；不支援此選擇器的環境一律不算。 */
function keyboardFocus(el: Element): boolean {
  try {
    return el.matches(":focus-visible");
  } catch {
    return false;
  }
}

/** title 為輪播最上方的範圍名稱（地區或縣市），四張卡片都一樣，切換時固定不動。 */
export function SummaryCards({ cards, title = "" }: { cards: CardModel[]; title?: string }) {
  const [active, setActive] = useState(0);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [touching, setTouching] = useState(false);
  const touchStart = useRef<{ x: number; y: number } | null>(null);

  const count = cards.length;
  const index = wrapIndex(active, count); // 卡片數變少時不要超出範圍
  const paused = hovered || focused || touching;
  const autoplay = count > 1 && !paused;
  const [direction, setDirection] = useState<1 | -1>(1); // 換頁方向：看不到的卡片從哪一邊滑入
  const go = (step: number) => {
    if (!step) return;
    setDirection(step > 0 ? 1 : -1);
    setActive((i) => wrapIndex(i + step, count));
  };

  // 每換一頁（不論自動或手動）都重新計時，手動切換後不會馬上又被換走
  useEffect(() => {
    if (!autoplay) return;
    const t = setTimeout(() => {
      setDirection(1);
      setActive((i) => wrapIndex(i + 1, count));
    }, CAROUSEL_INTERVAL_MS);
    return () => clearTimeout(t);
  }, [autoplay, index, count]);

  if (!count) return null;
  return (
    <section
      className="carousel"
      aria-roledescription="輪播"
      aria-label={title ? `重點摘要：${title}` : "重點摘要"}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={(e) => { if (keyboardFocus(e.target)) setFocused(true); }}
      onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setFocused(false); }}
      onTouchStart={(e) => {
        touchStart.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
        setTouching(true);
      }}
      onTouchEnd={(e) => {
        const start = touchStart.current;
        const t = e.changedTouches[0];
        if (start && t) go(swipeStep(t.clientX - start.x, t.clientY - start.y));
        touchStart.current = null;
        setTouching(false);
      }}
      onTouchCancel={() => { touchStart.current = null; setTouching(false); }}
    >
      <div className="carousel-viewport" aria-live={autoplay ? "off" : "polite"}>
        <div className="carousel-track" style={{ "--slide-from": `${direction * 16}px` } as CSSProperties}>
          {cards.map((c, i) => (
            <div
              key={c.label}
              className="carousel-slide"
              role="group"
              aria-roledescription="卡片"
              aria-label={`第 ${i + 1} 張，共 ${count} 張：${c.label}`}
              aria-hidden={i !== index}
            >
              <Card card={c} title={title} />
            </div>
          ))}
        </div>
      </div>
      {count > 1 && (
        <div className="carousel-controls">
          <button type="button" className="carousel-arrow" aria-label="上一張" onClick={() => go(-1)}>‹</button>
          <div className="carousel-dots">
            {cards.map((c, i) => (
              <button
                key={c.label}
                type="button"
                className="carousel-dot"
                aria-label={`顯示${c.label}`}
                aria-current={i === index ? "true" : undefined}
                onClick={() => go(i - index)}
              />
            ))}
          </div>
          <button type="button" className="carousel-arrow" aria-label="下一張" onClick={() => go(1)}>›</button>
        </div>
      )}
    </section>
  );
}
