"""「立即更新」：呼叫 GitHub API 觸發後端 workflow（workflow_dispatch）。

輸入：repo（owner/name）與具 Actions 寫入權限的 token。輸出：(是否成功, 失敗訊息)。
"""
import requests

WORKFLOW_FILE = "weather_worker.yml"


class WorkflowDispatcher:
    """觸發 weather_worker.yml 在 main 分支執行一次。"""

    def __init__(self, repo: str | None, token: str | None, post=requests.post):
        """post 可注入，測試時不連網。"""
        self._repo = repo
        self._token = token
        self._post = post

    def trigger(self) -> tuple[bool, str]:
        """成功回傳 (True, "")；官方文件現列 HTTP 200、實測為 204，兩者都算成功。失敗回傳 (False, 原因)。"""
        if not self._repo or not self._token:
            return False, "尚未設定 GH_REPO / GH_DISPATCH_TOKEN"
        try:
            resp = self._post(
                f"https://api.github.com/repos/{self._repo}/actions/workflows/{WORKFLOW_FILE}/dispatches",
                headers={"Authorization": f"Bearer {self._token}", "Accept": "application/vnd.github+json"},
                json={"ref": "main"}, timeout=15)
        except requests.RequestException as exc:
            return False, f"無法連線至 GitHub：{exc}"
        if resp.status_code in (200, 204):
            return True, ""
        return False, f"觸發失敗（HTTP {resp.status_code}）：{resp.text[:200]}"
