"""DB catalog search must find Korean aliases without inventing competitions."""

import pytest
from app.models import ApiFootballLeagueCatalog, League, LeagueTranslation
from tests.integration.test_streamer_management import management_client, login, BASE  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture()
def discovery(management_client):  # noqa: F811
    client, factory = management_client
    with factory() as session:
        for ident, name, country, kind in [
            (7, "Asian Cup", "World", "Cup"),
            (23, "EAFF E-1 Football Championship", "World", "Cup"),
            (803, "Asian Games", "World", "Cup"),
            (897, "Asian Cup Women", "World", "Cup"),
            (900039, "Premier League", "Sample Country", "League"),
            (140, "Different Source Name", "Spain", "League"),
        ]:
            session.add(
                ApiFootballLeagueCatalog(
                    external_id=ident,
                    name=name,
                    country_name=country,
                    type=kind,
                    seasons=[{"year": 2026, "current": True}, {"year": 2025}],
                )
            )
        session.commit()
    return client, factory, login(client)


def search(discovery, **params):
    client, _, headers = discovery
    response = client.get(BASE + "/catalog", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_aliases_and_exact_competition_selection(discovery):
    assert search(discovery, query="동아시아")["items"][0]["id"] == 23
    assert search(discovery, query="e-1")["items"][0]["id"] == 23
    assert search(discovery, query="아시안게임")["items"][0]["id"] == 803
    rows = search(discovery, query="아시안컵")["items"]
    assert rows[0]["id"] == 7 and {r["id"] for r in rows} == {7, 23, 897}
    assert next(r for r in rows if r["id"] == 897)["name"] == "여자 아시안컵"
    assert search(discovery, query="EPL")["items"][0]["id"] == 39
    assert search(discovery, query="잉글랜드 프리미어리그")["items"][0]["id"] == 39
    assert (
        search(discovery, query="라리가")["items"] == []
    )  # source name mismatch: no guessed alias
    assert search(discovery, query="%")["items"] == []  # wildcard characters are literal


def test_country_type_shortcuts_and_id_are_applied_before_pagination(discovery):
    assert search(discovery, query="Premier League")["total"] == 2
    result = search(discovery, query="Premier League", country="England", type="League")
    assert result["total"] == 1 and result["items"][0]["country_label"] == "잉글랜드"
    assert search(discovery, query="Premier League", type="Cup")["total"] == 0
    assert search(discovery, id=7, query="unmatched")["items"][0]["id"] == 7
    assert search(discovery, id=7, country="England")["total"] == 0
    assert {r["id"] for r in search(discovery, group="asia")["items"]} == {7, 23, 803, 897}
    assert search(discovery, group="club")["items"] == []
    assert {c["value"] for c in result["countries"]} == {
        "World",
        "England",
        "Spain",
        "Sample Country",
    }
    assert result["catalog_total"] == 7


def test_human_translation_precedence_including_intentional_blank(discovery):
    client, factory, headers = discovery
    with factory() as session:
        league = League(external_id=7, name="Asian Cup", type="Cup", slug="catalog-asian-cup")
        session.add(league)
        session.flush()
        translation = LeagueTranslation(
            league_id=league.id,
            name_ko="직접 수정 대회",
            short_name_ko="직접 약칭",
            human_modified=True,
        )
        session.add(translation)
        session.commit()
        assert search(discovery, query="직접약칭")["items"][0]["name"] == "직접 수정 대회"
        response = client.patch(
            BASE + f"/translations/league/{league.id}",
            headers=headers,
            json={"name_ko": None, "short_name_ko": None, "expected_version": translation.version},
        )
        assert response.status_code == 200, response.text
    assert search(discovery, id=7)["items"][0]["name"] == "Asian Cup"
    assert 7 in [
        row["id"] for row in search(discovery, query="아시안컵")["items"]
    ]  # alias retained below translated entries


def test_korean_display_names_rank_before_untranslated_results_before_paging(discovery):
    _, factory, _ = discovery
    with factory() as session:
        for ident, name_ko in [(39, None), (900039, "한국어 프리미어리그")]:
            league = League(
                external_id=ident, name="Premier League", type="League", slug=f"rank-{ident}"
            )
            session.add(league)
            session.flush()
            session.add(
                LeagueTranslation(league_id=league.id, name_ko=name_ko, human_modified=True)
            )
        session.commit()
    result = search(discovery, query="Premier League", page_size=1)
    assert result["total"] == 2
    assert result["items"][0]["id"] == 900039
    assert (
        search(discovery, query="Premier League", page_size=1, page=2)["items"][0]["name"]
        == "Premier League"
    )
    assert result["countries"][-1] == {"value": "Sample Country", "label": "Sample Country"}
    assert all(
        any("가" <= char <= "힣" for char in country["label"])
        for country in result["countries"][:-1]
    )


def test_all_results_remain_reachable_and_parameters_are_bounded(discovery):
    client, factory, headers = discovery
    with factory() as session:
        session.add_all(
            [
                ApiFootballLeagueCatalog(
                    external_id=990000 + i,
                    name=f"Search Test {i:03}",
                    type="Cup",
                    country_name="World",
                )
                for i in range(125)
            ]
        )
        session.commit()
    first = search(discovery, query="Search Test", page_size=100)
    second = search(discovery, query="Search Test", page_size=100, page=2)
    assert first["total"] == 125 and len(first["items"]) == 100 and len(second["items"]) == 25
    assert {r["id"] for r in first["items"]}.isdisjoint({r["id"] for r in second["items"]})
    for params in [{"page_size": 101}, {"page": 0}, {"group": "unknown"}, {"type": "unknown"}]:
        assert client.get(BASE + "/catalog", headers=headers, params=params).status_code == 422
    assert client.get(BASE + "/catalog").status_code == 401


def test_short_alias_does_not_match_across_word_boundaries(discovery):
    _, factory, _ = discovery
    with factory() as session:
        session.add(
            ApiFootballLeagueCatalog(
                external_id=888888,
                name="National League - Play-offs",
                type="Cup",
                country_name="England",
            )
        )
        session.commit()
    assert [row["id"] for row in search(discovery, query="EPL")["items"]] == [39]
    assert search(discovery, query="prem", country="England")["items"][0]["id"] == 39
