from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from data.plugins.astrbot_plugin_personal_network.main import (
    GENERATION_JOB_TTL_SECONDS,
    PersonalNetworkPlugin,
)


def make_plugin() -> PersonalNetworkPlugin:
    plugin = object.__new__(PersonalNetworkPlugin)
    plugin._generation_jobs = {}
    plugin._generation_tasks = set()
    plugin.storage = MagicMock()
    return plugin


def add_job(plugin: PersonalNetworkPlugin, job_id: str = "job-1") -> dict:
    now = time.monotonic()
    job = {
        "persona_id": "alice",
        "status": "pending",
        "result": None,
        "count": 1,
        "density": "sparse",
        "allow_fill_existing": False,
        "created_at": now,
        "updated_at": now,
    }
    plugin._generation_jobs[job_id] = job
    return job


@pytest.mark.asyncio
async def test_background_generation_retains_valid_result():
    plugin = make_plugin()
    job = add_job(plugin)
    plugin._persona_prompt = AsyncMock(return_value="A reserved architect.")
    plugin.storage.get_network.return_value = {"characters": [], "relationships": []}
    provider = MagicMock()
    provider.text_chat = AsyncMock(
        return_value=SimpleNamespace(completion_text='{"characters": [], "relationships": []}')
    )
    plugin._generation_provider = MagicMock(return_value=provider)
    expected = {"valid": True, "raw": "{}", "draft": {}, "errors": []}
    plugin._validate_generation_text = AsyncMock(return_value=expected)

    await plugin._run_generation_job(
        "job-1",
        persona_id="alice",
        count=1,
        density="sparse",
        allow_fill_existing=False,
        generation_hint="大学同学",
    )

    assert job["status"] == "completed"
    assert job["result"] == expected
    assert provider.text_chat.await_count == 1
    assert "大学同学" in provider.text_chat.await_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_background_generation_converts_provider_error_to_job_result():
    plugin = make_plugin()
    job = add_job(plugin)
    plugin._persona_prompt = AsyncMock(return_value="Persona")
    plugin.storage.get_network.return_value = {"characters": [], "relationships": []}
    provider = MagicMock()
    provider.text_chat = AsyncMock(side_effect=RuntimeError("provider unavailable"))
    plugin._generation_provider = MagicMock(return_value=provider)

    await plugin._run_generation_job(
        "job-1",
        persona_id="alice",
        count=1,
        density="sparse",
        allow_fill_existing=False,
        generation_hint="",
    )

    assert job["status"] == "failed"
    assert job["result"]["valid"] is False
    assert job["result"]["errors"] == ["provider unavailable"]


@pytest.mark.asyncio
async def test_generate_api_returns_before_background_provider_finishes():
    plugin = make_plugin()
    plugin._json_payload = AsyncMock(
        return_value={
            "persona_id": "alice",
            "count": 6,
            "density": "balanced",
            "allow_fill_existing": False,
            "generation_hint": "",
        }
    )
    plugin.storage.is_enabled.return_value = True
    release = asyncio.Event()
    plugin._run_generation_job = AsyncMock(side_effect=release.wait)

    response = await plugin.api_generate_network()
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["status"] in {"pending", "running"}
    assert payload["expected_count"] == 6
    assert len(plugin._generation_tasks) == 1
    assert not next(iter(plugin._generation_tasks)).done()

    await plugin.terminate()


def test_start_generation_reuses_active_job_for_persona():
    plugin = make_plugin()
    add_job(plugin)

    job_id, reused = plugin._start_generation_job(
        persona_id="alice",
        count=6,
        density="balanced",
        allow_fill_existing=False,
        generation_hint="",
    )

    assert job_id == "job-1"
    assert reused is True
    assert plugin._generation_tasks == set()


def test_completed_generation_jobs_expire_after_retention_window():
    plugin = make_plugin()
    job = add_job(plugin)
    job["status"] = "completed"
    job["updated_at"] = time.monotonic() - GENERATION_JOB_TTL_SECONDS - 1

    plugin._prune_generation_jobs()

    assert plugin._generation_jobs == {}


@pytest.mark.asyncio
async def test_terminate_cancels_generation_tasks_and_closes_storage():
    plugin = make_plugin()
    task = asyncio.create_task(asyncio.sleep(60))
    plugin._generation_tasks.add(task)
    add_job(plugin)

    await plugin.terminate()

    assert task.cancelled()
    assert plugin._generation_tasks == set()
    assert plugin._generation_jobs == {}
    plugin.storage.close.assert_called_once_with()
