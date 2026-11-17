import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

import pytest
import asyncio
from unittest.mock import AsyncMock

from collectors.bybit import (
    compute_bybit_meta,
    _norm_sym,
    bybit_collect_once
)

@pytest.fixture
def mock_session():
    return AsyncMock()

@pytest.fixture
def fake_send_msg(monkeypatch):
    calls = []

    def fake(msg):
        calls.append(msg)

    monkeypatch.setattr("collectors.bybit.send_msg", fake)
    return calls


@pytest.fixture
def patch_fetch(monkeypatch):
    """
    Подмена fetch_json → возвращает заранее загруженные фикстуры
    """
    async def fake_fetch(session, url, proxy=None, timeout=10):
        return fake_fetch.data.pop(0)

    fake_fetch.data = []

    monkeypatch.setattr(
        "collectors.bybit.fetch_json",
        fake_fetch
    )

    return fake_fetch


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()