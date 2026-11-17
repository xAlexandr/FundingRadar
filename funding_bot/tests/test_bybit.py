import pytest
from tests.utils.load_fixture import load_fixture
from collectors.bybit import compute_bybit_meta, _norm_sym, bybit_collect_once
import asyncio

def test_compute_bybit_meta_from_fixture():
    data = load_fixture("bybit/futures.json")

    item = data["result"]["list"][0]   # берём РЕАЛЬНЫЙ элемент

    meta = compute_bybit_meta(item)

    assert isinstance(meta["funding"], float)
    assert isinstance(meta["bestBid"], float)
    assert isinstance(meta["bestAsk"], float)
    assert isinstance(meta["index_corr"], float)
    assert isinstance(meta["amount24"], int)

def test_compute_bybit_meta_real_values():
    data = load_fixture("bybit/futures.json")

    for item in data["result"]["list"][:10]:  # первые 10 монет
        meta = compute_bybit_meta(item)

        # funding всегда %
        assert -100 <= meta["funding"] <= 100

        # цены не отрицательные
        assert meta["bestBid"] >= 0
        assert meta["bestAsk"] >= 0

        # коррекция разумная
        assert -50 <= meta["index_corr"] <= 50

@pytest.mark.parametrize("inp,expected", [
    ("BTC_USDT", "BTCUSDT"),
    ("btc-usdt", "BTCUSDT"),
    ("btcusdt", "BTCUSDT"),
    (123, 123),
    (None, None),
])
def test_norm_sym(inp, expected):
    assert _norm_sym(inp) == expected

@pytest.mark.asyncio
async def test_bybit_collect_once(patch_fetch, mock_session, fake_send_msg):

    fut = load_fixture("bybit/futures.json")
    spot = load_fixture("bybit/spot.json")

    # порядок важен (gather → fut, spot)
    patch_fetch.data = [fut, spot]

    await bybit_collect_once(mock_session)

    assert len(fake_send_msg) == 1

    msg = fake_send_msg[0]

    # структура
    assert "market" in msg
    assert msg["market"] == "Bybit"

    assert "data_usdt" in msg
    assert "data_spot" in msg
    assert "market_meta" in msg

    # базовые инварианты
    assert len(msg["data_usdt"]) > 0
    assert isinstance(msg["market_meta"], dict)


@pytest.fixture
async def bybit_message(patch_fetch, mock_session, fake_send_msg):
    fut = load_fixture("bybit/futures.json")
    spot = load_fixture("bybit/spot.json")

    patch_fetch.data = [fut, spot]

    await bybit_collect_once(mock_session)

    return fake_send_msg[0]

def test_consistency_structure(bybit_message):

    usdt = bybit_message["data_usdt"]
    meta = bybit_message["market_meta"]

    symbols = {x[0] for x in usdt}

    assert symbols.issubset(meta.keys())
    assert len(meta) >= len(usdt)