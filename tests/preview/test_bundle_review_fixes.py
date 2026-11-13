"""PS-06 독립 검토 F1·F2·F3·F4·R2 수정의 대표 기록 검사.

이 파일이 확인하는 것(검토 보고서 §8의 확인 요청 범위만):

- **F1**: 실제 D0 스냅샷 모양(`standings=[{team_id, text}]`,
  `injuries=[{player_name: None, team_id, expected_status}]`)에서 순위 문장과 부상 상태가
  **작성 요청 본문에 그대로** 들어간다. 전달한 사실 수와 "전달했습니다" 문장이 일치한다.
- **F2**: 선수 통계 행의 `display_name_ko`(또는 주입된 이름 해석기)와 실제 기록 값이
  '주목 선수' 프롬프트의 후보 목록에 들어간다(55행을 읽고도 "후보 없음"이 되지 않는다).
- **F3**: 저장 payload의 `structured.forecast{lean,score,reasoning}`이 화면 구조 값으로
  그대로 투영된다.
- **F4**: 예상 스코어가 없는 전망은 `insufficient`로 내려가고, 부분 본문은 보존하며,
  스코어를 만들지 않는다.

실제 모델·외부 HTTP·DB는 부르지 않는다. `provider.RecordedTransport`(mode=live)는
**네트워크를 열지 않는 기록 transport**이며(`uses_network=False`), 그 사실을 여기 밝힌다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.preview import information_bundle as bundle_contract
from app.preview import provider
from app.preview.contracts import (
    Environment,
    ExecutionContext,
    ExecutionLimits,
    OperationKind,
    QualityStatus,
    RunMode,
)
from app.preview.localized_names import DisplayNames, LocalizedNameIndex, PlayerNameRow, TeamNameRow
from app.preview.modules import bundle_sections
from app.preview.retry import RunBudget, plan_limits
from app.preview.section_structured import (
    structured_from_payload,
    structured_row_from_section_result,
)

FIXED_NOW = datetime(2026, 11, 11, 6, 0, tzinfo=timezone.utc)
FIXTURE = {
    "fixture_id": 1557474,
    "league_id": 39,
    "season": 2026,
    "home_team_id": 13,
    "away_team_id": 4,
    "kickoff_at": "2026-11-21T12:30:00+00:00",
}
HOME_KO = "맨체스터 시티"
AWAY_KO = "풀럼"

# D0이 실제로 `text`에 담는 순위 문장(`sections._standings_facts`가 만드는 모양).
HOME_STANDING_TEXT = (
    f"{HOME_KO}는 10경기 7승 0무 3패, 승점 21, 리그 3위입니다."
    " 최근 5경기 폼은 LLLWW입니다."
)
AWAY_STANDING_TEXT = f"{AWAY_KO}는 10경기 3승 2무 5패, 승점 11, 리그 15위입니다."


def _bundle(
    *,
    with_web: bool = True,
    standings: tuple[dict, ...] | None = None,
    injuries: tuple[dict, ...] | None = None,
    roster: tuple[dict, ...] = (),
) -> bundle_contract.InformationBundle:
    sources: tuple[bundle_contract.BundleSource, ...] = ()
    if with_web:
        sources = (
            bundle_contract.BundleSource(
                source_id="src:stats",
                discovery_group=bundle_contract.DISCOVERY_GROUP_PLAYERS_INJURY,
                requested_url="https://example.test/stats",
                final_url="https://example.test/stats",
                nature="stats",
                method="fresh_http",
                title="시즌 기록",
                captured_at=FIXED_NOW,
                body_chars=60,
                passages=(
                    bundle_contract.Passage(
                        passage_id="src:stats#p1",
                        source_id="src:stats",
                        ordinal=1,
                        text="홈팀의 최근 5경기 성적은 3승 1무 1패입니다.",
                    ),
                    bundle_contract.Passage(
                        passage_id="src:stats#p2",
                        source_id="src:stats",
                        ordinal=2,
                        text="원정팀은 원정 5경기에서 1승만 거뒀습니다.",
                    ),
                ),
            ),
        )
    default_standings = (
        {"team_id": 13, "text": HOME_STANDING_TEXT},
        {"team_id": 4, "text": AWAY_STANDING_TEXT},
    )
    default_injuries = (
        # 실제 D0 모양: 이름이 `None`이고 상태 키가 `expected_status`다.
        {
            "player_name": None,
            "team_id": 13,
            "expected_status": "doubtful",
        },
    )
    return bundle_contract.InformationBundle(
        bundle_id="bundle-ps06-fix-test",
        fixture=dict(FIXTURE),
        team_id_space="internal",
        collected_at=FIXED_NOW,
        sources=sources,
        db_snapshot=bundle_contract.DbSnapshot(
            fixture=dict(FIXTURE),
            team_id_space="internal",
            collected_at=FIXED_NOW,
            teams=(
                {"team_id": 13, "name_ko": HOME_KO},
                {"team_id": 4, "name_ko": AWAY_KO},
            ),
            standings=default_standings if standings is None else standings,
            injuries=default_injuries if injuries is None else injuries,
            roster=roster,
            readable=True,
        ),
        mode="live",
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=OperationKind.PREVIEW,
        environment=Environment.DEV,
        mode=RunMode.LIVE,
        actor_id=1,
        config_version="ps06-fix-test",
        limits=ExecutionLimits(
            model_requests=8, api_requests=24, attempts_per_call=3, deadline_seconds=1800
        ),
    )


def _budget() -> RunBudget:
    return RunBudget.for_run(
        plan_limits(model_requests=8, normal_model_calls=8), now=FIXED_NOW
    )


def _recorded(answer: dict) -> provider.RecordedTransport:
    text = json.dumps(answer, ensure_ascii=False)
    transport = provider.RecordedTransport(
        script=[
            provider.TransportResult(
                http_status=200,
                raw_request={"contents": "요청"},
                raw_response={
                    "candidates": [
                        {
                            "content": {"parts": [{"text": text}], "role": "model"},
                            "finishReason": "STOP",
                        }
                    ]
                },
                usage={"input_tokens": 100, "output_tokens": 50},
            )
        ],
        provider="recorded-model",
        mode=RunMode.LIVE,
    )
    # 이 transport는 네트워크를 열지 않는다. 그 사실을 검사에서도 단언한다.
    assert transport.uses_network is False
    assert transport.is_recorded_transport is True
    return transport


def _sent_prompt(transport: provider.RecordedTransport) -> str:
    """그 요청이 실제로 보낸 본문. 모델 호출은 이 transport의 calls에만 남는다."""
    assert len(transport.calls) == 1
    spec = transport.calls[0]
    contents = spec.parameters["contents"]
    return contents[0]["parts"][0]["text"]


def _run(
    section_id: str,
    answer: dict,
    *,
    bundle=None,
    resolver=None,
):
    transport = _recorded(answer)
    draft = bundle_sections.build_bundle_section(
        section_id=section_id,
        bundle=bundle if bundle is not None else _bundle(),
        transport=transport,
        context=_context(),
        budget=_budget(),
        resolver=resolver,
        now=FIXED_NOW,
    )
    return draft, transport


def _stats_rows(count: int = 55) -> tuple[dict, ...]:
    """실제 `PlayerSeasonStat.to_dict()` 모양. 이름 키는 `display_name_ko`다."""
    rows: list[dict] = []
    for index in range(count):
        team_id = 13 if index % 2 == 0 else 4
        rows.append(
            {
                "player_id": 7000 + index,
                "team_id": team_id,
                "league_id": 1,
                "season_year": 2026,
                "position": "FW" if index % 3 == 0 else "MF",
                "appearances": 10 + index % 5,
                "minutes": 800 + index,
                "rating": 7.1,
                "goals": index % 7,
                "assists": index % 3,
                "updated_at": "2026-11-10T00:00:00+00:00",
                "display_name_ko": "엘링 홀란" if index == 0 else None,
            }
        )
    return tuple(rows)


# --------------------------------------------------------------------------
# F1 — 순위 문장·부상 상태가 실제 요청 본문에 들어간다
# --------------------------------------------------------------------------


def test_actual_standings_text_reaches_forecast_request_verbatim():
    """D0이 `text`에 담은 순위 문장이 최종 전망 요청에서 사라지지 않는다."""
    draft, transport = _run(
        bundle_contract.SECTION_AI_FORECAST,
        {
            "forecast": "홈팀이 리그 순위 우위를 바탕으로 주도권을 잡을 것으로 봅니다.",
            "predicted_score": {"home": 2, "away": 1},
            "score_reasoning": ["리그 3위"],
            "forecast_evidence": ["api:standings-13"],
        },
    )
    prompt = _sent_prompt(transport)
    assert HOME_STANDING_TEXT in prompt
    assert AWAY_STANDING_TEXT in prompt
    assert "순위 값 없음" not in prompt
    assert "api:standings-13" in prompt
    # 실제 전달한 사실 id만 인용 목록에 남는다.
    assert "api:standings-13" in draft.structured["forecast_evidence"]

def test_actual_expected_status_reaches_availability_request():
    """`expected_status`가 근거 줄과 인용 목록에 들어가고, 이름을 지어내지 않는다."""
    draft, transport = _run(
        bundle_contract.SECTION_AVAILABILITY,
        {
            "injuries": [
                {
                    "player_name": "이름 미확인",
                    "team_id": 13,
                    "status": "doubtful",
                    "injury": "출전 불확실",
                    "importance": "중원 영향",
                    "evidence": ["src:stats#p1"],
                }
            ]
        },
    )
    prompt = _sent_prompt(transport)
    assert "expected_status=doubtful" in prompt
    assert "api:injury-row1" in prompt
    assert "player_name=None" not in prompt
    # 전달한 사실 수(1건)와 상태 문장이 일치한다.
    assert "부상 사실 1건" in prompt


def test_injury_rows_without_serialized_values_do_not_claim_delivery():
    """값이 없는 부상 행은 '전달했습니다'로 쓰지 않고 전달 0건을 밝힌다."""
    bundle = _bundle(injuries=({"player_name": None, "team_id": 13},))
    _draft, transport = _run(
        bundle_contract.SECTION_AVAILABILITY,
        {
            "injuries": [
                {
                    "player_name": "이름 미확인",
                    "team_id": 13,
                    "status": "unknown",
                    "injury": "확인되지 않음",
                    "importance": "확인되지 않음",
                    "evidence": ["src:stats#p1"],
                }
            ]
        },
        bundle=bundle,
    )
    prompt = _sent_prompt(transport)
    assert "전달했습니다" not in prompt
    assert "전달된 부상 사실은 0건" in prompt


def test_injury_name_uses_trusted_player_id_and_injected_resolver():
    """이름이 `None`이어도 신뢰 ID + 주입된 해석기로 DB 한국어 이름을 쓴다."""
    resolver = DisplayNames(
        LocalizedNameIndex(
            teams=(
                TeamNameRow(team_id=13, external_id=50, english_name="Manchester City", name_ko=HOME_KO),
            ),
            players=(
                PlayerNameRow(
                    player_id=7101,
                    external_id=4001,
                    english_name="Rodri",
                    firstname="Rodrigo",
                    lastname="Hernandez",
                    current_team_id=13,
                    name_ko="로드리",
                ),
            ),
        )
    )
    bundle = _bundle(
        injuries=({"player_name": None, "player_id": 7101, "team_id": 13, "expected_status": "doubtful"},)
    )
    _draft, transport = _run(
        bundle_contract.SECTION_AVAILABILITY,
        {
            "injuries": [
                {
                    "player_name": "로드리",
                    "player_id": 7101,
                    "team_id": 13,
                    "status": "doubtful",
                    "injury": "출전 불확실",
                    "importance": "중원 영향",
                    "evidence": ["api:injury-7101"],
                }
            ]
        },
        bundle=bundle,
        resolver=resolver,
    )
    prompt = _sent_prompt(transport)
    assert "api:injury-7101" in prompt
    assert "로드리" in prompt
    assert "expected_status=doubtful" in prompt


# --------------------------------------------------------------------------
# F2 — 선수 후보(이름·기록)가 프롬프트에 실제로 들어간다
# --------------------------------------------------------------------------


def test_stats_candidates_and_display_name_ko_reach_players_request():
    """55행이 이름·기록 후보로 들어간다('후보 없음' 문장만 나오지 않는다)."""
    bundle = _bundle(roster=_stats_rows())
    _draft, transport = _run(
        bundle_contract.SECTION_PLAYERS,
        {
            "players": [
                {
                    "selected_player": "엘링 홀란",
                    "selection_reason": "리그 3위 팀의 득점 자원",
                    "team": HOME_KO,
                    "player_ref": "7000",
                    "evidence": ["src:stats#p1"],
                }
            ],
            "korean_labels": [],
        },
        bundle=bundle,
    )
    prompt = _sent_prompt(transport)
    assert "제공된 선수 후보 목록이 없습니다" not in prompt
    assert "엘링 홀란" in prompt
    assert "[player_ref=7000]" in prompt
    # 실제 기록 값이 후보 줄에 함께 들어간다(개수만 전달하지 않는다).
    assert "출전=" in prompt
    assert "골=" in prompt


def test_roster_name_falls_back_to_injected_resolver_by_trusted_id():
    """`display_name_ko`가 없어도 주입된 해석기의 DB 이름을 후보에 쓴다."""
    resolver = DisplayNames(
        LocalizedNameIndex(
            teams=(
                TeamNameRow(team_id=13, external_id=50, english_name="Manchester City", name_ko=HOME_KO),
            ),
            players=(
                PlayerNameRow(
                    player_id=7002,
                    external_id=4002,
                    english_name="Rodri",
                    firstname="Rodrigo",
                    lastname="Hernandez",
                    current_team_id=13,
                    name_ko="로드리",
                ),
            ),
        )
    )
    bundle = _bundle(roster=_stats_rows())
    _draft, transport = _run(
        bundle_contract.SECTION_PLAYERS,
        {
            "players": [
                {
                    "selected_player": "로드리",
                    "selection_reason": "중원 장악",
                    "team": HOME_KO,
                    "player_ref": "7002",
                    "evidence": ["src:stats#p1"],
                }
            ],
            "korean_labels": [],
        },
        bundle=bundle,
        resolver=resolver,
    )
    prompt = _sent_prompt(transport)
    assert "로드리" in prompt
    assert "[player_ref=7002]" in prompt


def test_injected_player_candidates_take_precedence_over_bundle_roster():
    """A가 만든 선수 후보(`player_candidates`)를 주면 묶음의 `roster`보다 우선한다."""
    bundle = _bundle(roster=_stats_rows())
    transport = _recorded(
        {
            "players": [
                {
                    "selected_player": "엘링 홀란",
                    "selection_reason": "리그 3위 팀의 득점 자원",
                    "team": HOME_KO,
                    "player_ref": "7000",
                    "evidence": ["src:stats#p1"],
                }
            ],
            "korean_labels": [],
        }
    )
    bundle_sections.build_bundle_section(
        section_id=bundle_contract.SECTION_PLAYERS,
        bundle=bundle,
        transport=transport,
        context=_context(),
        budget=_budget(),
        fixture_names={"home_team": HOME_KO, "away_team": AWAY_KO, "league": "EPL"},
        resolver=None,
        player_candidates=(
            {
                "player_id": 9001,
                "team_id": 13,
                "display_name_ko": "주입된 후보",
                "position": "FW",
                "appearances": 12,
                "goals": 9,
            },
        ),
        now=FIXED_NOW,
    )
    prompt = _sent_prompt(transport)
    assert "주입된 후보" in prompt
    assert "[player_ref=9001]" in prompt
    # 주입 후보를 줬으므로 묶음 roster의 선수는 후보 목록에 없다.
    assert "[player_ref=7000]" not in prompt


# --------------------------------------------------------------------------
# R2 — DB 한국어 우선, 없으면 같은 응답의 한글 표기
# --------------------------------------------------------------------------


def _names_resolver() -> DisplayNames:
    return DisplayNames(
        LocalizedNameIndex(
            teams=(
                TeamNameRow(team_id=13, external_id=50, english_name="Manchester City", name_ko=HOME_KO),
                TeamNameRow(team_id=4, external_id=36, english_name="Fulham", name_ko=AWAY_KO),
            ),
            players=(
                PlayerNameRow(
                    player_id=7101,
                    external_id=4001,
                    english_name="Erling Haaland",
                    firstname="Erling",
                    lastname="Haaland",
                    current_team_id=13,
                    name_ko="엘링 홀란",
                ),
                PlayerNameRow(
                    player_id=7102,
                    external_id=4002,
                    english_name="Phil Foden",
                    firstname="Phil",
                    lastname="Foden",
                    current_team_id=13,
                    name_ko=None,
                ),
            ),
        )
    )


def test_db_korean_wins_and_same_response_label_fills_missing_db_name():
    """DB 한국어가 있으면 그 값이 이기고, DB 값이 없을 때만 같은 응답의 표기를 쓴다."""
    draft, _transport = _run(
        bundle_contract.SECTION_PLAYERS,
        {
            "players": [
                {
                    "selected_player": "Erling Haaland",
                    "selection_reason": "결정력",
                    "team": "Manchester City",
                    "player_ref": "7101",
                    "evidence": ["src:stats#p1"],
                },
                {
                    "selected_player": "Phil Foden",
                    "selection_reason": "창의성",
                    "team": "Manchester City",
                    "player_ref": "7102",
                    "evidence": ["src:stats#p1"],
                },
            ],
            "korean_labels": [
                {"original": "Erling Haaland", "korean": "엘링 하알란드", "kind": "player"},
                {"original": "Phil Foden", "korean": "필 포든", "kind": "player"},
            ],
        },
        resolver=_names_resolver(),
    )
    rows = {row["player_id"]: row for row in draft.structured["players"]}
    # DB 한국어 값이 있으면 그 값이 이긴다(같은 응답의 '엘링 하알란드'를 쓰지 않는다).
    assert rows[7101]["selected_player"] == "엘링 홀란"
    # DB에 한국어 값이 없을 때만 같은 응답의 표기를 쓴다.
    assert rows[7102]["selected_player"] == "필 포든"


# --------------------------------------------------------------------------
# F3 — 저장 payload의 structured.forecast가 화면 구조 값으로 투영된다
# --------------------------------------------------------------------------


def test_saved_forecast_structured_projects_score_and_lean():
    """저장 payload의 `structured.forecast`가 `available=true`로 화면에 이어진다."""
    payload = {
        "section_id": bundle_contract.SECTION_AI_FORECAST,
        "structured": {
            "forecast": {
                "lean": "home",
                "score": "2-1",
                "reasoning": ["리그 3위로 상위권", "홈 10경기 7승"],
            },
            "forecast_evidence": ["api:standings-13"],
        },
    }
    structured = structured_from_payload(payload, workflow_id="section_ai_forecast")
    assert structured["forecast"]["score"] == "2-1"
    assert structured["forecast"]["lean"] == "home"
    assert structured["forecast"]["reasoning"] == ["리그 3위로 상위권", "홈 10경기 7승"]
    row = structured_row_from_section_result(
        {"section_result_id": "s-1", "workflow_id": "section_ai_forecast"}, payload=payload
    )
    assert row["available"] is True


def test_draft_structured_forecast_matches_saved_projection():
    """작성 초안의 forecast 값과 저장 payload 투영 값이 같다."""
    draft, _transport = _run(
        bundle_contract.SECTION_AI_FORECAST,
        {
            "forecast": "홈팀 우세가 예상됩니다.",
            "predicted_score": {"home": 2, "away": 0},
            "score_reasoning": ["리그 3위"],
            "forecast_evidence": ["api:standings-13"],
        },
    )
    saved = {"structured": dict(draft.structured)}
    projected = structured_from_payload(saved)
    draft_forecast = dict(draft.structured["forecast"])
    for key in ("lean", "score", "reasoning"):
        assert projected["forecast"][key] == draft_forecast[key], key


# --------------------------------------------------------------------------
# F4 — 스코어 없는 전망은 insufficient, 본문은 부분 보존, 스코어는 만들지 않음
# --------------------------------------------------------------------------


def test_forecast_without_score_is_insufficient_and_keeps_partial_body():
    """스코어가 없으면 `insufficient`·사유가 남고, 전망 문장은 보존하며 스코어를 만들지 않는다."""
    draft, _transport = _run(
        bundle_contract.SECTION_AI_FORECAST,
        {
            "forecast": "양 팀 모두 수비 조직력이 좋아 팽팽한 흐름이 예상됩니다.",
            "predicted_score": None,
            "score_reasoning": [],
            "forecast_evidence": ["api:standings-13"],
        },
    )
    assert draft.quality is QualityStatus.INSUFFICIENT
    assert draft.unavailable_reason
    assert "AI 예상 스코어" not in draft.body
    assert "팽팽한 흐름" in draft.body
    assert draft.structured["forecast"]["score"] is None
    assert draft.structured["forecast"]["lean"] is None


def test_forecast_with_score_stays_ready():
    """스코어가 있으면 기존처럼 `ready`다(과잉 차단 없음)."""
    draft, _transport = _run(
        bundle_contract.SECTION_AI_FORECAST,
        {
            "forecast": "홈팀 우세가 예상됩니다.",
            "predicted_score": {"home": 2, "away": 1},
            "score_reasoning": ["리그 3위"],
            "forecast_evidence": ["api:standings-13"],
        },
    )
    assert draft.quality is QualityStatus.READY
    assert draft.unavailable_reason is None
    assert "2-1" in draft.body


# --------------------------------------------------------------------------
# PF-B — 부상 이름 → 검증된 내부 ID/한국어 표기 연결
# --------------------------------------------------------------------------


def _injury_resolver() -> DisplayNames:
    """이 경기 두 팀 로스터. 부상 이름은 DB에 실제로 있는 표기다."""
    return DisplayNames(
        LocalizedNameIndex(
            teams=(
                TeamNameRow(team_id=13, external_id=50, english_name="Manchester City", name_ko=HOME_KO),
                TeamNameRow(team_id=4, external_id=36, english_name="Fulham", name_ko=AWAY_KO),
            ),
            players=(
                PlayerNameRow(
                    player_id=549,
                    external_id=67971,
                    english_name="M. Guéhi",
                    firstname="Marc",
                    lastname="Guéhi",
                    current_team_id=13,
                    name_ko="마크 게히",
                ),
                PlayerNameRow(
                    player_id=132,
                    external_id=19025,
                    english_name="T. Cairney",
                    firstname="Tom",
                    lastname="Cairney",
                    current_team_id=4,
                    name_ko="톰 케어니",
                ),
            ),
        )
    )


def test_injury_name_only_row_links_to_verified_db_player_id():
    """모델이 `player_id: null`로 낸 부상 행도 이름이 DB에서 확인되면 ID가 붙는다.

    실패하면 화면은 부상 선수의 한국어 이름·사진을 잃고 영어 표기만 남는다(사용자 지적).
    """
    draft, _transport = _run(
        bundle_contract.SECTION_AVAILABILITY,
        {
            "injuries": [
                {
                    "player_name": "Marc Guéhi",
                    "player_id": None,
                    "team_id": 13,
                    "status": "doubtful",
                    "injury": "고관절 부상",
                    "importance": "수비진 영향",
                    "evidence": ["src:stats#p1"],
                }
            ],
            "uncertainties": [],
        },
        resolver=_injury_resolver(),
    )
    row = draft.structured["injuries"][0]
    # 확인된 내부 ID와 DB 한국어 표기를 쓴다(추측·음차 아님).
    assert row["player_id"] == 549, row
    assert row["player_name"] == "마크 게히", row
    assert row["team_id"] == 13, row
    # 본문도 같은 표기를 쓴다.
    assert "마크 게히" in draft.body


def test_injury_name_not_in_db_keeps_name_without_id():
    """DB에서 확인되지 않는 이름은 ID를 만들지 않는다(동명이인·미확인 추측 금지)."""
    draft, _transport = _run(
        bundle_contract.SECTION_AVAILABILITY,
        {
            "injuries": [
                {
                    "player_name": "Unknown Trialist",
                    "player_id": None,
                    "team_id": 13,
                    "status": "doubtful",
                    "injury": "확인 불가",
                    "importance": "영향 미확인",
                    "evidence": ["src:stats#p1"],
                }
            ],
            "uncertainties": [],
        },
        resolver=_injury_resolver(),
    )
    row = draft.structured["injuries"][0]
    assert row["player_id"] is None, row
    assert row["player_name"] == "Unknown Trialist", row


# --------------------------------------------------------------------------
# PF-B — API-Football /odds 보충 읽기(명시 실행 전용, 최대 3행)
# --------------------------------------------------------------------------


class _FakeOddsClient:
    """제공자 클라이언트 대역. 실제 네트워크를 열지 않는다."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict]] = []
        self.closed = False

    def get(self, path: str, **params: object) -> dict:
        self.calls.append((path, dict(params)))
        return self.payload

    def close(self) -> None:
        self.closed = True


