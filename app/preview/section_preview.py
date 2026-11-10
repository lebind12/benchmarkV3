"""MP-09 저장 결과 → 독자용 투영·관리자 진단 (조회 전용).

이 파일은 **저장된 행만** 읽는다. 외부 모델·API 호출이 없고, 어떤 값을 새로 만들지도
않는다. 독자용 경로와 진단 경로를 따로 만드는 이유는, 독자 응답에 내부 값이 새는 것을
"화면에서 가리는" 방식으로 막지 않기 위해서다. 응답 자체를 분리한다.

투영 규칙:

- 독자용(`build_reader_view`): 본문·근거·예측 표시·기준 시각만. 진단·ID·시도 없음.
- 진단(`build_diagnostics_view`): 공백 사유, 제외된 주장, 선택된 입력 버전, 계약 버전.
- 승인·품질 상태는 관리자 판단 자료이므로 진단 쪽에 둔다.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.preview import presentation
from app.preview.contracts import contract_versions
from app.preview.modules import synthesis as synthesis_module

__all__ = [
    "build_diagnostics_view",
    "build_reader_view",
    "synthesis_result_payload",
]

SYNTHESIS_WORKFLOW_ID = synthesis_module.SECTION_WORKFLOW_ID


def _latest_synthesis_result(detail: Any) -> Mapping[str, Any] | None:
    """실행 상세에서 **최신 S1 결과**를 고른다.

    여러 버전이 있으면 마지막(가장 최근) 행을 쓴다. 이전 버전은 지우지 않고 남아
    있으므로, 비교는 기존 버전 비교 경로로 한다.
    """
    results = [
        row
        for row in (getattr(detail, "results", ()) or ())
        if str(row.get("module_id")) == synthesis_module.MODULE_ID
    ]
    if not results:
        return None
    results.sort(key=lambda row: (int(row.get("version") or 0), str(row.get("created_at"))))
    return results[-1]


def synthesis_result_payload(detail: Any) -> Mapping[str, Any] | None:
    """저장 행에서 S1 payload를 꺼낸다.

    `store.save_module_result`는 `ModuleResult.to_dict()`를 저장하므로 실제 payload가
    `payload` 키 안에 한 겹 더 들어 있다. 두 모양 모두 읽는다.
    """
    row = _latest_synthesis_result(detail)
    if row is None:
        return None
    payload = row.get("payload")
    if not isinstance(payload, Mapping):
        return None
    payload = dict(payload)
    inner = payload.get("payload")
    if isinstance(inner, Mapping) and inner:
        merged = dict(payload)
        merged.update(dict(inner))
        return merged
    return payload


def _synthesis_section(detail: Any) -> Mapping[str, Any] | None:
    sections = [
        row
        for row in (getattr(detail, "section_results", ()) or ())
        if str(row.get("workflow_id")) == SYNTHESIS_WORKFLOW_ID
    ]
    if not sections:
        return None
    sections.sort(
        key=lambda row: (int(row.get("version") or 0), str(row.get("created_at")))
    )
    return sections[-1]


def build_reader_view(session, detail: Any) -> dict[str, Any] | None:
    """독자용 응답. 결과가 없거나 본문이 없으면 `None`(빈 프리뷰를 만들지 않는다)."""
    payload = synthesis_result_payload(detail)
    section = _synthesis_section(detail)
    if payload is None and section is None:
        return None

    reader: dict[str, Any] | None = None
    if payload is not None:
        reader = synthesis_module.preview_payload_from_result(payload)

    if not reader:
        # S1 결과가 실패로 남았거나 저장 투영이 없으면, 저장된 섹션 본문도 확인한다.
        body = str((section or {}).get("body") or "").strip()
        if not body:
            return None
        reader = {
            "headline": str((section or {}).get("title") or ""),
            "body": body,
            "sources": [
                {
                    key: value
                    for key, value in dict(source).items()
                    if key in {"label", "kind", "url", "note", "observed_at"}
                }
                for source in (section or {}).get("sources") or ()
                if isinstance(source, Mapping)
            ],
            "generated_at": (section or {}).get("created_at"),
            "data_as_of": None,
        }

    body = str(reader.get("body") or "").strip()
    if not body:
        return None
    # 실행 방식·실행 ID·워크플로우 ID는 **독자용 응답에 넣지 않는다**. 관리자 화면은
    # 진단 경로(`/preview/diagnostics`)에서 같은 실행의 그 값을 함께 본다.
    return reader


def build_diagnostics_view(session, detail: Any) -> dict[str, Any]:
    """관리자 진단. 독자용 응답과 **다른 경로**로 낸다."""
    payload = synthesis_result_payload(detail) or {}
    validated = payload.get("validated") or {}
    section = _synthesis_section(detail)
    selected_inputs = _selected_inputs(detail, validated)

    gaps = list(validated.get("gaps") or ())
    excluded = [
        {
            "claim_id": claim.get("claim_id"),
            "kind": claim.get("kind"),
            "text": claim.get("text"),
            "reason": claim.get("decision_reason"),
        }
        for module in validated.get("modules") or ()
        for claim in module.get("excluded") or ()
        if isinstance(claim, Mapping)
    ]

    return {
        "run_id": str(detail.summary.run_id),
        "workflow_id": SYNTHESIS_WORKFLOW_ID,
        "workflow_version": (section or {}).get("workflow_version"),
        "section_result_id": (section or {}).get("section_result_id"),
        "mode": {
            "mode": (
                detail.summary.mode.value
                if hasattr(detail.summary.mode, "value")
                else str(detail.summary.mode)
            ),
            "label": presentation.mode_label(detail.summary.mode),
        },
        "quality": {
            "run": detail.summary.quality.value
            if hasattr(detail.summary.quality, "value")
            else str(detail.summary.quality),
            "section": (section or {}).get("quality"),
        },
        "gaps": gaps,
        "excluded_claims": excluded,
        "diagnostics": list(payload.get("diagnostics") or ())
        + list((section or {}).get("diagnostics") or ()),
        "unavailable_reason": payload.get("unavailable_reason"),
        "selected_inputs": selected_inputs,
        "contract_versions": dict(contract_versions()),
        "synthesis_versions": {
            "implementation": synthesis_module.IMPLEMENTATION_VERSION,
            "prompt": synthesis_module.PROMPT_VERSION,
            "output_contract": synthesis_module.OUTPUT_CONTRACT_VERSION,
        },
        "attempts_present": bool(payload.get("attempt_summary")),
    }


def _selected_inputs(detail: Any, validated: Mapping[str, Any]) -> list[dict[str, Any]]:
    """선택된 입력 버전 목록. **실제로 전달된 결과**와 버전을 그대로 보여준다."""
    rows: list[dict[str, Any]] = []
    for module in validated.get("modules") or ():
        if not isinstance(module, Mapping):
            continue
        rows.append(
            {
                "module_id": module.get("module_id"),
                "result_id": module.get("result_id"),
                "version": module.get("version"),
                "implementation_version": module.get("implementation_version"),
                "prompt_version": module.get("prompt_version"),
                "quality": module.get("quality"),
                "adopted_claim_count": len(module.get("adopted") or ()),
                "excluded_claim_count": len(module.get("excluded") or ()),
            }
        )
    return rows
