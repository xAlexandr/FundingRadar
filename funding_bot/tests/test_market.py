import pytest
from core.market import MarketState
from pathlib import Path

# Ожидаемый список бирж (порядок важен, совпадает с кодом)
EXPECTED_MARKETS = [
    'Bybit', 'Mexc', 'Kucoin', 'Gateio', 'Bitget', 'Huobi', 'Okx',
    'Binance', 'BingX', 'BitMart', 'Ourbit', 'Hyperliquid', 'LBank', 'Aster', 'XT', 'CoinEx', 'WEEX',
    'Phemex', 'BinanceAlpha'
]


@pytest.fixture
def market_state():
    """Создаёт свежий экземпляр MarketState для каждого теста."""
    return MarketState()


def test_markets_list(market_state):
    """Проверяет, что список market содержит все ожидаемые биржи и совпадает с ключами словарей."""
    assert market_state.markets == EXPECTED_MARKETS
    assert set(market_state.market.keys()) == set(EXPECTED_MARKETS)
    assert set(market_state.market_spot.keys()) == set(EXPECTED_MARKETS)
    assert set(market_state.fees.keys()) == set(EXPECTED_MARKETS)
    assert set(market_state.fees_fut.keys()) == set(EXPECTED_MARKETS)


def test_market_indexes_sequential(market_state):
    """
    Проверяет, что индексы в self.market:
    - для каждой биржи список длиной 8 (имя + 7 чисел),
    - числа образуют непрерывную последовательность от 1 до 7*N без пропусков,
      где N — количество бирж.
    """
    all_indexes = []
    for exchange, indices in market_state.market.items():
        assert len(indices) == 8, f"Для {exchange} ожидается 8 элементов, получено {len(indices)}"
        assert indices[0] == exchange, f"Первый элемент для {exchange} должен быть названием биржи"
        for idx in indices[1:]:
            assert isinstance(idx, int), f"Индекс {idx} для {exchange} не является целым числом"
            all_indexes.append(idx)

    n = len(market_state.market)  # количество бирж
    expected_max_index = 7 * n
    expected_range = list(range(1, expected_max_index + 1))

    assert len(all_indexes) == len(set(all_indexes)), "Индексы не уникальны"
    assert min(all_indexes) == 1, f"Минимальный индекс должен быть 1, получен {min(all_indexes)}"
    assert max(all_indexes) == expected_max_index, \
        f"Максимальный индекс должен быть {expected_max_index} (7 * {n}), а не {max(all_indexes)}"
    assert sorted(all_indexes) == expected_range, \
        f"Индексы не образуют непрерывный диапазон 1..{expected_max_index}"


def test_market_spot_indexes_sequential(market_state):
    """
    Проверяет, что индексы в self.market_spot:
    - для каждой биржи список длиной 2 (два числа),
    - числа образуют непрерывную последовательность от 1 до 2*N без пропусков,
      где N — количество бирж.
    """
    all_indexes = []
    for exchange, indices in market_state.market_spot.items():
        assert len(indices) == 2, f"Для {exchange} ожидается 2 элемента, получено {len(indices)}"
        for idx in indices:
            assert isinstance(idx, int), f"Индекс {idx} для {exchange} не является целым числом"
            all_indexes.append(idx)

    n = len(market_state.market_spot)  # количество бирж
    expected_max_index = 2 * n
    expected_range = list(range(1, expected_max_index + 1))

    assert len(all_indexes) == len(set(all_indexes)), "Индексы не уникальны"
    assert min(all_indexes) == 1, f"Минимальный индекс должен быть 1, получен {min(all_indexes)}"
    assert max(all_indexes) == expected_max_index, \
        f"Максимальный индекс должен быть {expected_max_index} (2 * {n}), а не {max(all_indexes)}"
    assert sorted(all_indexes) == expected_range, \
        f"Индексы не образуют непрерывный диапазон 1..{expected_max_index}"

def test_data_length_constants(market_state):
    """
    Проверяет константы длины массивов на соответствие количеству бирж.
    Формулы (N = число бирж):
        data_usdt_len_massiv = 1 + 7*N        (символ + 7 полей на биржу)
        data_to_spot_len_massiv = 1 + 2*N     (символ + 2 поля на биржу)
        len_data_usdt = 3 + 7*N               (запас +2 относительно data_usdt_len_massiv)

    Для текущих 14 бирж:
        data_usdt_len_massiv = 1 + 98 = 99
        data_to_spot_len_massiv = 1 + 28 = 29
        len_data_usdt = 3 + 98 = 101

    Также проверяется, что все индексы из self.market не выходят за пределы len_data_usdt.
    """
    n = len(EXPECTED_MARKETS)
    expected_futures_len = 1 + 7 * n
    expected_spot_len = 1 + 2 * n
    expected_len_data_usdt = 3 + 7 * n

    assert market_state.data_usdt_len_massiv == expected_futures_len, \
        f"data_usdt_len_massiv должно быть {expected_futures_len} (1 + 7*{n}), а не {market_state.data_usdt_len_massiv}"

    assert market_state.data_to_spot_len_massiv == expected_spot_len, \
        f"data_to_spot_len_massiv должно быть {expected_spot_len} (1 + 2*{n}), а не {market_state.data_to_spot_len_massiv}"

    assert market_state.len_data_usdt == expected_len_data_usdt, \
        f"len_data_usdt должно быть {expected_len_data_usdt} (3 + 7*{n}), а не {market_state.len_data_usdt}"

    # Проверяем, что все индексы из self.market не превышают len_data_usdt - 1
    max_index = max(max(indices[1:]) for indices in market_state.market.values())
    assert max_index < market_state.len_data_usdt, \
        f"Максимальный индекс {max_index} должен быть меньше len_data_usdt ({market_state.len_data_usdt})"


