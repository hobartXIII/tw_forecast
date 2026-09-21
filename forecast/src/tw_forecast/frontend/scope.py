"""目前的篩選範圍（地區與縣市互斥）與依範圍整理資料的純函式。

輸入：使用者選的地區、縣市。輸出：顯示層級、範圍內的縣市清單、依範圍篩過的資料、圖表用的多系列長表。
不依賴 Streamlit，方便單元測試。
"""
from dataclasses import dataclass

import pandas as pd

from tw_forecast.frontend.regions import ALL_REGIONS, CITY_ORDER, REGIONS, cities_in, region_of
from tw_forecast.frontend.temperature import display_temp


def add_region(df: pd.DataFrame) -> pd.DataFrame:
    """加上 region（所屬地區）與 order（縣市在北→離島順序中的位置，查不到為 99）欄位。"""
    df = df.copy()
    df["region"] = df["location_name"].map(region_of)
    df["order"] = df["location_name"].map(lambda c: CITY_ORDER.index(c) if c in CITY_ORDER else 99)
    return df


@dataclass(frozen=True)
class Scope:
    """篩選範圍。地區與縣市互斥：選了縣市時 region 應為「全部地區」；city 為 None 代表沒有選縣市。"""
    region: str = ALL_REGIONS
    city: str | None = None

    @property
    def level(self) -> str:
        """顯示層級：city（單一縣市，依時段）、all（全台，依地區平均）、region（單一地區，依縣市）。"""
        if self.city:
            return "city"
        return "all" if self.region == ALL_REGIONS else "region"

    @property
    def home_region(self) -> str | None:
        """單一縣市時，該縣市所屬的地區（地圖與對照範圍用）；其他層級為 None。"""
        return region_of(self.city) if self.city else None

    @property
    def region_cities(self) -> list[str]:
        """地圖與「目前時段」範圍內的縣市（單一縣市時是它所屬地區的全部縣市，作為對照）。"""
        return cities_in(self.home_region) if self.home_region else cities_in(self.region)

    @property
    def cities(self) -> list[str]:
        """趨勢圖、明細與日期查詢實際涵蓋的縣市。"""
        return [self.city] if self.city else self.region_cities

    @property
    def label(self) -> str:
        """說明文字用的範圍名稱。"""
        return {"all": "全台各地區平均", "region": f"{self.region}各縣市", "city": self.city}[self.level]

    def table_drop_columns(self) -> list[str]:
        """表格要隱藏的欄位：單一縣市不需要「縣市」「地區」，單一地區不需要「地區」，全台全部顯示。"""
        if self.city:
            return ["縣市", "地區"]
        return ["地區"] if self.region != ALL_REGIONS else []

    def filter_current(self, current: pd.DataFrame) -> pd.DataFrame:
        """「目前時段」資料中屬於地圖範圍的縣市，依縣市順序排序。"""
        return current[current["location_name"].isin(self.region_cities)].sort_values("order")

    def filter_forecast(self, forecast: pd.DataFrame) -> pd.DataFrame | None:
        """趨勢與明細用的預報資料（加上平均溫 avg 欄位）；沒有資料（過期或範圍內為空）回傳 None。"""
        if forecast.empty:
            return None
        fc = forecast[forecast["location_name"].isin(self.cities)]
        return fc.assign(avg=display_temp(fc)) if not fc.empty else None

    def series_data(self, forecast: pd.DataFrame, column: str) -> tuple[pd.DataFrame, list[str]]:
        """多系列長表（系列、forecast_time_start、值）與圖例順序。

        全台 → 每地區平均一條線；單一地區 → 每縣市一條線；單一縣市 → 一條線。
        """
        key = "region" if self.level == "all" else "location_name"
        data = (forecast.groupby([key, "forecast_time_start"], as_index=False)[column].mean()
                .rename(columns={key: "系列", column: "值"}))
        order = [n for n in (list(REGIONS) if self.level == "all" else CITY_ORDER) if n in set(data["系列"])]
        return data, order
