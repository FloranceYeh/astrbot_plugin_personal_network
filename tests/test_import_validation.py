"""Tests for import validation and the explicit LLM tool schema."""

from __future__ import annotations

import base64
import functools
import io
import uuid

import pytest
from PIL import Image
from astrbot.core.provider.register import llm_tools

from data.plugins.astrbot_plugin_personal_network.main import (
    PersonalNetworkPlugin,
)


def valid_payload() -> dict:
    """Build a minimal current-schema import payload.

    Returns:
        Structurally valid relationship-network export.
    """
    root_id = str(uuid.uuid4())
    person_id = str(uuid.uuid4())
    relationship_id = str(uuid.uuid4())
    return {
        "schema_version": 3,
        "characters": [
            {
                "id": root_id,
                "name": "Persona",
                "is_persona": True,
                "alias_usages": [],
            },
            {
                "id": person_id,
                "name": "Lin",
                "is_persona": False,
                "alias_usages": [],
            },
        ],
        "identities": [],
        "relationships": [
            {
                "id": relationship_id,
                "source_id": root_id,
                "target_id": person_id,
                "relation_type": "friend",
                "strength": 50,
                "status": "active",
            }
        ],
        "evidence": [],
    }


def test_tool_is_registered_by_decorator():
    update_tool = llm_tools.get_func("update_personal_network")
    query_tool = llm_tools.get_func("query_personal_network")

    assert update_tool is not None
    assert update_tool.handler is PersonalNetworkPlugin.update_personal_network
    assert set(update_tool.parameters["properties"]) == {
        "characters",
        "relationships",
    }
    assert update_tool.parameters["properties"]["characters"]["type"] == "array"
    assert update_tool.parameters["properties"]["characters"]["items"] == {
        "type": "object"
    }
    assert query_tool is not None
    assert query_tool.handler is PersonalNetworkPlugin.query_personal_network
    assert query_tool.parameters["properties"]["query"]["type"] == "string"


@pytest.mark.asyncio
async def test_decorated_tool_accepts_framework_instance_binding():
    tool = llm_tools.get_func("update_personal_network")
    plugin = PersonalNetworkPlugin.__new__(PersonalNetworkPlugin)
    plugin.config = {"enabled": False}

    handler = functools.partial(tool.handler, plugin)
    result = await handler(object(), [], [])

    assert result == '{"updated": false, "reason": "plugin disabled"}'


def test_import_rejects_unknown_relationship_character():
    plugin = PersonalNetworkPlugin.__new__(PersonalNetworkPlugin)
    payload = valid_payload()
    payload["relationships"][0]["target_id"] = str(uuid.uuid4())

    with pytest.raises(ValueError, match="unknown character"):
        plugin._validate_import(payload)


def test_import_accepts_a_bounded_webp_avatar():
    plugin = PersonalNetworkPlugin.__new__(PersonalNetworkPlugin)
    payload = valid_payload()
    image = Image.new("RGB", (16, 16), "#087f75")
    output = io.BytesIO()
    image.save(output, format="WEBP")
    payload["characters"][1]["avatar_data"] = (
        "data:image/webp;base64," + base64.b64encode(output.getvalue()).decode()
    )

    assert plugin._validate_import(payload) is payload


def test_import_rejects_non_image_avatar_data():
    plugin = PersonalNetworkPlugin.__new__(PersonalNetworkPlugin)
    payload = valid_payload()
    payload["characters"][1]["avatar_data"] = (
        "data:image/webp;base64," + base64.b64encode(b"not-an-image").decode()
    )

    with pytest.raises(ValueError, match="not a valid image"):
        plugin._validate_import(payload)


@pytest.mark.parametrize("schema_version", [1, 2])
def test_import_rejects_older_schema_versions(schema_version: int):
    plugin = PersonalNetworkPlugin.__new__(PersonalNetworkPlugin)
    payload = valid_payload()
    payload["schema_version"] = schema_version

    with pytest.raises(ValueError, match="only schema_version 3"):
        plugin._validate_import(payload)
