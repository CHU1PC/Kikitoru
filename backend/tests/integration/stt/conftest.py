import os

import pytest
import torch


@pytest.fixture(scope="module", autouse=True)  # noqa: RUF076 - GPU と HF_TOKEN の両方がない場合は、モジュール全体のテストをスキップする
def require_gpu_and_token() -> None:
    """GPU と HF_TOKEN の両方がない場合は、モジュール全体のテストをスキップする fixture."""
    if not torch.cuda.is_available():
        pytest.skip("integration test requires a CUDA GPU")
    if not os.environ.get("HF_TOKEN"):
        pytest.skip("integration test requires a real HF_TOKEN (set it in the project .env)")
