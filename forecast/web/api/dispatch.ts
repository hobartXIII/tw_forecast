/** POST /api/dispatch：伺服器端重新判斷一次，通過才觸發 workflow（邏輯在 src/server/updateService.ts）。 */
import { dispatchUpdate } from "../src/server/updateService.js";

export async function POST(): Promise<Response> {
  const result = await dispatchUpdate(process.env);
  return Response.json(result, { status: result.ok ? 200 : 409, headers: { "Cache-Control": "no-store" } });
}
