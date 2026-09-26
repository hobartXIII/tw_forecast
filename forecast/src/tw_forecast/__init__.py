"""台灣天氣預報系統。

- ``tw_forecast.backend``：排程流程（抓取氣象署預報 → 清洗 → 寫入 Supabase → 告警推播），由 GitHub Actions 執行。
- ``tw_forecast.config``：後端使用的常數（儀表板在 forecast/web/，以 TypeScript 撰寫）。
"""
