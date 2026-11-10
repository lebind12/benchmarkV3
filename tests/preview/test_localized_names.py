"""이름 표시 해석기(`app/preview/localized_names.py`) 집중 검사.

수용 기준과 검사 대응:

1. **DB 한국어 값이 영어보다 우선한다** — 팀·주목 선수 모두.
2. **ID 공간을 섞지 않는다** — 같은 숫자라도 다른 팀·선수를 고르지 않는다.
3. **애매하면 고르지 않는다** — 동률 후보가 있으면 원래 이름을 유지한다.
4. **한국어 값이 없으면 원래 이름 유지 + 사유 기록** — 지어내지 않는다.
5. **본문 치환이 다른 텍스트·동일성을 깨지 않는다** — URL, 다른 선수 이름,
   짧은 이름이 긴 이름 안에서 잘못 바뀌지 않는다.

DB를 쓰지 않는다. 합성 이름 행으로만 검사한다(운영 DB 읽기는 별도 확인이며
여기서 반복하지 않는다).
"""

from __future__ import annotations

import pytest

from app.preview.localized_names import (
    DbNameLookup,
    DisplayNames,
    LocalizedNameIndex,
    NameReason,
    NameSource,
    PlayerNameRow,
    TeamNameRow,
    normalize_name,
)


def _index() -> LocalizedNameIndex:
    """합성 이름 묶음. 실제 DB 값과 같은 모양(영어 + 한국어 번역)만 쓴다."""
    teams = (
        TeamNameRow(
            team_id=13,
            external_id=50,
            english_name="Manchester City",
            name_ko="맨체스터 시티",
            short_name_ko="맨시티",
        ),
        TeamNameRow(
            team_id=4,
            external_id=36,
            english_name="Fulham",
            name_ko="풀럼",
            short_name_ko="풀럼",
        ),
    )
    players = (
        PlayerNameRow(
            player_id=533,
            external_id=1100,
            english_name="E. Haaland",
            firstname="Erling",
            lastname="Braut Haaland",
            current_team_id=13,
            name_ko="엘링 홀란드",
            short_name_ko="홀란드",
        ),
        PlayerNameRow(
            player_id=124,
            external_id=1455,
            english_name="A. Iwobi",
            firstname="Alexander",
            lastname="Iwobi",
            current_team_id=4,
            name_ko="알렉산더 츄카 이워비",
            short_name_ko="이워비",
        ),
        PlayerNameRow(
            player_id=138,
            external_id=195106,
            english_name="Rodrigo Muniz",
            firstname="Rodrigo",
            lastname="Muniz Carvalho",
            current_team_id=4,
            name_ko="로드리고 무니즈",
            short_name_ko="무니즈",
        ),
        # 성만 같은 다른 선수. `name`이 `Muniz`와 정확히 같지는 않으므로 둘 다
        # 성 일치(등급 5)에 걸려 동률이 된다 — 고르면 안 되는 경우다.
        PlayerNameRow(
            player_id=900,
            external_id=9900,
            english_name="Joao Muniz",
            firstname="Joao",
            lastname="Muniz",
            current_team_id=13,
            name_ko="주앙 무니즈",
        ),
    )
    return LocalizedNameIndex(teams=teams, players=players)