def _odds_payload(bookmakers: list[dict], *, fixture_id: int = 1557474) -> dict:
    return {
        "errors": [],
        "results": 1,
        "response": [
            {
                "fixture": {"id": fixture_id},
                "update": "2026-11-12T09:00:00+00:00",
                "bookmakers": bookmakers,
            }
        ],
    }


def _bookmaker(book_id: int, name: str, home: str, draw: str, away: str) -> dict:
    return {
        "id": book_id,
        "name": name,
        "update": "2026-11-12T09:00:00+00:00",
        "bets": [
            {
                "id": 5,
                "name": "Match Winner",
                "values": [
                    {"value": "Home", "odd": home},
                    {"value": "Draw", "odd": draw},
                    {"value": "Away", "odd": away},
                ],
            }
        ],
    }


def test_provider_odds_reads_one_request_and_keeps_three_distinct_bookmakers():
    """`/odds` 한 번으로 서로 다른 북메이커 최대 3행을 실제 값 그대로 읽는다."""
    from app.preview.sources import provider_odds

    client = _FakeOddsClient(
        _odds_payload(
            [
                _bookmaker(8, "Bet365", "1.85", "3.60", "4.20"),
                _bookmaker(11, "Unibet", "1.88", "3.55", "4.10"),
                _bookmaker(16, "William Hill", "1.90", "3.50", "4.05"),
                _bookmaker(19, "Extra Book", "1.95", "3.40", "3.90"),
            ]
        )
    )
    result = provider_odds.read_provider_odds(
        fixture_id=1557474,
        collected_at=datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc),
        client=client,
    )
    # 요청은 **한 번**이다(재시도·반복 호출 없음).
    assert client.calls == [("/odds", {"fixture": 1557474})]
    assert result.sent == 1
    assert result.available is True
    # 최대 3행이며 값은 제공자 원문 그대로다(합성·추정 없음).
    assert len(result.quotes) == 3
    assert [quote.site for quote in result.quotes] == ["Bet365", "Unibet", "William Hill"]
    assert result.quotes[0].home_decimal == 1.85
    assert result.quotes[0].market == bundle_contract.ODDS_MARKET_REGULATION_1X2


