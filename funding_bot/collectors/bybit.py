# collectors/bybit.py
import asyncio
import aiohttp
import time
import socket
import struct
import pickle
import gzip
import os
from datetime import datetime
import logging
import json

logger = logging.getLogger("bybit_mexc")
logging.basicConfig(level=logging.INFO)

SOCKET_PATH = os.getenv('SOCKET_PATH', '/tmp/funding.sock')
SLEEP = float(os.getenv('COLLECTOR_SLEEP', '2.0'))
SLEEP_MEXC = 4.0
# PROXY = os.getenv("proxy1")  # опционально прокси
# PROXY_BITMART = os.getenv("proxy_ourbit")
PROXY = None
PROXY_BITMART = None
#PROXY_XT = "socks5://127.0.0.1:2080"
PROXY_VPN = "socks5://127.0.0.1:2080"

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
        except Exception:
            time.sleep(0.05)
    print("Collector: failed to send", msg.get('market'))

# Bybit endpoints
BYBIT_FUT_URL = 'https://api.bybit.com/v5/market/tickers?category=linear'
BYBIT_SPOT_URL = 'https://api.bybit.com/v5/market/tickers?category=spot'

# Mexc endpoints
MEXC_FUT_URL = 'https://contract.mexc.com/api/v1/contract/ticker'
MEXC_SPOT_URL = 'https://api.mexc.com/api/v3/ticker/bookTicker'
MEXC_FUND_URL = 'https://contract.mexc.com/api/v1/contract/funding_rate/'
MEXC_CONT_URL = 'https://contract.mexc.com/api/v1/contract/detail'

mexc_contract = {}

# OKX endpoints
OKX_FUND_URL = 'https://www.okx.com/api/v5/public/funding-rate?instId=ANY'
OKX_TICKERS_URL = 'https://www.okx.com/api/v5/market/tickers?instType=SWAP'
OKX_SPOT_URL = 'https://www.okx.com/api/v5/market/tickers?instType=SPOT'
OKX_MARK_URL = 'https://www.okx.com/api/v5/public/mark-price?instType=SWAP'
OKX_INDEX_URL = 'https://www.okx.com/api/v5/market/index-tickers?quoteCcy=USDT'

# Binance endpoints
BINANCE_PREMIUM = 'https://fapi.binance.com/fapi/v1/premiumIndex'
BINANCE_FUT_BOOK = 'https://fapi.binance.com/fapi/v1/ticker/bookTicker'
BINANCE_SPOT_BOOK = 'https://api.binance.com/api/v3/ticker/bookTicker'

# BingX endpoints
BINGX_PREMIUM = 'https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex'
BINGX_TICKER_SWAP = 'https://open-api.bingx.com/openApi/swap/v2/quote/ticker'
BINGX_SPOT_24H = 'https://open-api.bingx.com/openApi/spot/v1/ticker/24hr'

# BitMart endpoints
BITMART_CONTRACTS = 'https://api-cloud-v2.bitmart.com/contract/public/details'
BITMART_SPOT = 'https://api-cloud.bitmart.com/spot/quotation/v3/tickers'
BITMART_WS = 'wss://openapi-ws-v2.bitmart.com'

# runtime storage for WS-updated best bids/asks
bitmart_funding_data = {}          # symbol -> {'bestBid': float, 'bestAsk': float}
bitmart_lock = asyncio.Lock()      # to protect bitmart_funding_data
# Helper fetch with proxy + safe return None on error

# ===== XT endpoints =====
XT_FUT_CONTRACTS_URL = 'https://fapi.xt.com/future/market/v1/public/cg/contracts'
XT_SPOT_TICKER_URL = 'https://sapi.xt.com/v4/public/ticker'


# Глобальные хранилища для CoinEx (защищены блокировкой)
coinex_ticker_data = {}   # symbol -> {'bestBid': float, 'bestAsk': float}
coinex_index_data = {}    # symbol -> {'markPrice': float, 'indexPrice': float}
coinex_spot_data = {}     # symbol -> {'bestBid': float, 'bestAsk': float}
coinex_funding_data = {}  # symbol -> {'latest_funding_rate': float, 'next_funding_rate': float, 'next_funding_time': int}
coinex_spot_symbols = []  # список спотовых символов для подписки
coinex_lock = asyncio.Lock()
# CoinEx endpoints
COINEX_FUT_TICKER_URL = 'https://api.coinex.com/v2/futures/ticker'


# ===== WEEX collector (v3 API) =============================================

# Фьючерсные эндпоинты WEEX (capi/v3)
WEEX_FUT_TICKER_URL = 'https://api-contract.weex.com/capi/v3/market/ticker/24hr'  # 24h статистика
WEEX_FUNDING_URL = 'https://api-contract.weex.com/capi/v3/market/premiumIndex'    # текущая ставка + mark/index
WEEX_BOOK_URL = 'https://api-contract.weex.com/capi/v3/market/ticker/bookTicker'  # лучший bid/ask
WEEX_EXCHANGE_INFO_URL = 'https://api-contract.weex.com/capi/v3/market/exchangeInfo'  # информация о контрактах

# Спотовые эндпоинты WEEX (api/v3)
WEEX_SPOT_BOOK_URL = 'https://api-spot.weex.com/api/v3/market/ticker/bookTicker'  # лучший bid/ask для спота
WEEX_SPOT_24HR_URL = 'https://api-spot.weex.com/api/v3/market/ticker/24hr'        # 24h статистика для спота

# Глобальное хранилище для лимитов контрактов WEEX
weex_contract_limits = {}

# ===== Phemex collector =====================================================

# Phemex endpoints
PHEMEX_FUT_TICKER_URL = 'https://api.phemex.com/md/v3/ticker/24hr/all'
PHEMEX_SPOT_TICKER_URL = 'https://api.phemex.com/md/v3/spot/ticker/24hr/all'
PHEMEX_REAL_FUNDING_URL = 'https://api.phemex.com/contract-biz/public/real-funding-rates'  # без symbol → все символы
PHEMEX_PRODUCTS_URL = 'https://api.phemex.com/public/products'

# Глобальный словарь для хранения priceScale спотовых символов
phemex_spot_scales = {}
phemex_scales_lock = asyncio.Lock()  # на случай параллельного доступа

# Binance Alpha endpoint (spot only)
BINANCE_ALPHA_URL = 'https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list'

async def fetch_json(session, url, proxy=None, timeout=12):
    try:
        async with session.get(url, proxy=proxy, timeout=timeout) as r:
            # Если сервер вернул 429 Too Many Requests
            if r.status == 429:
                logger.warning(f"[429] Rate limit on {url}")
                # читаем тело для отладки, если оно есть
                try:
                    text = await r.text()
                    if text:
                        logger.debug(f"[429-body] {text[:200]}")
                except Exception:
                    pass
                return None

            # другие неуспешные статусы — 4xx или 5xx
            if r.status >= 400:
                logger.warning(f"[HTTP {r.status}] Error fetching {url}")
                try:
                    text = await r.text()
                    if text:
                        logger.debug(f"[HTTP-body] {text[:200]}")
                except Exception:
                    pass
                return None

            # нормальный ответ
            return await r.json()
    except asyncio.TimeoutError:
        logger.warning(f"[Timeout] fetch_json timeout for {url}")
        return None
    except aiohttp.ClientConnectorError as e:
        logger.warning(f"[ConnError] fetch_json connection error for {url}: {e}")
        return None
    except Exception as e:
        logger.warning(f"[Error] fetch_json failed {url}: {e}")
        return None


# ---------------- Bybit ----------------
def compute_bybit_meta(item):
    meta = {}
    meta['fee'] = 0.1
    # funding keep more precision to avoid rounding to 0
    try:
        fr = float(item.get('fundingRate', 0) or 0)
        meta['funding'] = round(fr * 100, 2)
    except:
        meta['funding'] = 0.0
    try:
        meta['bestBid'] = float(item.get('bid1Price') or 0)
        meta['bestAsk'] = float(item.get('ask1Price') or 0)
    except:
        meta['bestBid'] = 0.0; meta['bestAsk'] = 0.0
    try:
        meta['index_corr'] = round(((float(item.get('markPrice', 1)) / float(item.get('indexPrice', 1))) - 1) * 100, 1)
    except:
        meta['index_corr'] = 0.0
    # fundingInterval (best-effort)
    try:
        meta['amount24'] = round(float(item.get('turnover24h', 0.0)))
    except:
        meta['amount24'] = 0.0
    try:
        nft = item.get('nextFundingTime')
        if nft:
            fundingTime = int(int(nft) / 1000)
            hourTime = int(datetime.fromtimestamp(int(fundingTime)).hour)
            if hourTime in (3, 11, 19):
                meta['fundingInterval'] = 8
            elif hourTime in (7, 15, 23):
                meta['fundingInterval'] = 4
            elif hourTime in (5, 13, 21):
                meta['fundingInterval'] = 2
            else:
                meta['fundingInterval'] = 1
        else:
            meta['fundingInterval'] = 8
    except:
        meta['fundingInterval'] = 8
    meta['predict'] = '-'
    return meta

def _norm_sym(s):
    if not isinstance(s, str):
        return s
    return s.replace('_','').replace('-','').upper()

async def bybit_collect_once(session, use_proxy_toggle=False):
    proxy = PROXY if use_proxy_toggle else None
    fut, spot = await asyncio.gather(
        fetch_json(session, BYBIT_FUT_URL, proxy=proxy, timeout=10),
        fetch_json(session, BYBIT_SPOT_URL, proxy=proxy, timeout=10),
    )

    data_usdt = []; market_meta = {}; data_spot = {}

    if fut:
        for item in fut.get('result', {}).get('list', []):
            sym = item.get('symbol')
            if not sym or 'USDT' not in sym:
                continue
            meta = compute_bybit_meta(item)
            bid = meta.get('bestBid', 0); ask = meta.get('bestAsk', 0)
            funding = meta.get('funding', 0); idx = meta.get('index_corr', 0)
            data_usdt.append([sym, funding, bid, 0, idx, 0, ask, 0])
            market_meta[sym] = {
                'fundingInterval': meta.get('fundingInterval'),
                'fee': meta.get('fee'),
                'predict': meta.get('predict'),
                'bestBid': bid,
                'bestAsk': ask,
                'index_corr': idx,
                'amount24': meta.get('amount24'),
            }

    if spot:
        for it in spot.get('result', {}).get('list', []):
            sym = it.get('symbol')
            if not sym or 'USDT' not in sym:
                continue
            try:
                sym = _norm_sym(sym)
                bid = float(it.get('bid1Price') or 0)
                ask = float(it.get('ask1Price') or 0)
                amount24_spot = round(float(it.get('turnover24h') or 0))
                mm = market_meta.get(sym) or {}
                mm.update({
                    'amount24_spot': amount24_spot
                })
                market_meta[sym] = mm
            except:
                bid = 0.0; ask = 0.0
            data_spot[sym] = [sym, bid, ask]

    msg = {
        'market': 'Bybit',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)

