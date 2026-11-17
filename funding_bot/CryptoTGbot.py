import datetime
import asyncio
import aiogram.exceptions
import aiohttp
import sqlite3
import json
import os
import sys
import re
from pybit.unified_trading import HTTP
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardRemove, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardMarkup, InlineKeyboardMarkup
from routers import router as main_router
from routers.page_markets import get_markets_callback, show_futures_page, add_page_from_pagination
from routers.spot_page_markets import get_spot_markets_callback, show_spot_page
from routers.dex_page_markets import show_dex_page, handler_dex_market
from libs.tgfunc import *
import pickle
import threading
import mysql.connector
import zlib
import logging
import orjson
from copy import copy
import redis.asyncio as aioredis
import uuid
from typing import Any, Dict, Tuple, Callable, Optional, List
from collections import defaultdict
from aiogram.client.session.aiohttp import AiohttpSession

logger = logging.getLogger("CryptoTGbot")
logging.basicConfig(level=logging.INFO)

DEBUG = os.getenv('DEBUG', 'False') == 'True'

REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = os.getenv('REDIS_PORT', '6379')

MYSQL_ROOT_PASSWORD = os.getenv('MYSQL_ROOT_PASSWORD', '')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'funding')
MYSQL_USER = os.getenv('MYSQL_USER', 'username')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'password')
DB_HOST = os.getenv('DB_HOST', 'mysql')
DB_PORT = os.getenv('DB_PORT', '3306')

FILTER_HOST = os.getenv('FILTER_HOST', 'localhost')
GO_BASE = f"http://{FILTER_HOST}:8081"

# Константы
REDIS_ADDR = f"redis://{REDIS_HOST}:{REDIS_PORT}"
NOTIF_KEYS = [
    {"db": 0, "key": "Notifications:Spreads", "type": "spread"},
    {"db": 1, "key": "Notifications:SpotFutures", "type": "spot"},
    {"db": 2, "key": "Notifications:Dex", "type": "dex"},
]
# интервал ожидания при неудачном RENAME (мелкий бэофф)
RENAME_BACKOFF = 0.05

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

dp = Dispatcher()
dp.include_router(main_router)
bot = None

sessionBybit = HTTP(testnet=False)
bids_asks_futures = []
bids_asks_spot = {}

DEDUP_TTL = 3 * 60 * 60  # 4 часа
MAX_DEDUP_PER_USER = 4000  # предел на количество ключей на пользователя

_dedupe_lock = asyncio.Lock()
_dedupe_map: dict[str, dict[str, float]] = defaultdict(dict)

_scan_trigger_q = None
_scan_worker_task = None

ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

async def fetch_go_futures(user_id: int, page: int = 1, items: int = 5, sort: str = "spread", lt: int = 0, timeout=5):
    params = {
        "user_id": str(user_id),
        "page": str(page),
        "items": str(items),
        "sort": sort,
        "lt": str(lt),
    }
    url = f"{GO_BASE}/api/futures"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.json()

# helper (вставь рядом с другими helper'ами)
async def fetch_go_spot(user_id: int, page: int = 1, items: int = 5, sort: str = "spread", lt: int = 0, timeout=5):
    """
    Запрос к /api/spot
    Возвращает JSON-ответ от сервера Go (status, pages, current_page, total_pages и т.д.)
    """
    params = {
        "user_id": str(user_id),
        "page": str(page),
        "items": str(items),
        "sort": sort,
        "lt": str(lt),
    }
    url = f"{GO_BASE}/api/spot"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.json()

def _extract_user_filters_from_accounts(accounts, user_id):
    """
    Возвращает (active: bool, dataSearch: dict)
    dataSearch — разобранный JSON (если есть), иначе {}.
    """
    for acc in accounts:
        # acc[2] — user_id (как в твоём коде)
        if str(acc[2]) == str(user_id) and any(x == '1' for x in [acc[9], acc[10], acc[14]]):
            # активный
            dataSearch_raw = acc[4] if acc[4] is not None else 'no'
            try:
                if dataSearch_raw == 'no':
                    dataSearch = {}
                else:
                    # acc[4] может быть bytes или string
                    if isinstance(dataSearch_raw, (bytes, bytearray)):
                        dataSearch = orjson.loads(dataSearch_raw)
                    else:
                        dataSearch = orjson.loads(dataSearch_raw)
            except Exception:
                dataSearch = {}
            return True, dataSearch
    return False, {}

def _map_dataSearch_to_service_params(dataSearch):
    """
    Преобразует dataSearch → sort, lt (по умолчанию spread, lt=0).
    Если нужно — скорректируй эту функцию под реальные поля dataSearch.
    Правило, которое я использовал:
      - sort = 'course'  если dataSearch['filter_course_or_spread'] == '1'
      - иначе sort = 'spread'
      - lt = 0 если пользователь включил фильтр "Вход > 0"
        (в твоём фронте этот флаг хранится в entryPositiveState; в dataSearch может быть другое поле —
         если у тебя другое имя, замени проверку).
    """
    sort = "spread"
    lt = 0

    # sort mapping
    if dataSearch.get("filter_course_or_spread") == "1":
        sort = "spread"
    else:
        sort = "funding"

    # lt mapping — здесь я предполагаю флаг entryPositive в dataSearch['entry_positive'] (замени по необходимости).
    # Если у тебя нет такого поля, оставим lt=0 (как в примере).
    if dataSearch.get("filter_big_or_all_course") == "1":
        lt = 1
    else:
        # если нужно — передавать другой lt (например пустую строку), но сервис в примере ожидает 0
        lt = 0

    return sort, lt

def build_inline_from_service_page(builder: InlineKeyboardBuilder, page_obj):
    """
    page_obj: dict with keys 'page' and 'items' (items is list of [text, symbol])
    Заполняет builder кнопками-рынками.
    """
    for item in page_obj.get("items", []):
        text = item[0]
        symbol = item[1]
        # callback_data — оставляем прежний формат 'market:SYMBOL'
        builder.row(InlineKeyboardButton(text=text, callback_data=f"market:{symbol}"))


@dp.message(F.text == 'Фьючерсы 🔄')
async def get_spreads(message: types.Message):
    user_id = message.from_user.id
    print(f"{user_id} - {message.from_user.username} - Spreads")

    # получаем аккаунты как раньше
    accounts = fetch_accounts_from_db()

    active, dataSearch = _extract_user_filters_from_accounts(accounts, user_id)

    if not active:
        await message.answer(text='Ваша подписка неактивна')
        return

    # определяем параметры для Go-сервиса
    sort, lt = _map_dataSearch_to_service_params(dataSearch)

    try:
        resp = await fetch_go_futures(user_id=user_id, page=1, items=5, sort=sort, lt=lt)
    except Exception as e:
        # ошибка обращения к сервису
        await message.answer(text="Ошибка получения данных от сервиса. Повторите позже.")
        print("fetch_go_futures error:", e)
        return

    # статус обработки (совпадает с твоим API)
    if resp.get("status") in ("no_sub", "inactive"):
        await message.answer(text='Ваша подписка неактивна')
        return

    pages = resp.get("pages", [])
    if not pages or len(pages) == 0:
        await message.answer(text='Нет данных для отображения.')
        return

    # Построим клавиатуру для первой страницы (pages[0])
    inline_kb1 = InlineKeyboardBuilder()
    build_inline_from_service_page(inline_kb1, pages[0])

    # Пагинация (можно использовать create_pagination_buttons если есть — я добавил свою функцию)
    # если это глобальная таблица "фьючерсы" — использовать page_from style:
    current_page = int(resp.get("current_page") or 1)
    total_pages = int(resp.get("total_pages") or 1)
    add_page_from_pagination(inline_kb1, current_page=current_page, total_pages=total_pages, cb_prefix="page_from")

    # добавляем фильтры кнопки слева/справа
    add_filter_buttons_futures(inline_kb1, dataSearch)

    await message.answer(text='Список фьючерс/фьючерс', reply_markup=inline_kb1.as_markup())


def fetch_combined_spot_data(futures_exchange, futures_symbol, spot_exchange, spot_symbol):
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE
    )
    cursor = connection.cursor(dictionary=True)

    query = """
        SELECT 
            f.datetime AS futures_time,
            f.ask AS futures_ask,
            f.bid AS futures_bid,
            s.datetime AS spot_time,
            s.ask AS spot_ask,
            s.bid AS spot_bid
        FROM 
            futures f
        JOIN 
            spot s 
        ON 
            f.datetime = s.datetime
        WHERE 
            f.exchange_name = %s AND f.symbol = %s
            AND s.exchange_name = %s AND s.symbol = %s
        ORDER BY f.datetime DESC
        LIMIT 144;
    """
    cursor.execute(query, (futures_exchange, futures_symbol, spot_exchange, spot_symbol))
    result = cursor.fetchall()
    cursor.close()
    connection.close()
    return result

def fetch_combined_futures_data(exchange1, symbol1, exchange2, symbol2):
    """
    Извлекает объединенные данные для двух фьючерсных рынков по временной метке.

    :param exchange1: Название биржи для первого фьючерсного рынка.
    :param symbol1: Символ для первого фьючерсного рынка.
    :param exchange2: Название биржи для второго фьючерсного рынка.
    :param symbol2: Символ для второго фьючерсного рынка.
    :return: Список объединенных записей.
    """
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE
    )
    cursor = connection.cursor(dictionary=True)

    query = """
        SELECT 
            f1.datetime AS futures1_time,
            f1.ask AS futures1_ask,
            f1.bid AS futures1_bid,
            f2.datetime AS futures2_time,
            f2.ask AS futures2_ask,
            f2.bid AS futures2_bid
        FROM 
            futures f1
        JOIN 
            futures f2 
        ON 
            f1.datetime = f2.datetime
        WHERE 
            f1.exchange_name = %s AND f1.symbol = %s
            AND f2.exchange_name = %s AND f2.symbol = %s
        ORDER BY f1.datetime DESC
        LIMIT 144;
    """
    cursor.execute(query, (exchange1, symbol1, exchange2, symbol2))
    result = cursor.fetchall()
    cursor.close()
    connection.close()
    return result


with open('rating_coins_full.pickle', 'rb') as f:
    if f != None:
        data_coins = pickle.load(f)

counter = 0
coin_cap = []
for i in data_coins[0]:
    counter += 1
    coin_cap.append([counter, i['symbol']])

# замена функции get_spot_futures
@dp.message(F.text == 'Спот/Фьючерсы 🔀')
async def get_spot_futures(message: types.Message):
    user_id = message.from_user.id
    print(f"{user_id} - {message.from_user.username} - SpotFutures")

    # получаем аккаунты (чтобы проверить подписку и dataSearch)
    accounts = fetch_accounts_from_db()

    active, dataSearch = _extract_user_filters_from_accounts(accounts, user_id)
    # (Если у тебя есть кастомная функция получения dataSearch/markets для спота — используй её вместо _extract_user_filters_from_accounts)

    if not active:
        await message.answer(text='Ваша подписка неактивна')
        return

    # map params
    try:
        sort, lt = _map_dataSearch_to_service_params(dataSearch or {})
    except Exception:
        sort, lt = "spread", 0

    # запрос к Go
    try:
        resp = await fetch_go_spot(user_id=user_id, page=1, items=5, sort=sort, lt=lt)
    except Exception as e:
        logger.exception("fetch_go_spot error: %s", e)
        await message.answer(text="Ошибка получения данных от сервиса. Повторите позже.")
        return

    if not isinstance(resp, dict):
        await message.answer(text="Ответ сервиса в неверном формате.")
        return

    if resp.get("status") in ("no_sub", "inactive"):
        await message.answer(text='Ваша подписка неактивна')
        return

    pages = resp.get("pages", [])
    if not pages:
        await message.answer(text='Нет данных для отображения.')
        return

    # Построим клавиатуру для первой страницы (pages[0])
    inline_kb1 = InlineKeyboardBuilder()

    # каждая item в pages[0]["items"] ожидается как [text, symbol_or_id]
    for itm in pages[0].get("items", []):
        text = itm[0]
        symbol = itm[1]
        inline_kb1.row(InlineKeyboardButton(text=text, callback_data=f"spot_market:{symbol}"))

    # пагинация: сервис отдаёт current_page/total_pages — используем свои кнопки
    current_page = int(resp.get("current_page") or pages[0].get("page") or 1)
    total_pages = int(resp.get("total_pages") or resp.get("end_page") or current_page)

    prev_page = max(1, current_page - 1)
    next_page = min(total_pages, current_page + 1)

    inline_kb1.row(
        InlineKeyboardButton(text="<", callback_data=f"spot_page:{prev_page}"),
        InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data=f"spot_page:1"),
        InlineKeyboardButton(text=">", callback_data=f"spot_page:{next_page}")
    )

    # add filters (если есть функция)
    try:
        add_filter_buttons_spot(inline_kb1, dataSearch)
    except Exception:
        pass

    await message.answer(text='Список спот/фьючерсы', reply_markup=inline_kb1.as_markup())


def get_spread_by_symbol_and_markets(symbol, market1, market2):
    r = REDIS_CLIENTS[0]
    raw = r.get("Spreads:all")
    if not raw:
        return None

    try:
        all_spreads = orjson.loads(raw)
    except Exception as e:
        print("Ошибка при загрузке JSON:", e)
        return None

    for data in all_spreads:
        if (
            data.get('symbol') == symbol and (
                (data.get('market1') == market1 and data.get('market2') == market2) or
                (data.get('market1') == market2 and data.get('market2') == market1)
            )
        ):
            try:
                spread = (
                    0,
                    data.get('symbol', ''),
                    data.get('market1', ''),
                    data.get('market2', ''),
                    float(data.get('market1funding', 0)),
                    float(data.get('market2funding', 0)),
                    float(data.get('market1time', 0)),
                    float(data.get('market2time', 0)),
                    float(data.get('market1bid', 0)),
                    float(data.get('market2bid', 0)),
                    float(data.get('market1fee', 0)),
                    float(data.get('market2fee', 0)),
                    data.get('market1predict', ''),
                    data.get('market2predict', ''),
                    float(data.get('spread', 0)),
                    data.get('isNew', ''),
                    data.get('isUpdated', ''),
                    float(data.get('isDeviation1', 0)),
                    float(data.get('isDeviation2', 0)),
                    float(data.get('market1ask', 0)),
                    float(data.get('market2ask', 0)),
                    data.get('m1h1', ''),
                    data.get('m1h3', ''),
                    data.get('m1h7', ''),
                    data.get('m1h30', ''),
                    data.get('m2h1', ''),
                    data.get('m2h3', ''),
                    data.get('m2h7', ''),
                    data.get('m2h30', ''),
                    float(data.get('amount24m1', 0)),
                    float(data.get('amount24m2', 0)),
                    float(data.get('limitsm1', 0)),
                    float(data.get('limitsm2', 0)),
                )
                return spread
            except Exception as e:
                print("Ошибка при формировании tuple:", e)
                return None
    return None  # Ничего не найдено


def get_spot_spread_by_symbol_and_markets(symbol, market1, market2):
    all_spreads = get_cached_spotfutures()
    if all_spreads is None:
        # fallback: прочитать Redis один раз
        try:
            r = REDIS_CLIENTS[1]
            raw = r.get("SpotFutures:all")
            all_spreads = orjson.loads(raw) if raw else []
        except Exception:
            logger.exception("get_spot_spread_by_symbol_and_markets: redis fallback failed")
            return None

    for data in all_spreads:
        if (
            data.get('symbol') == symbol and (
                (data.get('market1') == market1 and data.get('market2') == market2)
            )
        ):
            try:
                spread = (
                    0,  # В вашем случае ID — пока 0
                    data.get('symbol', ''),
                    data.get('market1', ''),
                    data.get('market2', ''),
                    float(data.get('market2funding', 0)),  # market2funding, как в spot_futures_write_redis
                    float(data.get('market2time', 0)),  # market2time, как в spot_futures_write_redis
                    float(data.get('market2bid', 0)),  # market2bid, как в spot_futures_write_redis
                    float(data.get('market1fee', 0)),  # market1fee, как в spot_futures_write_redis
                    float(data.get('market2fee', 0)),  # market2fee, как в spot_futures_write_redis
                    data.get('market2predict', ''),  # market2predict
                    data.get('spread', ''),  # spread
                    data.get('isNew', ''),  # isNew
                    data.get('isUpdated', ''),  # isUpdated
                    float(data.get('isDeviation2', 0)),  # isDeviation2, как в spot_futures_write_redis
                    float(data.get('spot1bid', 0)),  # spot1bid (это было 'market1bid'
                    float(data.get('market2ask', 0)),  # market2ask
                    float(data.get('spot1ask', 0)),  # spot1ask
                    data.get('m2h1', ''),  # m2h1
                    data.get('m2h3', ''),  # m2h3
                    data.get('m2h7', ''),  # m2h7
                    data.get('m2h30', ''),  # m2h30
                    float(data.get('amount24m2', 0)),
                    float(data.get('limitsm2', 0)),
                    float(data.get('amount24spot', 0)),
                )
                return spread
            except Exception as e:
                print("Ошибка при формировании tuple:", e)
                return None
    return None  # Ничего не найдено