def test_db_korean_names_win_over_english_for_teams_and_hot_players() -> None:
    """DB 한국어 값이 영어 표기보다 우선한다(팀 제목 + 주목 선수 + 본문)."""
    names = DisplayNames(_index())

    label = names.fixture_label(home_team_id=13, away_team_id=4)
    assert label == "맨체스터 시티 vs 풀럼"

    result = names.watch_players(
        [
            {"player": "Erling Haaland", "team": "Manchester City", "reason": "결정력"},
            {"player": "Alex Iwobi", "team": "Fulham", "reason": "창의성"},
            {"player": "Rodrigo Muniz", "team": "Fulham", "reason": "공격"},
        ],
        scope_team_ids=[13, 4],
    )
    assert [row["player"] for row in result.rows] == [
        "엘링 홀란드",
        "알렉산더 츄카 이워비",
        "로드리고 무니즈",
    ]
    # 팀 표기도 DB 값이다.
    assert [row["team"] for row in result.rows] == ["맨체스터 시티", "풀럼", "풀럼"]
    # 원래 항목의 다른 키는 그대로 남는다.
    assert [row["reason"] for row in result.rows] == ["결정력", "창의성", "공격"]
    assert result.unmapped == ()

    body = (
        "Manchester City와 Fulham의 맞대결입니다. "
        "Manchester City는 최근 2연승입니다. Erling Haaland(Manchester City)가 주목됩니다."
    )
    rewritten = names.rewrite_body(body)
    assert "맨체스터 시티와 풀럼의 맞대결입니다." in rewritten
    assert "엘링 홀란드(맨체스터 시티)가 주목됩니다." in rewritten
    # 원래 영어 이름은 남지 않는다.
    assert "Manchester City" not in rewritten
    # 같은 선수가 여러 번 나와도 같은 값으로 바뀐다.
    repeated = names.rewrite_body("Erling Haaland가 있고, Erling Haaland가 또 있다.")
    assert repeated == "엘링 홀란드가 있고, 엘링 홀란드가 또 있다."


def test_source_marks_db_korean_and_original_separately() -> None:
    """표시 값의 출처를 남긴다. 모델이 만든 한국어가 DB 값으로 둔갑하지 않는다."""
    names = DisplayNames(_index())
    resolved = names.resolve_team("Manchester City", team_id=13)
    assert resolved is not None
    assert resolved.source is NameSource.DB_KOREAN
    assert resolved.display_name == "맨체스터 시티"

    player = names.resolve_player("E. Haaland", player_id=533).player
    assert player is not None
    assert player.source is NameSource.DB_KOREAN
    assert player.display_name == "엘링 홀란드"


def test_id_space_is_not_mixed_between_internal_and_external_ids() -> None:
    """DB 기본키와 API-Football ID를 섞으면 다른 팀을 고르지 않고 미해결로 돌려준다."""
    names = DisplayNames(_index())

    # internal 공간에서 50은 어떤 팀도 아니다(13·4만 있다). external 50은 맨시티다.
    internal = names.resolve_team("Some Club", team_id=50, id_space="internal")
    assert internal is not None
    # 다른 공간의 같은 숫자로 DB 한국어 이름을 붙이지 않는다.
    assert internal.source is NameSource.ORIGINAL
    assert internal.display_name == "Some Club"
    assert internal.team_id is None

    # 이름 없이 해석할 수 없는 ID만 주면 값을 지어내지 않고 None을 돌려준다.
    assert names.resolve_team(team_id=50, id_space="internal") is None

    external = names.resolve_team(team_id=50, id_space="external")
    assert external is not None
    assert external.display_name == "맨체스터 시티"
    assert external.team_id == 13

    # 선수도 같은 규칙이다. internal 1100은 없다.
    mixed = names.resolve_player("E. Haaland", player_id=1100, id_space="internal")
    assert mixed.player is None
    assert mixed.display_name == "E. Haaland"
    assert mixed.unmapped is not None
    assert mixed.unmapped.reason is NameReason.NOT_FOUND

    right = names.resolve_player("E. Haaland", player_id=1100, id_space="external")
    assert right.player is not None
    assert right.display_name == "엘링 홀란드"


def test_ambiguous_candidates_are_not_picked_at_random() -> None:
    """동률 후보가 둘 이상이면 아무나 고르지 않고 원래 이름을 유지한다."""
    names = DisplayNames(_index())
    # `Muniz`는 두 선수의 성이다. 범위를 전체로 두면 고르지 않아야 한다.
    result = names.resolve_player("Muniz")
    assert result.player is None
    assert result.display_name == "Muniz"
    assert result.unmapped is not None
    assert result.unmapped.reason is NameReason.AMBIGUOUS

    # 팀 힌트로 범위를 좁히면 그 팀 선수로 확정된다.
    scoped = names.resolve_player("Rodrigo Muniz", team_hint="Fulham")
    assert scoped.player is not None
    assert scoped.display_name == "로드리고 무니즈"


