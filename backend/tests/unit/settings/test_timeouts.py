import importlib

import pytest

from app.settings.config import Settings
from app.settings.job_queue import HEARTBEAT_INTERVAL_SECONDS, ORPHAN_THRESHOLD_SECONDS
from app.settings.timeouts import (
    ATTEMPT_MAX_SECONDS,
    LLM_MAX_RETRY,
    LLM_MAX_WAIT_SECONDS,
    MAX_RUNTIME_SECONDS,
    STT_MAX_WAIT_SECONDS,
)

_MISSED_BEATS_BEFORE_ORPHAN = 3


def _production_attempt_max() -> int:
    """本番の既定値で 1 試行の最悪秒数を組み立てる.

    テスト環境は conftest が LLM_TIMEOUT_SECONDS を短く上書きするので, 既定値から計算し直す.

    Returns:
        int: 本番既定での 1 試行の最悪秒数.
    """
    default_llm_timeout = Settings.model_fields["LLM_TIMEOUT_SECONDS"].default
    return STT_MAX_WAIT_SECONDS + default_llm_timeout * (1 + LLM_MAX_RETRY)


def test_runtime_budget_allows_one_full_attempt_in_production() -> None:
    """本番の既定値でも合計上限が 1 試行の最悪を上回ることを確認するテスト.

    下回ると, LLM の内部リトライで復帰しかけている正常なジョブを途中で殺す.
    STT の窓を伸ばしたのに上限を据え置いた場合にここで落ちる.
    """
    assert _production_attempt_max() < MAX_RUNTIME_SECONDS


def test_attempt_max_is_the_sum_of_its_parts() -> None:
    """1 試行の最悪が STT と LLM の直列合計であることを確認するテスト."""
    assert ATTEMPT_MAX_SECONDS == STT_MAX_WAIT_SECONDS + LLM_MAX_WAIT_SECONDS


def test_broken_budget_fails_at_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """上限が 1 試行を下回る組み合わせが起動時に弾かれることを確認するテスト.

    LLM_TIMEOUT_SECONDS は env で変えられるので, テストだけでは本番の破綻を捕まえられない.
    """
    import app.settings.config as config_module  # ruff:ignore[import-outside-top-level]
    import app.settings.timeouts as timeouts_module  # ruff:ignore[import-outside-top-level]

    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", str(MAX_RUNTIME_SECONDS))
    try:
        importlib.reload(config_module)
        with pytest.raises(ValueError, match="must exceed"):
            importlib.reload(timeouts_module)
    finally:  # 他のテストに壊れた状態を持ち越さない
        monkeypatch.undo()
        importlib.reload(config_module)
        importlib.reload(timeouts_module)


def test_orphan_threshold_tolerates_missed_heartbeats() -> None:
    """孤児判定が生存報告の欠測を数回許容することを確認するテスト.

    間隔と閾値が近いと, 一時的な DB 遅延で健全なジョブを孤児と誤判定する.
    """
    assert ORPHAN_THRESHOLD_SECONDS >= HEARTBEAT_INTERVAL_SECONDS * _MISSED_BEATS_BEFORE_ORPHAN