# @dp.callback_query(F.data.startswith("spot_id"))
# async def callbacks_num(call: types.CallbackQuery):
#     global bids_asks_futures, bids_asks_spot, coin_cap
#     print(call.from_user.id, ' - ', call.from_user.username, ' - ', 'data=', call.data)
#
#     show_id = call.data
#     if 'spot_id' in show_id:
#         reload = False
#         reloard_or_not = show_id.replace('spot_id', '')
#         if '_reload' in reloard_or_not:
#             reload = True
#             show_id = reloard_or_not.split('_')[0]
#         inline_kb1 = InlineKeyboardBuilder()
#         connection = mysql.connector.connect(
#             host=DB_HOST,
#             user=MYSQL_USER,
#             password=MYSQL_PASSWORD,
#             database=MYSQL_DATABASE
#         )
#         cursor = connection.cursor()
#         cursor.execute('''SELECT * FROM Users''')
#         accounts = cursor.fetchall()
#         connection.close()
#         successActive = False
#         if len(accounts) > 0:
#             for acc in accounts:
#                 if str(acc[2]) == str(call.from_user.id):
#                     if acc[9] == '1' and acc[10] == '2':
#                         successActive = True
#                     elif acc[10] == '1':
#                         successActive = True
#                     elif acc[14] == '1':
#                         successActive = True
#             if successActive:
#                 print('yes ID')
#                 call_data = show_id.replace('spot_id', '')
#
#                 spreads = None
#                 if reload is False:
#                     try:
#                         s1 = call.data.split('_')[4]
#                         m1 = call.data.split('_')[2]
#                         m2 = call.data.split('_')[3]
#                         spreads = get_spot_spread_by_symbol_and_markets(s1, m1, m2)
#
#                     except Exception:
#                         spreads = None
#                 else:
#                     try:
#                         s1 = call.data.split('_')[5]
#                         m1 = call.data.split('_')[3]
#                         m2 = call.data.split('_')[4]
#                         spreads = get_spot_spread_by_symbol_and_markets(s1, m1, m2)
#                     except Exception:
#                         spreads = None
#
#                 bot_message = spreads
#
#                 if bot_message is not None:
#                     button_reload_id = InlineKeyboardButton(text='Обновить',
#                                                             callback_data=f'spot_id0_reload_{bot_message[2]}_{bot_message[3]}_{bot_message[1]}')
#                     button_graphic_spot = add_inline_button_graphic_spot(bot_message)
#
#                     if bot_message is not None:
#                         creating_message = create_message_to_spot(bot_message, coin_cap)
#                         inline_kb1.row(button_reload_id, button_graphic_spot)
#                         if reload:
#                             try:
#                                 await call.message.edit_text(creating_message, reply_markup=inline_kb1.as_markup(), parse_mode='HTML', disable_web_page_preview=True)
#                             except Exception:
#                                 print('not modified SPOT_ID')
#                         else:
#                             await call.message.answer(creating_message, reply_markup=inline_kb1.as_markup(), parse_mode='HTML', disable_web_page_preview=True)
#                 else:
#                     await call.message.answer(text='Возможно этого спреда больше нет', parse_mode='HTML')


@dp.callback_query(F.data.startswith("marketlist"))
async def marketlist_call(call: types.CallbackQuery):
    await call.answer(cache_time=0)
    connection = None
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()
        cursor.execute('''SELECT * FROM Users''')
        inline_kb1 = InlineKeyboardBuilder()
        accounts = cursor.fetchall()
        marketslistfutures = None
        marketslistspot = None
        if len(accounts) > 0:
            for acc in accounts:
                if str(acc[2]) == str(call.from_user.id):
                    marketslistfutures = acc[5]
                    marketslistspot = acc[6]
        marketslistfutures = orjson.loads(marketslistfutures)
        marketslistspot = orjson.loads(marketslistspot)
        if len(str(call.data).split('_')) == 3:
            if 'marketlist_future' in call.data:
                market = str(call.data).split('_')[2]
                for i in range(0, len(marketslistfutures)):
                    if market.capitalize() == 'Bingx':
                        market_check = 'BingX'
                    elif market.capitalize() == 'Bitmart':
                        market_check = 'BitMart'
                    elif market.capitalize() == 'Coinex':
                        market_check = 'CoinEx'
                    elif market.capitalize() == 'Lbank':
                        market_check = 'LBank'
                    elif market.capitalize() == 'Xt':
                        market_check = 'XT'
                    elif market.capitalize() == 'Weex':
                        market_check = 'WEEX'
                    elif market.capitalize() == 'Binancealpha':
                        market_check = 'BinanceAlpha'
                    else:
                        market_check = market.capitalize()
                    if marketslistfutures[i].split('_')[0] == market_check:
                        marketslistfutures[i] = market_check+'_0'
                send_list = orjson.dumps(marketslistfutures)
                cursor.execute('''Update Users SET listMarketsFutures=%s WHERE tgid=%s;''', (send_list, call.from_user.id))
                connection.commit()
            elif 'marketlist_spot' in call.data:
                market = str(call.data).split('_')[2]

                for i in range(0, len(marketslistspot)):
                    if market.capitalize() == 'Bingx':
                        market_check = 'BingX'
                    elif market.capitalize() == 'Bitmart':
                        market_check = 'BitMart'
                    elif market.capitalize() == 'Coinex':
                        market_check = 'CoinEx'
                    elif market.capitalize() == 'Lbank':
                        market_check = 'LBank'
                    elif market.capitalize() == 'Xt':
                        market_check = 'XT'
                    elif market.capitalize() == 'Weex':
                        market_check = 'WEEX'
                    elif market.capitalize() == 'Binancealpha':
                        market_check = 'BinanceAlpha'
                    else:
                        market_check = market.capitalize()
                    if marketslistspot[i].split('_')[0] == market_check:
                        marketslistspot[i] = market_check + '_0'
                send_list = orjson.dumps(marketslistspot)
                cursor.execute('''Update Users SET listMarketsSpot=%s WHERE tgid=%s;''',
                               (send_list, call.from_user.id))
                connection.commit()
        elif len(str(call.data).split('_')) == 4:
            if 'marketlist_future' in call.data:
                market = str(call.data).split('_')[2]
                isOff = str(call.data).split('_')[3]
                if isOff == 'off':
                    for i in range(0, len(marketslistfutures)):
                        if market.capitalize() == 'Bingx':
                            market_check = 'BingX'
                        elif market.capitalize() == 'Bitmart':
                            market_check = 'BitMart'
                        elif market.capitalize() == 'Coinex':
                            market_check = 'CoinEx'
                        elif market.capitalize() == 'Lbank':
                            market_check = 'LBank'
                        elif market.capitalize() == 'Xt':
                            market_check = 'XT'
                        elif market.capitalize() == 'Weex':
                            market_check = 'WEEX'
                        elif market.capitalize() == 'Binancealpha':
                            market_check = 'BinanceAlpha'
                        else:
                            market_check = market.capitalize()
                        if marketslistfutures[i].split('_')[0] == market_check:
                            marketslistfutures[i] = market_check + '_1'
                    send_list = orjson.dumps(marketslistfutures)
                    cursor.execute('''Update Users SET listMarketsFutures=%s WHERE tgid=%s;''',
                                   (send_list, call.from_user.id))
                    connection.commit()
            if 'marketlist_spot' in call.data:
                market = str(call.data).split('_')[2]
                isOff = str(call.data).split('_')[3]
                if isOff == 'off':
                    for i in range(0, len(marketslistspot)):
                        if market.capitalize() == 'Bingx':
                            market_check = 'BingX'
                        elif market.capitalize() == 'Bitmart':
                            market_check = 'BitMart'
                        elif market.capitalize() == 'Coinex':
                            market_check = 'CoinEx'
                        elif market.capitalize() == 'Lbank':
                            market_check = 'LBank'
                        elif market.capitalize() == 'Xt':
                            market_check = 'XT'
                        elif market.capitalize() == 'Weex':
                            market_check = 'WEEX'
                        elif market.capitalize() == 'Binancealpha':
                            market_check = 'BinanceAlpha'
                        else:
                            market_check = market.capitalize()
                        if marketslistspot[i].split('_')[0] == market_check:
                            marketslistspot[i] = market_check + '_1'
                    send_list = orjson.dumps(marketslistspot)
                    cursor.execute('''Update Users SET listMarketsSpot=%s WHERE tgid=%s;''',
                                   (send_list, call.from_user.id))
                    connection.commit()
    except Exception as e:
        print('exception markets:', e)
    finally:
        try:
            if connection:
                connection.close()
        except Exception as e:
            print('cant close conn marketlist_call:', e)
    futures_spot = []
    for i in range(len(marketslistfutures)):
        futures_spot.append([marketslistfutures[i], marketslistspot[i]])
    for s_f in futures_spot:
        if str(s_f[0]).split('_')[1] == '1' and str(s_f[1]).split('_')[1] == '1':
            inline_kb1.row(globals()[f"button_futures_{str(s_f[0]).split('_')[0].lower()}"], globals()[f"button_spot_{str(s_f[0]).split('_')[0].lower()}"])
        elif str(s_f[0]).split('_')[1] == '0' and str(s_f[1]).split('_')[1] == '1':
            inline_kb1.row(globals()[f"button_futures_{str(s_f[0]).split('_')[0].lower()}_off"], globals()[f"button_spot_{str(s_f[0]).split('_')[0].lower()}"])
        elif str(s_f[0]).split('_')[1] == '1' and str(s_f[1]).split('_')[1] == '0':
            inline_kb1.row(globals()[f"button_futures_{str(s_f[0]).split('_')[0].lower()}"], globals()[f"button_spot_{str(s_f[0]).split('_')[0].lower()}_off"])
        elif str(s_f[0]).split('_')[1] == '0' and str(s_f[1]).split('_')[1] == '0':
            inline_kb1.row(globals()[f"button_futures_{str(s_f[0]).split('_')[0].lower()}_off"], globals()[f"button_spot_{str(s_f[0]).split('_')[0].lower()}_off"])
    try:
        await call.message.edit_text('Список бирж (фьючерсы | спот)', reply_markup=inline_kb1.as_markup())
    except Exception as e:
        print(e)


@dp.message(F.text == 'Биржи ⚙️')
async def list_markets(message: types.Message):
    print(message.from_user.id, ' - ', message.from_user.username, ' - ', 'ListOfMarkets')
    inline_kb1 = InlineKeyboardBuilder()

    connection = mysql.connector.connect(
        host=DB_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE
    )
    cursor = connection.cursor()
    cursor.execute('''SELECT * FROM Users''')
    accounts = cursor.fetchall()
    connection.close()
    marketslistfutures = None
    marketlistspot = None
    if len(accounts) > 0:
        for acc in accounts:
            if str(acc[2]) == str(message.from_user.id):
                marketslistfutures = acc[5]
                marketslistspot = acc[6]
    marketslistfutures = orjson.loads(marketslistfutures)
    marketslistspot = orjson.loads(marketslistspot)
    futures_spot = []
    for i in range(len(marketslistfutures)):
        futures_spot.append([marketslistfutures[i], marketslistspot[i]])
    for s_f in futures_spot:
        if str(s_f[0]).split('_')[1] == '1' and str(s_f[1]).split('_')[1] == '1':
            inline_kb1.row(globals()[f"button_futures_{str(s_f[0]).split('_')[0].lower()}"], globals()[f"button_spot_{str(s_f[0]).split('_')[0].lower()}"])
        elif str(s_f[0]).split('_')[1] == '0' and str(s_f[1]).split('_')[1] == '1':
            inline_kb1.row(globals()[f"button_futures_{str(s_f[0]).split('_')[0].lower()}_off"], globals()[f"button_spot_{str(s_f[0]).split('_')[0].lower()}"])
        elif str(s_f[0]).split('_')[1] == '1' and str(s_f[1]).split('_')[1] == '0':
            inline_kb1.row(globals()[f"button_futures_{str(s_f[0]).split('_')[0].lower()}"], globals()[f"button_spot_{str(s_f[0]).split('_')[0].lower()}_off"])
        elif str(s_f[0]).split('_')[1] == '0' and str(s_f[1]).split('_')[1] == '0':
            inline_kb1.row(globals()[f"button_futures_{str(s_f[0]).split('_')[0].lower()}_off"], globals()[f"button_spot_{str(s_f[0]).split('_')[0].lower()}_off"])
    await message.answer(text='Список бирж (фьючерсы | спот)', reply_markup=inline_kb1.as_markup())


@dp.callback_query(F.data.startswith("mon_restore"))
async def restore_monitoring(call: types.CallbackQuery):
    print(call.from_user.id, ' - ', call.from_user.username, ' - ', 'Mon_restore')
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE
    )
    cursor = connection.cursor()
    cursor.execute('''SELECT * FROM Users''')
    accounts = cursor.fetchall()

    if len(accounts) > 0:
        for acc in accounts:
            if str(acc[2]) == str(call.from_user.id):
                cursor.execute('''
                         UPDATE Users SET lastNoticeCoins=%s WHERE tgid=%s
                         ''', (b'no', call.from_user.id))
                connection.commit()
                connection.close()
                await call.message.answer(text='Готово')
                async with _dedupe_lock:
                    _dedupe_map.pop(str(call.from_user.id), None)

class Mydialog(StatesGroup):
    spread = State()
    course_spread = State()
    dex_diff_gt = State()  # ожидаем ввод порога > (например 2.0)
    dex_diff_lt = State()  # ожидаем ввод порога < (например -5.0)

class PaidAddress(StatesGroup):
    address = State()


class AdminFunc(StatesGroup):
    access = State()
    off_access = State()
    reset_access = State()


class CoinSearch(StatesGroup):
    awaiting_coin_futures = State()
    awaiting_coin_spot = State()


class PageSearch(StatesGroup):
    awaiting_page_futures = State()
    awaiting_page_spot = State()
    awaiting_page_dex = State()
    awaiting_coin_dex = State()

def parse_percent_input(text: str):
    """
    Принимает строку вида '2', '2%', ' -5,5%' -> возвращает float (например 2.0 или -5.5)
    Возвращает None при невалидном вводе.
    """
    if not isinstance(text, str):
        return None
    s = text.strip().replace(',', '.')
    if s.endswith('%'):
        s = s[:-1].strip()
    if s == '':
        return None
    try:
        val = float(s)
        # округляем до 2 знаков
        return round(val, 2)
    except Exception:
        return None

def load_dex_blacklist(acc):
    try:
        if acc[16] == b'no':
            return set()
        decompressed = zlib.decompress(acc[16])
        coins_dict = orjson.loads(decompressed.decode('utf-8'))
        return set(coins_dict.keys())
    except Exception as e:
        print(f'Ошибка при разборе blacklist: {e}')
        return set()


def decompress_info_blacklist(blob: bytes) -> dict:
    """
    Распаковать поле information (zlib compressed json) -> dict.
    Безопасно: при ошибке вернём пустой dict.
    """
    try:
        if not blob or blob == b'no':
            return {}
        # Если blob уже str (редко) — корректируем
        if isinstance(blob, str):
            try:
                return orjson.loads(blob)
            except Exception:
                return {}
        return orjson.loads(zlib.decompress(blob).decode('utf-8'))
    except Exception:
        logger.exception("decompress_info_blacklist failed")
        return {}

def normalize_symbol_key(sym: str) -> str:
    """
    Привести символ к ключу вида 'COINUSDT' (uppercase, с суффиксом USDT).
    Если вход 'BTC' -> 'BTCUSDT', если 'btcUsdt' -> 'BTCUSDT'.
    """
    try:
        s = str(sym).strip().upper()
        # удаляем возможные нежелательные символы вокруг
        s = ''.join(ch for ch in s if ch.isalnum())
        if not s:
            return ''
        if s.endswith('USDT'):
            return s
        return f"{s}USDT"
    except Exception:
        return ''


def extract_token_key(symbol: str) -> str:
    """
    Из symbol (например "TON_TONUSDT" или "TONUSDT" или "TON_TON") возвращаем нормализованный ключ
    для сравнения с dex_blacklist, в формате 'TONUSDT'.
    """
    try:
        s = (symbol or '').strip().upper()
        # если есть underscore — берем вторую часть
        if '_' in s:
            token_part = s.split('_', 1)[1]
        else:
            token_part = s

        # убираем суффикс USDT если есть
        if token_part.endswith('USDT'):
            token_part = token_part[:-4]

        # оставляем только букв/цифр
        token_core = ''.join(ch for ch in token_part if ch.isalnum())

        if not token_core:
            return ''
        # возвращаем в том же виде, который ты сохраняешь в БД (normalize_coin_for_store делает так же)
        return f"{token_core}USDT"
    except Exception:
        return ''