def test_missing_korean_value_keeps_original_with_reason() -> None:
    """DB에 한국어 값이 없으면 원래 이름을 유지하고 사유를 남긴다(지어내지 않음)."""
    index = LocalizedNameIndex(
        teams=(
            TeamNameRow(team_id=7, external_id=42, english_name="Arsenal", name_ko=None),
        ),
        players=(
            PlayerNameRow(
                player_id=1,
                external_id=11,
                english_name="No Korean",
                firstname="No",
                lastname="Korean",
                current_team_id=7,
                name_ko=None,
            ),
        ),
    )
    names = DisplayNames(index)
    team = names.resolve_team(team_id=7)
    assert team is not None
    assert team.display_name == "Arsenal"
    assert team.source is NameSource.ORIGINAL

    player = names.resolve_player("No Korean", team_hint="Arsenal")
    assert player.player is None or player.player.display_name == "No Korean"
    assert player.display_name == "No Korean"
    reasons = {item.reason for item in names.unmapped}
    assert NameReason.DB_KOREAN_MISSING in reasons


def test_unknown_name_is_reported_not_replaced() -> None:
    """저장된 이름과 맞지 않으면 원래 표기를 유지하고 미해결로 남긴다."""
    names = DisplayNames(_index())
    result = names.resolve_player("Someone Else", team_hint="Fulham")
    assert result.player is None
    assert result.display_name == "Someone Else"
    assert result.unmapped is not None
    assert result.unmapped.reason is NameReason.NOT_FOUND


def test_body_rewrite_preserves_urls_and_unrelated_text() -> None:
    """치환이 URL·다른 고유명사·문장부호를 건드리지 않는다."""
    names = DisplayNames(_index())
    body = (
        "출처: https://example.com/Manchester-City/Erling-Haaland?q=Fulham . "
        "Fulhamer는 다른 낱말이고, Manchester Cityzens도 다른 낱말입니다. "
        "맨체스터 시티는 이미 한국어입니다."
    )
    rewritten = names.rewrite_body(body)
    # URL은 그대로다.
    assert "https://example.com/Manchester-City/Erling-Haaland?q=Fulham" in rewritten
    # 다른 낱말 안의 부분 문자열은 바뀌지 않는다.
    assert "Fulhamer" in rewritten
    assert "Manchester Cityzens" in rewritten
    # 이미 한국어인 표기는 그대로다.
    assert "맨체스터 시티는 이미 한국어입니다." in rewritten


def test_short_name_does_not_replace_inside_another_player_name() -> None:
    """짧은 성이 다른 선수의 긴 이름 안에서 따로 바뀌지 않는다."""
    names = DisplayNames(_index())
    # `Muniz`(다른 선수 성, 동률)는 등록되지 않으므로 `Rodrigo Muniz`만 통째로 바뀐다.
    body = "Rodrigo Muniz가 슈팅했습니다. Muniz는 다른 선수입니다."
    rewritten = names.rewrite_body(body)
    assert rewritten.startswith("로드리고 무니즈가 슈팅했습니다.")
    # 확정되지 않은 짧은 성은 그대로 둔다(무작위 치환 금지).
    assert "Muniz는 다른 선수입니다." in rewritten


def test_repeated_mentions_and_team_short_name_are_handled() -> None:
    """같은 표기가 반복되고 짧은 한국어 팀 이름이 있어도 한 번만 훑는다."""
    names = DisplayNames(_index())
    names.resolve_team(team_id=13)
    body = "맨시티는 맨시티답게 Manchester City답게 움직였습니다."
    rewritten = names.rewrite_body(body)
    assert "Manchester City" not in rewritten
    assert rewritten.count("맨체스터 시티") >= 1


def test_confirmed_player_surface_is_rewritten_but_unconfirmed_is_not() -> None:
    """확인한 표기만 본문에서 바뀐다. 확인하지 않은 모델 표기는 추측으로 바꾸지 않는다."""
    body = "Alex Iwobi(풀럼)가 뛰었고 A. Iwobi도 뛰었습니다."

    # 확인 없이 바로 치환하면 DB 표기만 바뀐다(모델 표기는 그대로).
    plain = DisplayNames(_index()).rewrite_body(body)
    assert "A. Iwobi" not in plain
    assert "Alex Iwobi" in plain

    # 화면에 낼 선수를 먼저 확인하면 그 표기도 같은 값으로 바뀐다.
    names = DisplayNames(_index())
    confirmed = names.confirm_player("Alex Iwobi", team_hint="Fulham")
    assert confirmed.player is not None
    rewritten = names.rewrite_body(body)
    assert "Alex Iwobi" not in rewritten
    assert rewritten.count("알렉산더 츄카 이워비") == 2


