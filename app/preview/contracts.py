"""MP-02 공통 데이터 계약.

이 파일은 이후 MP-03/04/05/06/07/08/09/10이 같은 이름과 필드로 붙는 고정
계약이다. 필드를 바꾸려면 의존 작업과 변경 이유를 먼저 조정자에게 보고한다.

설계 원칙:

- 실행 방식(`mode`: live/replay/mock)과 자료 출처(`source_kind`: api/search)는
  서로 다른 축이다. 재생을 live 성공으로 계산하지 않는다.
- 실행 성공(`RunStatus.succeeded`)과 근거 확보(`QualityStatus`)는 독립이다.
- 내부 진단·누락·오류는 `ModuleResult`에 남기고 `PreviewDocument`에는 넣지 않는다.
- 비밀값은 계약에 값으로 담지 않는다. `RequestSpec.secret_refs`는 이름만 갖는다.
- 모르는 값은 `None`으로 둔다. 0이나 빈 문자열로 채우지 않는다.

직렬화는 JSONB 열에 그대로 넣을 수 있는 기본형만 쓴다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

# 계약 버전은 기록·검사·비교의 기준이다. 값이 바뀌면 기존 기록과 비교할 때
# 버전 차이를 표시해야 한다.
CONTRACT_VERSION = "mp02-1"
PROVIDER_CONTRACT_VERSION = "mp02-provider-1"
MODULE_INPUT_VERSION = "mp02-module-input-1"
PREVIEW_DOCUMENT_VERSION = "mp02-preview-1"
INSPECTOR_VERSION = "mp02-inspector-1"
APPROVAL_CONTRACT_VERSION = "mp02-approval-1"

# §5 초기 보관 설정. 개발 기본값이며 운영 정책은 배포 전에 다시 확인한다.
RAW_ARTIFACT_RETENTION_DAYS = 30
STRUCTURED_RECORD_RETENTION_DAYS = 180

# 승인 판정에 쓰는 버전 축. 이 중 하나라도 바뀌면 결과 의미가 바뀐 변경으로 본다.
APPROVAL_VERSION_AXES = (
    "prompt_version",
    "implementation_version",
    "contract_version",
    "output_contract_version",
)
APPROVAL_SCOPE_NOTE = (
    "승인 단위는 프리뷰 섹션을 만드는 완결된 워크플로우다. 내부 노드나 D0 같은 자료"
    " 준비 단계마다 따로 승인하지 않는다."
)


class ContractError(ValueError):
    """계약 위반. 호출자가 저장 전에 거부해야 하는 상태다."""


def contract_versions() -> dict[str, str]:
    """후속 워커에게 넘기는 계약 버전 목록."""
    return {
        "contract": CONTRACT_VERSION,
        "provider": PROVIDER_CONTRACT_VERSION,
        "module_input": MODULE_INPUT_VERSION,
        "preview_document": PREVIEW_DOCUMENT_VERSION,
        "inspector": INSPECTOR_VERSION,
        "approvals": APPROVAL_CONTRACT_VERSION,
    }


# --------------------------------------------------------------------------
# 열거형
# --------------------------------------------------------------------------


class OperationKind(str, Enum):
    """실행의 업무 목적. 단독 모듈 실행과 전체 실행이 같은 문맥을 쓴다."""

    PREVIEW = "preview"
    MODULE = "module"
    FIXTURE_CATALOG = "fixture_catalog"
    MOCK_DEMO = "mock_demo"


class Environment(str, Enum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class RunMode(str, Enum):
    """실행 방식. live만 외부 호출이 있었다는 뜻이다."""

    LIVE = "live"
    REPLAY = "replay"
    MOCK = "mock"


class SourceKind(str, Enum):
    """자료 출처. 실행 방식과 별개 축이다."""

    API = "api"
    SEARCH = "search"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    # 개발 실행 취소의 감사 표시. 삭제된 실행도 이 상태로 목록에 남는다.
    CANCELLED = "cancelled"


TERMINAL_RUN_STATUSES = frozenset(
    {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}
)


class QualityStatus(str, Enum):
    """프리뷰 품질 상태. 자료를 모두 확보했다는 뜻이 아니다."""

    PENDING = "pending"
    READY = "ready"
    INSUFFICIENT = "insufficient"


class FailureCode(str, Enum):
    DEADLINE_EXCEEDED = "deadline_exceeded"
    CONFIGURATION_ERROR = "configuration_error"
    INVALID_OUTPUT = "invalid_output"
    UNKNOWN_OUTCOME = "unknown_outcome"
    PROVIDER_ERROR = "provider_error"
    CANCELLED = "cancelled"


class ModuleStatus(str, Enum):
    """모듈 실행 상태. 실행 목록의 RunStatus와 같은 어휘를 쓴다."""

    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ClaimKind(str, Enum):
    FACT = "fact"
    EXTERNAL_FORECAST = "external_forecast"
    API_PREDICTION = "api_prediction"
    AI_INTERPRETATION = "ai_interpretation"


class ClaimDecision(str, Enum):
    ADOPTED = "adopted"
    EXCLUDED = "excluded"
    CONFLICT = "conflict"


class CoverageState(str, Enum):
    """자료 종류별 확보 상태. 빈 응답을 '없음'으로 단정하지 않기 위한 구분."""

    AVAILABLE = "available"
    SEARCH_NOT_FOUND = "search_not_found"
    API_NOT_PROVIDED = "api_not_provided"
    NOT_RUN = "not_run"
    CALL_ERROR = "call_error"
    VALIDATION_REJECTED = "validation_rejected"
    SOURCE_CONFLICT = "source_conflict"
    UNKNOWN = "unknown"


class ValidationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CONFLICT = "conflict"
    REJECTED = "rejected"


class ArtifactKind(str, Enum):
    RAW_REQUEST = "raw_request"
    RAW_RESPONSE = "raw_response"
    NORMALIZED_TRANSFORM = "normalized_transform"


class AttemptOutcome(str, Enum):
    OK = "ok"
    ERROR = "error"
    # 요청을 보냈지만 응답을 보존하기 전에 중단된 경우. 성공으로 세지 않는다.
    UNKNOWN = "unknown"


# --------------------------------------------------------------------------
# 직렬화 도우미
# --------------------------------------------------------------------------


def _plain(value: Any) -> Any:
    """JSONB에 넣을 수 있는 기본형으로 바꾼다."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _enum(enum_type, value):
    if value is None:
        return None
    if isinstance(value, enum_type):
        return value
    return enum_type(value)


