"""R4 주목 선수 선정 — 좁은 범위의 JSON 출력 계약.

이 파일은 **R4 결과의 모양만** 정한다. 프롬프트 전문·조사 로직·표시 변환은 여기에
없다(`players.py`, `prompts/players.md`, `panels/PlayersPanel.vue`가 각각 소유).

사용자 확정(2026-11-11): 주목 선수 각 항목은 **두 개의 독자 표시 필드**를 가진다.

- `selected_player`: 선정 선수. **DB의 한국어 이름** 문자열(없으면 원래 표기 + 미해결 표시).
- `selection_reason`: 선정 이유. 짧은 한국어 설명.

두 값을 한 문장 필드로 합치지 않는다. 선수/팀 ID, 근거, 출처, 매핑 상태는 내부
메타데이터이며 표시 필드가 아니다. 표시 이름을 모델 음차로 만들지 않고, 같은 인물은
같은 DB 한국어 값을 쓴다.

정직성 규칙:

- 스키마는 **문서·검증용**이다. 이 스키마를 제공자에 강제(response_schema)하지 않는다.
  R4는 기존과 같은 정상 호출 1회 + Google grounding 경로를 그대로 쓴다.
- 모르는 값은 `None`으로 둔다. 빈 문자열이나 추측값으로 채우지 않는다.
"""

from __future__ import annotations

from typing import Any, Mapping

__all__ = [
    "DISPLAY_FIELDS",
    "DISPLAY_LABELS",
    "INTERNAL_FIELDS",
    "MAX_SELECTED_PLAYERS",
    "MODEL_OUTPUT_SCHEMA",
    "MODULE_PAYLOAD_SCHEMA",
    "NAME_SOURCES",
    "OUTPUT_CONTRACT_VERSION",
    "SELECTION_RULE_NOTE",
    "display_fields",
    "contract_summary",
]

# R4 출력 계약 버전. 두 표시 필드 분리·DB 한글명 규칙이 들어간 첫 버전이다.
OUTPUT_CONTRACT_VERSION = "mp05p-r4-players-output-1"

# 한 경기에서 고를 수 있는 최대 인원. R1의 기존 상한(3명)과 같은 값이며,
# 품질 평가 기준이 아니라 출력 길이 계약이다.
MAX_SELECTED_PLAYERS = 3

SELECTED_PLAYER_FIELD = "selected_player"
SELECTION_REASON_FIELD = "selection_reason"

# UI 라벨(사용자 확정 표기). 화면은 이 두 라벨로 이름과 이유를 따로 보여준다.
DISPLAY_LABELS: Mapping[str, str] = {
    SELECTED_PLAYER_FIELD: "선정 선수",
    SELECTION_REASON_FIELD: "선정 이유",
}
DISPLAY_FIELDS: tuple[str, ...] = (SELECTED_PLAYER_FIELD, SELECTION_REASON_FIELD)

# 표시 필드가 아닌 내부 메타데이터. 진단·매핑·근거 추적에만 쓴다.
INTERNAL_FIELDS: tuple[str, ...] = (
    "team",
    "team_id",
    "player_id",
    "external_id",
    "id_space",
    "name_source",
    "mapping_status",
    "mapping_reason",
    "mapping_detail",
    "model_selected_player",
    "evidence",
    "superlative_basis",
    "source_url",
    "claim_id",
)

# 이름 출처 구분. `original`은 DB 한국어 값을 찾지 못해 원래 표기를 유지한 상태다.
NAME_SOURCES: tuple[str, ...] = ("db_korean", "db_short_korean", "original")

# 선정 자체는 AI 판단이라는 경계를 결과에 함께 남긴다(설계 §5 사용자 확정).
SELECTION_RULE_NOTE = (
    "선정 자체는 AI 판단입니다. 같은 선수를 고른 외부 보도를 요구하지 않으며,"
    " 선정 이유에 들어간 수치·부상 같은 사실 전제만 제공된 API/검색 근거와 대조합니다."
)


def display_fields(item: Mapping[str, Any]) -> tuple[str, str]:
    """항목에서 두 표시 필드만 꺼낸다. 합치지 않고 순서대로 돌려준다."""
    player = item.get(SELECTED_PLAYER_FIELD)
    reason = item.get(SELECTION_REASON_FIELD)
    return (
        str(player) if isinstance(player, str) else "",
        str(reason) if isinstance(reason, str) else "",
    )


# --------------------------------------------------------------------------
# 모델이 돌려주는 JSON (요청 1회의 응답 모양)
# --------------------------------------------------------------------------

