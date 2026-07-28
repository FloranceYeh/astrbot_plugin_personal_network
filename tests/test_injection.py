"""Tests for relationship context injection placement."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.provider import ProviderRequest
from data.plugins.astrbot_plugin_personal_network.main import PersonalNetworkPlugin


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "position", ["system_prompt", "user_content", "history_message"]
)
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
        contexts=[
            {
                "role": "system",
                "content": (
                    "<personal_network_context>旧关系</personal_network_context>"
                ),
            },
            {"role": "user", "content": "我见到了 FLF"},
        ],
    )

    await plugin.inject_network_context(event, request)

    matched_text = plugin.storage.build_context.call_args.args[1]
    assert matched_text == "Alfred 是谁"
    assert "旧关系" not in str(request.contexts)
    if position == "system_prompt":
        assert "父亲" in request.system_prompt
        assert request.extra_user_content_parts == []
    elif position == "user_content":
        assert request.system_prompt.startswith("base")
        assert "父亲" not in request.system_prompt
        assert request.extra_user_content_parts[0].text == (
            "<personal_network_context>父亲</personal_network_context>"
        )
    else:
        assert "父亲" not in request.system_prompt
        assert request.extra_user_content_parts == []
        assert request.contexts[-1] == {
            "role": "system",
            "content": "<personal_network_context>父亲</personal_network_context>",
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("position", ["history_message", "system_prompt"])
async def test_persisted_context_is_deduplicated_or_removed(position: str):
    plugin = object.__new__(PersonalNetworkPlugin)
    plugin.config = {
        "enabled": True,
        "enable_llm_query_tool": True,
        "context_injection_position": position,
    }
    plugin.storage = MagicMock()
    plugin.storage.is_enabled.return_value = True
    plugin.storage.build_context.return_value = ""
    plugin._resolve_persona_id = AsyncMock(return_value="Caranlaf")

    event = MagicMock()
    event.unified_msg_origin = "webchat:FriendMessage:test"
    event.message_str = "你好"
    event.get_platform_name.return_value = "webchat"
    event.get_platform_id.return_value = "webchat"
    event.get_sender_id.return_value = "user"
    event.get_group_id.return_value = ""
    event.get_sender_name.return_value = "User"
    old_context = "<personal_network_context>旧关系</personal_network_context>"
    latest_context = "<personal_network_context>最新关系</personal_network_context>"
    request = ProviderRequest(
        prompt="你好",
        system_prompt="base",
        contexts=[
            {"role": "system", "content": old_context},
            {"role": "user", "content": "上一条真实消息"},
            {"role": "system", "content": latest_context},
        ],
    )

    await plugin.inject_network_context(event, request)

    network_messages = [
        message
        for message in request.contexts
        if isinstance(message, dict)
        and str(message.get("content", "")).startswith(
            "<personal_network_context>"
        )
    ]
    if position == "history_message":
        assert network_messages == [{"role": "system", "content": latest_context}]
        assert request.contexts[-1] == network_messages[0]
    else:
        assert network_messages == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback_enabled", [True, False])
async def test_recent_context_fallback_is_configurable(fallback_enabled: bool):
    plugin = object.__new__(PersonalNetworkPlugin)
    plugin.config = {
        "enabled": True,
        "enable_llm_query_tool": False,
        "enable_recent_context_fallback": fallback_enabled,
        "recent_context_fallback_messages": 1,
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
        contexts=[
            {"role": "user", "content": "我见到了 FLF"},
            {"role": "assistant", "content": "你刚刚见到了 Alfred"},
        ],
    )
    request.func_tool = MagicMock()

    await plugin.inject_network_context(event, request)

    request.func_tool.remove_tool.assert_called_once_with("query_personal_network")
    assert "query_personal_network" not in request.system_prompt
    matched_text = plugin.storage.build_context.call_args.args[1]
    assert "他是谁" in matched_text
    assert ("Alfred" in matched_text) is fallback_enabled
    assert "FLF" not in matched_text


@pytest.mark.asyncio
async def test_disabled_llm_query_tool_rejects_direct_calls():
    plugin = object.__new__(PersonalNetworkPlugin)
    plugin.config = {
        "enabled": True,
        "enable_llm_query_tool": False,
    }

    result = await plugin.query_personal_network(MagicMock(), "Alfred")

    assert result == "LLM 主动查询人际网络工具已禁用。"
