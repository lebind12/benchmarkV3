"""관리자 검사 화면용 조회 모델.

이 모듈은 저장된 기록을 화면이 바로 그릴 수 있는 모양으로 바꾸기만 한다. 외부
제공자를 부르지 않고, 계산으로 없는 값을 만들지 않는다.

검사 탭은 설계 §6의 다섯 항목 중 MP-02가 기록할 수 있는 네 가지다.

1. 요청 (request): RequestSpec과 비밀값 제거 요청 원문
2. 응답 (response): 실제 수신 원문, 상태·오류·사용량·소요 시간
3. 변환 (transform): 정규화 결과, 채택·제외·충돌·누락, 검증 상태
4. 다음 입력 (next_input): 어느 결과 버전이 다음 호출에 전달됐는지와 실제 값

프리뷰 반영은 S1·V1이 생기는 MP-09 이후에 붙는다. MP-02에서 빈 탭을 만들지
않고 왜 없는지 표시한다.

모듈별 전용 패널이 없어도 네 탭은 항상 같은 모양으로 보인다. 새 모듈은
registry에 등록만 하면 이 공통 검사 경로를 그대로 쓴다.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.preview.contracts import INSPECTOR_VERSION, RunMode
from app.preview.registry import MOCK_DEMO_MODULE_ID, describe_registry, get_module

__all__ = [
    "INSPECTOR_TABS",
    "build_module_inspection",
    "build_run_inspection",
    "describe_mode",
]

INSPECTOR_TABS: tuple[dict[str, str], ...] = (
    {
        "id": "request",
        "label": "요청",
        "description": "제공자·모델·프롬프트 버전과 실제 전송 값(비밀값 제거)",
    },
    {
        "id": "response",
        "label": "원문 응답",
        "description": "실제 수신 본문, 상태 코드, 오류 분류, 제공된 사용량",
    },
    {
        "id": "transform",
        "label": "정규화 변환",
        "description": "원문에서 뽑아낸 근거, 채택·제외·충돌 사유, 자료 확보 상태",
    },
    {
        "id": "next_input",
        "label": "다음 입력",
        "description": "다음 단계에 전달한 결과 버전과 실제 전달 값",
    },
)

MODE_LABELS = {
    RunMode.LIVE.value: "실호출 (live)",
    RunMode.REPLAY.value: "저장 응답 재생 (replay)",
    RunMode.MOCK.value: "모의 실행 (mock, 외부 호출 없음)",
}

MODE_NOTES = {
    RunMode.LIVE.value: "외부 제공자에 실제 요청을 보낸 실행입니다.",
    RunMode.REPLAY.value: "저장된 응답을 다시 처리한 실행입니다. 새 호출이 없습니다.",
    RunMode.MOCK.value: (
        "외부 모델·API를 호출하지 않은 시연 실행입니다. "
        "이 기록을 실제 AI 호출 성공으로 인용하지 않습니다."
    ),
}


def describe_mode(mode: str) -> dict[str, str]:
    return {
        "mode": mode,
        "label": MODE_LABELS.get(mode, mode),
        "note": MODE_NOTES.get(mode, "실행 방식을 알 수 없습니다."),
    }


def _artifact_by_id(artifacts: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(artifact.get("artifact_id")): artifact for artifact in artifacts}


def _panel_for(module_id: str) -> dict[str, Any]:
    try:
        registration = get_module(module_id)
    except KeyError:
        return {
            "panel": "generic",
            "registered": False,
            "display_name": module_id,
            "display_name_note": "등록되지 않은 모듈입니다. 공통 패널로 표시합니다.",
            "mode_scope": [],
            "available": False,
            "unrunnable_reason": "이 모듈은 등록부에 없습니다.",
        }
    return {
        "panel": registration.inspector_panel,
        "registered": True,
        "display_name": registration.display_name,
        "description": registration.description,
        "mode_scope": [mode.value for mode in registration.mode_scope],
        "available": registration.implemented,
        "unrunnable_reason": registration.unrunnable_reason,
        "expected_model_calls": registration.expected_model_calls,
        "prompt_version": registration.prompt_version,
        "contract_version": registration.contract_version,
    }


def _attempt_tab_entry(
    attempt: Mapping[str, Any], artifacts: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    request_artifact = artifacts.get(str(attempt.get("request_artifact_id")))
    response_artifact = artifacts.get(str(attempt.get("response_artifact_id")))
    return {
        "attempt_id": attempt["attempt_id"],
        "logical_call_id": attempt["logical_call_id"],
        "attempt_ordinal": attempt["attempt_ordinal"],
        "provider": attempt["provider"],
        "model": attempt["model"],
        "mode": attempt["mode"],
        "outcome": attempt["outcome"],
        "http_status": attempt["http_status"],
        "error_class": attempt["error_class"],
        "error_message": attempt["error_message"],
        "usage": attempt["usage"],
        "wait_ms": attempt["wait_ms"],
        "started_at": attempt["started_at"],
        "finished_at": attempt["finished_at"],
        "request_spec": attempt["request_spec"],
        "request_body": request_artifact,
        "response_body": response_artifact,
    }


def _claim_rows(result_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return list(result_payload.get("claims") or [])


def _transform_tab(
    module: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    latest = module.get("latest_result") or {}
    payload = latest.get("payload") or {}
    transform_artifacts = [
        artifact
        for artifact in artifacts.values()
        if artifact.get("kind") == "normalized_transform"
    ]
    return {
        "available": bool(latest),
        "result_id": latest.get("result_id"),
        "version": latest.get("version"),
        "status": latest.get("status"),
        "quality": latest.get("quality"),
        "failure_code": latest.get("failure_code"),
        "claims": _claim_rows(payload),
        "coverage": list(payload.get("coverage") or []),
        "diagnostics": list(payload.get("diagnostics") or []),
        "contract_version": latest.get("contract_version"),
        "prompt_version": latest.get("prompt_version"),
        "implementation_version": latest.get("implementation_version"),
        "input_hash": latest.get("input_hash"),
        "artifacts": transform_artifacts,
        "note": None
        if latest
        else "아직 이 모듈 실행에 저장된 결과가 없습니다. 변환 결과를 만들지 않았습니다.",
    }


def _next_input_tab(module: Mapping[str, Any]) -> dict[str, Any]:
    delivered = module.get("delivered_next_input") or {}
    latest = module.get("latest_result") or {}
    selected = list(delivered.get("selected_result_ids") or [])
    latest_id = latest.get("result_id")
    return {
        "available": bool(delivered),
        "target_module_id": delivered.get("target_module_id"),
        "selected_result_ids": selected,
        "uses_latest_version": bool(latest_id) and latest_id in selected,
        "latest_result_id": latest_id,
        "latest_result_version": latest.get("version"),
        "values": list(delivered.get("values") or []),
        "note": None
        if delivered
        else (
            "이 모듈은 마지막 단계라 다음 입력이 없습니다. "
            "후속 모듈이 붙으면 전달한 값이 여기에 남습니다."
        ),
    }


def build_module_inspection(
    module: Mapping[str, Any],
    artifacts: Sequence[Mapping[str, Any]],
    *,
    run_mode: str,
) -> dict[str, Any]:
    """모듈 실행 하나를 공통 검사 탭 구조로 만든다.

    등록된 모듈이면 전용 패널 이름을 함께 알려준다. 등록되지 않은 모듈도 같은
    네 탭으로 표시하며, 등록부에 없다는 사실을 숨기지 않는다.
    """
    artifact_map = _artifact_by_id(artifacts)
    attempts = list(module.get("attempts") or [])
    latest = module.get("latest_result") or {}

    return {
        "inspector_version": INSPECTOR_VERSION,
        "module_execution_id": module["module_execution_id"],
        "module_id": module["module_id"],
        "panel": _panel_for(module["module_id"]),
        "run_mode": describe_mode(run_mode),
        "status": module["status"],
        "quality": module["quality"],
        "attempt_count": module["attempt_count"],
        "retry_count": module["retry_count"],
        "result_versions": list(module.get("result_versions") or []),
        "started_at": module.get("started_at"),
        "finished_at": module.get("finished_at"),
        "tabs": {
            "request": {
                "available": bool(attempts),
                "input": module.get("input"),
                "attempts": [_attempt_tab_entry(a, artifact_map) for a in attempts],
                "note": None if attempts else "이 모듈 실행에는 아직 시도 기록이 없습니다.",
            },
            "response": {
                "available": any(
                    a.get("response_artifact_id") or a.get("error_class") for a in attempts
                ),
                "attempts": [
                    {
                        "attempt_id": a["attempt_id"],
                        "logical_call_id": a["logical_call_id"],
                        "attempt_ordinal": a["attempt_ordinal"],
                        "outcome": a["outcome"],
                        "http_status": a["http_status"],
                        "error_class": a["error_class"],
                        "error_message": a["error_message"],
                        "usage": a["usage"],
                        "content": artifact_map.get(str(a.get("response_artifact_id"))),
                    }
                    for a in attempts
                ],
                "note": None if attempts else "수신한 원문이 아직 없습니다.",
            },
            "transform": _transform_tab(module, artifact_map),
            "next_input": _next_input_tab(module),
        },
        "tabs_meta": list(INSPECTOR_TABS),
    }


def build_run_inspection(run_detail: Mapping[str, Any]) -> dict[str, Any]:
    """실행 상세를 검사 화면 구조로 만든다. 모듈 목록은 등록부 기준으로 보강한다."""
    run_mode = str((run_detail.get("summary") or {}).get("mode", RunMode.MOCK.value))
    modules = [
        build_module_inspection(module, run_detail.get("artifacts") or (), run_mode=run_mode)
        for module in run_detail.get("modules") or ()
    ]
    registry = describe_registry()
    return {
        **run_detail,
        "inspector_version": INSPECTOR_VERSION,
        "mode_detail": describe_mode(run_mode),
        "inspector_modules": modules,
        "registry": registry,
        "mock_demo_module_id": MOCK_DEMO_MODULE_ID,
        "availability_note": (
            "D0·R1·R2·R3·S1은 아직 구현되지 않아 실행할 수 없습니다. "
            "MP-02가 제공하는 것은 기록 시연(모의) 실행과 그 검사 경로입니다."
        ),
    }
