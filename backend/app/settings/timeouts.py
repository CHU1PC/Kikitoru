from typing import Final

from app.settings.config import settings

# AWS Transcribe のポーリング. 実測 (処理時間 ≒ 46 秒 + 0.1 x 音声長) では 120 分の会議で 10〜12 分
STT_POLL_INTERVAL_SECONDS: Final = 5
STT_MAX_POLLS: Final = 240
STT_MAX_WAIT_SECONDS: Final = STT_POLL_INTERVAL_SECONDS * STT_MAX_POLLS

# 元のリクエストを含む試行回数 (HttpRetryOptions.attempts の意味). fallback 側にのみ効かせる
LLM_MAX_RETRY: Final = 3
# 主モデル 1 回 + fallback の LLM_MAX_RETRY 回. 例外なら fallback するので直列に足す
LLM_MAX_WAIT_SECONDS: Final = settings.LLM_TIMEOUT_SECONDS * (1 + LLM_MAX_RETRY)

# STT が窓ギリギリで成功し, その後 LLM が全滅する場合が 1 試行の最悪
ATTEMPT_MAX_SECONDS: Final = STT_MAX_WAIT_SECONDS + LLM_MAX_WAIT_SECONDS
