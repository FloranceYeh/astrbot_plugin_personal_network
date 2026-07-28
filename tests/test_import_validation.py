"""Tests for import validation and the explicit LLM tool schema."""

from __future__ import annotations

import base64
import functools
import io
import uuid
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from PIL import Image

from data.plugins.astrbot_plugin_personal_network.main import (
    TOOL_PARAMETERS,
    PersonalNetworkPlugin,
    PersonalNetworkTool,
)


def valid_payload() -> dict:
    """Build a minimal version-one import payload.

    Returns:
        Structurally valid relationship-network export.
    """
    root_id = str(uuid.uuid4())
    person_id = str(uuid.uuid4())
    relationship_id = str(uuid.uuid4())
    return {
        "schema_version": 1,
        "characters": [
            {"id": root_id, "name": "Persona", "is_persona": True},
            {"id": person_id, "name": "Lin", "is_persona": False},
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


def test_tool_schema_is_valid_and_plugin_owned():
    Draft202012Validator.check_schema(TOOL_PARAMETERS)
    tool = PersonalNetworkTool(
        name="update_personal_network",
        description="test",
        parameters=TOOL_PARAMETERS,
    )

    assert tool.__module__.endswith("astrbot_plugin_personal_network.main")
    assert set(TOOL_PARAMETERS["properties"]) == {"characters", "relationships"}


@pytest.mark.asyncio
async def test_tool_handler_accepts_framework_instance_binding(
    monkeypatch, tmp_path
):
    registered_tools = []
    context = SimpleNamespace(
        add_llm_tools=lambda *tools: registered_tools.extend(tools),
        register_web_api=lambda *args: None,
    )
    monkeypatch.setattr(
        "data.plugins.astrbot_plugin_personal_network.main.StarTools.get_data_dir",
        classmethod(lambda cls: tmp_path),
    )
    plugin = PersonalNetworkPlugin(context, {"enabled": False})

    try:
        tool = registered_tools[0]
        assert tool.handler is PersonalNetworkPlugin.update_personal_network

        handler = functools.partial(tool.handler, plugin)
        result = await handler(object(), [], [])

        assert result == '{"updated": false, "reason": "plugin disabled"}'
    finally:
        plugin.storage.close()


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


def test_version_one_identity_nickname_is_normalized_to_a_list():
    plugin = PersonalNetworkPlugin.__new__(PersonalNetworkPlugin)
    payload = valid_payload()
    payload["schema_version"] = 1
    payload["identities"] = [
        {
            "id": str(uuid.uuid4()),
            "character_id": payload["characters"][1]["id"],
            "platform": "test",
            "user_id": "user-1",
            "session_id": "group-1",
            "nickname": "Legacy Nick",
            "updated_at": "2026-01-02T00:00:00+00:00",
        }
    ]

    normalized = plugin._validate_import(payload)
    assert normalized["schema_version"] == 2
    assert normalized["identities"][0]["nicknames"][0]["nickname"] == "Legacy Nick"
    assert normalized["identities"][0]["nicknames"][0]["use_count"] == 1
