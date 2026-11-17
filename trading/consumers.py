# consumers.py — updated (DEX inactivity handling + improved logging)
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
import json
import time
import os
import sys
import select
import socket
import datetime
import threading
import logging
from datetime import timezone
import re
import hashlib
import base64
import aiohttp
import redis
import orjson  # быстрый парсер
from channels.layers import get_channel_layer
CHANNEL_LAYER = get_channel_layer()

# logging setup: explicit StreamHandler to stdout so container logs capture it
logger = logging.getLogger("consumers")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

sys.path.append("..")
User = get_user_model()

def safe_group_name(prefix: str, symbol: str) -> str:
    # Убираем всё, кроме ASCII допустимых
    if re.match(r"^[\-a-zA-Z0-9_.]+$", symbol):
        return f"{prefix}_{symbol}"
    # Если в символе не только ASCII — делаем хеш
    digest = hashlib.sha1(symbol.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"
# -------------------------
# Конфиги / глобалы
# -------------------------
MONGO_HOST = os.getenv('MONGO_HOST', 'mongodb')
MONGO_PORT = int(os.getenv('MONGO_PORT', '27017'))

REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))

# Timeouts
TIMEOUT = aiohttp.ClientTimeout(total=15)

# глобальный redis клиент (переиспользуется)
_redis_client_db2 = None

def get_redis_db2():
    global _redis_client_db2
    if _redis_client_db2 is None:
        _redis_client_db2 = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=2, decode_responses=True)
    return _redis_client_db2

async def dex_gc_loop():
    while True:
        async with dex_lock:
            for symbol, task in list(dex_tasks.items()):
                if task.done() or task.cancelled():
                    dex_tasks.pop(symbol, None)
                    dex_subscribers.pop(symbol, None)
        await asyncio.sleep(600)

# -------------------------
# Mongo клиент
# -------------------------
from motor.motor_asyncio import AsyncIOMotorClient
mongo_client = AsyncIOMotorClient(f"mongodb://{MONGO_HOST}:{MONGO_PORT}")
mongo_db = mongo_client["funding"]

# FIX: используем async context manager для find() — предотвращает утечку курсоров
async def fetch_coin_history_mongo_async(collection_name, exchange_name, coin_symbol):
    collection = mongo_db[collection_name]
    result = []
    async with collection.find(
        {"exchange_name": exchange_name, "symbol": coin_symbol},
        {"ask": 1, "bid": 1, "datetime": 1, "_id": 0}
    ) as cursor:
        async for doc in cursor:
            result.append((doc['ask'], doc['bid'], doc['datetime']))
    return result

# -------------------------
# Unix-socket / send queue (ваша старая логика) — оставлена
# -------------------------
lock = asyncio.Lock()
sync_lock = threading.Lock()

checkIsRun = False
socket_data = {}

# -------------------------
# DEX shared pollers (symbol -> subscribers set + symbol -> task)
# -------------------------
dex_subscribers: dict[str, set] = {}   # symbol -> set of channel_name
dex_tasks: dict[str, asyncio.Task] = {}  # symbol -> asyncio.Task
dex_lock = asyncio.Lock()  # защита для dex_subscribers/dex_tasks


def send_data_to_unix_socket(data):
    try:
        unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        unix_socket.connect('./from')
        unix_socket.send(json.dumps(data).encode('utf-8'))
        unix_socket.close()
    except Exception:
        logger.exception("send_data_to_unix_socket failed")

send_queue = asyncio.Queue()

async def socket_sender(path='./from'):
    while True:
        data = await send_queue.get()
        try:
            reader, writer = await asyncio.open_unix_connection(path)
            writer.write(json.dumps(data).encode('utf-8'))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        except Exception:
            logger.exception("socket_sender error")

def check_data_sockets():
    global socket_data, checkIsRun
    while True:
        try:
            checkIsRun = True
            try:
                server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                server_socket.bind('./data')
                server_socket.listen(1)
            except Exception:
                try:
                    if os.path.exists('./data'):
                        os.remove('./data')
                except Exception:
                    checkIsRun = False
                continue
            else:
                server_socket.setblocking(False)
                try:
                    while True:
                        try:
                            ready_to_read, _, _ = select.select([server_socket], [], [], 0.1)
                            for sock in ready_to_read:
                                connection, _ = sock.accept()
                                try:
                                    while True:
                                        received_data = connection.recv(8192).decode('utf-8')
                                        if received_data:
                                            nested_list = json.loads(received_data)
                                            if nested_list is not None:
                                                key = f'{nested_list["m1"]}_{nested_list["m2"]}_{nested_list["post_coin"]}_{nested_list["sp_or_ft"]}'
                                                socket_data[key] = nested_list
                                        else:
                                            break
                                except KeyboardInterrupt:
                                    connection.close()
                                    server_socket.close()
                                    checkIsRun = False
                        except Exception:
                            checkIsRun = False
                except KeyboardInterrupt:
                    server_socket.close()
                    checkIsRun = False
                finally:
                    server_socket.close()
                    checkIsRun = False
        except Exception:
            logger.exception('glob exception in check_data_sockets')

