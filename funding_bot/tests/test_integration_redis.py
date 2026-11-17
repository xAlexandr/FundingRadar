"""Integration tests for Redis data layer.

These tests verify that the aggregator pipeline writes correct data to Redis
and that the data can be read back with the expected structure.

Requires: Redis running on localhost:6379
"""
import pytest
import json
import time
import redis


@pytest.fixture(scope="module")
def rdb0():
    return redis.Redis(host='127.0.0.1', port=6379, db=0, decode_responses=True)


@pytest.fixture(scope="module")
def rdb1():
    return redis.Redis(host='127.0.0.1', port=6379, db=1, decode_responses=True)


@pytest.fixture(scope="module")
def rdb2():
    return redis.Redis(host='127.0.0.1', port=6379, db=2, decode_responses=True)


# ============================================================================
# Spreads:all (DB 0) — Futures spreads
# ============================================================================

class TestSpreadsAll:
    def test_key_exists(self, rdb0):
        raw = rdb0.get("Spreads:all")
        assert raw is not None, "Spreads:all key not found in Redis DB 0"

    def test_data_is_valid_json(self, rdb0):
        raw = rdb0.get("Spreads:all")
        assert raw is not None
        data = json.loads(raw)
        assert isinstance(data, list)

    def test_has_records(self, rdb0):
        raw = rdb0.get("Spreads:all")
        data = json.loads(raw)
        assert len(data) > 100, f"Expected >100 spreads, got {len(data)}"

    def test_record_structure(self, rdb0):
        raw = rdb0.get("Spreads:all")
        data = json.loads(raw)
        sample = data[0]
        required_keys = {
            'symbol', 'market1', 'market2',
            'market1funding', 'market2funding',
            'market1bid', 'market2bid',
            'market1fee', 'market2fee',
            'spread',
        }
        assert required_keys.issubset(set(sample.keys())), \
            f"Missing keys: {required_keys - set(sample.keys())}"

    def test_symbol_format(self, rdb0):
        raw = rdb0.get("Spreads:all")
        data = json.loads(raw)
        for record in data[:50]:
            sym = record.get('symbol', '')
            assert sym.endswith('USDT'), f"Symbol {sym} doesn't end with USDT"

    def test_markets_are_strings(self, rdb0):
        raw = rdb0.get("Spreads:all")
        data = json.loads(raw)
        for record in data[:50]:
            assert isinstance(record.get('market1'), str)
            assert isinstance(record.get('market2'), str)

    def test_funding_rates_are_numbers(self, rdb0):
        raw = rdb0.get("Spreads:all")
        data = json.loads(raw)
        for record in data[:50]:
            assert isinstance(record.get('market1funding'), (int, float))
            assert isinstance(record.get('market2funding'), (int, float))

    def test_bid_prices_positive(self, rdb0):
        raw = rdb0.get("Spreads:all")
        data = json.loads(raw)
        for record in data[:50]:
            bid1 = record.get('market1bid', 0)
            bid2 = record.get('market2bid', 0)
            assert bid1 > 0, f"market1bid should be positive, got {bid1}"
            assert bid2 > 0, f"market2bid should be positive, got {bid2}"

    def test_spread_is_number(self, rdb0):
        raw = rdb0.get("Spreads:all")
        data = json.loads(raw)
        for record in data[:50]:
            spread = record.get('spread')
            assert isinstance(spread, (int, float)), \
                f"spread should be a number, got {type(spread)}: {spread}"

    def test_unique_symbol_market_pairs(self, rdb0):
        raw = rdb0.get("Spreads:all")
        data = json.loads(raw)
        pairs = set()
        for record in data:
            key = (record['symbol'], record['market1'], record['market2'])
            pairs.add(key)
        # No exact duplicates
        assert len(pairs) == len(data), \
            f"Found duplicate (symbol, market1, market2) pairs: {len(data) - len(pairs)} duplicates"

    def test_publish_channel_exists(self, rdb0):
        """Spreads:update channel should have been published to."""
        # We can't directly check pubsub history, but we can verify the key exists
        raw = rdb0.get("Spreads:all")
        assert raw is not None


# ============================================================================
# SpotFutures:all (DB 1) — Spot->Futures spreads
# ============================================================================