def test_provider_odds_without_key_sends_nothing_and_says_why(monkeypatch):
    """키가 없으면 요청을 보내지 않고 사유를 남긴다(값을 만들어 채우지 않는다)."""
    from app.preview.sources import provider_odds

    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    monkeypatch.delenv("PREVIEW_API_FOOTBALL_KEY", raising=False)
    monkeypatch.setattr(provider_odds, "_api_key", lambda: None)
    result = provider_odds.read_provider_odds(
        fixture_id=1557474,
        collected_at=datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc),
    )
    assert result.sent == 0
    assert result.available is False
    assert result.quotes == ()
    assert "키가 설정되지 않아" in (result.reason or "")


def test_odds_section_puts_public_quote_first_then_provider_rows():
    """공개 표 값이 있으면 1행으로 유지하고 제공자 줄은 남는 자리만 채운다."""
    from app.preview.sources import provider_odds

    public = bundle_contract.OddsMarket(
        quotes=(
            bundle_contract.OddsQuote(
                source_id="src:odds",
                site="Pinnacle",
                market=bundle_contract.ODDS_MARKET_REGULATION_1X2,
                observed_at=FIXED_NOW,
                home_decimal=1.80,
                draw_decimal=3.70,
                away_decimal=4.30,
            ),
        ),
        collected_at=FIXED_NOW,
    )
    provider_rows = provider_odds.ProviderOddsResult(
        quotes=(
            bundle_contract.OddsQuote(
                source_id="api-football:odds:1557474:8",
                site="Bet365",
                market=bundle_contract.ODDS_MARKET_REGULATION_1X2,
                observed_at=FIXED_NOW,
                home_decimal=1.85,
                draw_decimal=3.60,
                away_decimal=4.20,
            ),
        ),
        sent=1,
    )
    merged = provider_odds.market_with_provider_quote(
        public, provider_rows, collected_at=FIXED_NOW
    )
    assert [quote.site for quote in merged.quotes] == ["Pinnacle", "Bet365"]
    assert merged.quotes[0].home_decimal == 1.80


