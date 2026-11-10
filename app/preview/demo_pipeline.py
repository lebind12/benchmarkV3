"""녹화된 모의 파이프라인 (MP-02 첫 화면 경로).

목적은 사용자가 개발 중에 각 호출의 자료 흐름을 직접 확인하는 것이다. 그래서
이 경로는 **외부 모델·API를 전혀 호출하지 않는다.** 대신 실제 저장 구조에
요청·원문 응답·정규화 변환·다음 입력·결과 버전을 그대로 남긴다. 이후 MP-03/04가
같은 저장 함수를 쓰므로, 지금 만든 검사 화면이 그대로 살아남는다.

명시적 계약:

- `mode=mock`, `operation_kind=mock_demo`로 기록한다. live 성공으로 셀 수 없다.
- 실행 생성은 관리자의 명시적 POST 한 번으로만 일어난다. GET은 저장된 행만 읽는다.
- 두 번째 결과 버전을 함께 남겨 버전 비교 화면을 실제 데이터로 확인할 수 있게 한다.
  이때 각 버전은 같은 모듈 실행의 서로 다른 버전이며, 이전 버전은 지우지 않는다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.preview import artifacts as artifact_store
from app.preview import store
from app.preview.contracts import (
    CONTRACT_VERSION,
    MODULE_INPUT_VERSION,
    AttemptOutcome,
    ClaimDecision,
    ClaimKind,
    CoverageEntry,
    CoverageState,
    Environment,
    EvidenceClaim,
    ExecutionContext,
    ExecutionLimits,
    FixtureIdentity,
    ModuleInput,
    ModuleResult,
    ModuleStatus,
    OperationKind,
    QualityStatus,
    RequestSpec,
    RunMode,
    RunStatus,
    SourceKind,
    ValidationStatus,
    compute_input_hash,
)
from app.preview.registry import MOCK_DEMO_MODULE_ID, get_module

__all__ = ["MOCK_DEMO_LABEL", "create_recorded_mock_run", "demo_fixture"]

# 이 라벨이 화면에서 mock 실행을 눈으로 구분하는 표시다.
MOCK_DEMO_LABEL = "기록 시연 (mock, 외부 호출 없음)"

MOCK_PROVIDER = "recorded-fixture"
MOCK_MODEL = "mock-demo-model"
# 저장된 응답임을 값 자체로 드러내는 표시. 실제 제공자 응답으로 오인되지 않게 한다.
MOCK_RESPONSE_MARKER = "recorded_mock_response"


def demo_fixture(now: datetime) -> FixtureIdentity:
    """시연용 경기 식별자. 실제 API-Football ID가 아니다."""
    return FixtureIdentity(
        fixture_id=900_001,
        league_id=39,
        season=2026,
        home_team_id=50,
        away_team_id=49,
        kickoff_at=(now + timedelta(days=1)).replace(microsecond=0),
    )


def _recorded_request_body(fixture: FixtureIdentity, prompt_version: str) -> dict[str, Any]:
    """모의 '요청 원문'. 실제로 전송하지 않은 본문이며 그 사실을 필드에 남긴다."""
    return {
        "recorded_mock_request": True,
        "note": "이 본문은 외부 제공자에 전송되지 않았습니다. 저장 경로 시연용입니다.",
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "다음 경기의 관전 포인트 후보를 근거와 함께 정리하세요. "
                            f"fixture_id={fixture.fixture_id}, prompt={prompt_version}"
                        )
                    }
                ],
            }
        ],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 512},
        # 비밀값 제거가 실제로 동작하는지 확인할 수 있도록 모양만 갖춘 헤더를 둔다.
        "headers": {
            "authorization": "Bearer mock-token-value-for-redaction-check",
            "x-goog-api-key": "mock-api-key-value-for-redaction-check",
            "content-type": "application/json",
        },
    }


def _recorded_response_body(fixture: FixtureIdentity) -> dict[str, Any]:
    """모의 '수신 원문'. 제공자 응답 모양을 따르되 저장된 값임을 표시한다."""
    return {
        "marker": MOCK_RESPONSE_MARKER,
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                f"경기 {fixture.fixture_id}: 홈팀은 최근 5경기에서 "
                                "2승 2무 1패입니다. 관전 포인트는 중원 압박 전환입니다."
                            )
                        }
                    ],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 412, "candidatesTokenCount": 188},
        # 응답에도 비밀 헤더가 섞여 들어올 수 있다는 전제로 같은 검사를 둔다.
        "echoed_headers": {"x-goog-api-key": "mock-api-key-value-for-redaction-check"},
    }


def _normalized_claims(fixture: FixtureIdentity, snapshot_id: uuid.UUID) -> tuple[EvidenceClaim, ...]:
    """원문에서 뽑아낸 정규화 결과. 채택·제외를 함께 남긴다."""
    return (
        EvidenceClaim(
            claim_id="claim-form-1",
            kind=ClaimKind.FACT,
            text="홈팀은 최근 5경기 2승 2무 1패입니다.",
            snapshot_ids=(snapshot_id,),
            decision=ClaimDecision.ADOPTED,
            decision_reason="저장된 모의 자료의 수치이며 원문에 그대로 있습니다.",
            subject_team_id=fixture.home_team_id,
        ),
        EvidenceClaim(
            claim_id="claim-watch-1",
            kind=ClaimKind.AI_INTERPRETATION,
            text="관전 포인트는 중원 압박 전환입니다.",
            snapshot_ids=(snapshot_id,),
            decision=ClaimDecision.ADOPTED,
            decision_reason="원문 문장을 해석으로 분류했습니다.",
        ),
        EvidenceClaim(
            claim_id="claim-odds-1",
            kind=ClaimKind.EXTERNAL_FORECAST,
            text="배당 자료 없음",
            snapshot_ids=(),
            decision=ClaimDecision.EXCLUDED,
            decision_reason="모의 실행에는 배당 자료가 없습니다. 값을 만들어 채우지 않았습니다.",
        ),
    )


def _coverage() -> tuple[CoverageEntry, ...]:
    return (
        CoverageEntry(
            topic="recent_form",
            state=CoverageState.AVAILABLE,
            detail="저장된 모의 원문에 포함",
        ),
        CoverageEntry(
            topic="odds",
            state=CoverageState.NOT_RUN,
            detail="모의 실행에서는 배당 수집 단계를 실행하지 않았습니다.",
        ),
        CoverageEntry(
            topic="search",
            state=CoverageState.SEARCH_NOT_FOUND,
            detail="모의 실행에는 검색 호출이 없습니다. 검색 실패와 구분해 기록합니다.",
        ),
    )


def _module_input(
    fixture: FixtureIdentity, snapshot_id: uuid.UUID, *, attempt_hint: int
) -> ModuleInput:
    payload = {
        "fixture": fixture.to_dict(),
        "snapshot_ids": [str(snapshot_id)],
        "attempt_hint": attempt_hint,
    }
    return ModuleInput(
        module_id=MOCK_DEMO_MODULE_ID,
        fixture=fixture,
        snapshot_ids=(snapshot_id,),
        selected_result_ids=(),
        input_hash=compute_input_hash(payload),
        prompt_version="mock-demo-1",
        contract_version=MODULE_INPUT_VERSION,
        implementation_version="mp02-recorded-demo-1",
        delivered=(),
        parameters={"attempt_hint": attempt_hint},
    )


@dataclass(frozen=True)
class MockRunResult:
    run_id: uuid.UUID
    module_execution_id: uuid.UUID
    result_ids: tuple[uuid.UUID, ...]
    attempt_id: uuid.UUID


def create_recorded_mock_run(
    session: Session,
    *,
    actor_id: int,
    now: datetime | None = None,
    environment: Environment = Environment.DEV,
) -> MockRunResult:
    """관리자의 명시적 요청으로 녹화된 모의 실행 한 건을 만든다.

    외부 호출은 0회다. 저장하는 값은 모두 이 함수 안에서 만든 모의 자료이며,
    원문에는 비밀값 제거를 확인할 수 있는 모양의 헤더가 포함된다.
    """
    moment = now or datetime.now(timezone.utc)
    fixture = demo_fixture(moment)
    registration = get_module(MOCK_DEMO_MODULE_ID)

    context = ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=OperationKind.MOCK_DEMO,
        environment=environment,
        mode=RunMode.MOCK,
        actor_id=actor_id,
        config_version=f"mp02-demo/{CONTRACT_VERSION}",
        limits=ExecutionLimits(
            model_requests=0,
            api_requests=0,
            attempts_per_call=1,
            deadline_seconds=0,
        ),
    )

    run = store.store_run(
        session,
        context,
        fixture=fixture,
        fixture_label="시연 경기 (모의 식별자, 실제 API 경기 아님)",
        label=MOCK_DEMO_LABEL,
        status=RunStatus.RUNNING,
    )

    # 1) 원문 저장 (비밀값 제거 후). 요청·응답·정규화 변환을 각각 남긴다.
    request_body = _recorded_request_body(fixture, registration.prompt_version or "mock-demo-1")
    request_artifact = artifact_store.save_artifact(
        session,
        run_id=run.id,
        kind=artifact_store.ArtifactKind.RAW_REQUEST,
        content=request_body,
        actor_id=actor_id,
        now=moment,
    )
    response_body = _recorded_response_body(fixture)
    response_artifact = artifact_store.save_artifact(
        session,
        run_id=run.id,
        kind=artifact_store.ArtifactKind.RAW_RESPONSE,
        content=response_body,
        actor_id=actor_id,
        now=moment,
    )

    # 2) 자료 스냅샷. 출처(API/검색)와 실행 방식(mock)이 다른 축임을 그대로 보인다.
    snapshot = store.record_source_snapshot(
        session,
        run_id=run.id,
        source_kind=SourceKind.API,
        provider=MOCK_PROVIDER,
        collected_at=moment,
        validation_status=ValidationStatus.UNVERIFIED,
        fixture=fixture,
        artifact_id=response_artifact.id,
        note="녹화된 모의 자료입니다. 실제 API 수집이 아닙니다.",
        actor_id=actor_id,
    )

    # 3) 모듈 실행과 시도. 시도 한 건이 곧 요청·응답 한 쌍이다.
    module_input = _module_input(fixture, snapshot.id, attempt_hint=1)
    execution = store.start_module_execution(
        session,
        run_id=run.id,
        module_id=MOCK_DEMO_MODULE_ID,
        module_input=module_input,
        actor_id=actor_id,
    )

    call_id = f"{MOCK_DEMO_MODULE_ID}-call-1"
    request_spec = RequestSpec(
        logical_call_id=call_id,
        provider=MOCK_PROVIDER,
        model=MOCK_MODEL,
        operation="execute_module",
        module_id=MOCK_DEMO_MODULE_ID,
        endpoint="recorded://mock-demo",
        parameters={"temperature": 0.2, "max_output_tokens": 512},
        prompt_version=registration.prompt_version,
        contract_version=CONTRACT_VERSION,
        timeout_seconds=None,
        secret_refs=("provider_api_key",),
    )
    attempt = store.append_attempt(
        session,
        run_id=run.id,
        module_execution_id=execution.id,
        module_id=MOCK_DEMO_MODULE_ID,
        logical_call_id=call_id,
        attempt_ordinal=0,
        provider=MOCK_PROVIDER,
        model=MOCK_MODEL,
        mode=RunMode.MOCK,
        operation="execute_module",
        outcome=AttemptOutcome.OK.value,
        request_spec=request_spec.to_dict(),
        http_status=200,
        request_artifact_id=request_artifact.id,
        response_artifact_id=response_artifact.id,
        usage={"input_tokens": 412, "output_tokens": 188, "search_queries": None},
        wait_ms=0,
        started_at=moment,
        finished_at=moment,
        actor_id=actor_id,
    )

    claims = _normalized_claims(fixture, snapshot.id)

    # 4) 첫 결과 버전. 정규화 변환 아티팩트와 변환 결과를 함께 남긴다.
    transform_body = {
        "claims": [claim.to_dict() for claim in claims],
        "coverage": [entry.to_dict() for entry in _coverage()],
        "extracted_from": str(response_artifact.id),
    }
    transform_artifact = artifact_store.save_artifact(
        session,
        run_id=run.id,
        kind=artifact_store.ArtifactKind.NORMALIZED_TRANSFORM,
        content=transform_body,
        attempt_id=attempt.id,
        actor_id=actor_id,
        now=moment,
    )

    first_result = ModuleResult(
        result_id=uuid.uuid4(),
        module_id=MOCK_DEMO_MODULE_ID,
        module_execution_id=execution.id,
        run_id=run.id,
        version=1,
        input_hash=module_input.input_hash,
        status=ModuleStatus.SUCCEEDED,
        quality=QualityStatus.PENDING,
        claims=claims,
        coverage=_coverage(),
        diagnostics=(
            "모의 실행입니다. 외부 모델·API 호출이 없습니다.",
            "일부 자료(배당·검색)는 이 시연에 포함되지 않았습니다.",
        ),
        implementation_version="mp02-recorded-demo-1",
        prompt_version=registration.prompt_version or "mock-demo-1",
        contract_version=CONTRACT_VERSION,
        payload={"transform_artifact_id": str(transform_artifact.id)},
    )
    store.save_module_result(session, first_result, actor_id=actor_id)

    # 5) 두 번째 결과 버전. 버전 비교 화면을 실제 데이터로 확인하기 위한 것으로,
    #    이전 버전을 덮어쓰지 않고 새 행으로 남긴다.
    refined_claims = tuple(
        claim
        if claim.claim_id != "claim-odds-1"
        else EvidenceClaim(
            claim_id=claim.claim_id,
            kind=claim.kind,
            text=claim.text,
            snapshot_ids=claim.snapshot_ids,
            decision=ClaimDecision.EXCLUDED,
            decision_reason=(
                "두 번째 버전에서도 배당 자료가 없어 제외를 유지했습니다. "
                "대체 값을 만들지 않았습니다."
            ),
        )
        for claim in claims
    ) + (
        EvidenceClaim(
            claim_id="claim-context-2",
            kind=ClaimKind.AI_INTERPRETATION,
            text="전환 국면에서 홈팀의 측면 활용이 관건입니다.",
            snapshot_ids=(snapshot.id,),
            decision=ClaimDecision.ADOPTED,
            decision_reason="두 번째 변환에서 추가로 정리한 해석입니다.",
        ),
    )
    second_result = ModuleResult(
        result_id=uuid.uuid4(),
        module_id=MOCK_DEMO_MODULE_ID,
        module_execution_id=execution.id,
        run_id=run.id,
        version=2,
        input_hash=module_input.input_hash,
        status=ModuleStatus.SUCCEEDED,
        quality=QualityStatus.PENDING,
        claims=refined_claims,
        coverage=_coverage(),
        diagnostics=(
            "모의 실행의 두 번째 변환입니다. 외부 호출은 여전히 0회입니다.",
            "이전 버전(1)은 삭제하지 않았습니다.",
        ),
        implementation_version="mp02-recorded-demo-2",
        prompt_version=registration.prompt_version or "mock-demo-1",
        contract_version=CONTRACT_VERSION,
        payload={"transform_artifact_id": str(transform_artifact.id)},
    )
    second_saved = store.save_module_result(session, second_result, actor_id=actor_id)

    # 6) 다음 입력. 이 모듈의 결과가 다음 단계로 어떻게 전달되는지 값을 그대로 남긴다.
    store.update_module_delivery(
        session,
        execution.id,
        {
            "target_module_id": None,
            "selected_result_ids": [str(second_saved.id)],
            "values": [
                {
                    "key": "adopted_claim_ids",
                    "value": [c.claim_id for c in refined_claims if c.decision is ClaimDecision.ADOPTED],
                },
                {"key": "excluded_claim_ids", "value": ["claim-odds-1"]},
                {"key": "data_as_of", "value": moment.isoformat()},
            ],
            "note": (
                "MP-02에는 후속 모듈이 없습니다. 후속 모듈이 붙으면 이 값이 실제로 전달되고 "
                "같은 검사 화면에서 확인됩니다."
            ),
        },
        status=ModuleStatus.SUCCEEDED,
        quality=QualityStatus.PENDING,
    )

    store.finish_run(
        session,
        run.id,
        status=RunStatus.SUCCEEDED,
        quality=QualityStatus.PENDING,
        actor_id=actor_id,
    )

    return MockRunResult(
        run_id=run.id,
        module_execution_id=execution.id,
        result_ids=(first_result.result_id, second_saved.id),
        attempt_id=attempt.id,
    )