@dp.callback_query(F.data == "dex_page_from:page")
async def ask_page_dex(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите номер страницы для DEX:")
    await state.set_state(PageSearch.awaiting_page_dex)
    await callback.answer()


@dp.callback_query(F.data == "dex_page_from:coin")
async def ask_coin_dex(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название монеты (например: ETH) или с блокчейном (ETH MNT):")
    await state.set_state(PageSearch.awaiting_coin_dex)
    await callback.answer()

@dp.message(PageSearch.awaiting_page_dex)
async def process_page_dex(message: types.Message, state: FSMContext):
    page = message.text.strip()

    if not page.isdigit() or (int(page) - 1) < 0:
        await message.answer("Введите корректный номер страницы (целое число от 1 и выше).")
        return

    await state.clear()
    try:
        await show_dex_page(message.from_user.id, int(page) - 1, message)
    except Exception:
        await message.answer("Ошибка при переходе на страницу DEX.")

@dp.message(PageSearch.awaiting_coin_dex)
async def process_coin_dex(message: types.Message, state: FSMContext):
    await state.clear()
    raw_text = message.text.strip().upper()

    parts = raw_text.split()
    symbol = raw_text
    found_symbol = None
    dex_recs = None

    if len(parts) == 2:
        # Пользователь ввел "CHAIN TOKEN"
        chain, token = parts
        symbol = f"{chain}_{token}"
        possible_symbols = {symbol, symbol + "USDT"}

        for s in possible_symbols:
            recs = get_cached_dex_by_symbol(s)
            if recs:
                found_symbol = s
                dex_recs = recs
                break

    else:
        # Пользователь ввёл только монету, например "TON"
        symbol_core = raw_text.replace(" ", "")
        if symbol_core.endswith("USDT"):
            symbol_core = symbol_core[:-4]

        # Формируем автодогадку по всем известным сетям
        guessed_symbols = []
        for chain_prefix in set(k[:3].upper() for k in CHAIN_MAP.keys()):
            guessed_symbols.append(f"{chain_prefix}_{symbol_core}")
            guessed_symbols.append(f"{chain_prefix}_{symbol_core}USDT")

        # Добавляем стандартные варианты
        guessed_symbols.append(symbol_core)
        guessed_symbols.append(symbol_core + "USDT")

        for s in guessed_symbols:
            recs = get_cached_dex_by_symbol(s)
            if recs:
                found_symbol = s
                dex_recs = recs
                break

    if not dex_recs:
        await message.answer(f"Монета {raw_text} не найдена в DEX.")
        return

    # Фейковый callback для handler_dex_market
    class FakeCall:
        def __init__(self, from_user, message, data):
            self.from_user = from_user
            self.message = message
            self.data = data

    fake_call = FakeCall(
        from_user=message.from_user,
        message=message,
        data=f"dex_market:in:{found_symbol}:0"
    )

    try:
        await handler_dex_market(fake_call)
    except Exception:
        import logging
        logging.exception("Ошибка в process_coin_dex handler_dex_market")
        await message.answer(f"Ошибка при поиске монеты {raw_text}.")



@dp.callback_query(F.data == "page_from:page")
async def ask_page_futures(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите номер страницы для фьючерс/фьючерс:")
    await state.set_state(PageSearch.awaiting_page_futures)
    await callback.answer()


@dp.callback_query(F.data == "spot_page_from:page")
async def ask_page_spot(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите номер страницы для спот/фьючерс:")
    await state.set_state(PageSearch.awaiting_page_spot)
    await callback.answer()


@dp.message(PageSearch.awaiting_page_futures)
async def process_page_futures(message: types.Message, state: FSMContext):
    page = message.text.strip()

    if not page.isdigit() or (int(page)-1) < 0:
        await message.answer("Введите корректный номер страницы (целое число от 1 и выше).")
        return

    await state.clear()
    try:
        await show_futures_page(message.from_user.id, int(page)-1, message)
    except Exception:
        await message.answer(f"Произошла ошибка при переходе на страницу")


@dp.message(PageSearch.awaiting_page_spot)
async def process_page_spot(message: types.Message, state: FSMContext):
    page = message.text.strip()

    if not page.isdigit() or (int(page)-1) < 0:
        await message.answer("Введите корректный номер страницы (целое число от 1 и выше).")
        return

    await state.clear()
    try:
        await show_spot_page(message.from_user.id, int(page)-1, message)
    except Exception:
        await message.answer(f"Произошла ошибка при переходе на страницу")


@dp.callback_query(F.data == "page_from:coin")
async def ask_coin_futures(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название монеты (например: BTC или BTCUSDT):")
    await state.set_state(CoinSearch.awaiting_coin_futures)
    await callback.answer()


@dp.callback_query(F.data == "spot_page_from:coin")
async def ask_coin_spot(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название монеты для спота (например: ETH или ETHUSDT):")
    await state.set_state(CoinSearch.awaiting_coin_spot)
    await callback.answer()


@dp.message(CoinSearch.awaiting_coin_futures)
async def process_coin_futures(message: types.Message, state: FSMContext):
    text = message.text.strip().upper().replace("USDT", "")
    if not text.isalnum():
        await message.answer("Название монеты должно содержать только латинские буквы и цифры.")
        return

    if len(text) > 25:
        await message.answer("Название монеты слишком длинное (максимум 25 символов).")
        return

    await state.clear()

    try:
        await get_markets_callback(user_id=message.from_user.id, symbolFind=text+'USDT', message=message)
    except Exception:
        await message.answer(f"Произошла ошибка при поиске монеты")

def build_monitoring_kb(dataSearch):
    """
    Вернёт InlineKeyboardBuilder с кнопками мониторинга, включая DEX-blacklist.
    dataSearch: 'no' | None | JSON-string | dict
    """
    kb = InlineKeyboardBuilder()

    # Нормализуем dataSearch в dict
    ds = {}
    if dataSearch and dataSearch != 'no':
        if isinstance(dataSearch, str):
            try:
                ds = json.loads(dataSearch)
            except Exception:
                ds = {}
        elif isinstance(dataSearch, dict):
            ds = dataSearch
        else:
            ds = {}
    else:
        ds = {}

    # 1) DEX blacklist row (view/add/del)
    kb.row(button_mon_dex_black_view, button_mon_dex_black_add, button_mon_dex_black_del)

    # 2) DEX thresholds ( > / < )
    if ds.get('dex_diff_gt', 'no') != 'no':
        kb.row(
            InlineKeyboardButton(text=f'DEX > {ds["dex_diff_gt"]}%', callback_data='None'),
            button_mon_dex_gt_on_act, button_mon_dex_gt_off
        )
    else:
        kb.row(button_mon_dex_gt, button_mon_dex_gt_on, button_mon_dex_gt_off_act)

    if ds.get('dex_diff_lt', 'no') != 'no':
        kb.row(
            InlineKeyboardButton(text=f'DEX < {ds["dex_diff_lt"]}%', callback_data='None'),
            button_mon_dex_lt_on_act, button_mon_dex_lt_off
        )
    else:
        kb.row(button_mon_dex_lt, button_mon_dex_lt_on, button_mon_dex_lt_off_act)

    # 3) Спреды/курсы — воспроизводим твою логику отображения кнопок (минимально)
    # Фандинг
    if ds.get('spread', 'no') != 'no':
        kb.row(button_mon_spread_count(ds['spread']), button_mon_spread_on_act, button_mon_spread_off)
    else:
        kb.row(button_mon_spread, button_mon_spread_on, button_mon_spread_off_act)

    # Вход
    if ds.get('course_spread', 'no') != 'no':
        kb.row(button_mon_course_spread_count(ds['course_spread']), button_mon_course_spread_on_act, button_mon_course_spread_off)
    else:
        kb.row(button_mon_course_spread, button_mon_course_spread_on, button_mon_course_spread_off_act)

    kb.row(button_restore_mon)
    return kb



@dp.message(CoinSearch.awaiting_coin_spot)
async def process_coin_spot(message: types.Message, state: FSMContext):
    text = message.text.strip().upper().replace("USDT", "")

    if not text.isalnum():
        await message.answer("Название монеты должно содержать только латинские буквы и цифры.")
        return

    if len(text) > 25:
        await message.answer("Название монеты слишком длинное (максимум 25 символов).")
        return

    await state.clear()

    try:
        await get_spot_markets_callback(user_id=message.from_user.id, symbolFind=text+'USDT', message=message)
    except Exception:
        await message.answer(f"Произошла ошибка при поиске монеты")


@dp.message(Mydialog.spread) # Принимаем состояние
async def start_spread_dial(message: types.Message, state: FSMContext):
    print(message.text)
    await state.clear()
    inline_kb1 = InlineKeyboardBuilder()
    try:
        check = round(float(message.text), 2)
        if check >= 0.6:
            connection = mysql.connector.connect(
                host=DB_HOST,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE
            )
            cursor = connection.cursor()
            cursor.execute('''SELECT * FROM Users''')
            accounts = cursor.fetchall()
            dataSearch = None
            if len(accounts) > 0:
                for acc in accounts:
                    if str(acc[2]) == str(message.from_user.id):
                        dataSearch = acc[4]
            if dataSearch == 'no':
                to_dump = {'spread': str(round(float(message.text), 2)), 'course_spread': 'no'}
                data_s = json.dumps(to_dump)
                dataSearch = data_s
                cursor.execute('''
                 UPDATE Users SET dataSearch=%s WHERE tgid=%s
                 ''', (data_s, message.from_user.id))
                connection.commit()
            else:
                from_dump = json.loads(dataSearch)
                from_dump['spread'] = str(round(float(message.text),2))
                data_s = json.dumps(from_dump)
                dataSearch = data_s
                cursor.execute('''
                         UPDATE Users SET dataSearch=%s WHERE tgid=%s
                         ''', (data_s, message.from_user.id))
                connection.commit()

            connection.close()
            inline_kb1 = build_monitoring_kb(dataSearch)
            await message.answer(text='Настройка мониторинга', reply_markup=inline_kb1.as_markup())
        else:
            await message.answer(text='Фандинг должен быть больше или равен 0.6')
    except Exception as e:
        await message.answer(text='Неверное значение')


@dp.message(Mydialog.course_spread) # Принимаем состояние
async def start_cour_sp(message: types.Message, state: FSMContext):
    print(message.text)
    await state.clear()
    inline_kb1 = InlineKeyboardBuilder()

    try:
        check = round(float(message.text), 2)
        if check >= 2:
            connection = mysql.connector.connect(
                host=DB_HOST,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE
            )
            cursor = connection.cursor()
            cursor.execute('''SELECT * FROM Users''')
            accounts = cursor.fetchall()
            dataSearch = None
            if len(accounts) > 0:
                for acc in accounts:
                    if str(acc[2]) == str(message.from_user.id):
                        dataSearch = acc[4]
            if dataSearch == 'no':
                to_dump = {'spread': 'no', 'course_spread': str(round(float(message.text), 2))}
                data_s = json.dumps(to_dump)
                cursor.execute('''
                     UPDATE Users SET dataSearch=%s WHERE tgid=%s
                     ''', (data_s, message.from_user.id))
                connection.commit()
                dataSearch = data_s
            else:
                from_dump = json.loads(dataSearch)
                from_dump['course_spread'] = str(round(float(message.text), 2))
                data_s = json.dumps(from_dump)
                dataSearch = data_s
                cursor.execute('''
                         UPDATE Users SET dataSearch=%s WHERE tgid=%s
                         ''', (data_s, message.from_user.id))
                connection.commit()

            connection.close()
            inline_kb1 = build_monitoring_kb(dataSearch)
            await message.answer(text='Настройка мониторинга', reply_markup=inline_kb1.as_markup())
        else:
            await message.answer(text='Спред входа должен быть больше или равен 2')
    except Exception as e:
        await message.answer(text='Неверное значение')

@dp.message(Mydialog.dex_diff_gt)
async def start_dex_gt(message: types.Message, state: FSMContext):
    await state.clear()
    inline_kb1 = InlineKeyboardBuilder()
    val = parse_percent_input(message.text)
    if val is None:
        await message.answer("Неверный формат. Введите число в процентах, например `2` или `2%`.")
        return

    # валидация: минимум 2.0 (можете изменить)
    if val < 2.0:
        await message.answer("Порог DEX (больше) должен быть не ниже 2.0% (введите, например, 2).")
        return

    # Сохраняем в Users.dataSearch (как у тебя в других хэндлерах)
    try:
        connection = mysql.connector.connect(host=DB_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DATABASE)
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM Users')
        accounts = cursor.fetchall()
        dataSearch = None
        for acc in accounts:
            if str(acc[2]) == str(message.from_user.id):
                dataSearch = acc[4]
                break

        if dataSearch == 'no' or dataSearch is None:
            to_dump = {'spread': 'no', 'course_spread': 'no', 'dex_diff_gt': str(val), 'dex_diff_lt': 'no'}
            data_s = json.dumps(to_dump)
            cursor.execute('UPDATE Users SET dataSearch=%s WHERE tgid=%s', (data_s, message.from_user.id))
        else:
            from_dump = json.loads(dataSearch)
            from_dump['dex_diff_gt'] = str(val)
            data_s = orjson.dumps(from_dump)
            cursor.execute('UPDATE Users SET dataSearch=%s WHERE tgid=%s', (data_s, message.from_user.id))
        connection.commit()
        connection.close()
        # собрать KB и показать
        inline_kb1 = build_monitoring_kb(data_s)
        await message.answer(text='Настройка мониторинга', reply_markup=inline_kb1.as_markup())

    except Exception as e:
        logger.exception("save dex_diff_gt error")
        await message.answer("Ошибка при сохранении. Попробуйте ещё раз позже.")
        return

    # Обновляем клавиатуру состояния мониторинга — можно повторить логику, как у тебя в start_spread_dial
    # Для простоты: отправим подтверждение
    await message.answer(f"Установлен порог DEX: уведомлять когда спред входа > {val}%.\n")

@dp.message(Mydialog.dex_diff_lt)
async def start_dex_lt(message: types.Message, state: FSMContext):
    await state.clear()
    val = parse_percent_input(message.text)
    if val is None:
        await message.answer("Неверный формат. Введите число в процентах, например `-5` или `-5%`.")
        return

    # валидация: максимум -5.0 (т.е. должно быть <= -5)
    if val > -5.0:
        await message.answer("Порог DEX (меньше) ожидается не выше -5.0% (введите, например, -5 или -7).")
        return

    try:
        connection = mysql.connector.connect(host=DB_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DATABASE)
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM Users')
        accounts = cursor.fetchall()
        dataSearch = None
        for acc in accounts:
            if str(acc[2]) == str(message.from_user.id):
                dataSearch = acc[4]
                break

        if dataSearch == 'no' or dataSearch is None:
            to_dump = {'spread': 'no', 'course_spread': 'no', 'dex_diff_gt': 'no', 'dex_diff_lt': str(val)}
            data_s = json.dumps(to_dump)
            cursor.execute('UPDATE Users SET dataSearch=%s WHERE tgid=%s', (data_s, message.from_user.id))
        else:
            from_dump = orjson.loads(dataSearch)
            from_dump['dex_diff_lt'] = str(val)
            data_s = json.dumps(from_dump)
            cursor.execute('UPDATE Users SET dataSearch=%s WHERE tgid=%s', (data_s, message.from_user.id))
        connection.commit()
        connection.close()
        # собрать KB и показать
        inline_kb1 = build_monitoring_kb(data_s)
        await message.answer(text='Настройка мониторинга', reply_markup=inline_kb1.as_markup())

    except Exception:
        logger.exception("save dex_diff_lt error")
        await message.answer("Ошибка при сохранении. Попробуйте ещё раз позже.")
        return

    await message.answer(f"Установлен порог DEX: уведомлять когда спред входа < {val}%.\n")


# ------------------------------------------------------------------
# Обработчик callback-ов монитора (вместо старого tracking_settings)
# ------------------------------------------------------------------
@dp.callback_query(F.data.startswith("mon_"))
async def tracking_settings(call: types.CallbackQuery, state: FSMContext):
    await call.answer()  # мгновенная апрувация callback чтобы не было "часиков"
    tgid = str(call.from_user.id)
    connection = None
    cursor = None
    try:
        connection = mysql.connector.connect(host=DB_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DATABASE)
        cursor = connection.cursor()
        # читаем только dataSearch и information (если понадобится) для текущего пользователя
        cursor.execute("SELECT dataSearch, information FROM Users WHERE tgid=%s", (tgid,))
        row = cursor.fetchone()
        dataSearch = row[0] if row and len(row) > 0 else None
        information_blob = row[1] if row and len(row) > 1 else None

        # --- Обработка кнопок DEX blacklist (view/add/del) ---
        if call.data == 'mon_dex_black_view':
            # Показываем DEX-чёрный список (используем утилиту get_user_dex_blacklist_db если есть)
            try:
                bl = get_user_dex_blacklist_db(call.from_user.id)
                if not bl:
                    await call.message.answer("DEX черный список пуст.")
                else:
                    coins = ', '.join(k.replace('USDT', '') for k in sorted(bl.keys()))
                    await call.message.answer(f"DEX черный список:\n\n{coins}")
            except Exception:
                logger.exception("mon_dex_black_view error")
                await call.message.answer("Ошибка при получении DEX-чёрного списка.")
            return

        if call.data == 'mon_dex_black_add':
            await call.message.answer("Введите монеты через запятую для добавления в DEX-чёрный список (напр.: BTC, eth):")
            await state.set_state(DexBlackListFunc.add_black_dex)
            return

        if call.data == 'mon_dex_black_del':
            await call.message.answer("Введите монеты через запятую для удаления из DEX-чёрного списка (напр.: BTC, eth):")
            await state.set_state(DexBlackListFunc.del_black_dex)
            return

        # --- DEX thresholds on/off ---
        if call.data == 'mon_dex_gt_on':
            await call.message.answer(text='Введите порог DEX для уведомления (например: 2 или 2%).')
            await state.set_state(Mydialog.dex_diff_gt)
            return

        if call.data == 'mon_dex_lt_on':
            await call.message.answer(text='Введите порог DEX для уведомления (меньше), например -5 или -5%.')
            await state.set_state(Mydialog.dex_diff_lt)
            return

        if call.data in ('mon_dex_gt_off', 'mon_dex_lt_off'):
            # обновляем dataSearch: ставим соответствующий ключ в 'no'
            ds = {}
            if dataSearch and dataSearch != 'no':
                try:
                    ds = json.loads(dataSearch)
                except Exception:
                    ds = {}
            # безопасно меняем нужный ключ
            if call.data == 'mon_dex_gt_off':
                ds['dex_diff_gt'] = 'no'
            else:
                ds['dex_diff_lt'] = 'no'

            data_s = json.dumps(ds)
            cursor.execute('UPDATE Users SET dataSearch=%s WHERE tgid=%s', (data_s, tgid))
            connection.commit()

            inline_kb = build_monitoring_kb(data_s)
            try:
                await call.message.edit_text(text='Настройка мониторинга', reply_markup=inline_kb.as_markup())
            except Exception:
                await call.message.answer(text='Настройка мониторинга', reply_markup=inline_kb.as_markup())
            return

        # --- Фандинг / Вход (spread/course_spread) on/off handlers ---
        if call.data == 'mon_spread_on':
            await call.message.answer(text='Введите желаемый фандинг от 0.6, например, 0.8')
            await state.set_state(Mydialog.spread)
            return

        if call.data == 'mon_coursespread_on':
            await call.message.answer(text='Введите желаемый спред входа от 2, например, 4.5')
            await state.set_state(Mydialog.course_spread)
            return

        if call.data in ('mon_spread_off', 'mon_coursespread_off'):
            ds = {}
            if dataSearch and dataSearch != 'no':
                try:
                    ds = json.loads(dataSearch)
                except Exception:
                    ds = {}
            if call.data == 'mon_spread_off':
                ds['spread'] = 'no'
            else:
                ds['course_spread'] = 'no'

            data_s = json.dumps(ds)
            cursor.execute('UPDATE Users SET dataSearch=%s WHERE tgid=%s', (data_s, tgid))
            connection.commit()

            inline_kb = build_monitoring_kb(data_s)
            try:
                await call.message.edit_text(text='Настройка мониторинга', reply_markup=inline_kb.as_markup())
            except Exception:
                await call.message.answer(text='Настройка мониторинга', reply_markup=inline_kb.as_markup())
            return

        # --- Если дошли сюда: неизвестный mon_* — просто обновляем клавиатуру (safe fallback) ---
        inline_kb = build_monitoring_kb(dataSearch)
        try:
            await call.message.edit_text(text='Настройка мониторинга', reply_markup=inline_kb.as_markup())
        except Exception:
            await call.message.answer(text='Настройка мониторинга', reply_markup=inline_kb.as_markup())

    except Exception as e:
        logger.exception("tracking_settings error")
        try:
            await call.message.answer("Ошибка при обработке настроек мониторинга.")
        except:
            pass
    finally:
        try:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
        except:
            pass

# ------------------------------------------------------------------
# Обработчик команды "Мониторинг 🔧" (заменяем tracking_spreads)
# ------------------------------------------------------------------
@dp.message(F.text == 'Мониторинг 🔧')
async def tracking_spreads(message: types.Message):
    tgid = str(message.from_user.id)
    connection = None
    cursor = None
    try:
        connection = mysql.connector.connect(host=DB_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DATABASE)
        cursor = connection.cursor()
        cursor.execute("SELECT dataSearch FROM Users WHERE tgid=%s", (tgid,))
        row = cursor.fetchone()
        dataSearch = row[0] if row and len(row) > 0 else None

        kb = build_monitoring_kb(dataSearch)
        await message.answer(text='Настройка мониторинга', reply_markup=kb.as_markup())

    except Exception:
        logger.exception("tracking_spreads error")
        await message.answer("Ошибка при открытии настроек мониторинга.")
    finally:
        try:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
        except:
            pass


@dp.message(F.text == 'Подсказка 🕓')
async def funding_timehelp(message: types.Message):
    print(message.from_user.id, ' - ', message.from_user.username, ' - ', message.text)
    await message.answer('Выплаты фандинга каждые 8ч(МСК):\nВсе биржи: 03:00, 11:00, 19:00\nKucoin: 07:00, 15:00, 23:00')


def run_asyncio_task_in_thread(coro_func):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(coro_func())


def start_thread(coro_func):
    thread = threading.Thread(target=run_asyncio_task_in_thread, args=(coro_func,))
    thread.daemon = True
    thread.start()

def _make_group_key_from_tuple(bot_tuple: Tuple[Any, ...]) -> str:
    # ожидается, что в tuple в позиции 1 находится symbol/pair вроде "BTCUSDT" или "ETHUSDT"
    return str(bot_tuple[1]).upper()

def create_aggregated_message_to_futures(primary_entry: Dict[str, Any], others: List[Dict[str, Any]], coin_cap) -> str:
    """
    primary_entry — dict, содержащий tuple + reverse
    others — список dict’ов (аналогично)
    """
    try:
        primary_tuple = primary_entry["tuple"]
        reverse = primary_entry.get("reverse", False)

        # корректный выбор рынка для детального сообщения
        reversed_market = primary_tuple[2] if reverse else primary_tuple[3]
        primary_html = create_message_to_futures(primary_tuple, reversed_market, coin_cap)

        if not others:
            return primary_html

        lines = []
        for other_entry in others:
            ln = _compact_line_for_futures(
                other_entry["tuple"],
                reverse=other_entry.get("reverse", False)
            )
            if ln:
                lines.append(ln)

        compact_block = "━━━━━━━━━━━━━━━\n" + "\n".join(lines) + "\n━━━━━━━━━━━━━━━"
        return primary_html + "\n" + compact_block

    except Exception as e:
        print(f"[aggregate futures error] {e}")
        return create_message_to_futures(primary_entry["tuple"], primary_entry["tuple"][3], coin_cap)

def _format_pair(left: str, right: str, max_len: int = 14, width: int = 15) -> str:
    pair = f"{left}/{right}"
    if len(pair) > max_len:
        # делим место между двумя именами
        half = (max_len - 1) // 2  # -1 потому что '/'
        left = left[:half]
        right = right[:half]
        pair = f"{left}/{right}"
    return pair.ljust(width)


def _compact_line_for_futures(entry_tuple, reverse: bool = False) -> str:
    """
    Краткая строка для фьючерсных связок с выравниванием:
    <code>Bybit/Binance        +0.24%  ⚡0.012%</code>
    """
    try:
        long_ex = str(entry_tuple[3]) if not reverse else str(entry_tuple[2])
        short_ex = str(entry_tuple[2]) if not reverse else str(entry_tuple[3])
        # --- Спред ---
        try:
            if not reverse:
                entry_spread = round(((float(entry_tuple[8]) / float(entry_tuple[20])) - 1) * 100, 2)
            else:
                entry_spread = round(((float(entry_tuple[9]) / float(entry_tuple[19])) - 1) * 100, 2)
        except Exception:
            entry_spread = None

        # --- Funding ---
        try:
            f_long = float(entry_tuple[4] or 0)
            f_short = float(entry_tuple[5] or 0)
            funding_diff = round((f_long - f_short) if not reverse else (f_short - f_long), 3)
        except Exception:
            funding_diff = 0.0

        parts = []
        if entry_spread is not None:
            parts.append(f"{entry_spread:+.1f}%")
        parts.append(f"⚡{funding_diff}%")

        # --- Выравнивание бирж ---
        pair_text = _format_pair(long_ex, short_ex, max_len=14, width=15)
        return f"<code>{pair_text}{'  '.join(parts)}</code>"

    except Exception as e:
        print(f"[compact futures error] {e}")
        return ""

def _compact_line_for_spot(entry_tuple) -> str:
    """
    Краткая строка для спот-связок с выравниванием:
    <code>Bybit/Binance        +0.2%  ⚡0.012%</code>
    """
    try:
        buy_ex = str(entry_tuple[2])
        short_ex = str(entry_tuple[3])

        try:
            entry_spread = round(((float(entry_tuple[6]) / float(entry_tuple[16])) - 1) * 100, 2)
        except Exception:
            entry_spread = None

        try:
            raw_val = entry_tuple[4]
            funding = round(float(raw_val), 3) if raw_val not in (None, '') else 0.0
        except Exception:
            funding = 0.0

        parts = []
        if entry_spread is not None:
            parts.append(f"{entry_spread:+.1f}%")
        parts.append(f"⚡{funding}%")

        pair_text = _format_pair(buy_ex, short_ex, max_len=14, width=15)
        return f"<code>{pair_text}{'  '.join(parts)}</code>"

    except Exception as e:
        print(f"[compact spot error] {e}")
        return ""

def _compact_line_for_dex(entry_tuple) -> str:
    """
    Краткая строка для DEX-связок с выравниванием:
    <code>DEX/Binance          +0.3%  ⚡0.01%</code>
    """
    try:
        dex_ex = str(entry_tuple[2])
        cex_ex = str(entry_tuple[3])

        try:
            diff = round(float(entry_tuple[6]), 3)
        except Exception:
            diff = None

        try:
            raw_val = entry_tuple[13] if len(entry_tuple) > 13 else None
            funding = round(float(raw_val), 3) if raw_val not in (None, '') else 0.0
        except Exception:
            funding = 0.0

        parts = []
        if diff is not None:
            parts.append(f"{diff:+.1f}%")
        parts.append(f"⚡{funding}%")

        pair_text = _format_pair(dex_ex, cex_ex, max_len=14, width=15)
        return f"<code>{pair_text}{'  '.join(parts)}</code>"

    except Exception as e:
        print(f"[compact dex error] {e}")
        return ""


def _select_best_primary(entries: List[Dict[str, Any]], notif_type: str) -> int:
    """
    Попытка выбрать 'best' primary среди entries (list of dicts with 'tuple').
    Возвращает индекс best; fallback -> 0.
    Логика: пытаемся извлечь числовую метрику (abs spread) или объем и взять максимум.
    Это best-effort — если поля отсутствуют, вернёт 0.
    """
    best_i = 0
    best_score = -1.0
    for i, e in enumerate(entries):
        t = e.get("tuple")
        score = 0.0
        try:
            if notif_type == "spread":
                # несколько попыток вычислить текущий спред
                # try index 14 (used in create_message_to_futures), else diff between two percents
                try:
                    val = float(t[14])
                    score = abs(val)
                except Exception:
                    try:
                        # try difference between positions 4 and 5
                        score = abs(float(t[4]) - float(t[5]))
                    except Exception:
                        score = 0.0
                # prefer also big volumes (29/30)
                try:
                    vol = max(float(t[29] or 0), float(t[30] or 0))
                    score += min(vol / 10000.0, 100.0)  # scale down
                except Exception:
                    pass

            elif notif_type == "spot":
                # try to use current percent at index 4 (as in create_message_to_spot)
                try:
                    score = abs(float(t[4]))
                except Exception:
                    score = 0.0
                try:
                    vol = float(t[21] or 0)
                    score += min(vol / 10000.0, 100.0)
                except Exception:
                    pass

            elif notif_type == "dex":
                # use diff (index 6) and volume (9/10)
                try:
                    score = abs(float(t[6]))
                except Exception:
                    score = 0.0
                try:
                    vol = max(float(t[9] or 0), float(t[10] or 0))
                    score += min(vol / 10000.0, 100.0)
                except Exception:
                    pass

        except Exception:
            score = 0.0

        if score > best_score:
            best_score = score
            best_i = i

    return best_i


def create_aggregated_message_to_spot(primary_tuple, others: List[Tuple], coin_cap) -> str:
    """
    primary_tuple — детальный блок (reuse create_message_to_spot)
    others — list of tuples — компактные строки под ним.
    """
    try:
        primary_html = create_message_to_spot(primary_tuple, coin_cap)

        if not others:
            return primary_html

        lines = []
        for other in others:
            ln = _compact_line_for_spot(other)
            if ln:
                lines.append(ln)

        compact_block = "━━━━━━━━━━━━━━━\n" + "\n".join(lines) + "\n━━━━━━━━━━━━━━━"

        return primary_html + "\n" + compact_block
    except Exception:
        return create_message_to_spot(primary_tuple, coin_cap)


def create_aggregated_message_to_dex(primary_tuple, others: List[Tuple]) -> str:
    """
    primary_tuple — детальный блок (reuse create_message_to_dex)
    others — list of tuples — компактные строки под ним.
    """
    try:
        primary_html = create_message_to_dex(primary_tuple)

        if not others:
            return primary_html

        lines = []
        for other in others:
            ln = _compact_line_for_dex(other)
            if ln:
                lines.append(ln)

        compact_block = "━━━━━━━━━━━━━━━\n" + "\n".join(lines) + "\n━━━━━━━━━━━━━━━"

        return primary_html + "\n" + compact_block
    except Exception:
        return create_message_to_dex(primary_tuple)


async def _create_redis(db_index: int, redis_url: str) -> aioredis.Redis:
    # создаём redis клиент для конкретного DB
    # redis_url может быть "redis://host:port"
    # redis-py позволяет передать db при создании клиента
    return aioredis.Redis.from_url(redis_url, db=db_index, decode_responses=False)


async def _try_atomic_rename(r: aioredis.Redis, src: str, dst: str) -> Optional[bool]:
    """
    Переименовывает src -> dst, если src существует.
    Возвращает:
      True  — если переименование успешно
      None  — если src не существует
      False — если произошла ошибка
    """
    try:
        exists = await r.exists(src)
        if not exists:
            return None  # нет данных — это нормально, не ошибка

        await r.rename(src, dst)
        return True

    except aioredis.exceptions.ResponseError:
        # src не существует (гонка) — просто пропустим
        return None
    except Exception as e:
        print(f"[rename error] {src} -> {dst}: {e}")
        return False


async def _drain_list_to_python(r: aioredis.Redis, key: str) -> List[bytes]:
    """
    Считывает все элементы списка key (LRANGE 0 -1) и возвращает как list[bytes].
    Потом удаляет список (DEL).
    Предполагается, что ключ уже переименован в временный.
    """
    # читаем все элементы
    items = await r.lrange(key, 0, -1)  # возвращает list[bytes] (decode_responses=False)
    # удаляем ключ
    await r.delete(key)
    return items


async def dedupe_check_and_add_local(tgid: str, key: str, now_ts: float = None) -> bool:
    """
    Возвращает True — если ключ новый (т.е. можно отправлять), и сразу добавляет запись.
    False — если уже был.
    Делает ленивую очистку старых записей.
    """
    if now_ts is None:
        now_ts = time.time()
    async with _dedupe_lock:
        m = _dedupe_map.get(tgid)
        if m is None:
            m = {}
            _dedupe_map[tgid] = m

        # очистка старых
        # (оптимизация: очищаем иногда — если len > threshold or random chance)
        if len(m) > 0:
            # лениво: удаляем только старые
            to_del = [k for k, ts in m.items() if now_ts - ts > DEDUP_TTL]
            for k in to_del:
                del m[k]

        if key in m:
            return False

        # вставляем
        m[key] = now_ts

        # держим bounded размер
        if len(m) > MAX_DEDUP_PER_USER:
            # удаляем самый старый
            oldest = min(m.items(), key=lambda it: it[1])[0]
            del m[oldest]

        return True


def _parse_json_bytes(b: bytes) -> Optional[Dict[str, Any]]:
    try:
        # b может быть bytes или str depending on decode_responses
        if isinstance(b, bytes):
            s = b.decode("utf-8")
        else:
            s = str(b)
        return json.loads(s)
    except Exception:
        return None


async def scan_notifications_once(
    redis_url: str,
    *,
    max_per_user: int = 15,
    batch_suffix_prefix: str = "processing",
    log_func: Callable[[str], None] = lambda s: None,
) -> Dict[str, int]:
    """
    Один проход обработки уведомлений из трёх Redis-баз:
      db0 → Notifications:Spreads  (Spread/Futures)
      db1 → Notifications:SpotFutures  (Spot-Futures)
      db2 → Notifications:Dex  (DEX)
    """

    stats = {"spread": 0, "spot": 0, "dex": 0}

    # Соответствие DB → ключ и тип уведомлений
    db_map = {
        0: {"key": "Notifications:Spreads", "type": "spread"},
        1: {"key": "Notifications:SpotFutures", "type": "spot"},
        2: {"key": "Notifications:Dex", "type": "dex"},
    }

    # Клиенты Redis
    redis_clients: Dict[int, aioredis.Redis] = {}
    transfers: List[Tuple[int, List[bytes]]] = []

    try:
        # --- 1. Создаём клиентов ---
        for db_index in db_map.keys():
            redis_clients[db_index] = await _create_redis(db_index, redis_url)

        # --- 2. Переносим и читаем списки из каждой DB ---
        for db_index, info in db_map.items():
            key = info["key"]
            client = redis_clients[db_index]
            tmp_key = f"{key}:{batch_suffix_prefix}:{uuid.uuid4().hex}"

            renamed = await _try_atomic_rename(client, key, tmp_key)

            if renamed is True:
                # Переименовано → читаем
                items = await _drain_list_to_python(client, tmp_key)
                if items:
                    transfers.append((db_index, items))

        # --- 3. Обрабатываем уведомления из каждой DB ---

        for db_index, items in transfers:
            notif_type = db_map[db_index]["type"]
          #  logger.info(f"Processing DB{db_index} ({notif_type}) with {len(items)} notifications")

            # --- new grouping approach ---
            # groups: tgid -> coin_key -> list of dicts { 'parsed': parsed, 'tuple': tuple, 'raw': raw, 'reverse': reverse, 'type': notif_type }
            groups: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

            for raw in items:
                parsed = _parse_json_bytes(raw)
                if not parsed:
                    continue
                try:
                    tgid = str(parsed.get("tgid", ""))
                    if not tgid:
                        continue

                    if db_index == 0:  # spread / futures
                        reverse = bool(parsed.get("reverse", False))

                        spread_tuple = parse_spread(parsed)
                        if not spread_tuple:
                            continue
                        coin = str(spread_tuple[1]).upper()
                        groups[tgid][coin].append({
                            "parsed": parsed,
                            "tuple": spread_tuple,
                            "reverse": reverse,
                            "db_index": db_index
                        })

                    elif db_index == 1:  # spot-futures
                        sf_tuple = parse_spotfuture(parsed)
                        if not sf_tuple:
                            continue
                        coin = str(sf_tuple[1]).upper()
                        groups[tgid][coin].append({
                            "parsed": parsed,
                            "tuple": sf_tuple,
                            "db_index": db_index
                        })

                    elif db_index == 2:  # dex
                        dex_tuple = parse_dex(parsed)
                        if not dex_tuple:
                            continue
                        # symbol in dex is like CHAIN_SYMBOL -> sort by full string
                        coin = str(dex_tuple[1]).upper()
                        groups[tgid][coin].append({
                            "parsed": parsed,
                            "tuple": dex_tuple,
                            "db_index": db_index
                        })

                except Exception as e:
                    log_func(f"[Grouping] DB{db_index} error: {e}")
                    continue

            # Теперь обходим собранные группы и формируем агрегированное сообщение для каждой (tgid, coin)
            for tgid, coins_map in groups.items():
                for coin, entries in coins_map.items():
                    # primary — первый элемент, others — остальные
                    best_i = _select_best_primary(entries, notif_type)
                    primary_entry = entries[best_i]
                    primary_tuple = primary_entry["tuple"]

                    if db_index == 0:
                        others = [e for idx, e in enumerate(entries) if idx != best_i]
                    else:
                        others = [e["tuple"] for idx, e in enumerate(entries) if idx != best_i]
                    # также получаем parsed/flags для primary:
                    primary_parsed_entry = entries[best_i]

                    # формируем dedup key — один чек на всю группу, чтобы не послать кучу сообщений за одну и ту же монету
                    # Используем coin + type (spread/spot/dex) — можно дополнительно включить sorted markets если нужно
                    dedup_key = f"{coin}|{notif_type}"
                    ok = await dedupe_check_and_add_local(tgid, dedup_key)
                    if not ok:
                        continue

                    # Создаём сообщение в зависимости от типа
                    if db_index == 0:
                        message_text = create_aggregated_message_to_futures(primary_entry, others, coin_cap)
                        # кнопки — по первичному (reuse existing builder)
                        reversed_primary = entries[0].get("reverse", False)
                        if reversed_primary:
                            callback = f"market_id_reload:id0_{entries[0]['parsed'].get('market1')}_{entries[0]['parsed'].get('market2')}_{primary_tuple[1]}"
                        else:
                            callback = f"market_id_reload:id0_{entries[0]['parsed'].get('market2')}_{entries[0]['parsed'].get('market1')}_{primary_tuple[1]}"
                        button_graphic = add_inline_button_graphic(primary_tuple, primary_tuple[3])
                        inline_kb = InlineKeyboardBuilder().row(
                            InlineKeyboardButton(text="Обновить", callback_data=callback),
                            button_graphic,
                        )

                        async with send_list_lock:
                            user_queue = send_list.setdefault(tgid, {"send": [], "sleep": 0})
                            if len(user_queue["send"]) < max_per_user:
                                user_queue["send"].append((tgid, message_text, inline_kb.as_markup()))
                                stats["spread"] += 1

                    elif db_index == 1:
                        message_text = create_aggregated_message_to_spot(primary_tuple, others, coin_cap)
                        button_graphic = add_inline_button_graphic_spot(primary_tuple)
                        inline_kb = InlineKeyboardBuilder().row(
                            InlineKeyboardButton(
                                text="Обновить",
                                callback_data=f"spot_id_reload:spotid0_{primary_tuple[2]}_{primary_tuple[3]}_{primary_tuple[1]}",
                            ),
                            button_graphic,
                        )
                        async with send_list_lock:
                            user_queue = send_list.setdefault(tgid, {"send": [], "sleep": 0})
                            if len(user_queue["send"]) < max_per_user:
                                user_queue["send"].append((tgid, message_text, inline_kb.as_markup()))
                                stats["spot"] += 1

                    elif db_index == 2:
                        message_text = create_aggregated_message_to_dex(primary_tuple, others)
                        back_btn = InlineKeyboardButton(
                            text="Назад", callback_data=f"dex_market:in:{primary_tuple[1]}:0"
                        )
                        graph_btn = add_inline_button_graphic_dex(primary_tuple[3], primary_tuple[1].replace("USDT", ""))
                        inline_kb = (
                            InlineKeyboardBuilder()
                            .row(
                                InlineKeyboardButton(
                                    text="Обновить",
                                    callback_data=f"dex_pair_update:in:{primary_tuple[1]}:{primary_tuple[3]}:0",
                                ),
                                graph_btn,
                            )
                            .row(back_btn)
                        )
                        async with send_list_lock:
                            user_queue = send_list.setdefault(tgid, {"send": [], "sleep": 0})
                            if len(user_queue["send"]) < max_per_user:
                                user_queue["send"].append((tgid, message_text, inline_kb.as_markup()))
                                stats["dex"] += 1


    finally:
        # --- 4. Закрываем все Redis-клиенты ---
        for client in redis_clients.values():
            try:
                await client.close()
            except Exception:
                pass

    return stats


async def _ensure_trigger_worker(redis_url: str, log_func = lambda s: None):
    global _scan_trigger_q, _scan_worker_task
    if _scan_trigger_q is None:
        _scan_trigger_q = asyncio.Queue()
    if _scan_worker_task is None or _scan_worker_task.done():
        async def _worker():
            while True:
                try:
                    await _scan_trigger_q.get()
                    try:
                        await scan_notifications_once(redis_url, log_func=log_func)
                    except Exception as e:
                        log_func(f"[scan worker] error: {e}")
                    # коалесцируем последующие триггеры
                    while True:
                        try:
                            _scan_trigger_q.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    await asyncio.sleep(0)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log_func(f"[scan worker] unexpected: {e}")
                    await asyncio.sleep(0.1)
        _scan_worker_task = asyncio.create_task(_worker())

async def _enqueue_scan_trigger():
    global _scan_trigger_q
    if _scan_trigger_q is None:
        return
    try:
        _scan_trigger_q.put_nowait(1)
    except asyncio.QueueFull:
        pass

async def _pubsub_single_channel(redis_url: str, channel: str, log_func = lambda s: None):
    r = await _create_redis(0, redis_url)  # подписываемся в DB0
    try:
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        log_func(f"[pubsub] subscribed to {channel} (DB0)")
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=10.0)
            if msg is None:
                await asyncio.sleep(0)  # yield
                continue
            # получили publish — ставим триггер
            log_func(f"[pubsub] message on {channel}")
            await _enqueue_scan_trigger()
    except asyncio.CancelledError:
        try:
            await pubsub.unsubscribe(channel)
        except Exception:
            pass
        raise
    except Exception as e:
        log_func(f"[pubsub] error: {e}")
    finally:
        try:
            await r.close()
        except Exception:
            pass

async def start_notifications_listener(redis_url: str, *, log_func = lambda s: None):
    await _ensure_trigger_worker(redis_url, log_func=log_func)
    reader_task = asyncio.create_task(_pubsub_single_channel(redis_url, "NotificationsPub:Flush", log_func=log_func))
    try:
        await reader_task
    except asyncio.CancelledError:
        reader_task.cancel()
        await asyncio.gather(reader_task, return_exceptions=True)
        if _scan_worker_task:
            _scan_worker_task.cancel()
            await asyncio.gather(_scan_worker_task, return_exceptions=True)
        raise

async def start_bot_func(dispatcher):
   # asyncio.create_task(start_bot_search())
    asyncio.create_task(go_send_list())
    asyncio.create_task(start_check_paid())
    asyncio.create_task(start_notifications_listener(REDIS_ADDR, log_func=logger.info))


@dp.message(F.text == 'Тестовый период')
async def test_start(message: types.Message):
    print(message.from_user.id, ' - ', message.from_user.username, ' - ', 'TEST start')
    await bot.send_message(ADMIN_ID, f"{message.from_user.id} - {message.from_user.username} - TEST",
                           parse_mode='HTML')
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE
    )
    cursor = connection.cursor()
    cursor.execute('''SELECT * FROM Users''')
    accounts = cursor.fetchall()

    # 1. Инлайн кнопки
    paid_inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [button_subscription_web, button_info_web],
    ])

    kb = [[button_spreads, button_spot],
          [button_blacklist, button_marketslist],
          [button_dex, button_monitoring]]
    greet_kb1 = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=False)
    for acc in accounts:
        if str(acc[2]) == str(message.from_user.id):
            timetest = acc[13]
            if timetest == 'no':
                data_send = datetime.datetime.isoformat(datetime.datetime.now())
                cursor.execute('''UPDATE Users SET timeTest=%s, testActive=%s WHERE tgid=%s''',
                               (data_send, 1, acc[2]))
                connection.commit()
                connection.close()
                test_started_msg = (
                    "✅ Вы успешно активировали тестовый доступ!\n\n"
                    "В течение 6 часов вам будут доступны все функции бота. "
                    "Если возникнут вопросы — смело обращайтесь в поддержку."
                )
                await message.answer(test_started_msg, reply_markup=greet_kb1, parse_mode='HTML')
            if timetest != 'no':
                await message.answer("⚠️ Вы уже использовали тестовый период.\n\n"
                                    "Для продолжения работы, пожалуйста, оформите подписку.", reply_markup=paid_inline_kb, parse_mode='HTML')


@dp.message(F.text == 'Список оплаты')
async def list_of_paids(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()

        cursor.execute('''SELECT * FROM Paids''')
        paids = cursor.fetchall()
        paids.reverse()
        new_message = 'Поступления:\n'
        if len(paids) > 0:
            counter = -1
            for paid in paids:
                counter += 1
                new_message += f'{paid[2]} - {paid[3]} - {paid[5]} - {paid[6]}\n'
                if counter > 10:
                    await message.answer(text=new_message)
                    new_message = ''
                    counter = -1
                    await asyncio.sleep(0.2)
            if counter <= 10:
                await message.answer(text=new_message)


        cursor.execute('''SELECT * FROM Users''')
        accounts = cursor.fetchall()
        connection.close()
        new_message = 'Аккаунты:\n'
        counter = -1
        counter2 = 0
        for acc in accounts:
            counter += 1
            counter2 += 1
            timeAdmin = 'no'
            if acc[11] != 'no':
                timeAdmin = acc[11].split('.')[0]
            timeTest = 'no'
            if acc[13] != 'no':
                timeTest = acc[13].split('.')[0]
            new_message += f'{counter2}){acc[1]}({acc[2]}) - {acc[9]} < {acc[10]} - {timeAdmin} >< {timeTest} - {acc[14]} > {acc[15]} - {acc[17]}\n'
            if counter > 10:
                await message.answer(text=new_message)
                new_message = ''
                counter = -1
                await asyncio.sleep(0.2)
        if counter <= 10:
            await message.answer(text=new_message)


@dp.message(F.text == 'Список активных')
async def list_of_paids(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()

        cursor.execute('''SELECT * FROM Paids''')
        paids = cursor.fetchall()
        paids.reverse()
        new_message = 'Поступления:\n'
        if len(paids) > 0:
            counter = -1
            for paid in paids:
                counter += 1
                new_message += f'{paid[2]} - {paid[3]} - {paid[5]} - {paid[6]}\n'
                if counter > 10:
                    await message.answer(text=new_message)
                    new_message = ''
                    counter = -1
                    await asyncio.sleep(0.2)
            if counter <= 10:
                await message.answer(text=new_message)


        cursor.execute('''SELECT * FROM Users''')
        accounts = cursor.fetchall()
        connection.close()
        new_message = 'Аккаунты:\n'
        counter = -1
        counter2 = 0
        for acc in accounts:
            if any(x == '1' for x in [acc[9], acc[10], acc[14]]):
                counter += 1
                counter2 += 1
                timeAdmin = 'no'
                if acc[11] != 'no':
                    timeAdmin = acc[11].split('.')[0]
                new_message += f'{counter2}){acc[1]}({acc[2]}) - {acc[9]} - {acc[10]} - {acc[14]} - {timeAdmin}\n'
            if counter > 10:
                await message.answer(text=new_message)
                new_message = ''
                counter = -1
                await asyncio.sleep(0.2)
        if counter <= 10:
            await message.answer(text=new_message)


@dp.message(AdminFunc.access) # Принимаем состояние
async def add_access(message: types.Message, state: FSMContext):
    print(message.text)

    # Клавиатура
    greet_kb = [[button_spreads, button_spot], [button_blacklist, button_marketslist], [button_dex, button_monitoring]]
    greet_kb1 = ReplyKeyboardMarkup(keyboard=greet_kb, resize_keyboard=True, one_time_keyboard=False)
    await state.clear()
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE
    )
    cursor = connection.cursor()
    cursor.execute('''SELECT * FROM Users''')
    accounts = cursor.fetchall()
    for acc in accounts:
        if acc[2] == message.text:
            timeActive = datetime.datetime.isoformat(datetime.datetime.now())
            cursor.execute('''UPDATE Users SET isActiveAdmin=%s, timeActiveAdmin=%s WHERE tgid=%s''',
                           (1, timeActive, acc[2]))
            connection.commit()
            await message.answer(text='Готово')
            creating_message = (
                "🎉 <b>Подписка активирована!</b>\n\n"
                "Теперь вам доступны все функции бота.\n"
                "Если возникнут вопросы — поддержка всегда на связи.\n"
                "Приятной работы! ✅"
            )
            await bot.send_message(acc[2], creating_message, reply_markup=greet_kb1,
                                   parse_mode='HTML')
            break

    connection.close()


@dp.message(AdminFunc.off_access) # Принимаем состояние
async def off_access(message: types.Message, state: FSMContext):
    print(message.text)
    await state.clear()
    # 1. Инлайн кнопки
    paid_inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [button_subscription_web, button_info_web],
    ])
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE
    )
    cursor = connection.cursor()
    cursor.execute('''SELECT * FROM Users''')
    accounts = cursor.fetchall()
    for acc in accounts:
        if acc[2] == message.text:
            timeActive = datetime.datetime.isoformat(datetime.datetime.now())
            cursor.execute('''UPDATE Users SET isActiveAdmin=%s, testActive=%s WHERE tgid=%s''',
                           (0, 0, acc[2]))
            connection.commit()

            await message.answer(text='Готово')
            creating_message = (
                "⚠️ <b>Подписка завершена.</b>\n\n"
                "Доступ к функциям бота ограничен."
            )
            await bot.send_message(acc[2], creating_message, reply_markup=ReplyKeyboardRemove(),
                                   parse_mode='HTML')
            creating_message_2 = (
                "📌 Чтобы продолжить пользоваться ботом, пожалуйста, оформите подписку."
            )
            await bot.send_message(acc[2], creating_message_2, reply_markup=paid_inline_kb, parse_mode='HTML')

            break
    connection.close()


