from typing import Final

# 初回 1 回 + retry 3 回. 取得のたびに attempts を加算し, これに達した失敗で failed に確定する
MAX_ATTEMPTS: Final = 4
# 失敗時の backoff は LINEAR_WAIT_SECONDS x attempts (60 / 120 / 180 秒)
LINEAR_WAIT_SECONDS: Final = 60

# キューへの問い合わせ間隔. frontend 自身が 3 秒間隔で見ているので, これ以上詰めても画面は変わらない
POLL_INTERVAL_SECONDS: Final = 2
RECLAIM_INTERVAL_SECONDS: Final = 60
PURGE_INTERVAL_SECONDS: Final = 60 * 60

HEARTBEAT_INTERVAL_SECONDS: Final = 60
# 生存報告が途絶えたら孤児とみなす閾値. 1 回の欠測で誤判定しないよう 10 回分の余裕を取る
ORPHAN_THRESHOLD_SECONDS: Final = HEARTBEAT_INTERVAL_SECONDS * 10

# completed の音声は summaries が参照するので消えない. failed は行が唯一の参照なので長めに残す
COMPLETED_RETENTION_DAYS: Final = 7
FAILED_RETENTION_DAYS: Final = 30

# 停止要求から in-flight を手放すまでの猶予. compose の stop_grace_period はこれより長くする
SHUTDOWN_GRACE_SECONDS: Final = 20