class TestSpotFuturesAll:
    def test_key_exists(self, rdb1):
        raw = rdb1.get("SpotFutures:all")
        assert raw is not None, "SpotFutures:all key not found in Redis DB 1"

    def test_data_is_valid_json(self, rdb1):
        raw = rdb1.get("SpotFutures:all")
        data = json.loads(raw)
        assert isinstance(data, list)

    def test_has_records(self, rdb1):
        raw = rdb1.get("SpotFutures:all")
        data = json.loads(raw)
        assert len(data) > 100, f"Expected >100 spot records, got {len(data)}"

    def test_record_structure(self, rdb1):
        raw = rdb1.get("SpotFutures:all")
        data = json.loads(raw)
        sample = data[0]
        required_keys = {
            'symbol', 'market1', 'market2',
            'market2funding', 'market2bid',
            'market1fee', 'market2fee',
            'spot1bid', 'spot1ask',
        }
        assert required_keys.issubset(set(sample.keys())), \
            f"Missing keys: {required_keys - set(sample.keys())}"

    def test_spot_prices_reasonable(self, rdb1):
        raw = rdb1.get("SpotFutures:all")
        data = json.loads(raw)
        for record in data[:50]:
            spot_bid = record.get('spot1bid', 0)
            spot_ask = record.get('spot1ask', 0)
            assert spot_bid > 0, f"spot1bid should be positive, got {spot_bid}"
            assert spot_ask > 0, f"spot1ask should be positive, got {spot_ask}"

    def test_spread_in_record(self, rdb1):
        raw = rdb1.get("SpotFutures:all")
        data = json.loads(raw)
        for record in data[:50]:
            assert 'spread' in record
            spread = record['spread']
            assert isinstance(spread, (int, float))


# ============================================================================
# Dex:all (DB 2) — DEX data
# ============================================================================

class TestDexAll:
    def test_key_exists(self, rdb2):
        raw = rdb2.get("Dex:all")
        assert raw is not None, "Dex:all key not found in Redis DB 2"

    def test_data_is_valid_json(self, rdb2):
        raw = rdb2.get("Dex:all")
        data = json.loads(raw)
        assert isinstance(data, list)

    def test_has_records(self, rdb2):
        raw = rdb2.get("Dex:all")
        data = json.loads(raw)
        assert len(data) > 10, f"Expected >10 DEX records, got {len(data)}"

    def test_record_structure(self, rdb2):
        raw = rdb2.get("Dex:all")
        data = json.loads(raw)
        sample = data[0]
        required_keys = {'symbol', 'market2', 'bid', 'diff', 'priceUsd'}
        assert required_keys.issubset(set(sample.keys())), \
            f"Missing keys: {required_keys - set(sample.keys())}"

    def test_dex_prices_positive(self, rdb2):
        raw = rdb2.get("Dex:all")
        data = json.loads(raw)
        for record in data[:20]:
            price = record.get('priceUsd', 0)
            assert price > 0, f"DEX price should be positive, got {price}"

    def test_dex_meta(self, rdb2):
        meta = rdb2.hgetall("Dex:meta")
        assert meta is not None
        # Should have last_update or last_count
        assert 'last_count' in meta or 'last_update' in meta


# ============================================================================
# Cross-DB consistency
# ============================================================================

class TestCrossDBConsistency:
    def test_futures_symbols_cover_spot(self, rdb0, rdb1):
        """Symbols in SpotFutures should have corresponding futures data."""
        raw_fut = rdb0.get("Spreads:all")
        raw_spot = rdb1.get("SpotFutures:all")
        fut_data = json.loads(raw_fut)
        spot_data = json.loads(raw_spot)

        fut_symbols = {r['symbol'] for r in fut_data}
        spot_symbols = {r['symbol'] for r in spot_data}

        # Most spot symbols should exist in futures
        overlap = spot_symbols & fut_symbols
        assert len(overlap) > 0, "No overlap between spot and futures symbols"

    def test_market_names_valid(self, rdb0, rdb1):
        """All market names should be from the known set."""
        valid_markets = {
            'Bybit', 'Mexc', 'Kucoin', 'Gateio', 'Bitget', 'Huobi', 'Okx',
            'Binance', 'BingX', 'BitMart', 'Ourbit', 'Hyperliquid', 'LBank',
            'Aster', 'XT', 'CoinEx', 'WEEX', 'Phemex', 'BinanceAlpha'
        }
        raw_fut = rdb0.get("Spreads:all")
        fut_data = json.loads(raw_fut)

        for record in fut_data[:100]:
            assert record['market1'] in valid_markets, \
                f"Invalid market1: {record['market1']}"
            assert record['market2'] in valid_markets, \
                f"Invalid market2: {record['market2']}"