@dp.message(AdminFunc.reset_access) # Принимаем состояние
async def reset_access(message: types.Message, state: FSMContext):
    print(message.text)
    await state.clear()

    # 1. Инлайн кнопки
    paid_inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [button_subscription_web, button_info_web],
    ])

    connection = mysql.connector.connect(
        host=DB_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE
    )
    cursor = connection.cursor()
    cursor.execute('''SELECT * FROM Users''')
    accounts = cursor.fetchall()
    for acc in accounts:
        if acc[2] == message.text:
            timeActive = datetime.datetime.isoformat(datetime.datetime.now())
            cursor.execute('''UPDATE Users SET isActiveAdmin=%s, timeActiveAdmin=%s WHERE tgid=%s''',
                           (2, timeActive, acc[2]))
            connection.commit()

            await message.answer(text='Готово')
            creating_message = (
                "⚠️ <b>Подписка завершена.</b>\n\n"
            "Доступ к функциям бота ограничен."
            )
            await bot.send_message(acc[2], creating_message, reply_markup=ReplyKeyboardRemove(),
                                   parse_mode='HTML')
            creating_message_2 = (
                "📌 Чтобы продолжить пользоваться ботом, пожалуйста, оформите подписку."
            )
            await bot.send_message(acc[2], creating_message_2, reply_markup=paid_inline_kb, parse_mode='HTML')

            break

    connection.close()


