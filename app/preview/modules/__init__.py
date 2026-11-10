"""프리뷰 섹션 모듈 묶음.

모듈은 `app/preview/modules/` 아래 파일 하나씩 두고, 공통 실행·기록 계약
(`ModuleInput`/`ModuleResult`/`ExecutionContext`)만 쓴다. 모델 호출은
`app.preview.provider.request_model` 하나만 통과한다.

지금 구현된 모듈은 R1(`form`)·R2(`availability`)·R3(`outlook`)다. S1은 아직 구현되지
않았고 등록부에서도 `implemented=False`로 남는다. 이 파일은 그 사실을 숨기지 않는다.
"""

from __future__ import annotations

__all__ = ["backed_modules", "module_versions"]

# 실제 조사 구현이 있는 모듈. 등록부(`registry.py`)의 implemented 값과 어긋나면
# `tests/preview/test_form_module.py`가 실패한다.
# 값은 (구현 버전, 프롬프트 버전)이며, 각 모듈 파일이 자기 값을 소유한다.
_IMPLEMENTED = {
    "R1": ("mp05-form-1", "mp05-form-prompt-1"),
    "R2": ("mp06-r2-1", "mp06-r2-prompt-1"),
    "R3": ("mp07-r3-1", "r3-outlook-1"),
}


def backed_modules() -> tuple[str, ...]:
    """실제 구현이 등록된 모듈 ID. 계획된 모듈을 실행 가능으로 꾸미지 않는다."""
    return tuple(sorted(_IMPLEMENTED))


def module_versions(module_id: str) -> tuple[str, str]:
    """(구현 버전, 프롬프트 버전). 미구현 모듈이면 예외."""
    try:
        return _IMPLEMENTED[module_id]
    except KeyError:
        raise KeyError(f"module {module_id!r} has no implemented research code") from None
