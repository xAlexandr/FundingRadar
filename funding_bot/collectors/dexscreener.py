# collectors/dexscreener.py
import asyncio
import aiohttp
import os
import time
import socket
import struct
import pickle
import logging
import random
from itertools import islice
from math import ceil

logger = logging.getLogger("collector.dexscreener")
logging.basicConfig(level=logging.INFO)

SOCKET_PATH = os.getenv('SOCKET_PATH', '/tmp/funding.sock')

# controls
DEX_RPM = int(os.getenv('DEX_RPM', '550'))           # requests per minute allowed by provider 550
DEX_CHUNK_SIZE = int(os.getenv('DEX_CHUNK_SIZE', '30'))  # dexscreener supports up to 30 addresses per request
DEX_CONCURRENCY = int(os.getenv('DEX_CONCURRENCY', '10')) # parallel http requests (10)
DEX_SLEEP = float(os.getenv('DEX_SLEEP', '10'))     # small sleep between loop iterations (10)
DEX_BACKOFF_SEC = float(os.getenv('DEX_BACKOFF_SEC', '0.05')) # (0.05)

# input: either env DEX_CONTRACTS (comma/semicolon separated items) or file path DEX_CONTRACTS_FILE
# expected format per token: chain:address  (e.g. ethereum:0xabc..., bsc:0xaaa..., solana:So1111...)
DEX_CONTRACTS = os.getenv('DEX_CONTRACTS', '')  # example: "ethereum:0x1,...;bsc:0x2,..."
DEX_CONTRACTS_FILE = os.getenv('DEX_CONTRACTS_FILE', '/app/dex_contracts.txt')  # alternative: one "chain:address" per line
# дополнительные пути к файлам контрактов (binance alpha, другие)
BINANCE_ALPHA_CONTRACTS_FILE = os.getenv('BINANCE_ALPHA_CONTRACTS_FILE', '/app/binance_alpha_contracts.txt')
# как часто (в секундах) перечитывать файлы контрактов (по умолчанию 60s)
DEX_CONTRACTS_POLL_INTERVAL = int(os.getenv('DEX_CONTRACTS_POLL_INTERVAL', '60'))
# proxies (optional): comma-separated urls (http://user:pass@host:port)
PROXY_LIST = [p.strip() for p in os.getenv('DEX_PROXY_LIST', '').split(',') if p.strip()]

# endpoints
DEXSCREENER_TOKENS_TEMPLATE = os.getenv('DEXSCREENER_TOKENS_TEMPLATE', 'https://api.dexscreener.com/tokens/v1/{chain}/{addrs}')

# helper: chunk iterable into fixed-size pieces
def chunked_iterable(iterable, size):
    it = iter(iterable)
    while True:
        chunk = list(islice(it, size))
        if not chunk:
            break
        yield chunk

def send_msg(msg):
    payload = pickle.dumps(msg)
    hdr = struct.pack('>I', len(payload))
    for _ in range(3):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(SOCKET_PATH)
            s.sendall(hdr + payload)
            s.close()
            return
        except Exception as e:
            logger.debug("send_msg socket fail %s", e)
            time.sleep(0.05)
    logger.error("Dex collector: failed to send message")

# parse input list from env or file into dict: chain -> set(address)
def _read_contract_file(path):
    """Read file with lines like 'chain:address' (or 'chain,address') and return set of (chain,addr)."""
    res = set()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith('#'):
                    continue
                # support "chain:addr" or "chain,addr" or "addr" (defaults to ethereum)
                raw_fixed = raw.replace(',', ':', 1) if ':' not in raw and ',' in raw else raw
                if ':' in raw_fixed:
                    chain, addr = raw_fixed.split(':', 1)
                else:
                    # bare address -> assume ethereum
                    chain, addr = 'ethereum', raw_fixed
                chain = chain.strip().lower()
                addr = addr.strip()
                if addr:
                    # normalize address to lowercase (helps dedupe)
                    res.add((chain, addr.lower()))
    except FileNotFoundError:
        # no file — that's fine
        pass
    except Exception:
        logger.exception("Error reading contract file %s", path)
    return res


