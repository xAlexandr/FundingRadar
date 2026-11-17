# collectors/kucoin.py
import asyncio
import aiohttp
import time
import socket
import struct
import pickle
import os
import logging
from datetime import datetime

logger = logging.getLogger("kucoin_gateio")
logging.basicConfig(level=logging.INFO)

SOCKET_PATH = os.getenv('SOCKET_PATH', '/tmp/funding.sock')
SLEEP = float(os.getenv('COLLECTOR_SLEEP', '2.0'))
SLEEP_HUOBI = 8.0
SLEEP_ASTER = 2.0
# PROXY = os.getenv('proxy1')  # optional proxy (same name as other collectors)
# PROXY_OURBIT = os.getenv('proxy_ourbit')
PROXY = None
PROXY_OURBIT = None
PROXY_ASTER = os.getenv('proxy_ourbit', None)
PROXY_VPN = "socks5://127.0.0.1:2080"
# ===== Kucoin endpoints (as in your original file) =====
KU_FUT_CONTRACTS = 'https://api-futures.kucoin.com/api/v1/contracts/active'
KU_BULLET = 'https://api-futures.kucoin.com/api/v1/bullet-public'
KU_TICKERS = 'https://api-futures.kucoin.com/api/v1/allTickers'
KU_SPOT = 'https://api.kucoin.com/api/v1/market/allTickers'

# ===== Gateio endpoints (taken from your older gateio snippet) =====
GATEIO_FUT_CONTRACTS = 'https://api.gateio.ws/api/v4/futures/usdt/contracts'
GATEIO_FUT_TICKERS = 'https://api.gateio.ws/api/v4/futures/usdt/tickers'
GATEIO_SPOT_TICKERS = 'https://api.gateio.ws/api/v4/spot/tickers'

# ===== Bitget endpoints =====
BITGET_FUND_URL = 'https://api.bitget.com/api/v2/mix/market/current-fund-rate?productType=usdt-futures'
BITGET_TICKERS_URL = 'https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES'
BITGET_SPOT_URL = 'https://api.bitget.com/api/v2/spot/market/tickers'  # optional: для spot (если нужен)

# ===== Huobi endpoints =====
HUOBI_FUND_URL = 'https://api.hbdm.com/linear-swap-api/v1/swap_batch_funding_rate'
HUOBI_BATCH_MERGED = 'https://api.hbdm.com/v2/linear-swap-ex/market/detail/batch_merged'
HUOBI_INDEX = 'https://api.hbdm.com/linear-swap-api/v1/swap_index'
HUOBI_SPOT = 'https://api.huobi.pro/market/tickers'

# Ourbit endpoints
OURBIT_FUT_URL = 'https://futures.ourbit.com/api/v1/contract/ticker'
OURBIT_SPOT_URL = 'https://api.ourbit.com/api/v3/ticker/bookTicker'
OURBIT_FUND_URL = 'https://futures.ourbit.com/api/v1/contract/funding_rate/'
OURBIT_CONT_URL = 'https://futures.ourbit.com/api/v1/contract/detail'

ourbit_contract = {}

# Hyperliquid endpoint
HYPERLIQ_URL = 'https://api.hyperliquid.xyz/info'

# LBank endpoints
LBANK_FUT_URL = 'https://lbkperp.lbank.com/cfd/openApi/v1/pub/marketData?productGroup=SwapU'
LBANK_SPOT_URL = 'https://api.lbank.info/v2/supplement/ticker/price.do'

# interval / helper storage for LBank
lbank_interval = {}

# ===== Aster (futures + spot) =====
ASTER_FUT_BASE = 'https://fapi.asterdex.com'
ASTER_SPOT_BASE = 'https://sapi.asterdex.com'
ASTER_PREMIUM = f'{ASTER_FUT_BASE}/fapi/v1/premiumIndex'   # mark price + funding
ASTER_BOOKTICKER = f'{ASTER_FUT_BASE}/fapi/v1/ticker/bookTicker'  # best bid/ask
ASTER_24HR = f'{ASTER_FUT_BASE}/fapi/v1/ticker/24hr'  # 24h stats
ASTER_FUNDING = f'{ASTER_FUT_BASE}/fapi/v1/fundingInfo'  # funding info
ASTER_SPOT_24HR = f'{ASTER_SPOT_BASE}/api/v3/ticker/24hr'  # spot 24h ticker
# simple cache for ASTER 24hr: keep last successful response and timestamp
_aster_stats_cache = None
_aster_stats_ts = 0.0
_ASTER_24HR_TTL = 120  # seconds: only refetch ASTER_24HR once per minute

# helper -------------------------------------------------------------------
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
    logger.error("Collector: failed to send %s", msg.get('market'))

async def fetch_json(session, url, proxy=None, timeout=12, content_type=None):
    """
    Универсальный fetch:
      - если content_type задан — сначала пробуем r.json(content_type=content_type)
      - логируем 429 / HTTP ошибки и сетевые ошибки как WARNING (чтобы при INFO ты видел предупреждения)
      - возвращаем распаршенный JSON (dict/list) или None
    """
    try:
        async with session.get(url, proxy=proxy, timeout=timeout) as r:
            # логируем статусы >=400
            if r.status == 429:
                logger.warning(f"[429] Rate limit on {url}")
                try:
                    text = await r.text()
                    if text:
                        logger.debug(f"[429-body] {text[:400]}")
                except Exception:
                    pass
                return None

            if r.status >= 400:
                logger.warning(f"[HTTP {r.status}] Error fetching {url}")
                try:
                    text = await r.text()
                    if text:
                        logger.debug(f"[HTTP-body] {text[:400]}")
                except Exception:
                    pass
                return None

            # Попытка распарсить с указанным content_type (если задан)
            if content_type:
                try:
                    return await r.json(content_type=content_type)
                except Exception as e:
                    logger.debug("fetch_json: json(content_type=%s) failed for %s: %s", content_type, url, e)
                    # fallback: попробуем обычный json()
                    try:
                        return await r.json()
                    except Exception as e2:
                        logger.debug("fetch_json: fallback json() also failed for %s: %s", url, e2)
                        # как последний вариант попробуем text -> json.loads
                        try:
                            text = await r.text()
                            import json as _json
                            return _json.loads(text)
                        except Exception as e3:
                            logger.debug("fetch_json: text->json.loads failed for %s: %s", url, e3)
                            return None

            # если content_type не задан — нормальная ветка
            try:
                return await r.json()
            except Exception as e:
                logger.debug("fetch_json: r.json() failed for %s: %s", url, e)
                try:
                    text = await r.text()
                    import json as _json
                    return _json.loads(text)
                except Exception as e2:
                    logger.debug("fetch_json: text->json.loads failed for %s: %s", url, e2)
                    return None

    except asyncio.TimeoutError:
        logger.warning(f"[Timeout] fetch_json timeout for {url}")
        return None
    except aiohttp.ClientConnectorError as e:
        logger.warning(f"[ConnError] fetch_json connection error for {url}: {e}")
        return None
    except Exception as e:
        logger.warning(f"[Error] fetch_json failed {url}: {e}")
        return None

def _norm_sym(s):
    if not isinstance(s, str):
        return s
    return s.replace('_','').replace('-','').upper()