@dp.message(F.text == 'Админ панель')
async def admin_panel_func(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        kb = [[button_start, button_list_active],
              [button_list_paids, button_add_active],
              [button_off_active, button_reset_active]]
        greet_kb1 = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=False)
        await message.answer(text='Готово', reply_markup=greet_kb1)


@dp.message(F.text == 'Дать доступ')
async def add_access_start(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await message.answer(text='Дать доступ, введите: tgid')
        await state.set_state(AdminFunc.access)


@dp.message(F.text == 'Убрать доступ')
async def off_address_start(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await message.answer(text='Убрать доступ, введите: tgid')
        await state.set_state(AdminFunc.off_access)


@dp.message(F.text == 'Сбросить доступ')
async def reset_address_start(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await message.answer(text='Сбросить доступ, введите: tgid')
        await state.set_state(AdminFunc.reset_access)


@dp.message(F.text == 'Информация')
async def get_button_info(message: types.Message):
    user = message.from_user
    name = user.first_name or user.username or "друг"

    # 1. Инлайн кнопки
    paid_inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [button_subscription_web, button_info_web],
    ])

    # 3. Приветствие
    text_active = f"👋 Привет, <b>{name}</b>!\n\n<i>Ваша подписка активна ✅</i>"
    text_inactive = f"👋 Привет, <b>{name}</b>!\n\n<i>У вас нет активной подписки</i>"

    print(message.from_user.id, ' - ', message.from_user.username, ' - ', 'Information')
    kb_admin = [[button_admin_panel],
                [button_spreads, button_spot],
          [button_blacklist, button_marketslist],
          [button_dex, button_monitoring]]
    kb = [[button_spreads, button_spot],
          [button_blacklist, button_marketslist],
          [button_dex, button_monitoring]]
    kbp = []
    # kbp_admin = [[button_admin_panel],
    #             [button_start_test]]
    kbp_admin = []
    greet_kb1 = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=False)
    admin_kb1 = ReplyKeyboardMarkup(keyboard=kb_admin, resize_keyboard=True, one_time_keyboard=False)
    if message.from_user.id == ADMIN_ID:
        paid_kb1 = ReplyKeyboardMarkup(keyboard=kbp_admin, resize_keyboard=True, one_time_keyboard=False)
    else:
        paid_kb1 = ReplyKeyboardMarkup(keyboard=kbp, resize_keyboard=True, one_time_keyboard=False)
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE
    )
    cursor = connection.cursor()
    cursor.execute('''SELECT * FROM Users''')
    accounts = cursor.fetchall()
    connection.close()
    if len(accounts) > 0:
        for acc in accounts:
            if str(acc[2]) == str(message.from_user.id):
                if acc[10] == '1':
                    if message.from_user.id == ADMIN_ID:
                        await message.answer(text_active, reply_markup=admin_kb1, parse_mode="HTML")
                    else:
                        await message.answer(text_active, reply_markup=greet_kb1, parse_mode="HTML")
                elif acc[9] == '1' and acc[10] == '2':
                    if message.from_user.id == ADMIN_ID:
                        await message.answer(text_active, reply_markup=admin_kb1, parse_mode="HTML")
                    else:
                        await message.answer(text_active, reply_markup=greet_kb1, parse_mode="HTML")
                elif (acc[9] == '0' and acc[10] == '2') or (acc[10] == '0'):
                    # 4. Сначала отправляем сообщение с relpy-клавиатурой
                    await message.answer(text_inactive, reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
                    # 5. Затем отправляем inline-кнопки
                    await message.answer(
                        "📌 Чтобы начать работу — выберите нужный раздел снизу.",
                        reply_markup=paid_inline_kb, parse_mode='HTML')


async def start_check_paid():
    global bot

    print('StartChecking')

    # 1. Инлайн кнопки
    paid_inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [button_subscription_web, button_info_web],
    ])

    kb = [[button_spreads, button_spot],
          [button_blacklist, button_marketslist],
          [button_dex, button_monitoring]]
    kbp = []
    greet_kb1 = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=False)
    paid_kb1 = ReplyKeyboardMarkup(keyboard=kbp, resize_keyboard=True, one_time_keyboard=False)
    connection = None

    while True:
        try:
            connection = mysql.connector.connect(
                host=DB_HOST,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE
            )
            cursor = connection.cursor()
            cursor.execute('''SELECT * FROM Users''')
            accounts = cursor.fetchall()
            accounts_list = []
            for acc in accounts:
                accounts_list.append(list(acc))
            cursor.execute('''SELECT * FROM Paids''')
            paids = cursor.fetchall()

            for acc in accounts_list:
                if acc[14] == '1' and acc[10] != '1':
                    if acc[13] != 'no':
                        testtime = datetime.datetime.fromisoformat(acc[13])
                        cur_time = datetime.datetime.now()
                        spend_time = cur_time - testtime
                        if spend_time.total_seconds() > 21600:  # 6 часов
                            cursor.execute('''UPDATE Users SET testActive=%s WHERE tgid=%s''',
                                           (0, acc[2]))
                            connection.commit()
                            creating_message = (
                                "⏳ Тестовый период завершён.\n\n"
                                "Чтобы продолжить пользоваться ботом — оформите подписку.\n"
                                "Если возникнут вопросы — поддержка всегда на связи."
                            )
                            try:

                                await bot.send_message(acc[2], "\u2063", reply_markup=ReplyKeyboardRemove())
                                await asyncio.sleep(0.1)
                                await bot.send_message(acc[2], creating_message, reply_markup=paid_inline_kb, parse_mode='HTML')
                            except aiogram.exceptions.TelegramForbiddenError:
                                print('checking1 Error Forbidden by', acc[2])
                memoAcc = acc[17]
                if len(paids) > 0:
                    if acc[9] == '0':
                        paids_data = []
                        for paid in paids:
                            if memoAcc == paid[5]:
                                paids_data.append(paid)
                        if len(paids_data) > 0:
                            successPaid = False
                            for pd in paids_data:
                                data_paid = datetime.datetime.fromisoformat(pd[4])
                                inusdt = pd[6]
                                current_time = datetime.datetime.now()
                                count_days = current_time - data_paid
                                if float(inusdt) > 19.5 and count_days.days < 32:
                                    successPaid = True
                            if successPaid:
                                acc[9] = 1
                                cursor.execute('''UPDATE Users SET isActive=%s WHERE tgid=%s''',
                                               (1, acc[2]))
                                connection.commit()
                                creating_message = 'Оплата прошла успешно'
                                try:
                                    await bot.send_message(acc[2], creating_message, reply_markup=greet_kb1,
                                                           parse_mode='HTML')
                                except aiogram.exceptions.TelegramForbiddenError:
                                    print('checkingpaid Error Forbidden by', acc[2])
                    if acc[9] == '1':
                        paids_data = []
                        for paid in paids:
                            if memoAcc == paid[5]:
                                paids_data.append(paid)
                        if len(paids_data) > 0:
                            isAvailable = False
                            for pd in paids_data:
                                data_paid = datetime.datetime.fromisoformat(pd[4])
                                inusdt = pd[6]
                                current_time = datetime.datetime.now()
                                count_days = current_time - data_paid
                                if float(inusdt) > 19.5 and count_days.days < 32:
                                    isAvailable = True
                            if isAvailable is False:
                                acc[9] = 0
                                cursor.execute('''UPDATE Users SET isActive=%s WHERE tgid=%s''',
                                               (0, acc[2]))
                                connection.commit()
                                creating_message = 'Оплаченный период окончен'
                                try:
                                    await bot.send_message(acc[2], creating_message, reply_markup=paid_kb1,
                                                           parse_mode='HTML')
                                except aiogram.exceptions.TelegramForbiddenError:
                                    print('checking2 Error Forbidden by', acc[2])
        except Exception as e:
            print('checkingError', e)
            logging.exception('Checking ERROR')
        finally:
            try:
                if connection:
                    connection.close()
            except Exception as e:
                print('exception close conn', e)
        await asyncio.sleep(30)