def load_contracts_from_env_or_file():
    """
    Returns dict chain -> set(address)
    combines:
      - DEX_CONTRACTS_FILE
      - BINANCE_ALPHA_CONTRACTS_FILE (if exists)
      - DEX_CONTRACTS env var (comma/semicolon separated entries)
    """
    contracts = {}

    # 1) read main file
    pairs = _read_contract_file(DEX_CONTRACTS_FILE)

    # 2) read binance alpha file (additional)
    pairs |= _read_contract_file(BINANCE_ALPHA_CONTRACTS_FILE)

    # 3) parse DEX_CONTRACTS env var (overrides/extends)
    if DEX_CONTRACTS:
        entries = [e.strip() for e in DEX_CONTRACTS.replace(';', ',').split(',') if e.strip()]
        for e in entries:
            if ':' in e:
                chain, addr = e.split(':', 1)
            elif '/' in e:
                chain, addr = e.split('/', 1)
            else:
                chain, addr = 'ethereum', e
            chain = chain.strip().lower()
            addr = addr.strip()
            if addr:
                pairs.add((chain, addr.lower()))

    # turn set of tuples into dict chain -> set(address)
    for chain, addr in pairs:
        contracts.setdefault(chain, set()).add(addr)

    return contracts


# Замените старый RateLimiter целиком на этот класс
class RateLimiter:
    def __init__(self, rpm, proxies=None):
        self.total_capacity = max(1, int(rpm))
        self.endpoints = ['local'] + (proxies or [])
        n = len(self.endpoints)
        base = self.total_capacity // n
        remainder = self.total_capacity - base * n

        import asyncio
        self.queues = {}
        for i, ep in enumerate(self.endpoints):
            cap = base + (1 if i < remainder else 0)
            q = asyncio.Queue(maxsize=cap)
            # per-endpoint fields
            per_sec = float(cap) / 60.0
            # START TOKENS: small warmup (avoid full burst at startup)
            start_tokens = max(1, int(per_sec * 2))  # ~2 sec worth on start
            start_tokens = min(start_tokens, cap)
            for _ in range(start_tokens):
                q.put_nowait(1)
            self.queues[ep] = {
                'queue': q,
                'cap': cap,
                'per_sec': per_sec,
                'acc': 0.0
            }

        self._task = None
        self._lock = asyncio.Lock()

    async def start_refill(self):
        # refill loop: every 1s add fractional tokens to each queue
        while True:
            await asyncio.sleep(1)
            try:
                for ep, obj in self.queues.items():
                    q = obj['queue']
                    per_sec = obj['per_sec']
                    obj['acc'] += per_sec
                    add = int(obj['acc'])
                    if add:
                        obj['acc'] -= add
                        for _ in range(add):
                            if not q.full():
                                try:
                                    q.put_nowait(1)
                                except Exception:
                                    break
            except Exception:
                # ignore refill errors
                pass

    async def acquire_for(self, proxy):
        """
        proxy: actual proxy string or None -> maps to 'local'
        This will await until token available for the chosen endpoint.
        """
        key = proxy or 'local'
        obj = self.queues.get(key)
        if not obj:
            obj = self.queues['local']
        return await obj['queue'].get()

    def release_for(self, proxy):
        # not strictly required because refill handles it, but keep if you want to return a token early
        key = proxy or 'local'
        obj = self.queues.get(key) or self.queues['local']
        try:
            obj['queue'].put_nowait(1)
        except Exception:
            pass

    # helper for diagnostics
    def debug_queue_sizes(self):
        res = {}
        for ep, obj in self.queues.items():
            try:
                res[ep] = (obj['queue'].qsize(), obj['cap'])
            except Exception:
                res[ep] = ('?', obj.get('cap'))
        return res