def test_bare_surname_is_never_registered_for_body_rewriting() -> None:
    """성 단독 표기는 본문 치환 대상이 아니다(이름이 깨지는 것을 막는다)."""
    names = DisplayNames(_index())
    names.confirm_player("Rodrigo Muniz", team_hint="Fulham")
    surfaces = {term.surface for term in names._build_terms()}  # noqa: SLF001 - 표기 목록 확인
    assert "Muniz" not in surfaces
    assert "Rodrigo Muniz" in surfaces
    # `Alex Iwobi` 같은 다른 선수 이름이 성 치환으로 깨지지 않는다.
    assert names.rewrite_body("Alex Iwobi는 그대로입니다.") == "Alex Iwobi는 그대로입니다."


def test_unverified_reference_falls_back_to_name_instead_of_blocking() -> None:
    """검증되지 않은 참조(모델이 적은 player_ref)는 버리고 이름으로 확인한다.

    실제 통합(R4 주목선수 모듈)에서 모델이 숫자를 잘못 적어도 확실한 한국어 이름을
    포기하지 않도록 하는 경로다. 반대로 신뢰 ID(기본값)는 기존처럼 엄격하다.
    """
    index = _index()

    hinted = DisplayNames(index).resolve_player(
        "Erling Haaland",
        team_hint="Manchester City",
        scope_team_ids=[13, 4],
        player_id=999_999,
        id_space="internal",
        id_is_hint=True,
    )
    assert hinted.player is not None
    assert hinted.display_name == "엘링 홀란드"

    strict = DisplayNames(index).resolve_player(
        "Erling Haaland",
        scope_team_ids=[13, 4],
        player_id=999_999,
        id_space="internal",
    )
    assert strict.player is None
    assert strict.display_name == "Erling Haaland"
    assert strict.unmapped is not None
    assert strict.unmapped.reason is NameReason.NOT_FOUND


def test_id_and_name_pointing_at_different_players_is_a_conflict() -> None:
    """ID와 이름이 다른 선수를 가리키면 어느 쪽도 임의로 고르지 않는다."""
    names = DisplayNames(_index())
    # 533은 하엘란트인데 이름은 다른 선수(무니즈)를 가리킨다.
    result = names.resolve_player(
        "Rodrigo Muniz", team_hint="Fulham", scope_team_ids=[13, 4],
        player_id=533, id_space="internal",
    )
    assert result.player is None
    assert result.display_name == "Rodrigo Muniz"
    assert result.unmapped is not None
    assert result.unmapped.reason is NameReason.CONFLICT


def test_lookup_refuses_unbounded_reads() -> None:
    """범위 없는 전체 조회를 거부한다(필요한 엔티티만 읽는다)."""
    lookup = DbNameLookup.__new__(DbNameLookup)  # 연결 없이 인자 검사만 한다
    with pytest.raises(ValueError):
        DbNameLookup.load_teams(lookup)  # type: ignore[misc]
    with pytest.raises(ValueError):
        DbNameLookup.load_players(lookup)  # type: ignore[misc]


def test_normalize_name_handles_accents_case_and_html_entities() -> None:
    """매칭용 정규화는 표기 차이만 줄인다(이름을 새로 만들지 않는다)."""
    assert normalize_name("E.  Haaland") == "e haaland"
    assert normalize_name("HAALAND") == normalize_name("haaland")
    # 실제 DB 값에 HTML 엔티티가 저장돼 있다(`N. O&apos;Reilly`).
    assert normalize_name("N. O&apos;Reilly") == normalize_name("N. O'Reilly")
    assert normalize_name("Kovačić") == normalize_name("Kovacic")


