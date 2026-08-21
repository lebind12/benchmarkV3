from __future__ import annotations

import pytest

from app.services.broadcast import BROADCAST_OVERLAY_TTL_SECONDS, _live_block_ttl

pytestmark = pytest.mark.unit


def test_empty_lineups_use_short_ttl() -> None:
    assert _live_block_ttl("lineups", [], 300) == BROADCAST_OVERLAY_TTL_SECONDS


def test_populated_lineups_keep_default_ttl() -> None:
    assert _live_block_ttl("lineups", [{"team": {"id": 1}}], 300) == 300


def test_other_empty_live_blocks_keep_default_ttl() -> None:
    assert _live_block_ttl("events", [], 10) == 10
