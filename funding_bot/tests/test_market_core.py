"""Tests for MarketState core behavior — data ingestion, freshness, blacklists, metadata.

Covers:
- apply_collector_batch: futures + spot + DEX data ingestion
- Blacklist handling in search
- Freshness checks
- Metadata getter methods
- _build_fut_record / _build_spot_record
- _to_compatible_number
"""
import pytest
import time
import numpy as np
from core.market import MarketState


@pytest.fixture
def ms():
    return MarketState()


# ============================================================================
# _to_compatible_number
# ============================================================================

class TestToCompatibleNumber:
    def test_zero_becomes_int(self):
        assert MarketState._to_compatible_number(0.0) == 0
        assert isinstance(MarketState._to_compatible_number(0.0), int)

    def test_nonzero_stays_float(self):
        assert MarketState._to_compatible_number(1.5) == 1.5
        assert isinstance(MarketState._to_compatible_number(1.5), float)

    def test_integer_input(self):
        assert MarketState._to_compatible_number(5) == 5


# ============================================================================
# _norm_sym
# ============================================================================

class TestNormSym:
    def test_with_underscore(self, ms):
        assert ms._norm_sym("BTC_USDT") == "BTCUSDT"

    def test_with_hyphen(self, ms):
        assert ms._norm_sym("btc-usdt") == "BTCUSDT"

    def test_already_normalized(self, ms):
        assert ms._norm_sym("BTCUSDT") == "BTCUSDT"

    def test_lowercase(self, ms):
        assert ms._norm_sym("ethusdt") == "ETHUSDT"

    def test_non_string_passthrough(self, ms):
        assert ms._norm_sym(42) == 42
        assert ms._norm_sym(None) is None


# ============================================================================
# _dex_base
# ============================================================================

class TestDexBase:
    def test_with_underscore(self, ms):
        assert ms._dex_base("ETH_TONUSDT") == "TONUSDT"

    def test_without_underscore(self, ms):
        assert ms._dex_base("BTCUSDT") == "BTCUSDT"

    def test_non_string(self, ms):
        assert ms._dex_base(123) == 123
        assert ms._dex_base(None) is None


# ============================================================================
# apply_collector_batch — Futures
# ============================================================================

