import pytest
from tests.utils.load_fixture import load_fixture
from collectors.bybit import phemex_collect_once, _norm_sym, phemex_spot_scales
import asyncio


def test_norm_sym():
    """Проверка нормализации символов (общая функция)."""
    assert _norm_sym("BTC_USDT") == "BTCUSDT"
    assert _norm_sym("btc-usdt") == "BTCUSDT"
    assert _norm_sym("btcusdt") == "BTCUSDT"
    assert _norm_sym(123) == 123
    assert _norm_sym(None) is None


@pytest.fixture
def patch_fetch_phemex(monkeypatch):
    """
    Подмена fetch_json в модуле collectors.bybit – возвращает заранее загруженные фикстуры.
    Порядок вызовов в phemex_collect_once:
        1. phemex_update_products -> PHEMEX_PRODUCTS_URL
        2. fut_task -> PHEMEX_FUT_TICKER_URL
        3. spot_task -> PHEMEX_SPOT_TICKER_URL
        4. funding_task -> PHEMEX_REAL_FUNDING_URL
    """
    async def fake_fetch(session, url, proxy=None, timeout=12):
        return fake_fetch.data.pop(0)

    fake_fetch.data = []

    monkeypatch.setattr(
        "collectors.bybit.fetch_json",
        fake_fetch
    )

    return fake_fetch


@pytest.fixture
def fake_send_msg(monkeypatch):
    """Перехватывает вызов send_msg и сохраняет сообщения в список."""
    messages = []

    def _send(msg):
        messages.append(msg)

    monkeypatch.setattr("collectors.bybit.send_msg", _send)
    return messages


@pytest.fixture
def mock_session():
    """Фикстура, возвращающая объект aiohttp.ClientSession (не используется)."""
    return None


@pytest.mark.asyncio
async def test_phemex_collect_once(patch_fetch_phemex, mock_session, fake_send_msg):
    """Проверяет, что phemex_collect_once корректно формирует сообщение."""
    # Загружаем фикстуры из папки phemex
    products = load_fixture("phemex/products.json")        # ответ для /public/products
    fut_ticker = load_fixture("phemex/futures_ticker.json")   # dict с полем result
    spot_ticker = load_fixture("phemex/spot_ticker.json")     # dict с полем result
    funding = load_fixture("phemex/funding.json")             # dict с data.rows

    # Порядок важен: products, futures_ticker, spot_ticker, funding
    patch_fetch_phemex.data = [products, fut_ticker, spot_ticker, funding]

    # Обнуляем глобальный словарь перед тестом, чтобы phemex_update_products отработал
    global phemex_spot_scales
    phemex_spot_scales = {}

    await phemex_collect_once(mock_session)

    assert len(fake_send_msg) == 1

    msg = fake_send_msg[0]

    # Проверяем структуру сообщения
    assert "market" in msg
    assert msg["market"] == "Phemex"

    assert "data_usdt" in msg
    assert "data_spot" in msg
    assert "market_meta" in msg

    # Проверяем, что данные не пусты
    assert len(msg["data_usdt"]) > 0
    assert isinstance(msg["market_meta"], dict)


@pytest.fixture
async def phemex_message(patch_fetch_phemex, mock_session, fake_send_msg):
    """Фикстура, возвращающая сообщение от phemex_collect_once."""
    products = load_fixture("phemex/products.json")
    fut_ticker = load_fixture("phemex/futures_ticker.json")
    spot_ticker = load_fixture("phemex/spot_ticker.json")
    funding = load_fixture("phemex/funding.json")

    patch_fetch_phemex.data = [products, fut_ticker, spot_ticker, funding]

    global phemex_spot_scales
    phemex_spot_scales = {}

    await phemex_collect_once(mock_session)

    return fake_send_msg[0]


def test_consistency_structure(phemex_message):
    """Проверяет, что все символы из data_usdt присутствуют в market_meta."""
    usdt = phemex_message["data_usdt"]
    meta = phemex_message["market_meta"]

    symbols = {x[0] for x in usdt}

    assert symbols.issubset(meta.keys())
    assert len(meta) >= len(usdt)


def test_market_meta_fields(phemex_message):
    """Проверяет наличие обязательных полей в market_meta для первого символа."""
    meta = phemex_message["market_meta"]
    first_symbol = next(iter(meta))
    entry = meta[first_symbol]

    required_keys = {
        "fundingInterval", "fee", "predict",
        "bestBid", "bestAsk", "index_corr", "amount24"
    }
    assert required_keys.issubset(entry.keys())

    assert isinstance(entry["fundingInterval"], int)
    assert isinstance(entry["fee"], float)
    assert isinstance(entry["bestBid"], float)
    assert isinstance(entry["bestAsk"], float)
    assert isinstance(entry["index_corr"], float)
    assert isinstance(entry["amount24"], int)


def test_data_usdt_format(phemex_message):
    """Проверяет формат каждой записи в data_usdt."""
    for row in phemex_message["data_usdt"]:
        assert len(row) == 8
        assert isinstance(row[0], str)
        assert isinstance(row[1], float)
        assert isinstance(row[2], float)
        assert row[3] == 0
        assert isinstance(row[4], float)
        assert row[5] == 0
        assert isinstance(row[6], float)
        assert row[7] == 0


def test_data_spot_format(phemex_message):
    """Проверяет формат каждой записи в data_spot."""
    for sym, row in phemex_message["data_spot"].items():
        assert isinstance(sym, str)
        assert len(row) == 3
        assert row[0] == sym
        assert isinstance(row[1], float)
        assert isinstance(row[2], float)


def test_funding_interval_from_funding_fixture(phemex_message):
    """
    Проверяет, что fundingInterval берётся из funding-фикстуры.
    """
    funding_data = load_fixture("phemex/funding.json")
    if not funding_data:
        return

    funding_map = {}
    rows = funding_data.get('data', {}).get('rows', [])
    for item in rows:
        sym = item.get("symbol")
        interval_sec = item.get("fundingInterval")
        if sym and interval_sec:
            funding_map[sym] = interval_sec // 3600

    if not phemex_message["data_usdt"]:
        return
    first_sym = phemex_message["data_usdt"][0][0]
    expected_interval = funding_map.get(first_sym)
    if expected_interval is not None:
        actual_interval = phemex_message["market_meta"][first_sym]["fundingInterval"]
        assert actual_interval == expected_interval