# -------------------------
# Утилиты
# -------------------------
def calculate_effective_price(order_book, trade_quantity):
    try:
        total_cost = 0
        total_volume = 0
        remaining_quantity = trade_quantity
        for price, amount in order_book:
            price = float(price)
            amount = float(amount)
            if remaining_quantity <= amount:
                partial_volume = remaining_quantity / price
                total_cost += remaining_quantity
                total_volume += partial_volume
                return total_cost / total_volume if total_volume else None
            else:
                total_cost += amount
                total_volume += amount / price
                remaining_quantity -= amount
        return None
    except Exception:
        return None

clearIsRun = False
def clear_socket_data():
    global socket_data, clearIsRun
    clearIsRun = True
    while True:
        time.sleep(5)
        try:
            for k, v in list(socket_data.items()):
                if (float(datetime.datetime.timestamp(datetime.datetime.now())) - float(v.get('current_time', 0))) > 10:
                    socket_data.pop(k, None)
        except Exception:
            logger.exception("clear_socket_data error")

# -------------------------
# Multipliers (in-memory) + kucoin token
# -------------------------
mexc_amounts = {}
gateio_amounts = {}
huobi_amounts = {}
okx_amounts = {}
kucoin_amounts = {}
bitmart_amounts = {}
poloniex_amounts = {}
lbank_amounts = {}
xt_amounts = {}
#coinex_amounts = {}
coins_list_full = {}

mexc_lock = asyncio.Lock()
gateio_lock = asyncio.Lock()
huobi_lock = asyncio.Lock()
okx_lock = asyncio.Lock()
kucoin_lock = asyncio.Lock()
bitmart_lock = asyncio.Lock()
poloniex_lock = asyncio.Lock()
lbank_lock = asyncio.Lock()
xt_lock = asyncio.Lock()
coins_lock = asyncio.Lock()
#coinex_lock = asyncio.Lock()

token_kucoin = None
token_kucoin_lock = asyncio.Lock()

# -------------------------
# Async helpers for HTTP
# -------------------------
async def fetch_json(session, url, name):
    try:
        async with session.get(url, timeout=TIMEOUT) as resp:
            return await resp.json()
    except asyncio.TimeoutError:
        logger.warning(f"[Timeout] {name} API did not respond in time")
    except Exception:
        logger.exception(f"[Error] {name} API")
    return None

async def fetch_json_huobi(session, url, name):
    try:
        async with session.get(url, timeout=TIMEOUT) as resp:
            text = await resp.text()
            return json.loads(text)
    except asyncio.TimeoutError:
        logger.warning(f"[Timeout] {name} API did not respond in time")
    except Exception:
        logger.exception(f"[Error] {name} API")
    return None