send_list = {}

send_list_lock = asyncio.Lock()

def make_dedup_key(coin: str, m1: str, m2: str, ignore_direction: bool = True) -> str:
    c = (coin or "").strip().upper()
    a = (m1 or "").strip().upper()
    b = (m2 or "").strip().upper()
    if ignore_direction:
        if a > b:
            a, b = b, a
    return f"{c}|{a}|{b}"


def reset_user_data_search(user_id):
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()
        # SQL-запрос на обновление поля dataSearch для пользователя с заданным user_id
        cursor.execute("UPDATE Users SET dataSearch = 'no' WHERE tgid = %s", (user_id,))
        connection.commit()  # сохраняем изменения в базе данных
        connection.close()   # закрываем соединение с базой данных
    except Exception as e:
        print(f"Error updating user dataSearch for user {user_id}: {e}")


async def send_message_async(user_id, message_text, reply_markup):
    try:
        await bot.send_message(user_id, message_text, reply_markup=reply_markup, parse_mode='HTML', disable_web_page_preview=True)

    except aiogram.exceptions.TelegramForbiddenError:
        print('reset Forbidden by:', user_id)
        reset_user_data_search(user_id)
    except Exception as e:
        print(f"Error sending message to user {user_id}: {e}")
        try:
            print(f"2Error sending message to user {user_id}: {e} {reply_markup}")
        except Exception as e:
            print(f"exception reply markup")

processing_users = set()


async def process_user_queue(user_id):
    try:
        first = True
        while True:
            async with send_list_lock:
                queue = send_list[user_id]['send']

            if not queue:
                break

            message_data = queue.pop(0)
            await send_message_async(*message_data)

            if not first:
                await asyncio.sleep(1.5)
            else:
                first = False

        # Очистка после завершения очереди
        async with send_list_lock:
            del send_list[user_id]
        processing_users.discard(user_id)

    except Exception as e:
        logging.exception(f'Exception in process_user_queue for {user_id}: {e}')
        processing_users.discard(user_id)


async def go_send_list():
    while True:
        try:
            async with send_list_lock:
                users = list(send_list.keys())

            for user_id in users:
                if user_id not in processing_users:
                    processing_users.add(user_id)
                    asyncio.create_task(process_user_queue(user_id))

            await asyncio.sleep(0.1)
        except Exception as e:
            print('Exception in go_send_list', e)
            logging.exception('go_send_list exception')


def load_blacklist(acc):
    try:
        if acc[8] == b'no':
            return set()
        decompressed = zlib.decompress(acc[8])
        coins_dict = orjson.loads(decompressed.decode('utf-8'))
        return set(coins_dict.keys())
    except Exception as e:
        print(f'Ошибка при разборе blacklist: {e}')
        return set()


# Лимиты
MAX_ENTRIES = 300              # Максимум записей
MAX_COMPRESSED_SIZE = 60000    # Максимум в байтах после сжатия
FOUR_HOURS_SECONDS = 4 * 60 * 60

# Очистка старых данных:
def clean_lastCoins(lastCoins):
    # Удалить старые по времени (старше 4 часов)
    now = datetime.datetime.now()
    lastCoins = {
        k: v for k, v in lastCoins.items()
        if (now - datetime.datetime.fromisoformat(v)).total_seconds() <= FOUR_HOURS_SECONDS
    }

    # Обрезать по количеству
    while len(lastCoins) > MAX_ENTRIES:
        oldest_key = min(lastCoins, key=lambda k: datetime.datetime.fromisoformat(lastCoins[k]))
        del lastCoins[oldest_key]

    # Проверка по размеру
    raw_json = orjson.dumps(lastCoins)
    compressed = zlib.compress(raw_json)
    while len(compressed) > MAX_COMPRESSED_SIZE and lastCoins:
        oldest_key = min(lastCoins, key=lambda k: datetime.datetime.fromisoformat(lastCoins[k]))
        del lastCoins[oldest_key]
        raw_json = orjson.dumps(lastCoins)
        compressed = zlib.compress(raw_json)

    return lastCoins, compressed


def handle_spread(spread, acc, lastCoins, dataSearch, blacklist):
    try:
        symbol = spread[1]
        if symbol in blacklist:
            return  # Монета в чёрном списке — пропускаем

        now = datetime.datetime.now()
        spread_threshold = float(dataSearch['spread']) if dataSearch.get('spread') and dataSearch['spread'] != 'no' else None
        course_threshold = float(dataSearch['course_spread']) if dataSearch.get('course_spread') and dataSearch['course_spread'] != 'no' else None

        # ==== Прямой вход ====
        spread_val = float(spread[14])
        course_val = check_spread_futures(spread)

        spread_ok = spread_threshold is not None and spread_val >= spread_threshold
        course_ok = course_threshold is not None and course_val >= course_threshold

        if spread_ok or course_ok:
            key = f'{spread[1]}_{spread[3]}_{spread[2]}_future'
            temp_data = lastCoins.get(key, 'None')
            goUpdate = temp_data == 'None' or (now - datetime.datetime.fromisoformat(temp_data)).total_seconds() > FOUR_HOURS_SECONDS

            if goUpdate:
                bot_message = spread
                button_graphic = add_inline_button_graphic(bot_message, spread[3])
                creating_message = create_message_to_futures(bot_message, spread[3], coin_cap)

                inline_kb1 = InlineKeyboardBuilder().row(
                    InlineKeyboardButton(
                        text='Обновить',
                        callback_data=f'id{spread[0]}_reload_{spread[3]}_{spread[2]}_{spread[1]}'
                    ),
                    button_graphic
                )

                with send_list_lock:
                    send_list.setdefault(acc[2], {'send': [], 'sleep': 0})
                    if len(send_list[acc[2]]['send']) < 10:
                        send_list[acc[2]]['send'].append((acc[2], creating_message, inline_kb1.as_markup()))
                        lastCoins[key] = now.isoformat()

        # ==== Обратный вход ====
        reversed_spread_val = float(spread[5]) - float(spread[4])
        reversed_course_val = check_spread_futures_reverse(spread)

        reversed_spread_ok = spread_threshold is not None and reversed_spread_val >= spread_threshold
        reversed_course_ok = course_threshold is not None and reversed_course_val >= course_threshold

        if reversed_spread_ok or reversed_course_ok:
            key_rev = f'{spread[1]}_{spread[2]}_{spread[3]}_future'
            temp_data_rev = lastCoins.get(key_rev, 'None')
            goUpdate_rev = temp_data_rev == 'None' or (now - datetime.datetime.fromisoformat(temp_data_rev)).total_seconds() > FOUR_HOURS_SECONDS

            if goUpdate_rev:
                bot_message = spread
                button_graphic = add_inline_button_graphic(bot_message, spread[2])
                creating_message = create_message_to_futures(bot_message, spread[2], coin_cap)

                inline_kb2 = InlineKeyboardBuilder().row(
                    InlineKeyboardButton(
                        text='Обновить',
                        callback_data=f'id{spread[0]}_reload_{spread[2]}_{spread[3]}_{spread[1]}'
                    ),
                    button_graphic
                )

                with send_list_lock:
                    send_list.setdefault(acc[2], {'send': [], 'sleep': 0})
                    if len(send_list[acc[2]]['send']) < 10:
                        send_list[acc[2]]['send'].append((acc[2], creating_message, inline_kb2.as_markup()))
                        lastCoins[key_rev] = now.isoformat()

    except Exception:
        logger.exception('handle_spread except')

def handle_spotfuture(sf, acc, lastCoins, dataSearch, blacklist):
    try:
        coin_name = sf[1]
        symbol = coin_name
        if symbol in blacklist:
            return
        # Условие триггера (как у тебя)
        cond1 = (dataSearch.get('course_spread') != 'no' and float(dataSearch.get('course_spread')) <= float(round(((float(sf[6]) / float(sf[16])) - 1) * 100, 2)))
        cond2 = (dataSearch.get('spread') != 'no' and float(dataSearch.get('spread')) <= float(sf[4]))
        if cond1 or cond2:
            bot_message = sf
            temp_key = f'{sf[1]}_{sf[2]}_{sf[3]}_spot'
            temp_data = lastCoins.get(temp_key, 'None')
            goUpdate = temp_data == 'None' or (datetime.datetime.now() - datetime.datetime.fromisoformat(temp_data)).total_seconds() > FOUR_HOURS_SECONDS
            if goUpdate:
                button_graphic_spot = add_inline_button_graphic_spot(bot_message)
                creating_message = create_message_to_spot(bot_message, coin_cap)

                inline_kb1 = InlineKeyboardBuilder().row(
                    InlineKeyboardButton(text='Обновить', callback_data=f'spot_id{sf[0]}_reload_{sf[2]}_{sf[3]}_{sf[1]}'),
                    button_graphic_spot
                )
                with send_list_lock:
                    send_list.setdefault(acc[2], {'send': [], 'sleep': 0})
                    if len(send_list[acc[2]]['send']) < 10:
                        send_list[acc[2]]['send'].append((acc[2], creating_message, inline_kb1.as_markup()))
                        lastCoins[temp_key] = datetime.datetime.now().isoformat()
    except Exception:
        logger.exception('handle_spotfuture except')