class TestApplyCollectorBatchFutures:
    def test_basic_futures_data(self, ms):
        msg = {
            'market': 'Bybit',
            'ts': time.time(),
            'data_usdt': [
                ['BTCUSDT', 0.01, 50000.0, 0, 50100.0, 0, 50200.0, 0],
                ['ETHUSDT', 0.005, 3000.0, 0, 3010.0, 0, 3020.0, 0],
            ],
            'data_spot': {},
            'market_meta': {
                'BTCUSDT': {'fundingInterval': 8, 'amount24': 1000000, 'limits_usdt': 50000},
            },
        }
        ms.apply_collector_batch(msg)

        assert 'BTCUSDT' in ms.data_usdt
        assert 'ETHUSDT' in ms.data_usdt
        assert ms.dirty is True
        assert 'Bybit' in ms.dirty_markets

    def test_futures_updates_numpy_arrays(self, ms):
        msg = {
            'market': 'Bybit',
            'ts': time.time(),
            'data_usdt': [
                ['BTCUSDT', 0.01, 50000.0, 0, 50100.0, 0, 50200.0, 0],
            ],
            'data_spot': {},
            'market_meta': {},
        }
        ms.apply_collector_batch(msg)

        idx = ms.sym_to_idx_fut.get('BTCUSDT')
        assert idx is not None
        bybit_idx = ms.market_to_idx['Bybit']
        assert ms.fut_funding[idx, bybit_idx] == pytest.approx(0.01)
        assert ms.fut_bid[idx, bybit_idx] == pytest.approx(50000.0)
        assert ms.fut_ask[idx, bybit_idx] == pytest.approx(50200.0)

    def test_empty_data_usdt(self, ms):
        msg = {
            'market': 'Bybit',
            'ts': time.time(),
            'data_usdt': [],
            'data_spot': {},
            'market_meta': {},
        }
        ms.apply_collector_batch(msg)
        assert len(ms.data_usdt) == 0

    def test_missing_market_field(self, ms):
        msg = {'ts': time.time(), 'data_usdt': [], 'data_spot': {}, 'market_meta': {}}
        ms.apply_collector_batch(msg)
        # Should not crash, just return early
        assert ms.dirty is False

    def test_bids_asks_stored(self, ms):
        ts = time.time()
        msg = {
            'market': 'Bybit',
            'ts': ts,
            'data_usdt': [
                ['BTCUSDT', 0.01, 50000.0, 0, 50100.0, 0, 50200.0, 0],
            ],
            'data_spot': {},
            'market_meta': {},
        }
        ms.apply_collector_batch(msg)
        assert 'BTCUSDT' in ms.bids_asks_futures_all['Bybit']
        stored = ms.bids_asks_futures_all['Bybit']['BTCUSDT']
        assert stored[0][0] == 50200.0  # ask
        assert stored[0][1] == 50000.0  # bid

    def test_meta_updates(self, ms):
        msg = {
            'market': 'Bybit',
            'ts': time.time(),
            'data_usdt': [['BTCUSDT', 0.01, 50000.0, 0, 50100.0, 0, 50200.0, 0]],
            'data_spot': {},
            'market_meta': {
                'BTCUSDT': {'fundingInterval': 4, 'amount24': 500000},
            },
        }
        ms.apply_collector_batch(msg)
        meta = ms.extra_meta_per_market['Bybit']['BTCUSDT']
        assert meta['fundingInterval'] == 4
        assert meta['amount24'] == 500000

        idx = ms.sym_to_idx_fut['BTCUSDT']
        bybit_idx = ms.market_to_idx['Bybit']
        assert ms.fut_interval[idx, bybit_idx] == 4
        assert ms.fut_amount24[idx, bybit_idx] == 500000


# ============================================================================
# apply_collector_batch — Spot
# ============================================================================

class TestApplyCollectorBatchSpot:
    def test_spot_data_stored(self, ms):
        msg = {
            'market': 'Bybit',
            'ts': time.time(),
            'data_usdt': [],
            'data_spot': {
                'BTCUSDT': ['BTCUSDT', 50000.0, 50010.0],
            },
            'market_meta': {},
        }
        ms.apply_collector_batch(msg)
        assert 'BTCUSDT' in ms.data_spot_usdt
        assert ms.data_spot_usdt['BTCUSDT'] == ['BTCUSDT', 50000.0, 50010.0]
        assert ms.data_spot_source['BTCUSDT'] == 'Bybit'

    def test_spot_bids_asks(self, ms):
        msg = {
            'market': 'Bybit',
            'ts': time.time(),
            'data_usdt': [],
            'data_spot': {
                'ETHUSDT': ['ETHUSDT', 3000.0, 3005.0],
            },
            'market_meta': {},
        }
        ms.apply_collector_batch(msg)
        assert 'ETHUSDT' in ms.bids_asks_spot_all['Bybit']
        stored = ms.bids_asks_spot_all['Bybit']['ETHUSDT']
        assert stored[0][0] == 3005.0  # ask
        assert stored[0][1] == 3000.0  # bid

    def test_spot_normalization(self, ms):
        msg = {
            'market': 'Bybit',
            'ts': time.time(),
            'data_usdt': [],
            'data_spot': {
                'btc_usdt': ['btc_usdt', 50000.0, 50010.0],
            },
            'market_meta': {},
        }
        ms.apply_collector_batch(msg)
        assert 'BTCUSDT' in ms.data_spot_usdt


# ============================================================================
# apply_collector_batch — DEX
# ============================================================================