def test_odds_section_without_any_real_value_stays_empty():
    """실제 값이 없으면 배당 표를 만들지 않는다(합성 목업값 금지)."""
    transport = _recorded({"odds": []})
    draft = bundle_sections.build_bundle_section(
        section_id=bundle_contract.SECTION_ODDS,
        bundle=_bundle(),
        transport=transport,
        context=_context(),
        budget=_budget(),
        now=FIXED_NOW,
        provider_odds=None,
    )
    assert draft.structured["odds"] == []
    assert draft.quality is QualityStatus.INSUFFICIENT


def test_injury_conflicting_model_player_id_is_dropped_not_guessed():
    """모델이 적은 ID가 이름과 다른 선수를 가리키면 어느 쪽도 고르지 않는다."""
    draft, _transport = _run(
        bundle_contract.SECTION_AVAILABILITY,
        {
            "injuries": [
                {
                    "player_name": "Marc Guéhi",
                    # 533은 이 경기 로스터의 다른 선수(홀란드)다.
                    "player_id": 533,
                    "team_id": 13,
                    "status": "doubtful",
                    "injury": "고관절 부상",
                    "importance": "수비진 영향",
                    "evidence": ["src:stats#p1"],
                }
            ],
            "uncertainties": [],
        },
        resolver=_injury_resolver(),
    )
    row = draft.structured["injuries"][0]
    # 충돌하는 ID를 그대로 두면 다른 선수의 사진이 나온다. 그래서 ID를 비운다.
    assert row["player_id"] is None, row
    assert row["player_name"] == "Marc Guéhi", row