def handle_dex(d, acc, lastCoins, dataSearch, dex_blacklist):
    try:
        coin_name = d[1]
        sym_key = extract_token_key(coin_name)  # возвращает 'COINUSDT'
        # Проверяем только DEX-blacklist (set)
        try:
            if sym_key and isinstance(dex_blacklist, (set, list)):
                if sym_key in dex_blacklist:
                    return
        except Exception:
            pass

        # Включён ли DEX мониторинг
        if not dataSearch or (dataSearch.get('dex_diff_gt') == 'no' and dataSearch.get('dex_diff_lt') == 'no'):
            return

        diff_val = float(d[6] or 0)
        notify = False
        try:
            if dataSearch.get('dex_diff_gt') and dataSearch.get('dex_diff_gt') != 'no':
                threshold_gt = float(dataSearch.get('dex_diff_gt'))
                if diff_val > threshold_gt:
                    notify = True
        except Exception:
            pass
        try:
            if dataSearch.get('dex_diff_lt') and dataSearch.get('dex_diff_lt') != 'no':
                threshold_lt = float(dataSearch.get('dex_diff_lt'))
                if diff_val < threshold_lt:
                    notify = True
        except Exception:
            pass

        if not notify:
            return

        temp_key = f'{d[1]}_{d[2]}_{d[3]}_dex'
        temp_data = lastCoins.get(temp_key, 'None')
        goUpdate = temp_data == 'None' or (datetime.datetime.now() - datetime.datetime.fromisoformat(temp_data)).total_seconds() > FOUR_HOURS_SECONDS
        if goUpdate:
            bot_message = d
            creating_message = create_message_to_dex(bot_message)
            back_btn = types.InlineKeyboardButton(text="Назад", callback_data=f'dex_market:in:{bot_message[1]}:0')
            to_graph_sym = copy(d[1])
            graph_btn = add_inline_button_graphic_dex(d[3], to_graph_sym.replace('USDT', ''))
            inline_kb1 = InlineKeyboardBuilder().row(
                InlineKeyboardButton(text='Обновить', callback_data=f'dex_pair_update:in:{bot_message[1]}:{bot_message[3]}:0'), graph_btn
            ).row(back_btn)

            with send_list_lock:
                send_list.setdefault(acc[2], {'send': [], 'sleep': 0})
                if len(send_list[acc[2]]['send']) < 10:
                    send_list[acc[2]]['send'].append((acc[2], creating_message, inline_kb1.as_markup()))
                    lastCoins[temp_key] = datetime.datetime.now().isoformat()
    except Exception:
        logger.exception('handle_dex except')


def parse_last_coins(raw_last_notice):
    try:
        return {} if raw_last_notice == b'no' else orjson.loads(zlib.decompress(raw_last_notice).decode('utf-8'))
    except Exception as e:
        logger.exception(f"Ошибка при загрузке lastNoticeCoins: {e}")
        return {}


def parse_market_dict(market_list):
    try:
        return {market.split('_')[0]: int(market.split('_')[1]) for market in orjson.loads(market_list)}
    except Exception as e:
        logger.exception(f"Ошибка в market_dict: {e}")
        return {}

def blob_to_bytes_safe(blob):
    """
    Привести значение acc[7] (lastNoticeCoins) к bytes для сравнения.
    Если blob is None или b'no' -> return None (означает "пусто").
    """
    try:
        if blob is None:
            return None
        if isinstance(blob, (bytes, bytearray)):
            if blob == b'no':
                return None
            return bytes(blob)
        if isinstance(blob, str):
            if blob.lower() in ('no', ''):
                return None
            # возможно это строка JSON (редко) — вернём её как bytes
            return blob.encode('utf-8')
        return None
    except Exception:
        return None


def process_accounts(connection, cursor, accounts, spreads, spotfutures, dex_records):
    """
    connection, cursor — созданные в start_bot_search.
    accounts — rows SELECT * FROM Users
    Обрабатываем каждого пользователя, обновляем lastCoins в памяти, затем
    делаем один UPDATE Users SET lastNoticeCoins=%s если compressed changed.
    """
    accounts_list = [list(acc) for acc in accounts if (acc[9] == '1' and acc[10] == '2') or acc[10] == '1' or acc[14] == '1']

    try:
        for acc in accounts_list:
            try:
                dataSearch = {} if acc[4] == 'no' else (orjson.loads(acc[4]) if isinstance(acc[4], str) else acc[4])
            except Exception:
                dataSearch = {}

            # Check monitoring flags
            has_monitoring = False
            if dataSearch and isinstance(dataSearch, dict):
                if dataSearch.get('spread') and dataSearch.get('spread') != 'no':
                    has_monitoring = True
                if dataSearch.get('course_spread') and dataSearch.get('course_spread') != 'no':
                    has_monitoring = True
                if dataSearch.get('dex_diff_gt') and dataSearch.get('dex_diff_gt') != 'no':
                    has_monitoring = True
                if dataSearch.get('dex_diff_lt') and dataSearch.get('dex_diff_lt') != 'no':
                    has_monitoring = True

            if not has_monitoring:
                continue

            # Загружаем lastCoins (в памяти) и вспомогательные словари
            lastCoins = parse_last_coins(acc[7])  # dict: key->isoformat
            markets_dict_futures = parse_market_dict(acc[5])
            markets_dict_spot = parse_market_dict(acc[6])
            blacklist = load_blacklist(acc)
            dex_blacklist = load_dex_blacklist(acc)  # set of normalized 'COINUSDT'

            # Обрабатываем все spreads (handle_* БЕЗ БД операций)
            for spread in spreads:
                try:
                    if markets_dict_futures.get(spread[2]) == 1 and markets_dict_futures.get(spread[3]) == 1:
                        handle_spread(spread, acc, lastCoins, dataSearch, blacklist)
                except Exception:
                    logger.exception("process_accounts: handle_spread error for user %s", acc[2])

            # Обрабатываем spotfutures
            for sf in spotfutures:
                try:
                    if markets_dict_spot.get(sf[2]) == 1 and markets_dict_spot.get(sf[3]) == 1:
                        handle_spotfuture(sf, acc, lastCoins, dataSearch, blacklist)
                except Exception:
                    logger.exception("process_accounts: handle_spotfuture error for user %s", acc[2])

            # DEX: передаём dex_blacklist
            for d in dex_records:
                try:
                    m2 = str(d[3])
                    ok = False
                    try:
                        if markets_dict_futures.get(m2) == 1 or markets_dict_spot.get(m2) == 1:
                            ok = True
                    except Exception:
                        ok = False
                    if not ok:
                        continue
                    handle_dex(d, acc, lastCoins, dataSearch, dex_blacklist)
                except Exception:
                    logger.exception("process_accounts: handle_dex error for user %s", acc[2])

            # --- Сохранение lastCoins в БД один раз (если изменился) ---
            try:
                lastCoins, compressed = clean_lastCoins(lastCoins)  # compressed = bytes
                old_blob = blob_to_bytes_safe(acc[7])
                # сравниваем: если старый blob отсутствует и compressed represents {} -> можно пропустить,
                # но проще сравнить байты: если разные — записать
                if compressed != old_blob:
                    cursor.execute('''UPDATE Users SET lastNoticeCoins=%s WHERE tgid=%s''', (compressed, acc[2]))
                    connection.commit()
                    # обновим acc[7] в памяти, чтобы при повторном проходе было текущее значение
                    acc[7] = compressed
            except Exception:
                logger.exception("process_accounts: failed to persist lastCoins for %s", acc[2])

    except Exception:
        logger.exception("process_accounts top-level exception")



def parse_spread(data):
    try:
        return (
            0,
            data.get('symbol', ''),
            data.get('market1', ''),
            data.get('market2', ''),
            data.get('market1funding', 0),
            data.get('market2funding', 0),
            data.get('market1time', 0),
            data.get('market2time', 0),
            data.get('market1bid', 0),
            data.get('market2bid', 0),
            data.get('market1fee', 0),
            data.get('market2fee', 0),
            data.get('market1predict', ''),
            data.get('market2predict', ''),
            data.get('spread', 0),
            data.get('isNew', ''),
            data.get('isUpdated', ''),
            data.get('isDeviation1', 0),
            data.get('isDeviation2', 0),
            data.get('market1ask', 0),
            data.get('market2ask', 0),
            data.get('m1h1', ''),
            data.get('m1h3', ''),
            data.get('m1h7', ''),
            data.get('m1h30', ''),
            data.get('m2h1', ''),
            data.get('m2h3', ''),
            data.get('m2h7', ''),
            data.get('m2h30', ''),
            data.get('amount24m1', 0),
            data.get('amount24m2', 0),
            data.get('limitsm1', 0),
            data.get('limitsm2', 0),
        )
    except Exception:
        return None


def parse_spotfuture(data):
    try:
        return (
            0,  # В вашем случае ID — пока 0
            data.get('symbol', ''),
            data.get('market1', ''),
            data.get('market2', ''),
            data.get('market2funding', 0),  # market2funding, как в spot_futures_write_redis
            data.get('market2time', 0),  # market2time, как в spot_futures_write_redis
            data.get('market2bid', 0),  # market2bid, как в spot_futures_write_redis
            data.get('market1fee', 0),  # market1fee, как в spot_futures_write_redis
            data.get('market2fee', 0),  # market2fee, как в spot_futures_write_redis
            data.get('market2predict', ''),  # market2predict
            data.get('spread', ''),  # spread
            data.get('isNew', ''),  # isNew
            data.get('isUpdated', ''),  # isUpdated
            data.get('isDeviation2', 0),  # isDeviation2, как в spot_futures_write_redis
            data.get('spot1bid', 0),  # spot1bid (это было 'market1bid'
            data.get('market2ask', 0),  # market2ask
            data.get('spot1ask', 0),  # spot1ask
            data.get('m2h1', ''),  # m2h1
            data.get('m2h3', ''),  # m2h3
            data.get('m2h7', ''),  # m2h7
            data.get('m2h30', ''),  # m2h30
            data.get('amount24m2', 0),
            data.get('limitsm2', 0),
            data.get('amount24spot', 0),
        )
    except Exception:
        return None

def parse_dex(data):
    """
    Преобразовать сырой объект DEX (из redis/json) в tuple,
    совместимый с create_message_to_dex.
    Порядок полей должен соответствовать тому, который ты используешь в router-е:
    (id, symbol, 'DEX', market2, bid, priceUsd, diff, contract, chain,
     volume24, volume24_cex, url, cex_ask, funding_rate)
    """
    try:
        return (
            0,  # id (временно)
            data.get('symbol', ''),
            'DEX',
            data.get('market2', ''),
            data.get('bid'),
            data.get('priceUsd'),
            data.get('diff'),
            data.get('contract', ''),
            data.get('chain', ''),
            data.get('volume24'),
            data.get('volume24_cex'),
            data.get('url', ''),
            data.get('cex_ask'),
            data.get('funding_rate')
        )
    except Exception:
        return None

SEARCH_RUNNING = False

async def start_bot_search():
    global bot, bids_asks_futures, bids_asks_spot, coin_cap, SEARCH_RUNNING
    print('StartSearching')
    r0 = REDIS_CLIENTS[0]
    r1 = REDIS_CLIENTS[1]
    r2 = REDIS_CLIENTS[2]

    while True:
        if SEARCH_RUNNING:
            await asyncio.sleep(2)
            continue
        SEARCH_RUNNING = True
        connection = None
        cursor = None
        try:
            # Открываем одно соединение на проход
            connection = mysql.connector.connect(
                host=DB_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DATABASE
            )
            cursor = connection.cursor()
            cursor.execute('SELECT * FROM Users')
            accounts = cursor.fetchall()


            spreads_data = orjson.loads(r0.get("Spreads:all") or "[]")
           # start_1 = time.time()
            spreads = [s for s in map(parse_spread, spreads_data) if s]
           # logger.info(f"cycle {round((time.time() - start_1) * 1000, 2)} ms")

            spreads_data_spot = orjson.loads(r1.get("SpotFutures:all") or "[]")
         #   start_2 = time.time()
            spotfutures = [s for s in map(parse_spotfuture, spreads_data_spot) if s]
          #  logger.info(f"cycle2 {round((time.time() - start_2) * 1000, 2)} ms")

            dex_data = orjson.loads(r2.get("Dex:all") or "[]")
            dex_records = [d for d in map(parse_dex, dex_data) if d]

            # Передаём connection и cursor внутрь, чтобы не открывать новых соединений в process_accounts
            process_accounts(connection, cursor, accounts, spreads, spotfutures, dex_records)
        except Exception:
            logger.exception('start_search_except')
        finally:
            # Закрываем соединение и снимаем флаг
            try:
                if cursor:
                    cursor.close()
                if connection:
                    connection.close()
            except Exception:
                logger.exception('except to close connection search')
            SEARCH_RUNNING = False
            await asyncio.sleep(2)


# ---- DEX blacklist helpers ----
def compress_info_blacklist(data: dict) -> bytes:
    return zlib.compress(orjson.dumps(data))

def decompress_info_blacklist(blob: bytes) -> dict:
    try:
        return orjson.loads(zlib.decompress(blob))
    except Exception:
        return {}

def normalize_coin_for_store(coin: str) -> str:
    # Убираем пробелы, приводим к верхнему регистру, убираем суффикс USDT, добавляем USDT
    c = coin.strip().upper()
    if c.endswith('USDT'):
        c = c[:-4]
    c = ''.join(ch for ch in c if ch.isalnum())  # допустим только букв/цифр
    return f'{c}USDT' if c else ''

def get_user_dex_blacklist_db(user_id: int) -> dict:
    try:
        connection = mysql.connector.connect(host=DB_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DATABASE)
        cursor = connection.cursor()
        cursor.execute("SELECT information FROM Users WHERE tgid=%s", (str(user_id),))
        row = cursor.fetchone()
        connection.close()
        if not row:
            return {}
        blob = row[0]
        if not blob or blob == b'no':
            return {}
        return decompress_info_blacklist(blob)
    except Exception:
        logger.exception("get_user_dex_blacklist_db error")
        return {}

def update_user_dex_blacklist_db(user_id: int, coins: list[str], add: bool = True) -> dict:
    """
    Возвращает текущее состояние (dict) или {'_error': '...'}.
    """
    try:
        # нормализуем вход
        coins_norm = [normalize_coin_for_store(c) for c in coins]
        coins_norm = [c for c in coins_norm if c]  # убираем пустые

        connection = mysql.connector.connect(host=DB_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DATABASE)
        cursor = connection.cursor()
        cursor.execute("SELECT information FROM Users WHERE tgid=%s", (str(user_id),))
        row = cursor.fetchone()
        current = {}
        if row:
            blob = row[0]
            if blob and blob != b'no':
                current = decompress_info_blacklist(blob)

        # apply changes
        for coin in coins_norm:
            if add:
                current[coin] = coin
            else:
                current.pop(coin, None)

        if len(current) > MAX_DEX_BLACKLIST_COINS:
            connection.close()
            return {"_error": f"Превышен лимит в {MAX_DEX_BLACKLIST_COINS} монет."}

        compressed = compress_info_blacklist(current)
        if len(compressed) > MAX_BLOB_SIZE:
            connection.close()
            return {"_error": "Слишком много данных, превышен лимит хранилища."}

        cursor.execute("UPDATE Users SET information = %s WHERE tgid = %s", (compressed, str(user_id)))
        connection.commit()
        connection.close()
        return current
    except Exception:
        logger.exception("update_user_dex_blacklist_db error")
        try:
            connection.close()
        except:
            pass
        return {"_error": "Ошибка при обновлении БД."}

@dp.callback_query(F.data == 'mon_dex_black_view')
async def mon_dex_black_view(call: types.CallbackQuery):
    await call.answer()
    bl = get_user_dex_blacklist_db(call.from_user.id)
    if not bl:
        await call.message.answer("DEX черный список пуст.")
    else:
        coins = ', '.join(k.replace('USDT','') for k in sorted(bl.keys()))
        await call.message.answer(f"DEX черный список:\n\n{coins}")

