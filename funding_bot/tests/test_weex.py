import pytest
from tests.utils.load_fixture import load_fixture
from collectors.bybit import weex_collect_once, _norm_sym
import asyncio


def test_norm_sym():
    """Проверка нормализации символов (общая функция)."""
    assert _norm_sym("BTC_USDT") == "BTCUSDT"
    assert _norm_sym("btc-usdt") == "BTCUSDT"
    assert _norm_sym("btcusdt") == "BTCUSDT"
    assert _norm_sym(123) == 123
    assert _norm_sym(None) is None


@pytest.fixture
def patch_fetch_weex(monkeypatch):
    """
    Подмена fetch_json в модуле collectors.bybit – возвращает заранее загруженные фикстуры.
    Порядок вызовов в weex_collect_once:
        1. ticker_task -> WEEX_FUT_TICKER_URL
        2. funding_task -> WEEX_FUNDING_URL
        3. book_task -> WEEX_BOOK_URL
        4. spot_book_task -> WEEX_SPOT_BOOK_URL
        5. spot_24hr_task -> WEEX_SPOT_24HR_URL
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
    # В тестах сессия не используется, так как fetch_json подменён.
    return None


@pytest.mark.asyncio
async def test_weex_collect_once(patch_fetch_weex, mock_session, fake_send_msg):
    """Проверяет, что weex_collect_once корректно формирует сообщение."""
    # Загружаем фикстуры из папки weex
    fut_ticker = load_fixture("weex/futures_ticker.json")   # список
    funding = load_fixture("weex/funding.json")             # список
    book = load_fixture("weex/book.json")                   # список
    spot_book = load_fixture("weex/spot_book.json")         # список
    spot_24hr = load_fixture("weex/spot_24hr.json")         # список

    # Порядок важен: ticker, funding, book, spot_book, spot_24hr
    patch_fetch_weex.data = [fut_ticker, funding, book, spot_book, spot_24hr]

    await weex_collect_once(mock_session)

    assert len(fake_send_msg) == 1

    msg = fake_send_msg[0]

    # Проверяем структуру сообщения
    assert "market" in msg
    assert msg["market"] == "WEEX"

    assert "data_usdt" in msg
    assert "data_spot" in msg
    assert "market_meta" in msg

    # Проверяем, что данные не пусты
    assert len(msg["data_usdt"]) > 0
    assert isinstance(msg["market_meta"], dict)


@pytest.fixture
async def weex_message(patch_fetch_weex, mock_session, fake_send_msg):
    """Фикстура, возвращающая сообщение от weex_collect_once."""
    fut_ticker = load_fixture("weex/futures_ticker.json")
    funding = load_fixture("weex/funding.json")
    book = load_fixture("weex/book.json")
    spot_book = load_fixture("weex/spot_book.json")
    spot_24hr = load_fixture("weex/spot_24hr.json")

    patch_fetch_weex.data = [fut_ticker, funding, book, spot_book, spot_24hr]

    await weex_collect_once(mock_session)

    return fake_send_msg[0]


def test_consistency_structure(weex_message):
    """Проверяет, что все символы из data_usdt присутствуют в market_meta."""
    usdt = weex_message["data_usdt"]
    meta = weex_message["market_meta"]

    symbols = {x[0] for x in usdt}

    # все символы должны быть ключами в meta
    assert symbols.issubset(meta.keys())
    # meta может содержать больше ключей (например, если есть спот-символы без фьючерсов)
    assert len(meta) >= len(usdt)


def test_market_meta_fields(weex_message):
    """Проверяет наличие обязательных полей в market_meta для первого символа."""
    meta = weex_message["market_meta"]
    first_symbol = next(iter(meta))
    entry = meta[first_symbol]

    required_keys = {
        "fundingInterval", "fee", "predict",
        "bestBid", "bestAsk", "index_corr", "amount24"
    }
    assert required_keys.issubset(entry.keys())

    # Типы полей
    assert isinstance(entry["fundingInterval"], int)
    assert isinstance(entry["fee"], float)
    assert isinstance(entry["bestBid"], float)
    assert isinstance(entry["bestAsk"], float)
    assert isinstance(entry["index_corr"], float)
    assert isinstance(entry["amount24"], int)


def test_data_usdt_format(weex_message):
    """Проверяет формат каждой записи в data_usdt."""
    for row in weex_message["data_usdt"]:
        # Должно быть 8 элементов: [symbol, funding%, bid, 0, index_corr, 0, ask, 0]
        assert len(row) == 8
        assert isinstance(row[0], str)
        assert isinstance(row[1], float)   # funding %
        assert isinstance(row[2], float)   # bid
        assert row[3] == 0
        assert isinstance(row[4], float)   # index_corr
        assert row[5] == 0
        assert isinstance(row[6], float)   # ask
        assert row[7] == 0


def test_data_spot_format(weex_message):
    """Проверяет формат каждой записи в data_spot."""
    for sym, row in weex_message["data_spot"].items():
        # row должно быть [symbol, bid, ask] или список из 3 элементов
        assert isinstance(sym, str)
        assert len(row) == 3
        assert row[0] == sym
        assert isinstance(row[1], float)
        assert isinstance(row[2], float)