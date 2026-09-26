/** GET /api/update-status：目前可否手動更新（邏輯在 src/server/updateService.ts）。 */
import { getUpdateStatus } from "../src/server/updateService.js";

export async function GET(): Promise<Response> {
  return Response.json(await getUpdateStatus(process.env), { headers: { "Cache-Control": "no-store" } });
}