async def bybit_loop():
    use_toggle = False
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await bybit_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                print("Bybit collector error:", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP)

# ---------------- Mexc ----------------
def compute_mexc_meta(item, funding_info=None):
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

async def mexc_collect_limits():
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(MEXC_CONT_URL) as mc:
                    contract = await mc.json()
                    for ct in contract.get('data', []):
                        s = ct.get('symbol').replace('_USDT','USDT')
                        if 'USDT' in s:
                            limit_max_vol = ct.get('limitMaxVol', 0)
                            contract_size = ct.get('contractSize', 0)
                            mexc_contract[s] = [limit_max_vol, contract_size]
            except:
                pass
            await asyncio.sleep(30)

async def mexc_collect_once(session, use_proxy_toggle=False):
    proxy = PROXY if use_proxy_toggle else None

    fut_resp, fund_resp, spot_resp = await asyncio.gather(
        fetch_json(session, MEXC_FUT_URL, proxy=proxy, timeout=12),
        fetch_json(session, MEXC_FUND_URL, proxy=proxy, timeout=12),
        fetch_json(session, MEXC_SPOT_URL, proxy=proxy, timeout=12),
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
                    meta = compute_mexc_meta(it, funding_info=funding_info)
                    bid = meta.get('bestBid', 0.0); ask = meta.get('bestAsk', 0.0)
                    funding = meta.get('funding', 0.0); idx = meta.get('index_corr', 0.0)
                    data_usdt.append([sym, funding, bid, 0, idx, 0, ask, 0])
                    mexc_cont = mexc_contract.get(sym)
                    limits, contract_size = mexc_cont
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
                    continue

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
        'market': 'Mexc',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)

async def mexc_loop():
    use_toggle = False
    asyncio.create_task(mexc_collect_limits())
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await mexc_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                print("Mexc collector error:", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP_MEXC)

# ===== Okx collector (HTTP only, с mark/index для index_corr) ============
async def okx_collect_once(session, use_proxy_toggle=False):
    """
    OKX collector:
    - funding rates (fundingRate,fundingTime,nextFundingTime)
    - swap tickers (bid/ask/vol)
    - mark prices and index tickers -> для вычисления index_corr
    - spot tickers (опционально)
    Формат вывода совпадает с другими collectors.
    """
    proxy = PROXY if use_proxy_toggle else None

    # параллельные запросы: funding, tickers, spot, mark, index
    fund_task = asyncio.create_task(fetch_json(session, OKX_FUND_URL, proxy=proxy, timeout=12))
    tickers_task = asyncio.create_task(fetch_json(session, OKX_TICKERS_URL, proxy=proxy, timeout=12))
    spot_task = asyncio.create_task(fetch_json(session, OKX_SPOT_URL, proxy=proxy, timeout=12))
    mark_task = asyncio.create_task(fetch_json(session, OKX_MARK_URL, proxy=proxy, timeout=12))
    index_task = asyncio.create_task(fetch_json(session, OKX_INDEX_URL, proxy=proxy, timeout=12))

    fund_json, tickers_json, spot_json, mark_json, index_json = await asyncio.gather(
        fund_task, tickers_task, spot_task, mark_task, index_task
    )

    # --- prepare maps ---
    funding_map = {}   # sym -> (funding_percent, funding_time_ms, next_funding_time_ms, interval_hours)
    mark_map = {}      # sym -> markPx (float)
    index_map = {}     # sym -> idxPx (float)
    correction_map = {}# sym -> correction in percent

    data_usdt = []
    market_meta = {}
    data_spot = {}

    # --- funding ---
    try:
        arr = fund_json.get('data') if isinstance(fund_json, dict) else None
        if isinstance(arr, list):
            for it in arr:
                try:
                    inst = it.get('instId') or ''
                    if not inst:
                        continue
                    sym = inst.replace('-USDT-SWAP', 'USDT').replace('-', '')
                    sym = _norm_sym(sym)
                    fr = it.get('fundingRate') or it.get('funding_rate') or '0'
                    try:
                        fr_val = float(fr) * 100.0
                    except:
                        fr_val = 0.0
                    try:
                        ft = int(it.get('fundingTime') or 0)
                    except:
                        ft = 0
                    try:
                        nft = int(it.get('nextFundingTime') or 0)
                    except:
                        nft = 0
                    try:
                        interval_h = int((nft - ft) / 1000 / 3600) if ft and nft and nft > ft else 8
                    except:
                        interval_h = 8
                    funding_map[sym] = (round(fr_val, 2), ft, nft, interval_h)
                except Exception:
                    continue
    except Exception:
        pass

    # --- mark prices ---
    try:
        arr = mark_json.get('data') if isinstance(mark_json, dict) else None
        if isinstance(arr, list):
            for it in arr:
                try:
                    inst = it.get('instId') or ''
                    if not inst:
                        continue
                    # normalize mark instId like "MOG-USDT-SWAP" -> "MOGUSDT"
                    sym = inst.replace('-USDT-SWAP', 'USDT').replace('-', '')
                    sym = _norm_sym(sym)
                    mark_px = it.get('markPx') or it.get('mark_price') or it.get('mark')
                    try:
                        mark_map[sym] = float(mark_px)
                    except:
                        mark_map[sym] = 0.0
                except Exception:
                    continue
    except Exception:
        pass

    # --- index tickers ---
    try:
        arr = index_json.get('data') if isinstance(index_json, dict) else None
        if isinstance(arr, list):
            for it in arr:
                try:
                    inst = it.get('instId') or ''
                    if not inst:
                        continue
                    # index instId like "MOG-USDT" -> "MOGUSDT"
                    sym = inst.replace('-USDT', 'USDT').replace('-', '')
                    sym = _norm_sym(sym)
                    idx_px = it.get('idxPx') or it.get('index') or it.get('idxPx')
                    try:
                        index_map[sym] = float(idx_px)
                    except:
                        index_map[sym] = 0.0
                except Exception:
                    continue
    except Exception:
        pass

    # --- compute correction_map where both mark and index exist ---
    for sym, mark_px in mark_map.items():
        idx_px = index_map.get(sym)
        try:
            if idx_px and idx_px != 0:
                corr = round(((mark_px / idx_px) - 1) * 100, 2)
            else:
                corr = 0.0
        except Exception:
            corr = 0.0
        correction_map[sym] = corr

    # --- parse swap tickers (best bid/ask and vol24) and attach correction ---
    try:
        arr = tickers_json.get('data') if isinstance(tickers_json, dict) else None
        if isinstance(arr, list):
            for it in arr:
                try:
                    inst = it.get('instId') or ''
                    if not inst:
                        continue
                    sym = inst.replace('-USDT-SWAP', 'USDT').replace('-', '')
                    sym = _norm_sym(sym)
                    bid = it.get('bidPx') or it.get('bid') or it.get('bidPx') or 0
                    ask = it.get('askPx') or it.get('ask') or it.get('askPx') or 0
                    vol = it.get('volCcy24h') or it.get('vol24h') or it.get('vol') or 0
                    try:
                        bid_f = float(bid)
                    except:
                        bid_f = 0.0
                    try:
                        ask_f = float(ask)
                    except:
                        ask_f = 0.0
                    try:
                        vol_f = round(float(vol) * bid_f)
                    except:
                        vol_f = 0.0

                    # funding info if exists
                    fd_info = funding_map.get(sym)
                    if fd_info:
                        fd_val, ft, nft, interval_h = fd_info
                    else:
                        fd_val, ft, nft, interval_h = 0.0, 0, 0, 8

                    # index_corr from correction_map (if exists) else 0.0
                    idx_corr = correction_map.get(sym, 0.0)

                    data_usdt.append([sym, fd_val, bid_f, 0, idx_corr, 0, ask_f, 0])

                    market_meta[sym] = {
                        'fundingInterval': interval_h,
                        'fee': 0.05,
                        'predict': '-',
                        'bestBid': bid_f,
                        'bestAsk': ask_f,
                        'index_corr': idx_corr,
                        'index_price': index_map.get(sym, None),
                        'amount24': vol_f
                    }
                except Exception:
                    continue
    except Exception:
        pass

    # --- parse spot tickers (optional) ---
    try:
        arr = spot_json.get('data') if isinstance(spot_json, dict) else None
        if isinstance(arr, list):
            for t in arr:
                try:
                    inst = t.get('instId') or ''
                    if not inst:
                        continue
                    sym = inst.replace('-USDT', 'USDT').replace('-', '').upper()
                    bid = float(t.get('bidPx') or t.get('bid') or 0)
                    ask = float(t.get('askPx') or t.get('ask') or 0)
                    data_spot[sym] = [sym, bid, ask]
                    mm = market_meta.get(sym) or {}
                    vol = float(t.get('vol24h') or t.get('volCcy24h') or 0)
                    try:
                        mm.update({'amount24_spot': round(float(vol * bid))})
                    except:
                        mm.update({'amount24_spot': 0.0})
                    market_meta[sym] = mm
                except Exception:
                    continue
    except Exception:
        pass

    # send message
    msg = {
        'market': 'Okx',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)
    logger.debug("Okx: sent %d futs / %d spots", len(data_usdt), len(data_spot))


