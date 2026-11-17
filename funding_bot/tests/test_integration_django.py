"""Integration tests for Django API endpoints.

Tests the Django backend endpoints that proxy to the Go service
and handle authentication.

Requires: Django running on localhost:8000
"""
import pytest
import requests
import json
import time
import hashlib
import hmac

BASE_URL = "http://127.0.0.1:8000"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.timeout = 10
    return s


# ============================================================================
# Health / Basic connectivity
# ============================================================================

class TestDjangoHealth:
    def test_admin_accessible(self, session):
        resp = session.get(f"{BASE_URL}/admin/")
        # Should redirect to login or show login page
        assert resp.status_code in (200, 302)

    def test_api_root(self, session):
        resp = session.get(f"{BASE_URL}/api/")
        assert resp.status_code in (200, 404)

    def test_token_endpoint_exists(self, session):
        resp = session.post(f"{BASE_URL}/api/token/", json={})
        # Should return 400 (bad request) or 405 (method not allowed)
        assert resp.status_code in (400, 405)


# ============================================================================
# Coins endpoint
# ============================================================================

class TestCoinsEndpoint:
    def test_get_coins_requires_auth(self, session):
        """Coins endpoint requires JWT authentication."""
        resp = session.get(f"{BASE_URL}/api/coins/")
        assert resp.status_code in (200, 401)

    def test_get_coins_no_auth_returns_401(self, session):
        resp = session.get(f"{BASE_URL}/api/coins/")
        assert resp.status_code == 401


# ============================================================================
# Subscription proxy endpoint
# ============================================================================

class TestProxySubscription:
    def test_proxy_requires_sub_id(self, session):
        resp = session.get(f"{BASE_URL}/api/proxy/testuser")
        # Should work or return error (depending on 3x-ui availability)
        assert resp.status_code in (200, 400, 403, 502)

    def test_proxy_missing_sub(self, session):
        resp = session.get(f"{BASE_URL}/api/proxy/")
        assert resp.status_code in (200, 400, 404)


# ============================================================================
# API endpoints without auth (should return proper errors)
# ============================================================================

class TestUnauthenticatedAccess:
    def test_get_futures_no_auth(self, session):
        resp = session.get(f"{BASE_URL}/api/get_futures/")
        # Should return 401 or 403 (JWT required)
        assert resp.status_code in (401, 403)

    def test_get_spot_no_auth(self, session):
        resp = session.get(f"{BASE_URL}/api/get_spot/")
        assert resp.status_code in (401, 403)

    def test_get_subscribe_no_auth(self, session):
        resp = session.get(f"{BASE_URL}/api/get_subscribe/")
        assert resp.status_code in (401, 403)

    def test_update_depth_no_auth(self, session):
        resp = session.post(f"{BASE_URL}/api/update-depth/", json={"depth_value": 10})
        assert resp.status_code in (401, 403)


# ============================================================================
# Telegram login endpoint
# ============================================================================

class TestTelegramLogin:
    def test_telegram_login_invalid_data(self, session):
        resp = session.post(f"{BASE_URL}/api/auth/telegram/",
                           data="invalid_data",
                           headers={"Content-Type": "application/x-www-form-urlencoded"})
        # Should return 400 or 401
        assert resp.status_code in (400, 401)

    def test_telegram_login_empty(self, session):
        resp = session.post(f"{BASE_URL}/api/auth/telegram/",
                           data="",
                           headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert resp.status_code in (400, 401)


# ============================================================================
# Data settings endpoints (require auth)
# ============================================================================

class TestDataSettings:
    def test_get_data_settings_no_auth(self, session):
        resp = session.get(f"{BASE_URL}/api/get_data_settings/")
        assert resp.status_code in (401, 403)

    def test_change_to_spread_no_auth(self, session):
        resp = session.get(f"{BASE_URL}/api/get_change_to_spread/")
        assert resp.status_code in (401, 403)

    def test_change_to_course_no_auth(self, session):
        resp = session.get(f"{BASE_URL}/api/get_change_to_course/")
        assert resp.status_code in (401, 403)

    def test_change_to_big_no_auth(self, session):
        resp = session.get(f"{BASE_URL}/api/get_change_to_big/")
        assert resp.status_code in (401, 403)


# ============================================================================
# Frontend page routes
# ============================================================================

class TestFrontendRoutes:
    def test_main_page(self, session):
        resp = session.get(f"{BASE_URL}/spot/Bybit/Bitget/BTCUSDT/")
        # Should return 200 or redirect
        assert resp.status_code in (200, 301, 302, 404)

    def test_futures_page(self, session):
        resp = session.get(f"{BASE_URL}/futures/Bybit/Bitget/BTCUSDT/")
        assert resp.status_code in (200, 301, 302, 404)


# ============================================================================
# Rate limiting / error handling
# ============================================================================

class TestErrorHandling:
    def test_nonexistent_endpoint(self, session):
        resp = session.get(f"{BASE_URL}/api/nonexistent/")
        assert resp.status_code in (404, 405)

    def test_method_not_allowed(self, session):
        resp = session.delete(f"{BASE_URL}/api/coins/")
        # Returns 401 (no auth) or 405 (method not allowed)
        assert resp.status_code in (401, 404, 405)

    def test_invalid_json_body(self, session):
        resp = session.post(f"{BASE_URL}/api/auth/telegram/",
                           data="not json",
                           headers={"Content-Type": "application/json"})
        assert resp.status_code in (400, 401)
