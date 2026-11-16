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
from app.preview import store as store_module
from app.preview.contracts import contract_versions
from app.preview.modules import synthesis as synthesis_module
from app.preview.section_structured import StructuredIdContext, team_logo_url

__all__ = [
    "build_bundle_reader_view",
    "build_diagnostics_view",
    "build_reader_view",
    "build_selected_inputs_view",
    "composition_section_blocks",
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


# 독자 화면에 내보이는 섹션 순서. 값을 만들지 않고 저장된 행 순서만 고정한다.
_READER_SECTION_ORDER: tuple[str, ...] = (
    "section_players",
    "section_availability",
    "section_outlook",
    "section_odds",
    "section_ai_forecast",
)

# 필수 섹션. 이 본문이 없으면 정상 완료로 표시하지 않는다(선택 섹션은 생략 가능).
_REQUIRED_READER_SECTIONS: tuple[str, ...] = ("section_players", "section_ai_forecast")

# 섹션 제목 폴백. 저장된 제목이 있으면 그것을 쓴다(여기 값으로 덮지 않는다).
_SECTION_TITLES: dict[str, str] = {
    "section_players": "주목 선수",
    "section_availability": "부상·결장",
    "section_outlook": "외부 매체 전망",
    "section_odds": "배당",
    "section_ai_forecast": "AI 경기 전망",
}


def _ordered_rows(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """저장된 섹션 행을 표시 순서로 정렬한다(같은 섹션이면 최신 버전)."""
    def key(row: Mapping[str, Any]) -> tuple[int, int, str]:
        workflow = str(row.get("workflow_id") or "")
        order = _READER_SECTION_ORDER.index(workflow) if workflow in _READER_SECTION_ORDER else 99
        return (order, -int(row.get("version") or 0), str(row.get("created_at") or ""))

    return sorted((row for row in rows if isinstance(row, Mapping)), key=key)


def _uuid_or_none(value: Any):
    """문자열 ID를 UUID로. 형식이 아니면 `None`(예외를 화면까지 올리지 않는다)."""
    import uuid as _uuid

    try:
        return _uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _row_view(row: Any) -> dict[str, Any] | None:
    """다른 실행의 섹션 결과 행을 이 실행의 행과 **같은 모양**으로 읽는다.

    저장된 값만 옮기며 새로 만들지 않는다. 본문이 없으면 `None`이다.
    """
    if row is None:
        return None
    body = str(getattr(row, "body", "") or "")
    if not body.strip():
        return None
    created = getattr(row, "created_at", None)
    return {
        "section_result_id": str(getattr(row, "id", "")),
        "run_id": str(getattr(row, "run_id", "")),
        "workflow_id": getattr(row, "workflow_id", None),
        "workflow_version": getattr(row, "workflow_version", None),
        "version": getattr(row, "version", None),
        "title": getattr(row, "title", None),
        "body": body,
        "sources": list(getattr(row, "sources", []) or []),
        "quality": getattr(row, "quality", None),
        "output_contract_version": getattr(row, "output_contract_version", None),
        "unavailable_reason": getattr(row, "unavailable_reason", None),
        "mode": getattr(row, "mode", None),
        "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
    }


def _reader_sources_of(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """독자용 출처 줄. 허용 키만 남기고 내부 값은 버린다."""
    allowed = {"label", "kind", "url", "note", "observed_at"}
    rows: list[dict[str, Any]] = []
    for source in row.get("sources") or ():
        if not isinstance(source, Mapping):
            continue
        cleaned = {key: value for key, value in dict(source).items() if key in allowed}
        if cleaned.get("label") or cleaned.get("url"):
            rows.append(cleaned)
    return rows


def _select_rows(
    rows: Sequence[Mapping[str, Any]],
    selected_result_ids: Sequence[str] = (),
) -> list[Mapping[str, Any]]:
    """섹션당 **한 행만** 고른다.

    - 관리자가 고른 결과 ID가 있으면 그 ID 행만 쓴다(선택이 기준이다). 같은 섹션에
      선택이 두 번 들어오면 첫 항목만 쓴다(UI가 섹션별 1개를 보장한다).
    - 선택 ID가 없는 섹션은 **최신 버전 1개**만 쓴다. 같은 섹션 v1·v2가 저장되어 있어도
      독자 본문에 둘을 함께 싣지 않는다(사용자 선택 의미 위반, SF-02 §4-a).
    """
    by_id = {
        str(row.get("section_result_id")): row
        for row in rows
        if isinstance(row, Mapping) and row.get("section_result_id")
    }
    chosen: dict[str, Mapping[str, Any]] = {}
    used_ids: set[str] = set()
    for raw_id in selected_result_ids:
        result_id = str(raw_id)
        row = by_id.get(result_id)
        if row is None or result_id in used_ids:
            continue
        workflow = str(row.get("workflow_id") or "")
        if not workflow or workflow in chosen:
            continue
        used_ids.add(result_id)
        chosen[workflow] = row
    # 선택되지 않은 섹션은 최신 버전 1개만 채운다. 선택을 덮어쓰지 않는다.
    for row in _ordered_rows(rows):
        workflow = str(row.get("workflow_id") or "")
        if not workflow or workflow in chosen:
            continue
        chosen[workflow] = row
    return _ordered_rows(list(chosen.values()))


def composition_section_blocks(
    rows: Sequence[Mapping[str, Any]],
    *,
    selected_result_ids: Sequence[str] = (),
) -> tuple[list[dict[str, Any]], list[str]]:
    """저장 섹션 행 → 독자 표시 블록. **본문이 있는 행만** 넣고 사유는 따로 돌려준다.

    - 섹션당 한 버전만 쓴다(`_select_rows`). 선택 ID가 있으면 그 버전이 기준이다.
    - 선택 섹션(부상·매체·배당)은 자료가 없으면 독자 화면에서 생략하고 사유를 남긴다.
    - 필수 섹션은 본문이 없거나 `ready`가 아니면 그 사실을 사유로 돌려준다(성공 위장 금지).
    - 진단 문구·내부 ID·수집 실패 설명은 블록 본문에 넣지 않는다.
    """
    blocks: list[dict[str, Any]] = []
    problems: list[str] = []
    for row in _select_rows(rows, selected_result_ids):
        workflow = str(row.get("workflow_id") or "")
        body = str(row.get("body") or "").strip()
        unavailable = row.get("unavailable_reason")
        if not body:
            if workflow in _REQUIRED_READER_SECTIONS:
                problems.append(
                    f"{workflow}: 본문이 없어 필수 섹션을 표시하지 못했습니다."
                    f" 사유: {unavailable or '사유 기록 없음'}"
                )
            continue
        if unavailable:
            # 부분 본문은 보존하지만 '정상 완료'는 아니다. 필수 섹션이면 문제로 남긴다.
            if workflow in _REQUIRED_READER_SECTIONS:
                problems.append(f"{workflow}: 부분 결과입니다. 사유: {unavailable}")
        blocks.append(
            {
                "section_id": workflow,
                "title": str(row.get("title") or _SECTION_TITLES.get(workflow) or workflow),
                "body": body,
                "sources": _reader_sources_of(row),
                "quality": row.get("quality"),
                "partial": bool(unavailable),
                # 관리자 진단이 버전을 따라갈 수 있게 남긴다(독자 본문에는 넣지 않는다).
                "version": row.get("version"),
                "workflow_version": row.get("workflow_version"),
                "output_contract_version": row.get("output_contract_version"),
                "created_at": row.get("created_at"),
            }
        )
    return blocks, problems


def build_bundle_reader_view(
    session, detail: Any, *, names=None
) -> dict[str, Any] | None:
    """새 정보 원문 묶음 경로의 **구성본**을 독자용 응답으로 투영한다.

    기존 S1 reader 경로가 이 묶음 결과를 읽지 않아, 새 경로로 만든 본문이 독자 화면에
    나타나지 않던 문제를 해결한다. 저장된 섹션 행만 읽고 값을 만들지 않는다.

    - 완성 본문과 출처를 **먼저** 돌려준다. 검색/본문/DB 수집 실패 진단은 여기 넣지
      않고 진단 경로(`build_diagnostics_view`)에 남긴다.
    - 필수 섹션 본문이 없으면 `complete=False`와 사유를 남긴다(정상 완료 위장 금지).
    """
    rows = [
        row
        for row in (getattr(detail, "section_results", ()) or ())
        if str(row.get("workflow_id")) in _READER_SECTION_ORDER
    ]
    if not rows:
        return None
    # 관리자가 저장한 구성본이 있으면 **그 선택 ID가 기준**이다. 구성본이 없을 때만
    # 섹션별 최신 1개를 쓴다. 선택되지 않은 버전을 독자 본문에 섞지 않는다.
    selected_ids: list[str] = []
    run_id = getattr(getattr(detail, "summary", None), "run_id", None)
    if run_id is not None:
        try:
            record = store_module.load_composition(session, run_id)
        except Exception:  # noqa: BLE001 - 구성본 조회 실패로 프리뷰를 없애지 않는다
            record = {"available": False}
        if record.get("available"):
            composition = record.get("composition") or {}
            selected_ids = [
                str(item["result_id"])
                for item in composition.get("items") or ()
                if isinstance(item, Mapping) and item.get("result_id")
            ]
    # 구성본 항목이 **다른 실행**의 결과를 가리킬 수 있다(예: 마지막 AI만 재실행한 run은
    # 앞 섹션 본문을 부모 실행에서 선택해 쓴다). 이 실행의 행에 없는 선택 ID는 그 결과가
    # 저장된 실행에서 읽어 후보로 더한다. 선택되지 않은 다른 버전은 더하지 않는다.
    if selected_ids:
        known = {
            str(row.get("section_result_id"))
            for row in rows
            if isinstance(row, Mapping)
        }
        for result_id in selected_ids:
            if result_id in known:
                continue
            try:
                picked_row = store_module.get_section_result_any_run(
                    session, _uuid_or_none(result_id)
                )
            except Exception:  # noqa: BLE001 - 못 읽으면 그 항목만 빠진다
                picked_row = None
            if picked_row is None:
                continue
            if str(getattr(picked_row, "workflow_id", "")) not in _READER_SECTION_ORDER:
                continue
            extra = _row_view(picked_row)
            if extra is not None:
                rows.append(extra)
                known.add(result_id)
    from app.preview import player_section_read

    checked_rows: list[Mapping[str, Any]] = []
    mismatch_problems: list[str] = []
    for row in rows:
        if session is not None and player_section_read.section_expects_canonical_storage(row):
            canonical = player_section_read.read_canonical_player_section(session, row)
            if canonical.storage_mismatch:
                mismatch_msg = str(canonical.storage_error or "정본 저장 행 누락")
                mismatch_problems.append(mismatch_msg)
                checked_rows.append(
                    {
                        **dict(row),
                        "body": "",
                        "unavailable_reason": mismatch_msg,
                    }
                )
                continue
        checked_rows.append(row)

    blocks, problems = composition_section_blocks(checked_rows, selected_result_ids=selected_ids)
    for err in mismatch_problems:
        if err not in problems:
            problems.append(err)
    if not blocks:
        return None
    fixture = getattr(detail, "fixture", None)
    label = getattr(getattr(detail, "summary", None), "fixture_label", None)
    fixture_payload = (
        fixture.to_dict() if fixture is not None and hasattr(fixture, "to_dict") else {}
    )
    reader: dict[str, Any] = {
        "fixture": {
            "fixture_id": fixture_payload.get("fixture_id"),
            "home_team_id": fixture_payload.get("home_team_id"),
            "away_team_id": fixture_payload.get("away_team_id"),
            "league_id": fixture_payload.get("league_id"),
            "season": fixture_payload.get("season"),
            "kickoff_at": fixture_payload.get("kickoff_at"),
            "label": label,
            "league": None,
        },
        "headline": blocks[0]["title"],
        "generated_at": (blocks[0].get("created_at") or getattr(getattr(detail, "summary", None), "finished_at", None)),
        "data_as_of": None,
        "sections": blocks,
        "body": "\n\n".join(block["body"] for block in blocks),
        "sources": [
            source for block in blocks for source in block.get("sources") or ()
        ],
        "complete": not problems,
    }
    if problems:
        # 독자 본문에는 사유를 넣지 않는다. 관리자 진단이 같은 값을 읽는다.
        reader["unavailable_reason"] = problems[0]
    if names is not None and getattr(names, "active", False):
        reader = _apply_display_names(reader, names=names)
    return reader


def build_selected_inputs_view(session, run_id: Any) -> list[dict[str, Any]]:
    """저장된 구성본의 **선택 결과 버전** 목록(관리자 진단)."""
    try:
        record = store_module.load_composition(session, run_id)
    except Exception:  # noqa: BLE001 - 구성본이 없으면 빈 목록이다
        return []
    composition = record.get("composition") or {}
    return [dict(item) for item in composition.get("items") or () if isinstance(item, Mapping)]


def build_reader_view(session, detail: Any, *, names=None) -> dict[str, Any] | None:
    """독자용 응답. 결과가 없거나 본문이 없으면 `None`(빈 프리뷰를 만들지 않는다).

    `names`(`display_names.DisplayNameBridge`)를 주면 **표시 값만** 한국어 표기로
    바꾼다. 저장된 본문·payload는 건드리지 않는다. 변환을 못 하면 원문을 그대로 낸다.
    """
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
    if names is not None and getattr(names, "active", False):
        # 화면에 낼 선수를 먼저 확정한 뒤 본문을 치환한다(모델 표기 등록 순서).
        reader = _apply_display_names(reader, names=names)
    # 실행 방식·실행 ID·워크플로우 ID는 **독자용 응답에 넣지 않는다**. 관리자 화면은
    # 진단 경로(`/preview/diagnostics`)에서 같은 실행의 그 값을 함께 본다.
    return reader


def build_diagnostics_view(session, detail: Any) -> dict[str, Any]:
    """관리자 진단. 독자용 응답과 **다른 경로**로 낸다.

    새 묶음 경로로 만든 섹션이 있으면 그 실행의 **저장 구성본 항목**(선택된 결과 버전과
    그 출처 실행)도 함께 낸다. 검색/본문/DB 수집 실패 사유는 이 경로에만 둔다.
    """
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
        # 새 묶음 경로: 구성본에 실제로 들어간 결과 버전들(없으면 빈 목록).
        "composition_inputs": build_selected_inputs_view(session, detail.summary.run_id)
        if getattr(detail, "summary", None) is not None
        else [],
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


def _apply_display_names(reader: dict[str, Any], *, names) -> dict[str, Any]:
    """독자용 응답의 표시 문자열만 한국어 표기로 바꾼 사본을 만든다.

    저장된 본문·payload는 그대로 두고, 응답 값만 바꾼다. 실패하면 원문을 쓴다.
    """
    localized = dict(reader)
    fixture_block = localized.get("fixture")
    fixture = fixture_block if isinstance(fixture_block, Mapping) else {}
    # 팀 외부 ID·배지 URL을 덧붙인다. 내부 `home_team_id`/`away_team_id`는 **그대로 둔다**
    # (같은 숫자가 다른 실체를 가리키므로 바꾸지 않는다). 확인된 팀만 값을 채우고,
    # 확인되지 않으면 `None`이며 URL을 만들지 않는다.
    if fixture:
        id_context = _structured_id_context(names)
        home_internal = _int_or_none(fixture.get("home_team_id"))
        away_internal = _int_or_none(fixture.get("away_team_id"))
        home_external = (
            id_context.team_external_id(home_internal)
            if id_context is not None and home_internal is not None
            else None
        )
        away_external = (
            id_context.team_external_id(away_internal)
            if id_context is not None and away_internal is not None
            else None
        )
        localized["fixture"] = {
            **dict(fixture),
            "home_team_external_id": home_external,
            "away_team_external_id": away_external,
            "home_team_logo_url": team_logo_url(home_external),
            "away_team_logo_url": team_logo_url(away_external),
        }
        fixture = localized["fixture"]
    players = [
        item for item in (localized.get("players_to_watch") or ()) if isinstance(item, Mapping)
    ]
    scope = [
        int(value)
        for key in ("home_team_id", "away_team_id")
        for value in [_int_or_none(fixture.get(key))]
        if value is not None
    ]
    if players and scope:
        converted = names.localize_players(players, scope_team_ids=scope)
        if converted:
            localized["players_to_watch"] = converted
    from app.preview import player_section_read

    # 구성본 섹션 블록의 본문·제목에도 **같은 표시 이름 규칙**을 적용한다.
    # 단, 새 계약 NS-01/02 선수/부상 섹션 본문은 생성 시점 한글 표기를 정본으로
    # 유지하며 후속 이름 치환으로 재작성하지 않는다.
    sections = localized.get("sections")
    has_preserved_player_section = False
    if isinstance(sections, list) and sections:
        rewritten_sections: list[Any] = []
        for item in sections:
            if not isinstance(item, Mapping):
                rewritten_sections.append(item)
                continue
            preserve_body = (
                str(item.get("section_id") or "") in {"section_players", "section_availability"}
                and player_section_read.is_new_player_section_contract(
                    item.get("output_contract_version")
                )
            )
            if preserve_body:
                has_preserved_player_section = True
            rewritten_sections.append(
                {
                    **dict(item),
                    **(
                        {
                            "body": (
                                str(item.get("body") or "")
                                if preserve_body
                                else names.rewrite_body(str(item.get("body") or ""))
                            )
                        }
                        if item.get("body")
                        else {}
                    ),
                    **(
                        {"title": names.rewrite_body(str(item.get("title") or ""))}
                        if item.get("title")
                        else {}
                    ),
                }
            )
        localized["sections"] = rewritten_sections

    text = str(localized.get("body") or "")
    if text:
        if has_preserved_player_section and isinstance(localized.get("sections"), list):
            localized["body"] = "\n\n".join(
                str(item.get("body") or "")
                for item in localized["sections"]
                if isinstance(item, Mapping) and item.get("body")
            )
        else:
            localized["body"] = names.rewrite_body(text)
    headline = localized.get("headline")
    if isinstance(headline, str) and headline:
        localized["headline"] = names.rewrite_body(headline)
    return localized


def _structured_id_context(names) -> StructuredIdContext | None:
    """표시 이름 파사드에서 **이미 열린** 해석기를 꺼내 외부 ID 확인 경계를 만든다.

    새 연결·새 쿼리를 만들지 않는다. 파사드가 없으면 `None`이고, 그때는 외부 ID와
    사진·배지 URL이 모두 `None`이다(추정하지 않는다).
    """
    resolver = getattr(names, "names", None)
    if resolver is None:
        return None
    try:
        return StructuredIdContext(resolver)
    except Exception:  # noqa: BLE001 - 확인 경계 생성 실패로 응답을 깨지 않는다
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
