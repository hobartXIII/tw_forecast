"""Streamlit 儀表板：資料存取、篩選範圍、圖表、地圖、告警設定與各區塊畫面。

分層（由下而上，上層可用下層，反之不行）：
- 純邏輯（不需要 Streamlit，可直接單元測試）：regions、formatting、temperature、update_gate、scope、tables、
  repository、github_dispatch、admin、charts、map_view
- Streamlit 相關：session、style、admin_ui、views/
- 入口：streamlit_app/app.py（只負責串接各區塊）
"""
