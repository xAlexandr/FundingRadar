# tests/test_market_search.py
import pytest
import asyncio
import time
from unittest.mock import MagicMock
from core.market import MarketState
from tests.utils.load_fixture import load_fixture
from collectors.bybit import (
    bybit_collect_once,
    xt_collect_once,
    weex_collect_once,
    phemex_collect_once,
    phemex_spot_scales
)

# ------------------- Вспомогательные функции для получения сообщений от коллекторов -------------------

def build_fetch_patch(monkeypatch, data_sequence):
    """
    Подменяет fetch_json в модуле collectors.bybit так, чтобы он последовательно
    возвращал элементы из data_sequence при каждом вызове.
    """
    async def fake_fetch(session, url, proxy=None, timeout=12):
        return data_sequence.pop(0)
    monkeypatch.setattr("collectors.bybit.fetch_json", fake_fetch)
    return fake_fetch

def capture_send_msg(monkeypatch):
    """Перехватывает вызовы send_msg и возвращает список сообщений."""
    messages = []
    def _send(msg):
        messages.append(msg)
    monkeypatch.setattr("collectors.bybit.send_msg", _send)
    return messages

async def get_exchange_message(exchange_name, monkeypatch, fixture_files):
    """
    Запускает коллектор для указанной биржи с подменой fetch_json и возвращает
    отправленное сообщение.
    """
    # Загружаем фикстуры в правильном порядке
    fixtures = [load_fixture(f) for f in fixture_files]
    build_fetch_patch(monkeypatch, fixtures)
    msgs = capture_send_msg(monkeypatch)

    # Выбираем функцию коллектора
    collectors = {
        'Bybit': bybit_collect_once,
        'XT': xt_collect_once,
        'WEEX': weex_collect_once,
        'Phemex': phemex_collect_once,
    }
    collector = collectors.get(exchange_name)
    if not collector:
        raise ValueError(f"Unknown exchange: {exchange_name}")

    # Для Phemex сбрасываем глобальный словарь масштабов
    if exchange_name == 'Phemex':
        global phemex_spot_scales
        phemex_spot_scales = {}

    # Запускаем коллектор (один проход)
    mock_session = MagicMock()
    await collector(mock_session)
    # Должно быть ровно одно сообщение
    assert len(msgs) == 1, f"Expected 1 message, got {len(msgs)}"
    return msgs[0]

# ------------------- Фикстура: сообщения от 4 бирж -------------------

@pytest.fixture
async def exchange_messages(monkeypatch):
    """
    Возвращает список сообщений от бирж Bybit, XT, WEEX, Phemex.
    """
    # Конфигурация для каждой биржи: имя и список файлов фикстур в порядке запросов
    configs = [
        ('Bybit', ['bybit/futures.json', 'bybit/spot.json']),
        ('XT', ['xt/futures.json', 'xt/spot.json']),
        ('WEEX', [
            'weex/futures_ticker.json',
            'weex/funding.json',
            'weex/book.json',
            'weex/spot_book.json',
            'weex/spot_24hr.json'
        ]),
        ('Phemex', [
            'phemex/products.json',
            'phemex/futures_ticker.json',
            'phemex/spot_ticker.json',
            'phemex/funding.json'
        ]),
    ]

    messages = []
    for name, files in configs:
        msg = await get_exchange_message(name, monkeypatch, files)
        messages.append(msg)
    return messages

# ------------------- Тесты -------------------