async def okx_loop():
    use_toggle = False
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await okx_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                logger.exception("Okx collector error: %s", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP)

# ===== Binance collector (HTTP only) =======================================
async def binance_collect_once(session, use_proxy_toggle=False):
    """
    Binance:
    - premiumIndex (futures) -> funding, markPrice, indexPrice, nextFundingTime
    - futures bookTicker -> best bid/ask for futures
    - spot bookTicker -> optional spot bids/asks (to fill data_spot / amount24_spot if desired)
    Формат output: same as others -> data_usdt entries: [sym, funding%, bestBid, 0, index_corr, 0, bestAsk, 0]
    market_meta contains 'fundingInterval', 'bestBid', 'bestAsk', 'index_corr', 'amount24' (if available)
    """
    proxy = PROXY if use_proxy_toggle else None

    # параллельные запросы
    prem_task = asyncio.create_task(fetch_json(session, BINANCE_PREMIUM, proxy=proxy, timeout=12))
    fut_book_task = asyncio.create_task(fetch_json(session, BINANCE_FUT_BOOK, proxy=proxy, timeout=12))
    spot_book_task = asyncio.create_task(fetch_json(session, BINANCE_SPOT_BOOK, proxy=proxy, timeout=12))

    prem_json, fut_book_json, spot_book_json = await asyncio.gather(
        prem_task, fut_book_task, spot_book_task
    )

    # maps
    premium_map = {}   # sym -> { funding, markPrice, indexPrice, nextFundingTime_ms, interval_hours }
    fut_bid_map = {}   # sym -> (bestBid, bestAsk)
    spot_map = {}      # sym -> (bid, ask)  (optional)

    data_usdt = []
    market_meta = {}
    data_spot = {}

    # --- parse premiumIndex (fapi) ---
    # premium is a list of dicts
    try:
        if isinstance(prem_json, list):
            for it in prem_json:
                try:
                    sym = it.get('symbol') or ''
                    if not sym or 'USDT' not in sym:
                        continue
                    # funding - use lastFundingRate if present, else lastFundingRate/estimated? keep current style
                    fr = it.get('lastFundingRate') or it.get('lastFundingRate') or it.get('lastFundingRate')
                    try:
                        fr_val = float(fr) * 100.0
                    except:
                        fr_val = 0.0
                    # mark/index prices
                    try:
                        mark_px = float(it.get('markPrice') or 0.0)
                    except:
                        mark_px = 0.0
                    try:
                        idx_px = float(it.get('indexPrice') or 0.0)
                    except:
                        idx_px = 0.0
                    # nextFundingTime ms -> compute interval hours (best effort like others)
                    try:
                        nft = int(it.get('nextFundingTime') or 0)
                    except:
                        nft = 0
                    try:
                        # compute interval by comparing nextFundingTime - now if available (fallback to 8)
                        if nft:
                            interval_h = 8
                            # we can deduce interval by hour of nextFundingTime similar to others
                            fundingTimeHour = int(datetime.fromtimestamp(int(nft/1000)).hour)
                            if fundingTimeHour in (3, 11, 19):
                                interval_h = 8
                            elif fundingTimeHour in (7, 15, 23):
                                interval_h = 4
                            elif fundingTimeHour in (5, 13, 21):
                                interval_h = 2
                            else:
                                interval_h = 1
                        else:
                            interval_h = 8
                    except:
                        interval_h = 8

                    premium_map[sym] = {
                        'funding': round(fr_val, 2),
                        'mark': mark_px,
                        'index': idx_px,
                        'nextFundingTime': nft,
                        'interval': interval_h
                    }
                except Exception:
                    continue
    except Exception:
        pass

    # --- parse futures bookTicker (fapi) for best bid/ask ---
    try:
        if isinstance(fut_book_json, list):
            for it in fut_book_json:
                try:
                    sym = it.get('symbol') or ''
                    if not sym or 'USDT' not in sym:
                        continue
                    try:
                        bid = float(it.get('bidPrice') or 0.0)
                    except:
                        bid = 0.0
                    try:
                        ask = float(it.get('askPrice') or 0.0)
                    except:
                        ask = 0.0
                    fut_bid_map[sym] = (bid, ask)
                except Exception:
                    continue
    except Exception:
        pass

    # --- parse spot bookTicker (optional) ---
    try:
        if isinstance(spot_book_json, list):
            for it in spot_book_json:
                try:
                    sym = it.get('symbol') or ''
                    if not sym or 'USDT' not in sym:
                        continue
                    try:
                        bid = float(it.get('bidPrice') or 0.0)
                    except:
                        bid = 0.0
                    try:
                        ask = float(it.get('askPrice') or 0.0)
                    except:
                        ask = 0.0
                    spot_map[sym] = (bid, ask)
                except Exception:
                    continue
    except Exception:
        pass

    # --- build data_usdt by iterating premium_map (this has mark/index/funding) ---
    for sym, info in premium_map.items():
        try:
            fd_val = info.get('funding', 0.0)
            mark_px = info.get('mark', 0.0)
            idx_px = info.get('index', 0.0)
            interval_h = info.get('interval', 8)

            bid, ask = fut_bid_map.get(sym, (0.0, 0.0))
            # compute index_corr: (mark / index - 1) * 100
            try:
                idx_corr = round(((mark_px / idx_px) - 1) * 100, 2) if idx_px else 0.0
            except:
                idx_corr = 0.0

            # amount24 not in premiumIndex; set 0. Optionally pull from other endpoints if needed.
            amount24 = 0.0

            # append in standard layout used elsewhere
            data_usdt.append([sym, fd_val, bid, 0, idx_corr, 0, ask, 0])

            market_meta[sym] = {
                'fundingInterval': interval_h,
                'fee': 0.04,   # примерная комиссия (подкорректируй если нужно)
                'predict': '-',
                'bestBid': bid,
                'bestAsk': ask,
                'index_corr': idx_corr,
                'index_price': idx_px,
                'amount24': amount24
            }
        except Exception:
            continue

    # --- optional: include spot tickers in data_spot (best effort) ---
    for sym, (bid, ask) in spot_map.items():
        try:
            data_spot[sym] = [sym, bid, ask]
            mm = market_meta.get(sym) or {}
            # amount24_spot unknown via this endpoint — left out or computed elsewhere
            mm.update({'amount24_spot': 0.0})
            market_meta[sym] = mm
        except Exception:
            continue

    # send message
    msg = {
        'market': 'Binance',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)
    logger.debug("Binance: sent %d futs / %d spots", len(data_usdt), len(data_spot))

async def binance_loop():
    use_toggle = False
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await binance_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                logger.exception("Binance collector error: %s", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP)

# ===== BingX collector (HTTP only) =======================================
async def bingx_collect_once(session, use_proxy_toggle=False):
    """
    BingX collector:
    - premiumIndex -> funding,lastFundingRate,markPrice,indexPrice,nextFundingTime
    - swap ticker -> bid/ask
    - spot 24hr -> spot bids/asks and vol
    Попытка извлечь amount24 (USD): ищем quote-volume поля; если их нет, умножаем базовый vol на markPx.
    """
    proxy = PROXY if use_proxy_toggle else None

    # параллельные запросы
    prem_task = asyncio.create_task(fetch_json(session, BINGX_PREMIUM, proxy=proxy, timeout=12))
    swap_task = asyncio.create_task(fetch_json(session, BINGX_TICKER_SWAP, proxy=proxy, timeout=12))
    spot_task = asyncio.create_task(fetch_json(session, f"{BINGX_SPOT_24H}?timestamp={int(time.time() * 1000)}", proxy=proxy, timeout=12))

    prem_json, swap_json, spot_json = await asyncio.gather(prem_task, swap_task, spot_task)

    data_usdt = []
    data_spot = {}
    market_meta = {}

    # --- parse premiumIndex (futures funding + mark/index) ---
    # expected structure: {'data': [ { 'symbol': 'BTC-USDT', 'lastFundingRate': '...', 'markPrice': '...', 'indexPrice': '...', 'nextFundingTime': 1767... }, ... ]}
    premium_map = {}
    try:
        arr = prem_json.get('data') if isinstance(prem_json, dict) else None
        if isinstance(arr, list):
            for it in arr:
                try:
                    raw = it.get('symbol') or it.get('symbol')
                    if not raw:
                        continue
                    # normalize symbol: 'BTC-USDT' -> 'BTCUSDT'
                    sym = raw.replace('-USDT', 'USDT').replace('-', '')
                    sym = _norm_sym(sym)
                    # funding
                    fr = it.get('lastFundingRate') or it.get('last_funding_rate') or it.get('fundingRate') or 0
                    try:
                        fr_val = float(fr) * 100.0
                    except:
                        fr_val = 0.0
                    # mark/index
                    try:
                        mark_px = float(it.get('markPrice') or it.get('mark_price') or 0.0)
                    except:
                        mark_px = 0.0
                    try:
                        idx_px = float(it.get('indexPrice') or it.get('index_price') or 0.0)
                    except:
                        idx_px = 0.0
                    # times
                    try:
                        nft = int(it.get('nextFundingTime') or 0)
                    except:
                        nft = 0
                    # compute interval hours best-effort (like others)
                    try:
                        if nft:
                            hour = int(datetime.fromtimestamp(int(nft/1000)).hour)
                            if hour in (3, 11, 19):
                                interval_h = 8
                            elif hour in (7, 15, 23):
                                interval_h = 4
                            elif hour in (5, 13, 21):
                                interval_h = 2
                            else:
                                interval_h = 1
                        else:
                            interval_h = 8
                    except:
                        interval_h = 8

                    premium_map[sym] = {
                        'funding': round(fr_val, 2),
                        'mark': mark_px,
                        'index': idx_px,
                        'nextFundingTime': nft,
                        'interval': interval_h,
                    }
                except Exception:
                    continue
    except Exception:
        pass

    # --- parse swap tickers (best bid/ask) ---
    swap_map = {}
    try:
        arr = swap_json.get('data') if isinstance(swap_json, dict) else None
        if isinstance(arr, list):
            for it in arr:
                try:
                    raw = it.get('symbol') or it.get('symbol')
                    if not raw:
                        continue
                    sym = raw.replace('-USDT', 'USDT').replace('-', '')
                    sym = _norm_sym(sym)
                    try:
                        bid = float(it.get('bidPrice') or it.get('bid') or 0.0)
                    except:
                        bid = 0.0
                    try:
                        ask = float(it.get('askPrice') or it.get('ask') or 0.0)
                    except:
                        ask = 0.0

                    try:
                        amount24 = float(it.get('quoteVolume') or 0.0)
                    except:
                        amount24 = 0.0

                    swap_map[sym] = (bid, ask, amount24)
                except Exception:
                    continue
    except Exception:
        pass

    # --- build data_usdt from premium_map and swap_map ---
    for sym, info in premium_map.items():
        try:
            fd_val = info.get('funding', 0.0)
            mark_px = info.get('mark', 0.0)
            idx_px = info.get('index', 0.0)
            interval_h = info.get('interval', 8)

            bid, ask, amount24 = swap_map.get(sym, (0.0, 0.0, 0.0))

            # compute index_corr
            try:
                idx_corr = round(((mark_px / idx_px) - 1) * 100, 2) if idx_px else 0.0
            except:
                idx_corr = 0.0

            data_usdt.append([sym, fd_val, bid, 0, idx_corr, 0, ask, 0])

            market_meta[sym] = {
                'fundingInterval': interval_h,
                'fee': 0.05,
                'predict': '-',
                'bestBid': bid,
                'bestAsk': ask,
                'index_corr': idx_corr,
                'index_price': idx_px if idx_px else None,
                'amount24': amount24
            }
        except Exception:
            continue

    # --- parse spot 24h (optional) ---
    try:
        arr = spot_json.get('data') if isinstance(spot_json, dict) else None
        if isinstance(arr, list):
            for it in arr:
                try:
                    raw = it.get('symbol') or it.get('symbol')
                    if not raw:
                        continue
                    sym = raw.replace('-USDT', 'USDT').replace('-', '').upper()
                    try:
                        bid = float(it.get('bidPrice') or 0.0)
                    except:
                        bid = 0.0
                    try:
                        ask = float(it.get('askPrice') or 0.0)
                    except:
                        ask = 0.0
                    # try to find quote volume already in USD
                    vol_quote = None
                    v = it.get('quoteVolume') or 0
                    if v is not None and v != '':
                        try:
                            vol_quote = float(v)
                        except:
                            pass
                    data_spot[sym] = [sym, bid, ask]
                    mm = market_meta.get(sym) or {}
                    # if vol_quote present treat as USD-ish; else leave 0
                    mm.update({'amount24_spot': round(vol_quote) if vol_quote else 0.0})
                    market_meta[sym] = mm
                except Exception:
                    continue
    except Exception:
        pass

    # send message
    msg = {
        'market': 'BingX',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)
    logger.debug("BingX: sent %d futs / %d spots", len(data_usdt), len(data_spot))

