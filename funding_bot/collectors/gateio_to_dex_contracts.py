#!/usr/bin/env python3
"""
gateio_to_dex_contracts.py

Автономный бот, который:
 - опрашивает Gate.io /api/v4/spot/tickers
 - для NEW currency_pair (левую часть до '_') запрашивает /api/v4/wallet/currency_chains?currency=XXX (один раз за запуск процесса)
 - сохраняет найденные contract_address в файл dex_contracts.txt в формате "chain:address"
 - если для монеты НЕ найдено contract_address, монета помечается в памяти как "обработанная в этом запуске" и больше не опрашивается до перезапуска
 - если контракты найдены и записаны — монета также добавляется в processed файл, чтобы на последующих запусках не дергать её снова

Конфигурация через env:
  GATEIO_BASE_URL (по умолчанию https://api.gateio.ws)
  DEX_CONTRACTS_FILE (по умолчанию ./dex_contracts.txt)
  PROCESSED_FILE (по умолчанию ./dex_processed.txt)
  TICKERS_POLL_INTERVAL (сек) (по умолчанию 20)
  REQUEST_DELAY (сек) между запросами к currency_chains (по умолчанию 0.5)
  HTTP_TIMEOUT (сек) (по умолчанию 15)
  LOG_LEVEL (по умолчанию INFO)
"""

import asyncio
import aiohttp
import os
import time
import logging
import signal

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("gateio_to_dex")

GATEIO_BASE = os.getenv("GATEIO_BASE_URL", "https://api.gateio.ws").rstrip("/")
DEX_CONTRACTS_FILE = os.getenv("DEX_CONTRACTS_FILE", "./dex_contracts.txt")
PROCESSED_FILE = os.getenv("PROCESSED_FILE", "./dex_processed.txt")
TICKERS_POLL_INTERVAL = float(os.getenv("TICKERS_POLL_INTERVAL", "20"))
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "2"))
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))
RETRY_MAX = int(os.getenv("RETRY_MAX", "3"))
RETRY_BACKOFF = float(os.getenv("RETRY_BACKOFF", "1.0"))
REMOVED_CONTRACTS_FILE = os.getenv("REMOVED_CONTRACTS_FILE", "./removed_contracts.txt")

# Простая карта названий цепочек GateIO -> dexscreener (используются ТОЛЬКО эти значения)
CHAIN_MAP = {
    "ETH": "ethereum", "ERC20": "ethereum", "ETHEREUM": "ethereum",
    "ARBEVM": "arbitrum", "ARB": "arbitrum", "ARBITRUM": "arbitrum",
    "BSC": "bsc", "BEP20": "bsc", "BEP20(BSC)": "bsc",
    "POLYGON": "polygon", "MATIC": "polygon", "POLYGONPOS": "polygon",
    "SOL": "solana", "SOLANA": "solana",
    "TRX": "tron",
    "AVAX": "avalanche", "AVALANCHE": "avalanche",
    "OPTIMISM": "optimism", "OP": "optimism",
    "HARMONY": "harmony",
    "KLAY": "klaytn", "KLAYTN": "klaytn",
    "RON": "ronin",
    "NEAR": "near",
    "CELO": "celo",
    "BASEEVM": "base",
    "BERA": "berachain",
    "APT": "aptos"
}

# Helpers for file I/O with minimal locking (single-process)
_file_lock = asyncio.Lock()

def load_removed_addresses(path):
    s = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                ln = line.strip()
                if not ln or ln.startswith("#"):
                    continue
                if ':' in ln:
                    _, addr = ln.split(':', 1)
                else:
                    addr = ln
                s.add(addr.strip().lower())
    except FileNotFoundError:
        pass
    return s


def load_existing_contracts(path):
    """Load existing contract lines 'chain:address' into a set."""
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

def load_processed(path):
    """Load processed currency symbols (one per line)"""
    s = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                v = line.strip()
                if v:
                    s.add(v.upper())
    except FileNotFoundError:
        pass
    return s