# --------------------------------------------------------------------------
# PF-B 후속 — 남는 자리 조건·1회 제한·파서 예외 경계·버전 축
# --------------------------------------------------------------------------


def _market(*sites: tuple[str, float, float, float]) -> bundle_contract.OddsMarket:
    return bundle_contract.OddsMarket(
        quotes=tuple(
            bundle_contract.OddsQuote(
                source_id=f"src:{site}",
                site=site,
                market=bundle_contract.ODDS_MARKET_REGULATION_1X2,
                observed_at=FIXED_NOW,
                home_decimal=home,
                draw_decimal=draw,
                away_decimal=away,
            )
            for site, home, draw, away in sites
        ),
        collected_at=FIXED_NOW,
    )


def test_remaining_slots_is_true_below_three_adopted_sites():
    """남는 자리 판정은 '0행일 때만'이 아니라 '채택 업체 3개 미만'이다.

    실패하면 공개 표가 1~2행일 때 제공자 보완이 아예 일어나지 않아 배당이 3행에 못 미친다.
    """
    from app.preview.sources import provider_odds

    assert provider_odds.adopted_site_count(None) == 0
    assert provider_odds.has_remaining_slots(None) is True
    assert provider_odds.adopted_site_count(_market(("Pinnacle", 1.8, 3.7, 4.3))) == 1
    assert provider_odds.has_remaining_slots(_market(("Pinnacle", 1.8, 3.7, 4.3))) is True
    two = _market(("Pinnacle", 1.8, 3.7, 4.3), ("Bet365", 1.85, 3.6, 4.2))
    assert provider_odds.adopted_site_count(two) == 2
    assert provider_odds.has_remaining_slots(two) is True
    three = _market(
        ("Pinnacle", 1.8, 3.7, 4.3),
        ("Bet365", 1.85, 3.6, 4.2),
        ("Unibet", 1.88, 3.55, 4.1),
    )
    assert provider_odds.adopted_site_count(three) == 3
    # 꽉 찼으면 제공자 호출을 하지 않는다.
    assert provider_odds.has_remaining_slots(three) is False