# -------------------------
# make_requests() — ваш код портирован
# -------------------------
async def make_requests():
    global mexc_amounts, gateio_amounts, huobi_amounts, okx_amounts
    global kucoin_amounts, bitmart_amounts, poloniex_amounts, coins_list_full, lbank_amounts, xt_amounts
   # global coinex_amounts
    logger.info('[make_requests] start')
    urls = {
        "mexc": "https://contract.mexc.com/api/v1/contract/detail",
        "gateio": "https://api.gateio.ws/api/v4/futures/usdt/contracts",
        "huobi": "https://api.hbdm.com/linear-swap-api/v1/swap_contract_info?business_type=swap",
        "okx": "https://www.okx.com/api/v5/public/instruments?instType=SWAP",
        "kucoin": "https://api-futures.kucoin.com/api/v1/contracts/active",
        "bitmart": "https://api-cloud-v2.bitmart.com/contract/public/details",
        "poloniex": "https://futures-api.poloniex.com/api/v1/contracts/active",
        "lbank": "https://lbkperp.lbank.com/cfd/openApi/v1/pub/instrument?productGroup=SwapU",
        "xt": "https://fapi.xt.com/future/market/v3/public/symbol/list",
     #   "coinex": "https://api.coinex.com/v2/futures/market"
    }
    try:
        new_mexc, new_gateio, new_huobi, new_okx = {}, {}, {}, {}
        new_kucoin, new_bitmart, new_poloniex, new_coins_list = {}, {}, {}, {}
        new_lbank, new_xt = {}, {}
        #new_coinex = {}
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            # MEXC
            data = await fetch_json(session, urls["mexc"], "MEXC")
            if data:
                for res in data.get('data', []):
                    symbol = res.get('symbol','').replace('_USDT', '')
                    new_coins_list[symbol.upper()] = symbol.upper()
                    new_mexc[res.get('symbol','').replace('_USDT', 'USDT')] = res.get('contractSize')
                logger.info('[make_requests] good mexc')

            # Gate.io
            data = await fetch_json(session, urls["gateio"], "Gate.io")
            if data:
                for res in data:
                    symbol = res.get('name','').replace('_USDT', '')
                    new_coins_list[symbol.upper()] = symbol.upper()
                    new_gateio[res.get('name','').replace('_USDT', 'USDT')] = res.get('quanto_multiplier')
                logger.info('[make_requests] good gateio')

            # Huobi
            data = await fetch_json_huobi(session, urls["huobi"], "Huobi")
            if data:
                for res in data.get('data', []):
                    symbol = res.get('contract_code','').replace('-USDT', '')
                    new_coins_list[symbol.upper()] = symbol.upper()
                    new_huobi[res.get('contract_code','').replace('-USDT', 'USDT')] = res.get('contract_size')
                logger.info('[make_requests] good huobi')

            # OKX
            data = await fetch_json(session, urls["okx"], "OKX")
            if data:
                for res in data.get('data', []):
                    if 'USDT' in res.get('instFamily',''):
                        symbol = res.get('instFamily','').replace('-USDT', '')
                        new_coins_list[symbol.upper()] = symbol.upper()
                        try:
                            new_okx[res.get('instFamily','').replace('-USDT', 'USDT')] = float(res.get('ctMult', 0)) * float(res.get('ctVal', 0))
                        except Exception:
                            pass
                logger.info('[make_requests] good okx')

            # KuCoin
            data = await fetch_json(session, urls["kucoin"], "KuCoin")
            if data:
                for res in data.get('data', []):
                    if 'USDTM' in res.get('symbol',''):
                        symbol = res.get('symbol','').replace('USDTM', '')
                        new_coins_list[symbol.upper()] = symbol.upper()
                        try:
                            new_kucoin[res.get('symbol','').replace('USDTM', 'USDT')] = float(res.get('multiplier', 0))
                        except Exception:
                            pass
                logger.info('[make_requests] good kucoin')

            # Bitmart
            data = await fetch_json(session, urls["bitmart"], "Bitmart")
            if data:
                for res in data.get('data', {}).get('symbols', []):
                    new_coins_list[res.get('symbol','').upper()] = res.get('symbol','').upper()
                    new_bitmart[res.get('symbol','')] = res.get('contract_size')
                logger.info('[make_requests] good bitmart')

            # Poloniex
            data = await fetch_json(session, urls["poloniex"], "Poloniex")
            if data:
                for res in data.get('data', []):
                    if 'USDTPERP' in res.get('symbol',''):
                        symbol = res.get('symbol','').replace('USDTPERP', '')
                        new_coins_list[symbol.upper()] = symbol.upper()
                        try:
                            new_poloniex[res.get('symbol','').replace('USDTPERP', 'USDT')] = float(res.get('multiplier', 0))
                        except Exception:
                            pass
                logger.info('[make_requests] good poloniex')

            # LBank
            data = await fetch_json(session, urls["lbank"], "LBank")
            if data:
                for res in data.get('data', []):
                    if 'USDT' in res.get('symbol',''):
                        symbol = res.get('symbol','').replace('USDT', '')
                        new_coins_list[symbol.upper()] = symbol.upper()
                        try:
                            new_lbank[res.get('symbol','')] = float(res.get('priceTick', 0))
                        except Exception:
                            pass
                logger.info('[make_requests] good lbank')

            # XT
            data = await fetch_json(session, urls["xt"], "XT")
            if data:
                symbols = data.get("result", {}).get("symbols", [])
                if isinstance(symbols, list):
                    for res in symbols:
                        try:
                            if not isinstance(res, dict):
                                continue
                            symbol = (res.get("symbol") or res.get("pair") or "").lower()
                            if not symbol:
                                continue
                            # only USDT contracts
                            if "usdt" not in symbol:
                                continue
                            # normalize to BTCUSDT
                            base = symbol.replace("_usdt", "").replace("usdt", "")
                            clean_symbol = f"{base}usdt"
                            contract_size = res.get("contractSize", 0)
                            try:
                                contract_size = float(contract_size)
                            except Exception:
                                contract_size = 0
                            new_xt[clean_symbol.upper()] = contract_size
                            new_coins_list[base.upper()] = base.upper()
                        except Exception:
                            continue
                logger.info('[make_requests] good xt')

            # # CoinEx
            # data = await fetch_json(session, urls["coinex"], "CoinEx")
            # if data and data.get('code') == 0:
            #     for res in data.get('data', []):
            #         market = res.get('market', '')
            #         if not market or 'USDT' not in market:
            #             continue
            #         # Нормализуем символ (убираем USDT)
            #         base = market.replace('USDT', '')
            #         clean_symbol = market.upper()  # "BTCUSDT"
            #         new_coins_list[base.upper()] = base.upper()
            #         # Множитель: явного contractSize нет -> используем 1
            #       #  new_coinex[clean_symbol] = float(res.get('tick_size', 1))
            #         new_coinex[clean_symbol] = 1
            #     logger.info('[make_requests] good coinex')
        # Atomic swap of caches
        if new_mexc:
            async with mexc_lock:
                mexc_amounts = new_mexc
        if new_gateio:
            async with gateio_lock:
                gateio_amounts = new_gateio
        if new_huobi:
            async with huobi_lock:
                huobi_amounts = new_huobi
        if new_okx:
            async with okx_lock:
                okx_amounts = new_okx
        if new_kucoin:
            async with kucoin_lock:
                kucoin_amounts = new_kucoin
        if new_bitmart:
            async with bitmart_lock:
                bitmart_amounts = new_bitmart
        if new_poloniex:
            async with poloniex_lock:
                poloniex_amounts = new_poloniex
        if new_lbank:
            async with lbank_lock:
                lbank_amounts = new_lbank
        if new_xt:
            async with xt_lock:
                xt_amounts = new_xt
        # if new_coinex:
        #     async with coinex_lock:
        #         coinex_amounts = new_coinex

        async with coins_lock:
            coins_list_full = new_coins_list

        logger.info('[make_requests] good update multiplicators')
    except Exception:
        logger.exception('[make_requests] FATAL ERROR')

