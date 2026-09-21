"""後端流程的例外類型。"""


class AbortRun(Exception):
    """流程必須中止（缺金鑰、API 超過用量等），訊息可直接顯示與寫入 pipeline_status（不含機密）。"""


class NotifyError(RuntimeError):
    """推播失敗；訊息保證不含 token 或網址。"""
