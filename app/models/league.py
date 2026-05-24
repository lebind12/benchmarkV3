"""league + league_translation models.

Spec: docs/spec/db-schema.md §3.1, §3.2.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class League(Base):
    __tablename__ = "league"
    __table_args__ = (
        CheckConstraint("type IN ('League', 'Cup')", name="league_type_check"),
        Index("league_type_idx", "type"),
        # Partial index — only `is_active = true` rows are stored (dynamic
        # league enablement query path: WHERE is_active). Mirrors migration
        # 0002_league_is_active.
        Index(
            "league_active_idx",
            "is_active",
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    external_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(Text)
    country_name: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str | None] = mapped_column(Text)
    country_flag: Mapped[str | None] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    current_season: Mapped[int | None] = mapped_column(Integer)
    # Dynamic league enable/disable flag (db-schema.md §3.1). Existing rows
    # default to true via the 0002 migration backfill (server_default 'true').
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LeagueTranslation(Base):
    __tablename__ = "league_translation"

    league_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("league.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    name_ko: Mapped[str | None] = mapped_column(Text)
    short_name_ko: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ApiFootballLeagueCatalog(Base):
    __tablename__ = "api_football_league_catalog"
    __table_args__ = (
        CheckConstraint("type IN ('League', 'Cup')", name="api_football_league_catalog_type_check"),
        Index("api_football_league_catalog_country_idx", "country_name"),
        Index("api_football_league_catalog_current_season_idx", "current_season"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    external_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(Text)
    country_name: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str | None] = mapped_column(Text)
    country_flag: Mapped[str | None] = mapped_column(Text)
    current_season: Mapped[int | None] = mapped_column(Integer)
    seasons: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    last_synced_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LeagueSyncTarget(Base):
    __tablename__ = "league_sync_target"
    __table_args__ = (
        UniqueConstraint("league_id", "season_year", name="league_sync_target_league_season_uq"),
        CheckConstraint("season_year >= 1900", name="league_sync_target_season_year_check"),
        CheckConstraint("fixture_limit IS NULL OR fixture_limit > 0", name="league_sync_target_fixture_limit_check"),
        Index(
            "league_sync_target_active_idx",
            "is_active",
            "league_id",
            "season_year",
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    league_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("league.id", ondelete="CASCADE"),
        nullable=False,
    )
    season_year: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    include_details: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    include_players: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    include_standings: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    fixture_limit: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