# -------------------------
# reload_multiplicators_data (background)
# -------------------------
async def reload_multiplicators_data():
    last_hour_run = -1
    last_regular_run = datetime.datetime.min
    while True:
        try:
            now = datetime.datetime.now()
            if now.minute == 0 and now.second >= 5:
                if now.hour != last_hour_run:
                    last_hour_run = now.hour
                    last_regular_run = now
                    logger.info("[HOURLY] reload_multiplicators_data running")
                    await make_requests()
            elif (now - last_regular_run).total_seconds() >= 300:
                last_regular_run = now
                logger.info("[5MIN] reload_multiplicators_data running")
                await make_requests()
        except Exception:
            logger.exception("reload_multiplicators_data error")
        await asyncio.sleep(1)

# -------------------------
# KuCoin token background
# -------------------------
async def update_kucoin_token_loop(interval_seconds: int = 9 * 60):
    global token_kucoin
    url = 'https://api-futures.kucoin.com/api/v1/bullet-public'
    while True:
        try:
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                async with session.post(url, json={}, timeout=15) as resp:
                    if resp.status == 200:
                        j = await resp.json()
                        new_token = j.get('data', {}).get('token')
                        if new_token:
                            async with token_kucoin_lock:
                                token_kucoin = new_token
                            logger.info('[update_kucoin_token_loop] token updated')
                    else:
                        logger.warning('[update_kucoin_token_loop] status %s', resp.status)
        except Exception:
            logger.exception('[update_kucoin_token_loop] error')
        await asyncio.sleep(interval_seconds)

# -------------------------
# DEX (Redis helper)
# -------------------------
def _read_dex_from_redis_sync(symbol):
    symbol = symbol + 'USDT'
    try:
        r = get_redis_db2()
        raw = r.get("Dex:all")
        raw_list = orjson.loads(raw) if raw else []
    except Exception:
        logger.exception("fetch_dex_spreads_symbol_from_db: redis read failed")
        return []

    spreads = []
    for data in raw_list:
        try:
            if data.get('symbol', '') != symbol:
                continue
            dex_market = 'DEX'
            cex_market = data.get('market2', '')
            dex_bid = float(data.get('bid') or 0)
            price_usd = float(data.get('priceUsd') or 0)
            diff = float(data.get('diff') or 0)
            contract = data.get('contract', '')
            chain = data.get('chain', '')
            volume24 = float(data.get('volume24') or 0)
            volume24_cex = float(data.get('volume24_cex') or 0)
            url = data.get('url', '')
            cex_ask = data.get('cex_ask', 0)
            funding_rate = data.get('funding_rate', 0)

            spread = {
                "symbol": symbol,
                "dex_market": dex_market,
                "cex_market": cex_market,
                "dex_bid": dex_bid,
                "price_usd": price_usd,
                "diff": diff,
                "contract": contract,
                "chain": chain,
                "volume24": volume24,
                "volume24_cex": volume24_cex,
                "url": url,
                "cex_ask": cex_ask,
                "funding_rate": funding_rate
            }
            spreads.append(spread)
        except Exception:
            logger.exception("fetch_dex_spreads_symbol_from_db: bad record for %s", symbol)
            continue
    return spreads

