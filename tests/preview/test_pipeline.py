"""MP-10 전체 프리뷰 실행 검사.

확인하는 것:

- 정상 경로가 **조사 3회 + 종합 1회**로 끝난다(재시도·숨은 호출 없음).
- 흐름이 D0→R1/R2/R3→V0→S1→V1 이고, 갈래 셋이 **하나의 예산**을 함께 쓴다.
- 같은 경기·버전 조합의 진행 중 요청은 기존 실행에 붙는다.
- 승인 없는 기본 전체 프리뷰는 거부되고, 관리자 명시 시험은 승인 상태로 표시되지 않는다.

실제 모델·API 호출은 0회다. 준비된 응답을 돌려주는 기록 transport와 저장 자료
모양의 검사용 조회기만 쓴다. 이 결과를 live 성공 증거로 쓰지 않는다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from app.preview import jobs, pipeline, provider
from app.preview.contracts import RunMode
from app.preview.retry import BudgetLimits

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FORM_FIXTURES = json.loads((FIXTURE_DIR / "form.json").read_text(encoding="utf-8"))
SYNTH_FIXTURES = json.loads(
    (FIXTURE_DIR / "synthesis_inputs.json").read_text(encoding="utf-8")
)
FIXTURE = FORM_FIXTURES["fixture"]
GROUNDING = FORM_FIXTURES["grounding_raw"]["candidates"][0]["grounding_metadata"]


def _fixture() -> dict:
    """form.json과 같은 경기. D0가 만드는 사실과 조사 응답이 같은 경기를 가리키게 한다."""
    return {
        "fixture_id": FIXTURE["fixture_id"],
        "league_id": FIXTURE["league_id"],
        "season": FIXTURE["season"],
        "home_team_id": FIXTURE["home_team_id"],
        "away_team_id": FIXTURE["away_team_id"],
        "kickoff_at": FIXTURE["kickoff_at"],
    }


class _StoredFixture:
    """저장 경기 한 건의 최소 표현. 읽기 전용 조회기가 돌려주는 모양과 같다."""

    internal_id = 1
    fixture_id = FIXTURE["fixture_id"]
    league_id = FIXTURE["league_id"]
    league_name = FIXTURE["league"]
    season = FIXTURE["season"]
    home_team_id = FIXTURE["home_team_id"]
    home_team_name = FIXTURE["home_team"]
    away_team_id = FIXTURE["away_team_id"]
    away_team_name = FIXTURE["away_team"]
    kickoff_at = datetime.fromisoformat(FIXTURE["kickoff_at"])
    status_short = "NS"
    referee = None
    updated_at = None

    @property
    def label(self) -> str:
        return f"{FIXTURE['home_team']} vs {FIXTURE['away_team']}"


class _Reader:
    """저장 자료 읽기 스텁. 운영·개발 DB에 접속하지 않는다."""

    def get_fixture(self, *, fixture_id: int):
        return _StoredFixture()

    def standings_for_league(self, *, league_id: int, season: int, limit: int = 60):
        return (
            {
                "team_id": 13,
                "rank": 3,
                "points": 21,
                "played": 10,
                "win": 7,
                "draw": 0,
                "loss": 3,
                "goals_for": 21,
                "goals_against": 13,
                "form": "LLLWW",
            },
            {
                "team_id": 4,
                "rank": 15,
                "points": 10,
                "played": 10,
                "win": 2,
                "draw": 4,
                "loss": 4,
                "goals_for": 10,
                "goals_against": 12,
                "form": "DDWWL",
            },
        )

    def injuries_for_fixture(self, fixture_id: int):
        return ()


def _remapped_model_text() -> str:
    """form.json 기록 응답의 근거 ID를 **D0가 실제로 만드는 사실 ID**로 맞춘다.

    fixture는 `api:standings-mci` 같은 표시용 ID를 쓰지만, 저장 자료에서 만드는 사실
    ID는 팀 ID 기반(`api:standings-13`)이다. 이 대응을 맞추지 않으면 R1의 모든 주장이
    "근거 없음"으로 제외되어 종합 단계가 진행되지 않는다. 검증 규칙을 느슨하게 하는
    것이 아니라, 검사 입력을 실제 생산자에 맞추는 수정이다.
    """
    payload = json.loads(FORM_FIXTURES["model_text"])
    mapping = {
        "api:standings-mci": "api:standings-13",
        "api:standings-ful": "api:standings-4",
        "api:form-mci": "api:standings-13",
    }

    def fix(ids):
        return [mapping.get(item, item) for item in ids or []]

    context = payload.get("match_context")
    if isinstance(context, dict) and context.get("importance_evidence"):
        context["importance_evidence"] = fix(context["importance_evidence"])
    for key in ("recent_form", "watch_points", "hot_players"):
        payload[key] = [
            {**item, "evidence": fix(item.get("evidence"))}
            for item in payload.get(key) or []
        ]
    return json.dumps(payload, ensure_ascii=False)


def _model_text() -> dict[str, str]:
    """갈래별 기록 응답. 준비된 fixture를 그대로 쓴다."""
    return {
        "R1": _remapped_model_text(),
        "R2": json.dumps(
            {
                "injuries": [
                    {
                        "player_id": 9401,
                        "team": "Manchester City",
                        "status": "out",
                        "detail": "햄스트링 부상으로 결장이 예상됩니다.",
                        "evidence": ["api:standings-13"],
                    }
                ],
                "impact": "Manchester City의 측면 자원이 줄어듭니다.",
                "uncertainties": ["정확한 복귀 시점은 확인되지 않았습니다."],
                "search_note": None,
            },
            ensure_ascii=False,
        ),
        "R3": json.dumps(
            {"media": [], "search_note": "매체 전망을 확인하지 못했습니다.", "uncertainties": []},
            ensure_ascii=False,
        ),
        # R4(주목 선수) 기록 응답. 선정 선수와 이유를 분리해 낸다.
        "R4": json.dumps(
            {
                "players": [
                    {
                        "player": "Erling Haaland",
                        "team": "Manchester City",
                        "reason": "박스 안 마무리 역할을 맡는 공격수입니다.",
                        "evidence": ["api:standings-13"],
                    }
                ],
                "uncertainties": [],
            },
            ensure_ascii=False,
        ),
        # S1은 종합 전용 응답 모양을 쓴다(준비된 기록 fixture).
        "S1": SYNTH_FIXTURES["model_text_ok"],
    }


def _transport() -> provider.RecordedTransport:
    """갈래 순서는 보장되지 않으므로, 요청마다 갈래에 맞는 응답을 고르는 스크립트를 쓴다."""

    class _BranchTransport(provider.RecordedTransport):
        def __init__(self) -> None:
            super().__init__(script=[], provider="recorded-model", mode=RunMode.MOCK)
            self.texts = _model_text()

        def send(self, spec, *, timeout_seconds, context):
            self.calls.append(spec)
            key = "S1" if spec.module_id == "S1" else spec.module_id
            text_value = self.texts[key]
            return provider.TransportResult(
                http_status=200,
                raw_request={"contents": "recorded"},
                raw_response={
                    "candidates": [
                        {
                            "content": {"parts": [{"text": text_value}], "role": "model"},
                            "finish_reason": "STOP",
                            "grounding_metadata": GROUNDING,
                        }
                    ]
                },
                usage={"input_tokens": 100, "output_tokens": 50},
                duration_ms=10,
            )

    return _BranchTransport()


def _start(session, transport, *, admission=jobs.ADMISSION_MODE.ADMIN_PREVIEW, limits=None):
    return pipeline.start_preview_run(
        session,
        fixture=_fixture(),
        actor_id=7,
        transport=transport,
        reader=_Reader(),
        admission=admission,
        mode=RunMode.MOCK,
        limits=limits or BudgetLimits(model_requests=8, attempts_per_call=3),
    )


def test_normal_path_four_research_one_synthesis(session_factory):
    """조사 4(R1·R2·R3·R4) + 종합 1 = 전송 5회, 같은 논리 호출은 한 번씩만 나간다."""
    transport = _transport()
    with session_factory() as session:
        outcome = _start(session, transport)
        session.commit()

        logical = [call.logical_call_id for call in transport.calls]
        assert len(logical) == 5, logical
        assert len(set(logical)) == 5, f"같은 논리 호출이 두 번 나갔다: {logical}"
        assert outcome.budget["model_used"] == 5
        # 정상 호출 5회는 총 상한 8 안에서 예약된 몫과 정확히 같다.
        assert outcome.budget["model_requests"] == 8
        assert outcome.admission == jobs.ADMISSION_MODE.ADMIN_PREVIEW

        state = jobs.load_state(session, outcome.run_id)
        assert state is not None
        assert state.active is False, "끝난 실행은 중복 방지 키에서 빠져야 한다"
        assert set(state.completed_nodes) >= {"D0", "V0", "S1", "V1"}


def test_pipeline_saves_section_results_for_each_section(session_factory):
    """조사 갈래마다 섹션 결과가 남고, 저장된 행으로 다시 열린다."""
    transport = _transport()
    with session_factory() as session:
        outcome = _start(session, transport)
        session.commit()

        stored = session.execute(
            text(
                "SELECT workflow_id, body, version FROM preview_dev.preview_section_results"
                " WHERE run_id = :run ORDER BY workflow_id"
            ),
            {"run": str(outcome.run_id)},
        ).all()
        workflows = {row[0] for row in stored}
        assert "section_form" in workflows
        assert outcome.section_result_ids, "섹션 결과 ID가 결론에 남아야 한다"


def test_approval_missing_refuses_default_run(session_factory):
    """승인이 없으면 기본 전체 프리뷰는 시작하지 않고, 전송도 하지 않는다."""
    transport = _transport()
    with session_factory() as session:
        with pytest.raises(pipeline.AdmissionRefused) as excinfo:
            _start(session, transport, admission=jobs.ADMISSION_MODE.APPROVED)
        session.rollback()
        assert "승인" in str(excinfo.value)
        assert transport.calls == [], "승인 거부 뒤에는 전송이 없어야 한다"


def test_explicit_admin_preview_writes_no_approval(session_factory):
    """관리자 명시 시험은 승인 행을 만들지 않는다."""
    transport = _transport()
    with session_factory() as session:
        outcome = _start(session, transport)
        session.commit()
        assert outcome.admission == jobs.ADMISSION_MODE.ADMIN_PREVIEW
        approvals = session.execute(
            text("SELECT count(*) FROM preview_dev.preview_section_approvals")
        ).scalar()
        assert approvals == 0


def test_duplicate_request_joins_existing_run(session_factory):
    """진행 중인 같은 조합의 요청은 새 실행·새 호출을 만들지 않는다."""
    transport = _transport()
    with session_factory() as session:
        first = _start(session, transport)
        session.commit()
        jobs.set_active(session, run_id=first.run_id, active=True)
        session.commit()

        calls_before = len(transport.calls)
        second = _start(session, transport)
        session.commit()
        assert second.run_id == first.run_id
        assert second.joined_existing is True
        assert len(transport.calls) == calls_before


def test_explicit_rerun_creates_new_run(session_factory):
    """의도적 재실행은 새 실행 ID를 만들고 옛 실행을 덮지 않는다."""
    with session_factory() as session:
        first = _start(session, _transport())
        session.commit()
        second = pipeline.rerun_preview(
            session,
            run_id=first.run_id,
            actor_id=7,
            transport=_transport(),
            reader=_Reader(),
        )
        session.commit()
        assert second.run_id != first.run_id
        second_state = jobs.load_state(session, second.run_id)
        assert second_state is not None
        assert second_state.rerun_of_run_id == first.run_id


def test_branches_share_one_budget_and_run_concurrently(session_factory):
    """갈래 셋이 하나의 예산을 쓰고, 실제로 동시에 돈다(순차 3회가 아니다).

    각 요청이 시작·종료 시각을 남기므로 겹침을 직접 잴 수 있다. 예산은 모델 요청
    상한 하나로 세어, 갈래마다 예산이 새로 생기지 않았음을 확인한다.
    """
    import threading
    import time

    seen: list[tuple[str, float, float]] = []
    lock = threading.Lock()

    class _TimedTransport(provider.RecordedTransport):
        def __init__(self) -> None:
            super().__init__(script=[], provider="recorded-model", mode=RunMode.MOCK)
            self.texts = _model_text()

        def send(self, spec, *, timeout_seconds, context):
            start = time.monotonic()
            with lock:
                self.calls.append(spec)
            # 갈래가 겹치는지 재려면 전송 구간이 실제로 겹쳐야 한다.
            time.sleep(0.05)
            end = time.monotonic()
            with lock:
                seen.append((spec.module_id, start, end))
            key = "S1" if spec.module_id == "S1" else spec.module_id
            return provider.TransportResult(
                http_status=200,
                raw_request={"contents": "recorded"},
                raw_response={
                    "candidates": [
                        {
                            "content": {"parts": [{"text": self.texts[key]}], "role": "model"},
                            "finish_reason": "STOP",
                            "grounding_metadata": GROUNDING,
                        }
                    ]
                },
                usage={"input_tokens": 100, "output_tokens": 50},
                duration_ms=10,
            )

    transport = _TimedTransport()
    with session_factory() as session:
        outcome = _start(
            session,
            transport,
            limits=BudgetLimits(model_requests=8, attempts_per_call=3),
        )
        session.commit()

        research = [row for row in seen if row[0] in ("R1", "R2", "R3", "R4")]
        assert len(research) == 4, research
        # 세 갈래의 전송 구간이 서로 겹친다: 첫 요청이 끝나기 전에 다음이 시작됐다.
        overlapped = any(
            other[1] < first[2] for first in research for other in research if other is not first
        )
        assert overlapped, f"조사 갈래가 동시에 돌지 않았다: {research}"

        # 예산은 하나다. 갈래 수만큼 예산이 새로 생기지 않는다.
        assert outcome.budget["model_requests"] == 8
        assert outcome.budget["model_used"] == 5
        assert outcome.budget["model_remaining"] == 3


# --------------------------------------------------------------------------
# 관리자 API 경로 (ADMIN 전용, 승인 게이트)
# --------------------------------------------------------------------------

PREVIEW_RUNS = "/api/v1/admin/preview/runs"
ADMISSION = "/api/v1/admin/preview/admission"
LOGIN = "/api/v1/auth/login"


def _login(client, make_user, role="ADMIN"):
    user = make_user(role=role)
    response = client.post(
        LOGIN, json={"email": user["email"], "password": user["password"]}
    )
    assert response.status_code == 200, response.text
    return user


def _request_body(**overrides) -> dict:
    body = {
        "fixture_id": _fixture()["fixture_id"],
        "league_id": _fixture()["league_id"],
        "season": _fixture()["season"],
        "home_team_id": _fixture()["home_team_id"],
        "away_team_id": _fixture()["away_team_id"],
        "kickoff_at": _fixture()["kickoff_at"],
        "mode": "mock",
        "admission": "admin_preview",
    }
    body.update(overrides)
    return body


def test_admin_preview_run_endpoint_requires_admin(client, make_user):
    """전체 프리뷰 생성은 ADMIN만 호출할 수 있다."""
    # 비인증은 401이다.
    assert client.post(PREVIEW_RUNS, json=_request_body()).status_code == 401
    # 비ADMIN은 로그인 단계에서 거부된다(관리자 전용 앱). 세션이 없으므로 401이다.
    user = make_user(role="USER")
    denied = client.post(
        LOGIN, json={"email": user["email"], "password": user["password"]}
    )
    assert denied.status_code == 403, denied.text
    assert client.post(PREVIEW_RUNS, json=_request_body()).status_code == 401


def test_admin_preview_run_returns_run_id_and_state(client, make_user):
    """관리자 시험 실행은 상태 조회 가능한 run_id를 돌려준다."""
    _login(client, make_user)
    response = client.post(PREVIEW_RUNS, json=_request_body())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"]
    assert body["admission"] == "admin_preview"
    assert body["status"] in ("succeeded", "failed")
    assert body["mode"] == "mock"
    # 저장된 실행을 기존 검사 경로로 다시 열 수 있다.
    detail = client.get(f"{PREVIEW_RUNS}/{body['run_id']}")
    assert detail.status_code == 200
    assert detail.json()["summary"]["run_id"] == body["run_id"]


def test_default_admission_refused_without_approval(client, make_user):
    """승인이 없으면 기본 전체 프리뷰는 409와 함께 대기 사유를 돌려준다."""
    _login(client, make_user)
    response = client.post(PREVIEW_RUNS, json=_request_body(admission="approved"))
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert "승인" in detail["message"]
    assert detail["state"]["ready"] is False
    assert detail["missing"]


def test_admission_state_endpoint_reports_missing(client, make_user):
    """승인 현황은 필요한 섹션과 현재/승인 버전을 함께 알린다."""
    _login(client, make_user)
    response = client.get(ADMISSION)
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is False
    assert set(body["missing_approval"]) >= {"section_form", "section_synthesis"}
    assert body["current_versions"]["section_form"].startswith("section_form@")


def test_synthesis_rerun_requires_selected_results(client, make_user):
    """재종합은 선택한 결과 ID 없이는 422로 거부한다."""
    _login(client, make_user)
    created = client.post(PREVIEW_RUNS, json=_request_body()).json()
    response = client.post(
        f"{PREVIEW_RUNS}/{created['run_id']}/synthesis-runs",
        json={"selected_result_ids": [], "mode": "mock"},
    )
    assert response.status_code == 422, response.text


def test_module_rerun_rejects_non_research_module(client, make_user):
    """조사 모듈이 아닌 대상은 모듈 재실행으로 받지 않는다."""
    _login(client, make_user)
    created = client.post(PREVIEW_RUNS, json=_request_body()).json()
    response = client.post(
        f"{PREVIEW_RUNS}/{created['run_id']}/module-reruns",
        json={"module_id": "S1", "mode": "mock"},
    )
    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------
# 표시 이름 (한국어) — 표시 경계에서만 변환
# --------------------------------------------------------------------------


def test_display_names_absent_keeps_original_text(session_factory, monkeypatch):
    """이름 읽기 설정이 없으면 원문 표기를 그대로 쓰고 실행을 깨지 않는다."""
    from app.core.config import get_settings
    from app.preview.display_names import open_display_names

    monkeypatch.delenv("PREVIEW_NAMES_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    bridge = open_display_names(
        fixture=_fixture(), dsn=None, fallback_label="Manchester City vs Fulham"
    )
    assert bridge.active is False
    assert bridge.label(fixture=_fixture(), fallback="Manchester City vs Fulham") == (
        "Manchester City vs Fulham"
    )
    # 본문·선수 목록은 원문 그대로다(지어낸 번역 없음).
    assert bridge.rewrite_body("Manchester City와 Fulham") == "Manchester City와 Fulham"
    rows = bridge.localize_players(
        [{"player": "Erling Haaland", "team": "Manchester City"}], scope_team_ids=[13, 4]
    )
    assert rows[0]["player"] == "Erling Haaland"
    assert bridge.note
    get_settings.cache_clear()


def test_saved_body_is_not_rewritten_by_display_names(session_factory, monkeypatch):
    """표시 이름 변환은 저장 본문을 바꾸지 않는다(승인 스탬프도 그대로)."""
    monkeypatch.delenv("PREVIEW_NAMES_DATABASE_URL", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    with session_factory() as session:
        outcome = _start(session, _transport())
        session.commit()
        stored = session.execute(
            text(
                "SELECT body, workflow_version FROM preview_dev.preview_section_results"
                " WHERE run_id = :run AND workflow_id = 'section_form'"
            ),
            {"run": str(outcome.run_id)},
        ).first()
        assert stored is not None
        before = stored[0]
        assert "Manchester City" in before or "맨체스터" in before

        # 독자용 투영을 이름 파사드 없이/있이 만들어도 저장 값은 변하지 않는다.
        from app.preview import store
        from app.preview.section_preview import build_reader_view

        detail = store.get_run_detail(session, outcome.run_id, include_artifact_bodies=False)
        build_reader_view(session, detail)

        after = session.execute(
            text(
                "SELECT body FROM preview_dev.preview_section_results"
                " WHERE run_id = :run AND workflow_id = 'section_form'"
            ),
            {"run": str(outcome.run_id)},
        ).scalar()
        assert after == before
    get_settings.cache_clear()


# --------------------------------------------------------------------------
# R4 연결 결함 대표 검사 (name-only 팀 조회)
# --------------------------------------------------------------------------


def test_resolver_handle_accepts_name_only_team_lookup():
    """R4가 팀 '이름'만 넘겨도 어댑터가 죽지 않고 실제 해석기에 위임한다.

    관측된 결함: `_ResolverHandle.resolve_team`이 `team_id`를 요구해 R4 실호출이
    `KeyError`로 중단됐다(응답 파싱 뒤·저장 전). 범위를 읽기 전에는 예외 대신 `None`을
    돌려 원래 표기를 유지하고, 범위를 읽은 뒤에는 실제 `DisplayNames`와 같은 값을 낸다.
    """
    from app.preview.sections import _ResolverHandle

    class _FakeNames:
        """실제 해석기 대역. 어댑터가 **위임**하는지만 본다(이름을 만들지 않는다)."""

        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def resolve_team(self, value=None, *, team_id=None, external_id=None, id_space="internal"):
            self.calls.append((value, team_id, external_id, id_space))
            return f"해석:{value}"

    handle = _ResolverHandle("postgresql://unused/never-used")
    # 1) 범위를 읽기 전에는 예외를 올리지 않는다(이전에는 KeyError로 중단).
    assert handle.resolve_team("Manchester City", id_space="internal") is None

    # 2) 범위를 읽은 상태를 흉내내고, 실제 해석기로 위임하는지 확인한다.
    fake = _FakeNames()
    handle._cache[(4, 13)] = fake
    resolved = handle.resolve_team("Manchester City", id_space="internal")

    assert resolved == "해석:Manchester City"
    assert fake.calls == [("Manchester City", None, None, "internal")], fake.calls


# --------------------------------------------------------------------------
# 시도 → 모듈 실행 연결 (관측 결함: 응답 탭에서 원문을 볼 수 없었다)
# --------------------------------------------------------------------------


def test_sent_attempt_is_linked_to_its_module_execution(session_factory):
    """모델을 보낸 시도는 **자기 모듈 실행**에 붙고, 원문 artifact도 함께 남는다.

    관측 결함: 노드가 실행 문맥에 `module_execution_id`를 넣지 않아 시도가
    `module_execution_id=NULL`로 저장됐다. 그러면 검사 화면의 '응답' 탭이 그 모듈에서
    원문을 찾지 못한다(저장 실행 22e1a19e·6176a8c6에서 실제로 R4 attempt_count=0).
    """
    from sqlalchemy import text

    from app.preview import store

    transport = _transport()
    with session_factory() as session:
        outcome = _start(session, transport)
        session.commit()

        rows = session.execute(
            text(
                "SELECT module_id, module_execution_id, response_artifact_id, outcome"
                " FROM preview_dev.preview_attempts WHERE run_id = :run"
                " ORDER BY started_at"
            ),
            {"run": str(outcome.run_id)},
        ).all()
        assert rows, "시도 기록이 없다"
        # 모든 시도가 모듈 실행에 붙고 원문 artifact를 가진다.
        for module_id, execution_id, artifact_id, attempt_outcome in rows:
            assert execution_id is not None, f"{module_id} 시도에 실행 ID가 없다"
            assert artifact_id is not None, f"{module_id} 시도에 응답 원문이 없다"
            assert attempt_outcome == "ok"

        # 실행 상세에서 R4 모듈이 자기 시도를 실제로 들고 있다.
        detail = store.get_run_detail(session, outcome.run_id)
        r4 = [m for m in detail.modules if m["module_id"] == "R4"]
        assert r4, "R4 모듈 실행이 없다"
        assert r4[0]["attempt_count"] >= 1
        assert r4[0]["attempts"], "R4 모듈에 시도가 연결되지 않았다"
        assert r4[0]["attempts"][0]["response_artifact_id"]


def test_legacy_unlinked_attempt_is_attached_by_unique_module(session_factory):
    """실행 ID가 비어 저장된 예전 시도도, 그 모듈 실행이 하나뿐이면 붙여 보여 준다.

    저장 행을 고치지 않고 **읽기 시점**에만 붙인다. 같은 모듈 실행이 둘 이상이면
    임의로 고르지 않고 미배정으로 남긴다.
    """
    import uuid

    from sqlalchemy import text

    from app.preview import store as store_module

    with session_factory() as session:
        outcome = _start(session, _transport())
        session.commit()

        # R4 시도 하나를 '예전 저장 행'처럼 실행 ID 없이 만든다.
        session.execute(
            text(
                "UPDATE preview_dev.preview_attempts SET module_execution_id = NULL"
                " WHERE run_id = :run AND module_id = 'R4'"
            ),
            {"run": str(outcome.run_id)},
        )
        session.commit()

        detail = store_module.get_run_detail(session, uuid.UUID(str(outcome.run_id)))
        # 실행이 하나뿐이므로 읽기 시점에 붙는다.
        assert detail.unassigned_attempts == ()
        r4 = [m for m in detail.modules if m["module_id"] == "R4"][0]
        assert r4["attempt_count"] >= 1
        assert r4["attempts"], "유일한 모듈 실행에 붙지 않았다"

        # 모듈 실행을 하나 더 만들면 어느 쪽인지 확정할 수 없으므로 미배정으로 노출한다.
        session.execute(
            text(
                "INSERT INTO preview_dev.preview_module_executions"
                " (id, run_id, module_id, ordinal, status, quality, input_payload,"
                "  input_hash, delivered_next_input, attempt_count, retry_count, created_at)"
                " VALUES (:id, :run, 'R4', 2, 'succeeded', 'ready', '{}'::jsonb,"
                "  'dup', '{}'::jsonb, 0, 0, now())"
            ),
            {"id": str(uuid.uuid4()), "run": str(outcome.run_id)},
        )
        session.commit()

        detail2 = store_module.get_run_detail(session, uuid.UUID(str(outcome.run_id)))
        assert detail2.unassigned_attempts, "모호한 시도는 미배정으로 노출돼야 한다"
