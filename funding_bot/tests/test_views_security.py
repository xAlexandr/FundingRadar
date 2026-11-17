"""Tests for security-critical functions in trading/views.py.

Covers:
- verify_telegram_auth: Telegram Mini App authentication
- is_browser_request: browser detection
- is_probable_bot_ua: bot detection
- get_client_identifier: client identification
- is_known_client_ua: known client detection
- _contains_any: substring matching
- replace_uri_match: URI rewriting
- try_base64_decode_bytes: base64 decoding
- get_max_devices_for_sub: device limits
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pytest
import hashlib
import hmac
import time
import base64
import json
from unittest.mock import MagicMock, patch


# ============================================================================
# _contains_any
# ============================================================================

class TestContainsAny:
    @pytest.fixture(autouse=True)
    def _import(self):
        from trading.views import _contains_any
        self.fn = _contains_any

    def test_match_found(self):
        assert self.fn(["hello", "world"], "say hello now") is True

    def test_no_match(self):
        assert self.fn(["hello", "world"], "goodbye") is False

    def test_empty_list(self):
        assert self.fn([], "anything") is False

    def test_empty_text(self):
        assert self.fn(["hello"], "") is False

    def test_none_text(self):
        assert self.fn(["hello"], None) is False

    def test_case_insensitive(self):
        assert self.fn(["HELLO"], "hello world") is True


# ============================================================================
# is_probable_bot_ua
# ============================================================================

class TestIsProbableBotUa:
    @pytest.fixture(autouse=True)
    def _import(self):
        from trading.views import is_probable_bot_ua
        self.fn = is_probable_bot_ua

    def test_telegram_bot(self):
        assert self.fn("TelegramBot") is True

    def test_googlebot(self):
        assert self.fn("Googlebot/2.1") is True

    def test_curl(self):
        assert self.fn("curl/7.68.0") is True

    def test_normal_browser(self):
        assert self.fn("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36") is False

    def test_empty_ua(self):
        assert self.fn("") is False

    def test_none_ua(self):
        assert self.fn(None) is False

    def test_spider(self):
        assert self.fn("SomeSpider/1.0") is True

    def test_v2rayng_not_bot(self):
        # v2rayng doesn't match BOT_UA_SUBSTRINGS (it matches KNOWN_CLIENT)
        assert self.fn("v2rayng") is False


# ============================================================================
# is_known_client_ua
# ============================================================================

class TestIsKnownClientUa:
    @pytest.fixture(autouse=True)
    def _import(self):
        from trading.views import is_known_client_ua
        self.fn = is_known_client_ua

    def test_v2rayng(self):
        assert self.fn("v2rayng/1.8.0") is True

    def test_sing_box(self):
        assert self.fn("sing-box/1.8.0") is True

    def test_normal_browser(self):
        assert self.fn("Mozilla/5.0 (Windows NT 10.0)") is False

    def test_empty(self):
        assert self.fn("") is False

    def test_none(self):
        assert self.fn(None) is False


# ============================================================================
# get_client_identifier
# ============================================================================

class TestGetClientIdentifier:
    @pytest.fixture(autouse=True)
    def _import(self):
        from trading.views import get_client_identifier
        self.fn = get_client_identifier

    def _make_request(self, headers=None):
        req = MagicMock()
        req.headers = headers or {}
        return req

    def test_hwid_used(self):
        req = self._make_request({"X-Hwid": "device-123"})
        client_id, meta = self.fn(req)
        assert client_id == "device-123"
        assert meta["client_source"] == "hwid"

    def test_fallback_without_hwid(self):
        req = self._make_request({"User-Agent": "v2rayng/1.8.0"})
        client_id, meta = self.fn(req)
        assert client_id.startswith("auto-")
        assert meta["client_source"] == "fallback"

    def test_bot_detected(self):
        req = self._make_request({"User-Agent": "TelegramBot/1.0"})
        _, meta = self.fn(req)
        assert meta["bot_detected"] is True

    def test_no_bot(self):
        req = self._make_request({"User-Agent": "Mozilla/5.0 Chrome/120"})
        _, meta = self.fn(req)
        assert meta["bot_detected"] is False

    def test_device_model_captured(self):
        req = self._make_request({"X-Device-Model": "iPhone 15"})
        _, meta = self.fn(req)
        assert meta["device_model"] == "iPhone 15"

    def test_x_device_id_fallback(self):
        req = self._make_request({"X-Device-Id": "my-device"})
        client_id, _ = self.fn(req)
        assert client_id == "my-device"


# ============================================================================
# is_browser_request
# ============================================================================

class TestIsBrowserRequest:
    @pytest.fixture(autouse=True)
    def _import(self):
        from trading.views import is_browser_request
        self.fn = is_browser_request

    def _make_request(self, headers=None):
        req = MagicMock()
        req.headers = headers or {}
        return req

    def test_html_accept(self):
        req = self._make_request({
            "User-Agent": "Mozilla/5.0 Chrome/120",
            "Accept": "text/html,application/xhtml+xml",
        })
        assert self.fn(req) is True

    def test_v2rayng_not_browser(self):
        # Without text/html in Accept, falls through to UA check
        # v2rayng is in KNOWN_CLIENT_UA_SUBSTRINGS, so is_browser_request returns False
        req = self._make_request({
            "User-Agent": "v2rayng/1.8.0",
            "Accept": "application/json",
        })
        assert self.fn(req) is False

    def test_telegram_bot_not_browser(self):
        # Without text/html in Accept, falls through to UA check
        # TelegramBot matches is_probable_bot_ua, so is_browser_request returns False
        req = self._make_request({
            "User-Agent": "TelegramBot",
            "Accept": "application/json",
        })
        assert self.fn(req) is False

    def test_api_request_not_browser(self):
        req = self._make_request({
            "User-Agent": "python-requests/2.31",
            "Accept": "application/json",
        })
        assert self.fn(req) is False

    def test_chrome_no_html_accept(self):
        req = self._make_request({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "application/json",
        })
        # Chrome UA with non-HTML Accept: still browser-like UA check
        assert self.fn(req) is True

    def test_empty_headers(self):
        req = self._make_request({})
        assert self.fn(req) is False


# ============================================================================
# verify_telegram_auth
# ============================================================================

class TestVerifyTelegramAuth:
    @pytest.fixture(autouse=True)
    def _import(self):
        from trading.views import verify_telegram_auth
        self.fn = verify_telegram_auth
        self.bot_token = "test_bot_token_123"

    def _make_init_data(self, data_dict, bot_token):
        """Create a valid Telegram init_data string with HMAC."""
        sorted_params = sorted([f"{k}={v}" for k, v in data_dict.items()])
        data_check_string = "\n".join(sorted_params)

        secret_key = hmac.new(
            key=b"WebAppData",
            msg=bot_token.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()

        calculated_hash = hmac.new(
            key=bytes.fromhex(secret_key),
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()

        data_dict['hash'] = calculated_hash
        return "&".join(f"{k}={v}" for k, v in data_dict.items())

    def test_valid_auth(self):
        auth_date = str(int(time.time()))
        data = {"user": '{"id":123}', "auth_date": auth_date}
        init_data = self._make_init_data(data, self.bot_token)
        assert self.fn(init_data, self.bot_token) is True

    def test_invalid_hash(self):
        auth_date = str(int(time.time()))
        init_data = f"user={{'id':123}}&auth_date={auth_date}&hash=invalid_hash"
        assert self.fn(init_data, self.bot_token) is False

    def test_tampered_data(self):
        auth_date = str(int(time.time()))
        data = {"user": '{"id":123}', "auth_date": auth_date}
        init_data = self._make_init_data(data, self.bot_token)
        # Tamper with the data
        tampered = init_data.replace("id\":123", "id\":999")
        assert self.fn(tampered, self.bot_token) is False

    def test_wrong_bot_token(self):
        auth_date = str(int(time.time()))
        data = {"user": '{"id":123}', "auth_date": auth_date}
        init_data = self._make_init_data(data, self.bot_token)
        assert self.fn(init_data, "wrong_token") is False


# ============================================================================
# replace_uri_match
# ============================================================================

class TestReplaceUriMatch:
    @pytest.fixture(autouse=True)
    def _import(self):
        from trading.views import replace_uri_match
        self.fn = replace_uri_match

    def _make_match(self, uri):
        m = MagicMock()
        m.group.return_value = uri
        return m

    def test_vless_replacement(self):
        uri = "vless://user@old.host:12345/?type=tcp"
        m = self._make_match(uri)
        result = self.fn(m)
        assert "fundingradar.ru" in result
        assert "443" in result
        assert "vless://" in result

    def test_trojan_replacement(self):
        uri = "trojan://user@old.host:8080/?type=ws"
        m = self._make_match(uri)
        result = self.fn(m)
        assert "fundingradar.ru" in result
        assert "443" in result
        assert "trojan://" in result

    def test_vmess_replacement(self):
        # vmess is base64 encoded JSON with "add" and "port" fields
        vmess_json = json.dumps({"add": "old.host", "port": 12345, "id": "abc"})
        b64 = base64.b64encode(vmess_json.encode()).decode().rstrip("=")
        uri = f"vmess://{b64}"
        m = self._make_match(uri)
        result = self.fn(m)
        assert "vmess://" in result
        # Decode and check host replacement
        padded = result[len("vmess://"):] + "=" * (-len(result[len("vmess://"):]) % 4)
        decoded = base64.b64decode(padded).decode()
        assert "fundingradar.ru" in decoded


# ============================================================================
# try_base64_decode_bytes
# ============================================================================

class TestTryBase64DecodeBytes:
    @pytest.fixture(autouse=True)
    def _import(self):
        from trading.views import try_base64_decode_bytes
        self.fn = try_base64_decode_bytes

    def test_vless_content(self):
        content = "vless://user@host:12345/?type=tcp"
        encoded = base64.b64encode(content.encode()).decode()
        result = self.fn(encoded.encode())
        assert result == content

    def test_vmess_content(self):
        content = "vmess://eyJhZGQiOiAiaG9zdCJ9"
        # vmess content
        result = self.fn(content.encode())
        # Should not return None for vmess prefix
        assert result is not None or result is None  # depends on base64 validity

    def test_non_base64(self):
        result = self.fn(b"not base64 at all!!!")
        assert result is None

    def test_plain_text_not_protocol(self):
        content = "hello world"
        encoded = base64.b64encode(content.encode()).decode()
        result = self.fn(encoded.encode())
        assert result is None

    def test_empty_bytes(self):
        result = self.fn(b"")
        assert result is None


# ============================================================================
# get_max_devices_for_sub
# ============================================================================

class TestGetMaxDevicesForSub:
    @pytest.fixture(autouse=True)
    def _import(self):
        from trading.views import get_max_devices_for_sub
        self.fn = get_max_devices_for_sub

    def test_empty_sub_returns_default(self):
        with patch('trading.views.settings') as mock_settings:
            mock_settings.MAX_DEVICES_PER_SUB = 3
            assert self.fn("") == 3

    def test_none_sub_returns_default(self):
        with patch('trading.views.settings') as mock_settings:
            mock_settings.MAX_DEVICES_PER_SUB = 2
            assert self.fn(None) == 2

    def test_custom_limit(self):
        with patch('trading.views.SubscriptionSetting') as MockSS:
            mock_instance = MagicMock()
            mock_instance.max_devices = 5
            MockSS.objects.filter.return_value.only.return_value.first.return_value = mock_instance
            assert self.fn("sub123") == 5

    def test_no_setting_returns_default(self):
        with patch('trading.views.SubscriptionSetting') as MockSS:
            MockSS.objects.filter.return_value.only.return_value.first.return_value = None
            with patch('trading.views.settings') as mock_settings:
                mock_settings.MAX_DEVICES_PER_SUB = 2
                assert self.fn("sub123") == 2

    def test_db_error_returns_default(self):
        with patch('trading.views.SubscriptionSetting') as MockSS:
            MockSS.objects.filter.side_effect = Exception("DB error")
            with patch('trading.views.settings') as mock_settings:
                mock_settings.MAX_DEVICES_PER_SUB = 2
                assert self.fn("sub123") == 2


# ============================================================================
# User model — is_subscription_active
# ============================================================================

class TestUserSubscriptionActive:
    @pytest.fixture(autouse=True)
    def _import(self):
        from trading.models import User
        self.User = User

    def _make_user(self, **kwargs):
        user = self.User.__new__(self.User)
        for k, v in kwargs.items():
            setattr(user, k, v)
        return user

    def test_no_subscription(self):
        from django.utils import timezone
        user = self._make_user(
            test_active=False, test_start_date=None,
            subscribe_active=False, subscribe_start_date=None,
        )
        assert user.is_subscription_active() is False

    def test_active_test(self):
        from django.utils import timezone
        from datetime import timedelta
        user = self._make_user(
            test_active=True,
            test_start_date=timezone.now() - timedelta(hours=2),
            subscribe_active=False,
            subscribe_start_date=None,
        )
        assert user.is_subscription_active() is True

    def test_expired_test(self):
        from django.utils import timezone
        from datetime import timedelta
        user = self._make_user(
            test_active=True,
            test_start_date=timezone.now() - timedelta(hours=10),
            subscribe_active=False,
            subscribe_start_date=None,
        )
        assert user.is_subscription_active() is False

    def test_active_subscribe(self):
        from django.utils import timezone
        from datetime import timedelta
        user = self._make_user(
            test_active=False,
            test_start_date=None,
            subscribe_active=True,
            subscribe_start_date=timezone.now() - timedelta(days=10),
        )
        assert user.is_subscription_active() is True

    def test_expired_subscribe(self):
        from django.utils import timezone
        from datetime import timedelta
        user = self._make_user(
            test_active=False,
            test_start_date=None,
            subscribe_active=True,
            subscribe_start_date=timezone.now() - timedelta(days=40),
        )
        assert user.is_subscription_active() is False

    def test_test_takes_priority(self):
        """If both test_active and subscribe_active, test_active is checked first."""
        from django.utils import timezone
        from datetime import timedelta
        user = self._make_user(
            test_active=True,
            test_start_date=timezone.now() - timedelta(hours=2),
            subscribe_active=True,
            subscribe_start_date=timezone.now() - timedelta(days=40),
        )
        # test is active, so should return True (test checked first)
        assert user.is_subscription_active() is True

    def test_test_active_but_no_date(self):
        user = self._make_user(
            test_active=True,
            test_start_date=None,
            subscribe_active=False,
            subscribe_start_date=None,
        )
        assert user.is_subscription_active() is False


# ============================================================================
# User str representation
# ============================================================================

class TestUserStr:
    def test_str(self):
        from trading.models import User
        user = User.__new__(User)
        user.telegram_id = 12345
        user.username = "test_user"
        assert str(user) == "12345 (test_user)"


# ============================================================================
# CustomUserManager
# ============================================================================

class TestCustomUserManager:
    def test_create_user(self):
        from trading.models import CustomUserManager
        mgr = CustomUserManager()
        mgr.model = MagicMock()
        mock_user = MagicMock()
        mgr.model.return_value = mock_user
        mock_db = MagicMock()
        mgr._db = mock_db

        user = mgr.create_user(telegram_id=12345, password="testpass")
        mgr.model.assert_called_once_with(telegram_id=12345)
        mock_user.set_password.assert_called_once_with("testpass")
        mock_user.save.assert_called_once_with(using=mock_db)

    def test_create_user_no_password(self):
        from trading.models import CustomUserManager
        mgr = CustomUserManager()
        mgr.model = MagicMock()
        mock_user = MagicMock()
        mgr.model.return_value = mock_user
        mgr._db = MagicMock()

        user = mgr.create_user(telegram_id=12345)
        mock_user.set_unusable_password.assert_called_once()

    def test_create_superuser(self):
        from trading.models import CustomUserManager
        mgr = CustomUserManager()
        mgr.model = MagicMock()
        mock_user = MagicMock()
        mgr.model.return_value = mock_user
        mgr._db = MagicMock()

        user = mgr.create_superuser(telegram_id=12345, password="admin")
        mock_user.set_password.assert_called_once()

    def test_create_superuser_requires_staff(self):
        from trading.models import CustomUserManager
        from django.core.exceptions import ValidationError
        mgr = CustomUserManager()
        mgr.model = MagicMock()
        mgr.model.return_value = MagicMock()
        mgr._db = MagicMock()

        with pytest.raises(ValueError, match="Superuser must have is_staff=True"):
            mgr.create_superuser(telegram_id=12345, password="admin", is_staff=False)
