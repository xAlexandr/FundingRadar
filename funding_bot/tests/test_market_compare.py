# tests/test_market_compare.py
import pytest
import time
from unittest.mock import MagicMock
from tests.utils.load_fixture import load_fixture
from core.market_old import MarketState as OldMarketState
from core.market import MarketState

from collectors.bybit import (
    bybit_collect_once,
    xt_collect_once,
    weex_collect_once,
    phemex_collect_once,
    phemex_spot_scales,
)


# ------------------- Вспомогательные функции -------------------
def build_fetch_patch(monkeypatch, data_sequence):
    """Подменяет fetch_json в collectors.bybit на последовательный возврат фикстур."""
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
    """Запускает коллектор с фикстурами и возвращает отправленное сообщение."""
    fixtures = [load_fixture(f) for f in fixture_files]
    build_fetch_patch(monkeypatch, fixtures)
    msgs = capture_send_msg(monkeypatch)

    collectors = {
        'Bybit': bybit_collect_once,
        'XT': xt_collect_once,
        'WEEX': weex_collect_once,
        'Phemex': phemex_collect_once,
    }
    collector = collectors.get(exchange_name)
    if not collector:
        raise ValueError(f"Unknown exchange: {exchange_name}")

    if exchange_name == 'Phemex':
        import collectors.bybit as bybit_collectors
        bybit_collectors.phemex_spot_scales = {}

    mock_session = MagicMock()
    await collector(mock_session)
    assert len(msgs) == 1, f"Expected 1 message, got {len(msgs)}"
    return msgs[0]


# ------------------- Фикстура -------------------
@pytest.fixture
async def exchange_messages(monkeypatch):
    """Сообщения от 4 бирж."""
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


# ------------------- Инструменты сравнения -------------------
def _normalize_record(record):
    """
    Приводит запись к кортежу, чтобы сравнивать вне зависимости от изменяемых типов.
    Все элементы приводятся к строкам — это безопасно, т.к. оба движка используют
    одни и те же исходные данные и должны выдавать идентичные строковые представления.
    """
    return tuple(str(item) for item in record)


def compare_bundles(name, old_records, new_records):
    """
    Сравнивает два списка связок, выводит сводку и детали расхождений.
    `old_records` и `new_records` — списки записей (для futures каждая запись — список полей,
    для spot — просто список полей).
    Возвращает True, если наборы полностью совпадают.
    """
    # futures хранится как [[record], ...] — вытащим record
    if old_records and isinstance(old_records[0], list) and len(old_records[0]) == 1:
        old_clean = [r[0] for r in old_records]
    else:
        old_clean = old_records

    if new_records and isinstance(new_records[0], list) and len(new_records[0]) == 1:
        new_clean = [r[0] for r in new_records]
    else:
        new_clean = new_records

    # Множества нормализованных кортежей
    old_set = {_normalize_record(r) for r in old_clean}
    new_set = {_normalize_record(r) for r in new_clean}

    print(f"\n=== Сравнение {name} ===")
    print(f"Старый код: {len(old_clean)} записей")
    print(f"Новый код:  {len(new_clean)} записей")
    print(f"Общих записей: {len(old_set & new_set)}")
    only_old = old_set - new_set
    only_new = new_set - old_set
    if only_old:
        print(f"Только в старом: {len(only_old)}")
    if only_new:
        print(f"Только в новом:  {len(only_new)}")

    # Если есть уникальные записи — выведем несколько для диагностики
    if only_old:
        print("Примеры записей только в старом коде (первые 3):")
        for i, rec in enumerate(list(only_old)[:3]):
            print(f"  {i+1}: {rec}")
    if only_new:
        print("Примеры записей только в новом коде (первые 3):")
        for i, rec in enumerate(list(only_new)[:3]):
            print(f"  {i+1}: {rec}")

    # Если общее количество совпадает, но множества не равны — ищем отличия по ключу (symbol, m1, m2)
    if len(old_clean) == len(new_clean) and old_set != new_set:
        # Строим словари по ключу (первые три поля)
        old_dict = {(_normalize_record(r)[0], _normalize_record(r)[1], _normalize_record(r)[2]): r
                    for r in old_clean}
        new_dict = {(_normalize_record(r)[0], _normalize_record(r)[1], _normalize_record(r)[2]): r
                    for r in new_clean}
        common_keys = set(old_dict.keys()) & set(new_dict.keys())
        differing = []
        for k in common_keys:
            if _normalize_record(old_dict[k]) != _normalize_record(new_dict[k]):
                differing.append(k)
        if differing:
            print(f"Записей с одинаковыми (symbol, market1, market2), но разными полями: {len(differing)}")
            for k in differing[:3]:
                print(f"  {k}:")
                print(f"    old: {_normalize_record(old_dict[k])}")
                print(f"    new: {_normalize_record(new_dict[k])}")

    return old_set == new_set