@dp.callback_query(F.data == 'mon_dex_black_add')
async def mon_dex_black_add(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Введите монеты через запятую для добавления в DEX-чёрный список (напр.: BTC, eth):")
    await state.set_state(DexBlackListFunc.add_black_dex)

@dp.callback_query(F.data == 'mon_dex_black_del')
async def mon_dex_black_del(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Введите монеты через запятую для удаления из DEX-чёрного списка (напр.: BTC, eth):")
    await state.set_state(DexBlackListFunc.del_black_dex)


MAX_BLACKLIST_COINS = 300
MAX_BLOB_SIZE = 64000  # Примерно до 64KB допустимо для обычного BLOB
MAX_DEX_BLACKLIST_COINS = 300

class DexBlackListFunc(StatesGroup):
    add_black_dex = State()
    del_black_dex = State()

@dp.message(DexBlackListFunc.add_black_dex)
async def process_add_black_dex(message: types.Message, state: FSMContext):
    await state.clear()
    coins = [c.strip() for c in message.text.split(',') if c.strip()]
    if not coins or any(len(c) > 20 for c in coins):
        await message.answer("Некоторые названия монет недопустимы (пустые или слишком длинные).")
        return
    result = update_user_dex_blacklist_db(message.from_user.id, coins, add=True)
    if isinstance(result, dict) and result.get("_error"):
        await message.answer(f"Ошибка: {result['_error']}")
        return
    coins_list = ', '.join(k.replace('USDT','') for k in sorted(result.keys()))
    await message.answer(f"Обновлён DEX-чёрный список:\n\n{coins_list}")

@dp.message(DexBlackListFunc.del_black_dex)
async def process_del_black_dex(message: types.Message, state: FSMContext):
    await state.clear()
    coins = [c.strip() for c in message.text.split(',') if c.strip()]
    if not coins or any(len(c) > 20 for c in coins):
        await message.answer("Некоторые названия монет недопустимы (пустые или слишком длинные).")
        return
    result = update_user_dex_blacklist_db(message.from_user.id, coins, add=False)
    if isinstance(result, dict) and result.get("_error"):
        await message.answer(f"Ошибка: {result['_error']}")
        return
    coins_list = ', '.join(k.replace('USDT','') for k in sorted(result.keys()))
    await message.answer(f"Обновлён DEX-чёрный список:\n\n{coins_list}")



class BlackListFunc(StatesGroup):
    add_black = State()
    del_black = State()


def compress_blacklist(data: dict) -> bytes:
    return zlib.compress(orjson.dumps(data))


def decompress_blacklist(blob: bytes) -> dict:
    try:
        return orjson.loads(zlib.decompress(blob))
    except:
        return {}


def get_user_blacklist(account) -> dict:
    user_blacklist_blob = account[8]
    if not user_blacklist_blob or user_blacklist_blob == b'no':
        return {}
    return decompress_blacklist(user_blacklist_blob)


def generate_blacklist_message(blacklist: dict):
    if not blacklist:
        return "Монеты в черном списке\n\nПусто"
    coins = ', '.join(coin.replace('USDT', '') for coin in blacklist)
    return f"Монеты в черном списке\n\n{coins}"


def is_user_active(acc):
    return (acc[9] == '1' and acc[10] == '2') or acc[10] == '1' or acc[14] == '1'


@dp.message(F.text == 'Черный список 🔴')
async def get_black_list(message: types.Message, state: FSMContext):
    accounts = fetch_accounts_from_db()
    inline_kb = InlineKeyboardBuilder().row(button_add_blacklist, button_del_blacklist)

    for acc in accounts:
        if str(acc[2]) == str(message.from_user.id) and is_user_active(acc):
            blacklist = get_user_blacklist(acc)
            msg = generate_blacklist_message(blacklist)
            await message.answer(text=msg, reply_markup=inline_kb.as_markup())
            return

    await message.answer("Аккаунт не найден или не активен.")


@dp.callback_query(F.data.startswith("button_add_blacklist"))
async def func_button_add_blacklist(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Введите монеты через запятую для добавления (например: BTC, ETH):")
    await state.set_state(BlackListFunc.add_black)


@dp.callback_query(F.data.startswith("button_del_blacklist"))
async def func_button_del_blacklist(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Введите монеты через запятую для удаления (например: BTC, ETH):")
    await state.set_state(BlackListFunc.del_black)


async def update_blacklist(user_id: int, coins: list[str], add: bool = True):
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE
    )
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM Users WHERE tgid = %s", (str(user_id),))
    account = cursor.fetchone()

    if not account:
        connection.close()
        return {}

    current_blacklist = get_user_blacklist(account)

    for coin in coins:
        coin_key = coin.upper() + 'USDT'
        if add:
            current_blacklist[coin_key] = coin_key
        else:
            current_blacklist.pop(coin_key, None)

    if len(current_blacklist) > MAX_BLACKLIST_COINS:
        connection.close()
        return {"_error": f"Превышен лимит в {MAX_BLACKLIST_COINS} монет."}

    compressed = compress_blacklist(current_blacklist)
    if len(compressed) > MAX_BLOB_SIZE:
        connection.close()
        return {"_error": "Слишком много данных, превышен лимит хранилища."}

    cursor.execute("UPDATE Users SET blacklist = %s WHERE tgid = %s", (compressed, str(user_id)))
    connection.commit()
    connection.close()
    return current_blacklist


@dp.message(BlackListFunc.add_black)
async def button_event_add_black(message: types.Message, state: FSMContext):
    await state.clear()
    coins = [c.strip() for c in message.text.split(',') if c.strip()]
    if not coins or any(len(c) > 20 for c in coins):
        await message.answer("Некоторые названия монет недопустимы (пустые или слишком длинные).")
        return

    result = await update_blacklist(message.from_user.id, coins, add=True)
    inline_kb = InlineKeyboardBuilder().row(button_add_blacklist, button_del_blacklist)

    if "_error" in result:
        await message.answer(f"Ошибка: {result['_error']}")
    else:
        msg = generate_blacklist_message(result)
        await message.answer(msg, reply_markup=inline_kb.as_markup())


@dp.message(BlackListFunc.del_black)
async def button_event_del_black(message: types.Message, state: FSMContext):
    await state.clear()
    coins = [c.strip() for c in message.text.split(',') if c.strip()]
    if not coins or any(len(c) > 20 for c in coins):
        await message.answer("Некоторые названия монет недопустимы (пустые или слишком длинные).")
        return

    result = await update_blacklist(message.from_user.id, coins, add=False)
    inline_kb = InlineKeyboardBuilder().row(button_add_blacklist, button_del_blacklist)

    if "_error" in result:
        await message.answer(f"Ошибка: {result['_error']}")
    else:
        msg = generate_blacklist_message(result)
        await message.answer(msg, reply_markup=inline_kb.as_markup())


BROADCAST_DELAY = 0.6  # секунда между отправками (подстрой под нагрузку)
PROGRESS_EVERY = 50     # как часто обновлять прогресс-отчёт админу

def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def split_text_by_len(text: str, max_len: int = 4096):
    """Разбить текст на части <= max_len, стараясь не разрывать слова."""
    if not text:
        return []
    parts = []
    while len(text) > max_len:
        cut = text.rfind(' ', 0, max_len)
        if cut == -1:
            cut = max_len
        parts.append(text[:cut])
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    return parts

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("⛔ У вас нет доступа к этой команде.")

    # --- Получаем "тело" рассылки и картинки ---
    raw_text = ""
    image_urls = []
    replied_photo_file_id = None
    reply_has_media_group = False

    # безопасно взять текст команды (message.text может быть None)
    message_text_safe = (message.text or "")

    if message.reply_to_message:
        replied = message.reply_to_message
        raw_text = (replied.text or replied.caption or "")
        # если сообщение содержит фото (single photo)
        if replied.photo:
            replied_photo_file_id = replied.photo[-1].file_id

        # если сообщение является частью media group — сообщим админу (ограничение API)
        if getattr(replied, "media_group_id", None):
            reply_has_media_group = True

        # ищем ссылки на картинки в тексте/подписи (простая регекса)
        image_urls = re.findall(r'(https?://\S+)', raw_text)
        for url in image_urls:
            raw_text = raw_text.replace(url, '').strip()
    else:
        # Поддержка /broadcast <текст> и /broadcast\n<текст>
        parts = message_text_safe.split(maxsplit=1)
        if len(parts) >= 2:
            raw_text = parts[1]
        else:
            return await message.answer(
                "⚠️ Используй: /broadcast <текст> (или /broadcast и перевод строки + текст) "
                "или ответь на сообщение с медиа/подписью."
            )
        image_urls = re.findall(r'(https?://\S+)', raw_text)
        for url in image_urls:
            raw_text = raw_text.replace(url, '').strip()

    if not raw_text and not image_urls and not replied_photo_file_id:
        return await message.answer("⚠️ Нет текста и нет изображений для рассылки.")

    # --- Выдергиваем пользователей из БД ---
    import mysql.connector
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE
    )
    cursor = connection.cursor()
    cursor.execute("SELECT tgid FROM Users")
    rows = cursor.fetchall()
    connection.close()

    user_ids = [r[0] for r in rows if r and r[0]]
    total = len(user_ids)
    if total == 0:
        return await message.answer("⚠️ В базе нет пользователей для рассылки.")

    status_msg = await message.answer(f"🚀 Начинаю рассылку: 0/{total}")

    success = 0
    failed = 0

    info_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Информация', web_app=WebAppInfo(
                    url=f'{ORIGIN}/info/'))]
    ])

    async def send_to(user_id: int):
        nonlocal success, failed
        max_attempts = 3
        attempt = 0
        while attempt < max_attempts:
            try:
                # 1) Если image_urls есть -> отправляем чанками по 10 (telegram ограничение)
                if image_urls:
                    # Отправляем альбом(ы) по 10 картинок
                    for chunk in chunk_list(image_urls, 10):
                        medias = []
                        caption_for_first = raw_text[:1024] if raw_text else None
                        for i, url in enumerate(chunk):
                            if i == 0:
                                medias.append(InputMediaPhoto(media=url, caption=caption_for_first or ""))
                                caption_for_first = None
                            else:
                                medias.append(InputMediaPhoto(media=url))
                        # отправляем альбом
                        await message.bot.send_media_group(chat_id=user_id, media=medias)
                        await asyncio.sleep(0.2)

                    # После альбома отправим отдельное сообщение с кнопкой (т.к. media_group может не поддерживать inline)
                    if raw_text:
                        await message.bot.send_message(
                            chat_id=user_id,
                            text=raw_text,
                            parse_mode="HTML",
                            disable_web_page_preview=True,
                            reply_markup=info_kb
                        )

                elif replied_photo_file_id:
                    # Отправляем single photo (с подписью и кнопкой)
                    caption = raw_text[:1024] if raw_text else None
                    await message.bot.send_photo(
                        chat_id=user_id,
                        photo=replied_photo_file_id,
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=info_kb
                    )

                else:
                    # Текст (возможно длинный) — разбиваем на части и отправляем с HTML
                    parts_text = split_text_by_len(raw_text or "", 4096)
                    for i, p in enumerate(parts_text):
                        # кнопку добавляем только к последнему фрагменту
                        markup = info_kb if (i == len(parts_text) - 1) else None
                        await message.bot.send_message(
                            chat_id=user_id,
                            text=p,
                            parse_mode="HTML",
                            disable_web_page_preview=True,
                            reply_markup=markup
                        )
                success += 1
                return
            except Exception as e:
                # Общая обработка ошибок (без конкретных импортов)
                retry_after = getattr(e, "retry_after", None)
                exc_name = e.__class__.__name__
                if retry_after is not None or "Retry" in exc_name or "retry" in exc_name.lower():
                    wait_for = int(retry_after) if retry_after is not None else 5
                    print(f"[broadcast] RetryAfter for {user_id}, sleeping {wait_for}s (attempt {attempt+1})")
                    await asyncio.sleep(wait_for + 1)
                    attempt += 1
                    continue
                if exc_name in {"BotBlocked", "ChatNotFound", "UserDeactivated"}:
                    print(f"[broadcast] Permanent error for {user_id}: {exc_name} — {e}")
                    failed += 1
                    return
                # иные ошибки — логируем и пробуем ещё раз
                print(f"[broadcast] Error for {user_id} ({exc_name}): {e} — attempt {attempt+1}")
                attempt += 1
                await asyncio.sleep(1)
                continue
        failed += 1
        print(f"[broadcast] Failed to send to {user_id} after {max_attempts} attempts.")

    # --- Основной цикл рассылки ---
    if reply_has_media_group:
        # предупреждение админу — бот может не иметь доступа ко всем картинкам альбома, если ответили только на одно сообщение.
        await message.reply(
            "⚠️ В ответном сообщении обнаружен media_group (альбом). "
            "Из-за ограничений Telegram бот может не получить все сообщения альбома, если вы ответили только на одно сообщение из альбома. "
            "Рекомендую: переслать все фото как прямые ссылки в тексте, или пересылать весь альбом в личку боту и ответить на него."
        )

    for idx, uid in enumerate(user_ids, start=1):
        await send_to(uid)

        if idx % PROGRESS_EVERY == 0 or idx == total:
            try:
                await message.bot.edit_message_text(
                    chat_id=status_msg.chat.id,
                    message_id=status_msg.message_id,
                    text=f"🚀 Рассылка: {idx}/{total}\n✅ Успешно: {success}\n🚫 Ошибок: {failed}"
                )
            except Exception:
                pass

        await asyncio.sleep(BROADCAST_DELAY)

    # Финальный отчёт
    try:
        await message.bot.edit_message_text(
            chat_id=status_msg.chat.id,
            message_id=status_msg.message_id,
            text=f"✅ Рассылка завершена: {total}/{total}\n✅ Успешно: {success}\n🚫 Ошибок: {failed}"
        )
    except Exception:
        await message.answer(f"✅ Рассылка завершена!\n✅ Успешно: {success}\n🚫 Ошибок: {failed}")


@dp.message(CommandStart())
async def start_bot(message: types.Message):
    print(message.from_user.id, ' - ', message.from_user.username, ' - ', message.text)
    connection = None
    cursor = None
    try:
        user = message.from_user
        name = user.first_name or user.username or "друг"

        # 1. Инлайн кнопки
        paid_inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [button_subscription_web, button_info_web ],
        ])

        # 3. Приветствие
        text_active = f"👋 Привет, <b>{name}</b>!\n\n<i>Ваша подписка активна ✅</i>"
        text_inactive = f"👋 Привет, <b>{name}</b>!\n\n<i>У вас нет активной подписки</i>"
        args = message.text.split()
        referral_id = args[1] if len(args) == 2 else None

        is_admin = message.from_user.id == ADMIN_ID

        if not is_admin:
            await bot.send_message(ADMIN_ID, f"{message.from_user.id} - {message.from_user.username} - START",
                                   parse_mode='HTML')
        # Клавиатура
        greet_kb = [[button_admin_panel]] if is_admin else []
        greet_kb += [[button_spreads, button_spot], [button_blacklist, button_marketslist], [button_dex, button_monitoring]]
        greet_kb1 = ReplyKeyboardMarkup(keyboard=greet_kb, resize_keyboard=True, one_time_keyboard=False )

        paid_kb = [[button_admin_panel]] if is_admin else []
       # paid_kb += [[button_start_test]]
        paid_kb1 = ReplyKeyboardMarkup(keyboard=paid_kb, resize_keyboard=True, one_time_keyboard=False )

        # Подключение к БД
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM Users')
        accounts = cursor.fetchall()

        addNew = True
        marketsliststart = json.dumps(['Bybit_1', 'Mexc_1', 'Kucoin_1', 'Gateio_1', 'Bitget_1',
                                       'Huobi_1', 'Okx_1', 'Binance_1', 'BingX_1', 'BitMart_1',
                                       'Ourbit_1', 'Hyperliquid_1', 'LBank_1', 'DEX_1', 'Aster_1', 'XT_1',
                                       'CoinEx_1', 'WEEX_1', 'Phemex_1', 'BinanceAlpha_1'])

        for acc in accounts:
            if str(acc[2]) == str(message.from_user.id):
                addNew = False
                if acc[10] == '1' or (acc[14] == '1' and acc[10] != '0') or (acc[9] == '1' and acc[10] == '2'):
                    await message.answer(text_active, reply_markup=greet_kb1, parse_mode="HTML")
                elif (acc[9] == '0' and acc[10] == '2') or (acc[10] == '0'):
                    # 4. Сначала отправляем сообщение с inline-кнопками
                    if acc[13] == 'no': # еще не был активирован тест
                        if is_admin:
                            await message.answer(text_inactive, reply_markup=paid_kb1, parse_mode="HTML")
                        else:
                            await message.answer(text_inactive, reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
                        # 5. Затем ставим reply-клавиатуру
                      #  await message.answer("📌 Чтобы начать работу — выберите нужный раздел снизу или нажмите <b>Начать тест</b>, чтобы активировать <u>бесплатный доступ на 24 часа</u>.", reply_markup=paid_inline_kb, parse_mode='HTML')
                        await message.answer("📌 Чтобы начать работу — выберите нужный раздел снизу.", reply_markup=paid_inline_kb, parse_mode='HTML')
                    else: # был активирован тест и уже доступа нет
                        if not is_admin:
                            await message.answer(text_inactive, reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
                            # 5. Затем ставим reply-клавиатуру
                            await message.answer(
                                "📌 Чтобы продолжить пользоваться ботом, пожалуйста, оформите подписку.",
                                reply_markup=paid_inline_kb, parse_mode='HTML')
                        else:
                            await message.answer(text_inactive, reply_markup=paid_kb1, parse_mode="HTML")
                            # 5. Затем ставим reply-клавиатуру
                            await message.answer(
                                "📌 Чтобы продолжить пользоваться ботом, пожалуйста, оформите подписку.",
                                reply_markup=paid_inline_kb, parse_mode='HTML')
                break

        if addNew:
            memo = random_alphanumeric_string(5) + str(message.from_user.id)[-3:]
            if not referral_id:
                referral_id = 'no'

            username = message.from_user.username if message.from_user.username else 'None'
            cursor.execute(
                '''INSERT INTO Users 
                (username, tgid, isSearching, dataSearch, listMarketsFutures, listMarketsSpot, lastNoticeCoins, blacklist, isActive, isActiveAdmin, timeActiveAdmin, dataaddress, timeTest, testActive, referral, information, memoAccount) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);''',
                [username, message.from_user.id, 0, 'no', marketsliststart, marketsliststart, b'no', b'no',
                 0, 2, 'no', 'no', 'no', 0, referral_id, b'no', memo]
            )
            connection.commit()

            if is_admin:
                await message.answer(text_inactive, reply_markup=paid_kb1, parse_mode="HTML")
            else:
                await message.answer(text_inactive, reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
            # 5. Затем ставим reply-клавиатуру
            await message.answer(
                "📌 Чтобы начать работу — выберите нужный раздел снизу.",
                reply_markup=paid_inline_kb, parse_mode='HTML')
    except Exception as e:
        logger.exception("start_bot error")
    finally:
        try:
            if cursor:
                cursor.close()
        except:
            pass
        if connection:
            connection.close()


async def main():
    global bot

    token = os.getenv("TELEGRAM_BOT_TOKEN_DEV") if DEBUG else os.getenv("TELEGRAM_BOT_TOKEN")
    proxy = os.getenv("PROXY_HTTP")

    session = AiohttpSession(proxy=proxy)
    bot = Bot(token=token, session=session)

    logging.basicConfig(level=logging.INFO)
    dp.startup.register(start_bot_func)
    await dp.start_polling(bot)


if __name__ == '__main__':

    asyncio.run(main())