# ===== Kucoin collector (refactor of your kucoin.py) ======================
async def kucoin_collect_once(session, use_proxy_toggle=False):
    proxy = PROXY if use_proxy_toggle else None

    # try to get bullet token (best-effort) and contracts once (we still call contracts each loop here,
    # to keep logic equal to original file - it is cheap)
    token = None
    try:
        async with session.post(KU_BULLET, timeout=10) as r:
            j = await r.json()
            token = j.get('data', {}).get('token')
    except Exception:
        token = None

    # fetch concurrently: futures tickers, spot tickers, contracts
    fut_task = session.get(KU_TICKERS, proxy=proxy, timeout=10)
    spot_task = session.get(KU_SPOT, proxy=proxy, timeout=10)
    contracts_task = session.get(KU_FUT_CONTRACTS, proxy=proxy, timeout=10)

    responses = await asyncio.gather(fut_task, spot_task, contracts_task, return_exceptions=True)

    fut = spot = contracts = None
    try:
        if isinstance(responses[0], aiohttp.ClientResponse):
            fut = await responses[0].json()
        if isinstance(responses[1], aiohttp.ClientResponse):
            spot = await responses[1].json()
        if isinstance(responses[2], aiohttp.ClientResponse):
            contracts = await responses[2].json()
    except Exception as e:
        logger.debug("Kucoin gather parse error: %s", e)

    data_usdt = []
    market_meta = {}
    funding_rates = {}

    # parse contracts to map funding/index/mark
    if contracts:
        for it in contracts.get('data', []):
            try:
                s = it.get('symbol', '').replace('USDTM', 'USDT')
                if 'USDT' not in s:
                    continue
                # fundingFeeRate -> percent, markPrice, indexPrice
                fd = round(float(it.get('fundingFeeRate', 0)) * 100, 2)
                mark = float(it.get('markPrice') or 0)
                ind = float(it.get('indexPrice') or 0)
                volume24 = round(float(it.get('turnoverOf24h') or 0))
                funding_rates[s] = [fd, mark, ind, volume24]
            except Exception:
                continue

    # futures: KU_TICKERS /allTickers
    if fut:
        for it in fut.get('data', []):
            try:
                sym = it.get('symbol', '').replace('USDTM', 'USDT')
                if 'USDT' not in sym:
                    continue
                fd = 0.0; mark_pr = 0.0; ind_pr = 0.0
                if sym in funding_rates:
                    fd, mark_pr, ind_pr, volume24_usd = funding_rates[sym]
                bestAsk = it.get('bestAskPrice') or it.get('bestAsk') or 0
                bestBid = it.get('bestBidPrice') or it.get('bestBid') or 0
                try:
                    bestAsk = float(bestAsk)
                except:
                    bestAsk = 0.0
                try:
                    bestBid = float(bestBid)
                except:
                    bestBid = 0.0
                idx = round(((mark_pr / ind_pr) - 1) * 100, 2) if ind_pr else 0
                data_usdt.append([sym, fd, bestBid, 0, idx, 0, bestAsk, 0])
                # meta
                limits = None
                market_meta[sym] = {
                    'fundingInterval': 8,
                    'fee': 0.1,
                    'predict': '-',
                    'bestBid': bestBid,
                    'bestAsk': bestAsk,
                    'index_corr': idx,
                    'amount24': volume24_usd
                }
            except Exception:
                continue

    # spot
    data_spot = {}
    if spot:
        # Kucoin returns {data: {ticker: [...]}}
        tickers = None
        try:
            tickers = spot.get('data', {}).get('ticker', [])
        except Exception:
            tickers = None
        if tickers:
            for t in tickers:
                try:
                    sym = t.get('symbol', '').replace('-', '')
                    if 'USDT' not in sym:
                        continue
                    bid = float(t.get('buy') or 0)
                    ask = float(t.get('sell') or 0)
                    volume24h_spot = round(float(t.get('volValue') or 0))
                    data_spot[_norm_sym(sym)] = [_norm_sym(sym), bid, ask]

                    mm = market_meta.get(sym) or {}
                    mm.update({
                        'amount24_spot': volume24h_spot
                    })
                    market_meta[sym] = mm
                except Exception:
                    continue

    msg = {
        'market': 'Kucoin',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)
    logger.debug("Kucoin: sent %d futs / %d spots", len(data_usdt), len(data_spot))

async def kucoin_loop():
    use_toggle = False
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await kucoin_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                logger.exception("Kucoin collector error: %s", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP)

