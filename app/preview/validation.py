"""MP-09 V0 근거 검증. S1 종합 호출에 들어갈 조사 결과만 남긴다.

이 파일이 책임지는 것:

- 선택된 R1/R2/R3(그리고 이후 등록되는 모듈)의 `ModuleResult` 버전과 그 결과가
  참조하는 D0 스냅샷을 같은 경기·같은 실행으로 확인한다.
- **사실(Fact)은 근거 참조가 있어야 통과**한다. 참조는 실제로 넘겨받은 스냅샷 ID
  또는 그 결과의 검색 출처 URL 중 하나여야 한다. 없는 참조는 지어낸 것이므로 제외한다.
- **AI 판단(해석·선정·예측)은 외부 증명을 요구하지 않는다**(사용자 확정 기준,
  설계 §5). 다만 판단 문장에 섞인 새 수치·날짜·선수 이름은 종합 단계에서 다시
  검사한다(`synthesis.py`).
- 검색 인용이 0건이거나 배당·부상 발생일 같은 선택 자료가 비어도 실패로 만들지 않는다.
  핵심 근거(경기 식별 + 참조가 붙은 채택 사실)가 있을 때만 `core_evidence_satisfied`다.

이 모듈은 외부 호출을 하지 않는다. 저장된 결과·스냅샷 행만 읽는다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from app.preview.contracts import (
    CONTRACT_VERSION,
    ClaimDecision,
    ClaimKind,
    EvidenceClaim,
    FixtureIdentity,
    SourceSnapshot,
    ValidatedResearch,
)

__all__ = [
    "EvidenceGap",
    "SelectedResultInput",
    "ValidatedEvidence",
    "ValidatedModule",
    "evidence_from_payload",
    "evidence_to_payload",
    "validate_evidence",
]

# 판단 자료. 근거 참조가 없어도 통과하지만, 문장에 새 사실을 끼워 넣으면 안 된다.
JUDGMENT_KINDS = frozenset(
    {ClaimKind.AI_INTERPRETATION, ClaimKind.EXTERNAL_FORECAST, ClaimKind.API_PREDICTION}
)


@dataclass(frozen=True)
class EvidenceGap:
    """자료 공백 하나. **관리자 진단 전용**이며 독자용 문서에 들어가지 않는다."""

    module_id: str
    reason: str

    def to_text(self) -> str:
        return f"{self.module_id}: {self.reason}"

    def to_dict(self) -> dict[str, Any]:
        return {"module_id": self.module_id, "reason": self.reason}


@dataclass(frozen=True)
class SelectedResultInput:
    """저장된 모듈 결과 한 건을 검증에 넣기 위한 최소 표현.

    `synthesis.load_selected_results`가 저장 행에서 이 값을 만든다. 검증·종합은
    DB 행에 직접 의존하지 않으므로, 기록된 fixture로도 같은 경로를 검사할 수 있다.
    """

    result_id: uuid.UUID
    module_id: str
    version: int
    status: str
    quality: str
    implementation_version: str
    prompt_version: str
    fixture: FixtureIdentity | None
    claims: tuple[EvidenceClaim, ...] = ()
    sources: tuple[Mapping[str, Any], ...] = ()
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": str(self.result_id),
            "module_id": self.module_id,
            "version": self.version,
            "status": self.status,
            "quality": self.quality,
            "implementation_version": self.implementation_version,
            "prompt_version": self.prompt_version,
            "fixture": self.fixture.to_dict() if self.fixture else None,
            "claims": [claim.to_dict() for claim in self.claims],
            "sources": [dict(row) for row in self.sources],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SelectedResultInput":
        return cls(
            result_id=uuid.UUID(str(data["result_id"])),
            module_id=str(data["module_id"]),
            version=int(data.get("version") or 0),
            status=str(data.get("status") or ""),
            quality=str(data.get("quality") or ""),
            implementation_version=str(data.get("implementation_version") or ""),
            prompt_version=str(data.get("prompt_version") or ""),
            fixture=(
                FixtureIdentity.from_dict(data["fixture"]) if data.get("fixture") else None
            ),
            claims=tuple(
                EvidenceClaim.from_dict(item) for item in data.get("claims") or ()
            ),
            sources=tuple(dict(row) for row in data.get("sources") or ()),
        )


@dataclass(frozen=True)
class ValidatedModule:
    """검증을 통과한 모듈 하나의 조사 결과. 버전을 그대로 남긴다."""

    module_id: str
    result_id: uuid.UUID
    version: int
    quality: str
    implementation_version: str
    prompt_version: str
    adopted: tuple[EvidenceClaim, ...]
    excluded: tuple[EvidenceClaim, ...]
    sources: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "result_id": str(self.result_id),
            "version": self.version,
            "quality": self.quality,
            "implementation_version": self.implementation_version,
            "prompt_version": self.prompt_version,
            "adopted": [claim.to_dict() for claim in self.adopted],
            "excluded": [claim.to_dict() for claim in self.excluded],
            "sources": [dict(row) for row in self.sources],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ValidatedModule":
        return cls(
            module_id=str(data["module_id"]),
            result_id=uuid.UUID(str(data["result_id"])),
            version=int(data.get("version") or 0),
            quality=str(data.get("quality") or ""),
            implementation_version=str(data.get("implementation_version") or ""),
            prompt_version=str(data.get("prompt_version") or ""),
            adopted=tuple(
                EvidenceClaim.from_dict(item) for item in data.get("adopted") or ()
            ),
            excluded=tuple(
                EvidenceClaim.from_dict(item) for item in data.get("excluded") or ()
            ),
            sources=tuple(dict(row) for row in data.get("sources") or ()),
        )


@dataclass(frozen=True)
class ValidatedEvidence:
    """V0 결과. S1의 실제 입력이며, 무엇을 버렸는지도 함께 넘긴다."""

    fixture: FixtureIdentity | None
    modules: tuple[ValidatedModule, ...]
    snapshots: tuple[SourceSnapshot, ...]
    gaps: tuple[EvidenceGap, ...]
    core_evidence_satisfied: bool
    contract_version: str = CONTRACT_VERSION

    # -- 조회 --------------------------------------------------------------

    @property
    def adopted_claims(self) -> tuple[EvidenceClaim, ...]:
        return tuple(claim for module in self.modules for claim in module.adopted)

    @property
    def excluded_claims(self) -> tuple[EvidenceClaim, ...]:
        return tuple(claim for module in self.modules for claim in module.excluded)

    @property
    def selected_result_ids(self) -> tuple[uuid.UUID, ...]:
        return tuple(module.result_id for module in self.modules)

    @property
    def snapshot_ids(self) -> tuple[uuid.UUID, ...]:
        seen: list[uuid.UUID] = []
        for claim in self.adopted_claims:
            for snapshot_id in claim.snapshot_ids:
                if snapshot_id not in seen:
                    seen.append(snapshot_id)
        return tuple(seen)

    @property
    def module_ids(self) -> tuple[str, ...]:
        return tuple(module.module_id for module in self.modules)

    def claims_by_id(self) -> dict[str, EvidenceClaim]:
        return {claim.claim_id: claim for claim in self.adopted_claims}

    def verdicts(self) -> tuple[EvidenceClaim, ...]:
        """제외 판정도 함께 보존한다. 왜 버렸는지가 남아야 재현할 수 있다."""
        return tuple(
            EvidenceClaim(
                claim_id=claim.claim_id,
                kind=claim.kind,
                text=claim.text,
                snapshot_ids=claim.snapshot_ids,
                decision=ClaimDecision.EXCLUDED,
                decision_reason=claim.decision_reason,
                subject_team_id=claim.subject_team_id,
                subject_player_id=claim.subject_player_id,
                claimed_at=claim.claimed_at,
                source_url=claim.source_url,
            )
            for claim in self.excluded_claims
        )

    def to_research(self) -> ValidatedResearch:
        """고정 계약(`ValidatedResearch`)으로 내보낸다. 기존 필드만 쓴다."""
        return ValidatedResearch(
            fixture=self.fixture,  # type: ignore[arg-type]
            selected_result_ids=self.selected_result_ids,
            snapshot_ids=self.snapshot_ids,
            adopted_claims=self.adopted_claims + self.verdicts(),
            excluded_claims=self.excluded_claims,
            core_evidence_satisfied=self.core_evidence_satisfied,
            contract_version=self.contract_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture": self.fixture.to_dict() if self.fixture else None,
            "modules": [module.to_dict() for module in self.modules],
            "snapshots": [snapshot.to_dict() for snapshot in self.snapshots],
            "gaps": [gap.to_dict() for gap in self.gaps],
            "core_evidence_satisfied": self.core_evidence_satisfied,
            "contract_version": self.contract_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ValidatedEvidence":
        return cls(
            fixture=(
                FixtureIdentity.from_dict(data["fixture"]) if data.get("fixture") else None
            ),
            modules=tuple(
                ValidatedModule.from_dict(item) for item in data.get("modules") or ()
            ),
            snapshots=tuple(
                SourceSnapshot(
                    snapshot_id=uuid.UUID(str(item["snapshot_id"])),
                    source_kind=item["source_kind"],
                    provider=str(item["provider"]),
                    collected_at=datetime.fromisoformat(str(item["collected_at"])),
                    provider_updated_at=(
                        datetime.fromisoformat(str(item["provider_updated_at"]))
                        if item.get("provider_updated_at")
                        else None
                    ),
                    fixture=None,
                    catalog_query=None,
                    artifact_id=None,
                    validation_status=item["validation_status"],
                    note=item.get("note"),
                )
                for item in data.get("snapshots") or ()
            ),
            gaps=tuple(
                EvidenceGap(
                    module_id=str(item["module_id"]), reason=str(item["reason"])
                )
                for item in data.get("gaps") or ()
            ),
            core_evidence_satisfied=bool(data.get("core_evidence_satisfied")),
            contract_version=str(data.get("contract_version") or CONTRACT_VERSION),
        )


def evidence_to_payload(evidence: ValidatedEvidence) -> dict[str, Any]:
    return evidence.to_dict()


def evidence_from_payload(payload: Mapping[str, Any] | None) -> ValidatedEvidence | None:
    if not payload:
        return None
    return ValidatedEvidence.from_dict(payload)


# --------------------------------------------------------------------------
# 검증
# --------------------------------------------------------------------------


def _source_urls(sources: Iterable[Mapping[str, Any]]) -> set[str]:
    return {
        str(source.get("url"))
        for source in sources
        if isinstance(source, Mapping) and source.get("url")
    }


def _resolves(claim: EvidenceClaim, *, snapshot_ids: set[uuid.UUID], urls: set[str]) -> bool:
    """사실 참조가 실제로 넘겨받은 근거를 가리키는가."""
    if claim.source_url and claim.source_url in urls:
        return True
    return any(snapshot_id in snapshot_ids for snapshot_id in claim.snapshot_ids)


def _claim_reason(claim: EvidenceClaim, reason: str) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=claim.claim_id,
        kind=claim.kind,
        text=claim.text,
        snapshot_ids=claim.snapshot_ids,
        decision=ClaimDecision.EXCLUDED,
        decision_reason=reason,
        subject_team_id=claim.subject_team_id,
        subject_player_id=claim.subject_player_id,
        claimed_at=claim.claimed_at,
        source_url=claim.source_url,
    )


def _coverage_gaps(
    results: Sequence[SelectedResultInput], module_ids: Sequence[str]
) -> list[EvidenceGap]:
    """선택되지 않았거나 자료가 빈 모듈을 진단에 남긴다. 실패로 만들지 않는다."""
    gaps: list[EvidenceGap] = []
    present = {result.module_id for result in results}
    for module_id in module_ids:
        if module_id not in present:
            gaps.append(
                EvidenceGap(
                    module_id=module_id,
                    reason="이 실행에 선택된 결과가 없습니다(선택 입력에서 빠짐).",
                )
            )
    for result in results:
        coverage = (result.payload or {}).get("coverage") or ()
        for entry in coverage:
            if not isinstance(entry, Mapping):
                continue
            state = str(entry.get("state") or "")
            if state in {"available", ""}:
                continue
            gaps.append(
                EvidenceGap(
                    module_id=result.module_id,
                    reason=(
                        f"자료 상태 {state}: {entry.get('detail') or entry.get('topic') or ''}"
                    ).strip(),
                )
            )
    return gaps


def validate_evidence(
    *,
    fixture: FixtureIdentity | Mapping[str, Any] | None,
    results: Sequence[SelectedResultInput],
    snapshots: Sequence[SourceSnapshot] = (),
    module_ids: Sequence[str] = (),
    selected_result_ids: Sequence[uuid.UUID] = (),
    now: datetime | None = None,
) -> ValidatedEvidence:
    """선택된 결과를 S1 입력으로 검증한다. 외부 호출은 없다.

    - 선택 ID와 실제 입력이 다르면 그 차이를 진단에 남긴다(조용히 채우지 않는다).
    - 다른 경기의 결과·실패한 결과·참조가 없는 사실은 제외한다.
    - 판단(해석·예측·매체 전망)은 외부 동의 출처를 요구하지 않는다. 매체 전망만
      실제 URL이 있어야 한다(그 매체가 실제로 말했다는 근거).
    """
    identity = (
        fixture
        if isinstance(fixture, FixtureIdentity)
        else (FixtureIdentity.from_dict(fixture) if fixture else None)
    )
    snapshot_index = {snapshot.snapshot_id: snapshot for snapshot in snapshots}
    gaps: list[EvidenceGap] = []

    ordered: list[SelectedResultInput] = []
    seen_ids: set[uuid.UUID] = set()
    for result in results:
        if result.result_id in seen_ids:
            continue
        seen_ids.add(result.result_id)
        ordered.append(result)
    ordered.sort(key=lambda item: (item.module_id, item.version, str(item.result_id)))

    missing = [
        str(result_id)
        for result_id in selected_result_ids
        if result_id not in seen_ids
    ]

    modules: list[ValidatedModule] = []
    for result in ordered:
        if identity is not None:
            if result.fixture is None:
                gaps.append(
                    EvidenceGap(
                        module_id=result.module_id,
                        reason=(
                            "결과에 경기 식별자가 없어 같은 경기인지 확인할 수 없습니다."
                        ),
                    )
                )
                continue
            if not _same_fixture(result.fixture, identity):
                gaps.append(
                    EvidenceGap(
                        module_id=result.module_id,
                        reason=(
                            "다른 경기의 결과입니다 "
                            f"(선택 경기 {identity.fixture_id}, "
                            f"결과 경기 {result.fixture.fixture_id})."
                        ),
                    )
                )
                continue
        if result.status != "succeeded":
            gaps.append(
                EvidenceGap(
                    module_id=result.module_id,
                    reason=f"실행 상태가 {result.status or '미상'}이라 종합 입력에서 제외했습니다.",
                )
            )
            continue

        urls = _source_urls(result.sources)
        adopted: list[EvidenceClaim] = []
        excluded: list[EvidenceClaim] = []
        for claim in result.claims:
            if claim.decision is not ClaimDecision.ADOPTED:
                # 이미 제외·상충으로 판정된 항목은 판정과 사유를 그대로 보존한다.
                excluded.append(claim)
                continue
            if claim.kind is ClaimKind.FACT:
                if not _resolves(claim, snapshot_ids=set(snapshot_index), urls=urls):
                    excluded.append(
                        _claim_reason(
                            claim,
                            "사실 문장에 실제 입력 근거(스냅샷·검색 URL) 참조가 없어"
                            " 종합에서 제외했습니다.",
                        )
                    )
                    continue
            elif claim.kind is ClaimKind.EXTERNAL_FORECAST:
                if not claim.source_url:
                    excluded.append(
                        _claim_reason(
                            claim,
                            "매체 전망인데 그 매체가 실제로 그렇게 말했다는 URL 근거가"
                            " 없어 종합에서 제외했습니다.",
                        )
                    )
                    continue
                if claim.source_url not in urls:
                    excluded.append(
                        _claim_reason(
                            claim,
                            "매체 전망 URL이 이 결과의 검색 출처 목록에 없어"
                            " 종합에서 제외했습니다.",
                        )
                    )
                    continue
            adopted.append(claim)

        if not adopted and not excluded:
            gaps.append(
                EvidenceGap(module_id=result.module_id, reason="채택된 근거 문장이 없습니다.")
            )
        modules.append(
            ValidatedModule(
                module_id=result.module_id,
                result_id=result.result_id,
                version=result.version,
                quality=result.quality,
                implementation_version=result.implementation_version,
                prompt_version=result.prompt_version,
                adopted=tuple(adopted),
                excluded=tuple(excluded),
                sources=tuple(dict(row) for row in result.sources),
            )
        )

    if missing:
        gaps.append(
            EvidenceGap(
                module_id="selection",
                reason=(
                    "선택한 결과 ID를 저장된 결과에서 찾지 못했습니다: "
                    + ", ".join(missing)
                ),
            )
        )
    gaps.extend(_coverage_gaps(ordered, module_ids))

    referenced = {claim for claim in (c for module in modules for c in module.adopted)}
    used_snapshots = tuple(
        snapshot
        for snapshot_id, snapshot in snapshot_index.items()
        if any(snapshot_id in claim.snapshot_ids for claim in referenced)
    )

    has_referenced_fact = any(
        claim.kind is ClaimKind.FACT and bool(claim.snapshot_ids or claim.source_url)
        for module in modules
        for claim in module.adopted
    )
    core = identity is not None and has_referenced_fact
    if identity is None:
        gaps.append(
            EvidenceGap(
                module_id="fixture",
                reason="경기 식별자가 없어 독자용 프리뷰를 만들 수 없습니다.",
            )
        )
    return ValidatedEvidence(
        fixture=identity,
        modules=tuple(modules),
        snapshots=used_snapshots,
        gaps=tuple(gaps),
        core_evidence_satisfied=core,
    )


def _same_fixture(left: FixtureIdentity, right: FixtureIdentity) -> bool:
    return (
        left.fixture_id == right.fixture_id
        and left.league_id == right.league_id
        and left.season == right.season
    )
