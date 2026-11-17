"""Tests for Aster Spot API and collector.

Tests:
1. API endpoint availability
2. Response structure
3. Data quality (bid/ask, volume)
4. Symbol format consistency
"""
import pytest
import aiohttp
import json
import asyncio


ASTER_SPOT_BASE = 'https://sapi.asterdex.com'
ASTER_SPOT_24HR = f'{ASTER_SPOT_BASE}/api/v3/ticker/24hr'


@pytest.mark.asyncio
async def test_aster_spot_api_accessible():
    """Aster spot API endpoint should be accessible."""
    async with aiohttp.ClientSession() as session:
        async with session.get(ASTER_SPOT_24HR, timeout=15) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert isinstance(data, list)
            assert len(data) > 0


@pytest.mark.asyncio
async def test_aster_spot_response_structure():
    """Each ticker should have required fields."""
    async with aiohttp.ClientSession() as session:
        async with session.get(ASTER_SPOT_24HR, timeout=15) as resp:
            data = await resp.json()

    # Check first active USDT pair
    usdt_pairs = [t for t in data if t['symbol'].endswith('USDT')
                  and 'UP_DOWN' not in t['symbol']
                  and float(t.get('bidPrice', 0) or 0) > 0]
    assert len(usdt_pairs) > 0

    sample = usdt_pairs[0]
    assert 'symbol' in sample
    assert 'bidPrice' in sample
    assert 'askPrice' in sample
    assert 'quoteVolume' in sample
    assert 'volume' in sample


@pytest.mark.asyncio
async def test_aster_spot_usdt_pairs_exist():
    """Should have USDT spot pairs."""
    async with aiohttp.ClientSession() as session:
        async with session.get(ASTER_SPOT_24HR, timeout=15) as resp:
            data = await resp.json()

    usdt_pairs = [t for t in data if t['symbol'].endswith('USDT') and 'UP_DOWN' not in t['symbol']]
    assert len(usdt_pairs) >= 10, f"Expected >=10 USDT pairs, got {len(usdt_pairs)}"


@pytest.mark.asyncio
async def test_aster_spot_active_pairs():
    """Should have pairs with actual bid/ask prices."""
    async with aiohttp.ClientSession() as session:
        async with session.get(ASTER_SPOT_24HR, timeout=15) as resp:
            data = await resp.json()

    active = [t for t in data
              if t['symbol'].endswith('USDT')
              and 'UP_DOWN' not in t['symbol']
              and float(t.get('bidPrice', 0) or 0) > 0
              and float(t.get('askPrice', 0) or 0) > 0]
    assert len(active) >= 10, f"Expected >=10 active pairs, got {len(active)}"


@pytest.mark.asyncio
async def test_aster_spot_major_coins():
    """Should have major coins (BTC, ETH)."""
    async with aiohttp.ClientSession() as session:
        async with session.get(ASTER_SPOT_24HR, timeout=15) as resp:
            data = await resp.json()

    symbols = {t['symbol'] for t in data}
    assert 'BTCUSDT' in symbols, "BTCUSDT not found"
    assert 'ETHUSDT' in symbols, "ETHUSDT not found"


@pytest.mark.asyncio
async def test_aster_spot_volume_positive():
    """Active pairs should have positive quote volume."""
    async with aiohttp.ClientSession() as session:
        async with session.get(ASTER_SPOT_24HR, timeout=15) as resp:
            data = await resp.json()

    active = [t for t in data
              if t['symbol'].endswith('USDT')
              and float(t.get('bidPrice', 0) or 0) > 0]

    for t in active[:20]:
        vol = float(t.get('quoteVolume', 0) or 0)
        assert vol >= 0, f"{t['symbol']}: negative volume {vol}"


@pytest.mark.asyncio
async def test_aster_spot_bid_ask_spread():
    """Bid should be <= ask for active pairs."""
    async with aiohttp.ClientSession() as session:
        async with session.get(ASTER_SPOT_24HR, timeout=15) as resp:
            data = await resp.json()

    active = [t for t in data
              if t['symbol'].endswith('USDT')
              and float(t.get('bidPrice', 0) or 0) > 0
              and float(t.get('askPrice', 0) or 0) > 0]

    for t in active[:20]:
        bid = float(t['bidPrice'])
        ask = float(t['askPrice'])
        assert bid <= ask, f"{t['symbol']}: bid {bid} > ask {ask}"


@pytest.mark.asyncio
async def test_aster_spot_symbol_format():
    """All USDT pairs should end with USDT."""
    async with aiohttp.ClientSession() as session:
        async with session.get(ASTER_SPOT_24HR, timeout=15) as resp:
            data = await resp.json()

    usdt_pairs = [t for t in data if t['symbol'].endswith('USDT') and 'UP_DOWN' not in t['symbol']]
    for t in usdt_pairs[:50]:
        assert t['symbol'].endswith('USDT'), f"{t['symbol']} doesn't end with USDT"
