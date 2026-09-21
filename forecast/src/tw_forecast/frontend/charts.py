"""一週趨勢圖：氣溫（最高／最低／平均）與降雨機率。時間軸一律以台灣當地時間顯示。

氣溫與降雨機率都用同一種折線圖（SeriesChart）：每個系列一種顏色，可點圖例強調單一系列；
折線用 monotone 曲線（柔和且不會超出資料範圍）。單一縣市的氣溫圖把最高／平均／最低三條線畫在一起。

輸入：長表（forecast_time_start、系列、值）與現在時間。輸出：Altair 圖表物件。
"""
from dataclasses import dataclass

import altair as alt
import pandas as pd

RAIN_ALERT = 60  # 與後端告警預設降雨門檻一致；圖上以紅色虛線標示
# Okabe-Ito 色盲友善色盤；一個地區最多 6 個縣市，全台則是 5 個地區
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9"]
TEMP_LINE_COLUMNS = {"最高溫": "max_temp", "平均溫": "avg", "最低溫": "min_temp"}  # 單一縣市合併圖的線條順序
TEMP_LINE_COLORS = ["#D55E00", "#009E73", "#0072B2"]  # 暖色最高、綠色平均、冷色最低
MISSING_TIP = "0（氣象署未提供，以 0 顯示）"
X_AXIS = alt.Axis(format="%m/%d %H:%M", labelAngle=-30)
CHART_HEIGHT = 440


def _naive(series: pd.Series) -> pd.Series:
    """去掉時區保留台灣當地時間，避免瀏覽器再依本機時區換算。"""
    return series.dt.tz_localize(None)


def _now_rule(times: pd.Series, now) -> alt.Chart | None:
    """在「現在」畫一條虛線；現在不在圖表範圍內就不畫。"""
    now = pd.Timestamp(now)
    now = now.tz_localize(None) if now.tzinfo else now
    if not (times.min() - pd.Timedelta(hours=12) <= now <= times.max() + pd.Timedelta(hours=12)):
        return None
    return (alt.Chart(pd.DataFrame({"時段": [now]}))
            .mark_rule(strokeDash=[4, 4], color="#495057").encode(x="時段:T"))


@dataclass
class SeriesChart:
    """多系列折線圖的設定與繪製。

    order 決定顏色與圖例順序；colors 指定各系列顏色（與 order 對應），沒給就用 PALETTE。
    threshold 有值時（降雨機率）畫出門檻虛線，並把 >= 門檻的點放大加紅框。
    fill_zero=True 時，值為 NaN（來源未提供）的時段補 0 並以空心點標示、提示「氣象署未提供」；
    否則這些時段不畫。
    """
    y_title: str
    order: list[str]
    zero: bool = False
    threshold: float | None = None
    fill_zero: bool = False
    colors: list[str] | None = None

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        """輸入：含 forecast_time_start (tz-aware)、系列、值 的長表。輸出：繪圖用資料（時段、系列、值、未提供、顯示）。"""
        d = data.copy()
        d["未提供"] = d["值"].isna()
        if self.fill_zero:
            d["值"] = d["值"].fillna(0)
        else:
            d = d[~d["未提供"]]
        d["時段"] = _naive(d["forecast_time_start"])
        fmt = "{:.0f}" if self.threshold is not None else "{:.1f}"
        d["顯示"] = [MISSING_TIP if m else fmt.format(v) for m, v in zip(d["未提供"], d["值"])]
        return d[["時段", "系列", "值", "未提供", "顯示"]]

    def build(self, data: pd.DataFrame, now) -> alt.LayerChart:
        """畫圖：折線 + 資料點（可點圖例強調）+ 選擇性的門檻線與「現在」虛線。"""
        d = self.prepare(data)
        select = alt.selection_point(fields=["系列"], bind="legend")
        scale = alt.Scale(domain=self.order, range=self.colors or PALETTE[:len(self.order)])
        color = alt.Color("系列:N", scale=scale, legend=alt.Legend(title=None, orient="top"))
        series_color = alt.Color("系列:N", scale=scale, legend=None)  # 點用，避免重複圖例
        x = alt.X("時段:T", title=None, axis=X_AXIS)
        y = alt.Y("值:Q", title=self.y_title,
                  scale=alt.Scale(zero=self.zero,
                                  domain=[0, 100] if self.threshold is not None else alt.Undefined))
        opacity = alt.condition(select, alt.value(1), alt.value(0.15))
        tooltip = ["系列:N", alt.Tooltip("時段:T", format="%m/%d %H:%M"),
                   alt.Tooltip("顯示:N", title=self.y_title)]

        lines = alt.Chart(d).mark_line(strokeWidth=2.5, strokeJoin="round", interpolate="monotone").encode(
            x=x, y=y, color=color, opacity=opacity)
        real, missing = d[~d["未提供"]], d[d["未提供"]]
        if self.threshold is None:
            size, stroke = alt.value(45), alt.value("white")
        else:
            over = alt.datum["值"] >= self.threshold
            size = alt.condition(over, alt.value(160), alt.value(45))
            stroke = alt.condition(over, alt.value("#c92a2a"), alt.value("white"))
        layers = [lines, alt.Chart(real).mark_point(filled=True).encode(
            x=x, y=y, color=series_color, size=size, stroke=stroke, strokeWidth=alt.value(2),
            opacity=opacity, tooltip=tooltip)]
        if not missing.empty:  # 補值的點畫成空心（白底＋系列色外框），一眼看得出不是真的預報值
            layers.append(alt.Chart(missing).mark_point(filled=False, fill="white", size=45, strokeWidth=2).encode(
                x=x, y=y, color=series_color, opacity=opacity, tooltip=tooltip))
        if self.threshold is not None:
            layers.append(alt.Chart(pd.DataFrame({"y": [self.threshold]}))
                          .mark_rule(strokeDash=[6, 4], color="#c92a2a", opacity=0.6).encode(y="y:Q"))
        rule = _now_rule(d["時段"], now) if not d.empty else None
        if rule is not None:
            layers.append(rule)
        return alt.layer(*layers).add_params(select).properties(height=CHART_HEIGHT)
