"""HP-IMPL 직접 검사 — 홈 공개 저장 문서의 선택·투영 경계.

검사 이유(실패 시 사용자 영향):

- 최신 기준이 저장 시각이 아니면, 본문 없는 새 실행이 보이던 본문을 가려 홈이 빈
  화면이 된다.
- 구성본 선택을 무시하면 관리자가 저장한 조합 대신 섹션별 최신 본문이 섞여 나온다.
- 모의·미승인 결과를 게시하면 검증용 본문이 실제 홈 기사처럼 보인다.
- 문서 없음과 읽기 실패를 뭉개면 장애가 "생성 예정" 안내로 위장된다.

합성 입력만 쓰며 실제 DB에 연결하지 않는다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.preview.models import PreviewRun, PreviewSectionApproval, PreviewSectionResult
from app.preview.section_structured import structured_row_from_section_result
from app.services import home_preview_document as pinned

pytestmark = pytest.mark.unit

BASE = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
APPROVED = {
    "section_players": frozenset({"v1"}),
    "section_ai_forecast": frozenset({"v1"}),
}


def section(
    workflow_id: str,
    *,
    result_id: str,
    body: str,
    created: datetime = BASE,
    version: int = 1,
    mode: str = "live",
    workflow_version: str = "v1",
    run_id: str = "run-1",
) -> dict:
    return {
        "section_result_id": result_id,
        "run_id": run_id,
        "workflow_id": workflow_id,
        "workflow_version": workflow_version,
        "version": version,
        "title": f"{workflow_id} 제목",
        "body": body,
        "sources": [{"label": "출처", "url": "https://example.test/a"}],
        "quality": "ready",
        "mode": mode,
        "unavailable_reason": None,
        "created_at": created.isoformat(),
        "result_ids": [],
    }


def run(run_id: str, sections: list[dict], selected: list[str] | None = None) -> dict:
    return {
        "run_id": run_id,
        "sections": sections,
        "composition_result_ids": selected or [],
    }


def test_newest_saved_document_wins_by_saved_time_not_request_order():
    older = run("run-old", [section("section_players", result_id="a1", body="이전 본문")])
    newer = run(
        "run-new",
        [section("section_players", result_id="a2", body="새 본문", created=BASE + timedelta(hours=3))],
    )
    chosen = pinned.select_document([newer, older], APPROVED)
    assert chosen is not None
    assert chosen["run_id"] == "run-new"
    assert [row["section_result_id"] for row in chosen["rows"]] == ["a2"]


def test_run_without_body_never_shadows_previous_document():
    older = run("run-old", [section("section_players", result_id="a1", body="보이던 본문")])
    empty = run(
        "run-new",
        [section("section_players", result_id="a2", body="   ", created=BASE + timedelta(hours=5))],
    )
    chosen = pinned.select_document([empty, older], APPROVED)
    assert chosen is not None
    assert chosen["run_id"] == "run-old"
    assert chosen["rows"][0]["body"] == "보이던 본문"


def test_composition_choice_is_authoritative_over_newer_versions():
    rows = [
        section("section_players", result_id="a1", body="관리자가 고른 본문"),
        section("section_players", result_id="a9", body="나중 버전 본문", created=BASE + timedelta(hours=2), version=9),
    ]
    chosen = pinned.select_document([run("run-1", rows, ["a1"])], APPROVED)
    assert chosen is not None
    # 선택된 버전이 정본이다. 더 새 버전으로 바꿔 넣지 않는다.
    assert [row["section_result_id"] for row in chosen["rows"]] == ["a1"]


def test_unpublishable_composition_choice_is_dropped_not_replaced():
    """구성본이 고른 행이 표시 불가(빈 본문)면 그 섹션을 빼고 대신 다른 버전을 넣지 않는다.

    사용자 영향: 관리자가 구성본으로 저장한 버전 대신 같은 실행의 다른 버전 본문이 홈에
    나가면, 관리자에서 확인한 결과와 홈이 달라진다. 승인 여부는 더 이상 표시 조건이
    아니므로(2026-11-18 확정) 이 보호는 **빈 본문·모의·정본 불일치**에만 적용된다.
    """
    rows = [
        section("section_players", result_id="a1", body="정상 본문"),
        section("section_players", result_id="a2", body="   ", workflow_version="v2"),
    ]
    chosen = pinned.select_document([run("run-1", rows, ["a2"])], APPROVED)
    # 선택 행이 표시 불가면 문서에 표시 가능한 섹션이 남지 않는다.
    assert chosen is None
    # 다른 버전으로 대체하지 않는다(대체하면 관리자 조합과 다른 본문이 나간다).
    fallback = pinned.select_document([run("run-1", rows, ["a1"])], APPROVED)
    assert fallback is not None
    assert [row["section_result_id"] for row in fallback["rows"]] == ["a1"]


def test_mock_results_are_not_published_but_unapproved_live_results_are():
    """모의 실행은 게시하지 않고, 정상 live 본문은 승인 기록 없이도 게시한다.

    검사 이유(실패 시 사용자 영향): 승인은 번역·선수 연결 검수 상태이고 게시 허가가
    아니므로(2026-11-18 확정), 승인 행이 없다는 이유로 홈이 비면 사용자가 요청한
    "수집 → 생성 → 홈 즉시 확인" 경로가 끊긴다. 모의 본문 게시는 계속 막아야 한다.
    """
    mock = run(
        "run-mock",
        [section("section_players", result_id="m1", body="모의 본문", mode="mock")],
    )
    live = run(
        "run-v9",
        [section("section_players", result_id="u1", body="미승인 live 본문", workflow_version="v9")],
    )
    # 모의 실행만 있으면 게시할 것이 없다.
    assert pinned.select_document([mock], APPROVED) is None
    # 승인 기록이 전혀 없어도 정상 live 본문은 게시된다.
    assert pinned.select_document([live], {}) is not None
    chosen = pinned.select_document([live], {})
    assert [row["section_result_id"] for row in chosen["rows"]] == ["u1"]


def test_missing_document_reason_separates_absent_from_unapproved():
    no_runs = pinned.empty_document("no_stored_run", external_id=9)
    assert no_runs["status"] == "none"
    assert no_runs["sections"] == []
    assert no_runs["reason"] == "no_stored_run"
    assert pinned._reason_key([]) == "no_stored_run"
    # 본문은 있는데 승인만 없으면 '승인 없음'이다. '문서 없음'과 다른 사유다.
    assert (
        pinned._reason_key([run("run-1", [section("section_players", result_id="a1", body="본문")])])
        == "no_approved_version"
    )


def test_projection_carries_reader_fields_and_no_internal_diagnostics():
    rows = [
        section("section_players", result_id="a1", body="선정 선수: 가\n선정 이유: 나"),
    ]
    rows[0]["diagnostics"] = ["내부 진단"]
    rows[0]["module_execution_ids"] = ["internal-exec"]
    document = pinned.project_document(
        {"run_id": "run-1", "rows": rows, "saved_at": BASE.isoformat()},
        external_id=55,
        fixtures={"external_id": 55},
    )
    assert document["status"] == "available"
    assert document["reason"] is None
    assert document["fixture_id"] == 55
    assert document["saved_at"] == BASE.isoformat()
    assert document["sections"][0]["body"] == "선정 선수: 가\n선정 이유: 나"
    serialized = str(document)
    assert "내부 진단" not in serialized
    assert "internal-exec" not in serialized
    # 구조 값은 저장 본문에서만 읽고, 없는 표는 만들지 않는다.
    assert document["sections"][0]["structured"] is None


def test_partial_body_is_shown_instead_of_hidden_behind_a_new_threshold():
    rows = [section("section_players", result_id="a1", body="주목 선수 본문")]
    document = pinned.project_document(
        {"run_id": "run-1", "rows": rows, "saved_at": BASE.isoformat()},
        external_id=55,
    )
    # 승인 설계는 누락 섹션 개수 같은 새 품질 문턱을 금지한다. 필수 섹션이 빠져 있어도
    # 본문이 있으면 표시 가능이며, 화면은 없는 섹션의 빈 카드를 만들지 않는다.
    assert document["status"] == "available"
    assert [item["workflow_id"] for item in document["sections"]] == ["section_players"]
    assert document["sections"][0]["body"] == "주목 선수 본문"


class _StubSession:
    """`read_document`가 쓰는 조회만 흉내 내는 세션. 실제 DB에 연결하지 않는다."""

    def __init__(self, runs, sections_by_run, approvals=(), payloads=(), composition=None):
        self._runs = runs
        self._sections = sections_by_run
        self._approvals = list(approvals)
        self._payloads = list(payloads)
        self._composition = composition or {}
        self.info = {}

    def scalars(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is PreviewRun:
            return iter(self._runs)
        if entity is PreviewSectionApproval:
            return iter(self._approvals)
        return iter(self._sections.get("__all__", []))

    def get(self, model, identifier):
        for row in self._payloads:
            if getattr(row, "id", None) == identifier:
                return row
        return None


def _stub_run(run_id, fixture_id=90001, status="succeeded"):
    row = type("Run", (), {})()
    row.id = run_id
    row.fixture_id = fixture_id
    row.status = status
    return row


def _stub_section(section_id, run_id, workflow_id, body, created=BASE, workflow_version="v1"):
    row = type("Section", (), {})()
    row.id = section_id
    row.run_id = run_id
    row.workflow_id = workflow_id
    row.workflow_version = workflow_version
    row.version = 1
    row.title = f"{workflow_id} 제목"
    row.body = body
    row.sources = []
    row.quality = "ready"
    row.mode = "live"
    row.unavailable_reason = None
    row.created_at = created
    row.result_ids = []
    return row


def _stub_approval(workflow_id, version="v1"):
    row = type("Approval", (), {})()
    row.workflow_id = workflow_id
    row.workflow_version = version
    row.active = True
    return row



class _RunScopedSession(_StubSession):
    """실제 조회처럼 **실행별 섹션만** 돌려주는 대역.

    공용 `_StubSession`은 모든 섹션을 한꺼번에 주므로, 실행 간 선택을 비교하는
    검사에서는 실제 쿼리와 다르게 보인다. 이 검사들은 그 차이가 결과를 바꾸므로
    where 절의 run_id를 여기서 흉내 낸다.
    """

    def scalars(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is not PreviewSectionResult:
            return super().scalars(statement)
        wanted = None
        for key, value in statement.compile().params.items():
            if key.startswith("run_id"):
                wanted = value
                break
        rows = list(self._sections.get("__all__", []))
        if wanted is None:
            return iter(rows)
        return iter([row for row in rows if getattr(row, "run_id", None) == wanted])


def test_read_document_reports_no_stored_run_without_reading_sections():
    session = _StubSession([], {"__all__": []})
    result = pinned.read_document(session, 90001)
    assert result["status"] == "none"
    assert result["reason"] == "no_stored_run"
    assert result["sections"] == []


def test_read_document_returns_the_saved_body_from_stored_rows(monkeypatch):
    import uuid

    run_id = uuid.uuid4()
    players = _stub_section(uuid.uuid4(), run_id, "section_players", "저장된 선수 본문")
    approved = [_stub_approval("section_players")]
    session = _StubSession(
        [_stub_run(run_id)],
        {"__all__": [players]},
        approvals=approved,
    )
    monkeypatch.setattr(pinned.store_module, "load_composition", lambda *a, **k: {"available": False})
    result = pinned.read_document(session, 90001)
    assert result["status"] == "available"
    assert result["sections"][0]["body"] == "저장된 선수 본문"
    assert result["run_id"] == str(run_id)
    assert result["saved_at"] is not None


def test_read_document_publishes_a_live_run_with_no_approval_rows(monkeypatch):
    """승인 행이 하나도 없어도 정상 live 저장 문서는 홈에 게시된다.

    검사 이유(실패 시 사용자 영향): 승인은 번역 검수 상태이며 게시 허가가 아니다.
    승인 표가 비었다는 이유로 홈이 "표시 불가"가 되면 수집 직후 결과를 볼 수 없다.
    """
    import uuid

    run_id = uuid.uuid4()
    players = _stub_section(uuid.uuid4(), run_id, "section_players", "승인 없는 live 본문")
    session = _StubSession([_stub_run(run_id)], {"__all__": [players]}, approvals=[])
    monkeypatch.setattr(pinned.store_module, "load_composition", lambda *a, **k: {"available": False})
    result = pinned.read_document(session, 90001)
    assert result["status"] == "available"
    assert result["sections"][0]["body"] == "승인 없는 live 본문"
    assert result["run_id"] == str(run_id)


def test_projection_drops_internal_primary_keys_from_structured_values():
    rows = [section("section_players", result_id="a1", body="선정 선수: 홀란드\n선정 이유: 6골")]
    # `read_document`가 확인 경계를 거쳐 만드는 구조 값과 같은 모양을 넣는다.
    rows[0]["structured"] = {
        "structured_version": "mp11-structured-2",
        "workflow_id": "section_players",
        "players": [
            {
                "player": "홀란드",
                "reason": "6골",
                "team": "맨시티",
                "player_id": 533,
                "team_id": 13,
                "external_player_id": 1100,
                "photo_url": "https://media.api-sports.io/football/players/1100.png",
            }
        ],
        "injuries": [],
        "media": [],
        "odds": [],
        "forecast": None,
    }
    document = pinned.project_document(
        {"run_id": "run-1", "rows": rows, "saved_at": BASE.isoformat()},
        external_id=55,
    )
    structured = document["sections"][0]["structured"]
    # 확인된 외부 ID와 서버가 준 사진 주소는 남는다.
    assert structured["players"][0]["external_player_id"] == 1100
    assert structured["players"][0]["photo_url"].endswith("/1100.png")
    # 내부 기본키는 공개 계약에 넣지 않는다.
    assert "player_id" not in structured["players"][0]
    assert "team_id" not in structured["players"][0]


def test_absence_boundary_uses_fixed_clock_and_never_touches_system_time():
    """6시간/킥오프 경계를 고정 시각으로 확인한다.

    사용자 영향: 경계가 틀어지면 생성 시점이 지난 경기에 기본 안내가 나오거나, 아직
    여유 있는 경기에 문제 안내가 나와 사용자가 잘못된 상태를 확인한다.
    """
    now = datetime(2026, 11, 13, 0, 0, tzinfo=timezone.utc)
    cases = {
        "6시간 남음": (now + timedelta(hours=6), "upcoming_overdue"),
        "6시간 1초 남음": (now + timedelta(hours=6, seconds=1), "upcoming"),
        "1분 남음": (now + timedelta(minutes=1), "upcoming_overdue"),
        "정확히 킥오프": (now, "past"),
        "1시간 지남": (now - timedelta(hours=1), "past"),
    }
    for label, (kickoff, expected) in cases.items():
        assert pinned.absence_notice(kickoff, now=now)["state"] == expected, label


def test_absent_document_carries_absence_state_without_a_body():
    now = datetime(2026, 11, 13, 0, 0, tzinfo=timezone.utc)
    due = pinned.empty_document(
        "no_stored_run",
        external_id=7,
        fixtures={"external_id": 7, "kickoff_at": (now + timedelta(hours=2)).isoformat()},
        now=now,
    )
    assert due["status"] == "none"
    assert due["absence"]["state"] == "upcoming_overdue"
    assert due["sections"] == []
    far = pinned.empty_document(
        "no_stored_run",
        external_id=7,
        fixtures={"external_id": 7, "kickoff_at": (now + timedelta(days=3)).isoformat()},
        now=now,
    )
    assert far["absence"]["state"] == "upcoming"


# --------------------------------------------------------------------------
# HP-EVIDENCE: 활성 승인이 정확히 가리키는 섹션 결과
# --------------------------------------------------------------------------


def test_approval_pointing_at_an_exact_result_is_displayed_despite_version_drift():
    """사용자가 명시 승인한 저장 섹션이 홈에서 빠지지 않는다.

    검사 이유(실패 시 사용자 영향): 승인 서비스가 계산한 구성 버전과 저장 행의 버전
    스탬프가 다르면, 사용자가 승인한 5섹션 중 4섹션이 홈에서 사라진다(실제 관측:
    available 응답에 section_odds 1건만 남음). 승인 행은 검토한 실행·섹션 결과를
    정확히 가리키므로, 그 근거가 일치하면 버전 문자열이 달라도 표시해야 한다.
    """
    run_id = "run-approved-1"
    # 저장 행의 스탬프와 승인 행의 버전이 서로 다르다(실제 관측 상태와 같은 모양).
    approved_row = section(
        "section_ai_forecast",
        result_id="81b710b7-7c97-4235-a550-0654df51a269",
        body="사용자가 승인한 전망 본문",
        workflow_version="section_ai_forecast@8d4f5288197089fe",
        run_id=run_id,
    )
    # 같은 워크플로우의 다른 결과. 승인 근거가 아니다.
    other_row = section(
        "section_ai_forecast",
        result_id="unapproved-result",
        body="승인되지 않은 다른 본문",
        workflow_version="section_ai_forecast@9999",
        run_id=run_id,
        created=BASE + timedelta(hours=4),
        version=4,
    )
    mock_row = section(
        "section_players",
        result_id="mock-result",
        body="모의 본문",
        mode="mock",
        run_id=run_id,
    )
    inactive_row = section(
        "section_odds",
        result_id="inactive-result",
        body="비활성 승인 본문",
        workflow_version="section_odds@inactive",
        run_id=run_id,
    )

    rows = [approved_row, other_row, mock_row, inactive_row]
    # 승인 표: 버전 문자열은 저장 행과 맞지 않는다.
    approvals = [
        {
            "workflow_id": "section_ai_forecast",
            "workflow_version": "section_ai_forecast@c186f27356d4bb80",
            "reviewed_run_id": run_id,
            "section_result_id": "81b710b7-7c97-4235-a550-0654df51a269",
            "active": True,
        },
        {
            "workflow_id": "section_odds",
            "workflow_version": "section_odds@inactive",
            "reviewed_run_id": run_id,
            "section_result_id": "inactive-result",
            "active": False,
        },
    ]
    approved = pinned.approved_versions(approvals)
    evidence = pinned.approved_evidence(approvals)

    # 비활성 승인은 근거 표에도, 버전 표에도 들어가지 않는다.
    assert ("section_odds", run_id, "inactive-result") not in evidence
    assert approved.get("section_odds") is None

    chosen = pinned.select_document(
        [run(run_id, rows)], approved, evidence
    )
    assert chosen is not None
    shown = [row["section_result_id"] for row in chosen["rows"]]

    # 승인 표와 무관하게 워크플로우당 최신 버전이 표시된다(게시는 승인에 의존하지 않는다).
    assert "unapproved-result" in shown
    assert "81b710b7-7c97-4235-a550-0654df51a269" not in shown
    # 모의 본문은 승인 여부와 무관하게 계속 제외된다.
    assert "mock-result" not in shown
    # 비활성 승인도 게시 조건이 아니므로 일반 행으로 표시된다.
    assert "inactive-result" in shown


# --------------------------------------------------------------------------
# HP-PHOTO: 내부 ID → 외부 ID 확인 경계(사진·팀 로고)
# --------------------------------------------------------------------------


class _Resolver:
    """`StructuredIdContext`가 요구하는 해석기 대역. 계약의 이름·인자만 흉내 낸다."""

    def __init__(self):
        self.player_calls: list[int] = []
        self.team_calls: list[int] = []
        self.name_calls: list[tuple[str, tuple[int, ...]]] = []

    def resolve_player(self, name="", *, player_id=None, id_is_hint=True, team_hint=None, scope_team_ids=None):
        if player_id is not None:
            self.player_calls.append(player_id)
            # 내부 533 → 외부 1100. 확인된 값만 돌려준다.
            if player_id == 533:
                return type("R", (), {"player": type("P", (), {"external_id": 1100, "player_id": 533})()})()
            return None
        # 이름으로 확인하는 경로. 이 경기 두 팀 범위만 후보로 본다.
        self.name_calls.append((name, tuple(scope_team_ids or ())))
        if name == "홀란드":
            return type(
                "R",
                (),
                {
                    "player": type(
                        "P",
                        (),
                        {"player_id": 533, "external_id": 1100, "display_name": "홀란드", "team_display_name": "맨체스터 시티"},
                    )()
                },
            )()
        return None

    def resolve_team(self, value=None, *, team_id=None, external_id=None, id_space="internal"):
        if team_id is not None:
            self.team_calls.append(team_id)
            if team_id == 13:
                return type("T", (), {"team_id": 13, "external_id": 50, "display_name": "맨체스터 시티"})()
            return None
        if value == "맨체스터 시티":
            return type("T", (), {"team_id": 13, "external_id": 50, "display_name": "맨체스터 시티"})()
        return None


class _Bridge:
    """표시 이름 파사드 대역. 해석기는 `names`에 들어 있다(실제 구조와 같다)."""

    def __init__(self, names):
        self.names = names
        self.active = names is not None
        self.closed = False

    def close(self):
        self.closed = True


def test_photo_and_logo_ids_survive_when_the_resolver_is_connected(monkeypatch):
    """확인된 선수·부상 사진과 팀 외부 ID가 공개 투영까지 보존된다.

    검사 이유(실패 시 사용자 영향): 홈에서 주목 선수·부상 선수의 사진이 모두 빠지고
    팀 로고도 일부만 남는다. 사진 주소는 확인된 외부 ID에서만 만들어지므로, 해석기 연결이
    어긋나면 사용자는 '사진 없음'만 본다.
    """
    from app.services import home_preview_document as doc

    resolver = _Resolver()
    bridge = _Bridge(resolver)

    # 실행 행: 이 경기의 두 팀 내부 ID가 팀 범위가 된다.
    run = type("Run", (), {})()
    run.id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    run.home_team_id = 13
    run.away_team_id = 36
    run.fixture_label = "맨체스터 시티 대 풀럼"

    # `_id_context`는 함수 안에서 해석기 팩토리를 import한다. 그 실제 경계를 바꿔 끼운다
    # (DB·설정을 열지 않고, 연결 결과만 대역으로 대체한다).
    import app.preview.display_names as display_names

    monkeypatch.setattr(
        display_names, "open_display_names", lambda **_kwargs: bridge
    )
    id_context, returned_bridge = doc._id_context(None, run)

    assert id_context is not None, "해석기가 연결되어야 한다"
    assert returned_bridge is bridge

    # 저장 payload: 내부 ID가 있는 선수 1명과, 이름만 있는 부상 1명.
    payload = {
        "players": [{"player": "홀란드", "reason": "최근 5경기 6골", "player_id": 533, "team_id": 13}],
        "injuries": [{"player": "홀란드", "team": "맨체스터 시티", "status": "out", "summary": "부상"}],
    }
    row = {
        "section_result_id": "s-photo",
        "run_id": str(run.id),
        "workflow_id": "section_players",
        "workflow_version": "v1",
        "version": 1,
        "title": "주목 선수",
        "body": "선정 선수: 홀란드\n선정 이유: 최근 5경기 6골",
        "sources": [],
        "quality": "ready",
        "mode": "live",
        "unavailable_reason": None,
        "created_at": BASE.isoformat(),
        "result_ids": [],
    }
    structured = doc._public_row(
        {
            **row,
            **structured_row_from_section_result(row, payload=payload, id_context=id_context),
        }
    )["structured"]

    player = structured["players"][0]
    # 확인된 외부 ID → 서버가 만든 사진 주소가 살아 있다.
    assert player["external_player_id"] == 1100
    assert player["photo_url"] == "https://media.api-sports.io/football/players/1100.png"
    assert player["team_external_id"] == 50
    # 내부 기본키는 여전히 공개하지 않는다.
    assert "player_id" not in player
    assert "team_id" not in player

    injury = structured["injuries"][0]
    assert injury["external_player_id"] == 1100
    assert injury["photo_url"] == "https://media.api-sports.io/football/players/1100.png"
    # 이름만 있는 부상은 이 경기 두 팀 범위에서만 확인한다.
    assert resolver.name_calls and all(scope == (13, 36) for _name, scope in resolver.name_calls)


def test_missing_players_section_never_reports_complete_true():
    """필수 선수 섹션(`section_players`)이 없으면 complete=False여야 한다.

    검사 이유(실패 시 사용자 영향): outlook/odds/ai_forecast 3섹션만 있어도 complete=true로
    내려보내면 소비자가 선수 섹션까지 모두 완료된 프리뷰로 오인한다(1557474 실측 사례).
    """
    rows = [
        section("section_outlook", result_id="r-outlook", body="전망 요약", run_id="4f90e50b-ce55-4beb-8a17-20ef6e9192fb"),
        section("section_odds", result_id="r-odds", body="배당 요약", run_id="4f90e50b-ce55-4beb-8a17-20ef6e9192fb"),
        section("section_ai_forecast", result_id="r-forecast", body="AI 전망 본문", run_id="4f90e50b-ce55-4beb-8a17-20ef6e9192fb"),
    ]
    document = pinned.project_document(
        {
            "run_id": "4f90e50b-ce55-4beb-8a17-20ef6e9192fb",
            "rows": rows,
            "saved_at": BASE.isoformat(),
        },
        external_id=1557474,
    )
    assert document["status"] == "available"
    assert [item["workflow_id"] for item in document["sections"]] == [
        "section_outlook",
        "section_odds",
        "section_ai_forecast",
    ]
    assert document["complete"] is False


def test_failed_run_never_replaces_the_previous_healthy_document(monkeypatch):
    """필수 섹션을 만들지 못한 failed 실행은 공개 후보에서 빠진다.

    사용자 영향: 수집 뒤 자동 생성이 실패하면 그 실행이 이전 정상 문서를 덮어 홈이
    `complete=false`로 조용히 빈약해진다(2026-11-18 CE-E2E에서 실제 관측).
    """
    healthy_run = uuid.uuid4()
    failed_run = uuid.uuid4()
    healthy = _stub_section(uuid.uuid4(), healthy_run, "section_players", "이전 정상 본문")
    failed = _stub_section(
        uuid.uuid4(), failed_run, "section_players", "실패 실행 본문",
        created=BASE + timedelta(hours=3),
    )
    session = _RunScopedSession(
        [_stub_run(failed_run, status="failed"), _stub_run(healthy_run)],
        {"__all__": [failed, healthy]},
        approvals=[_stub_approval("section_players")],
    )
    monkeypatch.setattr(
        pinned.store_module, "load_composition", lambda *a, **k: {"available": False}
    )
    result = pinned.read_document(session, 90001)
    assert result["status"] == "available"
    assert result["run_id"] == str(healthy_run)
    assert result["sections"][0]["body"] == "이전 정상 본문"


def test_newer_successful_run_still_wins_over_older_one(monkeypatch):
    """성공한 새 실행은 지금처럼 이전 문서를 대체한다(부분 표시 정책 유지)."""
    old_run = uuid.uuid4()
    new_run = uuid.uuid4()
    old = _stub_section(uuid.uuid4(), old_run, "section_players", "오래된 본문")
    new = _stub_section(
        uuid.uuid4(), new_run, "section_players", "새 정상 본문",
        created=BASE + timedelta(hours=3),
    )
    session = _RunScopedSession(
        [_stub_run(new_run), _stub_run(old_run)],
        {"__all__": [new, old]},
        approvals=[_stub_approval("section_players")],
    )
    monkeypatch.setattr(
        pinned.store_module, "load_composition", lambda *a, **k: {"available": False}
    )
    result = pinned.read_document(session, 90001)
    assert result["status"] == "available"
    assert result["run_id"] == str(new_run)
    assert result["sections"][0]["body"] == "새 정상 본문"
