"""Tests for relationship context injection triggers and placement."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.provider import ProviderRequest
from data.plugins.astrbot_plugin_personal_network.main import PersonalNetworkPlugin


def make_plugin(position: str = "system_prompt") -> PersonalNetworkPlugin:
    """Create a minimally configured plugin instance.

    Args:
        position: Requested relationship context injection position.

    Returns:
        Plugin instance with mocked storage and persona resolution.
    """
    plugin = object.__new__(PersonalNetworkPlugin)
    plugin.config = {
        "enabled": True,
        "enable_llm_query_tool": True,
        "context_injection_position": position,
        "pronoun_history_messages": 20,
        "pronoun_patterns": [r"(?<![其吉维])他(?!们)", "他们", "对方"],
    }
    plugin.storage = MagicMock()
    plugin.storage.is_enabled.return_value = True
    plugin.storage.build_context.return_value = (
        "<personal_network_context>父亲</personal_network_context>"
    )
    plugin._resolve_persona_id = AsyncMock(return_value="Caranlaf")
    return plugin


def make_event(message: str) -> MagicMock:
    """Create a mock AstrBot event.

    Args:
        message: Current user message.

    Returns:
        Event mock populated with sender metadata.
    """
    event = MagicMock()
    event.unified_msg_origin = "webchat:FriendMessage:test"
    event.message_str = message
    event.get_platform_name.return_value = "webchat"
    event.get_platform_id.return_value = "webchat"
    event.get_sender_id.return_value = "user"
    event.get_group_id.return_value = ""
    event.get_sender_name.return_value = "User"
    return event


@pytest.mark.asyncio
@pytest.mark.parametrize("position", ["system_prompt", "user_content"])
async def test_current_name_injects_without_history(position: str):
    plugin = make_plugin(position)
    request = ProviderRequest(
        prompt="ALFRED 是谁",
        system_prompt="base",
        contexts=[{"role": "user", "content": "我见到了 Mei"}],
    )

    await plugin.inject_network_context(make_event("ALFRED 是谁"), request)

    assert plugin.storage.build_context.call_args.args[1] == ["ALFRED 是谁"]
    if position == "system_prompt":
        assert "父亲" in request.system_prompt
        assert request.extra_user_content_parts == []
    else:
        assert "父亲" not in request.system_prompt
        assert request.extra_user_content_parts[0].text.endswith(
            "父亲</personal_network_context>"
        )


@pytest.mark.asyncio
async def test_pronoun_searches_recent_real_messages_in_reverse_order():
    plugin = make_plugin()
    request = ProviderRequest(
        prompt="他是谁",
        system_prompt="base",
        contexts=[
            {"role": "user", "content": "更早提到了 Lin"},
            {"role": "system", "content": "系统中的 Fake Person"},
            {"role": "assistant", "content": "最近提到了 Alfred 和 Mei"},
            {"role": "tool", "content": "工具中的 Tool Person"},
        ],
    )

    await plugin.inject_network_context(make_event("他是谁"), request)

    assert plugin.storage.build_context.call_args.args[1] == [
        "他是谁",
        "最近提到了 Alfred 和 Mei",
        "更早提到了 Lin",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["其他事情", "弹吉他", "维他命"])
async def test_common_words_do_not_trigger_single_pronoun_search(message: str):
    plugin = make_plugin()
    request = ProviderRequest(
        prompt=message,
        system_prompt="base",
        contexts=[{"role": "user", "content": "Alfred"}],
    )

    await plugin.inject_network_context(make_event(message), request)

    assert plugin.storage.build_context.call_args.args[1] == [message]


@pytest.mark.asyncio
async def test_history_limit_and_multimodal_text_are_respected():
    plugin = make_plugin()
    plugin.config["pronoun_history_messages"] = 2
    request = ProviderRequest(
        prompt="对方怎么样",
        system_prompt="base",
        contexts=[
            {"role": "user", "content": "太早的 Lin"},
            {"role": "assistant", "content": "第二条 Alfred"},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "test"}},
                    {"type": "text", "text": "最近的 Mei"},
                ],
            },
        ],
    )

    await plugin.inject_network_context(make_event("对方怎么样"), request)

    assert plugin.storage.build_context.call_args.args[1] == [
        "对方怎么样",
        "最近的 Mei",
        "第二条 Alfred",
    ]


@pytest.mark.asyncio
async def test_old_persisted_context_is_removed_and_not_reused():
    plugin = make_plugin("history_message")
    plugin.storage.build_context.return_value = ""
    request = ProviderRequest(
        prompt="你好",
        system_prompt="base",
        contexts=[
            {
                "role": "system",
                "content": "<personal_network_context>旧关系</personal_network_context>",
            },
            {"role": "user", "content": "普通消息"},
        ],
    )

    await plugin.inject_network_context(make_event("你好"), request)

    assert request.contexts == [{"role": "user", "content": "普通消息"}]
    assert "旧关系" not in request.system_prompt


@pytest.mark.asyncio
async def test_disabled_llm_query_tool_does_not_disable_pronoun_lookup():
    plugin = make_plugin()
    plugin.config["enable_llm_query_tool"] = False
    request = ProviderRequest(
        prompt="他是谁",
        system_prompt="base",
        contexts=[{"role": "user", "content": "Alfred"}],
    )
    request.func_tool = MagicMock()

    await plugin.inject_network_context(make_event("他是谁"), request)

    request.func_tool.remove_tool.assert_called_once_with("query_personal_network")
    assert plugin.storage.build_context.call_args.args[1] == ["他是谁", "Alfred"]


@pytest.mark.asyncio
async def test_disabled_llm_query_tool_rejects_direct_calls():
    plugin = make_plugin()
    plugin.config["enable_llm_query_tool"] = False

    result = await plugin.query_personal_network(MagicMock(), "Alfred")

    assert result == "LLM 主动查询人际网络工具已禁用。"
