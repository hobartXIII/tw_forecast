"""整頁煙霧測試：用 Streamlit 的 AppTest 真的執行 streamlit_app/app.py，資料庫換成假的、時間固定。

驗證整條前端流程（讀資料 → 篩選 → 摘要／地圖／分頁）不會出錯，並抽查關鍵畫面內容。
"""
import json
from datetime import datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from fakes import FakeClient, forecast_rows
from tw_forecast.frontend import repository, session
from tw_forecast.frontend.repository import TZ
from tw_forecast.frontend.update_gate import DispatchLog

APP = Path(__file__).resolve().parents[2] / "streamlit_app" / "app.py"
NOW = datetime(2026, 9, 21, 10, 0, tzinfo=TZ)
STATUS = [{"trigger_type": "schedule", "last_success_at": "2026-09-21T09:30:00+08:00", "last_run_at": None},
          {"trigger_type": "manual", "last_success_at": "2026-09-21T08:00:00+08:00", "last_run_at": None}]


@pytest.fixture
def app(monkeypatch):
    """固定時間、假資料庫、假 secrets；地圖元件不需要真的渲染。"""
    client = FakeClient({"weather_forecasts": forecast_rows(datetime(2026, 9, 20, 6, 0, tzinfo=TZ), days=4),
                         "pipeline_status": STATUS})
    monkeypatch.setattr(repository, "now_taipei", lambda: NOW)
    monkeypatch.setattr(session, "now_taipei", lambda: NOW)
    monkeypatch.setattr(session, "get_client", lambda: client)
    monkeypatch.setattr(session, "is_configured", lambda: True)
    monkeypatch.setattr(session, "secret", lambda name: None)
    monkeypatch.setattr(session, "dispatch_log", lambda log=DispatchLog(): log)  # 每個測試各自一份，不共用快取
    import streamlit_folium
    monkeypatch.setattr(streamlit_folium, "st_folium", lambda *a, **k: {})
    return AppTest.from_file(str(APP), default_timeout=120).run()


def spec_text(chart) -> str:
    """圖表規格轉成可搜尋的文字（規格裡的中文是跳脫編碼，需先解析）。"""
    return json.dumps(json.loads(chart.proto.spec), ensure_ascii=False)


def select(at, label, value):
    next(s for s in at.selectbox if s.label == label).select(value).run()


def test_default_page_renders_without_errors(app):
    assert not app.exception
    assert app.title[0].value == "🌤️ 台灣天氣預報"
    assert [t.label for t in app.tabs] == ["📈 氣溫趨勢", "🌧️ 降雨機率", "📋 目前時段明細", "🕒 後續時段", "📅 日期查詢"]
    cards = [m.value for m in app.markdown if 'class="glass"' in m.value]
    assert len(cards) == 4 and "平均氣溫" in cards[0]
    assert len(app.dataframe) == 2  # 目前時段明細（22 縣市）與後續時段


def test_update_status_caption_and_allowed_button(app):
    captions = [c.value for c in app.caption]
    assert any("最近排程更新 09/21 09:30" in c and "最近手動更新 09/21 08:00" in c for c in captions)
    update = next(b for b in app.button if b.label == "🔄 立即更新")
    assert not update.disabled  # 距上次更新已超過 20 分鐘


def test_single_city_shows_combined_temperature_chart_and_no_metric_radio(app):
    select(app, "縣市", "臺中市")
    assert not app.exception
    assert [t.label for t in app.tabs] == ["📈 氣溫趨勢", "🌧️ 降雨機率", "📋 一週預報", "📅 日期查詢"]
    assert not app.radio  # 單一縣市不需要指標單選鈕
    charts = app.get("vega_lite_chart")
    assert len(charts) == 2 and all(name in spec_text(charts[0]) for name in ("最高溫", "平均溫", "最低溫"))


def test_region_and_city_filters_are_mutually_exclusive(app):
    select(app, "縣市", "臺中市")
    select(app, "地區", "離島地區")
    assert next(s for s in app.selectbox if s.label == "縣市").value == "全部縣市"
    select(app, "縣市", "臺北市")
    assert next(s for s in app.selectbox if s.label == "地區").value == "全部地區"


def test_metric_radio_switches_region_chart(app):
    select(app, "地區", "北部地區")
    app.radio[0].set_value("最低溫").run()
    assert not app.exception and "最低溫 (°C)" in spec_text(app.get("vega_lite_chart")[0])


def test_date_query_lists_days_and_renders_table(app):
    select(app, "縣市", "臺中市")
    picker = next(s for s in app.selectbox if s.label.startswith("日期"))
    assert len(picker.options) == 4
    picker.select(picker.options[1]).run()
    assert not app.exception and len(app.dataframe) == 2  # 一週預報 + 該日表格


def test_stale_data_shows_warning(app, monkeypatch):
    monkeypatch.setattr(session, "now_taipei", lambda: datetime(2026, 12, 1, 10, 0, tzinfo=TZ))
    monkeypatch.setattr(repository, "now_taipei", lambda: datetime(2026, 12, 1, 10, 0, tzinfo=TZ))
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception and any("目前沒有涵蓋此刻的預報時段" in w.value for w in at.warning)


def test_unconfigured_app_asks_for_secrets(monkeypatch):
    monkeypatch.setattr(session, "is_configured", lambda: False)
    monkeypatch.setattr(session, "secret", lambda name: None)
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert any("尚未設定 SUPABASE_URL" in e.value for e in at.error)
    assert next(b for b in at.button if b.label == "⚙️ 告警設定").disabled


def test_empty_database_shows_warning(monkeypatch):
    monkeypatch.setattr(session, "now_taipei", lambda: NOW)
    monkeypatch.setattr(repository, "now_taipei", lambda: NOW)
    monkeypatch.setattr(session, "get_client", lambda: FakeClient({"weather_forecasts": [], "pipeline_status": STATUS}))
    monkeypatch.setattr(session, "is_configured", lambda: True)
    monkeypatch.setattr(session, "secret", lambda name: None)
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert any("資料庫目前沒有預報資料" in w.value for w in at.warning)


def test_refresh_after_dispatch_keeps_update_button_disabled(app, monkeypatch):
    """按下「立即更新」→ F5（全新連線）後，資料庫還沒更新，按鈕仍要維持停用。"""
    from tw_forecast.frontend import github_dispatch
    monkeypatch.setattr(github_dispatch.WorkflowDispatcher, "trigger", lambda self: (True, ""))
    monkeypatch.setattr(session, "secret", lambda name: "x")
    next(b for b in app.button if b.label == "🔄 立即更新").click().run()
    assert not app.exception
    assert next(b for b in app.button if b.label == "⏳ 更新中…").disabled  # 同一連線：倒數中

    fresh = AppTest.from_file(str(APP), default_timeout=120).run()  # 模擬 F5：全新的連線
    button = next(b for b in fresh.button if b.label == "🔄 立即更新")
    assert button.disabled
    assert any("已觸發更新" in i.value for i in fresh.info)
