from typing import Final

from app.settings.config import settings
from app.settings.timeouts import MAX_RUNTIME_SECONDS

# DB から参照されない S3 オブジェクトの回収. 掃除ループを回す間隔
ORPHAN_MEDIA_INTERVAL_SECONDS: Final = 24 * 60 * 60
# 削除対象にする最低年齢. 参照が commit されるまでの窓は数秒だが, 時計ずれの保険で大きく取る
ORPHAN_MEDIA_MIN_AGE_SECONDS: Final = 24 * 60 * 60

# 参照が部分的にしか無い DB (リストア直後, 接続先違い) を弾く中止条件.
# 割合だけだと少数のとき誤検知し, 件数だけだと大規模で効かないので両方を満たしたら中止する
ORPHAN_MEDIA_ABORT_RATIO: Final = 0.5
# 正常時の孤児は異常終了した分だけなので, 1 周期で二桁に達したら DB 側を疑う
ORPHAN_MEDIA_ABORT_MIN_COUNT: Final = settings.ORPHAN_MEDIA_ABORT_MIN_COUNT

# 実行中のジョブは行が残っているので年齢ガードとは無関係だが, 逆転していたら設定が壊れている
if ORPHAN_MEDIA_MIN_AGE_SECONDS < MAX_RUNTIME_SECONDS:
    _msg = (
        f"ORPHAN_MEDIA_MIN_AGE_SECONDS ({ORPHAN_MEDIA_MIN_AGE_SECONDS}s) must not be shorter "
        f"than MAX_RUNTIME_SECONDS ({MAX_RUNTIME_SECONDS}s)"
    )
    raise ValueError(_msg)