# ------------------- Тесты сравнения -------------------
def test_old_vs_new_bundles(exchange_messages):
    """
    Полное сравнение наборов связок старого и нового кода.
    """
    # 1. Старая версия
    old_state = OldMarketState()
    for msg in exchange_messages:
        old_state.apply_collector_batch(msg)
    old_state.rebuild_spot_global()
    old_state.search_futures()
    old_state.search_spot()

    # 2. Новая версия (numpy)
    new_state = MarketState()
    for msg in exchange_messages:
        new_state.apply_collector_batch(msg)
    new_state.rebuild_spot_global()
    new_state.search_futures()
    new_state.search_spot()

    with old_state.lock, new_state.lock:
        old_fut = list(old_state.data_to_db)
        old_spot = list(old_state.data_to_spot)
        new_fut = list(new_state.data_to_db)
        new_spot = list(new_state.data_to_spot)

    # Сравниваем фьючерсные связки
    fut_ok = compare_bundles("Futures bundles", old_fut, new_fut)
    # Сравниваем спотовые связки
    spot_ok = compare_bundles("Spot bundles", old_spot, new_spot)

    assert fut_ok, "Futures bundles mismatch between old and new code (see details above)"
    assert spot_ok, "Spot bundles mismatch between old and new code (see details above)"


def test_performance_comparison(exchange_messages):
    """
    Сравнивает время выполнения и выводит ускорение.
    """
    old_state = OldMarketState()
    new_state = MarketState()
    for msg in exchange_messages:
        old_state.apply_collector_batch(msg)
        new_state.apply_collector_batch(msg)
    old_state.rebuild_spot_global()
    new_state.rebuild_spot_global()

    # Прогрев
    old_state.search_futures()
    old_state.search_spot()
    new_state.search_futures()
    new_state.search_spot()

    ITERATIONS = 5
    timings = {
        'old_fut': [], 'new_fut': [],
        'old_spot': [], 'new_spot': [],
    }

    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        old_state.search_futures()
        timings['old_fut'].append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        new_state.search_futures()
        timings['new_fut'].append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        old_state.search_spot()
        timings['old_spot'].append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        new_state.search_spot()
        timings['new_spot'].append(time.perf_counter() - t0)

    def stats(arr):
        return sum(arr)/len(arr), min(arr), max(arr)

    old_fut_avg, old_fut_min, old_fut_max = stats(timings['old_fut'])
    new_fut_avg, new_fut_min, new_fut_max = stats(timings['new_fut'])
    old_spot_avg, old_spot_min, old_spot_max = stats(timings['old_spot'])
    new_spot_avg, new_spot_min, new_spot_max = stats(timings['new_spot'])

    print("\n=== Performance Summary ===")
    print(f"Futures search: old avg={old_fut_avg:.5f}s, new avg={new_fut_avg:.5f}s "
          f"({(old_fut_avg/new_fut_avg - 1)*100:+.1f}% speedup)")
    print(f"Spot search:    old avg={old_spot_avg:.5f}s, new avg={new_spot_avg:.5f}s "
          f"({(old_spot_avg/new_spot_avg - 1)*100:+.1f}% speedup)")

    # Убедимся, что новый не медленнее старого (10% запас)
    assert new_fut_avg <= old_fut_avg * 1.1, \
        f"Futures search regressed: {new_fut_avg:.4f}s vs {old_fut_avg:.4f}s"
    assert new_spot_avg <= old_spot_avg * 1.1, \
        f"Spot search regressed: {new_spot_avg:.4f}s vs {old_spot_avg:.4f}s"