/** 提示框（對應 st.info／st.warning／st.error）。 */
import type { ReactNode } from "react";

export function Notice({ kind, children }: { kind: "info" | "warning" | "error" | "success"; children: ReactNode }) {
  return <div className={`notice notice-${kind}`} role={kind === "error" ? "alert" : "status"}>{children}</div>;
}