async def bingx_loop():
    use_toggle = False
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await bingx_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                logger.exception("BingX collector error: %s", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP)


async def bitmart_ws_manager():
    """
    Бесконечный менеджер WebSocket для BitMart.
    Подключается, подписывается на 'futures/ticker' и обновляет bitmart_funding_data.
    При ошибке/разрыве — очищает данные и переподключается через паузу.
    """
    pong_task = None
    pong_flag = True
    while True:
        try:
            async with aiohttp.ClientSession() as ws_session:
                try:
                    async with ws_session.ws_connect(BITMART_WS, receive_timeout=180) as ws:
                        logger.info("BitMart WS connected")
                        # Подписка как в старом коде
                        subs = {'action': 'subscribe', 'args': ['futures/ticker']}
                        await ws.send_str(json.dumps(subs))

                        async def send_pong_periodically():
                            nonlocal pong_flag
                            try:
                                while pong_flag:
                                    await asyncio.sleep(15)  # Ожидание 15 секунд
                                    ping_msg = dict(action='ping')
                                    ping_msg = json.dumps(ping_msg)
                                    await ws.send_str(ping_msg)
                            except Exception:
                                logger.exception(f'Bitmart exception send ping')

                        pong_task = asyncio.create_task(send_pong_periodically())

                        async for msg in ws:
                            try:
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    obj = json.loads(msg.data)
                                    data = obj.get('data')
                                    # data может быть словарём либо списком — проверяем оба
                                    if isinstance(data, dict):
                                        # пример: {'symbol': 'BTCUSDT', 'ask_price': '...', 'bid_price': '...'}
                                        symbol = data.get('symbol')
                                        if symbol:
                                            try:
                                                bestAsk = float(data.get('ask_price') or data.get('ask_price_str') or 0.0)
                                            except:
                                                bestAsk = 0.0
                                            try:
                                                bestBid = float(data.get('bid_price') or data.get('bid_price_str') or 0.0)
                                            except:
                                                bestBid = 0.0
                                            async with bitmart_lock:
                                                bitmart_funding_data[symbol] = {'bestAsk': bestAsk, 'bestBid': bestBid}
                                    elif isinstance(data, list):
                                        # если приходят массивы — обрабатываем элементы
                                        for item in data:
                                            if not isinstance(item, dict):
                                                continue
                                            symbol = item.get('symbol')
                                            if not symbol:
                                                continue
                                            try:
                                                bestAsk = float(item.get('ask_price') or 0.0)
                                            except:
                                                bestAsk = 0.0
                                            try:
                                                bestBid = float(item.get('bid_price') or 0.0)
                                            except:
                                                bestBid = 0.0
                                            async with bitmart_lock:
                                                bitmart_funding_data[symbol] = {'bestAsk': bestAsk, 'bestBid': bestBid}
                                elif msg.type == aiohttp.WSMsgType.CLOSED:
                                    logger.warning("BitMart WS closed")
                                    break
                                elif msg.type == aiohttp.WSMsgType.ERROR:
                                    logger.warning("BitMart WS error: %s", ws.exception())
                                    break
                            except Exception:
                                logger.exception("BitMart WS message handling error")
                        logger.info("BitMart WS disconnecting (inner loop end)")
                except Exception as e:
                    logger.warning("BitMart WS connection error: %s", e)
        except Exception as e:
            try:
                pong_flag = False
                if pong_task:
                    pong_task.cancel()
                    await pong_task
            except asyncio.CancelledError:
                pass
            logger.exception("BitMart WS outer error")
        # on any disconnection/exception: clear data and sleep a bit before reconnect
        try:
            async with bitmart_lock:
                bitmart_funding_data.clear()
        except Exception:
            pass
        await asyncio.sleep(2)  # пауза перед переподключением

async def bitmart_collect_once(session, use_proxy_toggle=False):
    """
    Собираем данные из BitMart:
    - контрактный endpoint -> funding rates + last/index price
    - получаем bestBid/bestAsk из bitmart_funding_data (WS)
    Формируем data_usdt, data_spot, market_meta в общем формате.
    """
    proxy = PROXY if use_proxy_toggle else None
   # proxy = PROXY_BITMART
    # запрашиваем контрактный список и (опционально) спот
    contract_task = asyncio.create_task(fetch_json(session, BITMART_CONTRACTS, proxy=proxy, timeout=12))
    spot_task = asyncio.create_task(fetch_json(session, BITMART_SPOT, proxy=proxy, timeout=12))

    contract_json, spot_json = await asyncio.gather(contract_task, spot_task)

    data_usdt = []
    data_spot = {}
    market_meta = {}

    # parse contracts -> contract_json['data']['symbols'] как в старом коде
    try:
        symbols = contract_json.get('data', {}).get('symbols') if isinstance(contract_json, dict) else None
        if isinstance(symbols, list):
            for it in symbols:
                try:
                    sym = it.get('symbol')
                    if not sym or 'USDT' not in sym:
                        continue
                    # funding values
                    try:
                        if float(it.get('volume_24h', 0)) == 0:
                            continue
                    except:
                        pass
                    try:
                        expected_funding = float(it.get('expected_funding_rate') or it.get('expectedFundingRate') or 0.0) * 100.0
                    except:
                        expected_funding = 0.0
                    try:
                        funding_rate = float(it.get('funding_rate') or it.get('fundingRate') or 0.0) * 100.0
                    except:
                        funding_rate = 0.0
                    # prices
                    try:
                        last_price = float(it.get('last_price') or it.get('lastPrice') or 0.0)
                    except:
                        last_price = 0.0
                    try:
                        index_price = float(it.get('index_price') or it.get('indexPrice') or 0.0)
                    except:
                        index_price = 0.0
                    # index_corr
                    try:
                        index_corr = round(((last_price / index_price) - 1) * 100, 2) if index_price else 0.0
                    except:
                        index_corr = 0.0

                    # build data_usdt row in our standard layout:
                    # [sym, expected_funding%, bestBid, funding_rate%, index_corr, 0, bestAsk, 0]
                    data_usdt.append([sym, round(expected_funding, 2), last_price, round(funding_rate, 2), index_corr, 0, last_price, 0])

                    market_meta[sym] = {
                        'fundingInterval': 8,
                        'fee': 0.06,
                        'predict': '-',
                        'bestBid': last_price,
                        'bestAsk': last_price,
                        'index_corr': index_corr,
                        # amount24 пока не считаем
                        'amount24': 0.0
                    }
                except Exception:
                    continue
    except Exception:
        pass

    # parse spot tickers if needed (best-effort)
    try:
        arr = spot_json.get('data') if isinstance(spot_json, dict) else None
        if isinstance(arr, list):
            for t in arr:
                try:
                    if isinstance(t, (list, tuple)) and len(t) > 0:
                        # older response may be list with symbol at index 0, bid at index 8, ask at 10 (as in old code)
                        raw = t[0]
                        sym = raw.replace('_', '').upper()
                        if 'USDT' not in sym:
                            continue
                        bid = float(t[8]) if len(t) > 8 else 0.0
                        ask = float(t[10]) if len(t) > 10 else 0.0
                        data_spot[sym] = [sym, bid, ask]
                except Exception:
                    continue
    except Exception:
        pass

    # send message
    msg = {
        'market': 'BitMart',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)
    logger.debug("BitMart: sent %d futs / %d spots", len(data_usdt), len(data_spot))

