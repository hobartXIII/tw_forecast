"""氣溫折線圖（最高/最低氣溫，一週趨勢）。"""
import altair as alt
import pandas as pd

LABELS = {"max_temp": "最高氣溫", "min_temp": "最低氣溫"}
COLORS = {"最高氣溫": "#d9480f", "最低氣溫": "#1971c2"}


def temp_trend_chart(df: pd.DataFrame) -> alt.Chart:
    """df 需含 forecast_time_start (Asia/Taipei tz-aware)、min_temp、max_temp。"""
    data = df[["forecast_time_start", "min_temp", "max_temp"]].copy()
    # 去掉時區保留台灣當地時間，避免瀏覽器再依本機時區換算
    data["時段"] = data["forecast_time_start"].dt.tz_localize(None)
    long = data.melt(id_vars="時段", value_vars=list(LABELS), var_name="項目", value_name="氣溫 (°C)")
    long["項目"] = long["項目"].map(LABELS)
    return (alt.Chart(long).mark_line(point=True)
            .encode(x=alt.X("時段:T", title=None, axis=alt.Axis(format="%m/%d %H:%M")),
                    y=alt.Y("氣溫 (°C):Q", scale=alt.Scale(zero=False)),
                    color=alt.Color("項目:N", scale=alt.Scale(domain=list(COLORS), range=list(COLORS.values())),
                                    legend=alt.Legend(title=None, orient="top")),
                    tooltip=["時段:T", "項目:N", "氣溫 (°C):Q"])
            .properties(height=320))
