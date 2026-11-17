import datetime
import gzip
import logging
import asyncio
import aiohttp
import pickle
import threading
import copy
import json
import os
from pybit.unified_trading import WebSocket
import socket
import time
from decimal import Decimal
import random
import PushDataV3ApiWrapper_pb2
from aiohttp_socks import ProxyConnector

PROXY = os.getenv("proxy1")


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
)

logger = logging.getLogger(__name__)

coins_list_full = {}
checkIsRun = False
token_kucoin = ''
token_poloniex = ''
mexc_amounts = {}
kucoin_amounts = {}
gateio_amounts = {}
huobi_amounts = {}
okx_amounts = {}
bitmart_amounts = {}
poloniex_amounts = {}
ourbit_amounts = {}
hyperliquid_amounts = {}
lbank_amounts = {}

mexc_lock = asyncio.Lock()
kucoin_lock = asyncio.Lock()
gateio_lock = asyncio.Lock()
huobi_lock = asyncio.Lock()
okx_lock = asyncio.Lock()
bitmart_lock = asyncio.Lock()
poloniex_lock = asyncio.Lock()
ourbit_lock = asyncio.Lock()
hyperliquid_lock = asyncio.Lock()
lbank_lock = asyncio.Lock()

temp_coins_2 = []

with open('rating_coins_full.pickle', 'rb') as f:
    if f != None:
        temp_coins_2 = pickle.load(f)

for coin in temp_coins_2[0]:
    coins_list_full[coin['symbol'].upper()] = coin['symbol'].upper()

markets_list = ['Bybit', 'Mexc', 'Kucoin', 'Gateio', 'Bitget', 'Huobi', 'Okx', 'Binance', 'BingX', 'BitMart', 'Poloniex', 'CoinEx', 'Ourbit', 'Hyperliquid', 'LBank']


async def check_to_close_socket(open_sockets_dict, data_dict):
    for sock in list(open_sockets_dict.keys()):
        # Проверка времени последней активности
        if (datetime.datetime.now() - open_sockets_dict[sock][1]).seconds > 3:
            # Установим флаг "нужно закрыть"
            open_sockets_dict[sock][2] = 1

            # Дождёмся завершения async задачи (если она есть)
            socket_task = open_sockets_dict[sock][0]  # это asyncio.Task

            if socket_task and not socket_task.done():
                try:
                    socket_task.cancel()
                    await socket_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"[ERROR] Socket task cancellation failed for {sock}:", e)

            try:
                open_sockets_dict.pop(sock)
                data_dict.pop(sock, None)
                print(f"[INFO] Socket closed and removed: {sock}")
            except Exception as e:
                print(f"[ERROR] Failed to remove socket {sock}:", e)
                logger.exception('Socket Cleanup Error')


async def start_sock(m1, post_coin, open_sockets_okx, sp_or_ft):
    if post_coin in open_sockets_okx.keys():
        if open_sockets_okx[post_coin][2] != 1:
            open_sockets_okx[post_coin][1] = datetime.datetime.now()

    if post_coin not in open_sockets_okx.keys():
        print('start:', m1, post_coin, sp_or_ft)
        asyncio.create_task(run_socket(m1, post_coin, sp_or_ft))


async def reload_multiplicators_data():
    global mexc_amounts, gateio_amounts, huobi_amounts, okx_amounts, kucoin_amounts, bitmart_amounts, poloniex_amounts, coins_list_full

    last_hour_run = -1
    last_regular_run = datetime.datetime.min

    while True:

        try:
            now = datetime.datetime.now()
            # ✅ Ежечасный запуск (в начале часа, начиная с 5 секунды)
            if now.minute == 0 and now.second >= 5:
                if now.hour != last_hour_run:
                    print(f"[HOURLY] {now.strftime('%H:%M:%S')} → Запуск")
                    last_hour_run = now.hour
                    last_regular_run = now  # чтобы избежать немедленного срабатывания обычного запроса
                    await make_requests()
                    with open("all_coins.pickle", "wb") as file:
                        pickle.dump(coins_list_full, file)

            # ✅ Запуск каждые 5 минут
            elif (now - last_regular_run).total_seconds() >= 300:
                print(f"[5MIN] {now.strftime('%H:%M:%S')} → Запуск")
                last_regular_run = now
                print("[make_requests] старт 5-минутного обновления")
                await make_requests()
                print("[make_requests] запись в all_coins.pickle в 5M")
                with open("all_coins.pickle", "wb") as file:
                    pickle.dump(coins_list_full, file)

        except Exception as e:
            print(f"[ERROR] reload_multiplicators_data: {e}")

        await asyncio.sleep(1)


TIMEOUT = aiohttp.ClientTimeout(total=15)  # 10 секунд общий таймаут


async def fetch_json(session, url, name):
    try:
        async with session.get(url) as resp:
            return await resp.json()
    except asyncio.TimeoutError:
        print(f"[Timeout] {name} API не ответил вовремя")
    except Exception as e:
        print(f"[Error] {name} API: {e}")
    return None

async def fetch_json_huobi(session, url, name):
    try:
        async with session.get(url) as resp:
            text = await resp.text()
            return json.loads(text)
    except asyncio.TimeoutError:
        print(f"[Timeout] {name} API не ответил вовремя")
    except Exception as e:
        print(f"[Error] {name} API: {e}")
    return None

async def make_requests():
    global mexc_amounts, gateio_amounts, huobi_amounts, okx_amounts
    global kucoin_amounts, bitmart_amounts, poloniex_amounts, coins_list_full
    global lbank_amounts
    print('[make_requests] start')

    urls = {
        "mexc": "https://contract.mexc.com/api/v1/contract/detail",
        "gateio": "https://api.gateio.ws/api/v4/futures/usdt/contracts",
        "huobi": "https://api.hbdm.com/linear-swap-api/v1/swap_contract_info?business_type=swap",
        "okx": "https://www.okx.com/api/v5/public/instruments?instType=SWAP",
        "kucoin": "https://api-futures.kucoin.com/api/v1/contracts/active",
        "bitmart": "https://api-cloud-v2.bitmart.com/contract/public/details",
        "poloniex": "https://futures-api.poloniex.com/api/v1/contracts/active",
        "lbank": "https://lbkperp.lbank.com/cfd/openApi/v1/pub/instrument?productGroup=SwapU"
    }

    try:
        # Локальные словари
        new_mexc, new_gateio, new_huobi, new_okx = {}, {}, {}, {}
        new_kucoin, new_bitmart, new_poloniex, new_coins_list = {}, {}, {}, {}
        new_lbank = {}
        connector = ProxyConnector.from_url(PROXY)
        async with aiohttp.ClientSession(connector=connector, timeout=TIMEOUT) as session:
            # MEXC
            data = await fetch_json(session, urls["mexc"], "MEXC")
            if data:
                for res in data.get('data', []):
                    symbol = res['symbol'].replace('_USDT', '')
                    new_coins_list[symbol.upper()] = symbol.upper()
                    new_mexc[res['symbol'].replace('_USDT', 'USDT')] = res['contractSize']
                print('[make_requests] good mexc')
            # Gate.io
            data = await fetch_json(session, urls["gateio"], "Gate.io")
            if data:
                for res in data:
                    symbol = res['name'].replace('_USDT', '')
                    new_coins_list[symbol.upper()] = symbol.upper()
                    new_gateio[res['name'].replace('_USDT', 'USDT')] = res['quanto_multiplier']
                print('[make_requests] good gateio')
            # Huobi
            data = await fetch_json_huobi(session, urls["huobi"], "Huobi")
            if data:
                for res in data.get('data', []):
                    symbol = res['contract_code'].replace('-USDT', '')
                    new_coins_list[symbol.upper()] = symbol.upper()
                    new_huobi[res['contract_code'].replace('-USDT', 'USDT')] = res['contract_size']
                print('[make_requests] good huobi')
            # OKX
            data = await fetch_json(session, urls["okx"], "OKX")
            if data:
                for res in data.get('data', []):
                    if 'USDT' in res['instFamily']:
                        symbol = res['instFamily'].replace('-USDT', '')
                        new_coins_list[symbol.upper()] = symbol.upper()
                        new_okx[res['instFamily'].replace('-USDT', 'USDT')] = float(res['ctMult']) * float(res['ctVal'])
                print('[make_requests] good okx')
            # KuCoin
            data = await fetch_json(session, urls["kucoin"], "KuCoin")
            if data:
                for res in data.get('data', []):
                    if 'USDTM' in res['symbol']:
                        symbol = res['symbol'].replace('USDTM', '')
                        new_coins_list[symbol.upper()] = symbol.upper()
                        new_kucoin[res['symbol'].replace('USDTM', 'USDT')] = float(res['multiplier'])
                print('[make_requests] good kucoin')
            # Bitmart
            data = await fetch_json(session, urls["bitmart"], "Bitmart")
            if data:
                for res in data.get('data', {}).get('symbols', []):
                    new_coins_list[res['symbol'].upper()] = res['symbol'].upper()
                    new_bitmart[res['symbol']] = res['contract_size']
                print('[make_requests] good bitmart')
            # Poloniex
            data = await fetch_json(session, urls["poloniex"], "Poloniex")
            if data:
                for res in data.get('data', []):
                    if 'USDTPERP' in res['symbol']:
                        symbol = res['symbol'].replace('USDTPERP', '')
                        new_coins_list[symbol.upper()] = symbol.upper()
                        new_poloniex[res['symbol'].replace('USDTPERP', 'USDT')] = float(res['multiplier'])
                print('[make_requests] good poloniex')
            # LBank
            data = await fetch_json(session, urls["lbank"], "LBank")
            if data:
                for res in data.get('data', []):
                    if 'USDT' in res['symbol']:
                        symbol = res['symbol'].replace('USDT', '')
                        new_coins_list[symbol.upper()] = symbol.upper()
                        new_lbank[res['symbol']] = float(res['priceTick'])
                print('[make_requests] good lbank')
        # Атомарная подмена
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

        coins_list_full = new_coins_list

        print('[make_requests] good update multiplicators')

    except Exception as e:
        print('[make_requests] FATAL ERROR:', e)


async def check_token_kucoin():
    global token_kucoin, checkIsRun
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post('https://api-futures.kucoin.com/api/v1/bullet-public') as resp:
                    response1 = await resp.json()
                    token_kucoin = response1['data']['token']
                    checkIsRun = True
        except Exception as e:
            print('check_token', e)
        await asyncio.sleep(600)


checkSockets = False

bybit_spot_sockets = {}

open_sockets_kucoin = {}
open_sockets_okx = {}
open_sockets_bybit = {}
open_sockets_mexc = {}
open_sockets_gateio = {}
open_sockets_bitget = {}
open_sockets_huobi = {}
open_sockets_binance = {}
open_sockets_bingx = {}
open_sockets_bitmart = {}
open_sockets_poloniex = {}
open_sockets_coinex = {}
open_sockets_ourbit = {}
open_sockets_hyperliquid = {}
open_sockets_lbank = {}

kucoin_futures_data = {}
okx_futures_data = {}
bybit_futures_data = {}
mexc_futures_data = {}
gateio_futures_data = {}
bitget_futures_data = {}
huobi_futures_data = {}
binance_futures_data = {}
bingx_futures_data = {}
bitmart_futures_data = {}
poloniex_futures_data = {}
coinex_futures_data = {}
ourbit_futures_data = {}
hyperliquid_futures_data = {}
lbank_futures_data = {}

spot_open_sockets_kucoin = {}
spot_open_sockets_okx = {}
spot_open_sockets_bybit = {}
spot_open_sockets_mexc = {}
spot_open_sockets_gateio = {}
spot_open_sockets_bitget = {}
spot_open_sockets_huobi = {}
spot_open_sockets_binance = {}
spot_open_sockets_bingx = {}
spot_open_sockets_bitmart = {}
spot_open_sockets_poloniex = {}
spot_open_sockets_coinex = {}
spot_open_sockets_ourbit = {}
spot_open_sockets_hyperliquid = {}
spot_open_sockets_lbank = {}

kucoin_spot_data = {}
okx_spot_data = {}
bybit_spot_data = {}
mexc_spot_data = {}
gateio_spot_data = {}
bitget_spot_data = {}
huobi_spot_data = {}
binance_spot_data = {}
bingx_spot_data = {}
bitmart_spot_data = {}
poloniex_spot_data = {}
coinex_spot_data = {}
ourbit_spot_data = {}
hyperliquid_spot_data = {}
lbank_spot_data = {}