async def bitmart_loop():
    use_toggle = False
    # запустим WS-менеджер в фоне (он будет пытаться переподключаться сам)
  #  ws_task = asyncio.create_task(bitmart_ws_manager())
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await bitmart_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                logger.exception("BitMart collector error: %s", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP)


def compute_xt_meta(contract):
    """
    Вычисляет мета-данные для фьючерсного контракта XT.
    Ожидается элемент из ответа /future/market/v1/public/cg/contracts.
    """
    meta = {}
    meta['fee'] = 0.06  # комиссия XT для фьючерсов (по умолчанию)

    # funding rate (%)
    try:
        fr = float(contract.get('funding_rate', 0) or 0)
        meta['funding'] = round(fr * 100, 2)
    except:
        meta['funding'] = 0.0

    # bestBid / bestAsk
    try:
        meta['bestBid'] = float(contract.get('bid', 0) or 0)
        meta['bestAsk'] = float(contract.get('ask', 0) or 0)
    except:
        meta['bestBid'] = 0.0
        meta['bestAsk'] = 0.0

    # index_corr: (last_price / index_price - 1) * 100
    try:
        last_price = float(contract.get('last_price', 0) or 0)
        index_price = float(contract.get('index_price', 0) or 0)
        if index_price and index_price != 0:
            meta['index_corr'] = round(((last_price / index_price) - 1) * 100, 2)
        else:
            meta['index_corr'] = 0.0
    except:
        meta['index_corr'] = 0.0

    # fundingInterval — XT funding происходит каждые 8 часов (16:00, 00:00, 08:00 UTC)
    try:
        funding_interval = contract.get('collection_internal')
        if funding_interval:
            meta['fundingInterval'] = int(funding_interval)
        else:
            next_funding_ts = contract.get('next_funding_rate_timestamp')
            if next_funding_ts and not funding_interval:
                funding_time = int(int(next_funding_ts) / 1000)
                hour = int(datetime.fromtimestamp(funding_time).hour)
                if hour in (3, 11, 19):
                    meta['fundingInterval'] = 8
                elif hour in (7, 15, 23):
                    meta['fundingInterval'] = 4
                elif hour in (5, 13, 21):
                    meta['fundingInterval'] = 2
                else:
                    meta['fundingInterval'] = 1
            else:
                meta['fundingInterval'] = 8
    except:
        meta['fundingInterval'] = 8

    # amount24 — объём торгов за 24ч в USD (target_volume * last_price)
    try:
        target_volume = float(contract.get('target_volume', 0) or 0)
        meta['amount24'] = round(target_volume)
    except:
        meta['amount24'] = 0.0

    meta['predict'] = '-'
    return meta

async def xt_collect_once(session, use_proxy_toggle=False):
    """
    Сбор данных с XT.com.
    - Фьючерсы: /future/market/v1/public/cg/contracts (все контракты разом)
    - Спот: /v4/public/ticker (все спотовые пары разом)
    """
    proxy = PROXY if use_proxy_toggle else None

    # Параллельные запросы
    futures_task = asyncio.create_task(
        fetch_json(session, XT_FUT_CONTRACTS_URL, proxy=proxy, timeout=12)
    )
    spot_task = asyncio.create_task(
        fetch_json(session, XT_SPOT_TICKER_URL, proxy=proxy, timeout=12)
    )

    futures_json, spot_json = await asyncio.gather(futures_task, spot_task)

    data_usdt = []
    market_meta = {}
    data_spot = {}

    # ===== Обработка фьючерсов =====
    # Ответ ожидается в виде списка контрактов
    try:
        contracts = futures_json if isinstance(futures_json, list) else None
        if contracts:
            for contract in contracts:
                try:
                    # Проверяем, что это USDT-контракт
                    symbol_raw = contract.get('symbol', '')
                    if not symbol_raw or 'usdt' not in symbol_raw.lower():
                        continue

                    # Нормализуем символ: eth_usdt -> ETHUSDT
                    sym = _norm_sym(symbol_raw)

                    # Вычисляем мета-данные
                    meta = compute_xt_meta(contract)

                    funding = meta.get('funding', 0.0)
                    bid = meta.get('bestBid', 0.0)
                    ask = meta.get('bestAsk', 0.0)
                    idx_corr = meta.get('index_corr', 0.0)

                    # Формат: [symbol, funding%, bestBid, 0, index_corr, 0, bestAsk, 0]
                    data_usdt.append([sym, funding, bid, 0, idx_corr, 0, ask, 0])

                    # Мета-данные для market_meta
                    market_meta[sym] = {
                        'fundingInterval': meta.get('fundingInterval'),
                        'fee': meta.get('fee'),
                        'predict': meta.get('predict'),
                        'bestBid': bid,
                        'bestAsk': ask,
                        'index_corr': idx_corr,
                        'amount24': meta.get('amount24'),
                    }

                except Exception as e:
                    logger.exception(f"XT futures: error processing contract {contract}")
                    continue
    except Exception as e:
        logger.exception("XT futures: error parsing response")

    # ===== Обработка спота =====
    # Ответ: { "rc": 0, "result": [ { "s": "btc_usdt", "bp": bid, "ap": ask, ... } ] }
    try:
        if isinstance(spot_json, dict):
            result = spot_json.get('result', [])
            if isinstance(result, list):
                for item in result:
                    try:
                        symbol_raw = item.get('s', '')
                        if not symbol_raw or 'usdt' not in symbol_raw.lower():
                            continue

                        sym = _norm_sym(symbol_raw)

                        # bid (buy price) и ask (sell price)
                        bid = float(item.get('bp', 0) or 0)
                        ask = float(item.get('ap', 0) or 0)

                        # Если bid/ask нет, пробуем взять из последней цены
                        if bid == 0 and ask == 0:
                            last = float(item.get('c', 0) or 0)
                            bid = last
                            ask = last

                        data_spot[sym] = [sym, bid, ask]

                        # Добавляем amount24_spot в market_meta если есть
                        if sym in market_meta:
                            try:
                                vol = float(item.get('v', 0) or 0)  # объём в USD
                                market_meta[sym]['amount24_spot'] = round(vol)
                            except:
                                pass

                    except Exception as e:
                        logger.exception(f"XT spot: error processing item {item}")
                        continue
    except Exception as e:
        logger.exception("XT spot: error parsing response")

    # ===== Отправка сообщения =====
    msg = {
        'market': 'XT',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)
    logger.debug("XT: sent %d futs / %d spots", len(data_usdt), len(data_spot))

async def xt_loop():
    """Основной цикл сборщика XT."""
    use_toggle = False
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await xt_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                logger.exception("XT collector error: %s", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP)


# ===== CoinEx collector (HTTP + WebSocket) ==================================
# Вспомогательная функция для отправки пинга
async def coinex_send_ping(ws, ping_id):
    while True:
        await asyncio.sleep(3)
        try:
            ping_msg = {"method": "server.ping", "params": {}, "id": ping_id}
            await ws.send_str(json.dumps(ping_msg))
        except Exception:
            break

# WebSocket для фьючерсных тикеров (bbo)
async def coinex_ws_ticker():
    while True:
        try:
            # Ждём, пока появится список символов из funding
            while not coinex_funding_data:
                await asyncio.sleep(1)
            symbols = list(coinex_funding_data.keys())
            url = 'wss://socket.coinex.com/v2/futures'
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url) as ws:
                    # Очищаем старые данные перед подключением
                    async with coinex_lock:
                        coinex_ticker_data.clear()
                    subs = {
                        "method": "bbo.subscribe",
                        "params": {"market_list": symbols},
                        "id": 1
                    }
                    await ws.send_str(json.dumps(subs))
                    logger.info("CoinEx WS ticker connected, subscribed to %d symbols", len(symbols))
                    ping_task = asyncio.create_task(coinex_send_ping(ws, 1))
                    try:
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                data = gzip.decompress(msg.data).decode('utf-8')
                                obj = json.loads(data)
                                d = obj.get('data')
                                if d and isinstance(d, dict):
                                    symbol = d.get('market')
                                    if symbol:
                                        try:
                                            bestAsk = float(d.get('best_ask_price') or 0.0)
                                        except:
                                            bestAsk = 0.0
                                        try:
                                            bestBid = float(d.get('best_bid_price') or 0.0)
                                        except:
                                            bestBid = 0.0
                                        async with coinex_lock:
                                            coinex_ticker_data[symbol] = {'bestAsk': bestAsk, 'bestBid': bestBid}
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
                    finally:
                        ping_task.cancel()
                        try:
                            await ping_task
                        except:
                            pass
        except Exception as e:
            logger.exception("CoinEx WS ticker error, reconnecting...")
            await asyncio.sleep(3)

# WebSocket для фьючерсных индексов (mark/index)
async def coinex_ws_index():
    while True:
        try:
            while not coinex_funding_data:
                await asyncio.sleep(1)
            symbols = list(coinex_funding_data.keys())
            url = 'wss://socket.coinex.com/v2/futures'
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url) as ws:
                    async with coinex_lock:
                        coinex_index_data.clear()
                    subs = {
                        "method": "index.subscribe",
                        "params": {"market_list": symbols},
                        "id": 2
                    }
                    await ws.send_str(json.dumps(subs))
                    logger.info("CoinEx WS index connected, subscribed to %d symbols", len(symbols))
                    ping_task = asyncio.create_task(coinex_send_ping(ws, 2))
                    try:
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                data = gzip.decompress(msg.data).decode('utf-8')
                                obj = json.loads(data)
                                d = obj.get('data')
                                if d and isinstance(d, dict):
                                    symbol = d.get('market')
                                    if symbol:
                                        try:
                                            markPrice = float(d.get('mark_price') or 0.0)
                                            indexPrice = float(d.get('index_price') or 0.0)
                                        except:
                                            markPrice = 0.0
                                            indexPrice = 0.0
                                        async with coinex_lock:
                                            coinex_index_data[symbol] = {'markPrice': markPrice, 'indexPrice': indexPrice}
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
                    finally:
                        ping_task.cancel()
                        try:
                            await ping_task
                        except:
                            pass
        except Exception as e:
            logger.exception("CoinEx WS index error, reconnecting...")
            await asyncio.sleep(3)

