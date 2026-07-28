"""Tests for relationship context injection placement."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.provider import ProviderRequest
from data.plugins.astrbot_plugin_personal_network.main import PersonalNetworkPlugin


@pytest.mark.asyncio
@pytest.mark.parametrize("position", ["system_prompt", "user_content"])
async def test_injection_position_matches_only_current_message(position: str):
    plugin = object.__new__(PersonalNetworkPlugin)
    plugin.config = {
        "enabled": True,
        "enable_llm_query_tool": True,
        "context_injection_position": position,
    }
    plugin.storage = MagicMock()
    plugin.storage.is_enabled.return_value = True
    plugin.storage.build_context.return_value = "<personal_network_context>父亲</personal_network_context>"
    plugin._resolve_persona_id = AsyncMock(return_value="Caranlaf")

    event = MagicMock()
    event.unified_msg_origin = "webchat:FriendMessage:test"
    event.message_str = "Alfred 是谁"
    event.get_platform_name.return_value = "webchat"
    event.get_platform_id.return_value = "webchat"
    event.get_sender_id.return_value = "user"
    event.get_group_id.return_value = ""
    event.get_sender_name.return_value = "User"
    request = ProviderRequest(
        prompt="Alfred 是谁",
        system_prompt="base",
        contexts=[{"role": "user", "content": "我见到了 FLF"}],
    )

    await plugin.inject_network_context(event, request)

    matched_text = plugin.storage.build_context.call_args.args[1]
    assert matched_text == "Alfred 是谁"
    if position == "system_prompt":
        assert "父亲" in request.system_prompt
        assert request.extra_user_content_parts == []
    else:
        assert request.system_prompt.startswith("base")
        assert "父亲" not in request.system_prompt
        assert request.extra_user_content_parts[0].text == (
            "<personal_network_context>父亲</personal_network_context>"
        )


@pytest.mark.asyncio
async def test_disabled_llm_query_tool_uses_recent_context_as_fallback():
    plugin = object.__new__(PersonalNetworkPlugin)
    plugin.config = {
        "enabled": True,
        "enable_llm_query_tool": False,
    }
    plugin.storage = MagicMock()
    plugin.storage.is_enabled.return_value = True
    plugin.storage.build_context.return_value = ""
    plugin._resolve_persona_id = AsyncMock(return_value="Caranlaf")

    event = MagicMock()
    event.unified_msg_origin = "webchat:FriendMessage:test"
    event.message_str = "他是谁"
    event.get_platform_name.return_value = "webchat"
    event.get_platform_id.return_value = "webchat"
    event.get_sender_id.return_value = "user"
    event.get_group_id.return_value = ""
    event.get_sender_name.return_value = "User"
    request = ProviderRequest(
        prompt="他是谁",
        system_prompt="base",
        contexts=[{"role": "user", "content": "我见到了 Alfred"}],
    )
    request.func_tool = MagicMock()

    await plugin.inject_network_context(event, request)

    request.func_tool.remove_tool.assert_called_once_with("query_personal_network")
    assert "query_personal_network" not in request.system_prompt
    matched_text = plugin.storage.build_context.call_args.args[1]
    assert "他是谁" in matched_text
    assert "Alfred" in matched_text


@pytest.mark.asyncio
async def test_disabled_llm_query_tool_rejects_direct_calls():
    plugin = object.__new__(PersonalNetworkPlugin)
    plugin.config = {
        "enabled": True,
        "enable_llm_query_tool": False,
    }

    result = await plugin.query_personal_network(MagicMock(), "Alfred")

    assert result == "LLM 主动查询人际网络工具已禁用。"
