"""Tests for personal network persistence and relationship behavior."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from data.plugins.astrbot_plugin_personal_network.storage import NetworkStorage


@pytest.fixture
def storage(tmp_path: Path):
    """Provide an isolated storage instance.

    Args:
        tmp_path: Pytest temporary directory.

    Yields:
        Initialized network storage.
    """
    instance = NetworkStorage(tmp_path / "network.sqlite3")
    yield instance
    instance.close()


def test_networks_are_isolated_and_roots_are_stable(storage: NetworkStorage):
    alice_root = storage.ensure_network("alice", "Alice")
    bob_root = storage.ensure_network("bob", "Bob")

    assert alice_root != bob_root
    assert storage.ensure_network("alice", "Alice") == alice_root
    assert len(storage.get_network("alice")["characters"]) == 1
    assert len(storage.get_network("bob")["characters"]) == 1


def test_tool_batch_binds_sender_and_creates_directed_relationship(
    storage: NetworkStorage,
):
    sender = {
        "platform": "aiocqhttp",
        "user_id": "10001",
        "session_id": "group-7",
        "nickname": "Group Nick",
        "umo": "aiocqhttp:group:group-7",
    }
    result = storage.upsert_batch(
        "alice",
        [
            {
                "ref": "speaker",
                "name": "Lin",
                "aliases": ["Xiao Lin"],
                "bio": "Alice's classmate",
                "facts": ["Enjoys astronomy"],
                "current_sender": True,
            }
        ],
        [
            {
                "source": "persona",
                "target": "speaker",
                "type": "friend",
                "strength": 72,
                "status": "active",
                "description": "A trusted school friend",
                "evidence": "We have been friends since middle school.",
            }
        ],
        sender=sender,
    )

    data = storage.get_network("alice")
    person_id = result["refs"]["speaker"]
    identity = data["identities"][0]
    relationship = data["relationships"][0]
    assert identity["character_id"] == person_id
    assert identity["nicknames"][0]["nickname"] == "Group Nick"
    assert identity["nicknames"][0]["use_count"] == 1
    assert identity["session_id"] == "group-7"
    assert relationship["target_id"] == person_id
    assert relationship["strength"] == 72
    assert data["evidence"][0]["excerpt"].startswith("We have been")


def test_nicknames_are_lists_sorted_by_usage_frequency(storage: NetworkStorage):
    sender = {
        "platform": "aiocqhttp",
        "user_id": "10001",
        "session_id": "group-7",
        "nickname": "Lin",
        "umo": "aiocqhttp:group:group-7",
    }
    storage.upsert_batch(
        "alice",
        [{"ref": "speaker", "name": "Lin", "current_sender": True}],
        [],
        sender=sender,
    )
    for nickname in ("Xiao Lin", "Lin", "Xiao Lin", "Xiao Lin"):
        assert storage.record_known_sender_nickname(
            "alice",
            platform="aiocqhttp",
            user_id="10001",
            session_id="group-7",
            nickname=nickname,
        )

    identity = storage.get_network("alice")["identities"][0]
    assert [item["nickname"] for item in identity["nicknames"]] == [
        "Xiao Lin",
        "Lin",
    ]
    assert [item["use_count"] for item in identity["nicknames"]] == [3, 2]
    assert not storage.record_known_sender_nickname(
        "alice",
        platform="aiocqhttp",
        user_id="10001",
        session_id="another-group",
        nickname="Other Group Name",
    )


def test_version_one_nickname_is_migrated_to_frequency_list(tmp_path: Path):
    database_path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO schema_meta(key, value) VALUES ('version', '1');
        CREATE TABLE external_identities (
            id TEXT PRIMARY KEY,
            persona_id TEXT NOT NULL,
            character_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL DEFAULT '',
            nickname TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(persona_id, platform, user_id, session_id)
        );
        """
    )
    connection.execute(
        """INSERT INTO external_identities VALUES
           ('identity-1', 'alice', 'person-1', 'test', 'user-1', 'group-1',
            'Legacy Nick', '2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00')"""
    )
    connection.commit()
    connection.close()

    migrated = NetworkStorage(database_path)
    try:
        identity = migrated.get_network("alice")["identities"][0]
        assert identity["nicknames"] == [
            {
                "id": identity["nicknames"][0]["id"],
                "nickname": "Legacy Nick",
                "use_count": 1,
                "last_used_at": "2026-01-02T00:00:00+00:00",
            }
        ]
    finally:
        migrated.close()


def test_batch_rolls_back_when_a_relationship_reference_is_invalid(
    storage: NetworkStorage,
):
    with pytest.raises(ValueError, match="unknown character reference"):
        storage.upsert_batch(
            "alice",
            [{"ref": "new", "name": "Temporary"}],
            [
                {
                    "source": "new",
                    "target": "missing",
                    "type": "friend",
                    "strength": 1,
                }
            ],
        )

    assert [item["name"] for item in storage.get_network("alice")["characters"]] == [
        "alice"
    ]