class TestApplyCollectorBatchDex:
    def test_dex_data_stored(self, ms):
        msg = {
            'market': 'Dex',
            'ts': time.time(),
            'data_spot': {
                'ETH_TONUSDT': ['ETH_TONUSDT', 5.0, 5.0],
            },
            'market_meta': {
                'ETH_TONUSDT': {'priceUsd': 5.0, 'contract': '0xabc'},
            },
        }
        ms.apply_collector_batch(msg)
        assert 'ETH_TONUSDT' in ms.dex_data
        assert ms.dex_data['ETH_TONUSDT'] == 5.0
        assert ms.dex_changed == {'ETH_TONUSDT'}

    def test_dex_meta_updated(self, ms):
        msg = {
            'market': 'Dex',
            'ts': time.time(),
            'data_spot': {
                'SOLUSDT': ['SOLUSDT', 150.0, 150.0],
            },
            'market_meta': {
                'SOLUSDT': {'priceUsd': 150.0, 'chain': 'solana'},
            },
        }
        ms.apply_collector_batch(msg)
        assert 'SOLUSDT' in ms.dex_meta
        assert ms.dex_meta['SOLUSDT']['chain'] == 'solana'

    def test_dex_skips_zero_price(self, ms):
        msg = {
            'market': 'Dex',
            'ts': time.time(),
            'data_spot': {
                'BADUSDT': ['BADUSDT', 0.0, 0.0],
            },
            'market_meta': {
                'BADUSDT': {'priceUsd': 0},
            },
        }
        ms.apply_collector_batch(msg)
        assert 'BADUSDT' not in ms.dex_data


# ============================================================================
# _is_fresh
# ============================================================================

class TestIsFresh:
    def test_fresh_data(self, ms):
        key = ('BTCUSDT', 'Bybit')
        ms.last_seen[key] = time.time()
        assert ms._is_fresh('BTCUSDT', 'Bybit') is True

    def test_stale_data(self, ms):
        key = ('BTCUSDT', 'Bybit')
        ms.last_seen[key] = time.time() - 100
        assert ms._is_fresh('BTCUSDT', 'Bybit') is False

    def test_no_data(self, ms):
        assert ms._is_fresh('NONEXISTENT', 'Bybit') is False

    def test_spot_freshness(self, ms):
        key = ('BTCUSDT', 'Bybit_spot')
        ms.last_seen[key] = time.time()
        assert ms._is_fresh('BTCUSDT', 'Bybit', spot=True) is True


# ============================================================================
# Metadata getters
# ============================================================================

class TestMetadataGetters:
    def test_get_funding_interval_default(self, ms):
        assert ms._get_funding_interval('Bybit', 'BTCUSDT') == 8

    def test_get_funding_interval_from_meta(self, ms):
        ms.extra_meta_per_market['Bybit'] = {'BTCUSDT': {'fundingInterval': 4}}
        assert ms._get_funding_interval('Bybit', 'BTCUSDT') == 4

    def test_get_amount24_default(self, ms):
        assert ms._get_amount24('Bybit', 'BTCUSDT') == 0

    def test_get_amount24_from_meta(self, ms):
        ms.extra_meta_per_market['Bybit'] = {'BTCUSDT': {'amount24': 1000000}}
        assert ms._get_amount24('Bybit', 'BTCUSDT') == 1000000

    def test_get_amount24_spot_default(self, ms):
        assert ms._get_amount24_spot('Bybit', 'BTCUSDT') == 0

    def test_get_amount24_spot_from_meta(self, ms):
        ms.extra_meta_per_market['Bybit'] = {'BTCUSDT': {'amount24_spot': 500000}}
        assert ms._get_amount24_spot('Bybit', 'BTCUSDT') == 500000

    def test_get_limits_usdt_default(self, ms):
        assert ms._get_limits_usdt('Bybit', 'BTCUSDT') == 0

    def test_get_limits_usdt_from_meta(self, ms):
        ms.extra_meta_per_market['Bybit'] = {'BTCUSDT': {'limits_usdt': 50000}}
        assert ms._get_limits_usdt('Bybit', 'BTCUSDT') == 50000

    def test_getters_handle_non_dict_meta(self, ms):
        ms.extra_meta_per_market['Bybit'] = {'BTCUSDT': "not a dict"}
        assert ms._get_funding_interval('Bybit', 'BTCUSDT') == 8
        assert ms._get_amount24('Bybit', 'BTCUSDT') == 0