# `selected_player`는 모델이 **입력 자료에 적힌 표기 그대로** 옮겨 적는 값이다.
# 입력에 로스터(DB 이름·ID)가 있으면 그 표기를, 없으면 API 자료에 나온 표기를 쓴다.
# 한국어 음차 표기를 모델이 만들지 않는다. 최종 표시 이름은 모듈이 DB에서 확인해
# 같은 필드에 다시 채운다.
MODEL_OUTPUT_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "required": ["players"],
    "additionalProperties": False,
    "properties": {
        "players": {
            "type": "array",
            "maxItems": MAX_SELECTED_PLAYERS,
            "items": {
                "type": "object",
                "required": ["selected_player", "team", "selection_reason"],
                "additionalProperties": False,
                "properties": {
                    "selected_player": {
                        "type": "string",
                        "description": "입력 자료에 적힌 선수 표기를 그대로 옮긴 문자열",
                    },
                    "team": {"type": "string"},
                    "player_ref": {
                        "type": ["string", "null"],
                        "description": "입력 로스터의 player_id 문자열. 로스터가 없으면 null",
                    },
                    "selection_reason": {
                        "type": "string",
                        "description": "한국어 1~2문장. 수치·사건 전제는 evidence와 연결",
                    },
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "사실 전제에 쓴 API 사실 id 또는 검색 URL. 판단만이면 빈 배열",
                    },
                    "superlative_basis": {
                        "type": ["string", "null"],
                        "description": (
                            "'압도적'·'최고' 같은 단정 표현을 썼을 때 그 근거. 없으면 null"
                        ),
                    },
                },
            },
        },
        "search_note": {"type": ["string", "null"]},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
    },
}


# --------------------------------------------------------------------------
# 모듈이 저장하는 payload (ModuleResult.payload 안의 값)
# --------------------------------------------------------------------------

_PLAYER_ITEM_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "required": [SELECTED_PLAYER_FIELD, SELECTION_REASON_FIELD],
    "additionalProperties": True,
    "properties": {
        SELECTED_PLAYER_FIELD: {
            "type": "string",
            "description": "선정 선수. DB 한국어 이름. DB 값이 없으면 원래 표기 + mapping_status",
        },
        SELECTION_REASON_FIELD: {
            "type": "string",
            "description": "선정 이유. 짧은 한국어 설명. 이름과 합치지 않는다.",
        },
        "team": {"type": ["string", "null"]},
        "team_id": {"type": ["integer", "null"]},
        "player_id": {"type": ["integer", "null"]},
        "external_id": {"type": ["integer", "null"]},
        "id_space": {"type": "string", "enum": ["internal", "external"]},
        "name_source": {"type": "string", "enum": list(NAME_SOURCES)},
        "mapping_status": {
            "type": "string",
            "enum": ["resolved", "unresolved", "resolver_not_injected"],
        },
        "mapping_reason": {"type": ["string", "null"]},
        "mapping_detail": {"type": ["string", "null"]},
        "model_selected_player": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "superlative_basis": {"type": ["string", "null"]},
        "source_url": {"type": ["string", "null"]},
        "claim_id": {"type": ["string", "null"]},
    },
}

MODULE_PAYLOAD_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "required": ["module_id", "output_contract_version", "players"],
    "additionalProperties": True,
    "properties": {
        "module_id": {"const": "R4"},
        "output_contract_version": {"const": OUTPUT_CONTRACT_VERSION},
        "implementation_version": {"type": "string"},
        "prompt_version": {"type": "string"},
        "mode": {"type": "string"},
        "display_labels": {"type": "object"},
        "players": {"type": "array", "items": _PLAYER_ITEM_SCHEMA},
        "unmapped": {"type": "array", "items": {"type": "object"}},
        "mapping": {"type": "object"},
        "claims": {"type": "array", "items": {"type": "object"}},
        "coverage": {"type": "array", "items": {"type": "object"}},
        "diagnostics": {"type": "array", "items": {"type": "string"}},
        "search_note": {"type": ["string", "null"]},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "raw_grounding": {"type": "object"},
        "raw_model_text": {"type": ["string", "null"]},
        "selection_rule_note": {"type": "string"},
    },
}


def contract_summary() -> dict[str, Any]:
    """인계용 요약. 이 값이 모듈·UI·공유 등록 담당의 기준이다."""
    return {
        "output_contract_version": OUTPUT_CONTRACT_VERSION,
        "module_id": "R4",
        "display_fields": list(DISPLAY_FIELDS),
        "display_labels": dict(DISPLAY_LABELS),
        "internal_fields": list(INTERNAL_FIELDS),
        "max_selected_players": MAX_SELECTED_PLAYERS,
        "model_output_schema": dict(MODEL_OUTPUT_SCHEMA),
        "module_payload_schema": dict(MODULE_PAYLOAD_SCHEMA),
        "selection_rule_note": SELECTION_RULE_NOTE,
    }
