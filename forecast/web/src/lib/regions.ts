/** 縣市 → 分區（北／中／南／東／離島）靜態對照表與查詢函式。 */

export const REGIONS: Record<string, string[]> = {
  北部地區: ["臺北市", "新北市", "基隆市", "桃園市", "新竹市", "新竹縣"],
  中部地區: ["苗栗縣", "臺中市", "彰化縣", "南投縣", "雲林縣"],
  南部地區: ["嘉義市", "嘉義縣", "臺南市", "高雄市", "屏東縣"],
  東部地區: ["宜蘭縣", "花蓮縣", "臺東縣"],
  離島地區: ["澎湖縣", "金門縣", "連江縣"],
};
export const REGION_NAMES = Object.keys(REGIONS);
export const ALL_REGIONS = "全部地區";
export const ALL_CITIES = "全部縣市";

export const CITY_TO_REGION: Record<string, string> = Object.fromEntries(
  Object.entries(REGIONS).flatMap(([region, cities]) => cities.map((c) => [c, region])),
);
/** 北 → 中 → 南 → 東 → 離島 */
export const CITY_ORDER: string[] = Object.values(REGIONS).flat();

/** API 用「臺」，統一字形以免對照失敗。 */
export function normalizeCity(name: string): string {
  return name.replaceAll("台", "臺");
}

/** 縣市所屬地區；查不到回傳 null。 */
export function regionOf(city: string): string | null {
  return CITY_TO_REGION[normalizeCity(city)] ?? null;
}

/** 地區內的縣市清單；「全部地區」回傳全部縣市。 */
export function citiesIn(region: string): string[] {
  return region === ALL_REGIONS ? CITY_ORDER : REGIONS[region];
}
