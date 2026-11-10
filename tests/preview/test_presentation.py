"""MP-09 독자용 투영·표현 검사.

이 파일이 확인하는 것:

- `to_preview_document`는 넘긴 값만 담고 **내부 ID·진단·운영 안내를 지운다**.
- 독자용 API 투영은 **허용 목록**이라 내부 필드가 새 키로 새지 않는다.
- 없는 보조 항목은 빈 배열·빈 카드로 남기지 않고 키 자체를 만들지 않는다.
- 사실/판단 표기(`사실(fact):`/`해석(interpretation):`)와 내부 근거 ID(`[api:…]`)가
  본문에서 읽히는 문장으로 바뀐다.
- AI 예측 표시·자료 기준 시각·출처 표시가 유지된다.

모든 값은 기록 fixture에서 온다. 실제 모델 호출은 없다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.preview import presentation
from app.preview.contracts import (
    PREVIEW_DOCUMENT_VERSION,
    ClaimKind,
    FixtureIdentity,
)

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "synthesis_inputs.json").read_text(
        encoding="utf-8"
    )
)
FIXTURE = FixtureIdentity.from_dict(FIXTURES["fixture"])
NOW = datetime(2026, 11, 10, 12, 30, tzinfo=timezone.utc)
DATA_AS_OF = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

SOURCE_ROWS = (
    {
        "label": "Manchester City vs Fulham preview",
        "url": "https://www.bbc.com/sport/football/manchester-city-fulham-preview",
        "kind": "search",
        "note": "Google Search grounding이 제공한 출처입니다.",
    },
    {
        "label": "API-Football 저장 자료",
        "kind": "api",
        "url": None,
        "note": "수집 2026-11-10 · 저장 자료",
        "collected_at": "2026-11-10T12:00:00+00:00",
    },
)


def _document(**overrides):
    kwargs = {
        "document_id": uuid.uuid4(),
        "run_id": uuid.uuid4(),
        "fixture": FIXTURE,
        "generated_at": NOW,
        "data_as_of": DATA_AS_OF,
        "headline": "리그 3위 Manchester City가 홈에서 하위권 Fulham을 상대합니다.",
        "watch_points": (
            "Manchester City가 홈에서 볼 점유를 오래 가져가는 흐름을 볼 만합니다.",
        ),
        "players_to_watch": (
            {
                "player": "Erling Haaland",
                "team": "Manchester City",
                "reason": "상대 수비가 내려서는 경기에서 먼저 지켜볼 선수입니다.",
            },
        ),
        "absences_impact": "Manchester City는 왼쪽 수비 자원이 줄어 측면 대응이 달라질 수 있습니다.",
        "external_outlook": (
            {
                "publisher": "BBC Sport",
                "statement": "Manchester City가 홈에서 우세할 것으로 전망했습니다.",
                "published_at": "2026-11-09",
                "url": "https://www.bbc.com/sport/football/manchester-city-fulham-preview",
                "source_kind": ClaimKind.EXTERNAL_FORECAST.value,
            },
            {
                "publisher": "API-Football",
                "statement": "알고리즘은 홈팀 우세로 계산했습니다.",
                "source_kind": ClaimKind.API_PREDICTION.value,
            },
        ),
        "ai_prediction": {
            "lean": "home",
            "score": "2-1",
            "reasoning": ("상대가 하위권이고 홈 이점이 있어 홈팀 우세로 봅니다.",),
            "note": "예상은 결과를 보장하지 않습니다.",
        },
        "sources": SOURCE_ROWS,
    }
    kwargs.update(overrides)
    return presentation.to_preview_document(**kwargs)


def _reader(document=None) -> presentation.ReaderPreview:
    document = document or _document()
    return presentation.ReaderPreview(
        document=document,
        fixture_label="Manchester City vs Fulham",
        league="Premier League",
        sources=document.sources,
        attribution={
            "model": "recorded-model",
            "provider": "recorded-model",
            "mode": "mock",
            "executed_at": NOW.isoformat(),
            "external_calls": 0,
        },
    )


# --------------------------------------------------------------------------
# 계약 문서
# --------------------------------------------------------------------------


def test_document_uses_contract_and_carries_values_unchanged():
    document = _document()
    assert isinstance(document, presentation.PreviewDocument)
    assert document.contract_version == PREVIEW_DOCUMENT_VERSION
    assert document.fixture.fixture_id == FIXTURE.fixture_id
    assert document.ai_prediction["lean"] == "home"
    assert document.ai_prediction["score"] == "2-1"
    assert document.data_as_of == DATA_AS_OF


def test_missing_optional_section_makes_no_empty_card():
    """없는 보조 항목은 빈 배열·플레이스홀더가 아니라 '없음'이다."""
    document = _document(
        absences_impact=None,
        external_outlook=(),
        players_to_watch=(),
        sources=(),
    )
    assert document.absences_impact is None
    assert document.external_outlook == ()
    assert document.players_to_watch == ()
    assert document.sources == ()

    body = presentation.compose_reader_body(document)
    # 본문에도 그 항목의 문단이 생기지 않는다.
    assert "외부 전망입니다." not in body
    assert "주목할 선수는 이렇습니다." not in body
    assert "자료 없음" not in body and "미확보" not in body
    # 남아 있는 내용은 그대로 읽힌다.
    assert document.headline in body
    assert presentation.AI_FORECAST_LABEL in body


def test_reader_payload_is_an_allow_list():
    """독자용 응답에는 허용한 키만 있고 내부 필드는 새지 않는다."""
    payload = presentation.reader_payload(
        _reader(), generated_at=NOW, data_as_of=DATA_AS_OF
    )
    allowed = {
        "fixture",
        "headline",
        "generated_at",
        "data_as_of",
        "attribution",
        "watch_points",
        "players_to_watch",
        "absences_impact",
        "external_outlook",
        "ai_prediction",
        "sources",
        "body",
    }
    assert set(payload) <= allowed
    assert set(payload["fixture"]) == {
        "fixture_id",
        "home_team_id",
        "away_team_id",
        "league_id",
        "season",
        "kickoff_at",
        "label",
        "league",
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in (
        "diagnostics",
        "coverage",
        "selected_result_ids",
        "snapshot",
        "attempt",
        "workflow_id",
        "workflow_version",
        "run_id",
    ):
        assert forbidden not in serialized


def test_diagnostics_and_reader_are_separate_outputs():
    diagnostics = presentation.admin_diagnostics(
        gaps=[{"module_id": "R3", "reason": "배당 자료가 제공되지 않았습니다."}],
        excluded_claims=(),
        diagnostics=["검색 인용 출처를 확인하지 못했습니다."],
        selected_inputs=[{"module_id": "R1", "version": 2}],
        contract_versions={"contract": "mp02-1"},
    )
    assert diagnostics["gaps"]
    assert diagnostics["selected_inputs"]
    payload = presentation.reader_payload(
        _reader(), generated_at=NOW, data_as_of=DATA_AS_OF
    )
    assert "gaps" not in payload
    assert "selected_inputs" not in payload


# --------------------------------------------------------------------------
# 본문 문장 정리
# --------------------------------------------------------------------------


def test_internal_evidence_ids_and_markers_are_cleaned():
    document = _document(
        watch_points=(
            "사실(fact): Manchester City는 리그 3위입니다 [api:standings-13].",
            "해석(interpretation): 홈 이점이 커 보입니다.",
        ),
    )
    body = presentation.compose_reader_body(document)
    assert "[api:standings-13]" not in body
    assert "사실(fact)" not in body
    assert "해석(interpretation)" not in body
    # 해석은 해석임을 표시한 문장으로 남는다.
    assert "AI 해석으로는" in body
    # 사실 문장 자체는 남는다.
    assert "Manchester City는 리그 3위입니다" in body


def test_internal_ids_are_removed_from_players_and_sources():
    document = _document(
        players_to_watch=(
            {
                "player": "Erling Haaland",
                "reason": "r1-player-0 근거로 선정했습니다.",
            },
        ),
        sources=(
            {"label": "r3-media-0 출처", "url": "https://example.test/a", "kind": "search"},
        ),
    )
    body = presentation.compose_reader_body(document)
    assert "r1-player-0" not in body
    reader = _reader(document)
    payload = presentation.reader_payload(
        reader, generated_at=NOW, data_as_of=DATA_AS_OF
    )
    assert "r3-media-0" not in json.dumps(payload, ensure_ascii=False)


def test_ai_forecast_attribution_and_source_times_are_kept():
    reader = _reader()
    payload = presentation.reader_payload(
        reader, generated_at=NOW, data_as_of=DATA_AS_OF
    )
    attribution = payload["attribution"]
    assert attribution["ai_forecast_label"] == presentation.AI_FORECAST_LABEL
    assert attribution["ai_forecast_note"]
    assert attribution["executed_at"] == NOW.isoformat()
    # 자료 기준 시각이 남는다(독자 이해에 필요한 정보).
    assert payload["data_as_of"] == DATA_AS_OF.isoformat()
    # 출처 행에 검색 URL과 수집 시각이 있다.
    assert payload["sources"][0]["url"].startswith("https://www.bbc.com/")
    assert payload["sources"][1]["observed_at"] == "2026-11-10T12:00:00+00:00"


def test_api_prediction_row_is_marked_as_algorithmic():
    reader = _reader()
    payload = presentation.reader_payload(
        reader, generated_at=NOW, data_as_of=DATA_AS_OF
    )
    api_rows = [
        row
        for row in payload["external_outlook"]
        if row["source_kind"] == ClaimKind.API_PREDICTION.value
    ]
    assert api_rows
    # 제공자 이름은 실제 값 그대로 남고(지어낸 일반 라벨로 덮지 않는다), 알고리즘
    # 예측이라는 구분은 별도 표시로 유지된다.
    assert api_rows[0]["publisher"] == "API-Football"
    assert api_rows[0]["source_note"].startswith("제공자 알고리즘 예측")


def test_real_provider_names_survive_cleanup():
    """정리 규칙이 실제 출처 이름을 지우지 않는다(내부 ID 오탐 회귀 검사).

    실제 결함: 대소문자 무시 규칙이 "API-Football"을 내부 ID `api-…`로 오인해 지웠다.
    """
    text = presentation._reader_text("API-Football 알고리즘 예측과 API 가이드")
    assert "API-Football" in text
    assert "API 가이드" in text
    # 진짜 내부 ID는 계속 지운다.
    assert "r1-watch-0" not in presentation._reader_text("r1-watch-0 문장")
    assert "9a8f1d2e-0001-4000-8000-000000000001" not in presentation._reader_text(
        "9a8f1d2e-0001-4000-8000-000000000001 문장"
    )


def test_mode_label_distinguishes_mock_from_live():
    """모의·재생 표시를 실제 생성으로 읽지 않게 한다."""
    from app.preview.contracts import RunMode

    assert "mock" in presentation.mode_label(RunMode.MOCK)
    assert "live" in presentation.mode_label(RunMode.LIVE)
    assert presentation.mode_label("unknown-mode") == "unknown-mode"


# --------------------------------------------------------------------------
# 관리자 API 경계 (ADMIN 전용·독자용 분리)
# --------------------------------------------------------------------------

LOGIN = "/api/v1/auth/login"
PREVIEW_API = "/api/v1/admin/preview"


def _login_admin(client, make_user) -> dict:
    user = make_user(role="ADMIN")
    response = client.post(
        LOGIN, json={"email": user["email"], "password": user["password"]}
    )
    assert response.status_code == 200, response.text
    return user


def _run_synthesis(session_factory):
    from app.preview import sections, runner
    from tests.preview.test_synthesis import (
        FIXTURES as SYNTH_FIXTURES,
        MOMENT as SYNTH_MOMENT,
        _seed_selected_results,
        _transport,
    )

    seeds = _seed_selected_results(session_factory)
    implementations = sections.build_implementations(
        "section_synthesis",
        transport=_transport(SYNTH_FIXTURES["model_text_ok"]),
        now=SYNTH_MOMENT,
    )
    with session_factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id="section_synthesis",
            implementations=implementations,
            actor_id=1,
            fixture=SYNTH_FIXTURES["fixture"],
            fixture_label="Manchester City vs Fulham",
            selected_result_ids=seeds,
        )
        session.commit()
        return str(result.run_id), result.body


def test_preview_endpoint_requires_admin(client, make_user):
    """독자용 프리뷰 조회도 서버의 ADMIN 검사를 통과해야 한다."""
    from app.auth.identity import IdentityUser
    from app.auth.service import issue_session
    from app.db import get_session_factory

    anonymous = uuid.uuid4()
    assert client.get(f"{PREVIEW_API}/runs/{anonymous}/preview").status_code == 401
    assert (
        client.get(f"{PREVIEW_API}/runs/{anonymous}/preview/diagnostics").status_code
        == 401
    )

    # 세션은 유효하지만 역할이 ADMIN이 아닌 경우: 401이 아니라 403이어야 한다.
    user = make_user(role="STREAMER")
    factory = get_session_factory()
    with factory() as session:
        principal = IdentityUser(
            id=user["id"], email=user["email"], role=user["role"], is_active=True
        )
        issued = issue_session(session, principal)
        token = issued.token
        session.commit()
    client.cookies.set("preview_admin_session", token)
    assert client.get(f"{PREVIEW_API}/runs/{anonymous}/preview").status_code == 403
    assert (
        client.get(f"{PREVIEW_API}/runs/{anonymous}/preview/diagnostics").status_code
        == 403
    )


def test_preview_endpoint_returns_reader_projection_only(
    client, make_user, session_factory
):
    """독자용 응답에는 본문·근거만 있고 진단·ID는 별도 경로에 있다."""
    _login_admin(client, make_user)
    run_id, body = _run_synthesis(session_factory)

    response = client.get(f"{PREVIEW_API}/runs/{run_id}/preview")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["body"] == body
    assert payload["headline"]
    assert payload["sources"]
    assert payload["ai_prediction"]["lean"] in {"home", "draw", "away"}

    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in (
        "diagnostics",
        "coverage",
        "selected_result_ids",
        "snapshot_ids",
        "workflow_version",
        "attempt",
        "api:standings-13",
    ):
        assert forbidden not in serialized, forbidden

    diagnostics = client.get(f"{PREVIEW_API}/runs/{run_id}/preview/diagnostics")
    assert diagnostics.status_code == 200, diagnostics.text
    view = diagnostics.json()
    assert view["selected_inputs"]
    assert {row["module_id"] for row in view["selected_inputs"]} == {"R1", "R2", "R3"}
    assert view["synthesis_versions"]["implementation"] == "mp09-s1-1"
    # 진단에는 모의 실행 표시가 남는다(실제 생성으로 읽지 않게).
    assert "mock" in view["mode"]["mode"]


def test_preview_endpoint_reports_missing_preview_honestly(
    client, make_user, session_factory
):
    """프리뷰가 없는 실행은 빈 본문을 만들지 않고 404로 사실대로 알린다."""
    from app.preview import demo_pipeline

    _login_admin(client, make_user)
    with session_factory() as session:
        created = demo_pipeline.create_recorded_mock_run(session, actor_id=1)
        session.commit()
        run_id = str(created.run_id)

    response = client.get(f"{PREVIEW_API}/runs/{run_id}/preview")
    assert response.status_code == 404
    assert "독자용 프리뷰 결과가 없습니다" in response.json()["detail"]
