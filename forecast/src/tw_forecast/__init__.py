"""台灣天氣預報系統。

- ``tw_forecast.backend``：排程流程（抓取氣象署預報 → 清洗 → 寫入 Supabase → 告警推播），由 GitHub Actions 執行。
- ``tw_forecast.frontend``：Streamlit 儀表板用的資料存取、圖表、地圖與告警設定。
- ``tw_forecast.config``：前後端共用的常數。
"""