async def _dex_poller(symbol: str):
    """
    Пуллер для одного symbol: каждую 1s читает Redis и group_send -> dex_{symbol}
    """
    group_name = safe_group_name("dex", symbol.upper())
    logger.info(f"_dex_poller started for {symbol}")
    try:
        while True:
            try:
                spreads = await asyncio.to_thread(_read_dex_from_redis_sync, symbol)
                entry = spreads[0] if spreads else None
                payload = {
                    "type": "dex.update",  # локальный тип в payload
                    "symbol": symbol,
                    "data": entry,
                    "timestamp": int(time.time())
                }
                # Отправляем во все подписанные consumer'ы через channels group
                await CHANNEL_LAYER.group_send(group_name, {
                    "type": "dex.message",  # вызывается dex_message в consumer
                    "payload": payload
                })
            except Exception:
                logger.exception(f"_dex_poller error for {symbol}")
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info(f"_dex_poller cancelled for {symbol}")
        return
    except Exception:
        logger.exception(f"_dex_poller fatal for {symbol}")
    finally:
        # очистка: если кто-то оставил состояние, можно удалить task из dex_tasks
        async with dex_lock:
            dex_tasks.pop(symbol, None)
        logger.info(f"_dex_poller finished for {symbol}")


async def start_dex_poller(symbol: str):
    """Запустить poller для symbol, если его ещё нет."""
    async with dex_lock:
        if symbol in dex_tasks and not dex_tasks[symbol].done():
            return
        task = asyncio.create_task(_dex_poller(symbol))
        dex_tasks[symbol] = task
        logger.info(f"start_dex_poller: started poller for {symbol}")


async def stop_dex_poller_if_empty(symbol: str):
    """Остановить poller, если подписчиков для symbol нет."""
    async with dex_lock:
        subs = dex_subscribers.get(symbol, set())
        if (not subs) and symbol in dex_tasks:
            task = dex_tasks.pop(symbol)
            try:
                task.cancel()
            except Exception:
                logger.exception("stop_dex_poller_if_empty: cancel error")
            dex_subscribers.pop(symbol, None)
            logger.info(f"stop_dex_poller_if_empty: stopped poller for {symbol}")