# WebSocket для спотовых тикеров (bbo)
async def coinex_ws_spot():
    while True:
        try:
            # Ждём, пока появятся спотовые символы
            while not coinex_spot_symbols:
                await asyncio.sleep(1)
            symbols = coinex_spot_symbols.copy()
            # Можно разбить на части, если список большой (как в старом коде)
            # Просто отправим все в одной подписке
            url = 'wss://socket.coinex.com/v2/spot'
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url) as ws:
                    async with coinex_lock:
                        coinex_spot_data.clear()
                    subs = {
                        "method": "bbo.subscribe",
                        "params": {"market_list": symbols},
                        "id": 3
                    }
                    await ws.send_str(json.dumps(subs))
                    logger.info("CoinEx WS spot connected, subscribed to %d symbols", len(symbols))
                    ping_task = asyncio.create_task(coinex_send_ping(ws, 3))
                    try:
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                data = gzip.decompress(msg.data).decode('utf-8')
                                obj = json.loads(data)
                                d = obj.get('data')
                                if d and isinstance(d, dict):
                                    symbol = d.get('market')
                                    if symbol:
                                        try:
                                            bestAsk = float(d.get('best_ask_price') or 0.0)
                                            bestBid = float(d.get('best_bid_price') or 0.0)
                                        except:
                                            bestAsk = 0.0
                                            bestBid = 0.0
                                        async with coinex_lock:
                                            coinex_spot_data[symbol] = {'bestAsk': bestAsk, 'bestBid': bestBid}
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
                    finally:
                        ping_task.cancel()
                        try:
                            await ping_task
                        except:
                            pass
        except Exception as e:
            logger.exception("CoinEx WS spot error, reconnecting...")
            await asyncio.sleep(3)

# HTTP сборщик CoinEx
# HTTP сборщик CoinEx
async def coinex_collect_once(session, use_proxy_toggle=False):
    proxy = PROXY if use_proxy_toggle else None
    funding_url = 'https://api.coinex.com/v2/futures/funding-rate'
    spot_url = 'https://api.coinex.com/v2/spot/ticker'

    # Добавляем запрос к фьючерсному тикеру для получения volume_24h
    funding_resp, spot_resp, fut_ticker_resp = await asyncio.gather(
        fetch_json(session, funding_url, proxy=proxy, timeout=12),
        fetch_json(session, spot_url, proxy=proxy, timeout=12),
        fetch_json(session, COINEX_FUT_TICKER_URL, proxy=proxy, timeout=12)
    )

    # Обновляем funding данные
    if funding_resp and funding_resp.get('code') == 0:
        for item in funding_resp.get('data', []):
            market = item.get('market')
            if market and 'USDT' in market:
                async with coinex_lock:
                    coinex_funding_data[market] = {
                        'latest_funding_rate': float(item.get('latest_funding_rate', 0)),
                        'next_funding_rate': float(item.get('next_funding_rate', 0)),
                        'latest_funding_time': item.get('latest_funding_time'),
                        'next_funding_time': item.get('next_funding_time')
                    }

    # Обновляем список спотовых символов
    spot_symbols = []
    spot_volume_map = {}
    if spot_resp and spot_resp.get('code') == 0:
        for item in spot_resp.get('data', []):
            market = item.get('market')
            if market and 'USDT' in market:
                spot_symbols.append(market)
                vol = item.get('value') or 0.0  # объём в USD
                try:
                    vol = float(vol)
                except:
                    vol = 0.0
                spot_volume_map[market] = vol
        async with coinex_lock:
            coinex_spot_symbols[:] = spot_symbols

    # Извлекаем объём за 24ч из фьючерсного тикера
    volume_map = {}
    if fut_ticker_resp and fut_ticker_resp.get('code') == 0:
        for item in fut_ticker_resp.get('data', []):
            market = item.get('market')
            if market and 'USDT' in market:
                vol = item.get('value') or item.get('volume') or 0.0
                try:
                    vol = float(vol)
                except:
                    vol = 0.0
                volume_map[market] = vol

    # Формируем data_usdt из WS данных + funding
    data_usdt = []
    market_meta = {}

    async with coinex_lock:
        ticker = coinex_ticker_data.copy()
        index = coinex_index_data.copy()
        funding = coinex_funding_data.copy()

    for sym, fund_info in funding.items():
        tick = ticker.get(sym)
        if tick is None:
            continue
        bestBid = tick.get('bestBid', 0.0)
        bestAsk = tick.get('bestAsk', 0.0)

        idx = index.get(sym)
        if idx is None:
            continue
        markPrice = idx.get('markPrice', 0.0)
        indexPrice = idx.get('indexPrice', 0.0)

        latest_funding = fund_info.get('latest_funding_rate', 0.0)
        next_funding = fund_info.get('next_funding_rate', 0.0)

        # index_corr
        try:
            index_corr = round(((markPrice / indexPrice) - 1) * 100, 2) if indexPrice else 0.0
        except:
            index_corr = 0.0

        # fundingInterval (вычисляем по разнице между next и latest funding times)
        lft = fund_info.get('latest_funding_time')
        nft = fund_info.get('next_funding_time')
        fundingInterval = 8
        if nft and lft:
            try:
                # разница в секундах / 3600 = часы
                diff_hours = (int(nft) - int(lft)) / 1000 / 3600
                if diff_hours in (1, 2, 4, 8):
                    fundingInterval = int(diff_hours)
                else:
                    # fallback по часу nextFundingTime
                    fundingTime = int(int(nft) / 1000)
                    hourTime = int(datetime.fromtimestamp(fundingTime).hour)
                    if hourTime in (3, 11, 19):
                        fundingInterval = 8
                    elif hourTime in (7, 15, 23):
                        fundingInterval = 4
                    elif hourTime in (5, 13, 21):
                        fundingInterval = 2
                    else:
                        fundingInterval = 1
            except:
                pass

        # Формат: [symbol, funding%, bestBid, nextFunding%, index_corr, 0, bestAsk, 0]
        data_usdt.append([
            sym,
            round(latest_funding * 100, 2),
            bestBid,
            round(next_funding * 100, 2),
            index_corr,
            0,
            bestAsk,
            0
        ])

        # Берём объём из volume_map
        amount24 = volume_map.get(sym, 0.0)

        market_meta[sym] = {
            'fundingInterval': fundingInterval,
            'fee': 0.05,
            'predict': '-',
            'bestBid': bestBid,
            'bestAsk': bestAsk,
            'index_corr': index_corr,
            'amount24': round(amount24)  # округляем до целых, как в других биржах
        }

    # Спотовые данные
    data_spot = {}
    async with coinex_lock:
        spot = coinex_spot_data.copy()
    for sym, vals in spot.items():
        if 'USDT' in sym:
            bid = vals.get('bestBid', 0.0)
            ask = vals.get('bestAsk', 0.0)
            data_spot[sym] = [sym, bid, ask]
            # Добавляем объём в market_meta, если символ уже есть (фьючерсный)
            vol_spot = spot_volume_map.get(sym, 0.0)
            if sym in market_meta:
                market_meta[sym]['amount24_spot'] = round(vol_spot)

    msg = {
        'market': 'CoinEx',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)
    logger.debug("CoinEx: sent %d futs / %d spots", len(data_usdt), len(data_spot))

# Основной цикл CoinEx
async def coinex_loop():
    # Первоначальный запрос, чтобы получить списки символов и запустить WS
    async with aiohttp.ClientSession() as session:
        # Запрашиваем funding
        funding_resp = await fetch_json(session, 'https://api.coinex.com/v2/futures/funding-rate', timeout=12)
        if funding_resp and funding_resp.get('code') == 0:
            for item in funding_resp.get('data', []):
                market = item.get('market')
                if market and 'USDT' in market:
                    async with coinex_lock:
                        coinex_funding_data[market] = {
                            'latest_funding_rate': float(item.get('latest_funding_rate', 0)),
                            'next_funding_rate': float(item.get('next_funding_rate', 0)),
                            'next_funding_time': item.get('latest_funding_time')
                        }

        # Запрашиваем спот для списка символов
        spot_resp = await fetch_json(session, 'https://api.coinex.com/v2/spot/ticker', timeout=12)
        spot_symbols = []
        if spot_resp and spot_resp.get('code') == 0:
            for item in spot_resp.get('data', []):
                market = item.get('market')
                if market and 'USDT' in market:
                    spot_symbols.append(market)
        async with coinex_lock:
            coinex_spot_symbols[:] = spot_symbols

        # Запускаем WS-воркеры, если есть данные
        if coinex_funding_data:
            asyncio.create_task(coinex_ws_ticker())
            asyncio.create_task(coinex_ws_index())
        if coinex_spot_symbols:
            asyncio.create_task(coinex_ws_spot())

        # Основной цикл HTTP
        use_toggle = False
        while True:
            try:
                await coinex_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                logger.exception("CoinEx collector error: %s", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP)

# WEEX
async def weex_fetch_contract_limits():
    """
    Периодически обновляет лимиты контрактов из exchangeInfo.
    Структура ответа: /capi/v3/market/exchangeInfo
    """
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                data = await fetch_json(session, WEEX_EXCHANGE_INFO_URL, timeout=12)
                if data and isinstance(data, dict):
                    symbols = data.get('symbols', [])
                    for contract in symbols:
                        symbol = contract.get('symbol', '')
                        if 'USDT' in symbol:
                            weex_contract_limits[symbol] = {
                                'minOrderSize': float(contract.get('minOrderSize', 0)),
                                'maxOrderSize': float(contract.get('maxOrderSize', 0)),
                                'maxPositionSize': float(contract.get('maxPositionSize', 0)),
                                'contractVal': float(contract.get('contractVal', 0)),
                                'takerFeeRate': float(contract.get('takerFeeRate', 0)),
                                'makerFeeRate': float(contract.get('makerFeeRate', 0)),
                            }
                    logger.debug(f"WEEX: обновлено {len(weex_contract_limits)} контрактов")
            except Exception as e:
                logger.warning(f"WEEX limits error: {e}")
            await asyncio.sleep(60)  # обновляем раз в минуту


