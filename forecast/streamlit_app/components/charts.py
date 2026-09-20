"""一週趨勢圖：氣溫（最高/最低）與降雨機率。時間軸一律以台灣當地時間顯示。

- 單一縣市：最高/最低雙線加灰色範圍帶（氣溫）、長條圖（降雨機率）。
- 多個縣市/地區：每個系列一種顏色的折線，可點圖例強調單一系列。
"""
import altair as alt
import pandas as pd

LABELS = {"max_temp": "最高氣溫", "min_temp": "最低氣溫"}
COLORS = {"最高氣溫": "#d9480f", "最低氣溫": "#1971c2"}
RAIN_ALERT = 60  # 與 fetch_and_store.py 的 ALERT_RAIN 一致
# Okabe-Ito 色盲友善色盤；一個地區最多 6 個縣市，全台則是 5 個地區
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9"]
X_AXIS = alt.Axis(format="%m/%d %H:%M", labelAngle=-30)


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


def temp_trend_chart(df: pd.DataFrame, now) -> alt.LayerChart:
    """df 需含 forecast_time_start (Asia/Taipei tz-aware)、min_temp、max_temp。"""
    data = df[["min_temp", "max_temp"]].copy()
    data["時段"] = _naive(df["forecast_time_start"])
    long = data.melt(id_vars="時段", value_vars=list(LABELS), var_name="項目", value_name="氣溫 (°C)")
    long["項目"] = long["項目"].map(LABELS)
    y_scale = alt.Scale(zero=False)
    band = (alt.Chart(data).mark_area(opacity=0.12, color="#868e96")
            .encode(x=alt.X("時段:T", title=None, axis=X_AXIS),
                    y=alt.Y("min_temp:Q", scale=y_scale, title="氣溫 (°C)"), y2="max_temp:Q"))
    lines = (alt.Chart(long).mark_line(point=True, strokeJoin="round")
             .encode(x=alt.X("時段:T", title=None, axis=X_AXIS),
                     y=alt.Y("氣溫 (°C):Q", scale=y_scale),
                     color=alt.Color("項目:N", scale=alt.Scale(domain=list(COLORS), range=list(COLORS.values())),
                                     legend=alt.Legend(title=None, orient="top")),
                     tooltip=[alt.Tooltip("時段:T", format="%m/%d %H:%M"), "項目:N",
                              alt.Tooltip("氣溫 (°C):Q", format=".1f")]))
    layers = [band, lines]
    rule = _now_rule(data["時段"], now)
    if rule is not None:
        layers.append(rule)
    return alt.layer(*layers).properties(height=320)


def rain_chart(df: pd.DataFrame, now) -> alt.LayerChart:
    """降雨機率長條圖（>= 告警門檻者標紅），df 需含 forecast_time_start、rain_probability。"""
    data = pd.DataFrame({"時段": _naive(df["forecast_time_start"]), "降雨機率 (%)": df["rain_probability"]})
    data = data.dropna()
    bars = (alt.Chart(data).mark_bar(size=16)
            .encode(x=alt.X("時段:T", title=None, axis=X_AXIS),
                    y=alt.Y("降雨機率 (%):Q", scale=alt.Scale(domain=[0, 100])),
                    color=alt.condition(alt.datum["降雨機率 (%)"] >= RAIN_ALERT,
                                        alt.value("#e03131"), alt.value("#4dabf7")),
                    tooltip=[alt.Tooltip("時段:T", format="%m/%d %H:%M"), "降雨機率 (%):Q"]))
    threshold = (alt.Chart(pd.DataFrame({"y": [RAIN_ALERT]}))
                 .mark_rule(strokeDash=[6, 4], color="#e03131", opacity=0.6).encode(y="y:Q"))
    layers = [bars, threshold]
    rule = _now_rule(data["時段"], now)
    if rule is not None:
        layers.append(rule)
    return alt.layer(*layers).properties(height=320)


def series_chart(data: pd.DataFrame, now, y_title: str, order: list[str],
                 zero: bool = False, threshold: float | None = None) -> alt.LayerChart:
    """多系列折線圖。data 需含 forecast_time_start (tz-aware)、系列、值；order 決定顏色與圖例順序。

    threshold 有值時（降雨機率）畫出門檻虛線，並把 >= 門檻的點放大加紅框。
    """
    d = data.dropna(subset=["值"]).copy()
    d["時段"] = _naive(d["forecast_time_start"])
    d = d[["時段", "系列", "值"]]
    select = alt.selection_point(fields=["系列"], bind="legend")
    color = alt.Color("系列:N", scale=alt.Scale(domain=order, range=PALETTE[:len(order)]),
                      legend=alt.Legend(title=None, orient="top"))
    x = alt.X("時段:T", title=None, axis=X_AXIS)
    y = alt.Y("值:Q", title=y_title,
              scale=alt.Scale(zero=zero, domain=[0, 100] if threshold is not None else alt.Undefined))
    opacity = alt.condition(select, alt.value(1), alt.value(0.15))
    tooltip = ["系列:N", alt.Tooltip("時段:T", format="%m/%d %H:%M"), alt.Tooltip("值:Q", title=y_title, format=".1f")]
    lines = alt.Chart(d).mark_line(strokeWidth=2.5, strokeJoin="round").encode(x=x, y=y, color=color, opacity=opacity)
    if threshold is None:
        points = alt.Chart(d).mark_point(filled=True, size=45).encode(
            x=x, y=y, color=color, opacity=opacity, tooltip=tooltip)
    else:
        over = alt.datum["值"] >= threshold
        points = alt.Chart(d).mark_point(filled=True).encode(
            x=x, y=y, color=color, opacity=opacity, tooltip=tooltip,
            size=alt.condition(over, alt.value(160), alt.value(45)),
            stroke=alt.condition(over, alt.value("#c92a2a"), alt.value("white")),
            strokeWidth=alt.value(2))
    layers = [lines, points]
    if threshold is not None:
        layers.append(alt.Chart(pd.DataFrame({"y": [threshold]}))
                      .mark_rule(strokeDash=[6, 4], color="#c92a2a", opacity=0.6).encode(y="y:Q"))
    rule = _now_rule(d["時段"], now) if not d.empty else None
    if rule is not None:
        layers.append(rule)
    return alt.layer(*layers).add_params(select).properties(height=320)
