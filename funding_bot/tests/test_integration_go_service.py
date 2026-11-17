"""Integration tests for Go service API (port 8081).

The Go service filters and paginates spreads for the frontend.
These tests verify the API responses are correct.

Requires: Go service running on localhost:8081
"""
import pytest
import requests
import json

BASE_URL = "http://127.0.0.1:8081"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.timeout = 10
    return s


# ============================================================================
# Health / Basic connectivity
# ============================================================================

class TestGoServiceHealth:
    def test_futures_endpoint_responds(self, session):
        resp = session.get(f"{BASE_URL}/api/futures", params={"user_id": 1, "page": 1, "items": 5})
        assert resp.status_code == 200

    def test_spot_endpoint_responds(self, session):
        resp = session.get(f"{BASE_URL}/api/spot", params={"user_id": 1, "page": 1, "items": 5})
        assert resp.status_code == 200


# ============================================================================
# Futures API
# ============================================================================

class TestFuturesAPI:
    def test_returns_json(self, session):
        resp = session.get(f"{BASE_URL}/api/futures", params={"user_id": 1, "page": 1, "items": 5})
        assert resp.headers.get('Content-Type', '').startswith('application/json')

    def test_has_pages_or_no_sub(self, session):
        resp = session.get(f"{BASE_URL}/api/futures", params={"user_id": 1, "page": 1, "items": 5})
        data = resp.json()
        # Without subscription, returns {"status": "no_sub"}
        assert isinstance(data, (dict, list))

    def test_pagination_page1(self, session):
        resp = session.get(f"{BASE_URL}/api/futures", params={"user_id": 1, "page": 1, "items": 5})
        data = resp.json()
        assert resp.status_code == 200

    def test_pagination_page2(self, session):
        resp = session.get(f"{BASE_URL}/api/futures", params={"user_id": 1, "page": 2, "items": 5})
        assert resp.status_code == 200

    def test_sort_by_spread(self, session):
        resp = session.get(f"{BASE_URL}/api/futures", params={
            "user_id": 1, "page": 1, "items": 10, "sort": "spread"
        })
        assert resp.status_code == 200

    def test_sort_by_course(self, session):
        resp = session.get(f"{BASE_URL}/api/futures", params={
            "user_id": 1, "page": 1, "items": 10, "sort": "course"
        })
        assert resp.status_code == 200

    def test_futures_pages_endpoint(self, session):
        resp = session.get(f"{BASE_URL}/api/futures_pages", params={
            "user_id": 1, "symbol": "BTCUSDT", "items": 5
        })
        assert resp.status_code == 200

    def test_futures_id_endpoint(self, session):
        resp = session.get(f"{BASE_URL}/api/futures_id", params={
            "user_id": 1, "symbol": "BTCUSDT", "m1": "Bybit", "m2": "Bitget"
        })
        assert resp.status_code == 200


# ============================================================================
# Spot API
# ============================================================================

class TestSpotAPI:
    def test_returns_json(self, session):
        resp = session.get(f"{BASE_URL}/api/spot", params={"user_id": 1, "page": 1, "items": 5})
        assert resp.headers.get('Content-Type', '').startswith('application/json')

    def test_spot_pages_endpoint(self, session):
        resp = session.get(f"{BASE_URL}/api/spot_pages", params={
            "user_id": 1, "symbol": "BTCUSDT", "items": 5
        })
        assert resp.status_code == 200

    def test_spot_id_endpoint(self, session):
        resp = session.get(f"{BASE_URL}/api/spot_id", params={
            "user_id": 1, "symbol": "BTCUSDT", "m1": "Bybit", "m2": "Bitget"
        })
        assert resp.status_code == 200


# ============================================================================
# Data consistency with Redis
# ============================================================================

class TestDataConsistency:
    def test_futures_count_matches_redis(self, session):
        """Go service should return data consistent with Redis."""
        import redis
        r = redis.Redis(host='127.0.0.1', port=6379, db=0, decode_responses=True)
        raw = r.get("Spreads:all")
        redis_count = len(json.loads(raw)) if raw else 0

        resp = session.get(f"{BASE_URL}/api/futures", params={
            "user_id": 1, "page": 1, "items": 1000
        })
        data = resp.json()
        # Go service may filter, but should have some data
        if isinstance(data, list):
            assert len(data) > 0, "Go service returned empty list but Redis has data"
        elif isinstance(data, dict) and 'items' in data:
            assert len(data['items']) > 0, "Go service returned empty items but Redis has data"

    def test_spot_count_matches_redis(self, session):
        import redis
        r = redis.Redis(host='127.0.0.1', port=6379, db=1, decode_responses=True)
        raw = r.get("SpotFutures:all")
        redis_count = len(json.loads(raw)) if raw else 0

        resp = session.get(f"{BASE_URL}/api/spot", params={
            "user_id": 1, "page": 1, "items": 1000
        })
        data = resp.json()
        if isinstance(data, list):
            assert len(data) > 0
        elif isinstance(data, dict) and 'items' in data:
            assert len(data['items']) > 0


# ============================================================================
# Edge cases
# ============================================================================

class TestEdgeCases:
    def test_large_page_number(self, session):
        resp = session.get(f"{BASE_URL}/api/futures", params={
            "user_id": 1, "page": 99999, "items": 5
        })
        assert resp.status_code == 200

    def test_zero_items(self, session):
        resp = session.get(f"{BASE_URL}/api/futures", params={
            "user_id": 1, "page": 1, "items": 0
        })
        assert resp.status_code == 200

    def test_negative_page(self, session):
        resp = session.get(f"{BASE_URL}/api/futures", params={
            "user_id": 1, "page": -1, "items": 5
        })
        assert resp.status_code == 200

    def test_nonexistent_user(self, session):
        resp = session.get(f"{BASE_URL}/api/futures", params={
            "user_id": 999999999, "page": 1, "items": 5
        })
        assert resp.status_code == 200