# ===== Gateio collector (based on your gateio snippet) =====================
async def gateio_collect_once(session, use_proxy_toggle=False):
    proxy = PROXY if use_proxy_toggle else None

    # fetch contracts, futures tickers, spot tickers concurrently
    fut_contracts_task = session.get(GATEIO_FUT_CONTRACTS, proxy=proxy, timeout=12)
    fut_tickers_task = session.get(GATEIO_FUT_TICKERS, proxy=proxy, timeout=12)
    spot_tickers_task = session.get(GATEIO_SPOT_TICKERS, proxy=proxy, timeout=12)

    responses = await asyncio.gather(fut_contracts_task, fut_tickers_task, spot_tickers_task, return_exceptions=True)

    contracts = futs = spot = None
    try:
        if isinstance(responses[0], aiohttp.ClientResponse):
            contracts = await responses[0].json()
        if isinstance(responses[1], aiohttp.ClientResponse):
            futs = await responses[1].json()
        if isinstance(responses[2], aiohttp.ClientResponse):
            spot = await responses[2].json()
    except Exception as e:
        logger.debug("Gateio gather parse error: %s", e)

    data_usdt = []
    market_meta = {}
    funding_map = {}

    # parse contracts -> funding_interval, funding_rate, mark/index
    if contracts:
        for i in contracts:
            try:
                # contract name in gateio may be like "BTC_USDT"
                name = i.get('name') or i.get('contract') or i.get('symbol') or ''
                # normalize to e.g. BTCUSDT
                if '_USDT' in name:
                    key = name.replace('_USDT', 'USDT')
                elif name.endswith('USDT'):
                    key = name.replace('_USDT', 'USDT')
                else:
                    key = name.replace('_', '').upper()
                if 'USDT' not in key:
                    continue
                fd = round((float(i.get('funding_rate', i.get('fundingRate', 0))) * 100), 2) if i.get('funding_rate') is not None or i.get('fundingRate') is not None else 0.0
                mark = float(i.get('mark_price') or i.get('markPrice') or 0)
                ind = float(i.get('index_price') or i.get('indexPrice') or 0)
                try:
                    interval_raw = i.get('funding_interval') or i.get('fundingInterval') or None
                    if interval_raw:
                        # gateio sometimes returns seconds -> hours
                        interval_hours = int(int(interval_raw) / 3600) if int(interval_raw) > 24 else int(interval_raw)
                    else:
                        interval_hours = 8
                except Exception:
                    interval_hours = 8
                funding_map[key] = (fd, mark, ind, interval_hours)
            except Exception:
                continue

    # parse futures tickers - build bestBid/bestAsk per contract
    # gateio futs response likely list of maps with 'contract','highest_bid','lowest_ask', etc.
    bestbids = {}
    if futs:
        for it in futs:
            try:
                contract_name = it.get('contract') or it.get('symbol') or ''
                if not contract_name:
                    continue
                sym = contract_name.replace('_USDT', 'USDT')
                if 'USDT' not in sym:
                    continue
                bestBid = it.get('highest_bid') or it.get('highestBid') or it.get('highest_bid') or 0
                bestAsk = it.get('lowest_ask') or it.get('lowestAsk') or it.get('lowest_ask') or 0
                volume24h_usdt = round(float(it.get('volume_24h_quote') or 0))

                try:
                    bestBid = float(bestBid)
                except:
                    bestBid = 0.0
                try:
                    bestAsk = float(bestAsk)
                except:
                    bestAsk = 0.0
                bestbids[sym] = (bestBid, bestAsk, volume24h_usdt)
            except Exception:
                continue

    # create data_usdt entries using funding_map and bestbids
    for sym, (bestBid, bestAsk, volume24h_usdt) in bestbids.items():
        try:
            if sym not in funding_map:
                # we still accept but with fd=0
                fd = 0.0; mark = 0.0; ind = 0.0; interval = 8
            else:
                fd, mark, ind, interval = funding_map[sym]
            idx = round(((mark / ind) - 1) * 100, 2) if ind else 0.0
            data_usdt.append([sym, fd, bestBid, 0, idx, 0, bestAsk, 0])
            market_meta[sym] = {
                'fundingInterval': interval,
                'fee': 0.05,
                'predict': '-',
                'bestBid': bestBid,
                'bestAsk': bestAsk,
                'index_corr': idx,
                'amount24': volume24h_usdt
            }
        except Exception:
            continue

    # parse spot tickers
    data_spot = {}
    if spot:
        for t in spot:
            try:
                # gateio spot ticker entry has 'currency_pair', 'highest_bid', 'lowest_ask' (or json structure)
                cp = t.get('currency_pair') or t.get('symbol') or t.get('id') or ''
                if not cp:
                    continue
                sym = cp.replace('_', '').replace('-', '').upper()
                if 'USDT' not in sym:
                    continue
                bid = float(t.get('highest_bid') or t.get('buy') or t.get('highestBid') or 0)
                ask = float(t.get('lowest_ask') or t.get('sell') or t.get('lowestAsk') or 0)
                volume24h_spot = round(float(t.get('quote_volume') or 0))
                data_spot[sym] = [sym, bid, ask]

                mm = market_meta.get(sym) or {}
                mm.update({
                    'amount24_spot': volume24h_spot
                })
                market_meta[sym] = mm

            except Exception:
                continue

    msg = {
        'market': 'Gateio',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)
    logger.debug("Gateio: sent %d futs / %d spots", len(data_usdt), len(data_spot))
    return len(data_usdt) > 0


async def create_gateio_session():
    connector = aiohttp.TCPConnector(
        ttl_dns_cache=600,
        keepalive_timeout=90,
        enable_cleanup_closed=True,
        limit=50,
    )

    timeout = aiohttp.ClientTimeout(
        total=30,
        connect=10,
        sock_read=20
    )

    return aiohttp.ClientSession(
        connector=connector,
        timeout=timeout
    )
# async def gateio_loop():
#     use_toggle = False
#     async with aiohttp.ClientSession() as session:
#         while True:
#             try:
#                 await gateio_collect_once(session, use_proxy_toggle=use_toggle)
#             except Exception as e:
#                 logger.exception("Gateio collector error: %s", e)
#             use_toggle = not use_toggle
#             await asyncio.sleep(SLEEP)

async def gateio_loop():
    use_toggle = False
    session = None
    recreate_every = 21600   # каждые 30 минут
    last_create = 0
    fail_count = 0

    while True:
        try:
            now = time.time()

            if session is None or session.closed or now - last_create > recreate_every:
                if session and not session.closed:
                    await session.close()

                session = await create_gateio_session()
                last_create = now
                logger.info("Gateio session recreated (timer)")

            ok = await gateio_collect_once(session, use_proxy_toggle=use_toggle)

            if ok:
                fail_count = 0
            else:
                fail_count += 1

            if fail_count >= 3:
                logger.warning("Gateio no data 3 times -> recreate")
                await session.close()
                session = await create_gateio_session()
                fail_count = 0

        except Exception as e:
            logger.warning(f"Gateio error: {e}")

            try:
                if session and not session.closed:
                    await session.close()
            except:
                pass

            session = await create_gateio_session()
            fail_count = 0

        use_toggle = not use_toggle
        await asyncio.sleep(SLEEP)
