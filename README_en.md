# Personal Network

[简体中文](README.md)

Personal Network is an AstrBot plugin that keeps a separate character and relationship graph for every persona. The active persona can record explicit, durable facts through a bounded LLM tool. Later requests receive relevant people and one-hop relationships based on names, aliases, and the current sender identity.

## Features

- Fully isolated people and relationships for every AstrBot persona.
- Character cards with aliases, avatars, profiles, personality, preferences, facts, and administrator notes.
- Multiple nicknames per platform identity and group session, sorted by usage frequency and recency.
- Directed multi-relationships with strength, status, descriptions, and evidence excerpts.
- Embedded Cytoscape.js network graph with cards, search, and relationship filters.
- Complete Dashboard CRUD, duplicate-person merging, avatar upload, and evidence review.
- Per-persona JSON import/export with conflict previews and embedded WebP avatars.
- Simplified Chinese and English UI, light and dark themes, and responsive mobile layout.

## Usage

1. Enable the plugin in AstrBot.
2. Open the **Personal Network** Page from the plugin detail view.
3. Select an AstrBot persona.
4. Chat normally. The model can call `update_personal_network` when the conversation establishes explicit and durable relationship information.

All existing personas are enabled by default and can be disabled individually from the Page. A disabled network accepts no LLM writes and injects no relationship context.

The LLM tool can create or update people, identities, relationships, and evidence. It cannot delete or merge people or change administrator notes. Those operations remain Dashboard-only.

## Nicknames

- Character aliases live in the character card's `aliases` list.
- Platform nicknames are isolated by platform, user ID, and group session. One identity may retain multiple historical nicknames in each group.
- Each message from a known identity increments the observed nickname's usage count.
- APIs and the WebUI sort nicknames by descending usage count and then by most recent use.
- Legacy databases and schema v1 JSON imports convert a single nickname into a nickname list with an initial count of one.

## Data and privacy

The SQLite database, avatars, and temporary exports live in AstrBot's plugin data directory. Deleting an AstrBot persona retains its network as an orphaned archive that remains available for export or manual cleanup.

Relationship evidence stores only an excerpt of up to 300 characters, the source session, speaker, and timestamp. Full messages are not retained.

## Development

Run from the AstrBot repository root:

```bash
uv run python -m pytest -q data/plugins/astrbot_plugin_personal_network/tests
uv run ruff format data/plugins/astrbot_plugin_personal_network
uv run ruff check data/plugins/astrbot_plugin_personal_network
```

Cytoscape.js 3.33.1 is bundled under the MIT license in `pages/network/vendor/`.