# --------------------------------------------------------------------------
# 경기 식별과 실행 문맥
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FixtureIdentity:
    """경기 동일성 키. 경기명은 표시용이며 동일성 판단에 쓰지 않는다."""

    fixture_id: int  # API-Football 외부 경기 ID
    league_id: int
    season: int
    home_team_id: int
    away_team_id: int
    kickoff_at: datetime  # UTC

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FixtureIdentity":
        return cls(
            fixture_id=int(data["fixture_id"]),
            league_id=int(data["league_id"]),
            season=int(data["season"]),
            home_team_id=int(data["home_team_id"]),
            away_team_id=int(data["away_team_id"]),
            kickoff_at=_dt(data["kickoff_at"]),  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class FixtureCatalogQuery:
    """경기 선택 전 목록 수집 조건. 아직 한 경기의 식별자를 요구하지 않는다."""

    league_id: int
    date: str  # YYYY-MM-DD
    timezone: str

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


@dataclass(frozen=True)
class ExecutionLimits:
    """실행 예산 상한. 값을 모르는 항목은 `None`으로 두고 성공을 꾸미지 않는다."""

    model_requests: int | None = None
    api_requests: int | None = None
    attempts_per_call: int | None = None
    deadline_seconds: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


@dataclass(frozen=True)
class ExecutionContext:
    """모든 실행·시도의 공통 문맥. 단독 모듈 실행과 전체 실행이 같은 모양이다."""

    run_id: uuid.UUID
    operation_kind: OperationKind
    environment: Environment
    mode: RunMode
    actor_id: int
    config_version: str
    limits: ExecutionLimits = field(default_factory=ExecutionLimits)
    module_execution_id: uuid.UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionContext":
        return cls(
            run_id=_uuid(data["run_id"]),  # type: ignore[arg-type]
            operation_kind=_enum(OperationKind, data["operation_kind"]),
            environment=_enum(Environment, data["environment"]),
            mode=_enum(RunMode, data["mode"]),
            actor_id=int(data["actor_id"]),
            config_version=str(data["config_version"]),
            limits=ExecutionLimits(
                **{k: v for k, v in (data.get("limits") or {}).items() if v is not None}
            ),
            module_execution_id=_uuid(data.get("module_execution_id")),
        )


# --------------------------------------------------------------------------
# 자료와 근거
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceSnapshot:
    """한 번 수집한 자료 묶음의 출처·시각·검증 상태."""

    snapshot_id: uuid.UUID
    source_kind: SourceKind
    provider: str
    collected_at: datetime
    provider_updated_at: datetime | None
    fixture: FixtureIdentity | None
    catalog_query: FixtureCatalogQuery | None
    artifact_id: uuid.UUID | None
    validation_status: ValidationStatus
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


@dataclass(frozen=True)
class EvidenceClaim:
    """근거가 붙은 한 문장. 해석과 사실을 같은 종류로 합치지 않는다."""

    claim_id: str
    kind: ClaimKind
    text: str
    snapshot_ids: tuple[uuid.UUID, ...] = ()
    decision: ClaimDecision = ClaimDecision.ADOPTED
    decision_reason: str | None = None
    subject_team_id: int | None = None
    subject_player_id: int | None = None
    claimed_at: datetime | None = None
    source_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceClaim":
        return cls(
            claim_id=str(data["claim_id"]),
            kind=_enum(ClaimKind, data["kind"]),
            text=str(data["text"]),
            snapshot_ids=tuple(_uuid(s) for s in data.get("snapshot_ids") or ()),
            decision=_enum(ClaimDecision, data.get("decision", ClaimDecision.ADOPTED)),
            decision_reason=data.get("decision_reason"),
            subject_team_id=data.get("subject_team_id"),
            subject_player_id=data.get("subject_player_id"),
            claimed_at=_dt(data.get("claimed_at")),
            source_url=data.get("source_url"),
        )


@dataclass(frozen=True)
class CoverageEntry:
    """자료 종류별 확보 상태와 사유."""

    topic: str
    state: CoverageState
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


# --------------------------------------------------------------------------
# 모듈 입출력
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DeliveredValue:
    """다음 단계에 실제로 전달한 값. 요약본이 아니라 전달값을 그대로 둔다."""

    key: str
    value: Any

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


@dataclass(frozen=True)
class ModuleInput:
    """한 모듈 실행에 들어간 입력. 실제 전달값도 따로 보관한다."""

    module_id: str
    fixture: FixtureIdentity | None
    snapshot_ids: tuple[uuid.UUID, ...]
    selected_result_ids: tuple[uuid.UUID, ...]
    input_hash: str
    prompt_version: str
    contract_version: str
    implementation_version: str
    delivered: tuple[DeliveredValue, ...] = ()
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ModuleInput":
        return cls(
            module_id=str(data["module_id"]),
            fixture=(
                FixtureIdentity.from_dict(data["fixture"]) if data.get("fixture") else None
            ),
            snapshot_ids=tuple(_uuid(s) for s in data.get("snapshot_ids") or ()),
            selected_result_ids=tuple(
                _uuid(s) for s in data.get("selected_result_ids") or ()
            ),
            input_hash=str(data["input_hash"]),
            prompt_version=str(data.get("prompt_version", "")),
            contract_version=str(data.get("contract_version", CONTRACT_VERSION)),
            implementation_version=str(data.get("implementation_version", "")),
            delivered=tuple(
                DeliveredValue(key=str(d["key"]), value=d.get("value"))
                for d in data.get("delivered") or ()
            ),
            parameters=dict(data.get("parameters") or {}),
        )


@dataclass(frozen=True)
class ModuleResult:
    """모듈 실행 결과. 실행 성공과 근거 확보를 독립적으로 표현한다."""

    result_id: uuid.UUID
    module_id: str
    module_execution_id: uuid.UUID
    run_id: uuid.UUID
    version: int
    input_hash: str
    status: ModuleStatus
    quality: QualityStatus
    claims: tuple[EvidenceClaim, ...] = ()
    coverage: tuple[CoverageEntry, ...] = ()
    diagnostics: tuple[str, ...] = ()
    failure_code: FailureCode | None = None
    implementation_version: str = ""
    prompt_version: str = ""
    contract_version: str = CONTRACT_VERSION
    created_at: datetime | None = None
    supersedes_result_id: uuid.UUID | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ModuleResult":
        return cls(
            result_id=_uuid(data["result_id"]),  # type: ignore[arg-type]
            module_id=str(data["module_id"]),
            module_execution_id=_uuid(data["module_execution_id"]),  # type: ignore[arg-type]
            run_id=_uuid(data["run_id"]),  # type: ignore[arg-type]
            version=int(data["version"]),
            input_hash=str(data["input_hash"]),
            status=_enum(ModuleStatus, data["status"]),
            quality=_enum(QualityStatus, data["quality"]),
            claims=tuple(EvidenceClaim.from_dict(c) for c in data.get("claims") or ()),
            coverage=tuple(
                CoverageEntry(
                    topic=str(c["topic"]),
                    state=_enum(CoverageState, c["state"]),
                    detail=c.get("detail"),
                )
                for c in data.get("coverage") or ()
            ),
            diagnostics=tuple(str(d) for d in data.get("diagnostics") or ()),
            failure_code=_enum(FailureCode, data.get("failure_code")),
            implementation_version=str(data.get("implementation_version", "")),
            prompt_version=str(data.get("prompt_version", "")),
            contract_version=str(data.get("contract_version", CONTRACT_VERSION)),
            created_at=_dt(data.get("created_at")),
            supersedes_result_id=_uuid(data.get("supersedes_result_id")),
            payload=dict(data.get("payload") or {}),
        )


@dataclass(frozen=True)
class ModuleRegistration:
    """모듈 등록 한 건. 등록은 `registry.py` 한 곳에서만 관리한다.

    `implemented=False`인 모듈은 화면에서 실행할 수 없는 것으로 표시한다.
    모의 시연 모듈도 `mode_scope`로 실제 실행 방식이 아님을 드러낸다.
    """

    module_id: str
    display_name: str
    description: str
    operation: str  # 실행 동작 이름. 공통 동작은 execute_module이다.
    depends_on: tuple[str, ...]
    contract_version: str
    prompt_version: str | None
    inspector_panel: str
    implemented: bool
    mode_scope: tuple[RunMode, ...]
    expected_model_calls: int
    unrunnable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @property
    def available(self) -> bool:
        return self.implemented


# --------------------------------------------------------------------------
# 섹션 워크플로우 승인
# --------------------------------------------------------------------------


class ApprovalState(str, Enum):
    """섹션 워크플로우 버전의 승인 상태.

    승인 단위는 **프리뷰 섹션을 만드는 완결된 워크플로우**다. 내부 노드나 D0 같은
    자료 준비 단계마다 따로 승인을 요구하지 않는다. 승인은 개발 워커가 만들지
    않는다.
    """

    # 한 번도 승인된 적이 없다.
    NONE = "none"
    # 승인된 적이 있으나 결과 의미를 바꾸는 변경이 있어 새 버전 확인이 필요하다.
    # 옛 승인은 유지되며 덮어쓰지 않는다.
    SUPERSEDED = "superseded"
    # 이 버전이 현재 활성 승인이다.
    APPROVED = "approved"


class ApprovalRequestError(ValueError):
    """승인 요청이 계약을 어긴다. 호출자가 저장 전에 거부해야 한다."""


@dataclass(frozen=True)
class SectionWorkflowRegistration:
    """프리뷰 섹션 하나를 만드는 워크플로우.

    한 섹션은 여러 노드·모듈·공유 자료 준비(D0)·검증·표현 처리를 포함할 수 있다.
    사용자는 이 단위의 **결과 본문과 근거**를 확인하고 승인한다. 모듈과 일대일이
    아니며, 이 목록은 승인 대상 구성과 진단 경로를 연결하는 용도다.
    """

    workflow_id: str
    display_name: str
    description: str
    # 이 섹션 결과에 영향을 주는 모듈들. D0 같은 공유 자료 준비도 포함된다.
    module_ids: tuple[str, ...]
    # 결과 의미를 바꾸는 출력 계약 버전. 이 값이 바뀌면 재확인이 필요하다.
    output_contract_version: str
    implemented: bool
    unrunnable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


@dataclass(frozen=True)
class ConstituentVersion:
    """승인 대상 섹션을 구성한 모듈 하나의 버전. 승인 기록에 함께 남긴다."""

    module_id: str
    prompt_version: str
    implementation_version: str
    contract_version: str

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


@dataclass(frozen=True)
class ReviewedSectionEvidence:
    """승인자가 실제로 확인한 실행과 섹션 결과.

    `section_result_id`는 섹션 본문 결과다. MP-02에는 섹션 실행이 없으므로 아직
    만들 수 없고, 승인도 그때까지 거부된다. 모의 실행은 이 자리에 넣지 않는다.
    """

    run_id: uuid.UUID
    section_result_id: uuid.UUID
    reviewed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


@dataclass(frozen=True)
class SectionApproval:
    """섹션 워크플로우 버전 승인 기록 한 건. append-only다."""

    approval_id: uuid.UUID
    workflow_id: str
    workflow_version: str
    constituents: tuple[ConstituentVersion, ...]
    evidence: ReviewedSectionEvidence
    approved_by_actor_id: str
    approved_at: datetime
    reviewed_note: str | None = None
    supersedes_approval_id: uuid.UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


@dataclass(frozen=True)
class SectionApprovalStatus:
    """섹션 하나의 승인 현황. 승인된 활성 버전과 재확인 후보를 구분한다."""

    workflow_id: str
    state: ApprovalState
    active_approval: SectionApproval | None
    # 승인된 적은 있으나 지금 구성이 바뀐 경우의 옛 승인. 계속 유효하다.
    pinned_approval: SectionApproval | None
    current_version: str | None
    current_constituents: tuple[ConstituentVersion, ...]
    candidate_note: str | None = None

    @property
    def approved(self) -> bool:
        return self.state is ApprovalState.APPROVED

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


# --------------------------------------------------------------------------
# 제공자 요청·응답과 시도
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestSpec:
    """제공자에 보낸 요청의 비밀값 없는 설명. 원문 본문은 아티팩트에 둔다."""

    logical_call_id: str
    provider: str
    model: str | None
    operation: str
    module_id: str | None
    endpoint: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)
    prompt_version: str | None = None
    contract_version: str = CONTRACT_VERSION
    timeout_seconds: int | None = None
    # 비밀값 이름만 담는다. 값은 아티팩트에도 기록하지 않는다.
    secret_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RequestSpec":
        return cls(
            logical_call_id=str(data["logical_call_id"]),
            provider=str(data["provider"]),
            model=data.get("model"),
            operation=str(data.get("operation", "")),
            module_id=data.get("module_id"),
            endpoint=data.get("endpoint"),
            parameters=dict(data.get("parameters") or {}),
            prompt_version=data.get("prompt_version"),
            contract_version=str(data.get("contract_version", CONTRACT_VERSION)),
            timeout_seconds=data.get("timeout_seconds"),
            secret_refs=tuple(str(s) for s in data.get("secret_refs") or ()),
        )


