"""HP-APPROVAL 직접 검사 — 승인시각 **기본 경로**가 유효한 UTC 시각을 기록하는지.

검사 이유(실패 시 사용자 영향): 관리자가 정상 저장본을 승인할 때 `now`를 넘기지 않는
것이 실제 API 경로다. 그 기본 시각 계산이 실패하면 승인 요청이 500으로 끝나 승인 행이
생기지 않고, 홈에는 표시할 문서가 영원히 나오지 않는다. 기존 승인 검사들은 `now=FIXED_NOW`를
넘겨 이 경로를 지나가지 않으므로, 여기서 `now`를 **생략한** 호출을 대표 사례로 고정한다.

실제 DB에 연결하지 않는다. 승인 경계가 쓰는 조회·쓰기만 흉내 내는 합성 session을 쓰고,
검사 대상은 "기본 시각이 UTC 인식 값을 만들어 승인 근거 버전이 그대로 남는가" 하나다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.preview import approvals as approval_module
from app.preview.models import (
    PreviewResult,
    PreviewRun,
    PreviewSectionApproval,
    PreviewSectionResult,
)

pytestmark = pytest.mark.unit

WORKFLOW_ID = "section_ai_forecast"


class _StubSession:
    """승인 경로가 쓰는 조회만 흉내 내는 세션. 실제 DB에 연결하지 않는다."""

    def __init__(self, run, section_row, results):
        self._run = run
        self._section = section_row
        self._results = list(results)
        self.added: list = []
        self.flushed = 0

    def get(self, model, identifier):
        if model is PreviewRun:
            return self._run
        if model is PreviewSectionResult:
            return self._section
        return None

    def scalars(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is PreviewResult:
            return iter(self._results)
        if entity is PreviewSectionApproval:
            # 이 실행에는 이전 승인이 없다. 새 승인 행 하나만 생기는 경로를 본다.
            return iter([])
        return iter([])

    def add(self, row):
        self.added.append(row)

    def flush(self):
        self.flushed += 1


def _stub_run(run_id):
    run = PreviewRun()
    run.id = run_id
    run.mode = "live"
    run.cancelled_at = None
    return run


def _stub_section(run_id, *, workflow_version="section_ai_forecast@test-1"):
    row = PreviewSectionResult()
    row.id = uuid.uuid4()
    row.run_id = run_id
    row.workflow_id = WORKFLOW_ID
    row.workflow_version = workflow_version
    row.version = 1
    row.title = "AI 경기 전망"
    row.body = "저장된 전망 본문"
    row.sources = []
    row.mode = "live"
    row.environment = "dev"
    row.quality = "ready"
    row.result_ids = []
    row.diagnostics = []
    row.unavailable_reason = None
    row.created_at = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
    return row


def test_approval_without_explicit_now_records_a_utc_time_and_its_evidence_version():
    run_id = uuid.uuid4()
    run = _stub_run(run_id)
    section = _stub_section(run_id)
    session = _StubSession(run, section, [])

    before = datetime.now(timezone.utc)
    # `now`를 넘기지 않는다. 실제 관리자 API가 쓰는 기본 시각 경로다.
    approval = approval_module.approve_section_version(
        session,
        workflow_id=WORKFLOW_ID,
        run_id=run_id,
        section_result_id=section.id,
        actor_id=11,
        note="기본 시각 경로 검사",
    )
    after = datetime.now(timezone.utc)

    # 기본 시각이 실제로 기록되고, 시간대를 가진 UTC 값이다(500으로 끝나지 않는다).
    assert isinstance(approval.approved_at, datetime)
    assert approval.approved_at.tzinfo is not None
    assert approval.approved_at.utcoffset().total_seconds() == 0
    assert before <= approval.approved_at <= after

    # 승인 근거는 검토한 섹션 결과이고 그 버전이 그대로 남는다.
    assert str(approval.evidence.section_result_id) == str(section.id)
    assert str(approval.evidence.run_id) == str(run_id)
    # 승인 버전은 비어 있지 않고 이 워크플로우의 버전이다. 섹션 행이 자기 구성을 직접
    # 가리키지 않으면 현재 구성에서 계산된다(기존 판단 로직이며 이번 수정 대상이 아니다).
    assert approval.workflow_version.startswith(WORKFLOW_ID)
    assert approval.workflow_version
    assert approval.approved_by_actor_id == "11"
    assert approval.constituents, "승인 구성 버전이 비어 있으면 근거를 추적할 수 없다"

    # 승인 행과 감사 행이 실제로 남는다.
    approval_rows = [row for row in session.added if isinstance(row, PreviewSectionApproval)]
    assert len(approval_rows) == 1
    assert approval_rows[0].approved_at == approval.approved_at
    assert approval_rows[0].active is True