def test_same_name_ambiguity_requires_uuid(storage: NetworkStorage):
    first_id = str(uuid.uuid4())
    second_id = str(uuid.uuid4())
    payload = {
        "characters": [
            {"id": first_id, "name": "Alex", "is_persona": False},
            {"id": second_id, "name": "Alex", "is_persona": False},
        ],
        "relationships": [],
        "evidence": [],
        "identities": [],
    }
    storage.replace_from_import("alice", payload)

    with pytest.raises(ValueError, match="ambiguous character name"):
        storage.upsert_batch("alice", [{"ref": "alex", "name": "Alex"}], [])

    result = storage.upsert_batch(
        "alice", [{"id": first_id, "ref": "alex", "name": "Alex", "bio": "First"}], []
    )
    assert result["refs"]["alex"] == first_id


def test_merge_rewires_and_deduplicates_relationships(storage: NetworkStorage):
    root = storage.ensure_network("alice")
    people = storage.upsert_batch(
        "alice",
        [{"ref": "keep", "name": "Lin"}, {"ref": "duplicate", "name": "Lynn"}],
        [
            {
                "source": "persona",
                "target": "keep",
                "type": "friend",
                "strength": 50,
                "evidence": "first",
            },
            {
                "source": "persona",
                "target": "duplicate",
                "type": "friend",
                "strength": 60,
                "evidence": "second",
            },
            {
                "source": "duplicate",
                "target": "keep",
                "type": "knows",
                "strength": 10,
            },
        ],
    )

    storage.merge_characters(
        "alice", people["refs"]["keep"], people["refs"]["duplicate"]
    )
    data = storage.get_network("alice")
    assert {item["id"] for item in data["characters"]} == {
        root,
        people["refs"]["keep"],
    }
    assert len(data["relationships"]) == 1
    assert len(data["evidence"]) == 2
    assert "Lynn" in next(
        item for item in data["characters"] if not item["is_persona"]
    )["aliases"]


def test_context_matches_alias_and_includes_one_hop(storage: NetworkStorage):
    storage.upsert_batch(
        "alice",
        [{"ref": "lin", "name": "Lin", "aliases": ["Xiao Lin"], "facts": ["Likes tea"]}],
        [
            {
                "source": "persona",
                "target": "lin",
                "type": "friend",
                "strength": 80,
                "description": "Long-time friend",
            }
        ],
    )

    context = storage.build_context(
        "alice",
        "How is Xiao Lin?",
        platform="test",
        user_id="none",
        max_characters=8,
        max_relationships=16,
        max_chars=6000,
    )
    assert "Likes tea" in context
    assert "RELATION alice -> Lin: friend" in context
    assert storage.build_context(
        "alice",
        "Nobody relevant",
        platform="test",
        user_id="none",
        max_characters=8,
        max_relationships=16,
        max_chars=6000,
    ) == ""


def test_import_merges_without_deleting_local_data(storage: NetworkStorage):
    local = storage.upsert_batch("alice", [{"ref": "local", "name": "Local"}], [])
    imported_id = str(uuid.uuid4())
    payload = {
        "characters": [{"id": imported_id, "name": "Imported", "is_persona": False}],
        "relationships": [],
        "evidence": [],
        "identities": [],
    }

    storage.replace_from_import("alice", payload)
    ids = {item["id"] for item in storage.get_network("alice")["characters"]}
    assert local["refs"]["local"] in ids
    assert imported_id in ids


def test_import_cannot_overwrite_another_personas_uuid(storage: NetworkStorage):
    created = storage.upsert_batch("alice", [{"ref": "person", "name": "Alice Person"}], [])
    malicious = {
        "characters": [
            {
                "id": created["refs"]["person"],
                "name": "Overwritten",
                "is_persona": False,
            }
        ],
        "relationships": [],
        "evidence": [],
        "identities": [],
    }

    with pytest.raises(ValueError, match="another persona"):
        storage.replace_from_import("bob", malicious)
    original = next(
        item
        for item in storage.get_network("alice")["characters"]
        if item["id"] == created["refs"]["person"]
    )
    assert original["name"] == "Alice Person"


def test_version_two_import_preserves_nickname_frequency(
    storage: NetworkStorage, tmp_path: Path
):
    sender = {
        "platform": "test",
        "user_id": "user-1",
        "session_id": "group-1",
        "nickname": "Lin",
        "umo": "test:group:group-1",
    }
    storage.upsert_batch(
        "alice",
        [{"ref": "speaker", "name": "Lin", "current_sender": True}],
        [],
        sender=sender,
    )
    storage.record_known_sender_nickname(
        "alice",
        platform="test",
        user_id="user-1",
        session_id="group-1",
        nickname="Xiao Lin",
    )
    storage.record_known_sender_nickname(
        "alice",
        platform="test",
        user_id="user-1",
        session_id="group-1",
        nickname="Xiao Lin",
    )
    payload = storage.get_network("alice")

    restored = NetworkStorage(tmp_path / "restored.sqlite3")
    try:
        restored.replace_from_import("alice", payload)
        nicknames = restored.get_network("alice")["identities"][0]["nicknames"]
        assert [(item["nickname"], item["use_count"]) for item in nicknames] == [
            ("Xiao Lin", 2),
            ("Lin", 1),
        ]
    finally:
        restored.close()


def test_export_shape_is_json_serializable(storage: NetworkStorage):
    storage.upsert_batch("alice", [{"ref": "lin", "name": "Lin"}], [])
    encoded = json.dumps(storage.get_network("alice"), ensure_ascii=False)
    assert "Lin" in encoded