def test_public_one_row_plus_provider_two_rows_keeps_site_first_three():
    """공개 1행 + 제공자 2행 => 사이트 우선 3개(공개가 맨 앞)."""
    from app.preview.sources import provider_odds

    result = provider_odds.ProviderOddsResult(
        quotes=(
            bundle_contract.OddsQuote(
                source_id="api-football:odds:1:8",
                site="Bet365",
                market=bundle_contract.ODDS_MARKET_REGULATION_1X2,
                observed_at=FIXED_NOW,
                home_decimal=1.85,
                draw_decimal=3.6,
                away_decimal=4.2,
            ),
            bundle_contract.OddsQuote(
                source_id="api-football:odds:1:11",
                site="Unibet",
                market=bundle_contract.ODDS_MARKET_REGULATION_1X2,
                observed_at=FIXED_NOW,
                home_decimal=1.88,
                draw_decimal=3.55,
                away_decimal=4.1,
            ),
        ),
        sent=1,
    )
    merged = provider_odds.market_with_provider_quote(
        _market(("Pinnacle", 1.8, 3.7, 4.3)), result, collected_at=FIXED_NOW
    )
    assert [quote.site for quote in merged.quotes] == ["Pinnacle", "Bet365", "Unibet"]
    assert merged.quotes[0].home_decimal == 1.8


def test_public_three_rows_means_no_provider_call():
    """공개 3개면 제공자 호출 0 — 남는 자리가 없으므로 읽지 않는다."""
    from app.preview.sources import provider_odds

    market = _market(
        ("Pinnacle", 1.8, 3.7, 4.3),
        ("Bet365", 1.85, 3.6, 4.2),
        ("Unibet", 1.88, 3.55, 4.1),
    )
    assert provider_odds.has_remaining_slots(market) is False
    # 호출자가 조건을 지키면 클라이언트는 한 번도 불리지 않는다.
    client = _FakeOddsClient(_odds_payload([_bookmaker(8, "Bet365", "1.85", "3.60", "4.20")]))
    if provider_odds.has_remaining_slots(market):
        provider_odds.read_provider_odds(
            fixture_id=1557474,
            collected_at=datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc),
            client=client,
        )
    assert client.calls == []


def test_read_once_guard_blocks_the_second_request():
    """같은 실행에서 두 번째 읽기는 요청을 보내지 않는다(호출 최대 1회)."""
    from app.preview.sources import provider_odds

    client = _FakeOddsClient(_odds_payload([_bookmaker(8, "Bet365", "1.85", "3.60", "4.20")]))
    guard = provider_odds.ReadOnceGuard()
    first = provider_odds.read_provider_odds_once(
        fixture_id=1557474,
        collected_at=datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc),
        guard=guard,
        client=client,
    )
    second = provider_odds.read_provider_odds_once(
        fixture_id=1557474,
        collected_at=datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc),
        guard=guard,
        client=client,
    )
    assert len(client.calls) == 1
    assert first.sent == 1
    assert second.sent == 0
    assert second.available is False
    assert "이미 한 번" in (second.reason or "")


def test_wrong_fixture_parse_error_becomes_missing_odds_not_a_crash():
    """제공자가 다른 경기 배당을 주면(WrongFixture) 배당 미제공으로 남고 흐름은 유지된다."""
    from app.preview.sources import provider_odds

    payload = _odds_payload([_bookmaker(8, "Bet365", "1.85", "3.60", "4.20")], fixture_id=999999)
    client = _FakeOddsClient(payload)
    result = provider_odds.read_provider_odds(
        fixture_id=1557474,
        collected_at=datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc),
        client=client,
    )
    assert result.sent == 1
    assert result.available is False
    assert result.quotes == ()
    assert "다른 경기" in (result.reason or "")


def test_malformed_odds_envelope_becomes_missing_odds():
    """봉투 모양 오류(ApiFootballError)도 배당 미제공으로 처리하고 예외를 올리지 않는다."""
    from app.preview.sources import provider_odds

    client = _FakeOddsClient({"errors": [], "response": "not-a-list"})
    result = provider_odds.read_provider_odds(
        fixture_id=1557474,
        collected_at=datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc),
        client=client,
    )
    assert result.sent == 1
    assert result.available is False
    assert "읽지 못했습니다" in (result.reason or "")