async def fetch_json(session, url, proxy=None, timeout=10):
    t0 = time.time()
    try:
        async with session.get(url, proxy=proxy, timeout=timeout) as r:
            elapsed = time.time() - t0
            if r.status == 200:
                logger.debug("fetch_json OK %s proxy=%s time=%.3fs", url, proxy, elapsed)
                return await r.json()
            else:
                text = await r.text()
                logger.warning("fetch_json non-200 %s proxy=%s status=%s time=%.3fs body=%s", url, proxy, r.status, elapsed, (text[:200] if text else ""))
                return None
    except asyncio.TimeoutError:
        logger.warning("fetch_json TIMEOUT %s proxy=%s time=%.3fs", url, proxy, time.time()-t0)
        return None
    except Exception as e:
        logger.exception("fetch_json exception %s proxy=%s err=%s time=%.3fs", url, proxy, e, time.time()-t0)
        return None

# pick proxy round-robin
class ProxyRotator:
    def __init__(self, proxies):
        # create rotation that includes None (local) + proxies so we alternate
        self.items = [None] + (proxies or [])
        self.idx = 0
        self.lock = asyncio.Lock()

    async def next(self):
        async with self.lock:
            if not self.items:
                return None
            p = self.items[self.idx % len(self.items)]
            self.idx += 1
            return p

# ---- вставить в collectors/dexscreener.py вместо process_chain_batches + dex_collector_loop ----

async def worker_loop(worker_id, work_q: asyncio.Queue, session, rate_limiter, proxy_rotator, sem, results_out):
    while True:
        try:
            task = await work_q.get()
            if task is None:
                work_q.task_done()
                break
            chain, chunk = task  # chunk is list of addresses (strings)
            # choose proxy (rotate None + proxies)
            proxy = None
            if proxy_rotator:
                proxy = await proxy_rotator.next()
            # acquire token for endpoint
            await rate_limiter.acquire_for(proxy)
            await asyncio.sleep(random.uniform(0.0, 0.06))  # 0..60ms jitter
            async with sem:
                addrs_str = ','.join(chunk)
                url = DEXSCREENER_TOKENS_TEMPLATE.format(chain=chain, addrs=addrs_str)
                t_req = time.time()
                j = await fetch_json(session, url, proxy=proxy, timeout=15)
                took = time.time() - t_req
                logger.debug("worker[%d] chain=%s chunk_len=%d proxy=%s took=%.3fs result=%s",
                             worker_id, chain, len(chunk), proxy, took, ("ok" if j else "empty"))
                if j:
                    if isinstance(j, list):
                        items = j
                    elif isinstance(j, dict) and 'pairs' in j:
                        items = j['pairs']
                    else:
                        items = j.get('pairs') or j.get('results') or (j.get('data') if isinstance(j.get('data'), list) else [])
                    for it in items:
                        try:
                            chainId = it.get('chainId') or chain
                            baseToken = it.get('baseToken') or {}
                            symbol = (baseToken.get('symbol') or baseToken.get('name') or '')
                            contract = baseToken.get('address') or it.get('pairAddress') or ''
                            price_usd = it.get('priceUsd') if it.get('priceUsd') is not None else (it.get('priceNative') or 0)
                            try:
                                price = float(price_usd or 0)
                            except:
                                price = 0.0
                            vol24 = 0.0
                            vol_obj = it.get('volume') or {}
                            try:
                                vol24 = float(vol_obj.get('h24') or 0)
                            except:
                                vol24 = 0.0

                            # формируем уникальный ключ: SYMBOL_CHAIN или SYMBOL_CHAIN_SHORTADDR
                            if symbol:
                                sym_norm = symbol.replace('_', '').replace('-', '').upper()
                            else:
                                sym_norm = (contract or '')[:6].upper()

                            chain_norm = str(chain).replace('-', '').upper()[:3]

                            # уникальный ключ с цепью и символом
                            key = f"{chain_norm}_{sym_norm}USDT"
                            results_out[key] = {
                                'symbol': key,
                                'price': price,
                                'priceUsd': price,
                                'volume24': vol24,
                                'contract': contract,
                                'chain': chainId,
                                'pairAddress': it.get('pairAddress'),
                                'dexId': it.get('dexId'),
                                'url': it.get('url'),
                                'priceChange': it.get('priceChange'),
                                'liquidity': it.get('liquidity'),
                                'info': it.get('info'),
                                'raw': it
                            }
                        except Exception:
                            pass
                # small backoff
            await asyncio.sleep(DEX_BACKOFF_SEC)
            work_q.task_done()
        except Exception:
            logger.exception("worker_loop exception")
            # avoid tight loop on exception
            await asyncio.sleep(0.1)