# ============================================================================
# _build_fut_record / _build_spot_record
# ============================================================================

class TestBuildRecords:
    def test_build_fut_record(self, ms):
        rec = ms._build_fut_record(
            'BTCUSDT', 'Bybit', 'Bitget', 0.01, 0.005, 8, 8,
            50000.0, 50100.0, 0.1, 0.1, 50050.0, 50060.0,
            50200.0, 50300.0, 1000000, 800000, 50000, 40000
        )
        assert rec[0] == 'BTCUSDT'
        assert rec[1] == 'Bybit'
        assert rec[2] == 'Bitget'
        assert rec[3] == '0.01'
        assert rec[4] == '0.005'
        assert len(rec) == 22

    def test_build_spot_record(self, ms):
        rec = ms._build_spot_record(
            'BTCUSDT', 'Bybit', 'Bitget', 0.01, 8, 50000.0,
            0.1, 0.1, '-', 50050.0, 49900.0,
            50200.0, 49950.0, 1000000, 50000, 200000
        )
        assert rec[0] == 'BTCUSDT'
        assert rec[1] == 'Bybit'
        assert rec[2] == 'Bitget'
        assert rec[3] == '0.01'
        assert len(rec) == 17


# ============================================================================
# Blacklist
# ============================================================================

class TestBlacklist:
    def test_blacklist_futures_structure(self, ms):
        assert isinstance(ms.blacklist_futures, set)
        for sym, markets in ms.blacklist_futures:
            assert isinstance(sym, str)
            assert isinstance(markets, frozenset)

    def test_blacklist_spot_structure(self, ms):
        assert isinstance(ms.blacklist_spot, set)
        for sym, markets in ms.blacklist_spot:
            assert isinstance(sym, str)
            assert isinstance(markets, frozenset)

    def test_blacklist_fut_set_has_indices(self, ms):
        """blacklist_fut_set should contain (symbol, i, j) tuples."""
        assert isinstance(ms.blacklist_fut_set, set)
        for item in ms.blacklist_fut_set:
            assert len(item) == 3
            sym, i, j = item
            assert isinstance(sym, str)
            assert isinstance(i, int)
            assert isinstance(j, int)

    def test_blacklist_affects_search(self, ms):
        """A blacklisted symbol should not appear in search results."""
        # Add data for a blacklisted symbol from both Bybit and Bitget
        ts = time.time()
        # Find a blacklisted pair
        for sym, froz in ms.blacklist_futures:
            items = tuple(froz)
            if len(items) == 2 and items[0] == 'Bybit' and items[1] == 'Bitget':
                # Add futures data for this symbol
                msg_bybit = {
                    'market': 'Bybit', 'ts': ts,
                    'data_usdt': [[sym, 0.01, 50000.0, 0, 50100.0, 0, 50200.0, 0]],
                    'data_spot': {}, 'market_meta': {},
                }
                msg_bitget = {
                    'market': 'Bitget', 'ts': ts,
                    'data_usdt': [[sym, 0.005, 50100.0, 0, 50150.0, 0, 50250.0, 0]],
                    'data_spot': {}, 'market_meta': {},
                }
                ms.apply_collector_batch(msg_bybit)
                ms.apply_collector_batch(msg_bitget)
                ms.search_futures()

                # Check that the blacklisted symbol is NOT in results
                found = False
                for rec in ms.data_to_db:
                    if rec[0][0] == sym and set([rec[0][1], rec[0][2]]) == {'Bybit', 'Bitget'}:
                        found = True
                        break
                assert not found, f"Blacklisted symbol {sym} Bybit/Bitget should not be in results"
                return

    def test_fees_all_markets(self, ms):
        for m in ms.markets:
            assert m in ms.fees
            assert m in ms.fees_fut
            assert isinstance(ms.fees[m], (int, float))
            assert isinstance(ms.fees_fut[m], (int, float))


# ============================================================================
# search_futures — basic behavior
# ============================================================================