# ===== Bitget collector (HTTP only, no websockets) ======================
async def bitget_collect_once(session, use_proxy_toggle=False):
    """
    Простая реализация: получаем funding rates (funding + interval) и tickers (bestBid/bestAsk/mark/index).
    Формируем data_usdt, data_spot и market_meta аналогично другим collectors и отправляем msg.
    """
    proxy = PROXY if use_proxy_toggle else None

    # параллельно запрашиваем funding и тикеры (и опционально спот)
    fut_fund_task = session.get(BITGET_FUND_URL, proxy=proxy, timeout=12)
    fut_tickers_task = session.get(BITGET_TICKERS_URL, proxy=proxy, timeout=12)
    spot_task = session.get(BITGET_SPOT_URL, proxy=proxy, timeout=12)

    responses = await asyncio.gather(fut_fund_task, fut_tickers_task, spot_task, return_exceptions=True)

    fund_json = tickers_json = spot_json = None
    try:
        if isinstance(responses[0], aiohttp.ClientResponse):
            fund_json = await responses[0].json()
        if isinstance(responses[1], aiohttp.ClientResponse):
            tickers_json = await responses[1].json()
        if isinstance(responses[2], aiohttp.ClientResponse):
            spot_json = await responses[2].json()
    except Exception as e:
        logger.debug("Bitget gather parse error: %s", e)

    # maps
    funding_map = {}   # symbol -> (funding_percent, interval_hours)
    data_usdt = []
    market_meta = {}
    data_spot = {}

    # parse funding rates response
    # expected structure: {"code":"00000", "data":[ { "symbol":"BTCUSDT", "fundingRate":"0.0001", "fundingRateInterval":"8", ... }, ... ]}
    try:
        arr = fund_json.get('data') if isinstance(fund_json, dict) else None
        if isinstance(arr, list):
            for it in arr:
                try:
                    sym = _norm_sym(it.get('symbol') or '')
                    if 'USDT' not in sym:
                        continue
                    fr = it.get('fundingRate') or it.get('funding_rate') or '0'
                    try:
                        fr_val = float(fr) * 100.0
                    except:
                        fr_val = 0.0

                    funding_map[sym] = round(fr_val, 2)
                except Exception:
                    continue
    except Exception:
        pass

    # parse tickers (futures) — bestBid, bestAsk, markPrice, indexPrice, volume
    # expected tickers_json['data'] -> list of { "symbol":"BTCUSDT", "askPr":"...", "bidPr":"...", "markPrice":"...", "indexPrice":"...", "usdtVolume": "..."}
    try:
        arr = tickers_json.get('data') if isinstance(tickers_json, dict) else None
        if isinstance(arr, list):
            for it in arr:
                try:
                    sym = _norm_sym(it.get('symbol') or '')
                    if 'USDT' not in sym:
                        continue
                    # best ask/bid fields may be named askPr/bidPr or askPrice/bidPrice
                    bestAsk = it.get('askPr') or it.get('ask') or it.get('askPrice') or it.get('askPrice')
                    bestBid = it.get('bidPr') or it.get('bid') or it.get('bidPrice') or it.get('bidPrice')
                    interval_h = it.get('fundingRateInterval') or 8
                    try:
                        bestAsk = float(bestAsk)
                    except:
                        bestAsk = 0.0
                    try:
                        bestBid = float(bestBid)
                    except:
                        bestBid = 0.0
                    mark = it.get('markPrice') or it.get('mark_price') or 0
                    index = it.get('indexPrice') or it.get('index_price') or 0
                    try:
                        mark_f = float(mark)
                    except:
                        mark_f = 0.0
                    try:
                        index_f = float(index)
                    except:
                        index_f = 0.0
                    # compute index correction
                    idx = round(((mark_f / index_f) - 1) * 100, 2) if index_f else 0.0
                    # volume24: try usdtVolume or quoteVolume
                    vol24 = it.get('usdtVolume') or it.get('quoteVolume') or it.get('quoteVolume24h') or 0
                    try:
                        vol24f = round(float(vol24))
                    except:
                        vol24f = 0.0

                    # funding value and interval from funding_map if present
                    fd_val = funding_map.get(sym, 0.0)

                    # append data_usdt in the same layout as others
                    data_usdt.append([sym, fd_val, bestBid, 0, idx, 0, bestAsk, 0])

                    market_meta[sym] = {
                        'fundingInterval': interval_h,
                        'fee': 0.06,   # use approx fee (adjust if needed)
                        'predict': '-',
                        'bestBid': bestBid,
                        'bestAsk': bestAsk,
                        'index_corr': idx,
                        'amount24': vol24f
                    }
                except Exception:
                    continue
    except Exception:
        pass

    # parse spot tickers (optional) — many installations don't need it; but we'll try to parse for completeness
    try:
        arr = spot_json.get('data') if isinstance(spot_json, dict) else None
        # bitget spot structure may be {"data": [{"symbol":"BTCUSDT","bidPr": "...","askPr":"...", "quoteVolume":"..."} , ...]}
        if isinstance(arr, list):
            for t in arr:
                try:
                    sym = _norm_sym(t.get('symbol') or '')
                    if 'USDT' not in sym:
                        continue
                    bid = float(t.get('bidPr') or t.get('bid') or 0)
                    ask = float(t.get('askPr') or t.get('ask') or 0)
                    vol24 = t.get('quoteVolume') or t.get('usdtVolume') or 0
                    try:
                        vol24f = round(float(vol24))
                    except:
                        vol24f = 0.0
                    data_spot[sym] = [sym, bid, ask]
                    mm = market_meta.get(sym) or {}
                    mm.update({'amount24_spot': vol24f})
                    market_meta[sym] = mm
                except Exception:
                    continue
    except Exception:
        pass

    # build msg and send
    msg = {
        'market': 'Bitget',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)
    logger.debug("Bitget: sent %d futs / %d spots", len(data_usdt), len(data_spot))


async def bitget_loop():
    use_toggle = False
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await bitget_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                logger.exception("Bitget collector error: %s", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP)

# ===== Huobi collector (HTTP only, no websockets) ======================
async def huobi_collect_once(session, use_proxy_toggle=False):
    """
    Сборщик Huobi: получает funding rates, batch_merged (bid/ask/last) и index (index_price).
    Мы используем index_price из HUOBI_INDEX и для contract_price теперь используем bid (как ты просил).
    Формат выходных списков совпадает с другими collectors.
    """
    proxy = PROXY if use_proxy_toggle else None

    # параллельные запросы: funding, merged ticks, index, spot (spot опционально)
    # Для funding — HUOBI раньше требовал content_type='text/plain;charset=utf-8'
    fund_task = asyncio.create_task(fetch_json(session, HUOBI_FUND_URL, proxy=proxy, timeout=12,
                                               content_type='text/plain;charset=utf-8'))
    merged_task = asyncio.create_task(fetch_json(session, HUOBI_BATCH_MERGED, proxy=proxy, timeout=12))
    index_task = asyncio.create_task(fetch_json(session, HUOBI_INDEX, proxy=proxy, timeout=12))
    spot_task = asyncio.create_task(fetch_json(session, HUOBI_SPOT, proxy=proxy, timeout=12))

    fund_json, merged_json, index_json, spot_json = await asyncio.gather(
        fund_task, merged_task, index_task, spot_task, return_exceptions=False
    )

    # диагностические предупреждения если какой-то из ответов пустой (None)
    if fund_json is None:
        logger.warning("Huobi: funding API returned no data (fund_json is None)")
    if merged_json is None:
        logger.warning("Huobi: batch_merged returned no data (merged_json is None)")
    if index_json is None:
        logger.warning("Huobi: index API returned no data (index_json is None)")
    if spot_json is None:
        logger.debug("Huobi: spot API returned no data (this may be normal if not used)")

    # mappings and outputs
    funding_map = {}   # sym -> funding_percent (already *100) and optional interval if available
    index_map = {}     # sym -> index_price (float)
    data_usdt = []
    market_meta = {}
    data_spot = {}

    # --- parse funding rates (HUOBI_FUND_URL) ---
    # expected: {"status":"ok", "data":[{"contract_code":"KAS-USDT","funding_rate":...}, ...]}
    try:
        arr = fund_json.get('data') if isinstance(fund_json, dict) else None
        if isinstance(arr, list):
            for it in arr:
                try:
                    code = it.get('contract_code') or it.get('symbol') or ''
                    if not code:
                        continue
                    # normalize contract like KAS-USDT -> KASUSDT
                    sym = _norm_sym(code.replace('-USDT', 'USDT').replace('-', ''))
                    fr = it.get('funding_rate') or it.get('fundingRate') or 0
                    try:
                        fr_val = float(fr) * 100.0
                    except:
                        fr_val = 0.0
                    funding_map[sym] = round(fr_val, 2)
                except Exception:
                    continue
    except Exception:
        pass

    # --- parse index prices (HUOBI_INDEX) ---
    # expected: {"status":"ok","data":[{"index_price":..., "contract_code":"KAS-USDT"}, ...]}
    try:
        arr = index_json.get('data') if isinstance(index_json, dict) else None
        if isinstance(arr, list):
            for it in arr:
                try:
                    code = it.get('contract_code') or it.get('symbol') or ''
                    if not code:
                        continue
                    sym = _norm_sym(code.replace('-USDT', 'USDT').replace('-', ''))
                    idx_price = it.get('index_price') or it.get('indexPrice') or 0
                    try:
                        index_map[sym] = float(idx_price)
                    except:
                        index_map[sym] = 0.0
                except Exception:
                    continue
    except Exception:
        pass

    # --- parse batch_merged ticks (bid/ask/last). This gives bestBid/bestAsk ---
    # expected merged_json['ticks'] -> list of { 'contract_code': 'KAS-USDT', 'bid': [price, ...], 'ask': [price, ...], ... }
    try:
        ticks = merged_json.get('ticks') if isinstance(merged_json, dict) else None
        if isinstance(ticks, list):
            for t in ticks:
                try:
                    code = t.get('contract_code') or t.get('symbol') or ''
                    if not code:
                        continue
                    sym = _norm_sym(code.replace('-USDT', 'USDT').replace('-', ''))
                    # best bid/ask in batch_merged are usually arrays: bid[0], ask[0]
                    bid_val = None
                    ask_val = None
                    try:
                        bid_val = float(t.get('bid')[0]) if t.get('bid') and len(t.get('bid'))>0 else float(t.get('bid') or 0)
                    except Exception:
                        try:
                            bid_val = float(t.get('bid') or 0)
                        except:
                            bid_val = 0.0
                    try:
                        ask_val = float(t.get('ask')[0]) if t.get('ask') and len(t.get('ask'))>0 else float(t.get('ask') or 0)
                    except Exception:
                        try:
                            ask_val = float(t.get('ask') or 0)
                        except:
                            ask_val = 0.0

                    # index price (from index_map) if available
                    idx_price = index_map.get(sym, 0.0)

                    # compute index_corr: same logic as у других — (mark/index -1) *100.
                    # mark we don't have from batch_merged reliably; we will approximate using bid_val as 'mark' replacement
                    idx = 0.0
                    try:
                        if idx_price and idx_price != 0:
                            idx = round((( (bid_val or 0.0) / float(idx_price) ) - 1) * 100, 2)
                        else:
                            idx = 0.0
                    except Exception:
                        idx = 0.0

                    # funding value from funding_map if present
                    fd_val = funding_map.get(sym, 0.0)

                    # amount24/volume not directly available here; set 0 or leave to later enrichment
                    amount24 = round(float(t.get('vol', 0)))

                    # append in standard layout
                    data_usdt.append([sym, fd_val, bid_val or 0.0, 0, idx, 0, ask_val or 0.0, 0])

                    market_meta[sym] = {
                        'fundingInterval': 8,
                        'fee': 0.2,      # пример — поправь на нужное, если знаешь
                        'predict': '-',
                        'bestBid': bid_val or 0.0,
                        'bestAsk': ask_val or 0.0,
                        'index_corr': idx,
                        'index_price': idx_price,
                        'amount24': amount24
                    }
                except Exception:
                    continue
    except Exception:
        pass

    # --- parse spot tickers (HUOBI_SPOT) — опционально, добавляем amount24_spot и spot bids ---
    try:
        tickers = spot_json.get('data') if isinstance(spot_json, dict) else None
        if isinstance(tickers, list):
            for t in tickers:
                try:
                    sym = _norm_sym(t.get('symbol') or '')
                    if 'USDT' not in sym:
                        continue
                    bid = float(t.get('bid') or 0)
                    ask = float(t.get('ask') or 0)
                    vol = t.get('vol') or t.get('amount') or t.get('volValue') or 0
                    try:
                        volf = round(float(vol))
                    except:
                        volf = 0.0
                    data_spot[sym] = [sym, bid, ask]
                    mm = market_meta.get(sym) or {}
                    mm.update({'amount24_spot': volf})
                    market_meta[sym] = mm
                except Exception:
                    continue
    except Exception:
        pass

    # build and send msg
    msg = {
        'market': 'Huobi',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)
    logger.debug("Huobi: sent %d futs / %d spots", len(data_usdt), len(data_spot))

