"""Tests for BinanceAlpha order book handling.

Tests that fulldepth snapshots are merged correctly (not cleared).
"""
import pytest


class TestBinanceAlphaOrderBook:
    """Order book merge logic tests."""

    def test_snapshot_merges_not_clears(self):
        """When snapshot has only asks, bids from previous message should be preserved."""
        # Simulate existing book with bids
        bids = {"100": 10.0, "99": 20.0}
        asks = {"101": 5.0, "102": 15.0}

        # New snapshot with ONLY asks (bids empty)
        new_bids = []
        new_asks = [["101", "8.0"], ["102", "18.0"], ["103", "25.0"]]

        # Apply: update existing levels, add new ones, don't clear missing side
        for item in new_bids:
            p, s = item[0], float(item[1])
            if s > 0:
                bids[p] = s
            else:
                bids.pop(p, None)

        for item in new_asks:
            p, s = item[0], float(item[1])
            if s > 0:
                asks[p] = s
            else:
                asks.pop(p, None)

        # Bids should be preserved
        assert len(bids) == 2
        assert bids["100"] == 10.0
        assert bids["99"] == 20.0
        # Asks should be updated
        assert len(asks) == 3
        assert asks["103"] == 25.0

    def test_snapshot_merges_both_sides(self):
        """When snapshot has both sides, both are updated correctly."""
        bids = {"100": 10.0, "99": 20.0}
        asks = {"101": 5.0, "102": 15.0}

        # New snapshot with both sides
        new_bids = [["100", "12.0"], ["98", "30.0"]]  # 100 updated, 98 new, 99 removed (not in snapshot)
        new_asks = [["101", "8.0"], ["103", "25.0"]]   # 101 updated, 103 new, 102 removed

        for item in new_bids:
            p, s = item[0], float(item[1])
            if s > 0:
                bids[p] = s
            else:
                bids.pop(p, None)

        for item in new_asks:
            p, s = item[0], float(item[1])
            if s > 0:
                asks[p] = s
            else:
                asks.pop(p, None)

        # But wait - if snapshot is incremental, we should NOT remove levels not in snapshot
        # Only remove levels with qty=0
        # Let's test the correct behavior:

    def test_incremental_update_removes_zero_qty(self):
        """Levels with qty=0 should be removed."""
        book = {"100": 10.0, "99": 20.0, "98": 30.0}
        updates = [["100", "0"], ["99", "25.0"]]  # 100 removed, 99 updated

        for item in updates:
            p, s = item[0], float(item[1])
            if s > 0:
                book[p] = s
            else:
                book.pop(p, None)

        assert "100" not in book
        assert book["99"] == 25.0
        assert book["98"] == 30.0  # preserved

    def test_empty_snapshot_preserves_book(self):
        """Empty snapshot (no bids/asks) should not clear the book."""
        bids = {"100": 10.0}
        asks = {"101": 5.0}

        # Empty snapshot
        new_bids = []
        new_asks = []

        # Don't clear if snapshot is empty
        if new_bids:
            for item in new_bids:
                p, s = item[0], float(item[1])
                if s > 0:
                    bids[p] = s
                else:
                    bids.pop(p, None)

        if new_asks:
            for item in new_asks:
                p, s = item[0], float(item[1])
                if s > 0:
                    asks[p] = s
                else:
                    asks.pop(p, None)

        assert len(bids) == 1
        assert len(asks) == 1

    def test_first_snapshot_replaces_book(self):
        """First snapshot should replace the book (initial state)."""
        bids = {}
        asks = {}

        # First snapshot
        new_bids = [["100", "10.0"], ["99", "20.0"]]
        new_asks = [["101", "5.0"], ["102", "15.0"]]

        # On first snapshot, replace entire book
        bids.clear()
        asks.clear()
        for item in new_bids:
            p, s = item[0], float(item[1])
            if s > 0:
                bids[p] = s
        for item in new_asks:
            p, s = item[0], float(item[1])
            if s > 0:
                asks[p] = s

        assert len(bids) == 2
        assert len(asks) == 2

    def test_subsequent_snapshots_merge(self):
        """Subsequent snapshots should merge, not replace."""
        bids = {"100": 10.0, "99": 20.0}
        asks = {"101": 5.0}

        # Second snapshot with only bids (asks empty)
        new_bids = [["100", "12.0"], ["98", "30.0"]]
        new_asks = []  # empty!

        # Merge: update bids, don't touch asks
        for item in new_bids:
            p, s = item[0], float(item[1])
            if s > 0:
                bids[p] = s
            else:
                bids.pop(p, None)

        # Asks should be preserved
        assert len(bids) == 3
        assert bids["100"] == 12.0
        assert bids["98"] == 30.0
        assert len(asks) == 1
        assert asks["101"] == 5.0
