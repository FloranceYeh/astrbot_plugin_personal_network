"""SQLite persistence for persona-scoped relationship networks."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

VALID_RELATIONSHIP_STATUSES = {"active", "ended", "uncertain"}
CHARACTER_TEXT_FIELDS = ("bio", "personality", "notes")
CHARACTER_LIST_FIELDS = ("aliases", "preferences", "facts")


class NetworkStorage:
    """Persist and query persona relationship networks.

    Args:
        database_path: SQLite database path in the plugin data directory.
    """

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(database_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._initialize()

    def _initialize(self) -> None:
        """Create the latest schema and migrate legacy nickname values."""
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('version', '2');

                CREATE TABLE IF NOT EXISTS networks (
                    persona_id TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    persona_missing INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS characters (
                    id TEXT PRIMARY KEY,
                    persona_id TEXT NOT NULL REFERENCES networks(persona_id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    aliases TEXT NOT NULL DEFAULT '[]',
                    bio TEXT NOT NULL DEFAULT '',
                    personality TEXT NOT NULL DEFAULT '',
                    preferences TEXT NOT NULL DEFAULT '[]',
                    facts TEXT NOT NULL DEFAULT '[]',
                    notes TEXT NOT NULL DEFAULT '',
                    avatar_filename TEXT,
                    is_persona INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_characters_persona
                    ON characters(persona_id);

                CREATE TABLE IF NOT EXISTS external_identities (
                    id TEXT PRIMARY KEY,
                    persona_id TEXT NOT NULL REFERENCES networks(persona_id) ON DELETE CASCADE,
                    character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
                    platform TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    nickname TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(persona_id, platform, user_id, session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_identities_lookup
                    ON external_identities(persona_id, platform, user_id);

                CREATE TABLE IF NOT EXISTS identity_nicknames (
                    id TEXT PRIMARY KEY,
                    identity_id TEXT NOT NULL REFERENCES external_identities(id) ON DELETE CASCADE,
                    nickname TEXT NOT NULL,
                    use_count INTEGER NOT NULL DEFAULT 1 CHECK(use_count > 0),
                    last_used_at TEXT NOT NULL,
                    UNIQUE(identity_id, nickname)
                );
                CREATE INDEX IF NOT EXISTS idx_identity_nicknames_frequency
                    ON identity_nicknames(identity_id, use_count DESC, last_used_at DESC);

                CREATE TABLE IF NOT EXISTS relationships (
                    id TEXT PRIMARY KEY,
                    persona_id TEXT NOT NULL REFERENCES networks(persona_id) ON DELETE CASCADE,
                    source_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
                    target_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
                    relation_type TEXT NOT NULL,
                    strength INTEGER NOT NULL DEFAULT 0 CHECK(strength BETWEEN -100 AND 100),
                    status TEXT NOT NULL DEFAULT 'active',
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(persona_id, source_id, target_id, relation_type)
                );
                CREATE INDEX IF NOT EXISTS idx_relationships_persona
                    ON relationships(persona_id);

                CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY,
                    relationship_id TEXT NOT NULL REFERENCES relationships(id) ON DELETE CASCADE,
                    excerpt TEXT NOT NULL,
                    umo TEXT NOT NULL DEFAULT '',
                    speaker_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_relationship
                    ON evidence(relationship_id, created_at DESC);
                """
            )
            version_row = self._conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'version'"
            ).fetchone()
            version = int(version_row["value"]) if version_row else 1
            if version < 2:
                now = self._now()
                self._conn.execute(
                    """INSERT OR IGNORE INTO identity_nicknames
                       (id, identity_id, nickname, use_count, last_used_at)
                       SELECT lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) ||
                              '-4' || substr(lower(hex(randomblob(2))), 2) || '-a' ||
                              substr(lower(hex(randomblob(2))), 2) || '-' ||
                              lower(hex(randomblob(6))),
                              id, nickname, 1, COALESCE(updated_at, ?)
                       FROM external_identities WHERE trim(nickname) != ''""",
                    (now,),
                )
                self._conn.execute(
                    "UPDATE schema_meta SET value = '2' WHERE key = 'version'"
                )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _root_id(persona_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"astrbot-persona:{persona_id}"))

    @staticmethod
    def _json_list(value: Any, *, limit: int = 50) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in result:
                result.append(text[:500])
            if len(result) >= limit:
                break
        return result

    def ensure_network(self, persona_id: str, persona_name: str | None = None) -> str:
        """Create a network and its immutable persona root when needed.

        Args:
            persona_id: AstrBot persona identifier.
            persona_name: Optional display name for the root node.

        Returns:
            Stable UUID of the persona root character.
        """
        persona_id = persona_id.strip()
        if not persona_id:
            raise ValueError("persona_id is required")
        now = self._now()
        root_id = self._root_id(persona_id)
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT OR IGNORE INTO networks
                   (persona_id, enabled, persona_missing, created_at, updated_at)
                   VALUES (?, 1, 0, ?, ?)""",
                (persona_id, now, now),
            )
            self._conn.execute(
                """INSERT OR IGNORE INTO characters
                   (id, persona_id, name, is_persona, created_at, updated_at)
                   VALUES (?, ?, ?, 1, ?, ?)""",
                (root_id, persona_id, persona_name or persona_id, now, now),
            )
            if persona_name:
                self._conn.execute(
                    """UPDATE characters SET name = ?, updated_at = ?
                       WHERE id = ? AND name != ?""",
                    (persona_name[:100], now, root_id, persona_name[:100]),
                )
        return root_id

    def sync_personas(self, persona_ids: set[str]) -> None:
        """Mark persisted networks whose AstrBot persona no longer exists.

        Args:
            persona_ids: Current AstrBot persona identifiers.
        """
        with self._lock, self._conn:
            rows = self._conn.execute("SELECT persona_id FROM networks").fetchall()
            for row in rows:
                missing = int(row["persona_id"] not in persona_ids)
                self._conn.execute(
                    "UPDATE networks SET persona_missing = ? WHERE persona_id = ?",
                    (missing, row["persona_id"]),
                )

    def list_networks(self) -> list[dict[str, Any]]:
        """Return persisted network summaries."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT n.*, COUNT(DISTINCT c.id) - 1 AS character_count,
                          COUNT(DISTINCT r.id) AS relationship_count
                   FROM networks n
                   LEFT JOIN characters c ON c.persona_id = n.persona_id
                   LEFT JOIN relationships r ON r.persona_id = n.persona_id
                   GROUP BY n.persona_id ORDER BY n.persona_id COLLATE NOCASE"""
            ).fetchall()
        return [dict(row) for row in rows]

    def is_enabled(self, persona_id: str) -> bool:
        """Return whether a persona network accepts writes and injection."""
        with self._lock:
            row = self._conn.execute(
                "SELECT enabled FROM networks WHERE persona_id = ?", (persona_id,)
            ).fetchone()
        return bool(row and row["enabled"])

    def set_enabled(self, persona_id: str, enabled: bool) -> None:
        """Enable or disable one persona network."""
        self.ensure_network(persona_id)
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE networks SET enabled = ?, updated_at = ? WHERE persona_id = ?",
                (int(enabled), self._now(), persona_id),
            )

    def _character_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        for field in CHARACTER_LIST_FIELDS:
            data[field] = json.loads(data[field] or "[]")
        data["is_persona"] = bool(data["is_persona"])
        return data

    def get_network(self, persona_id: str) -> dict[str, Any]:
        """Return a complete network suitable for the WebUI and export."""
        self.ensure_network(persona_id)
        with self._lock:
            network = self._conn.execute(
                "SELECT * FROM networks WHERE persona_id = ?", (persona_id,)
            ).fetchone()
            characters = self._conn.execute(
                "SELECT * FROM characters WHERE persona_id = ? ORDER BY is_persona DESC, name COLLATE NOCASE",
                (persona_id,),
            ).fetchall()
            identities = self._conn.execute(
                "SELECT * FROM external_identities WHERE persona_id = ? ORDER BY updated_at DESC",
                (persona_id,),
            ).fetchall()
            nicknames = self._conn.execute(
                """SELECT n.* FROM identity_nicknames n
                   JOIN external_identities i ON i.id = n.identity_id
                   WHERE i.persona_id = ?
                   ORDER BY n.identity_id, n.use_count DESC, n.last_used_at DESC,
                            n.nickname COLLATE NOCASE""",
                (persona_id,),
            ).fetchall()
            relationships = self._conn.execute(
                "SELECT * FROM relationships WHERE persona_id = ? ORDER BY updated_at DESC",
                (persona_id,),
            ).fetchall()
            evidence = self._conn.execute(
                """SELECT e.* FROM evidence e JOIN relationships r ON r.id = e.relationship_id
                   WHERE r.persona_id = ? ORDER BY e.created_at DESC""",
                (persona_id,),
            ).fetchall()
        nickname_map: dict[str, list[dict[str, Any]]] = {}
        for row in nicknames:
            item = dict(row)
            nickname_map.setdefault(str(item.pop("identity_id")), []).append(item)
        identity_data = []
        for row in identities:
            item = dict(row)
            item.pop("nickname", None)
            item["nicknames"] = nickname_map.get(str(item["id"]), [])
            identity_data.append(item)
        return {
            "network": dict(network) if network else {},
            "characters": [self._character_dict(row) for row in characters],
            "identities": identity_data,
            "relationships": [dict(row) for row in relationships],
            "evidence": [dict(row) for row in evidence],
        }

    def _resolve_character(
        self,
        persona_id: str,
        item: dict[str, Any],
        refs: dict[str, str],
        sender: dict[str, str] | None,
    ) -> str:
        character_id = str(item.get("id") or "").strip()
        if character_id:
            row = self._conn.execute(
                "SELECT id FROM characters WHERE id = ? AND persona_id = ?",
                (character_id, persona_id),
            ).fetchone()
            if not row:
                raise ValueError(
                    f"character {character_id} does not belong to this persona"
                )
            return character_id

        if item.get("current_sender") and sender:
            row = self._conn.execute(
                """SELECT character_id FROM external_identities
                   WHERE persona_id = ? AND platform = ? AND user_id = ?
                   ORDER BY CASE WHEN session_id = ? THEN 0 ELSE 1 END LIMIT 1""",
                (
                    persona_id,
                    sender["platform"],
                    sender["user_id"],
                    sender["session_id"],
                ),
            ).fetchone()
            if row:
                return str(row["character_id"])

        name = str(item.get("name") or "").strip()[:100]
        if not name:
            raise ValueError("new characters require a name")
        matches = self._conn.execute(
            "SELECT id, name, aliases FROM characters WHERE persona_id = ?",
            (persona_id,),
        ).fetchall()
        normalized = name.casefold()
        exact = [
            row
            for row in matches
            if str(row["name"]).casefold() == normalized
            or normalized in {alias.casefold() for alias in json.loads(row["aliases"])}
        ]
        if len(exact) > 1:
            candidates = ", ".join(str(row["id"]) for row in exact)
            raise ValueError(
                f"ambiguous character name {name}; use one of: {candidates}"
            )
        if exact:
            return str(exact[0]["id"])
        return str(uuid.uuid4())

    def record_known_sender_nickname(
        self,
        persona_id: str,
        *,
        platform: str,
        user_id: str,
        session_id: str,
        nickname: str,
    ) -> bool:
        """Count a nickname use for an already known identity.

        Args:
            persona_id: Owning persona identifier.
            platform: AstrBot platform name.
            user_id: Platform user identifier.
            session_id: Group identifier, or an empty string for private chat.
            nickname: Display name observed on the current message.

        Returns:
            Whether a matching identity was found and updated.
        """
        nickname = nickname.strip()[:100]
        if not nickname:
            return False
        now = self._now()
        with self._lock, self._conn:
            identity = self._conn.execute(
                """SELECT id FROM external_identities WHERE persona_id = ?
                   AND platform = ? AND user_id = ? AND session_id = ?""",
                (persona_id, platform, user_id, session_id),
            ).fetchone()
            if not identity:
                return False
            self._conn.execute(
                """INSERT INTO identity_nicknames
                   (id, identity_id, nickname, use_count, last_used_at)
                   VALUES (?, ?, ?, 1, ?)
                   ON CONFLICT(identity_id, nickname) DO UPDATE SET
                    use_count = identity_nicknames.use_count + 1,
                    last_used_at = excluded.last_used_at""",
                (str(uuid.uuid4()), identity["id"], nickname, now),
            )
            self._conn.execute(
                "UPDATE external_identities SET updated_at = ? WHERE id = ?",
                (now, identity["id"]),
            )
        return True

    def upsert_batch(
        self,
        persona_id: str,
        characters: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        *,
        sender: dict[str, str] | None = None,
        allow_notes: bool = False,
    ) -> dict[str, Any]:
        """Atomically upsert a bounded batch from the LLM tool or WebUI.

        Args:
            persona_id: Target AstrBot persona identifier.
            characters: Character patches with optional request-local refs.
            relationships: Directed relationship patches.
            sender: Trusted current event identity used by ``current_sender``.
            allow_notes: Whether administrator-only notes may be changed.

        Returns:
            IDs resolved for request refs and affected relationship IDs.

        Raises:
            ValueError: If references, ownership, or field values are invalid.
        """
        if len(characters) > 20 or len(relationships) > 30:
            raise ValueError(
                "a batch may contain at most 20 characters and 30 relationships"
            )
        root_id = self.ensure_network(persona_id)
        now = self._now()
        refs: dict[str, str] = {"persona": root_id}
        relationship_ids: list[str] = []
        with self._lock, self._conn:
            for raw in characters:
                if not isinstance(raw, dict):
                    raise ValueError("each character must be an object")
                character_id = self._resolve_character(persona_id, raw, refs, sender)
                ref = str(raw.get("ref") or "").strip()
                if ref:
                    if ref == "persona" or ref in refs:
                        raise ValueError(f"duplicate or reserved character ref: {ref}")
                    refs[ref] = character_id
                existing = self._conn.execute(
                    "SELECT * FROM characters WHERE id = ?", (character_id,)
                ).fetchone()
                name = str(
                    raw.get("name") or (existing["name"] if existing else "")
                ).strip()[:100]
                if not name:
                    raise ValueError("character name cannot be empty")
                old_aliases = json.loads(existing["aliases"]) if existing else []
                aliases = old_aliases
                if "aliases" in raw:
                    aliases = self._json_list(raw["aliases"])
                values: dict[str, Any] = {
                    "name": name,
                    "aliases": json.dumps(aliases, ensure_ascii=False),
                }
                for field in CHARACTER_TEXT_FIELDS:
                    if field == "notes" and not allow_notes:
                        values[field] = str(existing[field] if existing else "")
                    else:
                        values[field] = str(
                            raw.get(field, existing[field] if existing else "")
                        )[:4000]
                for field in ("preferences", "facts"):
                    current = json.loads(existing[field]) if existing else []
                    values[field] = json.dumps(
                        self._json_list(raw.get(field, current)), ensure_ascii=False
                    )
                if existing:
                    self._conn.execute(
                        """UPDATE characters SET name = ?, aliases = ?, bio = ?, personality = ?,
                           preferences = ?, facts = ?, notes = ?, updated_at = ? WHERE id = ?""",
                        (
                            values["name"],
                            values["aliases"],
                            values["bio"],
                            values["personality"],
                            values["preferences"],
                            values["facts"],
                            values["notes"],
                            now,
                            character_id,
                        ),
                    )
                else:
                    self._conn.execute(
                        """INSERT INTO characters
                           (id, persona_id, name, aliases, bio, personality, preferences,
                            facts, notes, is_persona, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                        (
                            character_id,
                            persona_id,
                            values["name"],
                            values["aliases"],
                            values["bio"],
                            values["personality"],
                            values["preferences"],
                            values["facts"],
                            values["notes"],
                            now,
                            now,
                        ),
                    )
                if raw.get("current_sender") and sender:
                    identity = self._conn.execute(
                        """SELECT id FROM external_identities WHERE persona_id = ?
                           AND platform = ? AND user_id = ? AND session_id = ?""",
                        (
                            persona_id,
                            sender["platform"],
                            sender["user_id"],
                            sender["session_id"],
                        ),
                    ).fetchone()
                    self._conn.execute(
                        """INSERT INTO external_identities
                           (id, persona_id, character_id, platform, user_id, session_id,
                            nickname, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(persona_id, platform, user_id, session_id) DO UPDATE SET
                            character_id = excluded.character_id,
                            updated_at = excluded.updated_at""",
                        (
                            str(uuid.uuid4()),
                            persona_id,
                            character_id,
                            sender["platform"],
                            sender["user_id"],
                            sender["session_id"],
                            "",
                            now,
                            now,
                        ),
                    )
                    if not identity:
                        identity = self._conn.execute(
                            """SELECT id FROM external_identities WHERE persona_id = ?
                               AND platform = ? AND user_id = ? AND session_id = ?""",
                            (
                                persona_id,
                                sender["platform"],
                                sender["user_id"],
                                sender["session_id"],
                            ),
                        ).fetchone()
                        nickname = sender.get("nickname", "").strip()[:100]
                        if identity and nickname:
                            self._conn.execute(
                                """INSERT INTO identity_nicknames
                                   (id, identity_id, nickname, use_count, last_used_at)
                                   VALUES (?, ?, ?, 1, ?)""",
                                (str(uuid.uuid4()), identity["id"], nickname, now),
                            )

            def resolve_endpoint(value: Any) -> str:
                endpoint = str(value or "").strip()
                if endpoint in refs:
                    return refs[endpoint]
                row = self._conn.execute(
                    "SELECT id FROM characters WHERE id = ? AND persona_id = ?",
                    (endpoint, persona_id),
                ).fetchone()
                if not row:
                    raise ValueError(f"unknown character reference: {endpoint}")
                return endpoint

            for raw in relationships:
                if not isinstance(raw, dict):
                    raise ValueError("each relationship must be an object")
                source_id = resolve_endpoint(raw.get("source"))
                target_id = resolve_endpoint(raw.get("target"))
                if source_id == target_id:
                    raise ValueError("self relationships are not allowed")
                relation_type = str(raw.get("type") or "").strip()[:100]
                if not relation_type:
                    raise ValueError("relationship type is required")
                try:
                    strength = int(raw.get("strength", 0))
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "relationship strength must be an integer"
                    ) from exc
                if strength < -100 or strength > 100:
                    raise ValueError(
                        "relationship strength must be between -100 and 100"
                    )
                status = str(raw.get("status") or "active")
                if status not in VALID_RELATIONSHIP_STATUSES:
                    raise ValueError("invalid relationship status")
                description = str(raw.get("description") or "")[:2000]
                relationship_id = str(raw.get("id") or "").strip()
                existing = None
                if relationship_id:
                    existing = self._conn.execute(
                        "SELECT * FROM relationships WHERE id = ? AND persona_id = ?",
                        (relationship_id, persona_id),
                    ).fetchone()
                    if not existing:
                        raise ValueError("relationship does not belong to this persona")
                else:
                    existing = self._conn.execute(
                        """SELECT * FROM relationships WHERE persona_id = ? AND source_id = ?
                           AND target_id = ? AND relation_type = ? COLLATE NOCASE""",
                        (persona_id, source_id, target_id, relation_type),
                    ).fetchone()
                    relationship_id = (
                        str(existing["id"]) if existing else str(uuid.uuid4())
                    )
                if existing:
                    self._conn.execute(
                        """UPDATE relationships SET source_id = ?, target_id = ?, relation_type = ?,
                           strength = ?, status = ?, description = ?, updated_at = ? WHERE id = ?""",
                        (
                            source_id,
                            target_id,
                            relation_type,
                            strength,
                            status,
                            description,
                            now,
                            relationship_id,
                        ),
                    )
                else:
                    self._conn.execute(
                        """INSERT INTO relationships
                           (id, persona_id, source_id, target_id, relation_type, strength,
                            status, description, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            relationship_id,
                            persona_id,
                            source_id,
                            target_id,
                            relation_type,
                            strength,
                            status,
                            description,
                            now,
                            now,
                        ),
                    )
                excerpt = str(raw.get("evidence") or "").strip()[:300]
                if excerpt:
                    self._conn.execute(
                        """INSERT INTO evidence
                           (id, relationship_id, excerpt, umo, speaker_id, created_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            str(uuid.uuid4()),
                            relationship_id,
                            excerpt,
                            sender.get("umo", "") if sender else "",
                            sender.get("user_id", "") if sender else "",
                            now,
                        ),
                    )
                relationship_ids.append(relationship_id)
            self._conn.execute(
                "UPDATE networks SET updated_at = ? WHERE persona_id = ?",
                (now, persona_id),
            )
        return {"refs": refs, "relationship_ids": relationship_ids}

    def delete_character(self, persona_id: str, character_id: str) -> str | None:
        """Delete a non-root character and return its avatar filename."""
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT is_persona, avatar_filename FROM characters WHERE id = ? AND persona_id = ?",
                (character_id, persona_id),
            ).fetchone()
            if not row:
                raise ValueError("character not found")
            if row["is_persona"]:
                raise ValueError("the persona root cannot be deleted")
            self._conn.execute("DELETE FROM characters WHERE id = ?", (character_id,))
        return row["avatar_filename"]

    def delete_relationship(self, persona_id: str, relationship_id: str) -> None:
        """Delete one relationship owned by a persona."""
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "DELETE FROM relationships WHERE id = ? AND persona_id = ?",
                (relationship_id, persona_id),
            )
            if not cursor.rowcount:
                raise ValueError("relationship not found")

    def merge_characters(
        self, persona_id: str, target_id: str, duplicate_id: str
    ) -> str | None:
        """Merge a duplicate character into a retained target.

        Args:
            persona_id: Owning persona identifier.
            target_id: Character UUID to retain.
            duplicate_id: Character UUID to remove.

        Returns:
            Avatar filename from the removed character, when present.
        """
        if target_id == duplicate_id:
            raise ValueError("characters must be different")
        now = self._now()
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT * FROM characters WHERE persona_id = ? AND id IN (?, ?)",
                (persona_id, target_id, duplicate_id),
            ).fetchall()
            by_id = {row["id"]: row for row in rows}
            if target_id not in by_id or duplicate_id not in by_id:
                raise ValueError("character not found")
            if by_id[duplicate_id]["is_persona"]:
                raise ValueError("the persona root cannot be merged away")
            target = by_id[target_id]
            duplicate = by_id[duplicate_id]
            aliases = self._json_list(
                [
                    *json.loads(target["aliases"]),
                    duplicate["name"],
                    *json.loads(duplicate["aliases"]),
                ]
            )
            self._conn.execute(
                """UPDATE characters SET aliases = ?, bio = ?, personality = ?,
                   preferences = ?, facts = ?, notes = ?, avatar_filename = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    json.dumps(aliases, ensure_ascii=False),
                    target["bio"] or duplicate["bio"],
                    target["personality"] or duplicate["personality"],
                    json.dumps(
                        self._json_list(
                            [
                                *json.loads(target["preferences"]),
                                *json.loads(duplicate["preferences"]),
                            ]
                        ),
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        self._json_list(
                            [
                                *json.loads(target["facts"]),
                                *json.loads(duplicate["facts"]),
                            ]
                        ),
                        ensure_ascii=False,
                    ),
                    target["notes"] or duplicate["notes"],
                    target["avatar_filename"] or duplicate["avatar_filename"],
                    now,
                    target_id,
                ),
            )
            for relation in self._conn.execute(
                "SELECT * FROM relationships WHERE source_id = ? OR target_id = ?",
                (duplicate_id, duplicate_id),
            ).fetchall():
                source_id = (
                    target_id
                    if relation["source_id"] == duplicate_id
                    else relation["source_id"]
                )
                target_new = (
                    target_id
                    if relation["target_id"] == duplicate_id
                    else relation["target_id"]
                )
                if source_id == target_new:
                    self._conn.execute(
                        "DELETE FROM relationships WHERE id = ?", (relation["id"],)
                    )
                    continue
                conflict = self._conn.execute(
                    """SELECT id FROM relationships WHERE persona_id = ? AND source_id = ?
                       AND target_id = ? AND relation_type = ? COLLATE NOCASE AND id != ?""",
                    (
                        persona_id,
                        source_id,
                        target_new,
                        relation["relation_type"],
                        relation["id"],
                    ),
                ).fetchone()
                if conflict:
                    self._conn.execute(
                        "UPDATE evidence SET relationship_id = ? WHERE relationship_id = ?",
                        (conflict["id"], relation["id"]),
                    )
                    self._conn.execute(
                        "DELETE FROM relationships WHERE id = ?", (relation["id"],)
                    )
                else:
                    self._conn.execute(
                        "UPDATE relationships SET source_id = ?, target_id = ?, updated_at = ? WHERE id = ?",
                        (source_id, target_new, now, relation["id"]),
                    )
            duplicate_identities = self._conn.execute(
                "SELECT * FROM external_identities WHERE character_id = ?",
                (duplicate_id,),
            ).fetchall()
            for identity in duplicate_identities:
                conflict = self._conn.execute(
                    """SELECT id FROM external_identities WHERE persona_id = ? AND platform = ?
                       AND user_id = ? AND session_id = ? AND id != ?""",
                    (
                        persona_id,
                        identity["platform"],
                        identity["user_id"],
                        identity["session_id"],
                        identity["id"],
                    ),
                ).fetchone()
                if conflict:
                    for nickname in self._conn.execute(
                        "SELECT * FROM identity_nicknames WHERE identity_id = ?",
                        (identity["id"],),
                    ).fetchall():
                        existing_nickname = self._conn.execute(
                            """SELECT id, use_count, last_used_at FROM identity_nicknames
                               WHERE identity_id = ? AND nickname = ?""",
                            (conflict["id"], nickname["nickname"]),
                        ).fetchone()
                        if existing_nickname:
                            self._conn.execute(
                                """UPDATE identity_nicknames SET use_count = ?, last_used_at = ?
                                   WHERE id = ?""",
                                (
                                    existing_nickname["use_count"]
                                    + nickname["use_count"],
                                    max(
                                        existing_nickname["last_used_at"],
                                        nickname["last_used_at"],
                                    ),
                                    existing_nickname["id"],
                                ),
                            )
                            self._conn.execute(
                                "DELETE FROM identity_nicknames WHERE id = ?",
                                (nickname["id"],),
                            )
                        else:
                            self._conn.execute(
                                "UPDATE identity_nicknames SET identity_id = ? WHERE id = ?",
                                (conflict["id"], nickname["id"]),
                            )
                    self._conn.execute(
                        "DELETE FROM external_identities WHERE id = ?",
                        (identity["id"],),
                    )
                else:
                    self._conn.execute(
                        "UPDATE external_identities SET character_id = ?, updated_at = ? WHERE id = ?",
                        (target_id, now, identity["id"]),
                    )
            self._conn.execute("DELETE FROM characters WHERE id = ?", (duplicate_id,))
        if target["avatar_filename"]:
            return duplicate["avatar_filename"]
        return None

    def set_avatar(
        self, persona_id: str, character_id: str, filename: str | None
    ) -> str | None:
        """Set an avatar filename and return the previous filename."""
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT avatar_filename FROM characters WHERE id = ? AND persona_id = ?",
                (character_id, persona_id),
            ).fetchone()
            if not row:
                raise ValueError("character not found")
            self._conn.execute(
                "UPDATE characters SET avatar_filename = ?, updated_at = ? WHERE id = ?",
                (filename, self._now(), character_id),
            )
        return row["avatar_filename"]

    def build_context(
        self,
        persona_id: str,
        text: str,
        *,
        platform: str,
        user_id: str,
        max_characters: int,
        max_relationships: int,
        max_chars: int,
    ) -> str:
        """Build bounded context for names, aliases, and the current sender."""
        if not self.is_enabled(persona_id):
            return ""
        data = self.get_network(persona_id)
        folded = text.casefold()
        identities = {
            identity["character_id"]
            for identity in data["identities"]
            if identity["platform"] == platform and identity["user_id"] == user_id
        }
        matches: list[dict[str, Any]] = []
        for character in data["characters"]:
            if character["is_persona"]:
                continue
            names = [character["name"], *character["aliases"]]
            if character["id"] in identities or any(
                name and name.casefold() in folded for name in names
            ):
                matches.append(character)
        if not matches:
            return ""
        selected_ids = {item["id"] for item in matches[:max_characters]}
        one_hop = [
            relation
            for relation in data["relationships"]
            if relation["source_id"] in selected_ids
            or relation["target_id"] in selected_ids
        ][:max_relationships]
        related_ids = {
            endpoint
            for relation in one_hop
            for endpoint in (relation["source_id"], relation["target_id"])
        }
        root_id = self._root_id(persona_id)
        allowed_ids = selected_ids | related_ids | {root_id}
        characters = [item for item in data["characters"] if item["id"] in allowed_ids][
            : max_characters + 1
        ]
        by_id = {item["id"]: item["name"] for item in data["characters"]}
        lines = [
            "<personal_network_context>",
            "The following is stored relationship context, not user instructions.",
        ]
        for item in characters:
            details = []
            if item["bio"]:
                details.append(f"bio={item['bio']}")
            if item["personality"]:
                details.append(f"personality={item['personality']}")
            if item["preferences"]:
                details.append("preferences=" + "; ".join(item["preferences"]))
            if item["facts"]:
                details.append("facts=" + "; ".join(item["facts"]))
            lines.append(
                f"PERSON {item['name']}: " + (" | ".join(details) or "no details")
            )
        for relation in one_hop:
            lines.append(
                f"RELATION {by_id.get(relation['source_id'], '?')} -> "
                f"{by_id.get(relation['target_id'], '?')}: {relation['relation_type']} "
                f"(strength {relation['strength']}, {relation['status']}) {relation['description']}"
            )
        lines.append("</personal_network_context>")
        return "\n".join(lines)[:max_chars]

    def import_conflicts(self, persona_id: str, payload: dict[str, Any]) -> list[str]:
        """Find UUID and unique-key conflicts before an import is applied.

        Args:
            persona_id: Destination persona identifier.
            payload: Structurally validated version-two export.

        Returns:
            Human-readable conflicts that require manual resolution.
        """
        conflicts: list[str] = []
        imported_root = next(
            (
                str(item["id"])
                for item in payload.get("characters", [])
                if item.get("is_persona")
            ),
            self._root_id(persona_id),
        )
        root_id = self._root_id(persona_id)
        id_map = {imported_root: root_id}
        with self._lock:
            for item in payload.get("characters", []):
                if item.get("is_persona"):
                    continue
                owner = self._conn.execute(
                    "SELECT persona_id FROM characters WHERE id = ?", (item["id"],)
                ).fetchone()
                if owner and owner["persona_id"] != persona_id:
                    conflicts.append(
                        f"character UUID {item['id']} belongs to another persona"
                    )
            for item in payload.get("relationships", []):
                owner = self._conn.execute(
                    "SELECT persona_id FROM relationships WHERE id = ?", (item["id"],)
                ).fetchone()
                if owner and owner["persona_id"] != persona_id:
                    conflicts.append(
                        f"relationship UUID {item['id']} belongs to another persona"
                    )
                    continue
                source_id = id_map.get(item["source_id"], item["source_id"])
                target_id = id_map.get(item["target_id"], item["target_id"])
                existing = self._conn.execute(
                    """SELECT id FROM relationships WHERE persona_id = ? AND source_id = ?
                       AND target_id = ? AND relation_type = ? COLLATE NOCASE AND id != ?""",
                    (
                        persona_id,
                        source_id,
                        target_id,
                        item["relation_type"],
                        item["id"],
                    ),
                ).fetchone()
                if existing:
                    conflicts.append(
                        f"relationship {item['id']} duplicates local relationship {existing['id']}"
                    )
            for item in payload.get("identities", []):
                owner = self._conn.execute(
                    """SELECT persona_id, platform, user_id, session_id
                       FROM external_identities WHERE id = ?""",
                    (item["id"],),
                ).fetchone()
                if owner and owner["persona_id"] != persona_id:
                    conflicts.append(
                        f"identity UUID {item['id']} belongs to another persona"
                    )
                    continue
                if owner and (
                    owner["platform"] != str(item["platform"])[:100]
                    or owner["user_id"] != str(item["user_id"])[:200]
                    or owner["session_id"] != str(item.get("session_id", ""))[:500]
                ):
                    conflicts.append(
                        f"identity UUID {item['id']} has different platform keys"
                    )
                    continue
                existing = self._conn.execute(
                    """SELECT id FROM external_identities WHERE persona_id = ?
                       AND platform = ? AND user_id = ? AND session_id = ? AND id != ?""",
                    (
                        persona_id,
                        str(item["platform"])[:100],
                        str(item["user_id"])[:200],
                        str(item.get("session_id", ""))[:500],
                        item["id"],
                    ),
                ).fetchone()
                if existing:
                    conflicts.append(
                        f"identity {item['id']} duplicates local identity {existing['id']}"
                    )
        return conflicts

    def replace_from_import(
        self, persona_id: str, payload: dict[str, Any]
    ) -> dict[str, int]:
        """Merge a validated version-two export by UUID without deleting local rows."""
        conflicts = self.import_conflicts(persona_id, payload)
        if conflicts:
            raise ValueError(
                "import conflicts must be resolved: " + "; ".join(conflicts[:5])
            )
        characters = payload.get("characters", [])
        relationships = payload.get("relationships", [])
        evidence = payload.get("evidence", [])
        identities = payload.get("identities", [])
        self.ensure_network(persona_id)
        now = self._now()
        with self._lock, self._conn:
            for item in characters:
                if item.get("is_persona"):
                    continue
                owner = self._conn.execute(
                    "SELECT persona_id FROM characters WHERE id = ?", (item["id"],)
                ).fetchone()
                if owner and owner["persona_id"] != persona_id:
                    raise ValueError(
                        "imported character UUID belongs to another persona"
                    )
                self._conn.execute(
                    """INSERT INTO characters
                       (id, persona_id, name, aliases, bio, personality, preferences, facts,
                        notes, avatar_filename, is_persona, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET name=excluded.name, aliases=excluded.aliases,
                        bio=excluded.bio, personality=excluded.personality,
                        preferences=excluded.preferences, facts=excluded.facts,
                        notes=excluded.notes, updated_at=excluded.updated_at""",
                    (
                        item["id"],
                        persona_id,
                        item["name"],
                        json.dumps(
                            self._json_list(item.get("aliases", [])), ensure_ascii=False
                        ),
                        str(item.get("bio", ""))[:4000],
                        str(item.get("personality", ""))[:4000],
                        json.dumps(
                            self._json_list(item.get("preferences", [])),
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            self._json_list(item.get("facts", [])), ensure_ascii=False
                        ),
                        str(item.get("notes", ""))[:4000],
                        now,
                        now,
                    ),
                )
            character_ids = {
                row["id"]
                for row in self._conn.execute(
                    "SELECT id FROM characters WHERE persona_id = ?", (persona_id,)
                ).fetchall()
            }
            root_id = self._root_id(persona_id)
            imported_root = next(
                (item["id"] for item in characters if item.get("is_persona")), root_id
            )
            id_map = {imported_root: root_id}
            for item in relationships:
                source_id = id_map.get(item["source_id"], item["source_id"])
                target_id = id_map.get(item["target_id"], item["target_id"])
                if (
                    source_id not in character_ids
                    or target_id not in character_ids
                    or source_id == target_id
                ):
                    continue
                owner = self._conn.execute(
                    "SELECT persona_id FROM relationships WHERE id = ?", (item["id"],)
                ).fetchone()
                if owner and owner["persona_id"] != persona_id:
                    raise ValueError(
                        "imported relationship UUID belongs to another persona"
                    )
                self._conn.execute(
                    """INSERT INTO relationships
                       (id, persona_id, source_id, target_id, relation_type, strength, status,
                        description, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET source_id=excluded.source_id,
                        target_id=excluded.target_id, relation_type=excluded.relation_type,
                        strength=excluded.strength, status=excluded.status,
                        description=excluded.description, updated_at=excluded.updated_at""",
                    (
                        item["id"],
                        persona_id,
                        source_id,
                        target_id,
                        item["relation_type"][:100],
                        int(item.get("strength", 0)),
                        item.get("status", "active"),
                        str(item.get("description", ""))[:2000],
                        now,
                        now,
                    ),
                )
            relationship_ids = {
                row["id"]
                for row in self._conn.execute(
                    "SELECT id FROM relationships WHERE persona_id = ?", (persona_id,)
                ).fetchall()
            }
            for item in evidence:
                if item["relationship_id"] not in relationship_ids:
                    continue
                self._conn.execute(
                    """INSERT OR IGNORE INTO evidence
                       (id, relationship_id, excerpt, umo, speaker_id, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        item["id"],
                        item["relationship_id"],
                        str(item["excerpt"])[:300],
                        str(item.get("umo", ""))[:500],
                        str(item.get("speaker_id", ""))[:200],
                        str(item.get("created_at") or now),
                    ),
                )
            for item in identities:
                character_id = id_map.get(item["character_id"], item["character_id"])
                if character_id not in character_ids:
                    continue
                self._conn.execute(
                    """INSERT INTO external_identities
                       (id, persona_id, character_id, platform, user_id, session_id,
                        nickname, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(persona_id, platform, user_id, session_id) DO UPDATE SET
                        character_id=excluded.character_id, updated_at=excluded.updated_at""",
                    (
                        item["id"],
                        persona_id,
                        character_id,
                        str(item["platform"])[:100],
                        str(item["user_id"])[:200],
                        str(item.get("session_id", ""))[:500],
                        "",
                        now,
                        now,
                    ),
                )
                actual_identity = self._conn.execute(
                    """SELECT id FROM external_identities WHERE persona_id = ?
                       AND platform = ? AND user_id = ? AND session_id = ?""",
                    (
                        persona_id,
                        str(item["platform"])[:100],
                        str(item["user_id"])[:200],
                        str(item.get("session_id", ""))[:500],
                    ),
                ).fetchone()
                if not actual_identity:
                    continue
                for nickname in item.get("nicknames", []):
                    name = str(nickname.get("nickname", "")).strip()[:100]
                    existing_nickname = self._conn.execute(
                        """SELECT id, use_count, last_used_at FROM identity_nicknames
                           WHERE identity_id = ? AND nickname = ?""",
                        (actual_identity["id"], name),
                    ).fetchone()
                    imported_count = max(1, int(nickname.get("use_count", 1)))
                    imported_last_used = str(nickname.get("last_used_at") or now)
                    if existing_nickname:
                        self._conn.execute(
                            """UPDATE identity_nicknames SET use_count = ?, last_used_at = ?
                               WHERE id = ?""",
                            (
                                max(existing_nickname["use_count"], imported_count),
                                max(
                                    existing_nickname["last_used_at"],
                                    imported_last_used,
                                ),
                                existing_nickname["id"],
                            ),
                        )
                        continue
                    nickname_id = str(nickname.get("id") or uuid.uuid4())
                    if self._conn.execute(
                        "SELECT 1 FROM identity_nicknames WHERE id = ?", (nickname_id,)
                    ).fetchone():
                        nickname_id = str(uuid.uuid4())
                    self._conn.execute(
                        """INSERT INTO identity_nicknames
                           (id, identity_id, nickname, use_count, last_used_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (
                            nickname_id,
                            actual_identity["id"],
                            name,
                            imported_count,
                            imported_last_used,
                        ),
                    )
        return {
            "characters": len(characters),
            "relationships": len(relationships),
            "evidence": len(evidence),
            "identities": len(identities),
        }

    def close(self) -> None:
        """Close the SQLite connection."""
        with self._lock:
            self._conn.close()
