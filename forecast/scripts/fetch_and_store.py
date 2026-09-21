"""流程一入口（GitHub Actions 執行 `python scripts/fetch_and_store.py`）。

實際邏輯都在 src/tw_forecast/backend/；這裡只負責把 src/ 加入匯入路徑後呼叫 cli.main()。
參數說明見 tw_forecast/backend/cli.py。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tw_forecast.backend.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
