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


def test_normal_path_three_research_one_synthesis(session_factory):
    """조사 3 + 종합 1 = 전송 4회, 같은 논리 호출은 한 번씩만 나간다."""
    transport = _transport()
    with session_factory() as session:
        outcome = _start(session, transport)
        session.commit()

        logical = [call.logical_call_id for call in transport.calls]
        assert len(logical) == 4, logical
        assert len(set(logical)) == 4, f"같은 논리 호출이 두 번 나갔다: {logical}"
        assert outcome.budget["model_used"] == 4
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

        research = [row for row in seen if row[0] in ("R1", "R2", "R3")]
        assert len(research) == 3, research
        # 세 갈래의 전송 구간이 서로 겹친다: 첫 요청이 끝나기 전에 다음이 시작됐다.
        overlapped = any(
            other[1] < first[2] for first in research for other in research if other is not first
        )
        assert overlapped, f"조사 갈래가 동시에 돌지 않았다: {research}"

        # 예산은 하나다. 갈래 수만큼 예산이 새로 생기지 않는다.
        assert outcome.budget["model_requests"] == 8
        assert outcome.budget["model_used"] == 4
        assert outcome.budget["model_remaining"] == 4


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
