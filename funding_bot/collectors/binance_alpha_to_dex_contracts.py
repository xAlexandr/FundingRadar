#!/usr/bin/env python3
"""
binance_alpha_to_dex_contracts.py

Polling Binance Alpha API every 60s, extracting token contract + chain,
mapping chain -> dexscreener style, and appending unique lines "chain:address"
to binance_alpha_contracts.txt
"""

import asyncio
import aiohttp
import os
import time
import logging
from typing import Set

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("binance_alpha")

BINANCE_ALPHA_URL = "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list"
OUTPUT_FILE = os.getenv("BINANCE_ALPHA_CONTRACTS_FILE", "./binance_alpha_contracts.txt")
POLL_INTERVAL = float(os.getenv("BINANCE_ALPHA_POLL_INTERVAL", "60"))  # seconds
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))
RETRY_MAX = int(os.getenv("RETRY_MAX", "3"))
RETRY_BACKOFF = float(os.getenv("RETRY_BACKOFF", "1.0"))
REMOVED_CONTRACTS_FILE = os.getenv("REMOVED_CONTRACTS_FILE", "./removed_contracts.txt")

# Map common chainName / chainId -> dexscreener canonical string
CHAIN_MAP = {
    # names likely returned by Binance in chainName
    "BSC": "bsc",
    "BINANCE SMART CHAIN": "bsc",
    "ETH": "ethereum",
    "ETHEREUM": "ethereum",
    "POLYGON": "polygon",
    "MATIC": "polygon",
    "SOL": "solana",
    "SOLANA": "solana",
    "TRON": "tron",
    "TRX": "tron",
    "AVAX": "avalanche",
    "AVALANCHE": "avalanche",
    "ARB": "arbitrum",
    "ARBITRUM": "arbitrum",
    "OPTIMISM": "optimism",
    "BASE": "base",
    "APTOS": "aptos",
    "NEAR": "near",
    "CELO": "celo",
    # add more as you see them
}

# Fallback mapping by chainId (as strings)
CHAINID_MAP = {
    "1": "ethereum",       # ETH
    "56": "bsc",           # BSC
    "137": "polygon",      # Polygon
    "43114": "avalanche",  # Avalanche
    "250": "fantom",       # Fantom (if appears)
    "11155111": "ethereum",# Sepolia (if appears)
    "42161": "arbitrum",
    "10": "optimism",
    "1313161554": "aurora",
    # add others as you discover them
}

# file lock for async safe writes (single-process)
_file_lock = asyncio.Lock()

def load_removed_addresses(path: str) -> set:
    s = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                ln = line.strip()
                if not ln or ln.startswith("#"):
                    continue
                # accept "chain:addr" or "addr"
                if ':' in ln:
                    _, addr = ln.split(':', 1)
                else:
                    addr = ln
                s.add(addr.strip().lower())
    except FileNotFoundError:
        pass
    return s


def load_existing_contracts(path: str) -> Set[str]:
    s = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                s.add(line)
    except FileNotFoundError:
        pass
    return s

async def append_contract_lines(path: str, lines):
    """Append unique lines atomically (simple)."""
    if not lines:
        return
    async with _file_lock:
        existing = load_existing_contracts(path)
        to_write = []
        for ln in lines:
            if ln not in existing:
                to_write.append(ln)
                existing.add(ln)
        if not to_write:
            return
        # ensure directory exists
        d = os.path.dirname(path)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for ln in to_write:
                f.write(ln + "\n")
        logger.info("Appended %d new contract lines to %s", len(to_write), path)

def map_chain(chain_name: str, chain_id) -> str:
    """Try to map chainName/chainId to canonical dexscreener chain string."""
    if chain_name:
        key = str(chain_name).strip().upper()
        mapped = CHAIN_MAP.get(key)
        if mapped:
            return mapped
    if chain_id is not None:
        cid = str(chain_id).strip()
        mapped = CHAINID_MAP.get(cid)
        if mapped:
            return mapped
    return None

async def http_get(session, url, params=None, headers=None, timeout=HTTP_TIMEOUT, retries=RETRY_MAX):
    for attempt in range(1, retries + 1):
        try:
            async with session.get(url, params=params, headers=headers, timeout=timeout) as r:
                text = await r.text()
                if r.status == 200:
                    try:
                        return await r.json()
                    except Exception:
                        logger.debug("Non-json from %s body=%s", url, (text[:200] if text else ""))
                        return None
                else:
                    logger.warning("GET %s returned status %s", url, r.status)
                    if 400 <= r.status < 500 and r.status != 429:
                        return None
        except asyncio.TimeoutError:
            logger.warning("Timeout GET %s (attempt %d/%d)", url, attempt, retries)
        except Exception as e:
            logger.debug("GET %s failed (attempt %d/%d): %s", url, attempt, retries, e)
        await asyncio.sleep(RETRY_BACKOFF * attempt)
    return None

async def fetch_and_persist(session):
    data = await http_get(session, BINANCE_ALPHA_URL)
    if not data or not isinstance(data, dict):
        logger.warning("No valid JSON from Binance Alpha endpoint")
        return 0

    rows = data.get("data") or []
    if not isinstance(rows, list):
        logger.warning("Unexpected 'data' type from Binance Alpha")
        return 0

    existing = load_existing_contracts(OUTPUT_FILE)
    removed_set = load_removed_addresses(REMOVED_CONTRACTS_FILE)
    to_add = []

    for token in rows:
        try:
            addr = token.get("contractAddress") or token.get("contract_address") or ""
            if not addr:
                continue
            chain_name = token.get("chainName") or token.get("chain") or None
            chain_id = token.get("chainId") or token.get("chain_id") or None

            mapped = map_chain(chain_name, chain_id)
            if not mapped:
                logger.debug("Unmapped chain for token %s: chainName=%s chainId=%s", token.get("symbol"), chain_name, chain_id)
                continue

            addr_norm = addr.strip().lower()
            # skip if addr in removed list
            if addr_norm in removed_set:
                logger.debug("Skipping %s because present in removed list", addr_norm)
                continue

            line = f"{mapped}:{addr_norm}"
            if line not in existing and line not in to_add:
                to_add.append(line)
        except Exception:
            logger.exception("Error processing token row: %s", token)
            continue

    if to_add:
        await append_contract_lines(OUTPUT_FILE, to_add)
    return len(to_add)


async def main_loop():
    logger.info("Starting Binance Alpha contracts poller; writing to %s", OUTPUT_FILE)
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=HTTP_TIMEOUT, sock_read=HTTP_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            try:
                added = await fetch_and_persist(session)
                if added:
                    logger.info("Added %d new contracts from Binance Alpha", added)
                else:
                    logger.debug("No new contracts found this cycle")
            except Exception:
                logger.exception("Error in fetch cycle")
            await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
