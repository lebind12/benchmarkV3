"""NS-02 선수·부상 섹션 생성 후처리·재생성·진단 직렬화 대표 사례 검사."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid

from app.api.v1 import preview_admin
from app.preview import bundle_pipeline
from app.preview import information_bundle as bundle_contract
from app.preview import localized_names
from app.preview import player_section_contracts as psc
from app.preview import player_section_processing as psp
from app.preview import provider
from app.preview.contracts import (
    Environment,
    ExecutionContext,
    ExecutionLimits,
    OperationKind,
    QualityStatus,
    RunMode,
)
from app.preview.modules import bundle_sections
from app.preview.retry import RunBudget, plan_limits

FIXED_NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
HOME_ID = 13
AWAY_ID = 4
HOME_KO = "맨체스터 시티"
AWAY_KO = "풀럼"


def _resolver() -> localized_names.DisplayNames:
    return localized_names.DisplayNames(
        localized_names.LocalizedNameIndex(
            teams=(
                localized_names.TeamNameRow(
                    team_id=HOME_ID,
                    external_id=50,
                    english_name="Manchester City",
                    name_ko=HOME_KO,
                ),
                localized_names.TeamNameRow(
                    team_id=AWAY_ID,
                    external_id=36,
                    english_name="Fulham",
                    name_ko=AWAY_KO,
                ),
            ),
            players=(
                localized_names.PlayerNameRow(
                    player_id=7101,
                    external_id=4001,
                    english_name="Erling Haaland",
                    firstname="Erling",
                    lastname="Haaland",
                    current_team_id=HOME_ID,
                    name_ko="엘링 홀란",
                ),
                localized_names.PlayerNameRow(
                    player_id=7102,
                    external_id=4002,
                    english_name="Phil Foden",
                    firstname="Phil",
                    lastname="Foden",
                    current_team_id=HOME_ID,
                    name_ko=None,
                ),
                localized_names.PlayerNameRow(
                    player_id=7103,
                    external_id=4003,
                    english_name="Rayan Cherki",
                    firstname="Rayan",
                    lastname="Cherki",
                    current_team_id=HOME_ID,
                    name_ko="라얀 셰르키",
                ),
                localized_names.PlayerNameRow(
                    player_id=7201,
                    external_id=5001,
                    english_name="Alex Iwobi",
                    firstname="Alex",
                    lastname="Iwobi",
                    current_team_id=AWAY_ID,
                    name_ko="알렉스 이워비",
                ),
                localized_names.PlayerNameRow(
                    player_id=7202,
                    external_id=5002,
                    english_name="Rodrigo Muniz",
                    firstname="Rodrigo",
                    lastname="Muniz",
                    current_team_id=AWAY_ID,
                    name_ko="호드리구 무니스",
                ),
            ),
        )
    )


def _bundle() -> dict:
    return {
        "bundle_id": "bundle-ns02-test",
        "bundle_version": "1",
        "fixture": {
            "fixture_id": 9001,
            "league_id": 39,
            "season": 2026,
            "kickoff_at": FIXED_NOW.isoformat(),
            "home_team_id": HOME_ID,
            "away_team_id": AWAY_ID,
        },
        "db_snapshot": {
            "teams": [
                {"team_id": HOME_ID, "name": "Manchester City", "side": "home"},
                {"team_id": AWAY_ID, "name": "Fulham", "side": "away"},
            ],
            "roster": [
                {"player_id": 7101, "team_id": HOME_ID, "name": "Erling Haaland"},
                {"player_id": 7102, "team_id": HOME_ID, "name": "Phil Foden"},
                {"player_id": 7103, "team_id": HOME_ID, "name": "Rayan Cherki"},
                {"player_id": 7201, "team_id": AWAY_ID, "name": "Alex Iwobi"},
                {"player_id": 7202, "team_id": AWAY_ID, "name": "Rodrigo Muniz"},
            ],
            "injuries": [
                {
                    "injury_id": 1,
                    "player_id": 7102,
                    "team_id": HOME_ID,
                    "player_name": "Phil Foden",
                    "status": "doubtful",
                    "reason": "발목 타박",
                }
            ],
        },
        "sources": [
            {
                "source_id": "src:stats",
                "discovery_group": "players_injury",
                "nature": "article",
                "method": "fetched",
                "passages": [
                    {
                        "source_id": "src:stats",
                        "passage_id": "src:stats#p1",
                        "text": "Manchester City vs Fulham preview stats.",
                    }
                ],
            }
        ],
    }


def _context() -> ExecutionContext:
    return ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=OperationKind.PREVIEW,
        environment=Environment.DEV,
        mode=RunMode.LIVE,
        actor_id=1,
        config_version="mp11-sections-test",
        limits=ExecutionLimits(
            model_requests=8, api_requests=24, attempts_per_call=3, deadline_seconds=1800
        ),
    )


def _budget() -> RunBudget:
    return RunBudget.for_run(
        plan_limits(model_requests=8, normal_model_calls=6), now=FIXED_NOW
    )


def _reply(answer: dict | str, *, finish_reason: str = "STOP", http_status: int = 200) -> provider.TransportResult:
    text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
    return provider.TransportResult(
        http_status=http_status,
        raw_request={"contents": "req"},
        raw_response={
            "candidates": [
                {
                    "content": {"parts": [{"text": text}], "role": "model"},
                    "finishReason": finish_reason,
                }
            ]
        },
        usage={"input_tokens": 50, "output_tokens": 30},
    )


def _run_section(
    section_id: str,
    script: list[provider.TransportResult],
    *,
    resolver=None,
) -> tuple[bundle_sections.SectionDraft, provider.RecordedTransport]:
    transport = provider.RecordedTransport(
        script=script, provider="recorded-model", mode=RunMode.LIVE
    )
    draft = bundle_sections.build_bundle_section(
        section_id=section_id,
        bundle=_bundle(),
        transport=transport,
        context=_context(),
        budget=_budget(),
        resolver=resolver,
        now=FIXED_NOW,
    )
    return draft, transport


def test_happy_path_two_per_team_db_ko_priority_and_contract_alignment():
    """DB 한글명이 같은 응답 AI 표기보다 우선하고 4슬롯·ETC=NULL·계약 변환이 일치해야 사용자가 검증된 사진·이름을 본다."""
    answer = {
        "players": [
            {
                "selected_player": "Erling Haaland",
                "team": "Manchester City",
                "player_ref": "7101",
                "selection_reason": "홈 전방 득점원이다.",
                "evidence": ["src:stats#p1"],
            },
            {
                "selected_player": "Phil Foden",
                "team": "Manchester City",
                "player_ref": "7102",
                "selection_reason": "하프스페이스 전개가 강점이다.",
                "evidence": ["src:stats#p1"],
            },
            {
                "selected_player": "Alex Iwobi",
                "team": "Fulham",
                "player_ref": "7201",
                "selection_reason": "원정 측면 핵심이다.",
                "evidence": ["src:stats#p1"],
            },
            {
                "selected_player": "Rodrigo Muniz",
                "team": "Fulham",
                "player_ref": "7202",
                "selection_reason": "박스 안 경합에 강하다.",
                "evidence": ["src:stats#p1"],
            },
        ],
        "korean_labels": [
            {"original": "Erling Haaland", "korean": "엘링 하알란드", "kind": "player"},
            {"original": "Phil Foden", "korean": "필 포든", "kind": "player"},
        ],
    }
    shared = _resolver()
    draft, transport = _run_section(
        bundle_contract.SECTION_PLAYERS, [_reply(answer)], resolver=shared
    )

    assert len(transport.calls) == 1
    assert draft.quality is QualityStatus.READY
    proc = draft.structured["processing"]
    assert proc["persisted"] is False
    assert proc["storage_status"] == "저장 예정 값"
    assert proc["home_etc"] is None and proc["away_etc"] is None
    assert proc["adopted_attempt_ordinal"] == 0
    assert proc["regeneration_count"] == 0
    assert proc["home1"]["name_ko"] == "엘링 홀란"
    assert proc["home1"]["name_source"] == "db_ko"
    assert proc["home1"]["player_id"] == 7101
    assert proc["home1"]["external_player_id"] == 4001
    assert proc["home2"]["name_ko"] == "필 포든"
    assert proc["home2"]["name_source"] == "ai_candidate"
    assert proc["home2"]["player_id"] == 7102
    assert proc["home2"]["external_player_id"] == 4002
    assert proc["away1"]["player_id"] == 7201 and proc["away2"]["player_id"] == 7202

    # 공통 계약 PlayerSectionProcessingResult 변환도 오류 없이 통과해야 한다.
    contract_result = psp.place_final_candidates(
        workflow_id=psc.PlayerSectionWorkflowId.SECTION_PLAYERS,
        fixture=psp.FixtureTeamContext(9001, HOME_ID, AWAY_ID, HOME_KO, AWAY_KO),
        candidates=psp.evaluate_raw_candidates(
            workflow_id=psc.PlayerSectionWorkflowId.SECTION_PLAYERS,
            payload=answer,
            fixture=psp.FixtureTeamContext(9001, HOME_ID, AWAY_ID, HOME_KO, AWAY_KO),
            resolver=shared.fork(),
        )[0],
        labels=answer["korean_labels"],
        attempts=[
            psp.ProcessingAttemptRecord(
                attempt_ordinal=0,
                logical_call_id="section_players",
                parsed_valid=True,
                raw_text="{}",
                parsed_json=answer,
            )
        ],
        regeneration_count=0,
        regeneration_reason=None,
        adopted_attempt_ordinal=0,
    ).to_contract_result()
    assert contract_result is not None
    assert contract_result.adopted_attempt_ordinal == 0


def test_unresolved_player_keeps_null_ids_ai_korean_body_and_reason_across_both_sections():
    """DB 미확인 선수는 주목·부상 섹션 모두 ID=NULL, AI 한글명 후보, 본문·미연결 사유를 함께 보존해야 진단이 정확하다."""
    player_answer = {
        "players": [
            {
                "selected_player": "Academy Prospect",
                "team": "Manchester City",
                "selection_reason": "Academy Prospect 선수의 압박 가담이 눈에 띈다.",
                "evidence": ["src:stats#p1"],
            }
        ],
        "korean_labels": [
            {"original": "Academy Prospect", "korean": "아카데미 유망주", "kind": "player"}
        ],
    }
    draft, _ = _run_section(
        bundle_contract.SECTION_PLAYERS, [_reply(player_answer)], resolver=_resolver()
    )
    proc = draft.structured["processing"]
    slot = proc["home1"]
    assert slot["player_id"] is None
    assert slot["external_player_id"] is None
    assert slot["name_ko"] == "아카데미 유망주"
    assert slot["name_source"] == "ai_candidate"
    assert "not_found" in (slot["unresolved_reason"] or "")
    # 본문은 후속 이름 치환으로 재작성되지 않아야 한다.
    assert slot["body"] == "Academy Prospect 선수의 압박 가담이 눈에 띈다."

    injury_answer = {
        "injuries": [
            {
                "player_name": "Academy Prospect",
                "team": "Fulham",
                "status": "doubtful",
                "injury": "종아리 근육 긴장",
                "importance": "교체 카드 선택 폭에 영향을 준다.",
                "evidence": ["src:stats#p1"],
            }
        ],
        "korean_labels": [
            {"original": "Academy Prospect", "korean": "아카데미 유망주", "kind": "player"}
        ],
    }
    inj_draft, _ = _run_section(
        bundle_contract.SECTION_AVAILABILITY, [_reply(injury_answer)], resolver=_resolver()
    )
    inj_proc = inj_draft.structured["processing"]
    inj_slot = inj_proc["away1"]
    assert inj_slot["player_id"] is None
    assert inj_slot["external_player_id"] is None
    assert inj_slot["name_ko"] == "아카데미 유망주"
    assert inj_slot["name_source"] == "ai_candidate"
    assert inj_slot["status"] == "doubtful"
    assert inj_draft.structured["injuries"][0]["summary"] == inj_slot["body"]
    assert inj_draft.structured["injuries"][0]["detail"] == inj_slot["body"]
    assert "출전 불확실" in inj_draft.body and "결장 확정" not in inj_draft.body


def test_verified_player_without_any_korean_name_fails_cleanly_as_translation_defect():
    """DB 한글명과 AI 한글명 후보가 모두 없는 선수는 영어 원문을 한글로 가장하지 않고 번역 결함·미배치로 남겨야 한다."""
    answer = {
        "players": [
            {
                "selected_player": "Phil Foden",
                "team": "Manchester City",
                "selection_reason": "중앙 전개 핵심이다.",
                "evidence": ["src:stats#p1"],
            }
        ],
        "korean_labels": [],
    }
    draft, _ = _run_section(
        bundle_contract.SECTION_PLAYERS, [_reply(answer)], resolver=_resolver()
    )

    assert draft.quality is QualityStatus.INSUFFICIENT
    assert draft.body == ""
    proc = draft.structured["processing"]
    assert proc["home1"] is None
    assert proc["translation_defects"]
    assert proc["unplaced_items"][0]["reason"] == "missing_name_ko"
    assert proc["unplaced_items"][0]["player_id"] == 7102


def test_first_missing_body_beyond_team_cap_and_duplicate_trigger_single_regeneration():
    """팀당 2명 절단 전 원시 응답의 누락·중복을 검사해 1회 재생성하고 연속 0-기반 ordinal로 최종 응답만 채택해야 한다."""
    first = {
        "players": [
            {
                "selected_player": "Erling Haaland",
                "team": "Manchester City",
                "selection_reason": "첫 유효 설명이다.",
                "evidence": ["src:stats#p1"],
            },
            {
                "selected_player": "Rayan Cherki",
                "team": "Manchester City",
                "selection_reason": "측면 돌파력이 좋다.",
                "evidence": ["src:stats#p1"],
            },
            {
                # 홈 3번째 항목이라 절단 후 검사였다면 놓쳤을 설명 누락이다.
                "selected_player": "Phil Foden",
                "team": "Manchester City",
                "selection_reason": "",
                "evidence": ["src:stats#p1"],
            },
            {
                # 동일 선수(Erling Haaland) 중복
                "selected_player": "E. Haaland",
                "team": "Manchester City",
                "selection_reason": "두 번째 중복 설명이다.",
                "evidence": ["src:stats#p1"],
            },
        ]
    }
    second = {
        "players": [
            {
                "selected_player": "Erling Haaland",
                "team": "Manchester City",
                "selection_reason": "재생성된 최신 설명이다.",
                "evidence": ["src:stats#p1"],
            },
            {
                "selected_player": "Alex Iwobi",
                "team": "Fulham",
                "selection_reason": "원정 공격 전환의 축이다.",
                "evidence": ["src:stats#p1"],
            },
        ]
    }
    draft, transport = _run_section(
        bundle_contract.SECTION_PLAYERS,
        [_reply(first), _reply(second)],
        resolver=_resolver(),
    )

    assert len(transport.calls) == 2
    assert draft.external_calls == 2
    assert draft.quality is QualityStatus.READY
    proc = draft.structured["processing"]
    assert proc["regeneration_count"] == 1
    assert proc["regeneration_reason"] == "missing_and_duplicate"
    assert proc["adopted_attempt_ordinal"] == 1
    assert [att["attempt_ordinal"] for att in proc["attempts"]] == [0, 1]
    assert proc["attempts"][0]["regeneration_triggered"] is True
    assert proc["home1"]["body"] == "재생성된 최신 설명이다."
    assert proc["away1"]["player_id"] == 7201
    # 첫 번째 응답의 R. Cherki가 섞여 들어오지 않아야 한다.
    assert proc["home2"] is None


def test_last_valid_response_dedup_missing_and_single_player_per_team_without_second_regen():
    """재생성 후 마지막 응답에도 누락·중복·팀당 1명이면 추가 재생성 없이 누락 제거->설명 있는 첫 항목 보존->팀당 1명만 배치해야 한다."""
    first = {
        "players": [
            {"selected_player": "Erling Haaland", "team": "Manchester City", "selection_reason": ""}
        ]
    }
    second = {
        "players": [
            {
                "selected_player": "Erling Haaland",
                "team": "Manchester City",
                "selection_reason": "",
            },
            {
                "selected_player": "E. Haaland",
                "team": "Manchester City",
                "selection_reason": "설명이 있는 첫 유효 항목이다.",
            },
            {
                "selected_player": "Erling Haaland",
                "team": "Manchester City",
                "selection_reason": "뒤에 나온 중복 항목이다.",
            },
            {
                "selected_player": "Alex Iwobi",
                "team": "Fulham",
                "selection_reason": "원정 한 명만 유효하다.",
            },
        ]
    }
    draft, transport = _run_section(
        bundle_contract.SECTION_PLAYERS,
        [_reply(first), _reply(second)],
        resolver=_resolver(),
    )

    assert len(transport.calls) == 2
    proc = draft.structured["processing"]
    assert proc["regeneration_count"] == 1
    assert proc["home1"]["player_id"] == 7101
    assert proc["home1"]["body"] == "설명이 있는 첫 유효 항목이다."
    assert proc["home2"] is None
    assert proc["away1"]["player_id"] == 7201
    assert proc["away2"] is None
    reasons = [item["reason"] for item in proc["unplaced_items"]]
    assert reasons == ["missing_body", "duplicate_player"]


def test_final_regeneration_failure_or_budget_exhausted_never_falls_back_to_first_response():
    """재생성 응답이 3회 상한 안에 실패하면 첫 유효 응답으로 fallback하지 않고 실패로 끝내야 한다."""
    first_with_dup = {
        "players": [
            {
                "selected_player": "Erling Haaland",
                "team": "Manchester City",
                "selection_reason": "첫 응답 설명",
            },
            {
                "selected_player": "E. Haaland",
                "team": "Manchester City",
                "selection_reason": "중복 설명",
            },
        ]
    }
    draft, transport = _run_section(
        bundle_contract.SECTION_PLAYERS,
        [
            _reply(first_with_dup),
            _reply('{"players": [', finish_reason="MAX_TOKENS"),
            _reply("not-json"),
            _reply(first_with_dup),
        ],
        resolver=_resolver(),
    )

    assert len(transport.calls) == 3
    assert draft.quality is QualityStatus.INSUFFICIENT
    assert draft.body == ""
    proc = draft.structured["processing"]
    assert proc["ok"] is False
    assert proc["adopted_attempt_ordinal"] is None
    assert [att["attempt_ordinal"] for att in proc["attempts"]] == [0, 1, 2]

    # 1차 호출에서 이미 전송 재시도 2회 + 유효 1회로 3회를 다 썼다면 4번째 전송 없이 실패해야 한다.
    draft_exhausted, transport_exhausted = _run_section(
        bundle_contract.SECTION_PLAYERS,
        [
            _reply("bad-1"),
            _reply("bad-2"),
            _reply(first_with_dup),
            _reply(first_with_dup),
        ],
        resolver=_resolver(),
    )
    assert len(transport_exhausted.calls) == 3
    assert draft_exhausted.quality is QualityStatus.INSUFFICIENT
    assert draft_exhausted.body == ""


def test_untrusted_raw_model_ids_and_bools_are_rejected_and_distinct_unresolved_names_stay_separate():
    """모델이 적은 임의 숫자·bool ID를 신뢰하지 않고 DB 문맥으로만 검증하며 미확인 유사 이름은 임의로 합치지 않아야 한다."""
    answer = {
        "players": [
            {
                "selected_player": "Erling Haaland",
                "team": "Manchester City",
                "player_ref": True,
                "selection_reason": "bool 참조 무시 검증",
                "evidence": ["src:stats#p1"],
            },
            {
                "selected_player": "Unknown Prospect",
                "team": "Manchester City",
                # 모델이 기존 DB 홀란드 ID(7101)를 잘못 적어도 미확인 선수를 홀란드로 연결하면 안 된다.
                "player_ref": "7101",
                "selection_reason": "잘못된 참조 무시 검증",
                "evidence": ["src:stats#p1"],
            },
            {
                "selected_player": "Kim M.",
                "team": "Fulham",
                "selection_reason": "미확인 유사 이름 1",
                "evidence": ["src:stats#p1"],
            },
            {
                "selected_player": "Kim S.",
                "team": "Fulham",
                "selection_reason": "미확인 유사 이름 2",
                "evidence": ["src:stats#p1"],
            },
        ],
        "korean_labels": [
            {"original": "Unknown Prospect", "korean": "미확인 유망주", "kind": "player"},
            {"original": "Kim M.", "korean": "김민수", "kind": "player"},
            {"original": "Kim S.", "korean": "김서준", "kind": "player"},
        ],
    }
    draft, _ = _run_section(
        bundle_contract.SECTION_PLAYERS, [_reply(answer)], resolver=_resolver()
    )
    proc = draft.structured["processing"]
    assert proc["home1"]["player_id"] == 7101
    assert proc["home1"]["external_player_id"] == 4001
    assert proc["home2"]["player_id"] is None
    assert proc["home2"]["external_player_id"] is None
    assert proc["home2"]["name_ko"] == "미확인 유망주"
    assert proc["away1"]["name_ko"] == "김민수"
    assert proc["away2"]["name_ko"] == "김서준"


def test_shared_resolver_isolation_and_preview_admin_serialization_do_not_mutate_or_rewrite():
    """섹션 로컬 resolver가 공유 상태를 오염시키지 않고 preview_admin 조회 직렬화가 NS-02 본문을 재작성하거나 재호출하지 않아야 한다."""
    shared = _resolver()
    answer = {
        "players": [
            {
                "selected_player": "Custom Wing",
                "team": "Manchester City",
                "selection_reason": "Custom Wing 돌파 후 크로스가 강점이다.",
                "evidence": ["src:stats#p1"],
            }
        ],
        "korean_labels": [
            {"original": "Custom Wing", "korean": "커스텀 윙어", "kind": "player"}
        ],
    }
    draft, _ = _run_section(
        bundle_contract.SECTION_PLAYERS, [_reply(answer)], resolver=shared
    )

    assert shared.model_label_rows() == ()
    assert shared.unmapped == ()
    assert "Custom Wing 돌파 후 크로스가 강점이다." in draft.body

    result_id = str(uuid.uuid4())
    raw_detail = {
        "results": [
            {
                "result_id": result_id,
                "section_id": "section_players",
                "payload": {"structured": draft.structured},
            }
        ]
    }
    inspection = {
        "section_results": [
            {
                "section_result_id": result_id,
                "section_id": "section_players",
                "result_id": result_id,
                "body": draft.body,
            }
        ],
        "inspector_modules": [
            {"module_execution_id": str(uuid.uuid4()), "module_id": "R4", "tabs": {}}
        ],
    }
    attached = preview_admin._attach_player_section_processing(inspection, raw_detail)
    localized = preview_admin._localized_inspection(attached, names=None)
    assert localized["section_results"][0]["body"] == draft.body
    assert localized["section_results"][0]["player_section_processing"]["storage_status"] == "저장 예정 값"
    assert localized["inspector_modules"][0]["player_section_processing"]["home1"]["name_ko"] == "커스텀 윙어"
    assert bundle_pipeline._section_resolver(shared) is not shared
