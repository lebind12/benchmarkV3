from __future__ import annotations

from pathlib import Path

from app.workers.daily_sync.translation_seed import iter_player_translation_seed


def test_iter_player_translation_seed_parses_expected_columns(tmp_path: Path):
    csv_path = tmp_path / "translations.csv"
    csv_path.write_text(
        '"id","player_id","team_id","eng_name","kor_name","kor_short_name","created_at"\n'
        "1,16797,1577,Mohamed El-Shenawy,모하메드 엘셰나위,엘셰나위,2025-06-15\n",
        encoding="utf-8",
    )

    rows = list(iter_player_translation_seed(csv_path))

    assert len(rows) == 1
    assert rows[0].player_external_id == 16797
    assert rows[0].team_external_id == 1577
    assert rows[0].eng_name == "Mohamed El-Shenawy"
    assert rows[0].name_ko == "모하메드 엘셰나위"
    assert rows[0].short_name_ko == "엘셰나위"


def test_iter_player_translation_seed_skips_rows_without_player_id(tmp_path: Path):
    csv_path = tmp_path / "translations.csv"
    csv_path.write_text(
        '"id","player_id","team_id","eng_name","kor_name","kor_short_name","created_at"\n'
        "1,,1577,Unknown,언노운,언노운,2025-06-15\n",
        encoding="utf-8",
    )

    assert list(iter_player_translation_seed(csv_path)) == []