def test_hot_player_payload_with_only_english_name_and_team_resolves() -> None:
    """원래 주목 선수 항목은 영어 이름과 팀만 있어도 팀 범위에서 확정된다."""
    names = DisplayNames(_index())
    # 모델은 성만 쓰기도 하고(`Haaland`), 초기+성(`E. Haaland`)을 쓰기도 한다.
    for payload_name in ("Erling Haaland", "E. Haaland", "Haaland"):
        result = names.resolve_player(payload_name, team_hint="Manchester City")
        assert result.player is not None, payload_name
        assert result.display_name == "엘링 홀란드"

    # 팀 범위 밖 선수를 다른 팀 후보로 확정하지 않는다(범위 우선).
    wrong_scope = DisplayNames(_index()).resolve_player(
        "Erling Haaland", scope_team_ids=[4]
    )
    assert wrong_scope.player is None
    assert wrong_scope.display_name == "Erling Haaland"


def test_player_without_team_hint_uses_supplied_scope_only() -> None:
    """팀 힌트가 없으면 넘긴 경기 범위 안에서만 찾는다."""
    names = DisplayNames(_index())
    result = names.resolve_player("Alex Iwobi", scope_team_ids=[4])
    assert result.player is not None
    assert result.display_name == "알렉산더 츄카 이워비"

    outside = DisplayNames(_index()).resolve_player("Alex Iwobi", scope_team_ids=[13])
    assert outside.player is None


def test_watch_players_keeps_unresolved_original_and_reason() -> None:
    """해석하지 못한 주목 선수는 원래 이름을 유지하고 사유를 모아 돌려준다."""
    names = DisplayNames(_index())
    result = names.watch_players(
        [
            {"player": "Erling Haaland", "team": "Manchester City", "reason": "a"},
            {"player": "Unknown Player", "team": "Fulham", "reason": "b"},
        ],
        scope_team_ids=[13, 4],
    )
    assert result.rows[0]["player"] == "엘링 홀란드"
    assert result.rows[1]["player"] == "Unknown Player"
    assert result.rows[1]["reason"] == "b"
    assert [item.reason for item in result.unmapped] == [NameReason.NOT_FOUND]


def test_korean_short_form_is_not_merged_into_another_korean_name() -> None:
    """본문의 한국어 짧은 이름(`이워비`)이 다른 한국어 이름에 붙어 있으면 건드리지 않는다."""
    names = DisplayNames(_index())
    body = "풀럼의 에이스 알렉스 이워비의 창의성과 로서 맨시티의 압박."
    rewritten = names.rewrite_body(body)
    # 한국어가 바로 붙은 짧은 표기는 그대로 둔다(없는 이름을 합성하지 않는다).
    assert "알렉스 이워비" in rewritten
    # 띄어 쓴 독립 표기는 DB 값으로 바뀐다.
    assert "로서 맨체스터 시티의 압박" in rewritten


def test_bare_korean_fragment_is_not_replaced_when_attached() -> None:
    """앞 한국어 낱말에 **붙어 있는** 짧은 표기는 더 큰 낱말로 보고 바꾸지 않는다."""
    names = DisplayNames(_index())
    # `슈퍼맨시티`처럼 앞 낱말에 붙은 표기는 그 낱말의 일부다.
    rewritten = names.rewrite_body("슈퍼맨시티 응원. 맨시티는 이겼습니다.")
    assert "슈퍼맨시티 응원." in rewritten
    # 띄어 쓴 독립 표기는 DB 값으로 바뀐다.
    assert "맨체스터 시티는 이겼습니다." in rewritten


def test_replacement_is_applied_once_and_never_reprocessed() -> None:
    """치환 결과를 다시 훑지 않는다(중복 치환·문장 손상 없음)."""
    names = DisplayNames(_index())
    body = "Manchester City vs Fulham. Manchester City won."
    rewritten = names.rewrite_body(body)
    assert rewritten == "맨체스터 시티 vs 풀럼. 맨체스터 시티 won."
    # 같은 문장을 두 번 넘겨도 결과가 안정적이다(멱등).
    assert names.rewrite_body(rewritten) == rewritten