def test_odds_workflow_version_changed_and_others_kept(monkeypatch):
    """배당 공급 경로가 승인 축에 들어가 배당 버전만 바뀐다(다른 섹션은 그대로).

    무관한 섹션의 **과거 해시를 고정하지 않는다.** 공통 계약 축을 저장과 같은 값으로
    맞추는 합법적인 변경(번들 계약을 `mp04-section-result-1`로 정렬)까지 실패로 만들면,
    승인 대상이 아닌 변경이 재승인을 요구하는 것처럼 보인다. 그래서 이 검사는 해시 상수가
    아니라 **관계**를 고정한다: 배당 제공자 구현 버전이 배당 승인 버전에 반영되고, 그
    변경이 무관한 availability 버전을 바꾸지 않는다.
    """
    from app.preview import version_manifest
    from app.preview.sources import provider_odds

    odds = version_manifest.workflow_version_of("section_odds")
    assert odds == "section_odds@49923b1c5dcb467a", odds
    by_module = {
        item.module_id: item
        for item in version_manifest.constituents_for_workflow("section_odds")
    }

    assert (
        by_module["compose_body"].implementation_version
        == provider_odds.PROVIDER_ODDS_IMPLEMENTATION_VERSION
    )

    # 관계 확인(임시 대역, 제품 파일 무변경): 제공자 구현 버전이 바뀌면 배당 승인 버전만
    # 바뀌고, 무관한 섹션은 그대로다(불필요한 재승인 금지).
    availability = version_manifest.workflow_version_of("section_availability")
    monkeypatch.setattr(
        provider_odds,
        "PROVIDER_ODDS_IMPLEMENTATION_VERSION",
        provider_odds.PROVIDER_ODDS_IMPLEMENTATION_VERSION + "-probe",
    )
    bumped_odds = version_manifest.workflow_version_of("section_odds")
    bumped_availability = version_manifest.workflow_version_of("section_availability")

    assert bumped_odds != odds, "배당 공급 경로 변경이 배당 승인 버전에 반영되어야 한다"
    assert bumped_availability == availability, (
        "배당 변경만으로 무관한 availability 버전이 바뀌면 불필요한 재승인이 생긴다"
    )


# --------------------------------------------------------------------------
# PF-B 2차 — 한국어 이름만 저장된 부상 행의 결정적 ID 연결
# --------------------------------------------------------------------------


def _korean_injury_resolver() -> DisplayNames:
    """새 run의 실제 저장 이름과 같은 형태(한국어 표기)를 가진 로스터."""
    return DisplayNames(
        LocalizedNameIndex(
            teams=(
                TeamNameRow(team_id=13, external_id=50, english_name="Manchester City", name_ko=HOME_KO),
                TeamNameRow(team_id=4, external_id=36, english_name="Fulham", name_ko=AWAY_KO),
            ),
            players=(
                PlayerNameRow(
                    player_id=549,
                    external_id=67971,
                    english_name="M. Guéhi",
                    firstname="Marc",
                    lastname="Guéhi",
                    current_team_id=13,
                    name_ko="마크 게히",
                ),
                PlayerNameRow(
                    player_id=139,
                    external_id=389315,
                    english_name="Joshua King",
                    firstname="Joshua",
                    lastname="King",
                    current_team_id=4,
                    name_ko="조슈아 킹",
                ),
            ),
        )
    )


def test_korean_only_injury_name_resolves_to_db_player_id():
    """모델이 **처음부터 한국어** 이름만 낸 부상 행도 저장 로스터로 ID가 연결된다.

    새 run(d96fe824)의 실제 저장 모양: `player_name`이 '마크 게히'/'조슈아 킹'이고
    `player_id`는 null. 영어 표기 규칙만 보면 not_found가 되어 사진이 비었다.
    실패하면 사용자가 보는 부상 카드에서 사진이 다시 사라진다.
    """
    from app.preview.section_structured import StructuredIdContext, structured_from_payload

    payload = {
        "payload": {
            "structured": {
                "injuries": [
                    {
                        "player_name": "마크 게히",
                        "player_id": None,
                        "team": "Manchester City",
                        "team_id": 13,
                        "status": "doubtful",
                        "summary": "고관절 부상",
                    },
                    {
                        "player_name": "조슈아 킹",
                        "player_id": None,
                        "team": "Fulham",
                        "team_id": 4,
                        "status": "doubtful",
                        "summary": "서혜부 부상",
                    },
                ]
            }
        }
    }
    ctx = StructuredIdContext(_korean_injury_resolver(), scope_team_ids=(13, 4))
    rows = structured_from_payload(payload, id_context=ctx)["injuries"]
    assert [(r["player_id"], r["external_player_id"], r["photo_url"]) for r in rows] == [
        (549, 67971, "https://media.api-sports.io/football/players/67971.png"),
        (139, 389315, "https://media.api-sports.io/football/players/389315.png"),
    ], rows


def test_english_only_injury_name_still_resolves_same_way():
    """기존 run(6c2ce4c2)의 영어 이름 저장 모양도 같은 결과를 낸다(회귀 없음)."""
    from app.preview.section_structured import StructuredIdContext, structured_from_payload

    payload = {
        "payload": {
            "structured": {
                "injuries": [
                    {
                        "player_name": "Marc Guéhi",
                        "player_id": None,
                        "team": "Manchester City",
                        "team_id": 13,
                        "status": "doubtful",
                        "summary": "고관절 부상",
                    }
                ]
            }
        }
    }
    ctx = StructuredIdContext(_korean_injury_resolver(), scope_team_ids=(13, 4))
    rows = structured_from_payload(payload, id_context=ctx)["injuries"]
    assert rows[0]["player_id"] == 549, rows
    assert rows[0]["photo_url"] == "https://media.api-sports.io/football/players/67971.png"
    # 표시 이름은 DB 한국어 값으로 통일된다(영어 표기가 남지 않는다).
    assert rows[0]["player"] == "마크 게히", rows


def test_partial_or_unknown_korean_name_is_not_guessed():
    """한국어 성만 쓰거나 저장 값에 없는 이름은 ID를 만들지 않는다(모호 매칭 금지)."""
    names = _korean_injury_resolver()
    for probe in ("게히", "킹", "없는 선수"):
        resolution = names.resolve_player(probe, scope_team_ids=[13, 4])
        assert resolution.player is None, probe