async def dex_collector_loop():
    contracts = load_contracts_from_env_or_file()
    if not contracts:
        logger.warning("No DEX contracts configured.")
    rate_limiter = RateLimiter(DEX_RPM, proxies=PROXY_LIST)
    asyncio.create_task(rate_limiter.start_refill())
    proxy_rotator = ProxyRotator(PROXY_LIST) if PROXY_LIST else None
    sem = asyncio.Semaphore(DEX_CONCURRENCY)

    timeout = aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=15)
    # Important: tune connector limits to allow high parallelism and keepalive
    connector = aiohttp.TCPConnector(limit=0, limit_per_host=0, ttl_dns_cache=300)
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        while True:
            start = time.time()
            # reload contracts only once per DEX_CONTRACTS_POLL_INTERVAL seconds
            # to avoid re-reading files too often. This ensures bot checks files ~1 time/min.
            now = time.time()
            if not hasattr(dex_collector_loop, "_last_contracts_reload"):
                dex_collector_loop._last_contracts_reload = 0.0
                dex_collector_loop._cached_contracts = None

            if now - dex_collector_loop._last_contracts_reload >= DEX_CONTRACTS_POLL_INTERVAL or dex_collector_loop._cached_contracts is None:
                try:
                    dex_collector_loop._cached_contracts = load_contracts_from_env_or_file()
                    dex_collector_loop._last_contracts_reload = now
                    logger.debug("Reloaded dex contracts from files; chains=%d",
                                 len(dex_collector_loop._cached_contracts))
                except Exception:
                    logger.exception("Failed reloading dex contracts")
                    dex_collector_loop._cached_contracts = load_contracts_from_env_or_file()

            contracts = dex_collector_loop._cached_contracts or {}
            # build global list of chunks
            work_q = asyncio.Queue()
            for chain, addrs_set in contracts.items():
                addrs_list = list(addrs_set)
                for chunk in chunked_iterable(addrs_list, DEX_CHUNK_SIZE):
                    await work_q.put((chain, chunk))
            # spawn workers
            results = {}
            workers = []
            n_workers = max(4, DEX_CONCURRENCY)  # at least some workers
            for i in range(n_workers):
                w = asyncio.create_task(worker_loop(i, work_q, session, rate_limiter, proxy_rotator, sem, results))
                workers.append(w)
            # wait for queue to be processed
            await work_q.join()
            # stop workers
            for _ in workers:
                await work_q.put(None)
            await asyncio.gather(*workers, return_exceptions=True)

            # prepare msg & send
            data_spot = {}
            market_meta = {}
            ts = time.time()
            for k, meta in results.items():
                try:
                    price = meta.get('price') or 0.0
                    data_spot[k] = [k, price, price]
                    market_meta[k] = {
                        'contract': meta.get('contract'),
                        'chain': meta.get('chain'),
                        'volume24': meta.get('volume24'),
                        'pairAddress': meta.get('pairAddress'),
                        'dexId': meta.get('dexId'),
                        'url': meta.get('url'),
                        'priceChange': meta.get('priceChange'),
                        'liquidity': meta.get('liquidity'),
                        'info': meta.get('info'),
                        'priceUsd': meta.get('price') or price
                    }
                except Exception:
                    continue

            msg = {
                'market': 'Dex',
                'data_usdt': [],
                'data_spot': data_spot,
                'market_meta': market_meta,
                'ts': ts
            }
            try:
                if data_spot:
                    send_msg(msg)
                    logger.info("Dex collector: sent %d tokens", len(data_spot))
                else:
                    logger.info("Dex collector: nothing to send")
            except Exception:
                logger.exception("Dex collector send fail")

            elapsed = time.time() - start
            await asyncio.sleep(max(0.5, DEX_SLEEP - elapsed))


if __name__ == '__main__':
    try:
        asyncio.run(dex_collector_loop())
    except KeyboardInterrupt:
        pass
