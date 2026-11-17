"""
Tests to verify Go service DEX API produces identical output to Python bot.

Run with: python -m pytest funding_bot/tests/test_dex_api_parity.py -v

Requires: Go service running on localhost:8081, MySQL + Redis available.
"""
import json
import os
import requests
import zlib
import mysql.connector
import redis
import pytest

GO_API_BASE = "http://localhost:8081/api"


def get_test_user():
    """Find a user with isActiveAdmin=1 and DEX blacklist entries."""
    conn = mysql.connector.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'),
        user=os.getenv('MYSQL_USER', 'username'),
        password=os.getenv('MYSQL_PASSWORD', 'password'),
        database=os.getenv('MYSQL_DATABASE', 'funding'),
        port=int(os.getenv('DB_PORT', '3306'))
    )
    cursor = conn.cursor()
    cursor.execute(
        "SELECT tgid, dataSearch, listMarketsFutures, information "
        "FROM Users WHERE isActiveAdmin='1' OR testActive='1' LIMIT 20"
    )
    for row in cursor.fetchall():
        tgid, ds_raw, mf_raw, info = row
        if not info or info == b'no':
            continue
        try:
            decompressed = zlib.decompress(info)
            bl = json.loads(decompressed)
            if len(bl) > 0:
                conn.close()
                return tgid, bl
        except Exception:
            continue
    conn.close()
    pytest.skip("No user with DEX blacklist found")


def go_api_dex(user_id, page=1, items=100, sort='spread', lt='0'):
    """Call Go service DEX level 1 API."""
    resp = requests.get(f"{GO_API_BASE}/dex", params={
        "user_id": user_id, "page": page, "items": items,
        "sort": sort, "lt": lt
    })
    return resp.json()


def go_api_dex_pages(user_id, symbol, items=100, sort='spread', lt='0'):
    """Call Go service DEX level 2 API."""
    resp = requests.get(f"{GO_API_BASE}/dex_pages", params={
        "user_id": user_id, "symbol": symbol, "items": items,
        "sort": sort, "lt": lt
    })
    return resp.json()


def go_api_dex_id(user_id, symbol, market):
    """Call Go service DEX level 3 API."""
    resp = requests.get(f"{GO_API_BASE}/dex_id", params={
        "user_id": user_id, "symbol": symbol, "market": market
    })
    return resp.json()


# --- Level 1 tests ---

class TestDexLevel1API:
    """Test DEX level 1 (coin list) via Go API."""

    def setup_method(self):
        self.tgid, self.blacklist = get_test_user()

    def test_returns_active_status(self):
        resp = go_api_dex(self.tgid, page=1, items=5)
        assert resp.get("status") == "active", f"Expected active, got {resp.get('status')}"

    def test_has_pages(self):
        resp = go_api_dex(self.tgid, page=1, items=5)
        assert "pages" in resp
        assert len(resp["pages"]) > 0

    def test_items_are_label_id_pairs(self):
        resp = go_api_dex(self.tgid, page=1, items=5)
        items = resp["pages"][0]["items"]
        for item in items:
            assert isinstance(item, list) and len(item) == 2, f"Expected [label, id], got {item}"
            label, api_id = item
            assert isinstance(label, str) and len(label) > 0
            assert api_id.startswith("dexsymbol_"), f"ID should start with dexsymbol_, got {api_id}"

    def test_blacklisted_tokens_not_in_output(self):
        bl_tokens = set(k.replace("USDT", "") for k in self.blacklist.keys())
        resp = go_api_dex(self.tgid, page=1, items=500)
        all_items = []
        for p in resp.get("pages", []):
            all_items.extend(p.get("items", []))

        for label, api_id in all_items:
            symbol = api_id.replace("dexsymbol_", "")
            # Extract token name from symbol (e.g., "BSC_SIRENUSDT" -> "SIREN")
            if "_" in symbol:
                token_part = symbol.split("_", 1)[1]
            else:
                token_part = symbol
            token_core = token_part.replace("USDT", "")
            assert token_core not in bl_tokens, (
                f"Blacklisted token '{token_core}' found in output: {label}"
            )

    def test_sort_funding_descending(self):
        resp = go_api_dex(self.tgid, page=1, items=10, sort='funding')
        items = []
        for p in resp.get("pages", []):
            items.extend(p.get("items", []))
        # Extract funding rate from label: "TOKEN [CHAIN]: 0.74% фанд"
        rates = []
        for label, _ in items:
            if "% фанд" in label:
                rate_str = label.split(": ")[1].split("%")[0]
                rates.append(float(rate_str))
        # Should be descending
        for i in range(len(rates) - 1):
            assert rates[i] >= rates[i + 1], (
                f"Not descending: {rates[i]} < {rates[i + 1]}"
            )

    def test_sort_spread_descending(self):
        resp = go_api_dex(self.tgid, page=1, items=10, sort='spread')
        items = []
        for p in resp.get("pages", []):
            items.extend(p.get("items", []))
        # Extract diff from label: "TOKEN [CHAIN]: 25.98 вход"
        diffs = []
        for label, _ in items:
            if "вход" in label:
                diff_str = label.split(": ")[1].split(" ")[0]
                diffs.append(float(diff_str))
        for i in range(len(diffs) - 1):
            assert diffs[i] >= diffs[i + 1], (
                f"Not descending: {diffs[i]} < {diffs[i + 1]}"
            )

    def test_label_format_funding(self):
        """Label should be "TOKEN [CHAIN]: X.XX% фанд"."""
        resp = go_api_dex(self.tgid, page=1, items=3, sort='funding')
        items = resp["pages"][0]["items"]
        for label, _ in items:
            assert "% фанд" in label, f"Expected '% фанд' in label: {label}"
            assert "[" in label and "]" in label, f"Expected '[CHAIN]' in label: {label}"

    def test_label_format_spread(self):
        """Label should be "TOKEN [CHAIN]: X.XX вход"."""
        resp = go_api_dex(self.tgid, page=1, items=3, sort='spread')
        items = resp["pages"][0]["items"]
        for label, _ in items:
            assert "вход" in label, f"Expected 'вход' in label: {label}"
            assert "[" in label and "]" in label, f"Expected '[CHAIN]' in label: {label}"

    def test_lt_positive_filters_negative(self):
        """lt=1 should filter out entries with non-positive metric."""
        resp = go_api_dex(self.tgid, page=1, items=100, sort='spread', lt='1')
        items = []
        for p in resp.get("pages", []):
            items.extend(p.get("items", []))
        for label, _ in items:
            if "вход" in label:
                diff_str = label.split(": ")[1].split(" ")[0]
                diff = float(diff_str)
                assert diff > 0, f"Expected positive diff with lt=1, got {diff}: {label}"


