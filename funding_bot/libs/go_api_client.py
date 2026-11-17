"""
Go service API client for DEX data.

Replaces direct Redis/MySQL reads with optimized Go service calls.
Go service pre-caches and pre-sorts data, making it faster than Python reads.
"""
import os
import logging
import requests
from typing import Optional

logger = logging.getLogger("go_api_client")

GO_SERVICE_HOST = os.getenv("FILTER_HOST", "localhost")
GO_SERVICE_PORT = os.getenv("GO_SERVICE_PORT", "8081")
GO_API_BASE = f"http://{GO_SERVICE_HOST}:{GO_SERVICE_PORT}/api"


def _get(path: str, params: dict, timeout: float = 5.0) -> Optional[dict]:
    """Generic GET request to Go service with error handling."""
    try:
        resp = requests.get(f"{GO_API_BASE}{path}", params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        logger.warning("Go service unreachable at %s", GO_API_BASE)
        return None
    except Exception as e:
        logger.error("Go API error: %s %s -> %s", path, params, e)
        return None


# --- Level 1: DEX coin list ---

def get_dex_list(user_id, page=1, items=100, sort='spread', lt='0'):
    """
    Get DEX coin list from Go service.

    Args:
        user_id: Telegram user ID
        page: page number (1-based)
        items: items per page
        sort: 'spread' (diff) or 'funding' (funding_rate)
        lt: '1' = positive only, '0' = all

    Returns:
        dict with 'status', 'pages', 'displayName', etc. or None on error
    """
    return _get("/dex", {
        "user_id": user_id, "page": page, "items": items,
        "sort": sort, "lt": lt
    })


# --- Level 2: Market pairs for a symbol ---

def get_dex_pages(user_id, symbol, items=100, sort='spread', lt='0'):
    """
    Get market pairs for a DEX symbol from Go service.

    Args:
        user_id: Telegram user ID
        symbol: raw symbol like 'BSCONUSDT'
        items: items per page
        sort: 'spread' (diff) or 'funding' (funding_rate)
        lt: '1' = positive only, '0' = all

    Returns:
        dict with 'status', 'symbol', 'displayName', 'pages', etc. or None
    """
    return _get("/dex_pages", {
        "user_id": user_id, "symbol": symbol, "items": items,
        "sort": sort, "lt": lt
    })


# --- Level 3: Pair details ---

def get_dex_id(user_id, symbol, market):
    """
    Get detailed info for a specific DEX pair from Go service.

    Args:
        user_id: Telegram user ID
        symbol: raw symbol like 'BSCONUSDT'
        market: CEX market name like 'Kucoin'

    Returns:
        dict with detailed pair info or None
    """
    return _get("/dex_id", {
        "user_id": user_id, "symbol": symbol, "market": market
    })


# --- ID mapping helpers ---

def api_id_to_level1_callback(api_id: str, mode: str = 'in', prev_page: int = 0) -> str:
    """
    Convert Go API level 1 ID to Telegram callback data.

    'dexsymbol_BSCONUSDT' -> 'dex_market:in:BSCONUSDT:0'
    """
    symbol = api_id.replace("dexsymbol_", "")
    return f"dex_market:{mode}:{symbol}:{prev_page}"


def api_id_to_level2_callback(api_id: str, mode: str = 'in', prev_page: int = 0) -> str:
    """
    Convert Go API level 2 ID to Telegram callback data.

    'dexid_Kucoin_BSCONUSDT' -> 'dex_pair:in:BSCONUSDT:Kucoin:0'
    'dexid_Bybit_ETH_MASKUSDT' -> 'dex_pair:in:ETH_MASKUSDT:Bybit:0'
    """
    rest = api_id.replace("dexid_", "")
    # Market name is always first token (no underscores in market names)
    # Symbol may contain underscores (e.g., ETH_MASKUSDT)
    parts = rest.split("_", 1)
    market2 = parts[0]
    symbol = parts[1] if len(parts) > 1 else ""
    return f"dex_pair:{mode}:{symbol}:{market2}:{prev_page}"


def sort_param_to_mode(sort_param: str) -> str:
    """Convert sort parameter to Telegram callback mode."""
    return 'fund' if sort_param == 'funding' else 'in'