async def weex_collect_once(session, use_proxy_toggle=False):
    """
    Сбор данных с WEEX:
    - Фьючерсы: 24hr ticker + premiumIndex (funding/mark/index) + bookTicker (best bid/ask)
    - Спот: bookTicker (best bid/ask) + 24hr (объём)
    """
    proxy = PROXY if use_proxy_toggle else None

    # Параллельные запросы для фьючерсов
    ticker_task = asyncio.create_task(fetch_json(session, WEEX_FUT_TICKER_URL, proxy=proxy, timeout=12))
    funding_task = asyncio.create_task(fetch_json(session, WEEX_FUNDING_URL, proxy=proxy, timeout=12))
    book_task = asyncio.create_task(fetch_json(session, WEEX_BOOK_URL, proxy=proxy, timeout=12))

    # Параллельные запросы для спота
    spot_book_task = asyncio.create_task(fetch_json(session, WEEX_SPOT_BOOK_URL, proxy=proxy, timeout=12))
    spot_24hr_task = asyncio.create_task(fetch_json(session, WEEX_SPOT_24HR_URL, proxy=proxy, timeout=12))

    ticker_json, funding_json, book_json, spot_book_json, spot_24hr_json = await asyncio.gather(
        ticker_task, funding_task, book_task, spot_book_task, spot_24hr_task
    )

    data_usdt = []
    market_meta = {}
    data_spot = {}

    # ---- Построение карт для быстрого доступа ----

    # 1. Карта фандинга: symbol -> {funding_rate, mark_price, index_price, next_funding_time, collect_cycle}
    funding_map = {}
    try:
        if isinstance(funding_json, list):
            for item in funding_json:
                symbol = item.get('symbol', '')
                if symbol and 'USDT' in symbol:
                    funding_map[symbol] = {
                        'fundingRate': float(item.get('lastFundingRate', 0) or 0),
                        'forecastFundingRate': float(item.get('forecastFundingRate', 0) or 0),
                        'markPrice': float(item.get('markPrice', 0) or 0),
                        'indexPrice': float(item.get('indexPrice', 0) or 0),
                        'nextFundingTime': int(item.get('nextFundingTime', 0) or 0),
                        'collectCycle': int(item.get('collectCycle', 0) or 0),  # в минутах
                        'time': int(item.get('time', 0) or 0),
                    }
    except Exception:
        pass

    # 2. Карта bookTicker: symbol -> (bidPrice, bidQty, askPrice, askQty)
    book_map = {}
    try:
        if isinstance(book_json, list):
            for item in book_json:
                symbol = item.get('symbol', '')
                if symbol and 'USDT' in symbol:
                    book_map[symbol] = {
                        'bidPrice': float(item.get('bidPrice', 0) or 0),
                        'bidQty': float(item.get('bidQty', 0) or 0),
                        'askPrice': float(item.get('askPrice', 0) or 0),
                        'askQty': float(item.get('askQty', 0) or 0),
                        'time': int(item.get('time', 0) or 0),
                    }
    except Exception:
        pass

    # 3. Карта 24hr ticker: symbol -> {lastPrice, volume, quoteVolume, markPrice, indexPrice, ...}
    ticker_map = {}
    try:
        if isinstance(ticker_json, list):
            for item in ticker_json:
                symbol = item.get('symbol', '')
                if symbol and 'USDT' in symbol:
                    ticker_map[symbol] = {
                        'lastPrice': float(item.get('lastPrice', 0) or 0),
                        'volume': float(item.get('volume', 0) or 0),
                        'quoteVolume': float(item.get('quoteVolume', 0) or 0),
                        'markPrice': float(item.get('markPrice', 0) or 0),
                        'indexPrice': float(item.get('indexPrice', 0) or 0),
                        'highPrice': float(item.get('highPrice', 0) or 0),
                        'lowPrice': float(item.get('lowPrice', 0) or 0),
                        'openPrice': float(item.get('openPrice', 0) or 0),
                        'priceChangePercent': float(item.get('priceChangePercent', 0) or 0),
                    }
    except Exception:
        pass

    # 4. Спотовый bookTicker: symbol -> (bidPrice, askPrice)
    spot_book_map = {}
    try:
        if isinstance(spot_book_json, list):
            for item in spot_book_json:
                symbol = item.get('symbol', '')
                if symbol and 'USDT' in symbol:
                    spot_book_map[symbol] = {
                        'bidPrice': float(item.get('bidPrice', 0) or 0),
                        'askPrice': float(item.get('askPrice', 0) or 0),
                    }
    except Exception:
        pass

    # 5. Спотовый 24hr: symbol -> quoteVolume
    spot_volume_map = {}
    try:
        if isinstance(spot_24hr_json, list):
            for item in spot_24hr_json:
                symbol = item.get('symbol', '')
                if symbol and 'USDT' in symbol:
                    spot_volume_map[symbol] = float(item.get('quoteVolume', 0) or 0)
    except Exception:
        pass

    # ---- Формирование data_usdt (фьючерсы) ----
    for symbol, funding_info in funding_map.items():
        try:
            book_info = book_map.get(symbol, {})
            ticker_info = ticker_map.get(symbol, {})

            bid = book_info.get('bidPrice', 0) or ticker_info.get('lastPrice', 0)
            ask = book_info.get('askPrice', 0) or ticker_info.get('lastPrice', 0)

            funding_rate = funding_info.get('fundingRate', 0) * 100
            funding_rate = round(funding_rate, 2)

            forecast = funding_info.get('forecastFundingRate', 0) * 100
            forecast = round(forecast, 2)

            mark_price = funding_info.get('markPrice', 0) or ticker_info.get('markPrice', 0)
            index_price = funding_info.get('indexPrice', 0) or ticker_info.get('indexPrice', 0)

            if index_price and index_price != 0:
                index_corr = round(((mark_price / index_price) - 1) * 100, 2)
            else:
                index_corr = 0.0

            # fundingInterval (как у вас)
            collect_cycle_min = funding_info.get('collectCycle', 0)
            if collect_cycle_min:
                funding_interval = collect_cycle_min // 60
                if funding_interval <= 0:
                    funding_interval = 1
            else:
                next_time = funding_info.get('nextFundingTime', 0)
                if next_time:
                    hour = int(datetime.fromtimestamp(next_time / 1000).hour)
                    if hour in (3, 11, 19):
                        funding_interval = 8
                    elif hour in (7, 15, 23):
                        funding_interval = 4
                    elif hour in (5, 13, 21):
                        funding_interval = 2
                    else:
                        funding_interval = 1
                else:
                    funding_interval = 8

            amount24 = ticker_info.get('quoteVolume', 0)

            # ===== НОВАЯ ПРОВЕРКА =====
            if amount24 == 0:
                # можно также проверить bid и ask > 0, если нужно
                # if bid == 0 or ask == 0:
                #     continue
                continue  # пропускаем этот символ

            # --- теперь добавляем ---
            data_usdt.append([symbol, funding_rate, bid, 0, index_corr, 0, ask, 0])

            limits = weex_contract_limits.get(symbol, {})
            market_meta[symbol] = {
                'fundingInterval': funding_interval,
                'fee': limits.get('takerFeeRate', 0.06) * 100,
                'predict': str(forecast) if forecast else '-',
                'bestBid': bid,
                'bestAsk': ask,
                'index_corr': index_corr,
                'amount24': round(amount24),
                'minOrderSize': limits.get('minOrderSize', 0),
                'maxOrderSize': limits.get('maxOrderSize', 0),
                'contractVal': limits.get('contractVal', 0),
                'nextFundingTime': funding_info.get('nextFundingTime', 0),
            }

        except Exception as e:
            logger.warning(f"WEEX futures error for {symbol}: {e}")
            continue
    # ---- Формирование data_spot (спот) ----

    for symbol, book_info in spot_book_map.items():
        try:
            bid = book_info.get('bidPrice', 0)
            ask = book_info.get('askPrice', 0)
            data_spot[symbol] = [symbol, bid, ask]

            # Добавляем объём в market_meta, если символ уже есть (фьючерсный)
            if symbol in market_meta:
                vol = spot_volume_map.get(symbol, 0)
                market_meta[symbol]['amount24_spot'] = round(vol)
            else:
                # Если символа нет в фьючерсах, создаём базовую запись
                vol = spot_volume_map.get(symbol, 0)
                market_meta[symbol] = {
                    'fundingInterval': 0,
                    'fee': 0.1,
                    'predict': '-',
                    'bestBid': bid,
                    'bestAsk': ask,
                    'index_corr': 0.0,
                    'amount24': 0,
                    'amount24_spot': round(vol),
                }

        except Exception as e:
            logger.warning(f"WEEX spot error for {symbol}: {e}")
            continue

    # ---- Отправка сообщения ----

    msg = {
        'market': 'WEEX',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)
    logger.debug(f"WEEX: отправлено {len(data_usdt)} фьючерсов / {len(data_spot)} спотов")


async def weex_loop():
    """
    Основной цикл сборщика WEEX.
    Запускает фоновую задачу для обновления лимитов и основной сбор данных.
    """
    use_toggle = False

    # Запускаем фоновое обновление лимитов контрактов
    asyncio.create_task(weex_fetch_contract_limits())

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await weex_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                logger.exception(f"WEEX collector error: {e}")
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP)


# ===== Phemex =====================================================
async def phemex_update_products(session):
    """
    Загружает /public/products и заполняет phemex_spot_scales.
    Для спотовых символов (type = 'Spot') берём priceScale.
    Символы нормализуются (убирается 's' в начале).
    """
    global phemex_spot_scales
    try:
        data = await fetch_json(session, PHEMEX_PRODUCTS_URL, timeout=12)
        if not data or 'result' not in data:
            return
        products = data.get('result', {}).get('products', [])
        new_scales = {}
        for prod in products:
            if prod.get('type') != 'Spot':
                continue
            symbol = prod.get('symbol', '')
            if not symbol or 'USDT' not in symbol:
                continue
            # Нормализуем символ так же, как в collector'е
            norm = symbol.upper().replace('_', '').replace('-', '')
            if norm.startswith('S') and norm[1:].endswith('USDT'):
                norm = norm[1:]
            price_scale = prod.get('priceScale', 0)
            if price_scale:
                new_scales[norm] = 10 ** price_scale  # 10^priceScale
        async with phemex_scales_lock:
            phemex_spot_scales = new_scales
        logger.debug(f"Phemex: loaded {len(new_scales)} spot scales")
    except Exception as e:
        logger.warning(f"Phemex: failed to load products: {e}")