async def append_contract_lines(path, lines):
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
        with open(path, "a", encoding="utf-8") as f:
            for ln in to_write:
                f.write(ln + "\n")
        logger.info("Appended %d new contract lines to %s", len(to_write), path)

async def append_processed_currency(path, currency):
    """Append processed currency (one per line)."""
    if not currency:
        return
    currency = currency.upper()
    async with _file_lock:
        processed = load_processed(path)
        if currency in processed:
            return
        with open(path, "a", encoding="utf-8") as f:
            f.write(currency + "\n")
        logger.debug("Marked %s as processed", currency)

def map_chain_to_dex(chain_raw):
    """Map raw GateIO chain name to dexscreener use.

    IMPORTANT: only use CHAIN_MAP. If chain not present -> return None.
    This prevents adding unknown/unsupported networks to dex_contracts.txt.
    """
    if not chain_raw:
        return None
    key = chain_raw.strip().upper()
    mapped = CHAIN_MAP.get(key)
    if mapped:
        return mapped
    return None

async def http_get(session, url, params=None, headers=None, timeout=HTTP_TIMEOUT, retries=RETRY_MAX):
    """Simple GET with retries."""
    for attempt in range(1, retries + 1):
        try:
            async with session.get(url, params=params, headers=headers, timeout=timeout) as r:
                text = await r.text()
                if r.status == 200:
                    try:
                        data = await r.json()
                        return data
                    except Exception:
                        logger.debug("Non-json from %s (status=%s) body=%s", url, r.status, (text[:200] if text else ""))
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

async def fetch_gateio_tickers(session):
    url = f"{GATEIO_BASE}/api/v4/spot/tickers"
    data = await http_get(session, url)
    if not data:
        return []
    result = []
    for item in data:
        cp = item.get("currency_pair")
        if not cp:
            continue
        result.append(cp)
    return result

async def fetch_currency_chains(session, currency):
    """currency: e.g. LAVA (no _USDT). Returns list of chain dicts or None."""
    url = f"{GATEIO_BASE}/api/v4/wallet/currency_chains"
    params = {"currency": currency}
    return await http_get(session, url, params=params)

async def process_new_currency(session, currency, existing_contracts, removed_set):
    """
    For given currency (e.g. LAVA), call wallet/currency_chains and append any found contract addresses.
    Returns tuple (wrote_any_contracts: bool, found_any_chain_entries: bool)
    - wrote_any_contracts: True if we appended at least one contract line (and external code should persist processed)
    - found_any_chain_entries: True if API returned non-empty list (even if entries had no contract_address)
    """
    logger.info("Processing new currency %s", currency)
    chains = await fetch_currency_chains(session, currency)
    if chains is None:
        logger.debug("No response (None) for currency_chains %s", currency)
        return (False, False)

    if not isinstance(chains, list) or len(chains) == 0:
        logger.debug("currency_chains returned empty list for %s", currency)
        return (False, True)  # we got a response but no entries

    to_append = []
    wrote_any = False
    for ch in chains:
        try:
            addr = (ch.get("contract_address") or "").strip()
            if not addr:
                # no contract address -> skip
                continue
            chain_raw = ch.get("chain") or ch.get("name_en") or ch.get("name_cn") or ""
            mapped = map_chain_to_dex(chain_raw)
            if not mapped:
                logger.debug("Chain mapping failed for %s (raw=%s) - skipping", currency, chain_raw)
                continue
            addr_norm = addr.lower()
            # skip if in removed set
            if addr_norm in removed_set:
                logger.debug("Skipping %s (in removed list)", addr_norm)
                continue
            line = f"{mapped}:{addr_norm}"
            if line not in existing_contracts:
                to_append.append(line)
                existing_contracts.add(line)
                wrote_any = True
        except Exception:
            logger.exception("Error processing chain entry for %s: %s", currency, ch)
            continue

    if to_append:
        await append_contract_lines(DEX_CONTRACTS_FILE, to_append)
    return (wrote_any, True)