def test_search_output_count(exchange_messages):
    """
    Применяет данные от 4 бирж к MarketState, выполняет поиск и проверяет,
    что количество записей в data_to_db и data_to_spot соответствует эталону.
    """
    state = MarketState()
    # Применяем все сообщения
    for msg in exchange_messages:
        state.apply_collector_batch(msg)

    # Перестраиваем глобальную таблицу
    state.rebuild_spot_global()

    # Выполняем поиск
    state.search_futures()
    state.search_spot()

    # Проверяем, что есть записи
    with state.lock:
        futures_count = len(state.data_to_db)
        spot_count = len(state.data_to_spot)

    # Эталонные значения (получены при первом прогоне с этими фикстурами)
    # При изменении фикстур эти числа нужно обновить.
    EXPECTED_FUTURES = 2807  # число пар фьючерсных связок
    EXPECTED_SPOT = 1865      # число спот-фьючерсных связок

    assert futures_count == EXPECTED_FUTURES, \
        f"Futures count mismatch: expected {EXPECTED_FUTURES}, got {futures_count}"
    assert spot_count == EXPECTED_SPOT, \
        f"Spot count mismatch: expected {EXPECTED_SPOT}, got {spot_count}"

    # Дополнительно проверяем структуру первых записей (наличие ключевых полей)
    if futures_count > 0:
        sample_fut = state.data_to_db[0][0]  # data_to_db хранит списки [список]
        assert len(sample_fut) >= 22, "Futures record too short"
        assert sample_fut[0]  # symbol
        assert sample_fut[1]  # market1
        assert sample_fut[2]  # market2

    if spot_count > 0:
        sample_spot = state.data_to_spot[0]
        assert len(sample_spot) >= 17, "Spot record too short"
        assert sample_spot[0]  # symbol
        assert sample_spot[1]  # market1 (spot exchange)
        assert sample_spot[2]  # market2 (futures exchange)


def test_search_performance(exchange_messages):
    """
    Измеряет время выполнения search_futures и search_spot после загрузки данных.
    Запускает поиск 5 раз и выводит среднее время.
    """
    state = MarketState()
    for msg in exchange_messages:
        state.apply_collector_batch(msg)
    state.rebuild_spot_global()

    # Прогрев
    state.search_futures()
    state.search_spot()

    # Измерения
    iterations = 5
    fut_times = []
    spot_times = []

    for _ in range(iterations):
        # Измеряем search_futures
        start = time.perf_counter()
        state.search_futures()
        fut_times.append(time.perf_counter() - start)

        # Измеряем search_spot
        start = time.perf_counter()
        state.search_spot()
        spot_times.append(time.perf_counter() - start)

    avg_fut = sum(fut_times) / iterations
    avg_spot = sum(spot_times) / iterations

    # Выводим статистику (pytest покажет в отчёте)
    print(f"\nPerformance stats ({iterations} runs):")
    print(f"  search_futures: avg {avg_fut:.4f}s, min {min(fut_times):.4f}s, max {max(fut_times):.4f}s")
    print(f"  search_spot:    avg {avg_spot:.4f}s, min {min(spot_times):.4f}s, max {max(spot_times):.4f}s")

    # Устанавливаем разумные ограничения (для CI / регрессии)
    # На текущем оборудовании ~1 сек на обе функции, но допустим запас
    assert avg_fut < 0.04, f"search_futures too slow: {avg_fut:.2f}s"
    assert avg_spot < 0.03, f"search_spot too slow: {avg_spot:.2f}s"


def test_determinism(exchange_messages):
    """
    Проверяет, что при повторном применении одних и тех же данных количество
    записей не меняется (детерминизм).
    """
    state1 = MarketState()
    for msg in exchange_messages:
        state1.apply_collector_batch(msg)
    state1.rebuild_spot_global()
    state1.search_futures()
    state1.search_spot()
    with state1.lock:
        count1_fut = len(state1.data_to_db)
        count1_spot = len(state1.data_to_spot)

    # Создаём второй экземпляр и повторяем
    state2 = MarketState()
    for msg in exchange_messages:
        state2.apply_collector_batch(msg)
    state2.rebuild_spot_global()
    state2.search_futures()
    state2.search_spot()
    with state2.lock:
        count2_fut = len(state2.data_to_db)
        count2_spot = len(state2.data_to_spot)

    assert count1_fut == count2_fut, "Futures counts differ between runs"
    assert count1_spot == count2_spot, "Spot counts differ between runs"