# --------------------------------------------------------------------------
# PF-B 3차 — 최신 실제 배당 채택(오래됐다는 이유로 버리지 않음)
# --------------------------------------------------------------------------


def _odds_record(name: str, home: str, draw: str, away: str, *, updated, book_id: int = 1):
    from app.preview.sources import api_football as api

    return api.OddsRecord(
        bookmaker_id=book_id,
        bookmaker=name,
        market_id=5,
        market="Match Winner",
        home=home,
        draw=draw,
        away=away,
        updated_at=updated,
    )


def test_stale_provider_quote_is_adopted_with_raw_observed_time():
    """94시간 지난 실제형태 값도 채택되고, 기준 시각은 **원시 갱신 시각** 그대로다.

    실패하면 사용자는 배당 표를 다시 보지 못한다(사용자 지시: 오래돼도 최신값을 쓴다).
    """
    from app.preview.sources import provider_odds

    stamp = datetime(2026, 11, 8, 12, 52, 18, tzinfo=timezone.utc)
    collected = datetime(2026, 11, 12, 21, 30, tzinfo=timezone.utc)
    # 실제 제공자 응답의 기준 시각(2026-11-08T12:52:18Z)과 같은 모양이다.
    assert 90 < (collected - stamp).total_seconds() / 3600 < 110
    quotes, _diagnostics = provider_odds._quotes_from_records(
        [_odds_record("Pinnacle", "1.80", "3.70", "4.30", updated=stamp)],
        fixture_id=1557474,
        collected_at=collected,
    )
    assert len(quotes) == 1
    assert quotes[0].home_decimal == 1.80
    # 수집 시각으로 바꾸지 않는다(오래된 값이 방금 측정된 것처럼 보이면 안 된다).
    assert quotes[0].observed_at == stamp
    assert quotes[0].observed_at != collected


def test_same_bookmaker_chooses_most_recent_update():
    """같은 업체 레코드가 여러 개면 갱신 시각이 가장 최근인 줄을 쓴다."""
    from app.preview.sources import provider_odds

    early = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    later = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)
    quotes, _diagnostics = provider_odds._quotes_from_records(
        [
            _odds_record("Bet365", "1.85", "3.60", "4.20", updated=early, book_id=8),
            _odds_record("Bet365", "1.80", "3.65", "4.30", updated=later, book_id=8),
            _odds_record("Unibet", "1.88", "3.55", "4.10", updated=early, book_id=11),
        ],
        fixture_id=1557474,
        collected_at=datetime(2026, 11, 12, 21, 30, tzinfo=timezone.utc),
    )
    by_site = {quote.site: quote for quote in quotes}
    # 최신 갱신값을 골랐고 업체당 한 행만 남는다.
    assert by_site["Bet365"].home_decimal == 1.80
    assert by_site["Bet365"].observed_at == later
    assert [q.site for q in quotes] == ["Bet365", "Unibet"]


def test_unknown_update_time_is_adopted_without_faking_freshness():
    """갱신 시각이 없어도 값은 채택하되 `observed_at`은 `None`(신선한 척하지 않는다)."""
    from app.preview.sources import provider_odds

    quotes, _diagnostics = provider_odds._quotes_from_records(
        [_odds_record("NoTime", "1.90", "3.50", "4.00", updated=None, book_id=99)],
        fixture_id=1557474,
        collected_at=datetime(2026, 11, 12, 21, 30, tzinfo=timezone.utc),
    )
    assert len(quotes) == 1
    assert quotes[0].observed_at is None
    assert "갱신 시각" in (quotes[0].note or "")


# --------------------------------------------------------------------------
# PD-B — 주목 선수 팀 로고 ID 연결(부상 행과 같은 계약)
# --------------------------------------------------------------------------


def test_player_team_external_id_comes_from_verified_db_team():
    """주목 선수 행이 **검증된** 내부/외부 팀 ID를 함께 낸다(팀 로고를 ID로 확정).

    저장 payload에는 팀 표시 이름(한국어)만 있고 `team_id`가 없다(실제 run d96fe824 모양).
    그때 같은 경기 두 팀 범위의 DB 이름으로만 확인한다. 실패하면 주목 선수 카드에 팀 로고가
    그려지지 않고, 별칭표가 없는 run에서는 좌우 판정까지 비어 로고가 영영 나오지 않는다.
    """
    from app.preview.section_structured import StructuredIdContext, structured_from_payload

    payload = {
        "payload": {
            "structured": {
                "players": [
                    {
                        "selected_player": "엘링 홀란드",
                        "selection_reason": "리그 9골",
                        "team": "맨체스터 시티",
                        "player_id": 533,
                    },
                    {
                        "selected_player": "로드리고 무니즈",
                        "selection_reason": "팀 내 최다 득점",
                        "team": "풀럼",
                        "player_id": 138,
                    },
                ]
            }
        }
    }
    ctx = StructuredIdContext(_names_resolver(), scope_team_ids=(13, 4))
    rows = structured_from_payload(payload, id_context=ctx)["players"]
    # 내부 team_id 는 보존하고, 외부 팀 ID 는 확인된 경우에만 덧붙인다.
    assert [(row["team_id"], row["team_external_id"]) for row in rows] == [
        (13, 50),
        (4, 36),
    ], rows


def test_unverified_player_team_leaves_team_ids_null():
    """팀을 확인하지 못하면 내부/외부 팀 ID를 만들지 않는다(배열 순서·이름 유사도 추측 금지)."""
    from app.preview.section_structured import StructuredIdContext, structured_from_payload

    payload = {
        "payload": {
            "structured": {
                "players": [
                    {
                        "selected_player": "이름 없는 팀 선수",
                        "selection_reason": "이유",
                        "team": "알 수 없는 FC",
                        "player_id": 700,
                    },
                    {
                        "selected_player": "팀 표기 없는 선수",
                        "selection_reason": "이유",
                        "player_id": 701,
                    },
                ]
            }
        }
    }
    ctx = StructuredIdContext(_names_resolver(), scope_team_ids=(13, 4))
    rows = structured_from_payload(payload, id_context=ctx)["players"]
    assert [row["team_id"] for row in rows] == [None, None], rows
    assert [row["team_external_id"] for row in rows] == [None, None], rows