async def huobi_loop():
    use_toggle = False
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await huobi_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                logger.exception("Huobi collector error: %s", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP_HUOBI)

# ---------------- Ourbit ----------------
def compute_ourbit_meta(item, funding_info=None):
    meta = {}
    meta['fee'] = 0.02
    # funding: prefer funding_info from funding API, else item
    funding_val = None
    try:
        if funding_info is not None:
            funding_val = funding_info.get('fundingRate') or funding_info.get('fundingRate', None)
        if funding_val is None:
            funding_val = item.get('fundingRate') or item.get('funding') or 0
        meta['funding'] = round(float(funding_val) * 100, 2)
    except Exception:
        meta['funding'] = 0.0

    try:
        bestBid = item.get('bid1') or item.get('bestBid') or item.get('bid') or 0
        bestAsk = item.get('ask1') or item.get('bestAsk') or item.get('ask') or 0
        meta['bestBid'] = float(bestBid) if bestBid is not None else 0.0
        meta['bestAsk'] = float(bestAsk) if bestAsk is not None else 0.0
    except:
        meta['bestBid'] = 0.0; meta['bestAsk'] = 0.0

    try:
        meta['index_corr'] = round(((float(item.get('fairPrice') or 1) / float(item.get('indexPrice') or 1)) - 1) * 100, 1)
    except:
        meta['index_corr'] = 0.0

    # fundingInterval: prefer collectCycle or nextSettleTime from funding_info
    fi = 8
    try:
        if funding_info:
            cc = funding_info.get('collectCycle')
            if cc:
                try:
                    fi = int(cc)
                except:
                    fi = 8
            else:
                nft = funding_info.get('nextSettleTime') or funding_info.get('nextSettleTimeMillis') or funding_info.get('timestamp')
                if nft:
                    try:
                        fundingTime = int(int(nft) / 1000)
                        hourTime = int(datetime.fromtimestamp(int(fundingTime)).hour)
                        if hourTime in (3, 11, 19):
                            fi = 8
                        elif hourTime in (7, 15, 23):
                            fi = 4
                        elif hourTime in (5, 13, 21):
                            fi = 2
                        else:
                            fi = 1
                    except:
                        fi = 8
    except:
        fi = 8
    meta['fundingInterval'] = fi
    meta['predict'] = '-'

    try:
        meta['amount24'] = round(float(item.get('amount24')),1)
    except:
        meta['amount24'] = 0.0
    return meta

async def ourbit_collect_limits():
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(OURBIT_CONT_URL, proxy=PROXY_OURBIT) as mc:
                    contract = await mc.json()
                    for ct in contract.get('data', []):
                        s = ct.get('symbol').replace('_USDT','USDT')
                        if 'USDT' in s:
                            limit_max_vol = ct.get('limitMaxVol', 0)
                            contract_size = ct.get('contractSize', 0)
                            ourbit_contract[s] = [limit_max_vol, contract_size]
            except:
                pass
            await asyncio.sleep(30)