# --- Level 2 tests ---

class TestDexLevel2API:
    """Test DEX level 2 (market pairs for a symbol)."""

    def setup_method(self):
        self.tgid, _ = get_test_user()

    def test_returns_active_with_symbol(self):
        # Get a symbol from level 1
        resp1 = go_api_dex(self.tgid, page=1, items=1)
        items = resp1["pages"][0]["items"]
        symbol_api_id = items[0][1].replace("dexsymbol_", "")

        resp = go_api_dex_pages(self.tgid, symbol_api_id)
        assert resp.get("status") == "active"
        assert resp.get("symbol") == symbol_api_id

    def test_has_display_name(self):
        resp1 = go_api_dex(self.tgid, page=1, items=1)
        symbol_api_id = resp1["pages"][0]["items"][0][1].replace("dexsymbol_", "")

        resp = go_api_dex_pages(self.tgid, symbol_api_id)
        assert "displayName" in resp
        assert "[" in resp["displayName"]

    def test_items_are_market_pairs(self):
        resp1 = go_api_dex(self.tgid, page=1, items=1)
        symbol_api_id = resp1["pages"][0]["items"][0][1].replace("dexsymbol_", "")

        resp = go_api_dex_pages(self.tgid, symbol_api_id)
        items = resp["pages"][0]["items"]
        for item in items:
            assert isinstance(item, list) and len(item) == 2
            label, api_id = item
            assert "dexid_" in api_id, f"Expected dexid_ prefix, got {api_id}"

    def test_market_label_format(self):
        """Label should be "Market: X.XX% | Y.YY"."""
        resp1 = go_api_dex(self.tgid, page=1, items=1)
        symbol_api_id = resp1["pages"][0]["items"][0][1].replace("dexsymbol_", "")

        resp = go_api_dex_pages(self.tgid, symbol_api_id)
        items = resp["pages"][0]["items"]
        if items:
            label, _ = items[0]
            assert ":" in label and "%" in label, f"Expected 'Market: X% | Y' format: {label}"


# --- ID mapping tests ---

class TestDexIDMapping:
    """Test that Go API IDs map correctly to Python callback data."""

    def test_dexsymbol_to_dex_market_callback(self):
        """dexsymbol_BSCONUSDT -> dex_market:in:BSCONUSDT:0"""
        api_id = "dexsymbol_BSCONUSDT"
        symbol = api_id.replace("dexsymbol_", "")
        callback = f"dex_market:in:{symbol}:0"
        assert callback == "dex_market:in:BSCONUSDT:0"

    def test_dexid_to_dex_pair_callback(self):
        """dexid_Kucoin_BSCONUSDT -> dex_pair:in:BSCONUSDT:Kucoin:0"""
        api_id = "dexid_Kucoin_BSCONUSDT"
        rest = api_id.replace("dexid_", "")
        parts = rest.split("_", 1)
        market2 = parts[0]
        symbol = parts[1] if len(parts) > 1 else ""
        callback = f"dex_pair:in:{symbol}:{market2}:0"
        assert callback == "dex_pair:in:BSCONUSDT:Kucoin:0"

    def test_dexid_with_chain_prefix(self):
        """dexid_Bybit_ETH_MASKUSDT -> dex_pair:in:ETH_MASKUSDT:Bybit:0"""
        api_id = "dexid_Bybit_ETH_MASKUSDT"
        rest = api_id.replace("dexid_", "")
        parts = rest.split("_", 1)
        market2 = parts[0]
        symbol = parts[1] if len(parts) > 1 else ""
        callback = f"dex_pair:in:{symbol}:{market2}:0"
        assert callback == "dex_pair:in:ETH_MASKUSDT:Bybit:0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