async def main_loop():
    # load persistent sets
    existing_contracts = load_existing_contracts(DEX_CONTRACTS_FILE)
    removed_set = load_removed_addresses(REMOVED_CONTRACTS_FILE)
    # ensure we don't add back removed addresses into existing_contracts
    # (just in case someone manually restored line) — prefer removed_set as authoritative
    # Do not include removed addresses into existing_contracts
    # (existing_contracts contains lines 'chain:addr', we keep them but filter later)
    processed_persistent = load_processed(PROCESSED_FILE)

    logger.info("Loaded %d existing contract entries from %s", len(existing_contracts), DEX_CONTRACTS_FILE)
    logger.info("Loaded %d processed currencies from %s", len(processed_persistent), PROCESSED_FILE)

    # in-memory seen set for this run: do not re-process a coin during this process run
    seen_this_run = set()

    stop = False
    def _stop_signal(sig=None, frame=None):
        nonlocal stop
        logger.info("Received stop signal, exiting main loop...")
        stop = True

    signal.signal(signal.SIGINT, _stop_signal)
    signal.signal(signal.SIGTERM, _stop_signal)

    timeout = aiohttp.ClientTimeout(total=None, sock_connect=HTTP_TIMEOUT, sock_read=HTTP_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # We will continuously poll tickers, but any currency will be processed at most once per run.
        while not stop:
            try:
                tickers = await fetch_gateio_tickers(session)
                if not tickers:
                    logger.warning("No tickers obtained from Gate.io")
                else:
                    logger.info("Got %d tickers", len(tickers))

                # sort for reproducibility
                for cp in sorted(tickers):
                    if stop:
                        break
                    # derive base token (left of underscore)
                    if "_" in cp:
                        base = cp.split("_", 1)[0].strip().upper()
                    else:
                        base = cp.strip().upper()
                    if not base:
                        continue

                    # If we've already processed persistently -> skip (we wrote contracts earlier)
                    if base in processed_persistent:
                        # skip permanently (across restarts)
                        continue

                    # If we've seen this coin earlier during this run (regardless of found/no-found) -> skip
                    if base in seen_this_run:
                        continue

                    try:
                        wrote, got_response = await process_new_currency(session, base, existing_contracts, removed_set)

                        # mark as seen in memory irrespective of result (so we don't retry this base during this run)
                        seen_this_run.add(base)

                        if wrote:
                            # if we wrote any contract lines, persist processed so next run won't reprocess
                            await append_processed_currency(PROCESSED_FILE, base)
                            processed_persistent.add(base)
                            logger.info("Added contracts for %s and marked processed", base)
                        else:
                            if got_response:
                                # We received a response but no contract addresses were present.
                                # As requested — we will NOT retry this currency during this run (seen_this_run covers that).
                                logger.debug("No contract_address for %s (response ok). Marked in-memory as seen for this run.", base)
                            else:
                                # got_response==False means we didn't get a response (http error). We also mark seen to avoid retrying here.
                                logger.debug("No currency_chains response for %s. Marked in-memory as seen for this run (no retry).", base)
                        # small delay between per-coin requests
                        await asyncio.sleep(REQUEST_DELAY)
                    except Exception:
                        logger.exception("Error processing currency %s", base)
                        # still mark as seen so we don't keep failing in tight loop
                        seen_this_run.add(base)
                        await asyncio.sleep(REQUEST_DELAY)

                # Sleep until next poll; new tickers (not seen_this_run and not in processed_persistent) will be processed when detected.
                logger.debug("Sleeping %s seconds before next tickers poll", TICKERS_POLL_INTERVAL)
                slept = 0.0
                while slept < TICKERS_POLL_INTERVAL:
                    if stop:
                        break
                    await asyncio.sleep(0.5)
                    slept += 0.5

            except Exception:
                logger.exception("Main loop exception, continuing")
                await asyncio.sleep(2.0)

    logger.info("Bot stopped cleanly.")

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
