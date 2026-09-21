"""機密遮蔽。"""
import os

from tw_forecast.config import SECRET_ENV_VARS


def mask_secrets(text: str) -> str:
    """輸入：任意文字。輸出：把環境變數中的機密值（長度 >= 8）換成 ***。

    失敗訊息會寫進 pipeline_status（前端可讀），不可含任何金鑰。
    """
    for name in SECRET_ENV_VARS:
        value = os.getenv(name)
        if value and len(value) >= 8:
            text = text.replace(value, "***")
    return text
