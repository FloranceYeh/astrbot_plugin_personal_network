from __future__ import annotations

from pathlib import Path

import pytest

from data.plugins.astrbot_plugin_personal_network.main import PersonalNetworkPlugin
from data.plugins.astrbot_plugin_personal_network.storage import NetworkStorage


@pytest.mark.asyncio
async def test_plugin_context_exposes_stable_character_ids(tmp_path: Path):
    plugin = object.__new__(PersonalNetworkPlugin)
    plugin.storage = NetworkStorage(tmp_path / "network.sqlite3")
    try:
        created = plugin.storage.upsert_batch(
            "alice",
            [{"ref": "lin", "name": "Lin", "bio": "College friend"}],
            [
                {
                    "source": "persona",
                    "target": "lin",
                    "type": "friend",
                    "strength": 80,
                }
            ],
        )

        context = await plugin.get_context_for_plugin("alice", max_chars=4000)

        assert created["refs"]["lin"] in context
        assert "name=Lin" in context
        assert "friend" in context
    finally:
        plugin.storage.close()


@pytest.mark.asyncio
async def test_plugin_event_api_rejects_non_plugin_sources(tmp_path: Path):
    plugin = object.__new__(PersonalNetworkPlugin)
    plugin.storage = NetworkStorage(tmp_path / "network.sqlite3")
    try:
        with pytest.raises(ValueError, match="AstrBot plugin"):
            await plugin.record_life_event_from_plugin(
                "alice",
                participant_ids=["missing"],
                event_type="meeting",
                summary="Met someone",
                occurred_at="2026-07-28T12:00:00+08:00",
                source="untrusted",
                source_key="event-1",
            )
    finally:
        plugin.storage.close()
