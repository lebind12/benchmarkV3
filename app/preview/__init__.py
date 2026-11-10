"""경기 프리뷰 실행 기록·검사 공통 계층 (MP-02).

이 패키지는 조사 모듈이 아니라 공통 계약·저장·검사·등록부를 담는다. 실제
조사 모듈(D0/R1/R2/R3/S1)은 MP-03~MP-09가 `contracts.py`와 `registry.py`를
사용해 붙인다.
"""

from __future__ import annotations

from app.preview.contracts import (
    CONTRACT_VERSION,
    INSPECTOR_VERSION,
    MODULE_INPUT_VERSION,
    PREVIEW_DOCUMENT_VERSION,
    PROVIDER_CONTRACT_VERSION,
    contract_versions,
)

__all__ = [
    "CONTRACT_VERSION",
    "INSPECTOR_VERSION",
    "MODULE_INPUT_VERSION",
    "PREVIEW_DOCUMENT_VERSION",
    "PROVIDER_CONTRACT_VERSION",
    "contract_versions",
]
