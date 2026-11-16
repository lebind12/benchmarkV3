"""MP-02 실행 기록 저장 구조.

모든 테이블은 `preview_dev` 스키마에만 만든다. 기존 `public` 영역은 읽기 전용이며
이 앱이 만들거나 바꾸지 않는다. 스키마를 생략한 쿼리에 의존하지 않는다
(`app/db.py`가 `search_path`도 `preview_dev`로 고정한다).

설계 메모:

- `preview_runs.environment`(dev/test/prod)와 `.mode`(live/replay/mock)는 서로
  다른 축이고, 자료 출처(`preview_source_snapshots.source_kind`, api/search)는
  또 다른 축이다. 재생·모의 실행을 live 성공으로 세지 않으려면 세 값을 분리해
  보관해야 한다.
- 결과는 덮어쓰지 않는다. 같은 모듈 실행에 새 결과를 저장하면 `version`이 하나
  올라간 행이 추가되고, 이전 행은 그대로 남는다.
- 원문 아티팩트는 비밀값을 제거한 본문과 요약을 함께 둔다. 보관 기간이 지나면
  본문만 지우고 요약·해시·기간은 남겨 "왜 못 여는지"를 보여준다.
- 실행 취소는 행을 지우되 실행 행과 감사 행은 남긴다. `cancelled_at`이 그 표시다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.preview.db import SCHEMA, Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_TABLE_ARGS = {"schema": SCHEMA}


class PreviewRun(Base):
    """실행 한 건. 목록·상세의 기준 행이다."""

    __tablename__ = "preview_runs"
    __table_args__ = _TABLE_ARGS

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    operation_kind: Mapped[str] = mapped_column(Text, nullable=False)
    environment: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    quality: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    config_version: Mapped[str] = mapped_column(Text, nullable=False)
    limits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    contract_versions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # 표시용 경기 정보. 동일성 키는 이 열들이 아니라 fixture_id 조합이다.
    fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    league_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    away_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    kickoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fixture_label: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 이 실행이 어떤 데이터를 소유하는지. 취소 시 지울 수 있는 범위의 근거다.
    write_scope: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="preview_dev"
    )
    label: Mapped[str | None] = mapped_column(Text, nullable=True)

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 실행 취소 감사 표시. 행을 지워도 이 값은 남는다.
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_by_actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PreviewModuleExecution(Base):
    """모듈 실행 한 건. 논리적 실행 단위이며 시도와 1:N이다."""

    __tablename__ = "preview_module_executions"
    __table_args__ = (
        UniqueConstraint("run_id", "module_id", "ordinal", name="uq_module_execution_ordinal"),
        _TABLE_ARGS,
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    module_id: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    quality: Mapped[str] = mapped_column(Text, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 모듈에 실제로 전달한 입력(ModuleInput)과 다음 단계로 넘긴 값.
    input_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    delivered_next_input: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PreviewAttempt(Base):
    """논리 호출의 실제 시도 한 건. 재시도를 한 행으로 뭉개지 않는다."""

    __tablename__ = "preview_attempts"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "logical_call_id", "attempt_ordinal", name="uq_attempt_ordinal"
        ),
        _TABLE_ARGS,
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    module_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_module_executions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    module_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    logical_call_id: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)

    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    request_spec: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    request_artifact_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    response_artifact_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    wait_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PreviewSourceSnapshot(Base):
    """자료 수집 한 건의 출처·시각·검증 상태."""

    __tablename__ = "preview_source_snapshots"
    __table_args__ = _TABLE_ARGS

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_attempts.id", ondelete="CASCADE"), nullable=True
    )
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fixture: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    catalog_query: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    validation_status: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class PreviewResult(Base):
    """모듈 결과 버전. 같은 모듈 실행의 이전 버전을 덮어쓰지 않는다."""

    __tablename__ = "preview_results"
    __table_args__ = (
        UniqueConstraint(
            "module_execution_id", "version", name="uq_result_version"
        ),
        _TABLE_ARGS,
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    module_execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_module_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    module_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    quality: Mapped[str] = mapped_column(Text, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    implementation_version: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    contract_version: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    supersedes_result_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class PreviewArtifact(Base):
    """비밀값을 제거한 원문·변환 결과 보관.

    `expires_at`이 지나면 `body`만 지우고 `summary`·해시·기간은 남긴다. 조회 화면은
    "만료됨"과 "읽기 실패"를 구분해 보여줘야 한다.
    """

    __tablename__ = "preview_artifacts"
    __table_args__ = _TABLE_ARGS

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_attempts.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    redacted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PreviewWriteAudit(Base):
    """개발 영역 쓰기·취소 감사 기록. 값이 아니라 무엇을 했는지만 남긴다."""

    __tablename__ = "preview_write_audit"
    __table_args__ = _TABLE_ARGS

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_table: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PreviewSectionApproval(Base):
    """섹션 워크플로우 버전 승인 기록.

    승인 단위는 프리뷰 섹션을 만드는 완결된 워크플로우다. 내부 노드나 D0 같은 자료
    준비 단계마다 따로 승인하지 않는다. 승인은 관리자가 섹션 본문 결과를 확인한 뒤
    만들며, 개발 워커가 만들지 않는다.

    이 표는 append-only다. 새 승인은 이전 승인을 `supersedes_approval_id`로 가리킬
    뿐 이전 행을 고치거나 지우지 않는다. 그래서 "언제 무엇을 어떤 실행 근거로
    승인했는지"가 나중에도 그대로 남는다. `active`는 섹션당 하나만 참이다.
    """

    __tablename__ = "preview_section_approvals"
    __table_args__ = _TABLE_ARGS

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    # 결과에 영향을 주는 축으로 계산한 섹션 워크플로우 버전.
    workflow_version: Mapped[str] = mapped_column(Text, nullable=False)
    version_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 구성 모듈/프롬프트/구현/계약 버전 집합. 승인 당시 값을 그대로 보존한다.
    constituents: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # 승인자가 확인한 실행과 섹션 결과.
    reviewed_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_runs.id", ondelete="SET NULL"), nullable=True
    )
    section_result_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    approved_by_actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    supersedes_approval_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class PreviewSectionResult(Base):
    """프리뷰 섹션 하나의 본문·근거 결과 버전.

    MP-04가 최소 저장 구조를 열었다. 승인 근거는 개별 노드·모듈 결과가 아니라 이
    행이다. 그래서 본문(`body`)과 근거(`sources`)를 먼저 담고, 노드별 원문·시도는
    `module_execution_ids`로 연결해 진단으로 펼친다.

    같은 실행·워크플로우에서 새 결과를 저장하면 `version`이 올라간 새 행이 생기고
    이전 행은 남는다. 승인은 확인한 버전을 그대로 가리키므로 나중 본문이 바뀌어도
    승인 근거가 흔들리지 않는다.

    `mode`가 mock/replay인 결과는 승인 근거로 쓰지 않는다. 화면과 API가 이 값을
    그대로 내보내므로 모의 결과가 실제 생성으로 읽히지 않는다.
    """

    __tablename__ = "preview_section_results"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "workflow_id", "version", name="uq_section_result_version"
        ),
        _TABLE_ARGS,
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    workflow_version: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # 독자용 근거. 출처 URL·매체·시각만 담고 내부 진단은 넣지 않는다.
    sources: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    mode: Mapped[str] = mapped_column(Text, nullable=False)
    environment: Mapped[str] = mapped_column(Text, nullable=False)
    quality: Mapped[str] = mapped_column(Text, nullable=False)

    # 이 섹션을 만든 노드·모듈 실행과 그 결과 버전. 진단 연결의 근거다.
    module_execution_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    result_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # 관리자 전용. 독자용 본문에는 넣지 않는다.
    diagnostics: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    output_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    contract_version: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    supersedes_section_result_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class PreviewPipelineRun(Base):
    """전체 프리뷰 실행의 작업 소유·진행 상태 (MP-10).

    `preview_runs`는 **무엇이 저장됐는지**의 기록이고, 이 표는 **누가 어디까지
    진행했는지**의 작업 상태다. 둘을 나누는 이유는 재개·중복 방지·오래된 실행자가
    최신 결과를 덮어쓰지 못하게 하는 판정이 결과 기록과 다른 수명을 갖기 때문이다.

    소유권은 `(owner_id, lease_expires_at)` 한 쌍이고, `fencing_token`은 소유권을
    넘길 때마다 증가한다. 저장 직전에 자기 토큰이 아직 최신인지 확인하므로, 멈춘
    실행자가 나중에 깨어나 새 실행자의 결과를 덮어쓸 수 없다. 외부 호출의 정확히
    한 번 실행을 보장하는 값이 아니다(그 보장은 하지 않는다).
    """

    __tablename__ = "preview_pipeline_runs"
    __table_args__ = (
        # 같은 경기·입력·버전 조합은 진행 중에 하나만 존재한다. 진행 중이 아닌 실행은
        # 이 키에서 빠지므로(부분 유니크) 의도적 재실행이 새 실행으로 남을 수 있다.
        Index(
            "uq_pipeline_active_dedup",
            "dedup_key",
            unique=True,
            postgresql_where=text("active"),
        ),
        _TABLE_ARGS,
    )

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_runs.id", ondelete="CASCADE"), primary_key=True
    )
    # 같은 경기·스냅샷·모델/프롬프트/구현 버전 조합. 진행 중 중복 요청을 합치는 키다.
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # 재개·재실행 계보. 원래 실행과 재실행을 구분해 남긴다.
    resume_of_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    rerun_of_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    # 이 실행이 승인된 버전으로 도는지, 관리자 명시적 시험인지.
    admission: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_versions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    selected_result_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # 진행 상태. `stage`는 마지막으로 끝난 단계이고 `pending_nodes`는 남은 단계다.
    stage: Mapped[str] = mapped_column(Text, nullable=False, server_default="created")
    pending_nodes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    completed_nodes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # 작업 소유권과 울타리. 만료된 임차는 다른 실행자가 가져갈 수 있다.
    owner_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fencing_token: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # 남은 예산은 실행 중 판단값이 아니라 **저장된 사실**이어야 재개가 이어진다.
    budget_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 왜 멈췄는지. 승인 대기와 실패를 같은 값으로 뭉개지 않는다.
    waiting_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


from app.preview.player_section_models import (  # noqa: E402, F401
    PreviewInjuryPlayerSection,
    PreviewPlayerNameCandidate,
    PreviewWatchPlayerSection,
)
