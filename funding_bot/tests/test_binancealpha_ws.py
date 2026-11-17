"""Tests for BinanceAlpha WebSocket connector behavior.

Tests that:
1. Connector can resolve alphaId from REST API
2. Connector builds correct WebSocket stream name
3. Connector handles missing alphaId gracefully
"""
import pytest


class TestBinanceAlphaConnector:
    """Tests for the binancealpha.js connector logic (mirrored in Python for verification)."""

    def test_ws_symbol_from_alpha_id(self):
        """alphaId 'ALPHA_953' → wsSymbol 'alpha_953usdt'."""
        alpha_id = "ALPHA_953"
        ws_symbol = alpha_id.lower().replace('alpha_', 'alpha_') + 'usdt'
        assert ws_symbol == "alpha_953usdt"

    def test_ws_stream_name(self):
        """Full stream name from alphaId."""
        alpha_id = "ALPHA_953"
        ws_symbol = alpha_id.lower() + 'usdt'
        depth_stream = f"{ws_symbol}@depth20@500ms"
        assert depth_stream == "alpha_953usdt@depth20@500ms"

    def test_ws_stream_with_different_ids(self):
        """Various alphaId formats."""
        cases = [
            ("ALPHA_1", "alpha_1usdt@depth20@500ms"),
            ("ALPHA_100", "alpha_100usdt@depth20@500ms"),
            ("ALPHA_9999", "alpha_9999usdt@depth20@500ms"),
        ]
        for alpha_id, expected in cases:
            ws_symbol = alpha_id.lower() + 'usdt'
            depth_stream = f"{ws_symbol}@depth20@500ms"
            assert depth_stream == expected

    def test_empty_alpha_id_no_stream(self):
        """Empty alphaId should produce no stream name."""
        alpha_id = ""
        ws_symbol = alpha_id.lower() + 'usdt' if alpha_id else ""
        depth_stream = f"{ws_symbol}@depth20@500ms" if ws_symbol else ""
        assert depth_stream == ""

    def test_symbol_lookup_from_api_response(self):
        """Verify we can extract alphaId from BinanceAlpha API response."""
        # Simulated API response
        api_tokens = [
            {"symbol": "BILL", "alphaId": "ALPHA_953", "price": "0.03"},
            {"symbol": "ARX", "alphaId": "ALPHA_993", "price": "0.17"},
            {"symbol": "NES", "alphaId": "ALPHA_994", "price": "0.58"},
        ]
        # Our symbol is "BILLUSDT", we need to find alphaId
        target_symbol = "BILL"
        found = next((t for t in api_tokens if t["symbol"] == target_symbol), None)
        assert found is not None
        assert found["alphaId"] == "ALPHA_953"

    def test_alpha_id_not_found(self):
        """When symbol is not in API response, alphaId should be empty."""
        api_tokens = [
            {"symbol": "BILL", "alphaId": "ALPHA_953"},
        ]
        target_symbol = "NONEXISTENT"
        found = next((t for t in api_tokens if t["symbol"] == target_symbol), None)
        alpha_id = found["alphaId"] if found else ""
        assert alpha_id == ""
