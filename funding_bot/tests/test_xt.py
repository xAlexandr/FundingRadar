import pytest
from tests.utils.load_fixture import load_fixture
from collectors.bybit import compute_xt_meta, _norm_sym, xt_collect_once
import asyncio


def test_compute_xt_meta_from_fixture():
    """Проверяет, что compute_xt_meta корректно извлекает поля из первого контракта."""
    data = load_fixture("xt/futures.json")  # это список контрактов
    item = data[0]  # берём первый элемент

    meta = compute_xt_meta(item)

    assert isinstance(meta["funding"], float)
    assert isinstance(meta["bestBid"], float)
    assert isinstance(meta["bestAsk"], float)
    assert isinstance(meta["index_corr"], float)
    assert isinstance(meta["amount24"], int)  # amount24 округляется до целого


def test_compute_xt_meta_real_values():
    """Проверяет разумные диапазоны для первых 10 контрактов."""
    data = load_fixture("xt/futures.json")

    for item in data[:10]:
        meta = compute_xt_meta(item)

        # funding в процентах, обычно в пределах -5%..5%, но допустим -100..100
        assert -100 <= meta["funding"] <= 100

        # цены не отрицательные
        assert meta["bestBid"] >= 0
        assert meta["bestAsk"] >= 0

        # коррекция обычно в пределах разумного
        assert -50 <= meta["index_corr"] <= 50

        # amount24 – неотрицательное целое
        assert meta["amount24"] >= 0


@pytest.mark.parametrize("inp,expected", [
    ("BTC_USDT", "BTCUSDT"),
    ("btc-usdt", "BTCUSDT"),
    ("btcusdt", "BTCUSDT"),
    (123, 123),
    (None, None),
])
def test_norm_sym(inp, expected):
    """Проверяет нормализацию символов (общая функция)."""
    assert _norm_sym(inp) == expected


@pytest.fixture
def patch_fetch_xt(monkeypatch):
    """
    Подмена fetch_json в модуле collectors.xt – возвращает заранее загруженные фикстуры.
    """
    async def fake_fetch(session, url, proxy=None, timeout=12):
        return fake_fetch.data.pop(0)

    fake_fetch.data = []

    monkeypatch.setattr(
        "collectors.bybit.fetch_json",
        fake_fetch
    )

    return fake_fetch


@pytest.mark.asyncio
async def test_xt_collect_once(patch_fetch_xt, mock_session, fake_send_msg):
    """Проверяет, что xt_collect_once корректно формирует сообщение."""
    fut = load_fixture("xt/futures.json")   # список
    spot = load_fixture("xt/spot.json")     # {"result": [...]}

    # порядок важен: сначала futures, потом spot (как в xt_collect_once)
    patch_fetch_xt.data = [fut, spot]

    await xt_collect_once(mock_session)

    assert len(fake_send_msg) == 1

    msg = fake_send_msg[0]

    # структура
    assert "market" in msg
    assert msg["market"] == "XT"

    assert "data_usdt" in msg
    assert "data_spot" in msg
    assert "market_meta" in msg

    # базовые инварианты
    assert len(msg["data_usdt"]) > 0
    assert isinstance(msg["market_meta"], dict)


@pytest.fixture
async def xt_message(patch_fetch_xt, mock_session, fake_send_msg):
    """Фикстура, возвращающая сообщение от xt_collect_once."""
    futures_task = load_fixture("xt/futures.json")
    spot_task = load_fixture("xt/spot.json")

    patch_fetch_xt.data = [futures_task, spot_task]

    await xt_collect_once(mock_session)

    return fake_send_msg[0]


def test_consistency_structure(xt_message):
    """Проверяет, что все символы из data_usdt присутствуют в market_meta."""
    usdt = xt_message["data_usdt"]
    meta = xt_message["market_meta"]

    symbols = {x[0] for x in usdt}

    # все символы должны быть ключами в meta
    assert symbols.issubset(meta.keys())
    # meta может содержать больше ключей (например, если есть спот-символы без фьючерсов)
    assert len(meta) >= len(usdt)