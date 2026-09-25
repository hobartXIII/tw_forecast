/** 篩選範圍 ↔ 網址參數（?region=中部地區 或 ?city=臺中市），重新整理或分享網址後保留選擇。

地區與縣市互斥：有 city 時忽略 region；不認得的值一律退回全台。
*/
import { ALL_REGIONS, CITY_ORDER, REGIONS, normalizeCity } from "./regions";
import { Scope } from "./scope";

export function scopeFromSearch(search: string): Scope {
  const params = new URLSearchParams(search);
  const city = params.get("city");
  if (city && CITY_ORDER.includes(normalizeCity(city))) return new Scope(ALL_REGIONS, normalizeCity(city));
  const region = params.get("region");
  return region && region in REGIONS ? new Scope(region) : new Scope();
}

/** 回傳 "?city=…"、"?region=…"，全台時回傳空字串。 */
export function searchFromScope(scope: Scope): string {
  if (scope.city) return `?${new URLSearchParams({ city: scope.city })}`;
  if (scope.region !== ALL_REGIONS) return `?${new URLSearchParams({ region: scope.region })}`;
  return "";
}