async def run_socket(market, k, sp_or_ft):
    global open_sockets_kucoin, open_sockets_okx
    global open_sockets_bybit
    global open_sockets_mexc
    global open_sockets_gateio
    global open_sockets_bitget
    global open_sockets_huobi
    global open_sockets_binance
    global open_sockets_bingx
    global open_sockets_bitmart
    global open_sockets_poloniex
    global open_sockets_coinex
    global open_sockets_ourbit
    global open_sockets_hyperliquid
    global open_sockets_lbank

    global spot_open_sockets_kucoin, spot_open_sockets_okx
    global spot_open_sockets_bybit
    global spot_open_sockets_mexc
    global spot_open_sockets_gateio
    global spot_open_sockets_bitget
    global spot_open_sockets_huobi
    global spot_open_sockets_binance
    global spot_open_sockets_bingx
    global spot_open_sockets_bitmart
    global spot_open_sockets_poloniex
    global spot_open_sockets_coinex
    global spot_open_sockets_ourbit
    global spot_open_sockets_hyperliquid
    global spot_open_sockets_lbank
    # В цикле запускаем асинхронный worker сокета внутри нового event loop
    if sp_or_ft == 'futures':

        if market == 'Kucoin':
            task = asyncio.create_task(socket_futures_kucoin(k))
            open_sockets_kucoin[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Okx':
            task = asyncio.create_task(socket_futures_okx(k))
            open_sockets_okx[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Bybit':
            task = asyncio.create_task(socket_futures_bybit(k))
            open_sockets_bybit[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Mexc':
            task = asyncio.create_task(socket_futures_mexc(k))
            open_sockets_mexc[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Gateio':
            task = asyncio.create_task(socket_futures_gateio(k))
            open_sockets_gateio[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Bitget':
            task = asyncio.create_task(socket_futures_bitget(k))
            open_sockets_bitget[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Huobi':
            task = asyncio.create_task(socket_futures_huobi(k))
            open_sockets_huobi[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Binance':
            task = asyncio.create_task(socket_futures_binance(k))
            open_sockets_binance[k] = [task, datetime.datetime.now(), 0]

        elif market == 'BingX':
            task = asyncio.create_task(socket_futures_bingx(k))
            open_sockets_bingx[k] = [task, datetime.datetime.now(), 0]

        elif market == 'BitMart':
            task = asyncio.create_task(socket_futures_bitmart(k))
            open_sockets_bitmart[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Poloniex':
            task = asyncio.create_task(socket_futures_poloniex(k))
            open_sockets_poloniex[k] = [task, datetime.datetime.now(), 0]

        elif market == 'CoinEx':
            task = asyncio.create_task(socket_futures_coinex(k))
            open_sockets_coinex[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Ourbit':
            task = asyncio.create_task(socket_futures_ourbit(k))
            open_sockets_ourbit[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Hyperliquid':
            task = asyncio.create_task(socket_futures_hyperliquid(k))
            open_sockets_hyperliquid[k] = [task, datetime.datetime.now(), 0]

        elif market == 'LBank':
            task = asyncio.create_task(socket_futures_lbank(k))
            open_sockets_lbank[k] = [task, datetime.datetime.now(), 0]

    elif sp_or_ft == 'spot':

        if market == 'Kucoin':
            task = asyncio.create_task(socket_spot_kucoin(k))
            spot_open_sockets_kucoin[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Okx':
            task = asyncio.create_task(socket_spot_okx(k))
            spot_open_sockets_okx[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Bybit':
            task = asyncio.create_task(socket_spot_bybit(k))
            spot_open_sockets_bybit[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Mexc':
            task = asyncio.create_task(socket_spot_mexc(k))
            spot_open_sockets_mexc[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Gateio':
            task = asyncio.create_task(socket_spot_gateio(k))
            spot_open_sockets_gateio[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Bitget':
            task = asyncio.create_task(socket_spot_bitget(k))
            spot_open_sockets_bitget[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Huobi':
            task = asyncio.create_task(socket_spot_huobi(k))
            spot_open_sockets_huobi[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Binance':
            task = asyncio.create_task(socket_spot_binance(k))
            spot_open_sockets_binance[k] = [task, datetime.datetime.now(), 0]

        elif market == 'BingX':
            task = asyncio.create_task(socket_spot_bingx(k))
            spot_open_sockets_bingx[k] = [task, datetime.datetime.now(), 0]

        elif market == 'BitMart':
            task = asyncio.create_task(socket_spot_bitmart(k))
            spot_open_sockets_bitmart[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Poloniex':
            task = asyncio.create_task(socket_spot_poloniex(k))
            spot_open_sockets_poloniex[k] = [task, datetime.datetime.now(), 0]

        elif market == 'CoinEx':
            task = asyncio.create_task(socket_spot_coinex(k))
            spot_open_sockets_coinex[k] = [task, datetime.datetime.now(), 0]

        elif market == 'Ourbit':
            task = asyncio.create_task(socket_spot_ourbit(k))
            spot_open_sockets_ourbit[k] = [task, datetime.datetime.now(), 0]

        elif market == 'LBank':
            task = asyncio.create_task(socket_spot_lbank(k))
            spot_open_sockets_lbank[k] = [task, datetime.datetime.now(), 0]

async def socket_futures_kucoin(k):
    global kucoin_futures_data, token_kucoin, open_sockets_kucoin
    pong_task = None
    pong_flag = True
    id = random.randint(100000, 999999)
    url = f'wss://ws-api-spot.kucoin.com/?token={token_kucoin}'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=18, receive_timeout=90) as ws:
                print('ConnectedKucoin:', datetime.datetime.now().isoformat())
                print(k.replace('USDT', 'USDTM'))
                subs = dict(
                    id=id,
                    type='subscribe',
                    topic=f"/contractMarket/level2Depth50:{k.replace('USDT', 'USDTM')}",
                    response='true',
                    privateChannel='false'
                )
                await ws.send_str(json.dumps(subs))

                async def send_pong_periodically():
                    nonlocal pong_flag
                    try:
                        while pong_flag:
                            await asyncio.sleep(18)  # Ожидание 15 секунд
                            if pong_flag:
                                ping_msg = dict(id=id, type='ping')
                                ping_msg = json.dumps(ping_msg)
                                await ws.send_str(ping_msg)
                    except Exception as ep:
                        print(f'Kucoin exception send ping: {ep}')

                pong_task = asyncio.create_task(send_pong_periodically())


                async for msg in ws:
                    if open_sockets_kucoin[k][2]:
                        print('Kucoin go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)
                            data = msg.get('data')
                            topic = msg.get('topic')
                            if topic is not None:
                                asks = data['asks']
                                bids = data['bids']
                                kucoin_futures_data[k] = {
                                    'asks': asks,
                                    'bids': bids,
                                    'time': datetime.datetime.now()
                                }
                    except Exception as e:
                        print('SocketGETerrorKucoin Cleaning', e)
                        logger.exception('SocketExcept')

    except Exception as e:
        print('Socket Error:', e)
    finally:
        try:
            pong_flag = False
            if pong_task:
                pong_task.cancel()
                await pong_task
        except asyncio.CancelledError:
            pass
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            open_sockets_kucoin[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)

        print('Disconnected Kucoin:', datetime.datetime.now().isoformat())


async def socket_futures_okx(k):
    global okx_futures_data, open_sockets_okx
    url = 'wss://ws.okx.com:8443/ws/v5/public'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=20, receive_timeout=60) as ws:

                print('ConnectedOkx:', datetime.datetime.now().isoformat())
                subs = dict(
                    op='subscribe',
                    args=[
                        dict(channel='books5', instType='SWAP', instId=f"{k.replace('USDT', '-USDT-SWAP')}")
                    ]
                )
                await ws.send_str(json.dumps(subs))

                async for msg in ws:
                    if open_sockets_okx[k][2]:
                        print('Okx go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)

                            data = msg.get('data')
                            if data is not None:
                                asks = data[0]['asks']
                                bids = data[0]['bids']
                                okx_futures_data[k] = {
                                    'asks': asks,
                                    'bids': bids,
                                    'time': datetime.datetime.now()
                                }

                    except Exception as e:
                        print('SocketGETerrorOkx', e)
                        logger.exception('SocketExcept')

    except Exception as e:
        print('Socket Error:', e)

    finally:
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            open_sockets_okx[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)

        print('Disconnected Okx:', datetime.datetime.now().isoformat())


def takeBybit(elem):
    return float(elem[0])


def handle_message_bybit(message):
    global bybit_futures_data, open_sockets_bybit

    asks = sorted(message['data']['a'], key=takeBybit)
    bids = sorted(message['data']['b'], key=takeBybit, reverse=True)

    bybit_futures_data[message['topic'].split('.')[-1]] = {
        'asks': asks,
        'bids': bids,
        'time': datetime.datetime.now()
    }


async def socket_futures_bybit(k):
    ws = WebSocket(
        testnet=False,
        channel_type="linear",
    )
    ws.orderbook_stream(
        depth=50,
        symbol=f"{k}",
        callback=handle_message_bybit
    )

    try:
        while True:
            await asyncio.sleep(1)  # Просто держим задачу "живой"
    except asyncio.CancelledError:
        print(f"[INFO] Cancelling WebSocket for Bybit: {k}")
        try:
            if hasattr(ws, "exited") and not ws.exited:
                ws.exit()
        except Exception as e:
            print(f"[ERROR] Failed to stop ws for {k}: {e}")
        raise  # обязательно пробрасываем CancelledError дальше


async def socket_futures_mexc(k):
    global mexc_futures_data, open_sockets_mexc
    pong_task = None
    pong_flag = True
    url = 'wss://contract.mexc.com/edge'
    if k == 'SOONUSDT':
        repl = 'SOONNETWORKUSDT'
    elif k == 'ARTUSDT':
        repl = 'LIVEARTUSDT'
    else:
        repl = k
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=10, receive_timeout=40) as ws:

                print('ConnectedMexc:', datetime.datetime.now().isoformat())
                subs = dict(
                    method='sub.depth.full',
                    param=dict(symbol=f"{repl.replace('USDT', '_USDT')}", limit="20")

                )
                await ws.send_str(json.dumps(subs))


                async def send_pong_periodically():
                    nonlocal pong_flag
                    try:
                        while pong_flag:
                            await asyncio.sleep(20)  # Ожидание 15 секунд
                            if pong_flag:
                                ping_msg = dict(method='ping')
                                ping_msg = json.dumps(ping_msg)
                                await ws.send_str(ping_msg)
                    except Exception as ep:
                        print(f'Mexc exception send ping: {ep}')


                pong_task = asyncio.create_task(send_pong_periodically())

                async for msg in ws:
                    if open_sockets_mexc[k][2]:
                        print('Mexc go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)

                            data = msg.get('data')
                            if isinstance(data, dict):
                                try:
                                    asks = data['asks']
                                    bids = data['bids']

                                    mexc_futures_data[k] = {
                                        'asks': asks,
                                        'bids': bids,
                                        'time': datetime.datetime.now()
                                    }
                                except Exception as e:
                                    print('mexc error socket msg', e)
                    except Exception as e:
                        print('SocketGETerrorMexc', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Socket Error:', e)
    finally:
        try:
            pong_flag = False
            if pong_task:
                pong_task.cancel()
                await pong_task
        except asyncio.CancelledError:
            pass
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            open_sockets_mexc[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)

        print('Disconnected Mexc:', datetime.datetime.now().isoformat())


async def socket_futures_gateio(k):
    global gateio_futures_data, open_sockets_gateio
    url = 'wss://fx-ws.gateio.ws/v4/ws/usdt'

    last_message = None

    async def processor():
        nonlocal last_message
        while True:
            await asyncio.sleep(0.1)  # интервал обработки: 100 мс
            if last_message:
                msg_to_process = last_message
                last_message = None  # сбрасываем сразу
                try:
                    msg = json.loads(msg_to_process)
                    data = msg.get('result')
                    if 'status' not in data:
                        gateio_futures_data[k] = {
                            'asks': data['asks'],
                            'bids': data['bids'],
                            'time': datetime.datetime.now()
                        }
                except Exception as e:
                    print(f"[ERROR] Processing Gateio message: {e}")


    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=10, receive_timeout=40) as ws:

                print('ConnectedGateio:', datetime.datetime.now().isoformat())
                subs = dict(
                    channel='futures.order_book',
                    event='subscribe',
                    payload=[f"{k.replace('USDT', '_USDT')}", "50", "0"]

                )
                await ws.send_str(json.dumps(subs))

                processor_task = asyncio.create_task(processor())

                async for msg in ws:
                    if open_sockets_gateio[k][2]:
                        print('Gateio go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            if '"status"' not in msg.data:  # Быстрая строковая проверка
                                try:
                                    last_message = msg.data
                                except Exception as e:
                                    print('[JSON Error]', e)
                    except Exception as e:
                        print('SocketGETerrorGateio', e)
                        logger.exception('SocketExcept')

    except Exception as e:
        print('Socket Error:', e)

    finally:
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            open_sockets_gateio[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)

        print('Disconnected Gateio:', datetime.datetime.now().isoformat())


async def socket_futures_bitget(k):
    global bitget_futures_data, open_sockets_bitget
    pong_task = None
    pong_flag = True
    url = 'wss://ws.bitget.com/v2/ws/public'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=10, receive_timeout=30) as ws:

                print('ConnectedBitget:', datetime.datetime.now().isoformat())
                subs = dict(
                    op='subscribe',
                    args=[
                        dict(instType="USDT-FUTURES",
                             channel="books15",
                             instId=f"{k}")
                    ],
                )
                await ws.send_str(json.dumps(subs))

                async def send_pong_periodically():
                    nonlocal pong_flag
                    try:
                        while pong_flag:
                            await asyncio.sleep(30)  # Ожидание 15 секунд
                            if pong_flag:
                                await ws.send_str('ping')
                    except Exception as ep:
                        print(f'Bitget exception send ping: {ep}')


                pong_task = asyncio.create_task(send_pong_periodically())

                async for msg in ws:
                    if open_sockets_bitget[k][2]:
                        print('Bitget go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            raw = msg.data.strip()

                            # Быстрая проверка: JSON всегда начинается с { или [
                            if raw.startswith('{'):
                                msg = json.loads(raw)
                                data = msg.get('data')
                                if data is not None:
                                    asks = data[0]['asks']
                                    bids = data[0]['bids']
                                    bitget_futures_data[k] = {
                                        'asks': asks,
                                        'bids': bids,
                                        'time': datetime.datetime.now()
                                    }

                    except Exception as e:
                        print('SocketGETerrorBitget', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Socket Error:', e)
    finally:
        try:
            pong_flag = False
            if pong_task:
                pong_task.cancel()
                await pong_task
        except asyncio.CancelledError:
            pass
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            open_sockets_bitget[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)

        print('Disconnected Bitget:', datetime.datetime.now().isoformat())


async def socket_futures_huobi(k):
    global huobi_futures_data, open_sockets_huobi
    url = 'wss://api.hbdm.com/linear-swap-ws'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=2, receive_timeout=90) as ws:

                print('ConnectedHuobi:', datetime.datetime.now().isoformat())
                subs = dict(
                    sub=f"market.{k.replace('USDT', '-USDT')}.depth.step0"
                )
                await ws.send_str(json.dumps(subs))

                async for msg in ws:
                    if open_sockets_huobi[k][2]:
                        print('Huobi go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        try:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                msg = gzip.decompress(msg.data).decode('utf-8')
                        except Exception:
                            print('error')
                        msg = json.loads(msg)
                        if 'ping' in msg:
                            await ws.send_str("pong")
                        if 'tick' in msg:
                            data = msg.get('tick')
                            if data is not None:
                                asks = data['asks']
                                bids = data['bids']
                                huobi_futures_data[k] = {
                                    'asks': asks,
                                    'bids': bids,
                                    'time': datetime.datetime.now()
                                }
                    except Exception as e:
                        print('SocketGETerrorHuobi', e)
                        logger.exception('SocketExcept')
                        try:
                            huobi_futures_data.pop(k)
                        except Exception as e:
                            print('cant pop data huobi', e)

    except Exception as e:
        print('Socket Error:', e)
    finally:
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            open_sockets_huobi[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)
        print('Disconnected Huobi:', datetime.datetime.now().isoformat())


async def socket_futures_binance(k):
    global binance_futures_data, open_sockets_binance
    url = 'wss://fstream.binance.com/ws'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=20, receive_timeout=60) as ws:

                print('ConnectedBinance:', datetime.datetime.now().isoformat())
                subs = {
                    "method": "SUBSCRIBE",
                    "params": [f"{k.lower()}@depth20@100ms"],
                    "id": 1
                }
                await ws.send_str(json.dumps(subs))

                async for msg in ws:
                    if open_sockets_binance[k][2]:
                        print('Binance go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)
                            b = msg.get('b')
                            a = msg.get('a')
                            if b is not None and a is not None:
                                asks = sorted(a, key=takeBybit)
                                bids = sorted(b, key=takeBybit, reverse=True)
                                binance_futures_data[k] = {
                                    'asks': asks,
                                    'bids': bids,
                                    'time': datetime.datetime.now()
                                }
                    except Exception as e:
                        print('SocketGETerrorBinance', e)
                        logger.exception('SocketExcept')

    except Exception as e:
        print('Socket Error:', e)
    finally:
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            open_sockets_binance[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)
        print('Disconnected Binance:', datetime.datetime.now().isoformat())


async def socket_futures_bingx(k):
    global bingx_futures_data, open_sockets_bingx
    url = 'wss://open-api-swap.bingx.com/swap-market'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=5, receive_timeout=90) as ws:

                print('ConnectedBingX:', datetime.datetime.now().isoformat())
                subs = {"id": "1", "reqType": "sub",
                        "dataType": f"{k.replace('USDT', '-USDT')}@depth50@200ms"}

                await ws.send_str(json.dumps(subs))

                async for msg in ws:
                    if open_sockets_bingx[k][2]:
                        print('BingX go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        try:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                msg = gzip.decompress(msg.data).decode('utf-8')
                        except Exception:
                            print('error')
                        try:
                            msg = json.loads(msg)
                        except Exception as e:
                            print('err json load', e)
                        if 'Ping' in msg:
                            await ws.send_str("Pong")
                        else:
                            data = msg.get('data')
                            if data is not None:
                                asks = sorted(data.get('asks'), key=takeBybit, reverse=False)
                                bids = data.get('bids')
                                bingx_futures_data[k] = {
                                    'asks': asks,
                                    'bids': bids,
                                    'time': datetime.datetime.now()
                                }
                    except Exception as e:
                        print('SocketGETerrorBingX', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Socket Error bingx:', e)
    finally:
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            open_sockets_bingx[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)
        print('Disconnected BingX:', datetime.datetime.now().isoformat())


async def socket_futures_bitmart(k):
    global bitmart_futures_data, open_sockets_bitmart
    url = 'wss://openapi-ws-v2.bitmart.com'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=5, receive_timeout=90) as ws:

                print('ConnectedBitmart:', datetime.datetime.now().isoformat())
                subs = dict(
                    action="subscribe",
                    args=[f'futures/depth50:{k}']
                )
                await ws.send_str(json.dumps(subs))

                async for msg in ws:
                    if open_sockets_bitmart[k][2]:
                        print('Bitmart go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        try:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                msg = json.loads(msg.data)
                        except Exception as e:
                            print('err json load', e)
                        data = msg.get('data')
                        if data is not None:
                            if data.get('way') == 2:
                                asks = data.get('depths')
                                new_asks = []
                                for ask in asks:
                                    new_asks.append([ask.get('price'), ask.get('vol')])
                                create_or_push = bitmart_futures_data.get(k, None)
                                if create_or_push is not None:
                                    bitmart_futures_data[k]['asks'] = new_asks
                                    bitmart_futures_data[k]['time'] = datetime.datetime.now()
                                else:
                                    bitmart_futures_data[k] = {}
                                    bitmart_futures_data[k]['asks'] = new_asks
                                    bitmart_futures_data[k]['time'] = datetime.datetime.now()
                            elif data.get('way') == 1:
                                bids = data.get('depths')
                                new_bids = []
                                for bid in bids:
                                    new_bids.append([bid.get('price'), bid.get('vol')])
                                create_or_push = bitmart_futures_data.get(k, None)
                                if create_or_push is not None:
                                    bitmart_futures_data[k]['bids'] = new_bids
                                    bitmart_futures_data[k]['time'] = datetime.datetime.now()
                                else:
                                    bitmart_futures_data[k] = {}
                                    bitmart_futures_data[k]['bids'] = new_bids
                                    bitmart_futures_data[k]['time'] = datetime.datetime.now()
                    except Exception as e:
                        print('SocketGETerrorBitmart', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Socket Error bitmart:', e)
    finally:
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            open_sockets_bitmart[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)
        print('Disconnected Bitmart:', datetime.datetime.now().isoformat())

async def socket_futures_poloniex(k):
    global poloniex_futures_data, open_sockets_poloniex, token_poloniex
    pong_flag = True
    pong_task = None
    url = f'wss://ws.poloniex.com/ws/v3/public'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, receive_timeout=90) as ws:

                print('ConnectedPoloniex:', datetime.datetime.now().isoformat())

                subs = dict(
                    event='subscribe',
                    channel=["book"],
                    symbols=[k.replace("USDT", "_USDT_PERP")],
                    depth=20,
                )
                await ws.send_str(json.dumps(subs))

                async def send_pong_periodically():
                    nonlocal pong_flag
                    try:
                        while pong_flag:
                            await asyncio.sleep(20)  # Ожидание 15 секунд
                            if pong_flag:
                                ping_msg = dict(event='ping')
                                ping_msg = json.dumps(ping_msg)
                                await ws.send_str(ping_msg)
                    except Exception as ep:
                        print(f'Mexc exception send ping: {ep}')

                pong_task = asyncio.create_task(send_pong_periodically())

                async for msg in ws:
                    if open_sockets_poloniex[k][2]:
                        print('Poloniex go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)
                            data = msg.get('data')
                            if data is not None:
                                asks = data[0]['asks']
                                bids = data[0]['bids']
                                poloniex_futures_data[k] = {
                                    'asks': asks,
                                    'bids': bids,
                                    'time': datetime.datetime.now()
                                }
                    except Exception as e:
                        print('SocketGETerrorPoloniex msg in ws:', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Socket Error poloniex:', e)
    finally:
        try:
            pong_flag = False
            if pong_task:
                pong_task.cancel()
                await pong_task
        except asyncio.CancelledError:
            pass
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            open_sockets_poloniex[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)
        print('Disconnected Poloniex:', datetime.datetime.now().isoformat())

async def socket_futures_coinex(k):
    global coinex_futures_data, open_sockets_coinex
    pong_flag = True
    pong_task = None
    id = random.randint(100000, 999999)
    url = f'wss://socket.coinex.com/v2/futures'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url) as ws:

                print('ConnectedCoinEx:', datetime.datetime.now().isoformat())

                subs = dict(
                    method='depth.subscribe',
                    params=dict(market_list=[[f'{k}', 50, "0", True]]),
                    id=id
                )
                await ws.send_str(json.dumps(subs))

                async def send_pong_periodically_coinex():
                    nonlocal pong_flag
                    while pong_flag:
                        await asyncio.sleep(5)
                        if pong_flag:
                            try:
                                # Ожидание 15 секунд
                                dataSend = dict(method="server.ping", params=dict(), id=id)
                                dataSend = json.dumps(dataSend)
                                await ws.send_str(dataSend)
                            except Exception as e:
                                print(f'Exception socket futures coinex {e} add bad sockets')
                                break

                pong_task = asyncio.create_task(send_pong_periodically_coinex())

                async for msg in ws:
                    if open_sockets_coinex[k][2]:
                        print('CoinEx go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        try:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                msg = gzip.decompress(msg.data).decode('utf-8')
                        except Exception:
                            print('error')

                        msg = json.loads(msg)
                        data = msg.get('data')
                        if data is not None and 'result' not in data:
                            depth = data.get('depth')
                            asks = depth['asks']
                            bids = depth['bids']
                            asks = sorted(asks, key=takeBybit)
                            bids = sorted(bids, key=takeBybit, reverse=True)
                            coinex_futures_data[k] = {
                                'asks': asks,
                                'bids': bids,
                                'time': datetime.datetime.now()
                            }
                    except Exception as e:
                        print('SocketGETerrorCoinEx msg in ws:', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Socket Error CoinEx:', e)
    finally:
        try:
            pong_flag = False
            if pong_task:
                pong_task.cancel()
                try:
                    await pong_task
                except asyncio.CancelledError:
                    pass
        except asyncio.CancelledError:
            pass
        try:
            if not ws.closed:  # или: if ws and not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            open_sockets_coinex[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)
        print('Disconnected CoinEx:', datetime.datetime.now().isoformat())


async def socket_futures_ourbit(k):
    global ourbit_futures_data, open_sockets_ourbit
    pong_task = None
    pong_flag = True
    url = 'wss://futures.ourbit.com/edge'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=10, receive_timeout=40) as ws:

                print('ConnectedOurbit:', datetime.datetime.now().isoformat())
                subs = dict(
                    method='sub.depth.step',
                    param=dict(symbol=f"{k.replace('USDT', '_USDT')}")

                )
                await ws.send_str(json.dumps(subs))


                async def send_pong_periodically():
                    nonlocal pong_flag
                    try:
                        while pong_flag:
                            await asyncio.sleep(20)  # Ожидание 15 секунд
                            if pong_flag:
                                ping_msg = dict(method='ping')
                                ping_msg = json.dumps(ping_msg)
                                await ws.send_str(ping_msg)
                    except Exception as ep:
                        print(f'Ourbit exception send ping: {ep}')

                pong_task = asyncio.create_task(send_pong_periodically())

                async for msg in ws:
                    if open_sockets_ourbit[k][2]:
                        print('Ourbit go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)

                            data = msg.get('data')
                            if isinstance(data, dict):
                                try:
                                    asks = data['asks']
                                    bids = data['bids']
                                    ourbit_futures_data[k] = {
                                        'asks': asks,
                                        'bids': bids,
                                        'time': datetime.datetime.now()
                                    }
                                except Exception as e:
                                    print('ourbit error socket msg', e)
                    except Exception as e:
                        print('SocketGETerrorOurbit', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Socket Error:', e)
    finally:
        try:
            pong_flag = False
            if pong_task:
                pong_task.cancel()
                await pong_task
        except asyncio.CancelledError:
            pass
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            open_sockets_ourbit[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)

        print('Disconnected Ourbit:', datetime.datetime.now().isoformat())


async def socket_futures_hyperliquid(k):
    global ourbit_futures_data, open_sockets_ourbit
    pong_task = None
    pong_flag = True
    url = 'wss://api.hyperliquid.xyz/ws'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=10, receive_timeout=40) as ws:

                print('Connected Hyperliquid:', datetime.datetime.now().isoformat())
                subs = dict(
                    method='subscribe',
                    subscription=dict(type="l2Book", coin=f"{k.replace('USDT', '')}")

                )
                await ws.send_str(json.dumps(subs))


                async def send_pong_periodically():
                    nonlocal pong_flag
                    try:
                        while pong_flag:
                            await asyncio.sleep(20)  # Ожидание 15 секунд
                            if pong_flag:
                                ping_msg = dict(method='ping')
                                ping_msg = json.dumps(ping_msg)
                                await ws.send_str(ping_msg)
                    except Exception as ep:
                        print(f'Hyperliquid exception send ping: {ep}')

                pong_task = asyncio.create_task(send_pong_periodically())

                async for msg in ws:
                    if open_sockets_hyperliquid[k][2]:
                        print('Hyperliquid go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)

                            if msg.get('channel') == 'l2Book':
                                data = msg.get('data', {})
                                levels = data.get('levels', [])

                                if isinstance(levels, list) and len(levels) == 2:
                                    bids = [[float(entry['px']), float(entry['sz'])] for entry in levels[0]]
                                    asks = [[float(entry['px']), float(entry['sz'])] for entry in levels[1]]

                                    hyperliquid_futures_data[k] = {
                                        'asks': asks,
                                        'bids': bids,
                                        'time': datetime.datetime.now()
                                    }
                    except Exception as e:
                        print('SocketGETerrorHyperliquid', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Socket Error:', e)
    finally:
        try:
            pong_flag = False
            if pong_task:
                pong_task.cancel()
                await pong_task
        except asyncio.CancelledError:
            pass
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            open_sockets_hyperliquid[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)

        print('Disconnected Hyperliquid:', datetime.datetime.now().isoformat())


async def socket_futures_lbank(k):
    global lbank_futures_data, open_sockets_lbank
    url = 'wss://uuws.rerrkvifj.com/ws/v3'
    id = random.randint(100000, 999999)
    pong_task = None
    pong_flag = True
    priceTick = lbank_amounts.get(k)
    if priceTick is not None:
        decimals = abs(Decimal(str(priceTick)).as_tuple().exponent)
        price_precision = f"{{:.{decimals}f}}".format(1 / (10 ** decimals)) if decimals > 0 else "1"
    else:
        price_precision = "0.0001"
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=2, receive_timeout=90) as ws:
                print('Connected LBank:', datetime.datetime.now().isoformat())
                subs = dict(
                    e="bvc=201",
                    x="3",
                    y=id,
                    a=dict(
                        i=f"{k}_{price_precision}_25",
                    ),
                    z = "1"
                )
                logger.warning(f"send {subs}")
                await ws.send_str(json.dumps(subs))

                async def send_pong_periodically():
                    nonlocal pong_flag
                    try:
                        while pong_flag:
                            await asyncio.sleep(5)  # Ожидание 15 секунд
                            if pong_flag:
                                await ws.send_str('ping')
                    except Exception as ep:
                        print(f'LBank exception send ping: {ep}')

                pong_task = asyncio.create_task(send_pong_periodically())

                async for msg in ws:
                    if open_sockets_lbank[k][2]:
                        print('LBank go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        try:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                raw = msg.data
                                try:
                                    decoded = raw.decode("utf-8")
                                except Exception:
                                    decoded = gzip.decompress(raw).decode("utf-8")
                                data = json.loads(decoded)

                                if 'b' in data and 's' in data:
                                    asks = data.get('s')
                                    bids = data.get('b')
                                    lbank_futures_data[k] = {
                                        'asks': asks,
                                        'bids': bids,
                                        'time': datetime.datetime.now()
                                    }
                        except Exception:
                            print('error')

                    except Exception as e:
                        print('SocketGETerrorLBank', e)
                        logger.exception('SocketExcept')
                        try:
                            lbank_futures_data.pop(k)
                        except Exception as e:
                            print('cant pop data lbank', e)

    except Exception as e:
        print('Socket Error:', e)
    finally:
        try:
            pong_flag = False
            if pong_task:
                pong_task.cancel()
                await pong_task
        except asyncio.CancelledError:
            pass
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            open_sockets_lbank[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)
        print('Disconnected LBank:', datetime.datetime.now().isoformat())
# --------------------------------------------------------------------------------------------------------------


async def socket_spot_kucoin(k):
    global kucoin_spot_data, token_kucoin, spot_open_sockets_kucoin
    pong_task = None
    pong_flag = True
    id = random.randint(100000, 999999)
    url = f'wss://ws-api-spot.kucoin.com/?token={token_kucoin}'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=18,
                                                 receive_timeout=90) as ws:
                print('ConnectedKucoin:', datetime.datetime.now().isoformat())
                print(k.replace('USDT', 'USDTM'))
                subs = dict(
                    id=id,
                    type='subscribe',
                    topic=f"/spotMarket/level2Depth50:{k.replace('USDT', '-USDT')}",
                    response='true',
                    privateChannel='false'
                )
                await ws.send_str(json.dumps(subs))

                async def send_pong_periodically():
                    nonlocal pong_flag
                    try:
                        while pong_flag:
                            await asyncio.sleep(18)  # Ожидание 15 секунд
                            if pong_flag:
                                ping_msg = dict(id=id, type='ping')
                                ping_msg = json.dumps(ping_msg)
                                await ws.send_str(ping_msg)
                    except Exception as ep:
                        print(f'Kucoin exception send ping: {ep}')

                pong_task = asyncio.create_task(send_pong_periodically())

                async for msg in ws:
                    if spot_open_sockets_kucoin[k][2]:
                        print('Kucoin go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)
                            data = msg.get('data')
                            topic = msg.get('topic')
                            if topic is not None:
                                asks = data['asks']
                                bids = data['bids']
                                kucoin_spot_data[k] = {
                                    'asks': asks,
                                    'bids': bids,
                                    'time': datetime.datetime.now()
                                }
                    except Exception as e:
                        print('SpotSocketGETerrorKucoin Cleaning', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Spot Socket Error:', e)
    finally:
        try:
            pong_flag = False
            if pong_task:
                pong_task.cancel()
                await pong_task
        except asyncio.CancelledError:
            pass
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            spot_open_sockets_kucoin[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)

        print('Disconnected Kucoin spot:', datetime.datetime.now().isoformat())


async def socket_spot_okx(k):
    global okx_spot_data, spot_open_sockets_okx
    url = 'wss://ws.okx.com:8443/ws/v5/public'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=20, receive_timeout=60) as ws:

                print('ConnectedOkx spot:', datetime.datetime.now().isoformat())
                subs = dict(
                    op='subscribe',
                    args=[
                        dict(channel='books5', instType='SPOT', instId=f"{k.replace('USDT', '-USDT')}")
                    ]
                )
                await ws.send_str(json.dumps(subs))

                async for msg in ws:
                    if spot_open_sockets_okx[k][2]:
                        print('Okx go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)
                            data = msg.get('data')
                            if data is not None:
                                asks = data[0]['asks']
                                bids = data[0]['bids']
                                okx_spot_data[k] = {
                                    'asks': asks,
                                    'bids': bids,
                                    'time': datetime.datetime.now()
                                }
                    except Exception as e:
                        print('Spot SocketGETerrorOkx', e)
                        logger.exception('Spot SocketExcept')
    except Exception as e:
        print('Spot Socket Error:', e)
    finally:
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            spot_open_sockets_okx[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)

        print('Disconnected Okx spot:', datetime.datetime.now().isoformat())


def handle_message_bybit_spot(message):
    global bybit_spot_data, spot_open_sockets_bybit, bybit_spot_sockets
    asks = sorted(message['data']['a'], key=takeBybit)
    bids = sorted(message['data']['b'], key=takeBybit, reverse=True)
    bybit_spot_data[message['topic'].split('.')[-1]] = {
        'asks': asks,
        'bids': bids,
        'time': datetime.datetime.now()
    }


async def socket_spot_bybit(k):
    global bybit_spot_sockets
    ws_spot = WebSocket(
        testnet=False,
        channel_type="spot",
    )

    ws_spot.orderbook_stream(
        depth=50,
        symbol=f"{k}",
        callback=handle_message_bybit_spot
    )

    try:
        while True:
            await asyncio.sleep(1)  # Просто держим задачу "живой"
    except asyncio.CancelledError:
        print(f"[INFO] Cancelling WebSocket for Bybit spot: {k}")
        try:
            if hasattr(ws_spot, "exited") and not ws_spot.exited:
                ws_spot.exit()
        except Exception as e:
            print(f"[ERROR] Failed to stop ws_spot for {k}: {e}")
        raise  # обязательно пробрасываем CancelledError дальше


async def socket_spot_mexc(k):
    global mexc_spot_data, spot_open_sockets_mexc
    pong_task = None
    pong_flag = True
    url = 'ws://wbs-api.mexc.com/ws'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=10, receive_timeout=40) as ws:

                print('ConnectedMexc spot:', datetime.datetime.now().isoformat())
                subs = dict(
                    method='SUBSCRIPTION',
                    params=[f'spot@public.limit.depth.v3.api.pb@{k}@20']
                )
                await ws.send_str(json.dumps(subs))

                async def send_pong_periodically():
                    nonlocal pong_flag
                    try:
                        while pong_flag:
                            await asyncio.sleep(20)  # Ожидание 15 секунд
                            if pong_flag:
                                ping_msg = dict(method='ping')
                                ping_msg = json.dumps(ping_msg)
                                await ws.send_str(ping_msg)
                    except Exception as ep:
                        print(f'Mexc exception send ping: {ep}')

                pong_task = asyncio.create_task(send_pong_periodically())

                async for msg in ws:
                    if spot_open_sockets_mexc[k][2]:
                        print('Mexc go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.BINARY:
                            try:
                                # Распаковка обёртки
                                result = PushDataV3ApiWrapper_pb2.PushDataV3ApiWrapper()
                                result.ParseFromString(msg.data)

                               # logger.info(f"Wrapper: channel={result.channel}, symbol={result.symbol}")

                                # Проверка — это ли нужный тип сообщения
                                if result.HasField("publicLimitDepths"):
                                    depth = result.publicLimitDepths  # ✅ доступ к нужному body-полю

                                    asks = [{"p": a.price, "v": a.quantity} for a in depth.asks]
                                    bids = [{"p": b.price, "v": b.quantity} for b in depth.bids]

                                   # logger.info(f"Asks: {asks}")
                                   # logger.info(f"Bids: {bids}")

                                    mexc_spot_data[k] = {
                                        "asks": asks,
                                        "bids": bids,
                                        "time": datetime.datetime.now(),
                                    }

                            except Exception as e:
                                logger.exception("Protobuf deserialization error")
                        elif msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)
                          #  logger.info(f"mexc msg: {msg}")
                            data = msg.get('d')
                            if data is not None:
                                try:
                                    asks = data['asks']
                                    bids = data['bids']
                                    mexc_spot_data[k] = {
                                        'asks': asks,
                                        'bids': bids,
                                        'time': datetime.datetime.now()
                                    }
                                except Exception as e:
                                    print('mexc error socket msg', e)
                    except Exception as e:
                        print('SocketGETerrorMexc', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Socket Error:', e)
    finally:
        try:
            pong_flag = False
            if pong_task:
                pong_task.cancel()
                await pong_task
        except asyncio.CancelledError:
            pass
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            spot_open_sockets_mexc[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)

        print('Disconnected Mexc spot:', datetime.datetime.now().isoformat())


async def socket_spot_gateio(k):
    global gateio_spot_data, spot_open_sockets_gateio
    url = 'wss://api.gateio.ws/ws/v4/'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=10, receive_timeout=40) as ws:

                print('ConnectedGateio spot:', datetime.datetime.now().isoformat())
                subs = dict(
                    channel='spot.order_book',
                    event='subscribe',
                    payload=[f"{k.replace('USDT', '_USDT')}", "50", "100ms"]

                )
                await ws.send_str(json.dumps(subs))

                async for msg in ws:
                    if spot_open_sockets_gateio[k][2]:
                        print('Gateio go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)
                            data = msg.get('result')
                            if data is not None and 'status' not in data.keys():
                                asks = data['asks']
                                bids = data['bids']
                                gateio_spot_data[k] = {
                                    'asks': asks,
                                    'bids': bids,
                                    'time': datetime.datetime.now()
                                }
                    except Exception as e:
                        print('SocketGETerrorGateio', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Spot Socket Error:', e)
    finally:
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            spot_open_sockets_gateio[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)

        print('Disconnected Gateio spot:', datetime.datetime.now().isoformat())


async def socket_spot_bitget(k):
    global bitget_spot_data, spot_open_sockets_bitget
    pong_task = None
    pong_flag = True
    url = 'wss://ws.bitget.com/v2/ws/public'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=10, receive_timeout=30) as ws:

                print('ConnectedBitget spot:', datetime.datetime.now().isoformat())
                subs = dict(
                    op='subscribe',
                    args=[
                        dict(instType="SPOT",
                             channel="books15",
                             instId=f"{k}")
                    ],
                )
                await ws.send_str(json.dumps(subs))

                async def send_pong_periodically():
                    nonlocal pong_flag
                    try:
                        while pong_flag:
                            await asyncio.sleep(30)  # Ожидание 15 секунд
                            if pong_flag:
                                await ws.send_str('ping')
                    except Exception as ep:
                        print(f'Bitget exception send ping: {ep}')

                pong_task = asyncio.create_task(send_pong_periodically())

                async for msg in ws:
                    if spot_open_sockets_bitget[k][2]:
                        print('Bitget go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            if msg.data != "pong":
                                msg = json.loads(msg.data)
                                data = msg.get('data')
                                if data is not None:
                                    asks = data[0]['asks']
                                    bids = data[0]['bids']
                                    bitget_spot_data[k] = {
                                        'asks': asks,
                                        'bids': bids,
                                        'time': datetime.datetime.now()
                                    }
                    except Exception as e:
                        print('SocketGETerrorBitget spot', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Socket Error spot:', e)
    finally:
        try:
            pong_flag = False
            if pong_task:
                pong_task.cancel()
                await pong_task
        except asyncio.CancelledError:
            pass
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            spot_open_sockets_bitget[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)

        print('Disconnected Bitget spot:', datetime.datetime.now().isoformat())


async def socket_spot_huobi(k):
    global huobi_spot_data, spot_open_sockets_huobi
    url = 'wss://api.huobi.pro/ws'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=2, receive_timeout=90) as ws:

                print('ConnectedHuobi spot:', datetime.datetime.now().isoformat())
                subs = dict(
                    sub=f"market.{k.lower()}.depth.step0"
                )
                await ws.send_str(json.dumps(subs))

                async for msg in ws:
                    if spot_open_sockets_huobi[k][2]:
                        print('Huobi go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        try:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                msg = gzip.decompress(msg.data).decode('utf-8')
                        except Exception:
                            print('error')
                        msg = json.loads(msg)
                        if 'ping' in msg:
                            await ws.send_str("pong")
                        if 'tick' in msg:
                            data = msg.get('tick')
                            if data is not None:
                                asks = data['asks']
                                bids = data['bids']
                                huobi_spot_data[k] = {
                                    'asks': asks,
                                    'bids': bids,
                                    'time': datetime.datetime.now()
                                }
                    except Exception as e:
                        print('SocketGETerrorHuobi', e)
                        logger.exception('SocketExcept')
                        try:
                            huobi_spot_data.pop(k)
                        except Exception as e:
                            print('cant pop data huobi', e)
    except Exception as e:
        print('Socket Error:', e)
    finally:
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            spot_open_sockets_huobi[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)
        print('Disconnected Huobi spot:', datetime.datetime.now().isoformat())


async def socket_spot_binance(k):
    global binance_spot_data, spot_open_sockets_binance
    url = 'wss://stream.binance.com:9443/ws'
    id = random.randint(100000, 999999)
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=20, receive_timeout=60) as ws:

                print('ConnectedBinance spot:', datetime.datetime.now().isoformat())
                subs = {
                    "method": "SUBSCRIBE",
                    "params": [f"{k.lower()}@depth20@100ms"],
                    "id": id
                }
                await ws.send_str(json.dumps(subs))

                async for msg in ws:
                    if spot_open_sockets_binance[k][2]:
                        print('Binance go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)

                            if "bids" in msg and "asks" in msg:
                                bids = sorted(msg["bids"], key=lambda x: float(x[0]), reverse=True)
                                asks = sorted(msg["asks"], key=lambda x: float(x[0]))

                                binance_spot_data[k] = {
                                    'asks': asks,
                                    'bids': bids,
                                    'time': datetime.datetime.now()
                                }
                    except Exception as e:
                        print('SocketGETerrorBinance', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Spot Socket Error:', e)
    finally:
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            spot_open_sockets_binance[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)
        print('Disconnected Binance spot:', datetime.datetime.now().isoformat())


async def socket_spot_bingx(k):
    global bingx_spot_data, spot_open_sockets_bingx
    url = 'wss://open-api-ws.bingx.com/market'
    if k == 'REDUSDT':
        repl = 'REDSTONEUSDT'
    else:
        repl = k
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=5, receive_timeout=90) as ws:

                print('ConnectedBingx spot:', datetime.datetime.now().isoformat())

                subs = {"id": "1", "reqType": "sub", "dataType": f"{repl.replace('USDT', '-USDT')}@depth50"}

                await ws.send_str(json.dumps(subs))

                async for msg in ws:
                    if spot_open_sockets_bingx[k][2]:
                        print('BingX go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        try:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                msg = gzip.decompress(msg.data).decode('utf-8')
                        except Exception:
                            print('error')
                        msg = json.loads(msg)
                        if 'ping' in msg:
                            await ws.send_str("pong")
                        else:
                            data = msg.get('data')

                            if data is not None:
                                asks = sorted(data.get('asks'), key=takeBybit)
                                bids = data.get('bids')

                                bingx_spot_data[k] = {
                                    'asks': asks,
                                    'bids': bids,
                                    'time': datetime.datetime.now()
                                }
                    except Exception as e:
                        print('SocketGETerrorBingx', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Spot Socket Error:', e)
    finally:
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            spot_open_sockets_bingx[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)
        print('Disconnected Bingx spot:', datetime.datetime.now().isoformat())


async def socket_spot_bitmart(k):
    global bitmart_spot_data, spot_open_sockets_bitmart
    url = 'wss://ws-manager-compress.bitmart.com/api?protocol=1.1'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=5, receive_timeout=90) as ws:

                print('ConnectedBitmart spot:', datetime.datetime.now().isoformat())
                subs = dict(
                    op="subscribe",
                    args=[f'spot/depth20:{k.replace("USDT", "_USDT")}']
                )

                await ws.send_str(json.dumps(subs))

                async for msg in ws:
                    if spot_open_sockets_bitmart[k][2]:
                        print('Bitmart go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)
                            data = msg.get('data')
                            if data is not None:
                                asks = data[0].get('asks')
                                bids = data[0].get('bids')
                                bitmart_spot_data[k] = {
                                    'asks': asks,
                                    'bids': bids,
                                    'time': datetime.datetime.now()
                                }
                    except Exception as e:
                        print('SocketGETerrorBitmart', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Spot Socket Error:', e)
    finally:
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            spot_open_sockets_bitmart[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)
        print('Disconnected Bitmart spot:', datetime.datetime.now().isoformat())


async def socket_spot_poloniex(k):
    global poloniex_spot_data, token_poloniex, spot_open_sockets_poloniex
    url = f'wss://ws.poloniex.com/ws/public'
    pong_task = None
    pong_flag = True
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=18, receive_timeout=45) as ws:
                print('ConnectedPoloniexSpot:', datetime.datetime.now().isoformat())
                subs = dict(
                    event='subscribe',
                    channel=["book"],
                    symbols=[f"{k.replace('USDT', '_USDT')}"],
                    depth=20
                )
                await ws.send_str(json.dumps(subs))

                async def send_pong_periodically():
                    nonlocal pong_flag
                    while pong_flag:
                        await asyncio.sleep(15)  # Ожидание 15 секунд
                        if pong_flag:
                            ping_msg = dict(event='ping')
                            ping_msg = json.dumps(ping_msg)
                            await ws.send_str(ping_msg)

                pong_task = asyncio.create_task(send_pong_periodically())

                async for msg in ws:
                    if spot_open_sockets_poloniex[k][2]:
                        print('Poloniex go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)
                            data = msg.get('data')
                            if data is not None:

                                asks = data[0]['asks']
                                bids = data[0]['bids']

                                poloniex_spot_data[k] = {
                                    'asks': asks,
                                    'bids': bids,
                                    'time': datetime.datetime.now()
                                }
                    except Exception as e:
                        print('SpotSocketGETerrorKucoin Cleaning', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Spot Socket Error:', e)
    finally:
        try:
            pong_flag = False
            pong_task.cancel()
        except Exception as e:
            print('pong_task cancel error:', e)
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            spot_open_sockets_poloniex[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)

        print('Disconnected Poloniex spot:', datetime.datetime.now().isoformat())

async def socket_spot_coinex(k):
    global coinex_spot_data, spot_open_sockets_coinex
    url = f'wss://socket.coinex.com/v2/spot'
    pong_flag = True
    pong_task = None
    id = random.randint(100000, 999999)
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url) as ws:

                print('ConnectedCoinExSpot:', datetime.datetime.now().isoformat())

                subs = dict(
                    method='depth.subscribe',
                    params=dict(market_list=[[f'{k}', 50, "0", True]]),
                    id=id
                )
                await ws.send_str(json.dumps(subs))

                async def send_pong_periodically_coinex():
                    nonlocal pong_flag
                    while pong_flag:
                        await asyncio.sleep(10)
                        if pong_flag:
                            try:
                                # Ожидание 15 секунд
                                dataSend = dict(method="server.ping", params=dict(), id=id)
                                dataSend = json.dumps(dataSend)
                                await ws.send_str(dataSend)
                            except Exception as e:
                                print(f'Exception socket spot coinex {e} add bad sockets')
                                break

                pong_task = asyncio.create_task(send_pong_periodically_coinex())

                async for msg in ws:
                    if spot_open_sockets_coinex[k][2]:
                        await ws.close()
                        break  # Просто break, не ws.close() здесь
                    try:
                        try:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                msg = gzip.decompress(msg.data).decode('utf-8')
                        except Exception:
                            print('error')
                        msg = json.loads(msg)

                        data = msg.get('data')

                        if data is not None and 'result' not in data:
                            depth = data.get('depth')
                            asks = depth['asks']
                            bids = depth['bids']
                            asks = sorted(asks, key=takeBybit)
                            bids = sorted(bids, key=takeBybit, reverse=True)

                            coinex_spot_data[k] = {
                                'asks': asks,
                                'bids': bids,
                                'time': datetime.datetime.now()
                            }
                    except Exception as e:
                        print('SpotSocketGETerrorCoinEx msg in ws:', e)
                        logger.exception('SocketExcept')
    except Exception as e:
        print('Spot Socket CoinEx Error:', e)
    finally:
        try:
            pong_flag = False
            if pong_task:
                pong_task.cancel()
                try:
                    await pong_task
                except asyncio.CancelledError:
                    pass
        except asyncio.CancelledError:
            pass
        try:
            if not ws.closed:  # или: if ws and not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            spot_open_sockets_coinex[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)

        print('Disconnected CoinEx spot:', datetime.datetime.now().isoformat())


async def socket_spot_ourbit(k):
    global ourbit_spot_data, spot_open_sockets_ourbit
    pong_task = None
    pong_flag = True
    url = 'wss://wbs.ourbit.com/ws'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=10, receive_timeout=40) as ws:

                print('ConnectedOurbit spot:', datetime.datetime.now().isoformat())
                subs = dict(
                    method='SUBSCRIPTION',
                    params=[f'spot@public.limit.depth.v3.api@{k}@20']
                )
                await ws.send_str(json.dumps(subs))

                async def send_pong_periodically():
                    nonlocal pong_flag
                    try:
                        while pong_flag:
                            await asyncio.sleep(20)  # Ожидание 15 секунд
                            if pong_flag:
                                ping_msg = dict(method='ping')
                                ping_msg = json.dumps(ping_msg)
                                await ws.send_str(ping_msg)
                    except Exception as ep:
                        print(f'Ourbit exception send ping: {ep}')

                pong_task = asyncio.create_task(send_pong_periodically())

                async for msg in ws:
                    if spot_open_sockets_ourbit[k][2]:
                        print('Ourbit go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)
                            data = msg.get('d')
                            if data is not None:
                                try:
                                    asks = data['asks']
                                    bids = data['bids']
                                    ourbit_spot_data[k] = {
                                        'asks': asks,
                                        'bids': bids,
                                        'time': datetime.datetime.now()
                                    }
                                except Exception as e:
                                    logger.exception('ourbit error socket msg')
                    except Exception as e:
                        logger.exception('SocketExcept Ourbit inner')
    except Exception as e:
        logger.exception('SocketExcept ourbit outer')
    finally:
        try:
            pong_flag = False
            if pong_task:
                pong_task.cancel()
                await pong_task
        except asyncio.CancelledError:
            pass
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            spot_open_sockets_ourbit[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)

        print('Disconnected Ourbit spot:', datetime.datetime.now().isoformat())


async def socket_spot_lbank(k):
    global lbank_spot_data, spot_open_sockets_lbank
    url = 'wss://www.lbkex.net/ws/V2/'
    try:
        async with aiohttp.ClientSession() as socket_session:
            async with socket_session.ws_connect(url, heartbeat=2, receive_timeout=90) as ws:

                print('Connected LBank spot:', datetime.datetime.now().isoformat())
                subs = dict(
                    action="subscribe",
                    subscribe="depth",
                    depth="5",
                    pair=f"{k.replace('USDT', '_usdt').lower()}"
                )
                await ws.send_str(json.dumps(subs))

                async for msg in ws:
                    if spot_open_sockets_lbank[k][2]:
                        print('LBank go break:', datetime.datetime.now().isoformat())
                        await ws.close()
                        break
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            msg = json.loads(msg.data)
                            if 'action' in msg and msg['action'] == 'ping':
                                await ws.send_str(json.dumps({"action":"ping", "ping": msg["ping"]}))
                            if 'depth' in msg:
                                data = msg.get('depth')
                                if data is not None:
                                    asks = data['asks']
                                    bids = data['bids']
                                    lbank_spot_data[k] = {
                                        'asks': asks,
                                        'bids': bids,
                                        'time': datetime.datetime.now()
                                    }
                    except Exception as e:
                        print('SocketGETerrorLBank', e)
                        logger.exception('SocketExcept')
                        try:
                            lbank_spot_data.pop(k)
                        except Exception as e:
                            print('cant pop data lbank', e)
    except Exception as e:
        print('Socket Error:', e)
    finally:
        try:
            if not ws.closed:
                await ws.close()
        except Exception as e:
            print(e)
        try:
            spot_open_sockets_lbank[k][2] = 1
        except Exception as e:
            print('cant finally change to 1', e)
        print('Disconnected LBank spot:', datetime.datetime.now().isoformat())


async def check_data(m1, m2, post_coin, sp_or_ft):
    global mexc_amounts, gateio_amounts, huobi_amounts, okx_amounts, kucoin_amounts, bitmart_amounts, poloniex_amounts, coins_list_full

    gateio_value = huobi_value = okx_value = kucoin_value = bitmart_value = poloniex_value = mexc_value = None

    async with gateio_lock:
        gateio_value = gateio_amounts.get(post_coin)

    async with huobi_lock:
        huobi_value = huobi_amounts.get(post_coin)

    async with okx_lock:
        okx_value = okx_amounts.get(post_coin)

    async with kucoin_lock:
        kucoin_value = kucoin_amounts.get(post_coin)

    async with bitmart_lock:
        bitmart_value = bitmart_amounts.get(post_coin)

    async with poloniex_lock:
        poloniex_value = poloniex_amounts.get(post_coin)

    async with mexc_lock:
        if post_coin == 'SOONUSDT':
            repl = 'SOONNETWORKUSDT'
        elif post_coin == 'ARTUSDT':
            repl = 'LIVEARTUSDT'
        else:
            repl = post_coin
        mexc_value = mexc_amounts.get(repl)

    if sp_or_ft == 'futures':
        try:
            if len(post_coin) < 20 and m1 in markets_list and m2 in markets_list:
                if (m1 == 'Kucoin' or m2 == 'Kucoin') and token_kucoin != '':
                    if post_coin in open_sockets_kucoin.keys():
                        if open_sockets_kucoin[post_coin][2] != 1:
                            open_sockets_kucoin[post_coin][1] = datetime.datetime.now()
                    if post_coin not in open_sockets_kucoin.keys():
                        if m1 == 'Kucoin':
                            print('start:', m1, post_coin, sp_or_ft)
                            asyncio.create_task(run_socket(m1, post_coin, sp_or_ft))
                        elif m2 == 'Kucoin':
                            print('start:', m2, post_coin, sp_or_ft)
                            asyncio.create_task(run_socket(m2, post_coin, sp_or_ft))

            if (m1 == 'Okx') or (m2 == 'Okx'):
                if m1 == 'Okx':
                    asyncio.create_task(start_sock(m1, post_coin, open_sockets_okx, sp_or_ft))
                elif m2 == 'Okx':
                    asyncio.create_task(start_sock(m2, post_coin, open_sockets_okx, sp_or_ft))

            if (m1 == 'Bybit') or (m2 == 'Bybit'):
                if m1 == 'Bybit':
                    asyncio.create_task(start_sock(m1, post_coin, open_sockets_bybit, sp_or_ft))
                elif m2 == 'Bybit':
                    asyncio.create_task(start_sock(m2, post_coin, open_sockets_bybit, sp_or_ft))

            if (m1 == 'Mexc') or (m2 == 'Mexc'):
                if m1 == 'Mexc':
                    asyncio.create_task(start_sock(m1, post_coin, open_sockets_mexc, sp_or_ft))
                elif m2 == 'Mexc':
                    asyncio.create_task(start_sock(m2, post_coin, open_sockets_mexc, sp_or_ft))

            if (m1 == 'Gateio') or (m2 == 'Gateio'):
                if m1 == 'Gateio':
                    asyncio.create_task(start_sock(m1, post_coin, open_sockets_gateio, sp_or_ft))
                elif m2 == 'Gateio':
                    asyncio.create_task(start_sock(m2, post_coin, open_sockets_gateio, sp_or_ft))

            if (m1 == 'Bitget') or (m2 == 'Bitget'):
                if m1 == 'Bitget':
                    asyncio.create_task(start_sock(m1, post_coin, open_sockets_bitget, sp_or_ft))
                elif m2 == 'Bitget':
                    asyncio.create_task(start_sock(m2, post_coin, open_sockets_bitget, sp_or_ft))

            if (m1 == 'Huobi') or (m2 == 'Huobi'):
                if m1 == 'Huobi':
                    asyncio.create_task(start_sock(m1, post_coin, open_sockets_huobi, sp_or_ft))
                elif m2 == 'Huobi':
                    asyncio.create_task(start_sock(m2, post_coin, open_sockets_huobi, sp_or_ft))

            if (m1 == 'Binance') or (m2 == 'Binance'):
                if m1 == 'Binance':
                    asyncio.create_task(start_sock(m1, post_coin, open_sockets_binance, sp_or_ft))
                elif m2 == 'Binance':
                    asyncio.create_task(start_sock(m2, post_coin, open_sockets_binance, sp_or_ft))

            if (m1 == 'BingX') or (m2 == 'BingX'):
                if m1 == 'BingX':
                    asyncio.create_task(start_sock(m1, post_coin, open_sockets_bingx, sp_or_ft))
                elif m2 == 'BingX':
                    asyncio.create_task(start_sock(m2, post_coin, open_sockets_bingx, sp_or_ft))

            if (m1 == 'BitMart') or (m2 == 'BitMart'):
                if m1 == 'BitMart':
                    asyncio.create_task(start_sock(m1, post_coin, open_sockets_bitmart, sp_or_ft))
                elif m2 == 'BitMart':
                    asyncio.create_task(start_sock(m2, post_coin, open_sockets_bitmart, sp_or_ft))

            if (m1 == 'Poloniex') or (m2 == 'Poloniex'):
                if m1 == 'Poloniex':
                    asyncio.create_task(start_sock(m1, post_coin, open_sockets_poloniex, sp_or_ft))
                elif m2 == 'Poloniex':
                    asyncio.create_task(start_sock(m2, post_coin, open_sockets_poloniex, sp_or_ft))

            if (m1 == 'CoinEx') or (m2 == 'CoinEx'):
                if m1 == 'CoinEx':
                    asyncio.create_task(start_sock(m1, post_coin, open_sockets_coinex, sp_or_ft))
                elif m2 == 'CoinEx':
                    asyncio.create_task(start_sock(m2, post_coin, open_sockets_coinex, sp_or_ft))

            if (m1 == 'Ourbit') or (m2 == 'Ourbit'):
                if m1 == 'Ourbit':
                    asyncio.create_task(start_sock(m1, post_coin, open_sockets_ourbit, sp_or_ft))
                elif m2 == 'Ourbit':
                    asyncio.create_task(start_sock(m2, post_coin, open_sockets_ourbit, sp_or_ft))

            if (m1 == 'Hyperliquid') or (m2 == 'Hyperliquid'):
                if m1 == 'Hyperliquid':
                    asyncio.create_task(start_sock(m1, post_coin, open_sockets_hyperliquid, sp_or_ft))
                elif m2 == 'Hyperliquid':
                    asyncio.create_task(start_sock(m2, post_coin, open_sockets_hyperliquid, sp_or_ft))

            if (m1 == 'LBank') or (m2 == 'LBank'):
                if m1 == 'LBank':
                    asyncio.create_task(start_sock(m1, post_coin, open_sockets_lbank, sp_or_ft))
                elif m2 == 'LBank':
                    asyncio.create_task(start_sock(m2, post_coin, open_sockets_lbank, sp_or_ft))

            asks1 = None
            bids1 = None
            asks2 = None
            bids2 = None
            try:
                if (m1 == 'Okx'):
                    asks1 = copy.deepcopy(okx_futures_data[post_coin]['asks'])
                    bids1 = copy.deepcopy(okx_futures_data[post_coin]['bids'])
                elif m1 == 'Kucoin':
                    asks1 = copy.deepcopy(kucoin_futures_data[post_coin]['asks'])
                    bids1 = copy.deepcopy(kucoin_futures_data[post_coin]['bids'])
                elif m1 == 'Bybit':
                    asks1 = copy.deepcopy(bybit_futures_data[post_coin]['asks'])
                    bids1 = copy.deepcopy(bybit_futures_data[post_coin]['bids'])
                elif m1 == 'Mexc':
                    asks1 = copy.deepcopy(mexc_futures_data[post_coin]['asks'])
                    bids1 = copy.deepcopy(mexc_futures_data[post_coin]['bids'])
                elif m1 == 'Gateio':
                    asks1 = copy.deepcopy(gateio_futures_data[post_coin]['asks'])
                    bids1 = copy.deepcopy(gateio_futures_data[post_coin]['bids'])
                elif m1 == 'Bitget':
                    asks1 = copy.deepcopy(bitget_futures_data[post_coin]['asks'])
                    bids1 = copy.deepcopy(bitget_futures_data[post_coin]['bids'])
                elif m1 == 'Huobi':
                    asks1 = copy.deepcopy(huobi_futures_data[post_coin]['asks'])
                    bids1 = copy.deepcopy(huobi_futures_data[post_coin]['bids'])
                elif m1 == 'Binance':
                    asks1 = copy.deepcopy(binance_futures_data[post_coin]['asks'])
                    bids1 = copy.deepcopy(binance_futures_data[post_coin]['bids'])
                elif m1 == 'BingX':
                    asks1 = copy.deepcopy(bingx_futures_data[post_coin]['asks'])
                    bids1 = copy.deepcopy(bingx_futures_data[post_coin]['bids'])
                elif m1 == 'BitMart':
                    asks1 = copy.deepcopy(bitmart_futures_data[post_coin]['asks'])
                    bids1 = copy.deepcopy(bitmart_futures_data[post_coin]['bids'])
                elif m1 == 'Poloniex':
                    asks1 = copy.deepcopy(poloniex_futures_data[post_coin]['asks'])
                    bids1 = copy.deepcopy(poloniex_futures_data[post_coin]['bids'])
                elif m1 == 'CoinEx':
                    asks1 = copy.deepcopy(coinex_futures_data[post_coin]['asks'])
                    bids1 = copy.deepcopy(coinex_futures_data[post_coin]['bids'])
                elif m1 == 'Ourbit':
                    asks1 = copy.deepcopy(ourbit_futures_data[post_coin]['asks'])
                    bids1 = copy.deepcopy(ourbit_futures_data[post_coin]['bids'])
                elif m1 == 'Hyperliquid':
                    asks1 = copy.deepcopy(hyperliquid_futures_data[post_coin]['asks'])
                    bids1 = copy.deepcopy(hyperliquid_futures_data[post_coin]['bids'])
                elif m1 == 'LBank':
                    asks1 = copy.deepcopy(lbank_futures_data[post_coin]['asks'])
                    bids1 = copy.deepcopy(lbank_futures_data[post_coin]['bids'])

                if (m2 == 'Okx'):
                    asks2 = copy.deepcopy(okx_futures_data[post_coin]['asks'])
                    bids2 = copy.deepcopy(okx_futures_data[post_coin]['bids'])
                elif m2 == 'Kucoin':
                    asks2 = copy.deepcopy(kucoin_futures_data[post_coin]['asks'])
                    bids2 = copy.deepcopy(kucoin_futures_data[post_coin]['bids'])
                elif m2 == 'Bybit':
                    asks2 = copy.deepcopy(bybit_futures_data[post_coin]['asks'])
                    bids2 = copy.deepcopy(bybit_futures_data[post_coin]['bids'])
                elif m2 == 'Mexc':
                    asks2 = copy.deepcopy(mexc_futures_data[post_coin]['asks'])
                    bids2 = copy.deepcopy(mexc_futures_data[post_coin]['bids'])
                elif m2 == 'Gateio':
                    asks2 = copy.deepcopy(gateio_futures_data[post_coin]['asks'])
                    bids2 = copy.deepcopy(gateio_futures_data[post_coin]['bids'])
                elif m2 == 'Bitget':
                    asks2 = copy.deepcopy(bitget_futures_data[post_coin]['asks'])
                    bids2 = copy.deepcopy(bitget_futures_data[post_coin]['bids'])
                elif m2 == 'Huobi':
                    asks2 = copy.deepcopy(huobi_futures_data[post_coin]['asks'])
                    bids2 = copy.deepcopy(huobi_futures_data[post_coin]['bids'])
                elif m2 == 'Binance':
                    asks2 = copy.deepcopy(binance_futures_data[post_coin]['asks'])
                    bids2 = copy.deepcopy(binance_futures_data[post_coin]['bids'])
                elif m2 == 'BingX':
                    asks2 = copy.deepcopy(bingx_futures_data[post_coin]['asks'])
                    bids2 = copy.deepcopy(bingx_futures_data[post_coin]['bids'])
                elif m2 == 'BitMart':
                    asks2 = copy.deepcopy(bitmart_futures_data[post_coin]['asks'])
                    bids2 = copy.deepcopy(bitmart_futures_data[post_coin]['bids'])
                elif m2 == 'Poloniex':
                    asks2 = copy.deepcopy(poloniex_futures_data[post_coin]['asks'])
                    bids2 = copy.deepcopy(poloniex_futures_data[post_coin]['bids'])
                elif m2 == 'CoinEx':
                    asks2 = copy.deepcopy(coinex_futures_data[post_coin]['asks'])
                    bids2 = copy.deepcopy(coinex_futures_data[post_coin]['bids'])
                elif m2 == 'Ourbit':
                    asks2 = copy.deepcopy(ourbit_futures_data[post_coin]['asks'])
                    bids2 = copy.deepcopy(ourbit_futures_data[post_coin]['bids'])
                elif m2 == 'Hyperliquid':
                    asks2 = copy.deepcopy(hyperliquid_futures_data[post_coin]['asks'])
                    bids2 = copy.deepcopy(hyperliquid_futures_data[post_coin]['bids'])
                elif m2 == 'LBank':
                    asks2 = copy.deepcopy(lbank_futures_data[post_coin]['asks'])
                    bids2 = copy.deepcopy(lbank_futures_data[post_coin]['bids'])

            except KeyError:
                send_data = {
                    "m1": m1,
                    "m2": m2,
                    "post_coin": post_coin,
                    "in": 'wait',
                    "out": 'wait',
                    "asks1": [[0]],
                    "bids1": [[0]],
                    "asks2": [[0]],
                    "bids2": [[0]],
                    "sp_or_ft": sp_or_ft,
                    "time": f"{datetime.datetime.now().minute}:{datetime.datetime.now().second}",
                    "current_time": f"{datetime.datetime.timestamp(datetime.datetime.now())}",
                }

                socket_thread = threading.Thread(target=send_data_to_unix_socket, args=(send_data,))
                socket_thread.daemon = True
                socket_thread.start()

            if m1 != 'Gateio':
                if asks1 is not None and bids1 is not None:
                    best_asks1 = asks1[0][0]
                    best_bids1 = bids1[0][0]
            else:
                if asks1 is not None and bids1 is not None:
                    best_asks1 = asks1[0]['p']
                    best_bids1 = bids1[0]['p']

            if m2 != 'Gateio':
                if asks2 is not None and bids2 is not None:
                    best_asks2 = asks2[0][0]
                    best_bids2 = bids2[0][0]
            else:
                if asks2 is not None and bids2 is not None:
                    best_asks2 = asks2[0]['p']
                    best_bids2 = bids2[0]['p']

            send_asks1 = []
            send_bids1 = []
            send_asks2 = []
            send_bids2 = []
            if asks1 is not None and asks2 is not None and bids1 is not None and bids2 is not None:
                try:
                    if m1 == 'Gateio':
                        for a in asks1:
                            a['s'] = float(float(a['s']) / float(1 / float(gateio_value)))
                        for b in bids1:
                            b['s'] = float(float(b['s']) / float(1 / float(gateio_value)))
                    if m1 == 'Huobi':
                        for a in asks1:
                            a[1] = float(float(a[1]) / float(1 / float(huobi_value)))
                        for b in bids1:
                            b[1] = float(float(b[1]) / float(1 / float(huobi_value)))
                    if m1 == 'Okx':
                        for a in asks1:
                            a[1] = float(float(okx_value) * float(a[1]))
                        for b in bids1:
                            b[1] = float(float(okx_value) * float(b[1]))
                    if m1 == 'Kucoin':
                        for a in asks1:
                            a[1] = float(float(a[1]) / float(1 / float(kucoin_value)))
                        for b in bids1:
                            b[1] = float(float(b[1]) / float(1 / float(kucoin_value)))
                    if m1 == 'BitMart':
                        for a in asks1:
                            a[1] = float(float(a[1]) / float(1 / float(bitmart_value)))
                        for b in bids1:
                            b[1] = float(float(b[1]) / float(1 / float(bitmart_value)))
                    if m1 == 'Poloniex':
                        for a in asks1:
                            a[1] = float(float(a[1]) / float(1 / float(poloniex_value)))
                        for b in bids1:
                            b[1] = float(float(b[1]) / float(1 / float(poloniex_value)))
                    if m1 == 'Ourbit':
                        for a in asks1:
                            a[1] = float(float(a[1]) / float(1 / float(10)))
                        for b in bids1:
                            b[1] = float(float(b[1]) / float(1 / float(10)))
                except Exception as e:
                    logger.exception('err in market1 amounts')

                try:
                    if m2 == 'Gateio':
                        for a in asks2:
                            a['s'] = float(float(a['s']) / float(1 / float(gateio_value)))
                        for b in bids2:
                            b['s'] = float(float(b['s']) / float(1 / float(gateio_value)))
                    if m2 == 'Huobi':
                        for a in asks2:
                            a[1] = float(float(a[1]) / float(1 / float(huobi_value)))
                        for b in bids2:
                            b[1] = float(float(b[1]) / float(1 / float(huobi_value)))
                    if m2 == 'Okx':
                        for a in asks2:
                            a[1] = float(float(okx_value) * float(a[1]))
                        for b in bids2:
                            b[1] = float(float(okx_value) * float(b[1]))
                    if m2 == 'Kucoin':
                        for a in asks2:
                            a[1] = float(float(a[1]) / float(1 / float(kucoin_value)))
                        for b in bids2:
                            b[1] = float(float(b[1]) / float(1 / float(kucoin_value)))
                    if m2 == 'BitMart':
                        for a in asks2:
                            a[1] = float(float(a[1]) / float(1 / float(bitmart_value)))
                        for b in bids2:
                            b[1] = float(float(b[1]) / float(1 / float(bitmart_value)))
                    if m2 == 'Poloniex':
                        for a in asks2:
                            a[1] = float(float(a[1]) / float(1 / float(poloniex_value)))
                        for b in bids2:
                            b[1] = float(float(b[1]) / float(1 / float(poloniex_value)))
                    if m2 == 'Ourbit':
                        for a in asks2:
                            a[1] = float(float(a[1]) / float(1 / float(10)))
                        for b in bids2:
                            b[1] = float(float(b[1]) / float(1 / float(10)))
                except Exception as e:
                    logger.exception('err in market2 amounts')

                counter = 0
                try:
                    if m1 == 'Gateio' and m2 == 'Gateio':

                        for a in asks1:
                            send_asks1.append([float(a['p']), int(float(a['p']) * float(a['s']))])
                        for a in asks2:
                            send_asks2.append([float(a['p']), int(float(a['p']) * float(a['s']))])
                        for b in bids1:
                            send_bids1.append([float(b['p']), int(float(b['p']) * float(b['s']))])
                        for b in bids2:
                            send_bids2.append([float(b['p']), int(float(b['p']) * float(b['s']))])
                    elif m1 == 'Gateio':
                        for a in asks1:
                            send_asks1.append([float(a['p']), int(float(a['p']) * float(a['s']))])
                        for a in asks2:
                            if m2 == 'Mexc':
                                send_asks2.append(
                                    [float(a[0]), int(float(a[0]) * float(
                                        float(a[1]) / float(1 / float(mexc_value))))])
                            else:
                                send_asks2.append([float(a[0]), int(float(a[0]) * float(a[1]))])
                        for b in bids1:
                            send_bids1.append([float(b['p']), int(float(b['p']) * float(b['s']))])
                        for b in bids2:
                            if m2 == 'Mexc':
                                send_bids2.append(
                                    [float(b[0]), int(float(b[0]) * float(
                                        float(b[1]) / float(1 / float(mexc_value))))])
                            else:
                                send_bids2.append([float(b[0]), int(float(b[0]) * float(b[1]))])
                    elif m2 == 'Gateio':
                        for a in asks1:
                            if m1 == 'Mexc':
                                send_asks1.append(
                                    [float(a[0]), int(float(a[0]) * float(
                                        float(a[1]) / float(1 / float(mexc_value))))])
                            else:
                                send_asks1.append([float(a[0]), int(float(a[0]) * float(a[1]))])
                        for a in asks2:
                            send_asks2.append([float(a['p']), int(float(a['p']) * float(a['s']))])
                        for b in bids1:
                            if m1 == 'Mexc':
                                send_bids1.append(
                                    [float(b[0]), int(float(b[0]) * float(
                                        float(b[1]) / float(1 / float(mexc_value))))])
                            else:
                                send_bids1.append([float(b[0]), int(float(b[0]) * float(b[1]))])
                        for b in bids2:
                            send_bids2.append([float(b['p']), int(float(b['p']) * float(b['s']))])
                    else:
                        for a in asks1:
                            if m1 == 'Mexc':
                                send_asks1.append([float(a[0]), int(float(a[0]) * float(
                                    float(a[1]) / float(1 / float(mexc_value))))])
                            else:
                                send_asks1.append([float(a[0]), int(float(a[0]) * float(a[1]))])
                        for a in asks2:
                            if m2 == 'Mexc':
                                send_asks2.append([float(a[0]), int(float(a[0]) * float(
                                    float(a[1]) / float(1 / float(mexc_value))))])
                            else:
                                send_asks2.append([float(a[0]), int(float(a[0]) * float(a[1]))])
                        for b in bids1:
                            if m1 == 'Mexc':
                                send_bids1.append([float(b[0]), int(float(b[0]) * float(
                                    float(b[1]) / float(1 / float(mexc_value))))])
                            else:
                                send_bids1.append([float(b[0]), int(float(b[0]) * float(b[1]))])
                        for b in bids2:
                            if m2 == 'Mexc':
                                send_bids2.append([float(b[0]), int(float(b[0]) * float(
                                    float(b[1]) / float(1 / float(mexc_value))))])
                            else:
                                send_bids2.append([float(b[0]), int(float(b[0]) * float(b[1]))])
                except Exception as e:
                    print(e)
                    logger.exception('Except')

                spread_in = round(((float(best_bids2) / float(best_asks1)) - 1) * 100, 2)
                spread_out = round(((float(best_asks2) / float(best_bids1)) - 1) * 100, 2)

                send_data = {
                        "m1": m1,
                        "m2": m2,
                        "post_coin": post_coin,
                        "in": spread_in,
                        "out": spread_out,
                        "asks1": send_asks1,
                        "bids1": send_bids1,
                        "asks2": send_asks2,
                        "bids2": send_bids2,
                        "sp_or_ft": sp_or_ft,
                        "time": f"{datetime.datetime.now().minute}:{datetime.datetime.now().second}",
                        "current_time": f"{datetime.datetime.timestamp(datetime.datetime.now())}",
                    }

                socket_thread = threading.Thread(target=send_data_to_unix_socket, args=(send_data,))
                socket_thread.daemon = True
                socket_thread.start()

            else:
                send_data = {
                    "m1": m1,
                    "m2": m2,
                    "post_coin": post_coin,
                    "in": 'Error',
                    "out": 'Error',
                    "asks1": [[0]],
                    "bids1": [[0]],
                    "asks2": [[0]],
                    "bids2": [[0]],
                    "sp_or_ft": sp_or_ft,
                    "time": f"{datetime.datetime.now().minute}:{datetime.datetime.now().second}",
                    "current_time": f"{datetime.datetime.timestamp(datetime.datetime.now())}",
                }

                socket_thread = threading.Thread(target=send_data_to_unix_socket, args=(send_data,))
                socket_thread.daemon = True
                socket_thread.start()

        except Exception as e:
            logger.exception('futures')

    elif sp_or_ft == 'spot':
        try:
            if len(post_coin) < 20 and m1 in markets_list and m2 in markets_list:

                if m1 == 'Kucoin' and token_kucoin != '':
                    if post_coin in spot_open_sockets_kucoin.keys():
                        if spot_open_sockets_kucoin[post_coin][2] != 1:
                            spot_open_sockets_kucoin[post_coin][1] = datetime.datetime.now()
                    if post_coin not in spot_open_sockets_kucoin.keys():
                        print('start:', m1, post_coin, sp_or_ft)
                        asyncio.create_task(run_socket(m1, post_coin, sp_or_ft))

                if m2 == 'Kucoin' and token_kucoin != '':
                    if post_coin in open_sockets_kucoin.keys():
                        if open_sockets_kucoin[post_coin][2] != 1:
                            open_sockets_kucoin[post_coin][1] = datetime.datetime.now()
                    if post_coin not in open_sockets_kucoin.keys():
                        print('start:', m2, post_coin, 'futures')
                        asyncio.create_task(run_socket(m2, post_coin, 'futures'))

                if (m1 == 'Okx') or (m2 == 'Okx'):
                    if m1 == 'Okx':
                        asyncio.create_task(start_sock(m1, post_coin, spot_open_sockets_okx, sp_or_ft))
                    if m2 == 'Okx':
                        asyncio.create_task(start_sock(m2, post_coin, open_sockets_okx, 'futures'))

                if (m1 == 'Bybit') or (m2 == 'Bybit'):
                    if m1 == 'Bybit':
                        asyncio.create_task(start_sock(m1, post_coin, spot_open_sockets_bybit, sp_or_ft))
                    if m2 == 'Bybit':
                        asyncio.create_task(start_sock(m2, post_coin, open_sockets_bybit, 'futures'))

                if (m1 == 'Mexc') or (m2 == 'Mexc'):
                    if m1 == 'Mexc':
                        asyncio.create_task(start_sock(m1, post_coin, spot_open_sockets_mexc, sp_or_ft))
                    if m2 == 'Mexc':
                        asyncio.create_task(start_sock(m2, post_coin, open_sockets_mexc, 'futures'))

                if (m1 == 'Gateio') or (m2 == 'Gateio'):
                    if m1 == 'Gateio':
                        asyncio.create_task(start_sock(m1, post_coin, spot_open_sockets_gateio, sp_or_ft))
                    if m2 == 'Gateio':
                        asyncio.create_task(start_sock(m2, post_coin, open_sockets_gateio, 'futures'))

                if (m1 == 'Bitget') or (m2 == 'Bitget'):
                    if m1 == 'Bitget':
                        asyncio.create_task(start_sock(m1, post_coin, spot_open_sockets_bitget, sp_or_ft))
                    if m2 == 'Bitget':
                        asyncio.create_task(start_sock(m2, post_coin, open_sockets_bitget, 'futures'))

                if (m1 == 'Huobi') or (m2 == 'Huobi'):
                    if m1 == 'Huobi':
                        asyncio.create_task(start_sock(m1, post_coin, spot_open_sockets_huobi, sp_or_ft))
                    if m2 == 'Huobi':
                        asyncio.create_task(start_sock(m2, post_coin, open_sockets_huobi, 'futures'))

                if (m1 == 'Binance') or (m2 == 'Binance'):
                    if m1 == 'Binance':
                        asyncio.create_task(start_sock(m1, post_coin, spot_open_sockets_binance, sp_or_ft))
                    if m2 == 'Binance':
                        asyncio.create_task(start_sock(m2, post_coin, open_sockets_binance, 'futures'))

                if (m1 == 'BingX') or (m2 == 'BingX'):
                    if m1 == 'BingX':
                        asyncio.create_task(start_sock(m1, post_coin, spot_open_sockets_bingx, sp_or_ft))
                    if m2 == 'BingX':
                        asyncio.create_task(start_sock(m2, post_coin, open_sockets_bingx, 'futures'))

                if (m1 == 'BitMart') or (m2 == 'BitMart'):
                    if m1 == 'BitMart':
                        asyncio.create_task(start_sock(m1, post_coin, spot_open_sockets_bitmart, sp_or_ft))
                    if m2 == 'BitMart':
                        asyncio.create_task(start_sock(m2, post_coin, open_sockets_bitmart, 'futures'))

                if (m1 == 'Poloniex') or (m2 == 'Poloniex'):
                    if m1 == 'Poloniex':
                        asyncio.create_task(start_sock(m1, post_coin, spot_open_sockets_poloniex, sp_or_ft))
                    if m2 == 'Poloniex':
                        asyncio.create_task(start_sock(m2, post_coin, open_sockets_poloniex, 'futures'))

                if (m1 == 'CoinEx') or (m2 == 'CoinEx'):
                    if m1 == 'CoinEx':
                        asyncio.create_task(start_sock(m1, post_coin, spot_open_sockets_coinex, sp_or_ft))
                    if m2 == 'CoinEx':
                        asyncio.create_task(start_sock(m2, post_coin, open_sockets_coinex, 'futures'))

                if (m1 == 'Ourbit') or (m2 == 'Ourbit'):
                    if m1 == 'Ourbit':
                        asyncio.create_task(start_sock(m1, post_coin, spot_open_sockets_ourbit, sp_or_ft))
                    if m2 == 'Ourbit':
                        asyncio.create_task(start_sock(m2, post_coin, open_sockets_ourbit, 'futures'))

                if (m1 == 'LBank') or (m2 == 'LBank'):
                    if m1 == 'LBank':
                        asyncio.create_task(start_sock(m1, post_coin, spot_open_sockets_lbank, sp_or_ft))
                    if m2 == 'LBank':
                        asyncio.create_task(start_sock(m2, post_coin, open_sockets_lbank, 'futures'))

                if m2 == 'Hyperliquid':
                    asyncio.create_task(start_sock(m2, post_coin, open_sockets_hyperliquid, 'futures'))



                asks1 = None
                bids1 = None
                asks2 = None
                bids2 = None
                try:
                    if (m1 == 'Okx'):
                        asks1 = copy.deepcopy(okx_spot_data[post_coin]['asks'])
                        bids1 = copy.deepcopy(okx_spot_data[post_coin]['bids'])
                    elif m1 == 'Kucoin':
                        asks1 = copy.deepcopy(kucoin_spot_data[post_coin]['asks'])
                        bids1 = copy.deepcopy(kucoin_spot_data[post_coin]['bids'])
                    elif m1 == 'Bybit':
                        asks1 = copy.deepcopy(bybit_spot_data[post_coin]['asks'])
                        bids1 = copy.deepcopy(bybit_spot_data[post_coin]['bids'])
                    elif m1 == 'Mexc':
                        asks1 = copy.deepcopy(mexc_spot_data[post_coin]['asks'])
                        bids1 = copy.deepcopy(mexc_spot_data[post_coin]['bids'])
                    elif m1 == 'Gateio':
                        asks1 = copy.deepcopy(gateio_spot_data[post_coin]['asks'])
                        bids1 = copy.deepcopy(gateio_spot_data[post_coin]['bids'])
                    elif m1 == 'Bitget':
                        asks1 = copy.deepcopy(bitget_spot_data[post_coin]['asks'])
                        bids1 = copy.deepcopy(bitget_spot_data[post_coin]['bids'])
                    elif m1 == 'Huobi':
                        asks1 = copy.deepcopy(huobi_spot_data[post_coin]['asks'])
                        bids1 = copy.deepcopy(huobi_spot_data[post_coin]['bids'])
                    elif m1 == 'Binance':
                        asks1 = copy.deepcopy(binance_spot_data[post_coin]['asks'])
                        bids1 = copy.deepcopy(binance_spot_data[post_coin]['bids'])
                    elif m1 == 'BingX':
                        asks1 = copy.deepcopy(bingx_spot_data[post_coin]['asks'])
                        bids1 = copy.deepcopy(bingx_spot_data[post_coin]['bids'])
                    elif m1 == 'BitMart':
                        asks1 = copy.deepcopy(bitmart_spot_data[post_coin]['asks'])
                        bids1 = copy.deepcopy(bitmart_spot_data[post_coin]['bids'])
                    elif m1 == 'Poloniex':
                        asks1 = copy.deepcopy(poloniex_spot_data[post_coin]['asks'])
                        bids1 = copy.deepcopy(poloniex_spot_data[post_coin]['bids'])
                    elif m1 == 'CoinEx':
                        asks1 = copy.deepcopy(coinex_spot_data[post_coin]['asks'])
                        bids1 = copy.deepcopy(coinex_spot_data[post_coin]['bids'])
                    elif m1 == 'Ourbit':
                        asks1 = copy.deepcopy(ourbit_spot_data[post_coin]['asks'])
                        bids1 = copy.deepcopy(ourbit_spot_data[post_coin]['bids'])
                    elif m1 == 'LBank':
                        asks1 = copy.deepcopy(lbank_spot_data[post_coin]['asks'])
                        bids1 = copy.deepcopy(lbank_spot_data[post_coin]['bids'])

                    if (m2 == 'Okx'):
                        asks2 = copy.deepcopy(okx_futures_data[post_coin]['asks'])
                        bids2 = copy.deepcopy(okx_futures_data[post_coin]['bids'])
                    elif m2 == 'Kucoin':
                        asks2 = copy.deepcopy(kucoin_futures_data[post_coin]['asks'])
                        bids2 = copy.deepcopy(kucoin_futures_data[post_coin]['bids'])
                    elif m2 == 'Bybit':
                        asks2 = copy.deepcopy(bybit_futures_data[post_coin]['asks'])
                        bids2 = copy.deepcopy(bybit_futures_data[post_coin]['bids'])
                    elif m2 == 'Mexc':
                        asks2 = copy.deepcopy(mexc_futures_data[post_coin]['asks'])
                        bids2 = copy.deepcopy(mexc_futures_data[post_coin]['bids'])
                    elif m2 == 'Gateio':
                        asks2 = copy.deepcopy(gateio_futures_data[post_coin]['asks'])
                        bids2 = copy.deepcopy(gateio_futures_data[post_coin]['bids'])
                    elif m2 == 'Bitget':
                        asks2 = copy.deepcopy(bitget_futures_data[post_coin]['asks'])
                        bids2 = copy.deepcopy(bitget_futures_data[post_coin]['bids'])
                    elif m2 == 'Huobi':
                        asks2 = copy.deepcopy(huobi_futures_data[post_coin]['asks'])
                        bids2 = copy.deepcopy(huobi_futures_data[post_coin]['bids'])
                    elif m2 == 'Binance':
                        asks2 = copy.deepcopy(binance_futures_data[post_coin]['asks'])
                        bids2 = copy.deepcopy(binance_futures_data[post_coin]['bids'])
                    elif m2 == 'BingX':
                        asks2 = copy.deepcopy(bingx_futures_data[post_coin]['asks'])
                        bids2 = copy.deepcopy(bingx_futures_data[post_coin]['bids'])
                    elif m2 == 'BitMart':
                        asks2 = copy.deepcopy(bitmart_futures_data[post_coin]['asks'])
                        bids2 = copy.deepcopy(bitmart_futures_data[post_coin]['bids'])
                    elif m2 == 'Poloniex':
                        asks2 = copy.deepcopy(poloniex_futures_data[post_coin]['asks'])
                        bids2 = copy.deepcopy(poloniex_futures_data[post_coin]['bids'])
                    elif m2 == 'CoinEx':
                        asks2 = copy.deepcopy(coinex_futures_data[post_coin]['asks'])
                        bids2 = copy.deepcopy(coinex_futures_data[post_coin]['bids'])
                    elif m2 == 'Ourbit':
                        asks2 = copy.deepcopy(ourbit_futures_data[post_coin]['asks'])
                        bids2 = copy.deepcopy(ourbit_futures_data[post_coin]['bids'])
                    elif m2 == 'Hyperliquid':
                        asks2 = copy.deepcopy(hyperliquid_futures_data[post_coin]['asks'])
                        bids2 = copy.deepcopy(hyperliquid_futures_data[post_coin]['bids'])
                    elif m2 == 'LBank':
                        asks2 = copy.deepcopy(lbank_futures_data[post_coin]['asks'])
                        bids2 = copy.deepcopy(lbank_futures_data[post_coin]['bids'])

                except KeyError:
                    send_data = {
                        "m1": m1,
                        "m2": m2,
                        "post_coin": post_coin,
                        "in": 'wait',
                        "out": 'wait',
                        "asks1": [[0]],
                        "bids1": [[0]],
                        "asks2": [[0]],
                        "bids2": [[0]],
                        "sp_or_ft": sp_or_ft,
                        "time": f"{datetime.datetime.now().minute}:{datetime.datetime.now().second}",
                        "current_time": f"{datetime.datetime.timestamp(datetime.datetime.now())}",
                    }
                    socket_thread = threading.Thread(target=send_data_to_unix_socket, args=(send_data,))
                    socket_thread.daemon = True
                    socket_thread.start()

                if m1 not in ('Mexc', 'Ourbit'):
                    if asks1 is not None and bids1 is not None:
                        best_asks1 = asks1[0][0]
                        best_bids1 = bids1[0][0]
                else:
                    if asks1 is not None and bids1 is not None:
                        best_asks1 = asks1[0]['p']
                        best_bids1 = bids1[0]['p']
                if m2 != 'Gateio':
                    if asks2 is not None and bids2 is not None:
                        best_asks2 = asks2[0][0]
                        best_bids2 = bids2[0][0]
                else:
                    if asks2 is not None and bids2 is not None:
                        best_asks2 = asks2[0]['p']
                        best_bids2 = bids2[0]['p']

                send_asks1 = []
                send_bids1 = []
                send_asks2 = []
                send_bids2 = []

                # --------------------------------------------------------------------------------------------------

                if asks1 is not None and asks2 is not None and bids1 is not None and bids2 is not None:
                    try:
                        if m2 == 'Gateio':
                            for a in asks2:
                                a['s'] = float(float(a['s']) / float(1 / float(gateio_value)))
                            for b in bids2:
                                b['s'] = float(float(b['s']) / float(1 / float(gateio_value)))
                        if m2 == 'Huobi':
                            for a in asks2:
                                a[1] = float(float(a[1]) / float(1 / float(huobi_value)))
                            for b in bids2:
                                b[1] = float(float(b[1]) / float(1 / float(huobi_value)))
                        if m2 == 'Okx':
                            for a in asks2:
                                a[1] = float(float(okx_value) * float(a[1]))
                            for b in bids2:
                                b[1] = float(float(okx_value) * float(b[1]))
                        if m2 == 'Kucoin':
                            for a in asks2:
                                a[1] = float(float(a[1]) / float(1 / float(kucoin_value)))
                            for b in bids2:
                                b[1] = float(float(b[1]) / float(1 / float(kucoin_value)))
                        if m2 == 'BitMart':
                            for a in asks2:
                                a[1] = float(float(a[1]) / float(1 / float(bitmart_value)))
                            for b in bids2:
                                b[1] = float(float(b[1]) / float(1 / float(bitmart_value)))
                        if m2 == 'Poloniex':
                            for a in asks2:
                                a[1] = float(float(a[1]) / float(1 / float(poloniex_value)))
                            for b in bids2:
                                b[1] = float(float(b[1]) / float(1 / float(poloniex_value)))
                    except Exception as e:
                        print('err market2 in amounts: ', e)

                    # -----------------------------------------------------------------------------------

                    counter = 0
                    try:
                        if m2 == 'Gateio':
                            for a in asks1:
                                if m1 in ('Mexc', 'Ourbit'):
                                    send_asks1.append(
                                        [a['p'], int(float(a['p']) * float(
                                            float(a['v'])))])
                                else:
                                    send_asks1.append([float(a[0]), int(float(a[0]) * float(a[1]))])
                            for a in asks2:
                                send_asks2.append([a['p'], int(float(a['p']) * float(a['s']))])
                            for b in bids1:
                                if m1 in ('Mexc', 'Ourbit'):
                                    send_bids1.append(
                                        [b['p'], int(float(b['p']) * float(
                                            float(b['v'])))])
                                else:
                                    send_bids1.append([float(b[0]), int(float(b[0]) * float(b[1]))])
                            for b in bids2:
                                send_bids2.append([b['p'], int(float(b['p']) * float(b['s']))])
                        else:
                            for a in asks1:
                                if m1 in ('Mexc', 'Ourbit'):
                                    send_asks1.append([a['p'], int(float(a['p']) * float(
                                        float(a['v'])))])
                                else:
                                    send_asks1.append([float(a[0]), int(float(a[0]) * float(a[1]))])
                            for a in asks2:
                                if m2 == 'Mexc':
                                    send_asks2.append([a[0], int(float(a[0]) * float(
                                        float(a[1]) / float(1 / float(mexc_value))))])
                                else:
                                    send_asks2.append([float(a[0]), int(float(a[0]) * float(a[1]))])
                            for b in bids1:
                                if m1 in ('Mexc', 'Ourbit'):
                                    send_bids1.append([b['p'], int(float(b['p']) * float(
                                        float(b['v'])))])
                                else:
                                    send_bids1.append([float(b[0]), int(float(b[0]) * float(b[1]))])
                            for b in bids2:
                                if m2 == 'Mexc':
                                    send_bids2.append([b[0], int(float(b[0]) * float(
                                        float(b[1]) / float(1 / float(mexc_value))))])
                                else:
                                    send_bids2.append([float(b[0]), int(float(b[0]) * float(b[1]))])
                    except Exception as e:
                        print(e)
                        logger.exception('Except')

                    spread_in = round(((float(best_bids2) / float(best_asks1)) - 1) * 100, 2)
                    spread_out = round(((float(best_asks2) / float(best_bids1)) - 1) * 100, 2)

                    send_data = {
                        "m1": m1,
                        "m2": m2,
                        "post_coin": post_coin,
                        "in": spread_in,
                        "out": spread_out,
                        "asks1": send_asks1,
                        "bids1": send_bids1,
                        "asks2": send_asks2,
                        "bids2": send_bids2,
                        "sp_or_ft": sp_or_ft,
                        "time": f"{datetime.datetime.now().minute}:{datetime.datetime.now().second}",
                        "current_time": f"{datetime.datetime.timestamp(datetime.datetime.now())}",
                    }
                    socket_thread = threading.Thread(target=send_data_to_unix_socket, args=(send_data,))
                    socket_thread.daemon = True
                    socket_thread.start()

                else:
                    send_data = {
                        "m1": m1,
                        "m2": m2,
                        "post_coin": post_coin,
                        "in": 'Error',
                        "out": 'Error',
                        "asks1": [[0]],
                        "bids1": [[0]],
                        "asks2": [[0]],
                        "bids2": [[0]],
                        "sp_or_ft": sp_or_ft,
                        "time": f"{datetime.datetime.now().minute}:{datetime.datetime.now().second}",
                        "current_time": f"{datetime.datetime.timestamp(datetime.datetime.now())}",
                    }
                    socket_thread = threading.Thread(target=send_data_to_unix_socket, args=(send_data,))
                    socket_thread.daemon = True
                    socket_thread.start()
        except Exception as e:
            print('spot', e)
            logger.exception('spot!')


SOCKET_PATH = './from'

last_calls = {}


async def handle_client(reader, writer):
    try:
        data = await reader.read(8192)
        message = data.decode()
        nested_list = json.loads(message)

        key = (nested_list.get('m1'), nested_list.get('m2'), nested_list.get('post_coin'), nested_list.get('sp_or_ft'))
        now = time.time()

        if last_calls.get(key) and now - last_calls[key] < 0.09:
            writer.close()
            await writer.wait_closed()
            return

        last_calls[key] = now
        await check_data(*key)
        writer.close()
        await writer.wait_closed()

    except Exception as e:
        print("Exception in handle_client:", e)


async def get_data_from_django_async():
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    server = await asyncio.start_unix_server(handle_client, path=SOCKET_PATH)
    print("UNIX socket server started...")

    async with server:
        await server.serve_forever()


def send_data_to_unix_socket(data):
    try:
        unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        unix_socket.connect('./data')

        # Отправляем данные через Unix-сокет
        unix_socket.send(json.dumps(data).encode('utf-8'))
        unix_socket.close()
    except Exception:
        print('error send to data')


async def monitor_socket_expiry():
    while True:
        await asyncio.sleep(5)

        await check_to_close_socket(open_sockets_kucoin, kucoin_futures_data)
        await check_to_close_socket(open_sockets_okx, okx_futures_data)
        await check_to_close_socket(open_sockets_bybit, bybit_futures_data)
        await check_to_close_socket(open_sockets_mexc, mexc_futures_data)
        await check_to_close_socket(open_sockets_gateio, gateio_futures_data)
        await check_to_close_socket(open_sockets_bitget, bitget_futures_data)
        await check_to_close_socket(open_sockets_huobi, huobi_futures_data)
        await check_to_close_socket(open_sockets_binance, binance_futures_data)
        await check_to_close_socket(open_sockets_bingx, bingx_futures_data)
        await check_to_close_socket(open_sockets_bitmart, bitmart_futures_data)
        await check_to_close_socket(open_sockets_poloniex, poloniex_futures_data)
        await check_to_close_socket(open_sockets_coinex, coinex_futures_data)
        await check_to_close_socket(open_sockets_ourbit, ourbit_futures_data)
        await check_to_close_socket(open_sockets_hyperliquid, hyperliquid_futures_data)
        await check_to_close_socket(open_sockets_lbank, lbank_futures_data)

        await check_to_close_socket(spot_open_sockets_kucoin, kucoin_spot_data)
        await check_to_close_socket(spot_open_sockets_okx, okx_spot_data)
        await check_to_close_socket(spot_open_sockets_bybit, bybit_spot_data)
        await check_to_close_socket(spot_open_sockets_mexc, mexc_spot_data)
        await check_to_close_socket(spot_open_sockets_gateio, gateio_spot_data)
        await check_to_close_socket(spot_open_sockets_bitget, bitget_spot_data)
        await check_to_close_socket(spot_open_sockets_huobi, huobi_spot_data)
        await check_to_close_socket(spot_open_sockets_binance, binance_spot_data)
        await check_to_close_socket(spot_open_sockets_bingx, bingx_spot_data)
        await check_to_close_socket(spot_open_sockets_bitmart, bitmart_spot_data)
        await check_to_close_socket(spot_open_sockets_poloniex, poloniex_spot_data)
        await check_to_close_socket(spot_open_sockets_coinex, coinex_spot_data)
        await check_to_close_socket(spot_open_sockets_ourbit, ourbit_spot_data)
        await check_to_close_socket(spot_open_sockets_lbank, lbank_spot_data)


async def main():
    print('Start')

    # Фоновый перезапускаемый таск
    async def run_with_restart(coro_func, name="task"):
        while True:
            try:
                print(f"[{name}] Starting")
                await coro_func()
            except Exception as e:
                print(f"[{name}] Crashed: {e}")
                await asyncio.sleep(5)  # Подождать перед перезапуском

    # Запуск перезапускаемого таска
    asyncio.create_task(run_with_restart(reload_multiplicators_data, name="Multiplicators"))

    # Запускаем Unix-сокет сервер асинхронно
    asyncio.create_task(get_data_from_django_async())

    # Запускаем мониторинг как фоновую задачу
    asyncio.create_task(monitor_socket_expiry())

    # запускаем обновление токена кукоина
    asyncio.create_task(check_token_kucoin())

    while True:
        await asyncio.sleep(0.01)

if __name__ == '__main__':
    asyncio.run(main())