@dataclass(frozen=True)
class ProviderUsage:
    """제공자가 알려준 사용량. 미제공 값은 None이며 0으로 채우지 않는다."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    search_queries: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ProviderUsage | None":
        if not data:
            return None
        return cls(
            input_tokens=data.get("input_tokens"),
            output_tokens=data.get("output_tokens"),
            search_queries=data.get("search_queries"),
        )


@dataclass(frozen=True)
class ProviderResponse:
    """수신 결과의 공통 표현. 원문 본문은 `raw_artifact_id`로 가리킨다."""

    attempt_id: uuid.UUID | None
    outcome: AttemptOutcome
    http_status: int | None = None
    provider_request_id: str | None = None
    raw_artifact_id: uuid.UUID | None = None
    error_class: str | None = None
    error_message: str | None = None
    usage: ProviderUsage | None = None
    duration_ms: int | None = None
    received_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProviderResponse":
        return cls(
            attempt_id=_uuid(data.get("attempt_id")),
            outcome=_enum(AttemptOutcome, data["outcome"]),
            http_status=data.get("http_status"),
            provider_request_id=data.get("provider_request_id"),
            raw_artifact_id=_uuid(data.get("raw_artifact_id")),
            error_class=data.get("error_class"),
            error_message=data.get("error_message"),
            usage=ProviderUsage.from_dict(data.get("usage")),
            duration_ms=data.get("duration_ms"),
            received_at=_dt(data.get("received_at")),
        )


@dataclass(frozen=True)
class AttemptTrace:
    """논리 호출 한 번의 실제 시도 한 건. 재시도를 한 행으로 뭉개지 않는다."""

    attempt_id: uuid.UUID
    logical_call_id: str
    attempt_ordinal: int
    run_id: uuid.UUID
    module_execution_id: uuid.UUID | None
    module_id: str | None
    provider: str
    model: str | None
    mode: RunMode
    outcome: AttemptOutcome
    request_spec: RequestSpec
    response: ProviderResponse | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    wait_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


# --------------------------------------------------------------------------
# 독자용 문서와 검증된 조사
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PreviewDocument:
    """독자용 프리뷰. 내부 진단·시도·비밀값·누락 안내를 담지 않는다."""

    document_id: uuid.UUID
    run_id: uuid.UUID
    fixture: FixtureIdentity
    generated_at: datetime
    data_as_of: datetime | None
    headline: str
    watch_points: tuple[str, ...] = ()
    players_to_watch: tuple[Mapping[str, Any], ...] = ()
    absences_impact: str | None = None
    external_outlook: tuple[Mapping[str, Any], ...] = ()
    ai_prediction: Mapping[str, Any] = field(default_factory=dict)
    sources: tuple[Mapping[str, Any], ...] = ()
    contract_version: str = PREVIEW_DOCUMENT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


@dataclass(frozen=True)
class ValidatedResearch:
    """V0 결과. S1의 입력이며 제외·충돌 사유를 함께 넘긴다."""

    fixture: FixtureIdentity
    selected_result_ids: tuple[uuid.UUID, ...]
    snapshot_ids: tuple[uuid.UUID, ...]
    adopted_claims: tuple[EvidenceClaim, ...]
    excluded_claims: tuple[EvidenceClaim, ...]
    core_evidence_satisfied: bool
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


# --------------------------------------------------------------------------
# 관리자 조회 계약
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactRef:
    """아티팩트 요약. 본문은 보관 기간이 지나면 사라져도 요약은 남는다."""

    artifact_id: uuid.UUID
    kind: ArtifactKind
    media_type: str
    byte_size: int
    sha256: str
    redacted: bool
    created_at: datetime
    expires_at: datetime
    expired_at: datetime | None = None

    @property
    def available(self) -> bool:
        return self.expired_at is None

    def to_dict(self) -> dict[str, Any]:
        return {**_plain(self), "available": self.available}


@dataclass(frozen=True)
class RunSummary:
    """실행 목록 한 행."""

    run_id: uuid.UUID
    operation_kind: OperationKind
    environment: Environment
    mode: RunMode
    status: RunStatus
    quality: QualityStatus
    fixture_label: str | None
    requested_at: datetime
    finished_at: datetime | None
    module_count: int
    attempt_count: int
    retry_count: int
    failure_code: FailureCode | None
    label: str | None
    cancelled_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


@dataclass(frozen=True)
class RunDetail:
    """실행 하나의 전체 기록. 조회는 저장된 행만 읽는다."""

    summary: RunSummary
    # 관리자 계정 ID(bigint). JS 숫자 안전 범위를 넘을 수 있으므로 문자열로 나간다.
    actor_id: str
    config_version: str
    limits: ExecutionLimits
    fixture: FixtureIdentity | None
    modules: tuple[Mapping[str, Any], ...]
    results: tuple[Mapping[str, Any], ...]
    sources: tuple[Mapping[str, Any], ...]
    attempts: tuple[Mapping[str, Any], ...]
    artifacts: tuple[Mapping[str, Any], ...]
    contract_versions: Mapping[str, str]
    undo: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


@dataclass(frozen=True)
class MetricsQuery:
    """지표 조회 조건. MP-02는 계약만 고정하고 집계는 MP-08이 구현한다."""

    from_at: datetime | None = None
    to_at: datetime | None = None
    environments: tuple[Environment, ...] = ()
    modes: tuple[RunMode, ...] = ()
    module_ids: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    contract_versions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


@dataclass(frozen=True)
class MetricsResult:
    metric: str
    numerator: int | None
    denominator: int | None
    window: Mapping[str, Any]
    filters: Mapping[str, Any]
    detail_run_ids: tuple[uuid.UUID, ...] = ()
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


def compute_input_hash(payload: Any) -> str:
    """같은 입력인지 비교할 수 있는 안정적인 해시.

    공급자·모듈 구현이 같은 입력을 다시 처리했는지 판단하는 근거로 쓴다.
    정렬된 JSON으로 계산하므로 dict 순서에 흔들리지 않는다.
    """
    import hashlib
    import json

    canonical = json.dumps(_plain(payload), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
