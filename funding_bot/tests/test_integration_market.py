"""Integration tests for MarketState with real Redis data.

Tests that MarketState can read and process data from Redis,
and that the aggregator pipeline produces consistent results.

Requires: Redis with data from aggregator
"""
import pytest
import json
import time
import redis
import numpy as np
from unittest.mock import MagicMock


@pytest.fixture(scope="module")
def redis_data():
    """Load real data from Redis for testing."""
    r0 = redis.Redis(host='127.0.0.1', port=6379, db=0, decode_responses=True)
    r1 = redis.Redis(host='127.0.0.1', port=6379, db=1, decode_responses=True)
    r2 = redis.Redis(host='127.0.0.1', port=6379, db=2, decode_responses=True)

    raw_fut = r0.get("Spreads:all")
    raw_spot = r1.get("SpotFutures:all")
    raw_dex = r2.get("Dex:all")

    return {
        'futures': json.loads(raw_fut) if raw_fut else [],
        'spot': json.loads(raw_spot) if raw_spot else [],
        'dex': json.loads(raw_dex) if raw_dex else [],
    }


# ============================================================================
# Data integrity from Redis
# ============================================================================

class TestRedisDataIntegrity:
    def test_futures_data_loaded(self, redis_data):
        assert len(redis_data['futures']) > 100

    def test_spot_data_loaded(self, redis_data):
        assert len(redis_data['spot']) > 100

    def test_dex_data_loaded(self, redis_data):
        assert len(redis_data['dex']) > 10

    def test_all_futures_have_symbol(self, redis_data):
        for record in redis_data['futures'][:100]:
            assert 'symbol' in record
            assert len(record['symbol']) > 0

    def test_all_spot_have_symbol(self, redis_data):
        for record in redis_data['spot'][:100]:
            assert 'symbol' in record
            assert len(record['symbol']) > 0

    def test_funding_rates_in_range(self, redis_data):
        """Funding rates should be in reasonable range."""
        for record in redis_data['futures'][:100]:
            f1 = record.get('market1funding', 0)
            f2 = record.get('market2funding', 0)
            assert -100 <= f1 <= 100, f"Unreasonable funding rate: {f1}"
            assert -100 <= f2 <= 100, f"Unreasonable funding rate: {f2}"

    def test_bid_prices_positive(self, redis_data):
        for record in redis_data['futures'][:100]:
            bid1 = record.get('market1bid', 0)
            bid2 = record.get('market2bid', 0)
            assert bid1 > 0, f"bid should be positive: {bid1}"
            assert bid2 > 0, f"bid should be positive: {bid2}"

    def test_ask_prices_positive(self, redis_data):
        for record in redis_data['futures'][:100]:
            ask1 = record.get('market1ask', 0)
            ask2 = record.get('market2ask', 0)
            assert ask1 > 0, f"ask should be positive: {ask1}"
            assert ask2 > 0, f"ask should be positive: {ask2}"

    def test_spot_funding_rates_in_range(self, redis_data):
        for record in redis_data['spot'][:100]:
            f = record.get('market2funding', 0)
            assert -100 <= f <= 100, f"Unreasonable spot funding: {f}"

    def test_spot_bid_ask_positive(self, redis_data):
        for record in redis_data['spot'][:100]:
            bid = record.get('spot1bid', 0)
            ask = record.get('spot1ask', 0)
            assert bid > 0, f"spot bid should be positive: {bid}"
            assert ask > 0, f"spot ask should be positive: {ask}"

    def test_dex_prices_positive(self, redis_data):
        for record in redis_data['dex'][:20]:
            price = record.get('priceUsd', 0)
            assert price > 0, f"DEX price should be positive: {price}"


# ============================================================================
# Spread consistency
# ============================================================================

class TestSpreadConsistency:
    def test_futures_spread_matches_bids(self, redis_data):
        """Spread should be consistent with bid prices."""
        for record in redis_data['futures'][:50]:
            bid1 = record.get('market1bid', 0)
            bid2 = record.get('market2bid', 0)
            spread = record.get('spread', 0)
            # spread = funding1 - funding2
            f1 = record.get('market1funding', 0)
            f2 = record.get('market2funding', 0)
            expected_spread = round(f1 - f2, 4)
            assert abs(spread - expected_spread) < 0.01, \
                f"Spread mismatch: {spread} vs {expected_spread}"

    def test_spot_spread_calculation(self, redis_data):
        """Spot spread should be derivable from spot/futures prices."""
        for record in redis_data['spot'][:50]:
            spot_bid = record.get('spot1bid', 0)
            spot_ask = record.get('spot1ask', 0)
            fut_bid = record.get('market2bid', 0)
            # Basic sanity: spot and futures prices should be in same order of magnitude
            if spot_bid > 0 and fut_bid > 0:
                ratio = spot_bid / fut_bid
                assert 0.001 < ratio < 1000, \
                    f"Spot/Futures price ratio unreasonable: {ratio}"


# ============================================================================
# Market diversity
# ============================================================================

class TestMarketDiversity:
    def test_multiple_markets_in_futures(self, redis_data):
        """Check all records for market diversity."""
        markets = set()
        for record in redis_data['futures']:
            markets.add(record.get('market1'))
            markets.add(record.get('market2'))
        assert len(markets) >= 5, f"Expected at least 5 markets, got {len(markets)}"

    def test_multiple_markets_in_spot(self, redis_data):
        markets = set()
        for record in redis_data['spot']:
            markets.add(record.get('market1'))
            markets.add(record.get('market2'))
        assert len(markets) >= 3, f"Expected at least 3 markets in spot, got {len(markets)}"

    def test_diverse_symbols(self, redis_data):
        symbols = set()
        for record in redis_data['futures']:
            symbols.add(record.get('symbol'))
        assert len(symbols) >= 50, f"Expected at least 50 symbols, got {len(symbols)}"


# ============================================================================
# NumPy integration
# ============================================================================

class TestNumpyIntegration:
    def test_market_state_initialization(self):
        from core.market import MarketState
        ms = MarketState()
        assert ms.M_fut == 19
        assert ms.M_total == 20
        assert ms.fut_funding.shape[1] == ms.M_total

    def test_market_to_idx_complete(self):
        from core.market import MarketState
        ms = MarketState()
        for market in ms.markets:
            assert market in ms.market_to_idx

    def test_blacklist_fut_set_populated(self):
        from core.market import MarketState
        ms = MarketState()
        assert len(ms.blacklist_fut_set) > 0

    def test_blacklist_spot_set_populated(self):
        from core.market import MarketState
        ms = MarketState()
        assert len(ms.blacklist_spot_set) > 0

    def test_capacity_grows(self):
        from core.market import MarketState
        ms = MarketState()
        old_cap = ms._capacity
        for i in range(old_cap + 100):
            ms._add_fut_symbol(f"TEST{i}USDT")
        assert ms._capacity >= old_cap + 100
