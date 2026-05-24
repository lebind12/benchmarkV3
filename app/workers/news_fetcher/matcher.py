"""Keyword matching for ESPN Soccer RSS rows."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from app.workers.news_fetcher import TARGET_LEAGUE_KEYWORDS


@dataclass(frozen=True)
class Keyword:
    value: str
    kind: str
    external_id: int


@dataclass
class MatchResult:
    matched: bool
    tags: dict[str, list[int]] = field(default_factory=dict)


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _contains_keyword(text_norm: str, keyword: str) -> bool:
    keyword_norm = _norm(keyword)
    if len(keyword_norm) < 4:
        return False
    # Word-ish boundary avoids short code false positives while still working
    # with spaces and punctuation around team/player names.
    return re.search(rf"(?<!\w){re.escape(keyword_norm)}(?!\w)", text_norm) is not None


def build_keyword_index(session, *, include_players: bool = True) -> list[Keyword]:
    keywords: list[Keyword] = []

    for external_id, names in TARGET_LEAGUE_KEYWORDS.items():
        for name in names:
            keywords.append(Keyword(value=name, kind="leagues", external_id=external_id))

    team_rows = session.execute(
        text(
            """
            SELECT DISTINCT t.external_id, t.name, t.code
            FROM team t
            JOIN team_season ts ON ts.team_id = t.id
            JOIN league l ON l.id = ts.league_id
            WHERE l.is_active = true
            """
        )
    ).mappings()
    for row in team_rows:
        keywords.append(Keyword(value=row["name"], kind="teams", external_id=row["external_id"]))
        code = row.get("code")
        if code and len(code) >= 3:
            keywords.append(Keyword(value=code, kind="teams", external_id=row["external_id"]))

    if include_players:
        player_rows = session.execute(
            text(
                """
                SELECT DISTINCT p.external_id, p.name, p.firstname, p.lastname
                FROM player p
                JOIN team t ON t.id = p.current_team_id
                JOIN team_season ts ON ts.team_id = t.id
                JOIN league l ON l.id = ts.league_id
                WHERE l.is_active = true
                """
            )
        ).mappings()
        for row in player_rows:
            # Use the full API-Football display name only. Firstname/lastname
            # alone creates broad false positives such as Diego, Austin, or
            # Robert in unrelated soccer news.
            value = row["name"]
            if value and len(str(value).strip()) >= 5:
                keywords.append(
                    Keyword(value=str(value), kind="players", external_id=row["external_id"])
                )

    return keywords


def match_article(*, title: str, summary: str | None, keywords: list[Keyword]) -> MatchResult:
    text_norm = _norm(f"{title} {summary or ''}")
    tags: dict[str, set[int]] = {}
    for keyword in keywords:
        if _contains_keyword(text_norm, keyword.value):
            tags.setdefault(keyword.kind, set()).add(keyword.external_id)

    return MatchResult(
        matched=bool(tags),
        tags={key: sorted(values) for key, values in tags.items()},
    )


def tags_json(tags: dict[str, list[int]]) -> dict[str, Any]:
    return {key: values for key, values in tags.items() if values}
