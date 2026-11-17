import pytest
from tests.utils.load_fixture import load_fixture
from collectors.bybit import binance_alpha_collect_once, _norm_sym


def test_fixture_structure():
    """Фикстура должна содержать ключ 'data' со списком токенов."""
    data = load_fixture("binance_alpha/tokens.json")
    assert "data" in data
    assert isinstance(data["data"], list)
    assert len(data["data"]) > 0


def test_token_fields():
    """У каждого токена должны быть обязательные поля."""
    data = load_fixture("binance_alpha/tokens.json")
    for token in data["data"]:
        assert "symbol" in token
        assert "price" in token
        assert "volume24h" in token
        # цена – строка, которую можно преобразовать в float
        try:
            float(token["price"])
        except (ValueError, TypeError):
            pytest.fail(f"price is not a valid number: {token['price']}")

def test_parse_single_token():
    """Проверяем, как из одного токена получатся цена и объём."""
    data = load_fixture("binance_alpha/tokens.json")
    token = data["data"][0]

    raw_symbol = token["symbol"]
    price = float(token["price"])
    vol24h = float(token["volume24h"])

    assert price > 0
    assert vol24h > 0

    # Нормализованный символ (как в коллекторе)
    sym = (raw_symbol + "USDT").upper().replace("-", "").replace("_", "")
    assert sym.endswith("USDT")
    assert sym != raw_symbol


# ------------------ Моки ------------------

@pytest.fixture
def patch_fetch_alpha(monkeypatch):
    """
    Подменяет fetch_json в collectors.bybit, чтобы возвращать
    предварительно загруженную фикстуру Binance Alpha.
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
def alpha_message(patch_fetch_alpha, mock_session, fake_send_msg):
    """Фикстура, запускающая binance_alpha_collect_once и возвращающая отправленное сообщение."""
    # Загружаем фикстуру (один ответ API)
    api_response = load_fixture("binance_alpha/tokens.json")
    patch_fetch_alpha.data = [api_response]

    # Вызываем коллектор (он асинхронный, но запускаем через asyncio.run или в тесте с маркером asyncio)
    return None  # Будем вызывать в асинхронном тесте


@pytest.mark.asyncio
async def test_binance_alpha_collect_once(patch_fetch_alpha, mock_session, fake_send_msg):
    """Тест полного цикла коллектора: запрос → сообщение."""
    api_response = load_fixture("binance_alpha/tokens.json")
    patch_fetch_alpha.data = [api_response]

    await binance_alpha_collect_once(mock_session)

    assert len(fake_send_msg) == 1
    msg = fake_send_msg[0]

    # Заголовки
    assert msg["market"] == "BinanceAlpha"
    assert "data_usdt" in msg
    assert "data_spot" in msg
    assert "market_meta" in msg

    # Фьючерсов быть не должно
    assert len(msg["data_usdt"]) == 0

    # Спотовые данные
    spot = msg["data_spot"]
    meta = msg["market_meta"]
    assert len(spot) > 0

    for sym, arr in spot.items():
        assert isinstance(arr, list) and len(arr) == 3
        assert arr[0] == sym
        price = arr[1]
        assert isinstance(price, (int, float))
        assert price > 0
        # bid и ask совпадают
        assert arr[1] == arr[2]

        # Проверяем наличие метаданных и volume24h
        assert sym in meta
        assert "amount24_spot" in meta[sym]
        assert meta[sym]["amount24_spot"] >= 0
        # Проверяем наличие контракта и цепочки для построения ссылок
        assert "contract_address" in meta[sym], f"Missing contract_address for {sym}"
        assert "chain_name" in meta[sym], f"Missing chain_name for {sym}"
        assert isinstance(meta[sym]["contract_address"], str)
        assert isinstance(meta[sym]["chain_name"], str)

    # Символы должны оканчиваться на USDT
    for sym in spot:
        assert sym.endswith("USDT")


@pytest.mark.parametrize("inp,expected", [
    ("BTCUSDT", "BTCUSDT"),
    ("btc_usdt", "BTCUSDT"),
    ("btc-usdt", "BTCUSDT"),
    (123, 123),
    (None, None),
])
def test_norm_sym(inp, expected):
    """Нормализация символов (общая утилита)."""
    assert _norm_sym(inp) == expected


def test_spot_symbols_normalized_in_message(patch_fetch_alpha, mock_session, fake_send_msg):
    """После работы коллектора все спотовые символы нормализованы (через _norm_sym)."""
    # Для простоты снова запустим коллектор (можно вынести в общую фикстуру)
    import asyncio
    async def run():
        api_response = load_fixture("binance_alpha/tokens.json")
        patch_fetch_alpha.data = [api_response]
        await binance_alpha_collect_once(mock_session)

    asyncio.run(run())

    msg = fake_send_msg[0]
    spot = msg["data_spot"]
    for sym in spot.keys():
        # Если символ не совпадает с результатом _norm_sym, что-то пошло не так
        assert sym == _norm_sym(sym)