# -------------------------
# Consumer
# -------------------------
class MonitorConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        global socket_data, checkIsRun, clearIsRun
        self.user = await self.get_user_from_token(self.scope["query_string"].decode())
        if self.user and self.user.is_authenticated:
            self.group_name = f"user_{self.user.id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            if not (self.user.test_active or self.user.subscribe_active):
                await self.send(text_data=json.dumps({"error": "Доступ запрещен: нет активной подписки"}))
                await self.close()
                return

            # state
            self.current_data = None
            self.is_sending_data = False
            self.last_ping_time = time.time()

            self.m1 = None
            self.m2 = None
            self.post_coin = None
            self.sp_or_ft = None
            self.depth = None

            # ping
            self.ping_interval = 20
            self.ping_task = asyncio.create_task(self.send_ping())

            # main loops
            if not self.is_sending_data:
                self.is_sending_data = True
                self.send_task = asyncio.create_task(self.send_data_periodically())
                self.additional_send_task = asyncio.create_task(self.send_additional_data())

            # unix socket listener - commented out by default (you can enable)
            # if checkIsRun is False:
            #     asyncio.create_task(socket_sender())
            #     socket_thread = threading.Thread(target=check_data_sockets)
            #     socket_thread.daemon = True
            #     socket_thread.start()
            # if clearIsRun is False:
            #     socket_thread2 = threading.Thread(target=clear_socket_data)
            #     socket_thread2.daemon = True
            #     socket_thread2.start()

            # start background tasks once per loop
            loop = asyncio.get_event_loop()
            if not hasattr(loop, '_multipliers_tasks_started'):
                loop._multipliers_tasks_started = True
                loop.create_task(reload_multiplicators_data())
                loop.create_task(update_kucoin_token_loop())
                loop.create_task(dex_gc_loop())  # FIX: добавили фоновую очистку dex_tasks
                logger.info("[MonitorConsumer] background multipliers & kucoin_token tasks started")

            # DEX subscription variables
            self.dex_task = None
            self.dex_symbol = None
            self.dex_last_activity = None  # timestamp when last dex_subscribe or keepalive received

        else:
            await self.close()

    async def disconnect(self, close_code):
        # Если клиент был подписан на какой-то dex_symbol, убрать его оттуда
        if getattr(self, "dex_symbol", None):
            symbol = self.dex_symbol
            group_name = safe_group_name("dex", symbol)  # FIX
            try:
                await self.channel_layer.group_discard(group_name, self.channel_name)
            except Exception:
                logger.exception("group_discard error in disconnect")
            async with dex_lock:
                if symbol in dex_subscribers:
                    dex_subscribers[symbol].discard(self.channel_name)
            await stop_dex_poller_if_empty(symbol)
            logger.info(f"Client {self.channel_name} removed from dex {symbol} on disconnect")
        for attr in ("ping_task", "send_task", "additional_send_task", "dex_task"):
            task = getattr(self, attr, None)
            if task:
                try:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                except Exception:
                    logger.exception(f"{attr} cancel/await error")
        if hasattr(self, "group_name"):
            try:
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
            except Exception:
                logger.exception("final group_discard error")

    async def send_ping(self):
        while True:
            await asyncio.sleep(self.ping_interval)
            if time.time() - self.last_ping_time > 60:
                logger.info("Closing connection due to ping timeout")
                await self.close()
                return

    async def dex_message(self, event):
        """
        Обработчик group-send'а от _dex_poller.
        event['payload'] содержит payload, который мы шлём клиенту.
        """
        payload = event.get("payload")
        if not payload:
            return
        # Пересылаем как JSON строку клиенту
        try:
            await self.send(text_data=json.dumps(payload))
        except Exception:
            logger.exception("dex_message: send error")

    async def send_data_periodically(self):
        global socket_data
        while True:
            await asyncio.sleep(0.1)
            # m1 = self.m1
            # m2 = self.m2
            # post_coin = self.post_coin
            # sp_or_ft = self.sp_or_ft
            # depth_value = self.depth
            #
            # if m1 is not None:
            #     send_data = dict(m1=m1, m2=m2, post_coin=post_coin, sp_or_ft=sp_or_ft)
            #     await send_queue.put(send_data)
            #
            #     key = f'{m1}_{m2}_{post_coin}_{sp_or_ft}'
            #     if key in socket_data:
            #         item = socket_data[key]
            #         spread_in = item.get('in')
            #         spread_out = item.get('out')
            #         send_asks1 = item.get('asks1', [])
            #         send_bids1 = item.get('bids1', [])
            #         send_asks2 = item.get('asks2', [])
            #         send_bids2 = item.get('bids2', [])
            #         sp_or_ft_item = item.get('sp_or_ft', sp_or_ft)
            #         time_spread = item.get('time')
            #     else:
            #         spread_in = "wait"
            #         spread_out = "wait"
            #         send_asks1 = [[0]]
            #         send_bids1 = [[0]]
            #         send_asks2 = [[0]]
            #         send_bids2 = [[0]]
            #         sp_or_ft_item = sp_or_ft
            #         time_spread = "0"
            #
            #     effective_asks1 = effective_bids1 = effective_asks2 = effective_bids2 = None
            #     effective_spread_in = effective_spread_out = None
            #     if depth_value and depth_value != 0:
            #         try:
            #             effective_asks1 = calculate_effective_price(send_asks1, depth_value)
            #             effective_bids1 = calculate_effective_price(send_bids1, depth_value)
            #             effective_asks2 = calculate_effective_price(send_asks2, depth_value)
            #             effective_bids2 = calculate_effective_price(send_bids2, depth_value)
            #             if effective_bids2 is not None and effective_asks1 is not None:
            #                 effective_spread_in = round(((float(effective_bids2) / float(effective_asks1)) - 1) * 100, 2)
            #             if effective_asks2 is not None and effective_bids1 is not None:
            #                 effective_spread_out = round(((float(effective_asks2) / float(effective_bids1)) - 1) * 100, 2)
            #         except Exception:
            #             logger.exception("error calculating effective spreads")
            #
            #     send_asks1 = send_asks1[:5][::-1] if isinstance(send_asks1, list) else send_asks1
            #     send_asks2 = send_asks2[:5][::-1] if isinstance(send_asks2, list) else send_asks2
            #     send_bids1 = send_bids1[:5] if isinstance(send_bids1, list) else send_bids1
            #     send_bids2 = send_bids2[:5] if isinstance(send_bids2, list) else send_bids2
            #
            #     socket_data_send = json.dumps({
            #         "type": "constant",
            #         "in": spread_in,
            #         "out": spread_out,
            #         "effective_in": effective_spread_in,
            #         "effective_out": effective_spread_out,
            #         "depth": depth_value,
            #         "asks1": send_asks1,
            #         "bids1": send_bids1,
            #         "asks2": send_asks2,
            #         "bids2": send_bids2,
            #         "sp_or_ft": sp_or_ft_item,
            #         "time": time_spread,
            #     })
            #     self.current_data = socket_data_send
            #
            # if self.current_data:
            #     try:
            #         await self.send(text_data=self.current_data)
            #     except Exception:
            #         logger.exception("send_data_periodically: send error")

    async def send_additional_data(self):
        while True:
            await asyncio.sleep(1)
            m1 = self.m1
            m2 = self.m2
            post_coin = getattr(self, "post_coin", None)
            post_coin2 = getattr(self, "post_coin2", None)
            sp_or_ft = self.sp_or_ft
            if m1 is None or post_coin is None or m2 is None or post_coin2 is None:
                await asyncio.sleep(1)
                continue
            post_coin = post_coin + 'USDT'
            post_coin2 = post_coin2 + 'USDT'
            spreads_in = []
            spreads_out = []
            spreads_time = []
            try:
                table_name = 'futures' if sp_or_ft == 'futures' else 'spot'
                if m1 == 'Dex':
                    table_name = 'spot'
                history_data_m1 = await fetch_coin_history_mongo_async(table_name, m1, post_coin)
                history_data_m2 = await fetch_coin_history_mongo_async('futures', m2, post_coin2)
                m1_dict = {entry[2]: (entry[0], entry[1]) for entry in history_data_m1}
                m2_dict = {entry[2]: (entry[0], entry[1]) for entry in history_data_m2}
                common_times = sorted(set(m1_dict.keys()) & set(m2_dict.keys()))
                for time_point in common_times:
                    m1_ask, m1_bid = m1_dict[time_point]
                    m2_ask, m2_bid = m2_dict[time_point]
                    if any(val == 0 for val in [m1_ask, m1_bid, m2_ask, m2_bid]):
                        continue
                    spreads_in.append(round(((m2_bid / m1_ask) - 1) * 100, 2))
                    spreads_out.append(round(((m2_ask / m1_bid) - 1) * 100, 2))
                    spreads_time.append(time_point.replace(tzinfo=timezone.utc).isoformat())
            except Exception:
                logger.exception('err in send_additional_data')

            if spreads_in and spreads_out and spreads_time:
                socket_data_send = json.dumps({
                    "type": "periodic",
                    "spreads_in": spreads_in,
                    "spreads_out": spreads_out,
                    "spreads_time": spreads_time,
                })
                self.current_data = socket_data_send
                await self.send(text_data=self.current_data)
            await asyncio.sleep(420)

    async def receive(self, text_data):
        """
        Handles:
         - action == "info" + info_type == "multipliers" => one-time multiplier response
         - action == "dex_subscribe" + symbol => starts dex worker (1s updates)
         - action == "dex_unsubscribe" => stops dex worker
         - otherwise: subscription for market1/market2/coin/sp_or_ft (same as before)
        """
        global socket_data, token_kucoin
        try:
            if not self.user or not self.user.is_authenticated:
                return

            data = json.loads(text_data)
            self.last_ping_time = time.time()
            logger.info(f"Received from client: {data}")

            action = data.get("action")
            if action == "info":
                info_type = data.get("info_type")
                if info_type == "multipliers":
                    m1 = data.get("market1")
                    m2 = data.get("market2")
                    c1 = data.get("coin1")
                    c2 = data.get("coin2")

                    def norm_coin(c):
                        if not c:
                            return None
                        c = c.upper()
                        return c if c.endswith("USDT") else c + "USDT"

                    coin_key1 = norm_coin(c1)
                    coin_key2 = norm_coin(c2)

                    multiplier1 = None
                    multiplier2 = None
                    try:
                        if coin_key1:
                            m1_key = (m1 or '').lower()
                            if m1_key == 'mexc':
                                multiplier1 = mexc_amounts.get(coin_key1)
                            elif m1_key == 'kucoin':
                                multiplier1 = kucoin_amounts.get(coin_key1)
                            elif m1_key == 'okx':
                                multiplier1 = okx_amounts.get(coin_key1)
                            elif m1_key == 'gateio':
                                multiplier1 = gateio_amounts.get(coin_key1)
                            elif m1_key == 'huobi':
                                multiplier1 = huobi_amounts.get(coin_key1)
                            elif m1_key == 'bitmart':
                                multiplier1 = bitmart_amounts.get(coin_key1)
                            elif m1_key == 'poloniex':
                                multiplier1 = poloniex_amounts.get(coin_key1)
                            elif m1_key == 'lbank':
                                multiplier1 = lbank_amounts.get(coin_key1)
                            elif m1_key == 'xt':
                                multiplier1 = xt_amounts.get(coin_key1)
                            # elif m1_key == 'coinex':
                            #     multiplier1 = coinex_amounts.get(coin_key1)
                        if coin_key2:
                            m2_key = (m2 or '').lower()
                            if m2_key == 'mexc':
                                multiplier2 = mexc_amounts.get(coin_key2)
                            elif m2_key == 'kucoin':
                                multiplier2 = kucoin_amounts.get(coin_key2)
                            elif m2_key == 'okx':
                                multiplier2 = okx_amounts.get(coin_key2)
                            elif m2_key == 'gateio':
                                multiplier2 = gateio_amounts.get(coin_key2)
                            elif m2_key == 'huobi':
                                multiplier2 = huobi_amounts.get(coin_key2)
                            elif m2_key == 'bitmart':
                                multiplier2 = bitmart_amounts.get(coin_key2)
                            elif m2_key == 'poloniex':
                                multiplier2 = poloniex_amounts.get(coin_key2)
                            elif m2_key == 'lbank':
                                multiplier2 = lbank_amounts.get(coin_key2)
                            elif m2_key == 'xt':
                                multiplier2 = xt_amounts.get(coin_key2)
                            # elif m2_key == 'coinex':
                            #     multiplier2 = coinex_amounts.get(coin_key2)
                    except Exception:
                        logger.exception("error reading multipliers")

                    async with token_kucoin_lock:
                        token = token_kucoin

                    resp = {
                        "type": "info_multipliers",
                        "market1": m1,
                        "coin1": coin_key1,
                        "multiplier1": multiplier1,
                        "market2": m2,
                        "coin2": coin_key2,
                        "multiplier2": multiplier2,
                        "kucoin_token": token,
                        "timestamp": int(time.time())
                    }
                    await self.send(text_data=json.dumps(resp))
                    return

                elif info_type == "kucoin_token":
                    async with token_kucoin_lock:
                        token = token_kucoin
                    resp = {"type": "info_kucoin_token", "kucoin_token": token, "timestamp": int(time.time())}
                    await self.send(text_data=json.dumps(resp))
                    return

                else:
                    await self.send(text_data=json.dumps({"type": "error", "message": "unknown info_type"}))
                    return

            # DEX subscribe / unsubscribe / keepalive
            if action == "dex_subscribe":
                symbol = data.get("symbol")
                if not symbol:
                    await self.send(text_data=json.dumps({"type": "error", "message": "missing symbol"}))
                    return
                symbol = symbol.upper()
                # FIX: безопасное имя группы
                group_name = safe_group_name("dex", symbol)

                await self.channel_layer.group_add(group_name, self.channel_name)

                # добавить в нашу локальную структуру подписчиков
                async with dex_lock:
                    s = dex_subscribers.get(symbol)
                    if not s:
                        dex_subscribers[symbol] = set()
                        s = dex_subscribers[symbol]
                    s.add(self.channel_name)

                # запустить poller, если его ещё нет
                await start_dex_poller(symbol)

                # сохранить состояние в consumer (для использования при disconnect/unsubscribe)
                self.dex_symbol = symbol

                logger.info(f"Client {self.channel_name} subscribed to DEX {symbol}")
                await self.send(text_data=json.dumps({"type": "dex_subscribed", "symbol": symbol}))
                return

            if action == "dex_keepalive":
                # client can send action dex_keepalive to extend subscription
                if getattr(self, 'dex_task', None) and data.get("symbol") == self.dex_symbol:
                    self.dex_last_activity = time.time()
                    await self.send(text_data=json.dumps({"type": "dex_keepalive_ack", "symbol": self.dex_symbol}))
                return

            if action == "dex_unsubscribe":
                symbol = data.get("symbol")
                if not symbol and getattr(self, "dex_symbol", None):
                    symbol = self.dex_symbol
                if not symbol:
                    await self.send(text_data=json.dumps({"type": "error", "message": "missing symbol"}))
                    return
                symbol = symbol.upper()
                group_name = safe_group_name("dex", symbol)  # FIX

                # remove from channels group
                try:
                    await self.channel_layer.group_discard(group_name, self.channel_name)
                except Exception:
                    logger.exception("group_discard error")

                # remove from local subscribers set
                async with dex_lock:
                    if symbol in dex_subscribers:
                        dex_subscribers[symbol].discard(self.channel_name)
                # try stop poller if nobody left
                await stop_dex_poller_if_empty(symbol)

                # cleanup consumer state
                if getattr(self, "dex_symbol", None) == symbol:
                    self.dex_symbol = None
                self.dex_last_activity = None

                logger.info(f"Client {self.channel_name} unsubscribed from DEX {symbol}")
                await self.send(text_data=json.dumps({"type": "dex_unsubscribed", "symbol": symbol}))
                return

            # Otherwise — normal subscription message (as before)
            if action == "get_history":
                m1 = data.get("market1")
                m2 = data.get("market2")
                coin = data.get("coin")
                coin2 = data.get("coin2")
                sp_or_ft = data.get("sp_or_ft")
                self.m1 = m1
                self.m2 = m2
                self.post_coin = coin
                self.post_coin2 = coin2
                self.sp_or_ft = sp_or_ft
                return


        except Exception:
            logger.exception('receive handler error')

    @database_sync_to_async
    def get_user_from_token(self, query_string):
        try:
            token = query_string.split("=")[1]
            access_token = AccessToken(token)
            return User.objects.get(id=access_token["user_id"])
        except Exception:
            return None

    @database_sync_to_async
    def get_user_depth_value(self):
        user = User.objects.get(id=self.user.id)
        return user.depth_value
