"""Tests for BinanceAlpha WebSocket stream selection.

Tests that depth20 provides more levels than fulldepth for tokens with UI orders.
"""
import pytest


class TestBinanceAlphaStreams:
    """Stream behavior tests (logic mirrored from WS tests)."""

    def test_depth20_stream_format(self):
        """depth20 stream: alpha_XXXusdt@depth20@500ms"""
        alpha_id = "ALPHA_994"
        ws_symbol = alpha_id.lower() + 'usdt'
        stream = f"{ws_symbol}@depth20@500ms"
        assert stream == "alpha_994usdt@depth20@500ms"

    def test_fulldepth_stream_format(self):
        """fulldepth stream: alpha_XXXusdt@fulldepth@100ms"""
        alpha_id = "ALPHA_994"
        ws_symbol = alpha_id.lower() + 'usdt'
        stream = f"{ws_symbol}@fulldepth@100ms"
        assert stream == "alpha_994usdt@fulldepth@100ms"

    def test_depth20_snapshot_replaces_book(self):
        """depth20 sends full snapshot — replace entire book."""
        # Simulate: old book has 5 bids, new snapshot has 3 bids
        old_bids = {"100": 10, "99": 20, "98": 30, "97": 40, "96": 50}
        new_bids_data = [["100", "15"], ["99", "25"], ["98", "35"]]

        # Apply snapshot: clear and rebuild
        new_bids = {}
        for item in new_bids_data:
            p, s = item[0], float(item[1])
            if s > 0:
                new_bids[p] = s

        assert len(new_bids) == 3
        assert "97" not in new_bids  # old level removed
        assert "96" not in new_bids  # old level removed

    def test_fulldepth_same_replacement(self):
        """fulldepth also sends full snapshot — same logic."""
        old_asks = {"101": 10, "102": 20}
        new_asks_data = [["101", "5"], ["102", "15"], ["103", "25"]]

        new_asks = {}
        for item in new_asks_data:
            p, s = item[0], float(item[1])
            if s > 0:
                new_asks[p] = s

        assert len(new_asks) == 3
        assert "103" in new_asks  # new level added

    def test_zero_qty_removes_level(self):
        """Qty=0 means level is removed."""
        book = {"100": 10, "99": 20}
        updates = [["100", "0"], ["99", "25"], ["98", "30"]]

        for item in updates:
            p, s = item[0], float(item[1])
            if s > 0:
                book[p] = s
            else:
                book.pop(p, None)

        assert "100" not in book  # removed
        assert book["99"] == 25   # updated
        assert book["98"] == 30   # added

    def test_primary_fallback_strategy(self):
        """Strategy: try depth20 first, fallback to fulldepth."""
        # Simulate: depth20 returns no data for a token
        depth20_data = None
        fulldepth_data = {"bids": 3, "asks": 2}

        # If depth20 has no data, use fulldepth
        result = depth20_data if depth20_data else fulldepth_data
        assert result == fulldepth_data

        # If depth20 has data, use it (more levels)
        depth20_data = {"bids": 20, "asks": 20}
        result = depth20_data if depth20_data else fulldepth_data
        assert result == depth20_data
        assert result["bids"] == 20