def test_fees_contain_all_markets(market_state):
    """Проверяет, что fees и fees_fut содержат все биржи и значения являются числами."""
    for exchange in EXPECTED_MARKETS:
        assert exchange in market_state.fees, f"Биржа {exchange} отсутствует в self.fees"
        assert exchange in market_state.fees_fut, f"Биржа {exchange} отсутствует в self.fees_fut"
        assert isinstance(market_state.fees[exchange], (int, float)), \
            f"Значение fees для {exchange} не число: {market_state.fees[exchange]}"
        assert isinstance(market_state.fees_fut[exchange], (int, float)), \
            f"Значение fees_fut для {exchange} не число: {market_state.fees_fut[exchange]}"


def test_blacklists_are_sets_of_tuples(market_state):
    """Проверяет, что blacklist_futures и blacklist_spot являются множествами кортежей правильной структуры."""
    for blacklist in (market_state.blacklist_futures, market_state.blacklist_spot):
        assert isinstance(blacklist, set), "Чёрный список должен быть множеством"
        for item in blacklist:
            assert isinstance(item, tuple), "Элемент чёрного списка должен быть кортежем"
            assert len(item) == 2, "Кортеж должен содержать 2 элемента: (symbol, frozenset)"
            symbol, markets_set = item
            assert isinstance(symbol, str), "Символ должен быть строкой"
            assert isinstance(markets_set, frozenset), "Второй элемент должен быть frozenset"
            for m in markets_set:
                assert isinstance(m, str), "Биржа в frozenset должна быть строкой"


def test_market_structure_internal_dicts(market_state):
    """
    Проверяет, что внутренние словари (bids_asks_futures_all, bids_asks_spot_all, extra_meta_per_market)
    инициализированы для всех бирж.
    """
    for exchange in EXPECTED_MARKETS:
        assert exchange in market_state.bids_asks_futures_all, \
            f"bids_asks_futures_all не содержит {exchange}"
        assert exchange in market_state.bids_asks_spot_all, \
            f"bids_asks_spot_all не содержит {exchange}"
        assert exchange in market_state.extra_meta_per_market, \
            f"extra_meta_per_market не содержит {exchange}"
        assert market_state.bids_asks_futures_all[exchange] == {}, \
            f"bids_asks_futures_all[{exchange}] должен быть пустым словарём"
        assert market_state.bids_asks_spot_all[exchange] == {}, \
            f"bids_asks_spot_all[{exchange}] должен быть пустым словарём"
        assert market_state.extra_meta_per_market[exchange] == {}, \
            f"extra_meta_per_market[{exchange}] должен быть пустым словарём"


def test_initial_flags_and_lock(market_state):
    """Проверяет начальные значения флагов и блокировки."""
    assert market_state.dirty is False
    assert market_state.dirty_markets == set()
    assert hasattr(market_state, 'lock')
    assert market_state.currentUpdated == 'updated2'


def test_norm_sym_method(market_state):
    """Проверяет метод _norm_sym."""
    assert market_state._norm_sym("BTC_USDT") == "BTCUSDT"
    assert market_state._norm_sym("btc-usdt") == "BTCUSDT"
    assert market_state._norm_sym("btcusdt") == "BTCUSDT"
    assert market_state._norm_sym(123) == 123
    assert market_state._norm_sym(None) is None


def test_dex_base_method(market_state):
    """Проверяет метод _dex_base."""
    assert market_state._dex_base("ETH_TONUSDT") == "TONUSDT"
    assert market_state._dex_base("TONUSDT") == "TONUSDT"
    assert market_state._dex_base(123) == 123
    assert market_state._dex_base(None) is None

def test_base_markets_up_to_date():
    """
    Проверяет, что список base_markets в файле add_market_to_db.py (на уровень выше)
    содержит все биржи из EXPECTED_MARKETS (каждая с суффиксом _1).
    Допускается наличие дополнительных записей, например DEX_1, которых нет в EXPECTED_MARKETS.
    """
    root_dir = Path(__file__).resolve().parent.parent
    update_file = root_dir / "add_market_to_db.py"
    assert update_file.exists(), f"Файл {update_file} не найден. Убедитесь, что скрипт обновления БД находится в корне."

    content = update_file.read_text(encoding='utf-8')
    import re
    match = re.search(r'base_markets\s*=\s*\[([^\]]+)\]', content, re.DOTALL)
    assert match, "Не найдено определение base_markets в файле"

    list_str = match.group(1)
    items = re.findall(r"'([^']+)'", list_str)
    # Извлекаем имена без суффикса _1
    base_names = set()
    for item in items:
        if item.endswith('_1'):
            base_names.add(item[:-2])  # удаляем _1
        else:
            # если есть без суффикса, добавим как есть (хотя по логике все должны быть с _1)
            base_names.add(item)

    expected_names = set(EXPECTED_MARKETS)
    missing = expected_names - base_names
    assert not missing, f"В base_markets отсутствуют биржи: {missing}"

    # Опционально: можно вывести предупреждение, если есть лишние имена (кроме DEX)
    extra = base_names - expected_names
    if extra:
        allowed_extra = {'DEX'}  # разрешённые дополнительные записи
        unexpected = extra - allowed_extra
        if unexpected:
            pytest.warns(UserWarning, f"В base_markets есть неожиданные имена: {unexpected}")