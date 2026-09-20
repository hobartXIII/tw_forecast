"""縣市 → 分區 (北/中/南/東/離島) 靜態對照表。"""
REGIONS: dict[str, list[str]] = {
    "北部地區": ["臺北市", "新北市", "基隆市", "桃園市", "新竹市", "新竹縣"],
    "中部地區": ["苗栗縣", "臺中市", "彰化縣", "南投縣", "雲林縣"],
    "南部地區": ["嘉義市", "嘉義縣", "臺南市", "高雄市", "屏東縣"],
    "東部地區": ["宜蘭縣", "花蓮縣", "臺東縣"],
    "離島地區": ["澎湖縣", "金門縣", "連江縣"],
}
ALL_REGIONS = "全部地區"

CITY_TO_REGION: dict[str, str] = {c: r for r, cities in REGIONS.items() for c in cities}
CITY_ORDER: list[str] = [c for cities in REGIONS.values() for c in cities]


def normalize_city(name: str) -> str:
    """API 用「臺」，統一字形以免對照失敗。"""
    return name.replace("台", "臺")


def region_of(city: str) -> str | None:
    return CITY_TO_REGION.get(normalize_city(city))


def cities_in(region: str) -> list[str]:
    return CITY_ORDER if region == ALL_REGIONS else REGIONS[region]