async def phemex_scales_updater(session):
    """Фоновая задача: обновляет масштабы каждые 10 минут."""
    while True:
        await phemex_update_products(session)
        await asyncio.sleep(600)  # 10 минут

async def phemex_collect_once(session, use_proxy_toggle=False):
    """
    Сбор данных с Phemex.
    - Фьючерсы: /md/v3/ticker/24hr/all
    - Спот: /md/v3/spot/ticker/24hr/all (масштабированные данные)
    - Реальные ставки финансирования: /contract-biz/public/real-funding-rates
    - Масштабы спота: /public/products (обновляются раз в 10 минут)
    """
    proxy = PROXY if use_proxy_toggle else None

    # Если словарь масштабов пуст, загрузим при первом вызове (на случай, если updater ещё не запущен)
    global phemex_spot_scales
    if not phemex_spot_scales:
        await phemex_update_products(session)

    fut_task = asyncio.create_task(fetch_json(session, PHEMEX_FUT_TICKER_URL, proxy=proxy, timeout=12))
    spot_task = asyncio.create_task(fetch_json(session, PHEMEX_SPOT_TICKER_URL, proxy=proxy, timeout=12))
    funding_task = asyncio.create_task(fetch_json(session, PHEMEX_REAL_FUNDING_URL, proxy=proxy, timeout=12))

    fut_json, spot_json, funding_json = await asyncio.gather(fut_task, spot_task, funding_task)

    data_usdt = []
    market_meta = {}
    data_spot = {}

    # ---- Обработка реальных ставок финансирования ----
    funding_map = {}
    try:
        if isinstance(funding_json, dict):
            rows = funding_json.get('data', {}).get('rows', [])
            for item in rows:
                symbol = item.get('symbol', '')
                if symbol and 'USDT' in symbol:
                    symbol = _norm_sym(symbol)
                    if symbol.startswith('S') and symbol[1:].endswith('USDT'):
                        symbol = symbol[1:]
                    funding_interval_sec = int(item.get('fundingInterval', 0))
                    funding_interval_hours = (funding_interval_sec // 3600) if funding_interval_sec > 0 else 8
                    funding_map[symbol] = {
                        'fundingInterval': funding_interval_hours,
                        'nextFundingTime': int(item.get('nextfundingTime', 0)),
                        'fundingRate': float(item.get('fundingRate', 0)),
                    }
    except Exception as e:
        logger.warning(f"Phemex: error parsing real-funding-rates: {e}")

    # ---- Обработка фьючерсных тикеров ----
    try:
        if fut_json and isinstance(fut_json, dict):
            result = fut_json.get('result')
            if isinstance(result, list):
                for item in result:
                    try:
                        raw_sym = item.get('symbol', '')
                        if not raw_sym or 'USDT' not in raw_sym:
                            continue
                        sym = _norm_sym(raw_sym)
                        if sym.startswith('S') and sym[1:].endswith('USDT'):
                            sym = sym[1:]

                        funding_rate = float(item.get('fundingRateRr', 0) or 0) * 100
                        funding_rate = round(funding_rate, 2)

                        pred_funding = float(item.get('predFundingRateRr', 0) or 0) * 100
                        pred_funding = round(pred_funding, 2)

                        bestBid = float(item.get('bidRp', 0) or 0)
                        bestAsk = float(item.get('askRp', 0) or 0)

                        markPrice = float(item.get('markRp', 0) or 0)
                        indexPrice = float(item.get('indexRp', 0) or 0)

                        if indexPrice and indexPrice != 0:
                            index_corr = round(((markPrice / indexPrice) - 1) * 100, 2)
                        else:
                            index_corr = 0.0

                        amount24 = round(float(item.get('turnoverRv', 0) or 0))
                        if amount24 == 0:
                            continue

                        fund_info = funding_map.get(sym, {})
                        funding_interval = fund_info.get('fundingInterval', 8)
                        next_funding_time = fund_info.get('nextFundingTime', 0)

                        data_usdt.append([
                            sym,
                            funding_rate,
                            bestBid,
                            0,
                            index_corr,
                            0,
                            bestAsk,
                            0
                        ])

                        market_meta[sym] = {
                            'fundingInterval': funding_interval,
                            'fee': 0.06,
                            'predict': str(pred_funding) if pred_funding else '-',
                            'bestBid': bestBid,
                            'bestAsk': bestAsk,
                            'index_corr': index_corr,
                            'amount24': amount24,
                            'markPrice': markPrice,
                            'indexPrice': indexPrice,
                            'nextFundingTime': next_funding_time,
                        }

                    except Exception as e:
                        logger.warning(f"Phemex futures error for {item.get('symbol')}: {e}")
                        continue
    except Exception as e:
        logger.exception("Phemex futures: error parsing response")

    # ---- Обработка спотовых тикеров ----
    try:
        if spot_json and isinstance(spot_json, dict):
            result = spot_json.get('result')
            if isinstance(result, list):
                for item in result:
                    try:
                        raw_sym = item.get('symbol', '')
                        if not raw_sym or 'USDT' not in raw_sym:
                            continue
                        sym = _norm_sym(raw_sym)
                        if sym.startswith('S') and sym[1:].endswith('USDT'):
                            sym = sym[1:]

                        async with phemex_scales_lock:
                            scale = phemex_spot_scales.get(sym, 100_000_000)
                        bid = float(item.get('bidEp', 0) or 0) / scale
                        ask = float(item.get('askEp', 0) or 0) / scale

                        data_spot[sym] = [sym, bid, ask]

                        vol = round(float(item.get('turnoverEv', 0) or 0) / scale)
                        if sym in market_meta:
                            market_meta[sym]['amount24_spot'] = vol
                        else:
                            market_meta[sym] = {
                                'fundingInterval': 0,
                                'fee': 0.1,
                                'predict': '-',
                                'bestBid': bid,
                                'bestAsk': ask,
                                'index_corr': 0.0,
                                'amount24': 0,
                                'amount24_spot': vol,
                            }

                    except Exception as e:
                        logger.warning(f"Phemex spot error for {item.get('symbol')}: {e}")
                        continue
    except Exception as e:
        logger.exception("Phemex spot: error parsing response")

    msg = {
        'market': 'Phemex',
        'data_usdt': data_usdt,
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)
    logger.debug(f"Phemex: отправлено {len(data_usdt)} фьючерсов / {len(data_spot)} спотовых")


async def phemex_loop():
    """Основной цикл сборщика Phemex."""
    use_toggle = False
    async with aiohttp.ClientSession() as session:
        # Запускаем фоновую задачу для обновления масштабов каждые 10 минут
        asyncio.create_task(phemex_scales_updater(session))
        # Первичная загрузка масштабов
        await phemex_update_products(session)
        while True:
            try:
                await phemex_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                logger.exception(f"Phemex collector error: {e}")
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP)


async def binance_alpha_collect_once(session, use_proxy_toggle=False):
    """
    Binance Alpha – только спотовые токены.
    Ответ содержит список токенов с полями symbol, price, volume24h.
    Цена используется и как bid, и как ask (стакан отсутствует).
    """
    proxy = PROXY if use_proxy_toggle else None
    data = await fetch_json(session, BINANCE_ALPHA_URL, proxy=proxy, timeout=12)

    data_spot = {}
    market_meta = {}

    if data and isinstance(data, dict):
        tokens = data.get('data', [])
        skipped_offline = 0
        skipped_noprice = 0
        for item in tokens:
            try:
                # Пропускаем оффлайн / делистнутые / скрытые токены
                if item.get('offline') or item.get('fullyDelisted') or item.get('cexOffDisplay'):
                    skipped_offline += 1
                    continue

                raw_symbol = item.get('symbol', '')
                if not raw_symbol:
                    continue
                sym = (raw_symbol + 'USDT').upper().replace('-', '').replace('_', '')
                try:
                    price = float(item.get('price', 0) or 0)
                except Exception:
                    price = 0.0
                if price <= 0:
                    skipped_noprice += 1
                    continue
                try:
                    vol24 = float(item.get('volume24h', 0) or 0)
                except Exception:
                    vol24 = 0.0

                data_spot[sym] = [sym, price, price]

                market_meta[sym] = {
                    'amount24_spot': round(vol24, 2),
                    'contract_address': item.get('contractAddress', ''),
                    'chain_name': item.get('chainName', 'bsc').lower(),
                    'alpha_id': item.get('alphaId', ''),
                }
            except Exception:
                logger.warning("BinanceAlpha: failed to process item %s", item.get('symbol'))
                continue

    msg = {
        'market': 'BinanceAlpha',
        'data_usdt': [],
        'data_spot': data_spot,
        'market_meta': market_meta,
        'ts': time.time()
    }
    send_msg(msg)
    logger.debug("BinanceAlpha: sent %d spots, skipped %d offline, %d no-price",
                 len(data_spot), skipped_offline, skipped_noprice)


async def binance_alpha_loop():
    use_toggle = False
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await binance_alpha_collect_once(session, use_proxy_toggle=use_toggle)
            except Exception as e:
                logger.exception("BinanceAlpha collector error: %s", e)
            use_toggle = not use_toggle
            await asyncio.sleep(SLEEP)   # используем общий SLEEP


# Run both collectors together
async def main():
    await asyncio.gather(
        bybit_loop(),
        mexc_loop(),
        okx_loop(),
        binance_loop(),
        bingx_loop(),
        bitmart_loop(),
        xt_loop(),
        coinex_loop(),
        weex_loop(),
        phemex_loop(),
        binance_alpha_loop()
    )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
