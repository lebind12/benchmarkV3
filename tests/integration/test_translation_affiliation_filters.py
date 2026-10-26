"""Affiliation conditions must match a single related team, before pagination."""

import pytest
from sqlalchemy import select
from app.models import (
    League,
    LeagueTranslation,
    Team,
    TeamTranslation,
    Player,
    PlayerTranslation,
    PlayerSeasonStat,
    Coach,
    TeamCoach,
    TeamSeason,
    ApiFootballLeagueCatalog,
)
from tests.integration.test_streamer_management import management_client, login, target, BASE  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture()
def affiliated(management_client):  # noqa: F811 - imported pytest fixture
    client, factory = management_client
    headers = login(client)
    with factory() as session:
        catalog = session.scalar(
            select(ApiFootballLeagueCatalog).where(ApiFootballLeagueCatalog.external_id == 39)
        )
        catalog.logo_url = "https://media.api-sports.io/football/leagues/39.png"
        session.commit()
    target(client, headers)
    with factory() as session:
        epl = session.scalar(select(League).where(League.external_id == 39))
        la = League(
            external_id=140, name="La Liga", type="League", slug="scope-la", current_season=2026
        )
        cl = League(
            external_id=2, name="Champions League", type="Cup", slug="scope-cl", current_season=2026
        )
        session.add_all([la, cl])
        session.flush()
        teams = [
            Team(
                external_id=id,
                name=name,
                slug=f"scope-team-{id}",
                logo_url=f"https://media.api-sports.io/football/teams/{id}.png",
            )
            for id, name in [(42, "Arsenal"), (40, "Liverpool"), (529, "Barcelona")]
        ]
        session.add_all(teams)
        session.flush()
        ars, liv, bar = teams
        session.add_all(
            [
                TeamTranslation(team_id=ars.id, name_ko="아스널"),
                LeagueTranslation(league_id=la.id, name_ko="라리가"),
            ]
        )
        players = [
            Player(external_id=100 + i, name=name, slug=f"scope-player-{i}")
            for i, name in enumerate(["Transfer Player", "Liverpool Player", "Unlinked Player"])
        ]
        session.add_all(players)
        session.flush()
        person, other, unlinked = players
        session.add(PlayerTranslation(player_id=person.id, name_ko="조건 선수"))
        for player, team, league, year in [
            (person, ars, epl, 2026),
            (person, ars, epl, 2025),
            (person, bar, la, 2026),
            (other, liv, epl, 2026),
        ]:
            session.add(
                PlayerSeasonStat(
                    player_id=player.id,
                    team_id=team.id,
                    league_id=league.id,
                    season_year=year,
                    raw_stats={},
                )
            )
        coaches = [
            Coach(external_id=501 + i, name=name, slug=f"scope-coach-{i}")
            for i, name in enumerate(["Arsenal Coach", "Transfer Coach", "Unlinked Coach"])
        ]
        session.add_all(coaches)
        session.flush()
        session.add_all(
            [
                TeamSeason(team_id=ars.id, league_id=epl.id, season_year=2026),
                TeamSeason(team_id=bar.id, league_id=la.id, season_year=2026),
            ]
        )
        # Last observed match was a cup. EPL scope still follows the same team's league membership.
        session.add_all(
            [
                TeamCoach(
                    team_id=ars.id, coach_id=coaches[0].id, league_id=cl.id, season_year=2026
                ),
                TeamCoach(
                    team_id=ars.id, coach_id=coaches[1].id, league_id=epl.id, season_year=2026
                ),
                TeamCoach(
                    team_id=bar.id, coach_id=coaches[1].id, league_id=la.id, season_year=2026
                ),
            ]
        )
        session.commit()
    return client, headers


def test_player_affiliations_are_anded_deduplicated_and_combined_with_text_status(affiliated):
    client, headers = affiliated

    def search(**params):
        response = client.get(
            BASE + "/translations", headers=headers, params={"type": "player", **params}
        )
        assert response.status_code == 200, response.text
        return response.json()

    assert search()["total"] == 3
    assert search(league_id=39)["total"] == 2
    assert search(team_id=42)["total"] == 1
    assert search(league_id=39, team_id=529)["total"] == 0
    assert search(league_id=140, team_id=529)["total"] == 1
    assert search(league_id=39, team_id=42, query="조건", status="translated")["total"] == 1
    assert search(league_id=39, team_id=42, status="untranslated")["total"] == 0
    assert search(league_id=39, team_id=42, page=2)["items"] == []
    assert search(league_id=999999)["total"] == 0
    assert (
        client.get(
            BASE + "/translations", headers=headers, params={"type": "team", "league_id": 39}
        ).status_code
        == 422
    )
    assert (
        client.get(
            BASE + "/translations", headers=headers, params={"type": "player", "team_id": 0}
        ).status_code
        == 422
    )


def test_coach_affiliations_use_team_membership_without_cross_team_league_matches(affiliated):
    client, headers = affiliated

    def search(**params):
        response = client.get(
            BASE + "/translations", headers=headers, params={"type": "coach", **params}
        )
        assert response.status_code == 200, response.text
        return response.json()

    assert search()["total"] == 3
    assert search(league_id=39, team_id=42)["total"] == 2
    assert search(league_id=39, team_id=529)["total"] == 0
    assert search(league_id=140, team_id=529)["total"] == 1
    assert search(league_id=39, query="Arsenal")["total"] == 1
    assert search(league_id=39, page=2)["items"] == []


def test_options_cascade_from_collected_membership_and_expose_logos(affiliated):
    client, headers = affiliated
    assert (
        client.get(BASE + "/catalog", headers=headers)
        .json()["items"][0]["logo_url"]
        .endswith("/39.png")
    )
    assert (
        client.get(BASE + "/targets", headers=headers)
        .json()["items"][0]["logo_url"]
        .endswith("/39.png")
    )
    for kind in ["player", "coach"]:
        response = client.get(
            BASE + "/translations/affiliation-filters",
            headers=headers,
            params={"type": kind, "league_id": 39},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert 39 in {r["id"] for r in body["leagues"]}
        assert 140 in {r["id"] for r in body["leagues"]}
        assert 529 not in {r["id"] for r in body["teams"]}
        assert next(r for r in body["teams"] if r["id"] == 42)["name"] == "아스널"
        assert next(r for r in body["teams"] if r["id"] == 42)["logo_url"].endswith("/42.png")
        empty = client.get(
            BASE + "/translations/affiliation-filters",
            headers=headers,
            params={"type": kind, "league_id": 999999},
        ).json()
        assert empty["teams"] == []
    assert (
        client.get(
            BASE + "/translations/affiliation-filters", params={"type": "player"}
        ).status_code
        == 401
    )
