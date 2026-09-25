/** 顯示一份 Vega-Lite 規格。vega-embed 較大，第一次用到圖表時才載入。 */
import { useEffect, useRef } from "react";
import type { TopLevelSpec } from "vega-lite";

export function VegaChart({ spec, dark }: { spec: TopLevelSpec; dark: boolean }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    let finalize: (() => void) | undefined;
    import("vega-embed").then(async ({ default: embed }) => {
      if (cancelled || !ref.current) return;
      const result = await embed(ref.current, spec, {
        actions: false, renderer: "svg", tooltip: { theme: dark ? "dark" : "light" },
      });
      if (cancelled) result.finalize();
      else finalize = () => result.finalize();
    });
    return () => {
      cancelled = true;
      finalize?.();
    };
  }, [spec, dark]);

  return <div ref={ref} className="chart" />;
}
