"""NS-01 선수 섹션(주목 선수·부상/결장) 및 한글명 후보 ORM 모델 (`preview_dev` 전용).

모든 테이블은 `preview_dev` 스키마에만 둔다. `public` 스키마에 외래 키나 DDL을
추가하지 않는다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.preview.db import SCHEMA, Base
from app.preview.player_section_contracts import (
    INJURY_PLAYERS_TABLE,
    PLAYER_NAME_CANDIDATES_TABLE,
    WATCH_PLAYERS_TABLE,
)

_TABLE_ARGS = {"schema": SCHEMA}
_EMPTY_JSONB_LIST = text("'[]'::jsonb")


class PreviewPlayerNameCandidate(Base):
    """실행·섹션 결과·슬롯 소유의 AI 한글명 번역 후보 스냅샷."""

    __tablename__ = PLAYER_NAME_CANDIDATES_TABLE
    __table_args__ = (
        UniqueConstraint(
            "section_result_id",
            "slot_key",
            name="uq_player_name_candidate_slot",
        ),
        Index(f"ix_{PLAYER_NAME_CANDIDATES_TABLE}_run_id", "run_id"),
        Index(
            f"ix_{PLAYER_NAME_CANDIDATES_TABLE}_section_result_id",
            "section_result_id",
        ),
        Index(f"ix_{PLAYER_NAME_CANDIDATES_TABLE}_fixture_id", "fixture_id"),
        Index(f"ix_{PLAYER_NAME_CANDIDATES_TABLE}_review_status", "review_status"),
        _TABLE_ARGS,
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_section_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    workflow_id: Mapped[str] = mapped_column(Text, nullable=False)
    slot_key: Mapped[str] = mapped_column(Text, nullable=False)
    fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_name_ko: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="ai_translation"
    )
    review_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PreviewWatchPlayerSection(Base):
    """주목 선수(`section_players`) 고정 4슬롯 저장 테이블."""

    __tablename__ = WATCH_PLAYERS_TABLE
    __table_args__ = (
        Index(f"ix_{WATCH_PLAYERS_TABLE}_run_id", "run_id"),
        Index(f"ix_{WATCH_PLAYERS_TABLE}_fixture_id", "fixture_id"),
        _TABLE_ARGS,
    )

    section_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_section_results.id", ondelete="CASCADE"),
        primary_key=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    home_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    away_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    output_contract_version: Mapped[str] = mapped_column(Text, nullable=False)

    home1_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    home1_original_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    home1_name_ko: Mapped[str | None] = mapped_column(Text, nullable=True)
    home1_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    home1_name_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    home1_unresolved_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    home1_translation_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.{PLAYER_NAME_CANDIDATES_TABLE}.id"), nullable=True
    )
    home1_evidence: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=_EMPTY_JSONB_LIST
    )

    home2_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    home2_original_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    home2_name_ko: Mapped[str | None] = mapped_column(Text, nullable=True)
    home2_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    home2_name_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    home2_unresolved_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    home2_translation_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.{PLAYER_NAME_CANDIDATES_TABLE}.id"), nullable=True
    )
    home2_evidence: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=_EMPTY_JSONB_LIST
    )

    away1_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    away1_original_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    away1_name_ko: Mapped[str | None] = mapped_column(Text, nullable=True)
    away1_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    away1_name_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    away1_unresolved_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    away1_translation_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.{PLAYER_NAME_CANDIDATES_TABLE}.id"), nullable=True
    )
    away1_evidence: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=_EMPTY_JSONB_LIST
    )

    away2_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    away2_original_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    away2_name_ko: Mapped[str | None] = mapped_column(Text, nullable=True)
    away2_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    away2_name_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    away2_unresolved_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    away2_translation_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.{PLAYER_NAME_CANDIDATES_TABLE}.id"), nullable=True
    )
    away2_evidence: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=_EMPTY_JSONB_LIST
    )

    home_etc: Mapped[str | None] = mapped_column(Text, nullable=True)
    away_etc: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PreviewInjuryPlayerSection(Base):
    """부상·결장(`section_availability`) 고정 4슬롯 저장 테이블."""

    __tablename__ = INJURY_PLAYERS_TABLE
    __table_args__ = (
        Index(f"ix_{INJURY_PLAYERS_TABLE}_run_id", "run_id"),
        Index(f"ix_{INJURY_PLAYERS_TABLE}_fixture_id", "fixture_id"),
        _TABLE_ARGS,
    )

    section_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_section_results.id", ondelete="CASCADE"),
        primary_key=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.preview_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    home_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    away_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    output_contract_version: Mapped[str] = mapped_column(Text, nullable=False)

    home1_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    home1_original_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    home1_name_ko: Mapped[str | None] = mapped_column(Text, nullable=True)
    home1_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    home1_name_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    home1_unresolved_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    home1_translation_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.{PLAYER_NAME_CANDIDATES_TABLE}.id"), nullable=True
    )
    home1_evidence: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=_EMPTY_JSONB_LIST
    )
    home1_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    home1_injury: Mapped[str | None] = mapped_column(Text, nullable=True)
    home1_importance: Mapped[str | None] = mapped_column(Text, nullable=True)

    home2_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    home2_original_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    home2_name_ko: Mapped[str | None] = mapped_column(Text, nullable=True)
    home2_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    home2_name_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    home2_unresolved_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    home2_translation_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.{PLAYER_NAME_CANDIDATES_TABLE}.id"), nullable=True
    )
    home2_evidence: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=_EMPTY_JSONB_LIST
    )
    home2_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    home2_injury: Mapped[str | None] = mapped_column(Text, nullable=True)
    home2_importance: Mapped[str | None] = mapped_column(Text, nullable=True)

    away1_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    away1_original_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    away1_name_ko: Mapped[str | None] = mapped_column(Text, nullable=True)
    away1_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    away1_name_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    away1_unresolved_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    away1_translation_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.{PLAYER_NAME_CANDIDATES_TABLE}.id"), nullable=True
    )
    away1_evidence: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=_EMPTY_JSONB_LIST
    )
    away1_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    away1_injury: Mapped[str | None] = mapped_column(Text, nullable=True)
    away1_importance: Mapped[str | None] = mapped_column(Text, nullable=True)

    away2_player_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    away2_original_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    away2_name_ko: Mapped[str | None] = mapped_column(Text, nullable=True)
    away2_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    away2_name_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    away2_unresolved_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    away2_translation_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.{PLAYER_NAME_CANDIDATES_TABLE}.id"), nullable=True
    )
    away2_evidence: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=_EMPTY_JSONB_LIST
    )
    away2_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    away2_injury: Mapped[str | None] = mapped_column(Text, nullable=True)
    away2_importance: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "PreviewInjuryPlayerSection",
    "PreviewPlayerNameCandidate",
    "PreviewWatchPlayerSection",
]