async def ourbit_collect_once(session, use_proxy_toggle=False):
    proxy = PROXY if use_proxy_toggle else None
   # proxy = PROXY_OURBIT
    fut_resp, fund_resp, spot_resp = await asyncio.gather(
        fetch_json(session, OURBIT_FUT_URL, proxy=proxy, timeout=12),
        fetch_json(session, OURBIT_FUND_URL, proxy=proxy, timeout=12),
        fetch_json(session, OURBIT_SPOT_URL, proxy=proxy, timeout=12),
    )

    fut = fut_resp
    fund = fund_resp
    spot = spot_resp

    # build funding map from fund API (normalize symbol -> e.g. BTC_USDT -> BTCUSDT)
    funding_map = {}
    try:
        if isinstance(fund, dict):
            for elem in fund.get('data', []) or []:
                try:
                    sym_raw = elem.get('symbol')
                    if not sym_raw:
                        continue
                    sym_key = sym_raw.replace('_USDT','USDT')
                    funding_map[sym_key] = elem
                except Exception:
                    continue
    except:
        pass

    data_usdt = []; market_meta = {}; data_spot = {}

    if fut:
        items = fut.get('data') if isinstance(fut, dict) and fut.get('data') is not None else fut
        if items:
            for it in items:
                try:
                    sym = it.get('symbol')
                    if not sym:
                        continue
                    # normalise symbol like BTC_USDT -> BTCUSDT
                    if '_USDT' in sym:
                        sym = sym.replace('_USDT', 'USDT')
                    if not sym or 'USDT' not in sym:
                        continue
                    funding_info = funding_map.get(sym)
                    meta = compute_ourbit_meta(it, funding_info=funding_info)
                    bid = meta.get('bestBid', 0.0); ask = meta.get('bestAsk', 0.0)
                    funding = meta.get('funding', 0.0); idx = meta.get('index_corr', 0.0)
                    data_usdt.append([sym, funding, bid, 0, idx, 0, ask, 0])
                    ourbit_cont = ourbit_contract.get(sym)
                    limits, contract_size = ourbit_cont
                    limits_coin = float(contract_size) * float(limits)
                    limits_usdt = round(limits_coin * ask, 1)
                    market_meta[sym] = {
                        'fundingInterval': meta.get('fundingInterval'),
                        'fee': meta.get('fee'),
                        'predict': meta.get('predict'),
                        'bestBid': bid,
                        'bestAsk': ask,
                        'index_corr': idx,
                        'amount24': meta.get('amount24'),
                        'limits_usdt': limits_usdt,
                    }
                except Exception:
                    pass
                  #  logger.exception("OURBIT EXCEPTION!")

    if spot:
        items = spot if isinstance(spot, list) else (spot.get('data') if isinstance(spot, dict) else None)
        if items:
            for t in items:
                try:
                    sym = t.get('symbol')
                    if not sym or 'USDT' not in sym:
                        continue
                    # mexc spot often is like BTCUSDT
                    sym = sym.replace('_USDT','USDT').replace('-','').replace('_','').upper()
                    bid = float(t.get('bidPrice') or t.get('bid') or 0)
                    ask = float(t.get('askPrice') or t.get('ask') or 0)
                    data_spot[sym] = [sym, bid, ask]
                except Exception:
                    continue

    msg = {
        'market': 'Ourbit',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
   # logger.info(f"ourbit msg: {msg}")
    send_msg(msg)

async def ourbit_loop():
    use_toggle = False
    asyncio.create_task(ourbit_collect_limits())
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await ourbit_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                print("Ourbit collector error:", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP)

async def hyperliquid_collect_once(session, use_proxy_toggle=False):
    """
    Hyperliquid collector (futures only).
    Запрашивает POST HYPERLIQ_URL с payload {"type": "metaAndAssetCtxs"} и парсит ответ.
    Формат вывода совместим с остальными collectors:
      data_usdt: [sym, funding_pct, bestBid, 0, index_corr, 0, bestAsk, 0]
      market_meta contains 'fundingInterval','fee','bestBid','bestAsk','index_corr','amount24'
    """
    proxy = PROXY if use_proxy_toggle else None

    data_usdt = []
    market_meta = {}

    payload = {"type": "metaAndAssetCtxs"}

    try:
        # Hyperliquid expects POST JSON
        async with session.post(HYPERLIQ_URL, json=payload, proxy=proxy, timeout=12) as resp:
            if resp.status != 200:
                logger.warning("Hyperliquid: non-200 status %s", resp.status)
                hyper_json = None
            else:
                hyper_json = await resp.json()
    except Exception as e:
        logger.debug("Hyperliquid fetch error: %s", e)
        hyper_json = None

    # expected structure (old code): data[0] -> universe, data[1] -> asset_ctxs
    try:
        if isinstance(hyper_json, list) and len(hyper_json) >= 2:
            universe = hyper_json[0].get('universe', []) if isinstance(hyper_json[0], dict) else []
            asset_ctxs = hyper_json[1] if isinstance(hyper_json[1], list) else hyper_json[1].get('asset_ctxs', [])
        else:
            universe = []
            asset_ctxs = []
    except Exception:
        universe = []
        asset_ctxs = []

    # iterate asset contexts and universe in parallel (old logic used index-based mapping)
    for idx, asset in enumerate(asset_ctxs):
        try:
            # symbol from universe entry if available, else try name in asset
            symbol = None
            if idx < len(universe) and isinstance(universe[idx], dict):
                # universe[idx]['name'] + 'USDT' in old code
                name = universe[idx].get('name')
                if name:
                    symbol = f"{name}USDT"
            # fallback: asset might contain symbol-like field
            if not symbol:
                # try common fields
                symbol = asset.get('symbol') or asset.get('name') or ''
                if symbol and not symbol.upper().endswith('USDT'):
                    symbol = f"{symbol}USDT"
                symbol = symbol.replace('-', '').replace('_', '').upper()

            if not symbol or 'USDT' not in symbol:
                continue

            # funding (asset.get('funding') is fractional -> *100)
            try:
                funding_rate = float(asset.get('funding', 0.0)) * 100.0
            except Exception:
                funding_rate = 0.0

            # midPx used as bestBid/bestAsk in old code
            mid_px = asset.get('midPx', None)
            if mid_px is None:
                # try other possible fields
                mid_px = asset.get('mid', asset.get('mid_price', 0))
            try:
                mid_px_f = float(mid_px)
            except Exception:
                mid_px_f = 0.0

            bid1 = mid_px_f
            ask1 = mid_px_f

            # mark and oracle (index) prices -> index_corr
            try:
                mark_price = float(asset.get('markPx', 0.0))
            except:
                mark_price = 0.0
            try:
                oracle_price = float(asset.get('oraclePx', 0.0))
            except:
                oracle_price = 0.0

            try:
                index_corr = round((mark_price / oracle_price - 1) * 100, 2) if oracle_price else 0.0
            except:
                index_corr = 0.0

            # volume24 not provided in old hyperliquid code -> leave 0
            amount24 = 0.0

            # append in standard layout
            data_usdt.append([symbol, round(funding_rate, 2), bid1, 0, index_corr, 0, ask1, 0])

            market_meta[symbol] = {
                'fundingInterval': 8,    # no timing info via this endpoint -> default 8
                'fee': 0.05,             # примерная комиссия (отредактируй при необходимости)
                'predict': '-',
                'bestBid': bid1,
                'bestAsk': ask1,
                'index_corr': index_corr,
                'amount24': amount24
            }

        except Exception as e:
            logger.debug("Hyperliquid parse error for idx %s: %s", idx, e)
            continue

    # send message (no spot)
    msg = {
        'market': 'Hyperliquid',
        'data_usdt': data_usdt,
        'data_spot': {},   # not used
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)
    logger.debug("Hyperliquid: sent %d futs", len(data_usdt))

async def hyperliquid_loop():
    use_toggle = False
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await hyperliquid_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                logger.exception("Hyperliquid collector error: %s", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP)

async def lbank_collect_once(session, use_proxy_toggle=False):
    """
    LBank collector:
      - futures: LBANK_FUT_URL -> list in response['data']
        fields used: symbol, fundingRate, lastPrice, markedPrice, underlyingPrice, volume, positionFeeTime
      - spot: LBANK_SPOT_URL -> response['data'] with entries containing 'symbol' like 'btc_usdt' and 'price'
    Output format matches other collectors:
      data_usdt entries: [sym, funding%, bestBid, 0, index_corr, 0, bestAsk, 0]
      market_meta contains 'fundingInterval','fee','bestBid','bestAsk','index_corr','amount24'
    """
    proxy = PROXY if use_proxy_toggle else None

    fut_json = await fetch_json(session, LBANK_FUT_URL, proxy=proxy, timeout=12)
    spot_json = await fetch_json(session, LBANK_SPOT_URL, proxy=proxy, timeout=12)

    data_usdt = []
    data_spot = {}
    market_meta = {}

    # --- futures ---
    try:
        arr = fut_json.get('data') if isinstance(fut_json, dict) else None
        if isinstance(arr, list):
            for it in arr:
                try:
                    # old code filtered by 'USDT' in symbol and volume != "0"
                    sym = it.get('symbol') or ''
                    if not sym or 'USDT' not in sym:
                        continue
                    vol = it.get('volume') or it.get('vol') or 0
                    # skip zero-volume contracts like in old logic
                    try:
                        if isinstance(vol, str) and vol.strip() == "0":
                            continue
                        if float(vol) == 0:
                            continue
                    except Exception:
                        # if can't parse volume — continue (do not skip)
                        pass

                    # funding
                    fr = it.get('fundingRate') or it.get('funding') or 0
                    try:
                        fr_val = round(float(fr) * 100.0, 2)
                    except:
                        fr_val = 0.0

                    # price fields
                    try:
                        last_price = float(it.get('lastPrice') or it.get('last_price') or 0.0)
                    except:
                        last_price = 0.0
                    try:
                        marked = float(it.get('markedPrice') or it.get('marked_price') or 0.0)
                    except:
                        marked = 0.0
                    try:
                        underlying = float(it.get('underlyingPrice') or it.get('underlying_price') or 0.0)
                    except:
                        underlying = 0.0

                    # index_corr (marked / underlying -1) *100
                    try:
                        idx_corr = round(((marked / underlying) - 1) * 100, 2) if underlying else 0.0
                    except:
                        idx_corr = 0.0

                    # funding interval: positionFeeTime is in seconds in old code -> convert to hours
                    try:
                        pos_fee_time = it.get('positionFeeTime')  # may be int/str
                        if pos_fee_time is not None:
                            pos_ft = int(pos_fee_time)
                            funding_interval_h = pos_ft / 3600.0
                            # keep integer-ish where possible
                            try:
                                funding_interval_h = int(funding_interval_h)
                            except:
                                pass
                        else:
                            funding_interval_h = 8
                    except:
                        funding_interval_h = 8

                    # amount24 try from volume or other
                    try:
                        amount24 = round(float(it.get('turnover') or it.get('volume') or 0))
                    except:
                        amount24 = 0.0

                    # append using last_price as bestBid/bestAsk (old code used lastPrice for both)
                    bid = last_price
                    ask = last_price

                    data_usdt.append([sym, fr_val, bid, 0, idx_corr, 0, ask, 0])

                    market_meta[sym] = {
                        'fundingInterval': funding_interval_h,
                        'fee': 0.06,   # примерная комиссия — поправь при необходимости
                        'predict': '-',
                        'bestBid': bid,
                        'bestAsk': ask,
                        'index_corr': idx_corr,
                        'amount24': amount24
                    }

                    # keep interval map (old class stored it separately)
                    try:
                        pft = it.get('positionFeeTime')
                        if pft is not None:
                            lbank_interval[sym] = int(pft)
                    except Exception:
                        pass

                except Exception:
                    continue
    except Exception:
        pass

    # --- spot ---
    try:
        # old LBank spot endpoint returns {'data': [ { 'symbol': 'btc_usdt', 'price': '...' }, ... ]}
        arr = spot_json.get('data') if isinstance(spot_json, dict) else None
        if isinstance(arr, list):
            for it in arr:
                try:
                    raw = it.get('symbol') or ''
                    if not raw:
                        continue
                    if 'usdt' not in raw.lower():
                        continue
                    # convert 'btc_usdt' -> 'BTCUSDT'
                    base = raw.split('_')[0].upper()
                    sym = f"{base}USDT"
                    price = it.get('price') or it.get('lastPrice') or it.get('price_usd') or 0
                    try:
                        p = float(price)
                    except:
                        p = 0.0

                    data_spot[sym] = [sym, p, p]

                    mm = market_meta.get(sym) or {}
                    # amount24_spot not provided by this endpoint (old code used price only) -> 0
                    mm.update({'amount24_spot': 0.0})
                    market_meta[sym] = mm
                except Exception:
                    continue
    except Exception:
        pass

    # send message
    msg = {
        'market': 'LBank',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)
    logger.debug("LBank: sent %d futs / %d spots", len(data_usdt), len(data_spot))

async def lbank_loop():
    use_toggle = False
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await lbank_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                logger.exception("LBank collector error: %s", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP)


async def aster_collect_once(session, use_proxy_toggle=False):
    """
    Collect Aster futures market data (futures only), using:
      - ASTER_PREMIUM   -> mark price + fallback funding
      - ASTER_BOOKTICKER-> best bid/ask
      - ASTER_24HR      -> volume/24h  (fetch only once per minute; reuse last if not time yet)
      - ASTER_FUNDING   -> fundingInfo (preferred)

    Minimal change: ASTER_24HR fetched at most once per minute; old value reused until a new successful fetch.
    """
    global _aster_stats_cache, _aster_stats_ts
    proxy = PROXY_ASTER if use_proxy_toggle else None

    now_ts = time.time()
    need_stats_fetch = (now_ts - _aster_stats_ts) >= _ASTER_24HR_TTL or _aster_stats_cache is None

    # fetch premium/book/funding in parallel as usual
    premium_task = session.get(ASTER_PREMIUM, proxy=proxy, timeout=10)
    book_task = session.get(ASTER_BOOKTICKER, proxy=proxy, timeout=10)
    fund_task = session.get(ASTER_FUNDING, proxy=proxy, timeout=10)

    # start the three tasks and await them together
    responses = await asyncio.gather(premium_task, book_task, fund_task, return_exceptions=True)

    premium_json = book_json = fund_json = None
    try:
        if isinstance(responses[0], aiohttp.ClientResponse):
            premium_json = await responses[0].json()
    except Exception:
        premium_json = None
    try:
        if isinstance(responses[1], aiohttp.ClientResponse):
            book_json = await responses[1].json()
    except Exception:
        book_json = None
    try:
        if isinstance(responses[2], aiohttp.ClientResponse):
            fund_json = await responses[2].json()
    except Exception:
        fund_json = None

    # Handle ASTER_24HR: fetch only if needed; otherwise reuse cached response
    stats_json = None
    if need_stats_fetch:
        try:
            stats_json = await fetch_json(session, ASTER_24HR, proxy=proxy, timeout=12)
            # only update cache on successful parse (non-None)
            if stats_json is not None:
                _aster_stats_cache = stats_json
                _aster_stats_ts = time.time()
            else:
                # if fetch failed, fall back to previous cache (if any)
                stats_json = _aster_stats_cache
        except Exception:
            # on any error fallback to cached
            stats_json = _aster_stats_cache
    else:
        # reuse last good cached response (could be None if never fetched successfully)
        stats_json = _aster_stats_cache

    # helper to convert possible envelopes to lists (unchanged)
    def _to_list(maybe):
        if isinstance(maybe, list):
            return maybe
        if isinstance(maybe, dict):
            for k in ('data', 'result', 'rows', 'list'):
                v = maybe.get(k)
                if isinstance(v, list):
                    return v
            return []
        return []

    premium_list = _to_list(premium_json)
    book_list = _to_list(book_json)
    stats_list = _to_list(stats_json)
    fund_list = _to_list(fund_json)

    # rest of function unchanged (build funding_map, premium_map, book_map, stats_map, assemble data)
    funding_map = {}
    for it in fund_list:
        try:
            raw_sym = it.get('symbol') or it.get('pair') or it.get('s') or ''
            sym = _norm_sym(raw_sym)
            if not sym or 'USDT' not in sym:
                continue
            interval_h = None
            try:
                fih = it.get('fundingIntervalHours')
                if fih is None:
                    fih = it.get('fundingInterval') or it.get('funding_interval') or it.get('fundingRateInterval')
                if fih is not None:
                    interval_h = int(fih)
                else:
                    interval_h = 8
            except Exception:
                interval_h = 8
            funding_map[sym] = interval_h
        except Exception:
            continue

    premium_map = {}
    for it in premium_list:
        try:
            raw_sym = it.get('symbol') or it.get('pair') or it.get('s') or ''
            sym = _norm_sym(raw_sym)
            if not sym or 'USDT' not in sym:
                continue
            fr = None
            for k in ('lastFundingRate', 'fundingRate', 'funding'):
                if it.get(k) is not None:
                    fr = it.get(k)
                    break
            try:
                fr_val = float(fr) * 100.0 if fr is not None else 0.0
            except:
                fr_val = 0.0
            try:
                mark = float(it.get('markPrice') or it.get('mark') or 0.0)
            except:
                mark = 0.0
            try:
                index_p = float(it.get('indexPrice') or it.get('index') or 0.0)
            except:
                index_p = 0.0
            next_f = it.get('nextFundingTime') or it.get('nextFundingTimeMillis') or None
            premium_map[sym] = (round(fr_val, 4) if fr_val else round(fr_val, 2), mark, index_p, next_f)
        except Exception:
            continue

    book_map = {}
    for it in book_list:
        try:
            raw_sym = it.get('symbol') or it.get('s') or it.get('pair') or ''
            sym = _norm_sym(raw_sym)
            if not sym or 'USDT' not in sym:
                continue
            bid = it.get('bidPrice') or it.get('bid') or it.get('b') or 0
            ask = it.get('askPrice') or it.get('ask') or it.get('a') or 0
            try:
                bid_f = float(bid)
            except:
                bid_f = 0.0
            try:
                ask_f = float(ask)
            except:
                ask_f = 0.0
            book_map[sym] = (bid_f, ask_f)
        except Exception:
            continue

    stats_map = {}
    for it in stats_list:
        try:
            raw_sym = it.get('symbol') or it.get('s') or it.get('pair') or ''
            sym = _norm_sym(raw_sym)
            if not sym or 'USDT' not in sym:
                continue
            vol = it.get('quoteVolume') or it.get('quoteVol') or it.get('usdtVolume') or it.get('volume') or it.get('vol') or 0
            try:
                volf = round(float(vol))
            except:
                volf = 0.0
            stats_map[sym] = volf
        except Exception:
            continue

    data_usdt = []
    market_meta = {}
    all_syms = set(list(funding_map.keys()) + list(premium_map.keys()) + list(book_map.keys()) + list(stats_map.keys()))
    for sym in all_syms:
        try:
            if sym in funding_map:
                interval_h = funding_map[sym]
            else:
                interval_h = 8
            if sym in premium_map:
                pm = premium_map.get(sym, (0.0, 0.0, 0.0, None))
                fd = pm[0]
            bid, ask = book_map.get(sym, (0.0, 0.0))
            vol24 = stats_map.get(sym, 0.0)
            mark = premium_map.get(sym, (0,0,0, None))[1] or 0.0
            index_p = premium_map.get(sym, (0,0,0, None))[2] or 0.0
            try:
                idx_corr = round(((mark / index_p) - 1) * 100, 2) if index_p else 0.0
            except Exception:
                idx_corr = 0.0
            data_usdt.append([sym, fd, bid or 0.0, 0, idx_corr, 0, ask or 0.0, 0])
            market_meta[sym] = {
                'fundingInterval': interval_h,
                'fee': 0.035,
                'predict': '-',
                'bestBid': bid or 0.0,
                'bestAsk': ask or 0.0,
                'index_corr': idx_corr,
                'amount24': vol24
            }
        except Exception:
            continue

    # --- Fetch spot data ---
    data_spot = {}
    try:
        spot_json = await fetch_json(session, ASTER_SPOT_24HR, proxy=proxy, timeout=12)
        if spot_json and isinstance(spot_json, list):
            for item in spot_json:
                try:
                    raw_sym = item.get('symbol', '')
                    if not raw_sym or not raw_sym.endswith('USDT'):
                        continue
                    # Skip prediction tokens
                    if 'UP_DOWN' in raw_sym or 'NUSDT' in raw_sym:
                        continue
                    sym = _norm_sym(raw_sym)
                    bid = float(item.get('bidPrice', 0) or 0)
                    ask = float(item.get('askPrice', 0) or 0)
                    vol = float(item.get('quoteVolume', 0) or 0)
                    if bid <= 0 or ask <= 0:
                        continue
                    data_spot[sym] = [sym, bid, ask]
                    # Add to market_meta for amount24_spot
                    market_meta[sym] = {
                        **market_meta.get(sym, {}),
                        'amount24_spot': round(vol, 2),
                    }
                except Exception:
                    continue
    except Exception as e:
        logger.warning("Aster spot fetch error: %s", e)

    msg = {
        'market': 'Aster',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }

    send_msg(msg)
    logger.debug("Aster: sent %d futs, %d spot", len(data_usdt), len(data_spot))



async def aster_loop():
    use_toggle = True
    async with aiohttp.ClientSession() as session, aiohttp.ClientSession() as session_proxy:
        while True:
            try:
                sess = session_proxy if use_toggle else session
                await aster_collect_once(sess, use_proxy_toggle=use_toggle)
            except Exception as e:
                logger.exception("Aster collector error: %s", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP_ASTER)

# main ---------------------------------------------------------------------
async def main():
    # run Kucoin and Gateio collectors concurrently (can add more)
    await asyncio.gather(
        kucoin_loop(),
        gateio_loop(),
        bitget_loop(),
        huobi_loop(),
        ourbit_loop(),
        hyperliquid_loop(),
        lbank_loop(),
        aster_loop(),
    )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