class TestSearchFutures:
    def test_empty_state(self, ms):
        ms.search_futures()
        assert len(ms.data_to_db) == 0

    def test_single_pair_finds_spread(self, ms):
        ts = time.time()
        msg1 = {
            'market': 'Bybit', 'ts': ts,
            'data_usdt': [['BTCUSDT', 0.01, 50000.0, 0, 50100.0, 0, 50200.0, 0]],
            'data_spot': {}, 'market_meta': {},
        }
        msg2 = {
            'market': 'Bitget', 'ts': ts,
            'data_usdt': [['BTCUSDT', 0.005, 50100.0, 0, 50150.0, 0, 50300.0, 0]],
            'data_spot': {}, 'market_meta': {},
        }
        ms.apply_collector_batch(msg1)
        ms.apply_collector_batch(msg2)
        ms.search_futures()

        assert len(ms.data_to_db) >= 1
        # Find BTCUSDT pair
        found = [r for r in ms.data_to_db if r[0][0] == 'BTCUSDT']
        assert len(found) >= 1

    def test_result_format(self, ms):
        ts = time.time()
        msg1 = {
            'market': 'Bybit', 'ts': ts,
            'data_usdt': [['BTCUSDT', 0.01, 50000.0, 0, 50100.0, 0, 50200.0, 0]],
            'data_spot': {}, 'market_meta': {},
        }
        msg2 = {
            'market': 'Bitget', 'ts': ts,
            'data_usdt': [['BTCUSDT', 0.005, 50100.0, 0, 50150.0, 0, 50300.0, 0]],
            'data_spot': {}, 'market_meta': {},
        }
        ms.apply_collector_batch(msg1)
        ms.apply_collector_batch(msg2)
        ms.search_futures()

        rec = ms.data_to_db[0][0]
        assert len(rec) == 22
        assert rec[0] == 'BTCUSDT'
        assert rec[1] in ms.markets  # market1
        assert rec[2] in ms.markets  # market2

    def test_higher_funding_is_market1(self, ms):
        """Market with higher funding should be market1."""
        ts = time.time()
        msg1 = {
            'market': 'Bybit', 'ts': ts,
            'data_usdt': [['BTCUSDT', 0.05, 50000.0, 0, 50100.0, 0, 50200.0, 0]],
            'data_spot': {}, 'market_meta': {},
        }
        msg2 = {
            'market': 'Bitget', 'ts': ts,
            'data_usdt': [['BTCUSDT', 0.01, 50100.0, 0, 50150.0, 0, 50300.0, 0]],
            'data_spot': {}, 'market_meta': {},
        }
        ms.apply_collector_batch(msg1)
        ms.apply_collector_batch(msg2)
        ms.search_futures()

        rec = ms.data_to_db[0][0]
        # Bybit has 0.05, Bitget has 0.01 -> Bybit should be market1
        assert rec[1] == 'Bybit'
        assert rec[2] == 'Bitget'
        assert float(rec[3]) == 0.05
        assert float(rec[4]) == 0.01


# ============================================================================
# _ensure_capacity
# ============================================================================

class TestEnsureCapacity:
    def test_grows_arrays(self, ms):
        old_cap = ms._capacity
        ms._ensure_capacity(old_cap + 100)
        assert ms._capacity >= old_cap + 100

    def test_no_op_if_enough(self, ms):
        ms._ensure_capacity(ms._capacity)
        cap = ms._capacity
        ms._ensure_capacity(cap)
        assert ms._capacity == cap

    def test_add_fut_symbol_grows(self, ms):
        for i in range(2000):
            ms._add_fut_symbol(f"SYM{i}USDT")
        assert ms._num_fut == 2000
        assert ms._capacity >= 2000


# ============================================================================
# _add_global_symbol
# ============================================================================

class TestAddGlobalSymbol:
    def test_add_new(self, ms):
        idx = ms._add_global_symbol("BTCUSDT")
        assert idx == 0
        assert ms._num_glob == 1

    def test_add_existing(self, ms):
        idx1 = ms._add_global_symbol("BTCUSDT")
        idx2 = ms._add_global_symbol("BTCUSDT")
        assert idx1 == idx2
        assert ms._num_glob == 1
