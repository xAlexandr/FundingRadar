import logging
from aiogram.types import KeyboardButton, InlineKeyboardButton
import random
import string
import json
import os
from aiogram.types.web_app_info import WebAppInfo
#from keras.models import load_model
import mysql.connector
import redis
#from motor.motor_asyncio import AsyncIOMotorClient
import statistics
import time
import zlib
# ---- BEGIN: IN-MEMORY CACHE FOR REDIS (insert near top of tgfunc.py, after imports) ----
import threading
import time as _time
import logging
import orjson
import html

logger = logging.getLogger("libs.tgfunc")
logging.basicConfig(level=logging.INFO)
# redis и json уже импортированы выше в модуле

REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))

MYSQL_ROOT_PASSWORD = os.getenv('MYSQL_ROOT_PASSWORD', '')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'funding')
MYSQL_USER = os.getenv('MYSQL_USER', 'username')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'password')
DB_HOST = os.getenv('DB_HOST', 'mysql')
DB_PORT = os.getenv('DB_PORT', '3306')

ORIGIN = os.getenv('ORIGIN')

logging.getLogger('tensorflow').setLevel(logging.ERROR)
logging.getLogger('keras').setLevel(logging.ERROR)


REDIS_CLIENTS = {
    0: redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True),
    1: redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=1, decode_responses=True),
    2: redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=2, decode_responses=True),
}

def _load_key_from_redis(db_index, key):
    try:
        r = REDIS_CLIENTS[db_index]
        raw = r.get(key)
        if not raw:
            return None
        return orjson.loads(raw)  # вместо json.loads
    except Exception:
        logger.exception("redis load error for %s db=%s", key, db_index)
        return None

def get_cached_spreads_by_symbol(symbol):
    arr = read_redis_list(0, "Spreads:all")
    if not arr:
        return []
    return [rec for rec in arr if rec.get('symbol') == symbol]

def get_cached_spotfutures_by_symbol(symbol):
    arr = read_redis_list(1, "SpotFutures:all")
    if not arr:
        return []
    return [rec for rec in arr if rec.get('symbol') == symbol]

def get_cached_dex_by_symbol(symbol):
    arr = read_redis_list(2, "Dex:all")
    if not arr:
        return []
    return [rec for rec in arr if rec.get('symbol') == symbol]

def get_cached_dex_by_market(market):
    arr = read_redis_list(2, "Dex:all")
    if not arr:
        return []
    return [rec for rec in arr if rec.get('market2') == market]

def get_cached_dex_all():
    return get_cached_dex()  # или применить ту же логику что и раньше

# --- DEX -> tuples helpers ---
def fetch_dex_spreads_from_db():
    """
    Вернуть список tuples, совместимых с get_user_markets/get_user_spreads,
    основанных на данных CACHE['Dex'] (или fallback чтение Redis db=2).
    """
    raw_list = get_cached_dex()
    if raw_list is None:
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=2, decode_responses=True)
            raw = r.get("Dex:all")
            raw_list = orjson.loads(raw) if raw else []
        except Exception:
            logger.exception("fetch_dex_spreads_from_db: redis read failed")
            return []

    spreads = []
    for data in raw_list:
        try:
            # Маппинг полей: стараемся заполнить те индексы, на которые смотрит UI
            # Формат подобен fetch_spreads_from_db, но многие поля будут 0/'' если нет в Dex записи
            symbol = data.get('symbol', '')
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
            funding_rate =  data.get('funding_rate', 0)

            spread = (
                0,
                symbol,
                dex_market,
                cex_market,
                dex_bid,
                price_usd,
                diff,
                contract,
                chain,
                volume24,
                volume24_cex,
                url,
                cex_ask,
                funding_rate
            )
            spreads.append(spread)
        except Exception:
            logger.exception("fetch_dex_spreads_from_db: bad record, skipping")
            continue

    return spreads


def fetch_dex_spreads_symbol_from_db(symbolFind):
    """
    Версия, фильтрующая по symbol — использует индекс get_cached_dex_by_symbol.
    Возвращает список tuples.
    """
    raw_list = get_cached_dex_by_symbol(symbolFind)
    if raw_list is None:
        raw_list = get_cached_dex()
        if raw_list is None:
            try:
                r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=2, decode_responses=True)
                raw = r.get("Dex:all")
                raw_list = orjson.loads(raw) if raw else []
            except Exception:
                logger.exception("fetch_dex_spreads_symbol_from_db: redis read failed")
                return []

    spreads = []
    for data in raw_list:
        try:
            # если raw_list получен через индекс, это уже отфильтровано; если нет, фильтруем
            if data.get('symbol', '') != symbolFind:
                continue
            # собираем tuple так же как в fetch_dex_spreads_from_db
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

            spread = (
                0,
                symbolFind,
                dex_market,
                cex_market,
                dex_bid,
                price_usd,
                diff,
                contract,
                chain,
                volume24,
                volume24_cex,
                url,
                cex_ask,
                funding_rate
            )
            spreads.append(spread)
        except Exception:
            logger.exception("fetch_dex_spreads_symbol_from_db: bad record for %s", symbolFind)
            continue

    return spreads


def fetch_dex_spreads_accounts_from_db():
    """
    Возвращает (spreads, accounts) для DEX (используется для show_dex_page).
    """
    raw_spreads = fetch_dex_spreads_from_db()
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM Users')
        accounts = cursor.fetchall()
        connection.close()
    except Exception:
        logger.exception("fetch_dex_spreads_accounts_from_db: mysql read failed")
        accounts = []
    return raw_spreads, accounts
# --- end DEX helpers ---
def read_redis_list(db_index, key):
    """
    Возвращает parsed list (или пустой список при отсутствии ключа).
    Использует существующий _load_key_from_redis (который возвращает parsed JSON или None).
    """
    try:
        data = _load_key_from_redis(db_index, key)
        if data is None:
            return []
        # Ожидаем, что data — list
        return data if isinstance(data, list) else []
    except Exception:
        logger.exception("read_redis_list failed db=%s key=%s", db_index, key)
        return []
# Доступные функции чтения кеша (возвращают копию списка или None)
# Совместимый API (чтобы минимально менять остальной код):
def get_cached_spreads():
    return read_redis_list(0, "Spreads:all")

def get_cached_spotfutures():
    return read_redis_list(1, "SpotFutures:all")

def get_cached_dex():
    return read_redis_list(2, "Dex:all")

def get_cache_meta(key):
    # раньше хранилось в CACHE['meta'] — теперь не поддерживается
    return None
# ---- END: IN-MEMORY CACHE FOR REDIS ----

#mongo_client = AsyncIOMotorClient("mongodb://localhost:27017/?readConcernLevel=available")

#mongo_db = mongo_client["funding"]

def takeSecondReverse(elem, direction='normal'):
    try:
        if direction == 'normal':  # первая биржа выше или равна
            return elem[14]
        elif direction == 'reverse':  # вторая биржа выше
            return round(float(elem[5])-float(elem[4]),2)
    except Exception:
        return 0

def takeSecondDex(elem):
    try:
        return elem[13]
    except Exception:
        return 0

def takeSecond(elem):
    return elem[14]


def takeOne(elem):
    return elem[4]


def take1d(elem, direction='normal'):
    if direction == 'normal':
        if elem[21] != '' and elem[25] != '':
            return round(elem[21] - elem[25], 2)
    elif direction == 'reverse':
        if elem[25] != '' and elem[21] != '':
            return round(elem[25] - elem[21], 2)
    return float('-inf')


def take3d(elem, direction='normal'):
    if direction == 'normal':
        if elem[22] != '' and elem[26] != '':
            return round(elem[22] - elem[26], 2)
    elif direction == 'reverse':
        if elem[26] != '' and elem[22] != '':
            return round(elem[26] - elem[22], 2)
    return float('-inf')


def take7d(elem, direction='normal'):
    if direction == 'normal':
        if elem[23] != '' and elem[27] != '':
            return round(elem[23] - elem[27], 2)
    elif direction == 'reverse':
        if elem[27] != '' and elem[23] != '':
            return round(elem[27] - elem[23], 2)
    return float('-inf')


def take30d(elem, direction='normal'):
    if direction == 'normal':
        if elem[24] != '' and elem[28] != '':
            return round(elem[24] - elem[28], 2)
    elif direction == 'reverse':
        if elem[28] != '' and elem[24] != '':
            return round(elem[28] - elem[24], 2)
    return float('-inf')


def spot_take1d(elem):
    if elem[17] != '':
        return elem[17]
    return float('-inf')


def spot_take3d(elem):
    if elem[18] != '':
        return elem[18]
    return float('-inf')


def spot_take7d(elem):
    if elem[19] != '':
        return elem[19]
    return float('-inf')


def spot_take30d(elem):
    if elem[20] != '':
        return elem[20]
    return float('-inf')


def takeCourseSpot(elem):
    try:
        return round(((float(elem[6]) / float(elem[16])) - 1) * 100, 2)
    except Exception:
        return 0


def takeCourse(elem):
    try:
        if float(elem[4]) >= float(elem[5]):
            return round(((float(elem[8]) / float(elem[20])) - 1) * 100, 2)
        elif float(elem[5]) > float(elem[4]):
            return round(((float(elem[9]) / float(elem[19])) - 1) * 100, 2)
    except Exception:
        return 0


def takeCourseReverse(elem, direction='normal'):
    try:
        if direction == 'normal':  # первая биржа выше или равна
            return round(((float(elem[8]) / float(elem[20])) - 1) * 100, 2)
        elif direction == 'reverse':  # вторая биржа выше
            return round(((float(elem[9]) / float(elem[19])) - 1) * 100, 2)
    except Exception:
        return 0


def takeCourseDex(elem):
    try:
        return elem[6]
    except Exception:
        return 0

# Дублируем спреды с учетом обоих направлений
def expand_spreads_with_directions(spreads):
    expanded = []
    for spread in spreads:
        try:
            if isinstance(spread, (list, tuple)) and len(spread) >= 6:
                base = spread if isinstance(spread, list) else list(spread)
                # Всегда добавляем оба направления
                expanded.append(base + ['normal'])
                expanded.append(base + ['reverse'])
        except Exception as e:
            print("Ошибка при расширении spread:", spread, e)
            continue
    return expanded


def query_spreads(data):
    print(data)
    if data == 'button_spreads':
        return True
    else:
        return False


def random_alphanumeric_string(length):
    return ''.join(
        random.choices(
            string.ascii_lowercase + string.digits,
            k=length
        )
    )

def fmt_amount_usd(x):
    """
    Форматирование объёма в человекочитаемый вид:
      123 -> "123"
      1234 -> "1.23K" -> будет "1.2K" (1 decimal, trailing zeros removed)
      1_234_567 -> "1.23M" -> "1.2M"
      1_200_000 -> "1.2M"
      1000 -> "1K"
    Безопасно для строк/None: возвращает исходное значение как str, если не парсится в float.
    """
    try:
        if x is None:
            return "0"
        # если уже строка с $ или суффиксами — просто вернуть (предположим, что пользователь не прошит)
        if isinstance(x, str):
            xs = x.strip()
            # убрать знак $ в конце/начале, если есть
            if xs.endswith('$'):
                xs = xs[:-1].strip()
            # попробовать конвертировать
            val = float(xs.replace(',', '').replace(' ', ''))
        else:
            val = float(x)
    except Exception:
        # если не получилось преобразовать — вернуть оригинал как строку
        try:
            return str(x)
        except:
            return "0"

    neg = val < 0
    v = abs(val)

    def strip_trailing(s):
        # убираем лишние .0
        s = s.rstrip('0').rstrip('.') if '.' in s else s
        return s

    if v >= 1_000_000_000:
        s = f"{v / 1_000_000_000:.1f}"
        s = strip_trailing(s) + "B"
    elif v >= 1_000_000:
        s = f"{v / 1_000_000:.1f}"
        s = strip_trailing(s) + "M"
    elif v >= 1_000:
        s = f"{v / 1_000:.1f}"
        s = strip_trailing(s) + "K"
    else:
        # для маленьких — показываем целое, если возможно, иначе 2 знака
        if v == int(v):
            s = str(int(v))
        else:
            s = strip_trailing(f"{v:.2f}")

    return ("-" if neg else "") + s


def fetch_spreads_symbol_from_db(symbolFind):
    """
    Использует индекс CACHE['Spreads_index'] когда он есть, иначе fallback на CACHE['Spreads'] или Redis.
    Возвращает список tuple (совместимо с остальным кодом).
    """
    # Попробуем индекс сначала
    try:
        raw_list = read_redis_list(0, "Spreads:all")
    except Exception:
        logger.exception("fetch_spreads_from_db: redis read failed")
        return []

    spreads = []
    for data in raw_list:
        try:
            if data.get('symbol', '') != symbolFind:
                continue
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
            spreads.append(spread)
        except Exception:
            logger.exception("fetch_spreads_symbol_from_db: bad record for %s", symbolFind)
            continue

    return spreads




def fetch_spot_spreads_symbol_from_db(symbolFind):
    try:
        raw_list = read_redis_list(1, "SpotFutures:all")
    except Exception:
        logger.exception("fetch_spreads_from_db: redis read failed")
        return []

    spreads = []
    for data in raw_list:
        try:
            if data.get('symbol', '') != symbolFind:
                continue
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
            spreads.append(spread)
        except Exception:
            logger.exception("fetch_spot_spreads_symbol_from_db: bad record for %s", symbolFind)
            continue

    return spreads




def fetch_spreads_from_db():
    """
    Возвращает список spread-ов (parsed tuples), берёт данные из in-memory CACHE если есть,
    иначе читает Redis (db 0) как раньше.
    """
    try:
        raw_list = read_redis_list(0, "Spreads:all")
    except Exception:
        logger.exception("fetch_spreads_from_db: redis read failed")
        return []

    spreads = []
    for data in raw_list:
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
            spreads.append(spread)
        except Exception:
            # Пропустить невалидную запись, но не падать
            logger.exception("fetch_spreads_from_db: bad spread record, skipping")
            continue

    return spreads



def fetch_accounts_from_db():
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE
    )
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM Users')
    ret = cursor.fetchall()
    connection.close()
    return ret


def fetch_spreads_accounts_from_db():
    """
    Возвращает (spreads, accounts).
    Сначала использует CACHE['Spreads'], иначе fallback на Redis db=0.
    """
    # Попытка взять из кеша
    try:
        raw_list = read_redis_list(0, "Spreads:all")
    except Exception:
        logger.exception("fetch_spreads_from_db: redis read failed")
        return []

    spreads = []
    for data in raw_list:
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
            spreads.append(spread)
        except Exception as e:
            logger.exception("fetch_spreads_accounts_from_db: bad record, skipping: %s", e)
            continue

    # достать accounts из MySQL (как раньше)
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM Users')
        accounts = cursor.fetchall()
        connection.close()
    except Exception:
        logger.exception("fetch_spreads_accounts_from_db: mysql read failed")
        accounts = []

    return spreads, accounts


def fetch_spot_spreads_from_db():
    """
    Возвращает список spot/futures spreads, пытаясь сначала взять из in-memory CACHE,
    иначе читает Redis db=1 (SpotFutures:all) как fallback.
    Возвращает list of tuples (совместимо с другими fetch_*).
    """
    try:
        raw_list = read_redis_list(1, "SpotFutures:all")
    except Exception:
        logger.exception("fetch_spreads_from_db: redis read failed")
        return []

    spreads = []
    for data in raw_list:
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
            )
            spreads.append(spread)
        except Exception:
            logger.exception("fetch_spot_spreads_from_db: bad record, skipping")
            continue

    return spreads

def fetch_spot_spreads_accounts_from_db():
    """
    Возвращает (spreads, accounts) для SpotFutures.
    Сначала использует CACHE['SpotFutures'], иначе fallback на Redis db=1.
    """
    try:
        raw_list = read_redis_list(1, "SpotFutures:all")
    except Exception:
        logger.exception("fetch_spreads_from_db: redis read failed")
        return []

    spreads = []
    for data in raw_list:
        try:
            spread = (
                0,
                data.get('symbol', ''),
                data.get('market1', ''),
                data.get('market2', ''),
                float(data.get('market2funding', 0)),
                float(data.get('market2time', 0)),
                float(data.get('market2bid', 0)),
                float(data.get('market1fee', 0)),
                float(data.get('market2fee', 0)),
                data.get('market2predict', ''),
                data.get('spread', ''),
                data.get('isNew', ''),
                data.get('isUpdated', ''),
                float(data.get('isDeviation2', 0)),
                float(data.get('spot1bid', 0)),
                float(data.get('market2ask', 0)),
                float(data.get('spot1ask', 0)),
                data.get('m2h1', ''),
                data.get('m2h3', ''),
                data.get('m2h7', ''),
                data.get('m2h30', ''),
                float(data.get('amount24m2', 0)),
                float(data.get('limitsm2', 0)),
                float(data.get('amount24spot', 0)),
            )
            spreads.append(spread)
        except Exception as e:
            logger.exception("fetch_spot_spreads_accounts_from_db: bad record, skipping: %s", e)
            continue

    # достать accounts из MySQL (как раньше)
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM Users')
        accounts = cursor.fetchall()
        connection.close()
    except Exception:
        logger.exception("fetch_spot_spreads_accounts_from_db: mysql read failed")
        accounts = []

    return spreads, accounts



def filter_spreads_spot_markets(spreads, markets_dict_spot, dataSearch, active):
    # Удаляем спреды с неактивными рынками
    spreads = [s for s in spreads if markets_dict_spot.get(s[2], 0) != 0 and markets_dict_spot.get(s[3], 0) != 0]

    inlines_spreads = []
    if len(spreads) > 0:
        if dataSearch != 'no':
            dataSearch = orjson.loads(dataSearch)
        if dataSearch != 'no' and 'filter_history' in dataSearch and dataSearch['filter_history'] != 'current':
            if dataSearch['filter_history'] == '1d':
                spreads.sort(key=spot_take1d, reverse=True)
            elif dataSearch['filter_history'] == '3d':
                spreads.sort(key=spot_take3d, reverse=True)
            elif dataSearch['filter_history'] == '7d':
                spreads.sort(key=spot_take7d, reverse=True)
            elif dataSearch['filter_history'] == '30d':
                spreads.sort(key=spot_take30d, reverse=True)
        elif dataSearch != 'no' and 'filter_course_or_spread' in dataSearch:
            if dataSearch['filter_course_or_spread'] == '1':
                spreads.sort(key=takeCourseSpot, reverse=True)
            else:
                spreads.sort(key=takeOne, reverse=True)
        else:
            spreads.sort(key=takeOne, reverse=True)
        for spread in spreads:
            if dataSearch != 'no' and 'filter_history' in dataSearch and dataSearch['filter_history'] != 'current':
                if dataSearch['filter_history'] == '1d':
                    inlines_spreads.append(build_inline_button_markets_spot_futures_history_1d(spread))
                elif dataSearch['filter_history'] == '3d':
                    inlines_spreads.append(build_inline_button_markets_spot_futures_history_3d(spread))
                elif dataSearch['filter_history'] == '7d':
                    inlines_spreads.append(build_inline_button_markets_spot_futures_history_7d(spread))
                elif dataSearch['filter_history'] == '30d':
                    inlines_spreads.append(build_inline_button_markets_spot_futures_history_30d(spread))

            elif dataSearch != 'no':
                if 'filter_big_or_all_course' in dataSearch:
                    if dataSearch['filter_big_or_all_course'] == '1':
                        if check_spread_spot(spread) > 0:
                            inlines_spreads.append(build_inline_button_markets_spot_futures(spread))
                    elif dataSearch['filter_big_or_all_course'] == '0':
                        inlines_spreads.append(build_inline_button_markets_spot_futures(spread))
                else:
                    inlines_spreads.append(build_inline_button_markets_spot_futures(spread))
            else:
                inlines_spreads.append(build_inline_button_markets_spot_futures(spread))
    return inlines_spreads, dataSearch, active


def filter_spreads_spot(spreads, markets_dict_spot, dataSearch, blacklist, active):
    # Удаляем спреды с неактивными рынками
    spreads = [
        s for s in spreads
        if markets_dict_spot.get(s[2], 0) != 0
           and markets_dict_spot.get(s[3], 0) != 0
           and s[1] not in blacklist  # 🔥 проверка чёрного списка
    ]

    inlines_spreads = []
    if len(spreads) > 0:
        if dataSearch != 'no':
            dataSearch = orjson.loads(dataSearch)
        if dataSearch != 'no' and 'filter_history' in dataSearch and dataSearch['filter_history'] != 'current':
            if dataSearch['filter_history'] == '1d':
                spreads.sort(key=spot_take1d, reverse=True)
            elif dataSearch['filter_history'] == '3d':
                spreads.sort(key=spot_take3d, reverse=True)
            elif dataSearch['filter_history'] == '7d':
                spreads.sort(key=spot_take7d, reverse=True)
            elif dataSearch['filter_history'] == '30d':
                spreads.sort(key=spot_take30d, reverse=True)
        elif dataSearch != 'no' and 'filter_course_or_spread' in dataSearch:
            if dataSearch['filter_course_or_spread'] == '1':
                spreads.sort(key=takeCourseSpot, reverse=True)
            else:
                spreads.sort(key=takeOne, reverse=True)
        else:
            spreads.sort(key=takeOne, reverse=True)
        unique_values = {}
        for sublist in spreads:
            key = sublist[1]
            if key not in unique_values:
                unique_values[key] = sublist
        spreads = list(unique_values.values())
        for spread in spreads:
            try:
                if dataSearch != 'no' and 'filter_history' in dataSearch and dataSearch['filter_history'] != 'current':
                    if dataSearch['filter_history'] == '1d':
                        inlines_spreads.append(build_inline_button_spot_futures_history_1d(spread))
                    elif dataSearch['filter_history'] == '3d':
                        inlines_spreads.append(build_inline_button_spot_futures_history_3d(spread))
                    elif dataSearch['filter_history'] == '7d':
                        inlines_spreads.append(build_inline_button_spot_futures_history_7d(spread))
                    elif dataSearch['filter_history'] == '30d':
                        inlines_spreads.append(build_inline_button_spot_futures_history_30d(spread))
                elif dataSearch != 'no' and 'filter_course_or_spread' in dataSearch and dataSearch[
                    'filter_course_or_spread'] == '1':
                    if dataSearch['filter_course_or_spread'] == '1':
                        if 'filter_big_or_all_course' in dataSearch:
                            if dataSearch['filter_big_or_all_course'] == '1':
                                if check_spread_spot(spread) > 0:
                                    inlines_spreads.append(build_inline_button_spot_futures(spread))
                            elif dataSearch['filter_big_or_all_course'] == '0':
                                inlines_spreads.append(build_inline_button_spot_futures(spread))
                        else:
                            inlines_spreads.append(build_inline_button_spot_futures(spread))
                elif dataSearch != 'no' and 'filter_big_or_all_course' in dataSearch and dataSearch[
                    'filter_big_or_all_course'] == '1':
                    if check_spread_spot(spread) > 0:
                        inlines_spreads.append(build_inline_button_spot_big(spread))
                else:
                    inlines_spreads.append(build_inline_button_spot_big(spread))
            except Exception:
                pass
    return inlines_spreads, dataSearch, active


def filter_spreads(spreads, markets_dict_futures, dataSearch, blacklist, active):
    # Удаляем спреды с неактивными рынками
    spreads = [
        s for s in spreads
        if markets_dict_futures.get(s[2], 0) != 0
           and markets_dict_futures.get(s[3], 0) != 0
           and s[1] not in blacklist  # 🔥 проверка чёрного списка
    ]
    # Парсим фильтры
    if dataSearch != 'no':
        dataSearch = orjson.loads(dataSearch)
    else:
        dataSearch = {}
    # Удваиваем все спреды по направлениям
    spreads = expand_spreads_with_directions(spreads)
    # Сортировка
    if dataSearch.get('filter_history') and dataSearch['filter_history'] != 'current':
        sort_key_funcs = {
            '1d': take1d,
            '3d': take3d,
            '7d': take7d,
            '30d': take30d,
        }
        sort_func = sort_key_funcs.get(dataSearch['filter_history'], take1d)
        spreads.sort(key=lambda x: sort_func(x, x[-1]), reverse=True)
    elif dataSearch.get('filter_course_or_spread') == '1':
        spreads.sort(key=lambda x: takeCourseReverse(x, x[-1]), reverse=True)
    else:
        spreads.sort(key=lambda x: takeSecondReverse(x, x[-1]), reverse=True)
    # Обработка и генерация кнопок
    seen_symbols = set()
    inlines_spreads = []
    for spread in spreads:
        symbol = spread[1]
        if symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)
        # Определяем направление
        if isinstance(spread[-1], str) and spread[-1] in ['normal', 'reverse']:
            spread_data = spread[:-1]
            direction = spread[-1]
        else:
            spread_data = spread
            direction = 'normal'

        # Исторический режим — отрисовываем соответствующую кнопку и пропускаем остальное
        if dataSearch.get('filter_history') and dataSearch['filter_history'] != 'current':
            history_map = {
                '1d': build_inline_button_history_1d,
                '3d': build_inline_button_history_3d,
                '7d': build_inline_button_history_7d,
                '30d': build_inline_button_history_30d,
            }
            builder = history_map.get(dataSearch['filter_history'])
            if builder:
                inlines_spreads.append(builder(spread_data, direction))
            continue

        # Фильтр "по курсу"
        if dataSearch.get('filter_course_or_spread') == '1':
            # Только крупные?
            if dataSearch.get('filter_big_or_all_course') == '1':
                if direction == 'normal' and check_spread_futures(spread_data) <= 0:
                    continue  # Мелкий — пропускаем
                elif direction == 'reverse' and check_spread_futures_reverse(spread_data) <= 0:
                    continue
            # Добавляем кнопку по направлению
            if direction == 'normal':
                inlines_spreads.append(build_inline_button_futures(spread))
            elif direction == 'reverse':
                inlines_spreads.append(build_inline_button_futures(spread, 'negative'))
            continue

        # Фильтр только крупных спредов (по умолчанию)
        if dataSearch.get('filter_big_or_all_course') == '1':
            if direction == 'normal' and check_spread_futures(spread_data) <= 0:
                continue  # Мелкий — пропускаем
            elif direction == 'reverse' and check_spread_futures_reverse(spread_data) <= 0:
                continue

        # По умолчанию — отображаем по направлению
        if direction == 'normal':
            inlines_spreads.append(build_inline_button_spot(spread))
        elif direction == 'reverse':
            inlines_spreads.append(build_inline_button_spot(spread, 'negative'))

    return inlines_spreads, dataSearch, active

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


def filter_spreads_dex(spreads, markets_dict_futures, dataSearch, blacklist_dex, active):
    # Удаляем спреды с неактивными рынками

    spreads = [
        s for s in spreads
        if markets_dict_futures.get(s[2], 0) != 0
           and markets_dict_futures.get(s[3], 0) != 0
           and extract_token_key(s[1]) not in blacklist_dex  # 🔥 проверка чёрного списка
    ]
    # Парсим фильтры
    if dataSearch != 'no':
        dataSearch = orjson.loads(dataSearch)
    else:
        dataSearch = {}

    if dataSearch.get('filter_course_or_spread') == '1':
        spreads.sort(key=lambda x: takeCourseDex(x), reverse=True)
    else:
        spreads.sort(key=lambda x: takeSecondDex(x), reverse=True)
    # Обработка и генерация кнопок
    seen_symbols = set()
    inlines_spreads = []
    for spread in spreads:
        symbol = spread[1]
        if symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)

        # Фильтр "по курсу"
        if dataSearch.get('filter_course_or_spread') == '1':
            # Только крупные?
            if dataSearch.get('filter_big_or_all_course') == '1':
                if check_spread_futures_dex(spread) <= 0:
                    continue  # Мелкий — пропускаем
            # Добавляем кнопку по направлению
            inlines_spreads.append(build_inline_button_spread_in_dex(spread))
            continue

        # Фильтр только крупных спредов (по умолчанию)
        if dataSearch.get('filter_big_or_all_course') == '1':
            if check_spread_futures_dex(spread) <= 0:
                continue  # Мелкий — пропускаем

        inlines_spreads.append(build_inline_button_spread_of_funding_dex(spread))


    return inlines_spreads, dataSearch, active


def filter_spreads_markets(spreads, markets_dict_futures, dataSearch, active):
    # Удаляем спреды с неактивными рынками
    spreads = [s for s in spreads if markets_dict_futures.get(s[2], 0) != 0 and markets_dict_futures.get(s[3], 0) != 0]

    # Парсим фильтры
    if dataSearch != 'no':
        dataSearch = orjson.loads(dataSearch)
    else:
        dataSearch = {}

    # Удваиваем все спреды по направлениям
    spreads = expand_spreads_with_directions(spreads)

    # Сортировка
    if dataSearch.get('filter_history') and dataSearch['filter_history'] != 'current':
        sort_key_funcs = {
            '1d': take1d,
            '3d': take3d,
            '7d': take7d,
            '30d': take30d,
        }
        sort_func = sort_key_funcs.get(dataSearch['filter_history'], take1d)
        spreads.sort(key=lambda x: sort_func(x, x[-1]), reverse=True)
    elif dataSearch.get('filter_course_or_spread') == '1':
        spreads.sort(key=lambda x: takeCourseReverse(x, x[-1]), reverse=True)
    else:
        spreads.sort(key=lambda x: takeSecondReverse(x, x[-1]), reverse=True)

    # Обработка и генерация кнопок
    inlines_spreads = []
    for spread in spreads:
        # Определяем направление
        if isinstance(spread[-1], str) and spread[-1] in ['normal', 'reverse']:
            spread_data = spread[:-1]
            direction = spread[-1]
        else:
            spread_data = spread
            direction = 'normal'

        # Исторический режим — отрисовываем соответствующую кнопку и пропускаем остальное
        if dataSearch.get('filter_history') and dataSearch['filter_history'] != 'current':
            history_map = {
                '1d': build_inline_button_markets_futures_history_1d,
                '3d': build_inline_button_markets_futures_history_3d,
                '7d': build_inline_button_markets_futures_history_7d,
                '30d': build_inline_button_markets_futures_history_30d,
            }
            builder = history_map.get(dataSearch['filter_history'])
            if builder:
                inlines_spreads.append(builder(spread_data, direction, spread_data[6] != spread_data[7]))
            continue

        # Фильтр "по курсу"
        if dataSearch.get('filter_course_or_spread') == '1':
            # Только крупные?
            if dataSearch.get('filter_big_or_all_course') == '1':
                if direction == 'normal' and check_spread_futures(spread_data) <= 0:
                    continue  # Мелкий — пропускаем
                elif direction == 'reverse' and check_spread_futures_reverse(spread_data) <= 0:
                    continue
            # Добавляем кнопку по направлению
            if direction == 'normal':
                inlines_spreads.append(build_inline_button_markets_futures(spread_data, spread_data[6] != spread_data[7]))
            elif direction == 'reverse':
                inlines_spreads.append(build_inline_button_markets_futures_negative(spread_data, spread_data[6] != spread_data[7]))
            continue

        # Фильтр только крупных спредов (по умолчанию)
        if dataSearch.get('filter_big_or_all_course') == '1':
            if direction == 'normal' and check_spread_futures(spread_data) <= 0:
                continue  # Мелкий — пропускаем
            elif direction == 'reverse' and check_spread_futures_reverse(spread_data) <= 0:
                continue

        # По умолчанию — отображаем по направлению
        if direction == 'normal':
            inlines_spreads.append(build_inline_button_markets_futures(spread_data, spread_data[6] != spread_data[7]))
        elif direction == 'reverse':
            inlines_spreads.append(build_inline_button_markets_futures_negative(spread_data, spread_data[6] != spread_data[7]))
    return inlines_spreads, dataSearch, active


def get_user_spot_markets(spreads, accounts, user_id, dataSearch=None):
    active = False
    for acc in accounts:
        if str(acc[2]) == str(user_id) and any(x == '1' for x in [acc[9], acc[10], acc[14]]):
            marketslistspot = orjson.loads(acc[6])
            markets_dict_spot = {market.split('_')[0]: int(market.split('_')[1]) for market in marketslistspot}
            if dataSearch is None:
                dataSearch = acc[4]
            active = True
            return filter_spreads_spot_markets(spreads, markets_dict_spot, dataSearch, active)
    return [], [], active


def get_user_spot_spreads(spreads, accounts, user_id, dataSearch=None):
    active = False
    for acc in accounts:
        if str(acc[2]) == str(user_id) and any(x == '1' for x in [acc[9], acc[10], acc[14]]):
            marketslistspot = orjson.loads(acc[6])
            markets_dict_spot = {market.split('_')[0]: int(market.split('_')[1]) for market in marketslistspot}
            if dataSearch is None:
                dataSearch = acc[4]
            try:
                if acc[8] == b'no':
                    blacklist = set()
                else:
                    decompressed = zlib.decompress(acc[8])
                    coins_dict = orjson.loads(decompressed.decode('utf-8'))
                    blacklist = set(coins_dict.keys())
            except Exception:
                blacklist = set()
            active = True
            return filter_spreads_spot(spreads, markets_dict_spot, dataSearch, blacklist, active)
    return [], [], active


def get_user_spreads(spreads, accounts, user_id, dataSearch=None):
    active = False
    for acc in accounts:
        if str(acc[2]) == str(user_id) and any(x == '1' for x in [acc[9], acc[10], acc[14]]):
            marketslistfutures = orjson.loads(acc[5])
            markets_dict_futures = {market.split('_')[0]: int(market.split('_')[1]) for market in marketslistfutures}
            if dataSearch is None:
                dataSearch = acc[4]
            active = True
            try:
                if acc[8] == b'no':
                    blacklist = set()
                else:
                    decompressed = zlib.decompress(acc[8])
                    coins_dict = orjson.loads(decompressed.decode('utf-8'))
                    blacklist = set(coins_dict.keys())
            except Exception:
                blacklist = set()
            return filter_spreads(spreads, markets_dict_futures, dataSearch, blacklist, active)
    return [], [], active


def get_user_spreads_dex(spreads, accounts, user_id, dataSearch=None):
    active = False
    for acc in accounts:
        if str(acc[2]) == str(user_id) and any(x == '1' for x in [acc[9], acc[10], acc[14]]):
            marketslistfutures = orjson.loads(acc[5])
            markets_dict_futures = {market.split('_')[0]: int(market.split('_')[1]) for market in marketslistfutures}
            if dataSearch is None:
                dataSearch = acc[4]
            active = True
            try:
                if acc[16] == b'no':
                    blacklist_dex = set()
                else:
                    decompressed = zlib.decompress(acc[16])
                    coins_dict = orjson.loads(decompressed.decode('utf-8'))
                    blacklist_dex = set(coins_dict.keys())
            except Exception:
                blacklist_dex = set()
            return filter_spreads_dex(spreads, markets_dict_futures, dataSearch, blacklist_dex, active)
    return [], [], active

def get_user_markets(spreads, accounts, user_id, dataSearch=None):
    active = False
    for acc in accounts:
        if str(acc[2]) == str(user_id) and any(x == '1' for x in [acc[9], acc[10], acc[14]]):
            marketslistfutures = orjson.loads(acc[5])
            markets_dict_futures = {market.split('_')[0]: int(market.split('_')[1]) for market in marketslistfutures}
            if dataSearch is None:
                dataSearch = acc[4]
            active = True
            return filter_spreads_markets(spreads, markets_dict_futures, dataSearch, active)
    return [], [], active


def check_spread_futures(spread):
    return round(((float(spread[8]) / float(spread[20])) - 1) * 100, 2)

def check_spread_futures_dex(spread):
    return spread[6]

def check_spread_futures_reverse(spread):
    return round(((float(spread[9]) / float(spread[19])) - 1) * 100, 2)


def check_spread_spot(spread):
    return round(((float(spread[6]) / float(spread[16])) - 1) * 100, 2)


def build_inline_button_markets_futures(spread, time):
    symbol = '🕓' if time else ''
    return InlineKeyboardButton(text=f'{spread[3]} - {spread[2]}: {spread[14]}% | {round(((float(spread[8]) / float(spread[20])) - 1) * 100, 2)}  вход {symbol}',
                         callback_data=f'id{spread[0]}_{spread[3]}_{spread[2]}_{spread[1]}')


def build_inline_button_markets_futures_negative(spread, time):
    symbol = '🕓' if time else ''

    return InlineKeyboardButton(text=f'{spread[2]} - {spread[3]}: {round(float(spread[5]) - float(spread[4]),2)}% | {round(((float(spread[9]) / float(spread[19])) - 1) * 100, 2)}  вход {symbol}',
                         callback_data=f'id{spread[0]}_{spread[2]}_{spread[3]}_{spread[1]}')


def build_inline_button_markets_spot_futures_history_1d(spread):
    if spread[17] is not None:
        return InlineKeyboardButton(text=
                f'{spread[2]} - {spread[3]}: {spread[4]}% | {spread[17]}% 1Д', callback_data=f'spot_id{spread[0]}_{spread[2]}_{spread[3]}_{spread[1]}')


def build_inline_button_markets_spot_futures_history_3d(spread):
    if spread[18] is not None:
        return InlineKeyboardButton(text=
                f'{spread[2]} - {spread[3]}: {spread[4]}% | {spread[18]}% 3Д', callback_data=f'spot_id{spread[0]}_{spread[2]}_{spread[3]}_{spread[1]}')


def build_inline_button_markets_spot_futures_history_7d(spread):
    if spread[19] is not None:
        return InlineKeyboardButton(text=
                f'{spread[2]} - {spread[3]}: {spread[4]}% | {spread[19]}% 1Н', callback_data=f'spot_id{spread[0]}_{spread[2]}_{spread[3]}_{spread[1]}')


def build_inline_button_markets_spot_futures_history_30d(spread):
    if spread[20] is not None:
        return InlineKeyboardButton(text=
                f'{spread[2]} - {spread[3]}: {spread[4]}% | {spread[20]}% 1М', callback_data=f'spot_id{spread[0]}_{spread[2]}_{spread[3]}_{spread[1]}')


def build_inline_button_markets_futures_history_1d(spread, direction, time):
    symbol = '🕓' if time else ''
    if direction == 'normal':
        val_a, val_b = spread[21], spread[25]
        exchange_a, exchange_b = spread[3], spread[2]
        spread_val = round(spread[4] - spread[5], 2)
    else:
        val_a, val_b = spread[25], spread[21]
        exchange_a, exchange_b = spread[2], spread[3]
        spread_val = round(spread[5] - spread[4], 2)

    if val_a != '' and val_b != '':
        return InlineKeyboardButton(
            text=f'{exchange_a} - {exchange_b}: {spread_val}% | {round(val_a - val_b, 2)}% 1Д {symbol}',
            callback_data=f'id{spread[0]}_{exchange_a}_{exchange_b}_{spread[1]}')
    elif val_a != '':
        return InlineKeyboardButton(
            text=f'{exchange_a} - {exchange_b}: {spread_val}% | {val_a}% 1Д {symbol}',
            callback_data=f'id{spread[0]}_{exchange_a}_{exchange_b}_{spread[1]}')
    elif val_b != '':
        return InlineKeyboardButton(
            text=f'{exchange_a} - {exchange_b}: {spread_val}% | {val_b}% 1Д {symbol}',
            callback_data=f'id{spread[0]}_{exchange_a}_{exchange_b}_{spread[1]}')


def build_inline_button_markets_futures_history_3d(spread, direction, time):
    symbol = '🕓' if time else ''
    if direction == 'normal':
        val_a, val_b = spread[22], spread[26]
        exchange_a, exchange_b = spread[3], spread[2]
        spread_val = round(spread[4] - spread[5], 2)
    else:
        val_a, val_b = spread[26], spread[22]
        exchange_a, exchange_b = spread[2], spread[3]
        spread_val = round(spread[5] - spread[4], 2)

    if val_a != '' and val_b != '':
        return InlineKeyboardButton(
            text=f'{exchange_a} - {exchange_b}: {spread_val}% | {round(val_a - val_b, 2)}% 3Д {symbol}',
            callback_data=f'id{spread[0]}_{exchange_a}_{exchange_b}_{spread[1]}')
    elif val_a != '':
        return InlineKeyboardButton(
            text=f'{exchange_a} - {exchange_b}: {spread_val}% | {val_a}% 3Д {symbol}',
            callback_data=f'id{spread[0]}_{exchange_a}_{exchange_b}_{spread[1]}')
    elif val_b != '':
        return InlineKeyboardButton(
            text=f'{exchange_a} - {exchange_b}: {spread_val}% | {val_b}% 3Д {symbol}',
            callback_data=f'id{spread[0]}_{exchange_a}_{exchange_b}_{spread[1]}')


def build_inline_button_markets_futures_history_7d(spread, direction, time):
    symbol = '🕓' if time else ''
    if direction == 'normal':
        val_a, val_b = spread[23], spread[27]
        exchange_a, exchange_b = spread[3], spread[2]
        spread_val = round(spread[4] - spread[5], 2)
    else:
        val_a, val_b = spread[27], spread[23]
        exchange_a, exchange_b = spread[2], spread[3]
        spread_val = round(spread[5] - spread[4], 2)

    if val_a != '' and val_b != '':
        return InlineKeyboardButton(
            text=f'{exchange_a} - {exchange_b}: {spread_val}% | {round(val_a - val_b, 2)}% 1Н {symbol}',
            callback_data=f'id{spread[0]}_{exchange_a}_{exchange_b}_{spread[1]}')
    elif val_a != '':
        return InlineKeyboardButton(
            text=f'{exchange_a} - {exchange_b}: {spread_val}% | {val_a}% 1Н {symbol}',
            callback_data=f'id{spread[0]}_{exchange_a}_{exchange_b}_{spread[1]}')
    elif val_b != '':
        return InlineKeyboardButton(
            text=f'{exchange_a} - {exchange_b}: {spread_val}% | {val_b}% 1Н {symbol}',
            callback_data=f'id{spread[0]}_{exchange_a}_{exchange_b}_{spread[1]}')


def build_inline_button_markets_futures_history_30d(spread, direction, time):
    symbol = '🕓' if time else ''
    if direction == 'normal':
        val_a, val_b = spread[24], spread[28]
        exchange_a, exchange_b = spread[3], spread[2]
        spread_val = round(spread[4] - spread[5], 2)
    else:
        val_a, val_b = spread[28], spread[24]
        exchange_a, exchange_b = spread[2], spread[3]
        spread_val = round(spread[5] - spread[4], 2)

    if val_a != '' and val_b != '':
        return InlineKeyboardButton(
            text=f'{exchange_a} - {exchange_b}: {spread_val}% | {round(val_a - val_b, 2)}% 1М {symbol}',
            callback_data=f'id{spread[0]}_{exchange_a}_{exchange_b}_{spread[1]}')
    elif val_a != '':
        return InlineKeyboardButton(
            text=f'{exchange_a} - {exchange_b}: {spread_val}% | {val_a}% 1М {symbol}',
            callback_data=f'id{spread[0]}_{exchange_a}_{exchange_b}_{spread[1]}')
    elif val_b != '':
        return InlineKeyboardButton(
            text=f'{exchange_a} - {exchange_b}: {spread_val}% | {val_b}% 1М {symbol}',
            callback_data=f'id{spread[0]}_{exchange_a}_{exchange_b}_{spread[1]}')


def build_inline_button_futures(spread, direction='normal'):
    if direction == 'normal':
        val = round(((float(spread[8]) / float(spread[20])) - 1) * 100, 2)
    else:
        val = round(((float(spread[9]) / float(spread[19])) - 1) * 100, 2)
    return InlineKeyboardButton(
        text=f'{spread[1]}: {val} вход',
        callback_data=f'market:{spread[1]}'
    )


# DEX-specific builders — возвращают dex_market callbacks
def build_inline_button_spread_in_dex(spread):
    # spread tuple: (0, symbol, 'DEX', market2, dex_bid, price_usd, diff, ...)
    val = spread[6]
    # mode 'in' — вход (spread)
    chain, symbol = spread[1].split('_')
    symbol = symbol[:-4]
    return InlineKeyboardButton(
        text=f'{symbol} [{chain}]: {val} вход',
        callback_data=f'dex_market:in:{spread[1]}'
    )

def build_inline_button_spread_of_funding_dex(spread):
    spread_val = spread[13] if len(spread) > 13 else 0
    # mode 'fund' — funding
    chain, symbol = spread[1].split('_')
    symbol = symbol[:-4]
    return InlineKeyboardButton(
        text=f'{symbol} [{chain}]: {spread_val}% фанд',
        callback_data=f'dex_market:fund:{spread[1]}'
    )

def build_inline_button_markets_spot_futures(spread):
    return InlineKeyboardButton(text=
            f'{spread[2]} - {spread[3]}: {spread[4]}% | {round(((float(spread[6]) / float(spread[16])) - 1) * 100, 2)}  вход',
                     callback_data=f'spot_id{spread[0]}_{spread[2]}_{spread[3]}_{spread[1]}')


def build_inline_button_spot_futures(spread):
    return InlineKeyboardButton(
        text=f'{spread[1]}: {round(((float(spread[6]) / float(spread[16])) - 1) * 100, 2)} вход',
                                                    callback_data=f'spot_market:{spread[1]}')


def build_inline_button_spot_big(spread):
    return InlineKeyboardButton(text=f'{spread[1]}: {spread[4]}% тек', callback_data=f'spot_market:{spread[1]}')


def build_inline_button_spot(spread, direction='normal'):
    if direction == 'normal':
        spread_val = round(spread[4] - spread[5], 2)
    else:
        spread_val = round(spread[5] - spread[4], 2)
    return InlineKeyboardButton(text=f'{spread[1]}: {spread_val}% тек', callback_data=f'market:{spread[1]}')


# СПОТ
def build_inline_button_spot_futures_history_1d(spread):
    if spread[17] != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {spread[17]}% 1Д', callback_data=f'spot_market:{spread[1]}')


def build_inline_button_spot_futures_history_3d(spread):
    if spread[18] != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {spread[18]}% 3Д', callback_data=f'spot_market:{spread[1]}')


def build_inline_button_spot_futures_history_7d(spread):
    if spread[19] != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {spread[19]}% 1Н', callback_data=f'spot_market:{spread[1]}')


def build_inline_button_spot_futures_history_30d(spread):
    if spread[20] != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {spread[20]}% 1М', callback_data=f'spot_market:{spread[1]}')


# ФЬЮЧЕРСЫ
def build_inline_button_history_1d(spread, direction):
    if direction == 'normal':
        val_a, val_b = spread[21], spread[25]
        spread_val = round(spread[4] - spread[5], 2)
    else:
        val_a, val_b = spread[25], spread[21]
        spread_val = round(spread[5] - spread[4], 2)

    if val_a != '' and val_b != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {round(val_a - val_b, 2)}% 1Д',
            callback_data=f'market:{spread[1]}'
        )
    elif val_a != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {val_a}% 1Д',
            callback_data=f'market:{spread[1]}'
        )
    elif val_b != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {val_b}% 1Д',
            callback_data=f'market:{spread[1]}'
        )


def build_inline_button_history_3d(spread, direction):

    if direction == 'normal':
        val_a, val_b = spread[22], spread[26]
    else:
        val_a, val_b = spread[26], spread[22]

    if val_a != '' and val_b != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {round(val_a - val_b, 2)}% 3Д',
            callback_data=f'market:{spread[1]}'
        )
    elif val_a != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {val_a}% 3Д',
            callback_data=f'market:{spread[1]}'
        )
    elif val_b != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {val_b}% 3Д',
            callback_data=f'market:{spread[1]}'
        )


def build_inline_button_history_7d(spread, direction):

    if direction == 'normal':
        val_a, val_b = spread[23], spread[27]
    else:
        val_a, val_b = spread[27], spread[23]

    if val_a != '' and val_b != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {round(val_a - val_b, 2)}% 7Д',
            callback_data=f'market:{spread[1]}'
        )
    elif val_a != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {val_a}% 7Д',
            callback_data=f'market:{spread[1]}'
        )
    elif val_b != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {val_b}% 7Д',
            callback_data=f'market:{spread[1]}'
        )


def build_inline_button_history_30d(spread, direction):

    if direction == 'normal':
        val_a, val_b = spread[24], spread[28]
    else:
        val_a, val_b = spread[28], spread[24]

    if val_a != '' and val_b != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {round(val_a - val_b, 2)}% 30Д',
            callback_data=f'market:{spread[1]}'
        )
    elif val_a != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {val_a}% 30Д',
            callback_data=f'market:{spread[1]}'
        )
    elif val_b != '':
        return InlineKeyboardButton(
            text=f'{spread[1]}: {val_b}% 30Д',
            callback_data=f'market:{spread[1]}'
        )


def change_to_big(accounts, dataSearch, id):
    page_start = 0

    if len(accounts) > 0:
        for acc in accounts:
            if str(acc[2]) == str(id):
                dataSearch = acc[4]
                break

    if dataSearch == 'no':
        dataSearch = {}
        dataSearch['filter_big_or_all_course'] = '1'
        dataSearch['spread'] = 'no'
        dataSearch['course_spread'] = 'no'
        data_s = orjson.dumps(dataSearch)
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()
        cursor.execute('''
                                         UPDATE Users SET dataSearch=%s WHERE tgid=%s
                                         ''', (data_s, id))
        connection.commit()
        connection.close()
        dataSearch = orjson.dumps(dataSearch)
    elif dataSearch != 'no':
        dataSearch = orjson.loads(dataSearch)
        dataSearch['filter_big_or_all_course'] = '1'
        data_s = orjson.dumps(dataSearch)
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()
        cursor.execute('''
                                                 UPDATE Users SET dataSearch=%s WHERE tgid=%s
                                                 ''', (data_s, id))
        connection.commit()
        connection.close()
        dataSearch = orjson.dumps(dataSearch)
    return page_start, dataSearch


def change_to_all(accounts, dataSearch, id):
    page_start = 0

    if len(accounts) > 0:
        for acc in accounts:
            if str(acc[2]) == str(id):
                dataSearch = acc[4]
                break

    if dataSearch == 'no':
        dataSearch = {}
        dataSearch['filter_big_or_all_course'] = '0'
        dataSearch['spread'] = 'no'
        dataSearch['course_spread'] = 'no'
        data_s = orjson.dumps(dataSearch)
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()
        cursor.execute('''
                                     UPDATE Users SET dataSearch=%s WHERE tgid=%s
                                     ''', (data_s, id))
        connection.commit()
        connection.close()
        dataSearch = orjson.dumps(dataSearch)
    elif dataSearch != 'no':
        dataSearch = orjson.loads(dataSearch)
        dataSearch['filter_big_or_all_course'] = '0'
        data_s = orjson.dumps(dataSearch)
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()
        cursor.execute('''
                                             UPDATE Users SET dataSearch=%s WHERE tgid=%s
                                             ''', (data_s, id))
        connection.commit()
        connection.close()
        dataSearch = orjson.dumps(dataSearch)
    return page_start, dataSearch


def change_to_spread(accounts, dataSearch, id):
    page_start = 0

    if len(accounts) > 0:
        for acc in accounts:
            if str(acc[2]) == str(id):
                dataSearch = acc[4]
                break

    if dataSearch == 'no':
        dataSearch = {}
        dataSearch['filter_course_or_spread'] = '1'
        dataSearch['spread'] = 'no'
        dataSearch['course_spread'] = 'no'
        data_s = orjson.dumps(dataSearch)
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()
        cursor.execute('''
                                 UPDATE Users SET dataSearch=%s WHERE tgid=%s
                                 ''', (data_s, id))
        connection.commit()
        connection.close()
        dataSearch = orjson.dumps(dataSearch)
    elif dataSearch != 'no':
        dataSearch = orjson.loads(dataSearch)
        dataSearch['filter_course_or_spread'] = '1'
        data_s = orjson.dumps(dataSearch)
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()
        cursor.execute('''
                                         UPDATE Users SET dataSearch=%s WHERE tgid=%s
                                         ''', (data_s, id))
        connection.commit()
        connection.close()
        dataSearch = orjson.dumps(dataSearch)
    return page_start, dataSearch


def change_to_course(accounts, dataSearch, id):
    page_start = 0

    if len(accounts) > 0:
        for acc in accounts:
            if str(acc[2]) == str(id):
                dataSearch = acc[4]
                break

    if dataSearch == 'no':
        dataSearch = {}
        dataSearch['filter_course_or_spread'] = '0'
        dataSearch['spread'] = 'no'
        dataSearch['course_spread'] = 'no'
        data_s = orjson.dumps(dataSearch)
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()
        cursor.execute('''
                                 UPDATE Users SET dataSearch=%s WHERE tgid=%s
                                 ''', (data_s, id))
        connection.commit()
        connection.close()
        dataSearch = orjson.dumps(dataSearch)
    elif dataSearch != 'no':
        dataSearch = orjson.loads(dataSearch)
        dataSearch['filter_course_or_spread'] = '0'
        data_s = orjson.dumps(dataSearch)
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()
        cursor.execute('''
                                         UPDATE Users SET dataSearch=%s WHERE tgid=%s
                                         ''', (data_s, id))
        connection.commit()
        connection.close()
        dataSearch = orjson.dumps(dataSearch)

    return page_start, dataSearch


def change_to_d(accounts, dataSearch, id, d):
    """
    Теперь переключение истории отключено: независимо от d ('1d','3d','7d','30d','current')
    мы сохраняем только 'current' в dataSearch['filter_history'].
    Возвращаем page_start=0 и json-представление dataSearch.
    """
    page_start = 0

    # Найдём dataSearch из аккаунтов, если передано
    if len(accounts) > 0:
        for acc in accounts:
            if str(acc[2]) == str(id):
                dataSearch = acc[4]
                break

    # Всегда ставим 'current' — таким образом пользователю нельзя переключиться
    # на исторические диапазоны, но исторические данные остаются в структуре записей.
    if dataSearch == 'no' or dataSearch is None:
        dataSearch = {}
        dataSearch['filter_history'] = 'current'
        dataSearch['spread'] = 'no'
        dataSearch['course_spread'] = 'no'
        data_s = orjson.dumps(dataSearch)
        try:
            connection = mysql.connector.connect(
                host=DB_HOST,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE
            )
            cursor = connection.cursor()
            cursor.execute('UPDATE Users SET dataSearch=%s WHERE tgid=%s', (data_s, id))
            connection.commit()
            connection.close()
        except Exception as e:
            print(f"change_to_d: error saving dataSearch for user {id}: {e}")
        dataSearch = orjson.dumps(dataSearch)
    else:
        # если есть dataSearch — распакуем, перезапишем filter_history как 'current' и сохраним
        try:
            dataSearch = orjson.loads(dataSearch)
        except Exception:
            dataSearch = {}
        dataSearch['filter_history'] = 'current'
        data_s = orjson.dumps(dataSearch)
        try:
            connection = mysql.connector.connect(
                host=DB_HOST,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE
            )
            cursor = connection.cursor()
            cursor.execute('UPDATE Users SET dataSearch=%s WHERE tgid=%s', (data_s, id))
            connection.commit()
            connection.close()
        except Exception as e:
            print(f"change_to_d: error updating dataSearch for user {id}: {e}")
        dataSearch = orjson.dumps(dataSearch)

    return page_start, dataSearch


def create_pagination_buttons(inlines_spreads, inline_kb1, type, page_start=0, symbolFind=None, main_prev=0):
    items_per_page = 5
    len_list = len(inlines_spreads)
    try:
        page_start_int = int(page_start)
    except Exception:
        page_start_int = 0

    # total pages (количество страниц)
    all_pages = (len_list + items_per_page - 1) // items_per_page if len_list > 0 else 1
    # current page = 1-based
    current_page = max(1, page_start_int + 1)

    # Добавляем элементы текущей страницы
    page_start_index = page_start_int * items_per_page
    page_end = page_start_index + items_per_page
    for i in range(page_start_index, min(page_end, len_list)):
        btn = inlines_spreads[i]
        # Special-case для dex_market (сохраняем callback с текущей main page), оставляем прежнюю логику
        if type == 'dex_page_from':
            try:
                cb = getattr(btn, 'callback_data', None)
                text = getattr(btn, 'text', None)
                if cb and isinstance(cb, str) and cb.startswith('dex_market:'):
                    symbol = cb.split(':', 1)[1] if ':' in cb else ''
                    page_number = page_start_int
                    new_cb = f'dex_market:{symbol}:{page_number}'
                    inline_kb1.row(
                        InlineKeyboardButton(text=text or btn.text, callback_data=new_cb)
                    )
                    continue
            except Exception:
                pass

        inline_kb1.row(btn)

    # prev / center / next offsets (page_start_int is 0-based index)
    prev_offset = max(0, page_start_int - 1)
    next_offset = min(all_pages - 1, page_start_int + 1)

    # Формируем callback-строки в зависимости от типа
    if type == 'page_from':
        prev_button = InlineKeyboardButton(text='<', callback_data=f'page_from:{prev_offset}')
        pages_button = InlineKeyboardButton(text=f'{current_page}/{all_pages}', callback_data=f'page_from:0')
        next_button = InlineKeyboardButton(text='>', callback_data=f'page_from:{next_offset}')
    elif type == 'spot_page_from':
        prev_button = InlineKeyboardButton(text='<', callback_data=f'spot_page_from:{prev_offset}')
        pages_button = InlineKeyboardButton(text=f'{current_page}/{all_pages}', callback_data=f'spot_page_from:0')
        next_button = InlineKeyboardButton(text='>', callback_data=f'spot_page_from:{next_offset}')
    elif type == 'page_market':
        prev_button = InlineKeyboardButton(text='<', callback_data=f'page_market:{prev_offset}:{symbolFind}')
        pages_button = InlineKeyboardButton(text=f'{current_page}/{all_pages}', callback_data=f'page_market:0:{symbolFind}')
        next_button = InlineKeyboardButton(text='>', callback_data=f'page_market:{next_offset}:{symbolFind}')
    elif type == 'spot_page_market':
        prev_button = InlineKeyboardButton(text='<', callback_data=f'spot_page_market:{prev_offset}:{symbolFind}')
        pages_button = InlineKeyboardButton(text=f'{current_page}/{all_pages}', callback_data=f'spot_page_market:0:{symbolFind}')
        next_button = InlineKeyboardButton(text='>', callback_data=f'spot_page_market:{next_offset}:{symbolFind}')
    elif type == 'dex_page_from':
        prev_button = InlineKeyboardButton(text='<', callback_data=f'dex_page_from:{prev_offset}:{symbolFind or ""}')
        pages_button = InlineKeyboardButton(text=f'{current_page}/{all_pages}', callback_data=f'dex_page_from:0:{symbolFind or ""}')
        next_button = InlineKeyboardButton(text='>', callback_data=f'dex_page_from:{next_offset}:{symbolFind or ""}')
    elif type == 'dex_market_page':
        parts = (symbolFind or '').split(':', 1)
        if len(parts) == 2:
            mode, sym = parts[0], parts[1]
        else:
            mode, sym = '', ''
        prev_button = InlineKeyboardButton(text='<',
                                           callback_data=f'dex_market_from:{prev_offset}:{mode}:{sym}:{main_prev}')
        pages_button = InlineKeyboardButton(text=f'{current_page}/{all_pages}',
                                            callback_data=f'dex_market_from:0:{mode}:{sym}:{main_prev}')
        next_button = InlineKeyboardButton(text='>',
                                           callback_data=f'dex_market_from:{next_offset}:{mode}:{sym}:{main_prev}')
    else:
        # default fallback to page_from-style callbacks
        prev_button = InlineKeyboardButton(text='<', callback_data=f'page_from:{prev_offset}')
        pages_button = InlineKeyboardButton(text=f'{current_page}/{all_pages}', callback_data=f'page_from:0')
        next_button = InlineKeyboardButton(text='>', callback_data=f'page_from:{next_offset}')

    inline_kb1.row(prev_button, pages_button, next_button)
    return inline_kb1



def add_filter_buttons_futures(inline_kb1, dataSearch):
    """
    Убраны кнопки истории (current/1d/3d/7d/30d).
    Оставляем только две строки: выбор All/Big/Course/Spread + навигацию (page/coin).
    """
    # Кнопки фильтров (формирование кнопок уже есть выше в модуле)
    # предполагаем, что button_filter_* функции/объекты определены в модуле
    # (мы используем их — но не добавляем истории)
    if dataSearch != 'no' and 'filter_course_or_spread' in dataSearch:
        if dataSearch['filter_course_or_spread'] == '1':
            # показываем Course / Big-ALL варианты
            if 'filter_big_or_all_course' in dataSearch and dataSearch['filter_big_or_all_course'] == '1':
                inline_kb1.row(button_filter_big_course, button_filter_course)
            else:
                inline_kb1.row(button_filter_all_course, button_filter_course)
            # строка навигации: page / coin (убрали current)
            inline_kb1.row(button_filter_page, button_filter_coin)
        else:
            # filter_course_or_spread == '0' -> spread mode
            if 'filter_big_or_all_course' in dataSearch and dataSearch['filter_big_or_all_course'] == '1':
                inline_kb1.row(button_filter_big_course, button_filter_spread)
            else:
                inline_kb1.row(button_filter_all_course, button_filter_spread)
            inline_kb1.row(button_filter_page, button_filter_coin)
    else:
        # default view
        inline_kb1.row(button_filter_all_course, button_filter_spread)
        inline_kb1.row(button_filter_page, button_filter_coin)


def add_filter_buttons_futures_market(inline_kb1, dataSearch, symbolFind):
    """
    Версия для страницы по конкретной монете: убраны кнопки истории.
    Безопасно парсит dataSearch, если тот приходит как JSON-строка.
    """
    # подготовка кнопок
    button_filter_big_course = get_button_filter_big_course(symbolFind)
    button_filter_course = get_button_filter_course(symbolFind)
    button_filter_all_course = get_button_filter_all_course(symbolFind)
    button_filter_spread = get_button_filter_spread(symbolFind)

    # безопасно распарсить dataSearch, если это JSON-строка (и не 'no')
    parsed = 'no'
    try:
        if dataSearch is None:
            parsed = 'no'
        elif isinstance(dataSearch, (bytes, bytearray)):
            s = dataSearch.decode('utf-8', errors='ignore')
            parsed = orjson.loads(s) if s != 'no' else 'no'
        elif isinstance(dataSearch, str):
            # если строка 'no' — оставляем 'no', иначе пытаемся распарсить json
            if dataSearch == 'no':
                parsed = 'no'
            else:
                try:
                    parsed = orjson.loads(dataSearch)
                except Exception:
                    # если не JSON — считаем, что фильтров нет
                    parsed = {}
        elif isinstance(dataSearch, dict):
            parsed = dataSearch
        else:
            # другие типы — безопасно игнорируем
            parsed = {}
    except Exception:
        parsed = {}

    # Теперь parsed — либо 'no' либо dict
    if parsed != 'no' and isinstance(parsed, dict) and 'filter_course_or_spread' in parsed:
        if parsed['filter_course_or_spread'] == '1':
            if 'filter_big_or_all_course' in parsed and parsed['filter_big_or_all_course'] == '1':
                inline_kb1.row(button_filter_big_course, button_filter_course)
            else:
                inline_kb1.row(button_filter_all_course, button_filter_course)
            inline_kb1.row(button_filter_page, button_filter_coin)
        else:
            if 'filter_big_or_all_course' in parsed and parsed['filter_big_or_all_course'] == '1':
                inline_kb1.row(button_filter_big_course, button_filter_spread)
            else:
                inline_kb1.row(button_filter_all_course, button_filter_spread)
            inline_kb1.row(button_filter_page, button_filter_coin)
    else:
        inline_kb1.row(button_filter_all_course, button_filter_spread)
        inline_kb1.row(button_filter_page, button_filter_coin)



def add_filter_buttons_spot(inline_kb1, dataSearch):
    """
    Spot/фьючерс - убраны кнопки истории.
    """
    if dataSearch != 'no' and 'filter_course_or_spread' in dataSearch:
        if dataSearch['filter_course_or_spread'] == '1':
            if 'filter_big_or_all_course' in dataSearch and dataSearch['filter_big_or_all_course'] == '1':
                inline_kb1.row(button_filter_big_course_spot, button_filter_course_spot)
            else:
                inline_kb1.row(button_filter_all_course_spot, button_filter_course_spot)
            inline_kb1.row(button_filter_page_spot, button_filter_coin_spot)
        else:
            if 'filter_big_or_all_course' in dataSearch and dataSearch['filter_big_or_all_course'] == '1':
                inline_kb1.row(button_filter_big_course_spot, button_filter_spread_spot)
            else:
                inline_kb1.row(button_filter_all_course_spot, button_filter_spread_spot)
            inline_kb1.row(button_filter_page_spot, button_filter_coin_spot)
    else:
        inline_kb1.row(button_filter_all_course_spot, button_filter_spread_spot)
        inline_kb1.row(button_filter_page_spot, button_filter_coin_spot)



def add_filter_buttons_spot_market(inline_kb1, dataSearch, symbolFind):
    """
    Spot-market (по монете) - убраны кнопки истории.
    """
    button_filter_big_course_spot = get_button_filter_big_course_spot(symbolFind)
    button_filter_course_spot = get_button_filter_course_spot(symbolFind)
    button_filter_all_course_spot = get_button_filter_all_course_spot(symbolFind)
    button_filter_spread_spot = get_button_filter_spread_spot(symbolFind)

    if dataSearch != 'no' and 'filter_course_or_spread' in dataSearch:
        if dataSearch['filter_course_or_spread'] == '1':
            if 'filter_big_or_all_course' in dataSearch and dataSearch['filter_big_or_all_course'] == '1':
                inline_kb1.row(button_filter_big_course_spot, button_filter_course_spot)
            else:
                inline_kb1.row(button_filter_all_course_spot, button_filter_course_spot)
            inline_kb1.row(button_filter_page_spot, button_filter_coin_spot)
        else:
            if 'filter_big_or_all_course' in dataSearch and dataSearch['filter_big_or_all_course'] == '1':
                inline_kb1.row(button_filter_big_course_spot, button_filter_spread_spot)
            else:
                inline_kb1.row(button_filter_all_course_spot, button_filter_spread_spot)
            inline_kb1.row(button_filter_page_spot, button_filter_coin_spot)
    else:
        inline_kb1.row(button_filter_all_course_spot, button_filter_spread_spot)
        inline_kb1.row(button_filter_page_spot, button_filter_coin_spot)



button_start = KeyboardButton(text='/start')
button_info = KeyboardButton(text='Информация')
button_spreads = KeyboardButton(text='Фьючерсы 🔄')
button_spot = KeyboardButton(text='Спот/Фьючерсы 🔀')
button_fundingTime = KeyboardButton(text='Подсказка 🕓')
button_marketslist = KeyboardButton(text='Биржи ⚙️')
button_monitoring = KeyboardButton(text='Мониторинг 🔧')
button_add_address = KeyboardButton(text='Добавить адрес')
button_check_address = KeyboardButton(text='Мои адреса')
button_start_test = KeyboardButton(text='Начать тест')
button_blacklist = KeyboardButton(text='Черный список 🔴')
button_dex = KeyboardButton(text="DEX 🌐")

button_admin_panel = KeyboardButton(text='Админ панель')
button_list_paids = KeyboardButton(text='Список оплаты')
button_list_active = KeyboardButton(text='Список активных')
button_add_active = KeyboardButton(text='Дать доступ')
button_off_active = KeyboardButton(text='Убрать доступ')
button_reset_active = KeyboardButton(text='Сбросить доступ')

button_futures_bybit = InlineKeyboardButton(text='Bybit ✅', callback_data='marketlist_futures_bybit')
button_futures_mexc = InlineKeyboardButton(text='Mexc ✅', callback_data='marketlist_futures_mexc')
button_futures_kucoin = InlineKeyboardButton(text='Kucoin ✅', callback_data='marketlist_futures_kucoin')
button_futures_gateio = InlineKeyboardButton(text='Gateio ✅', callback_data='marketlist_futures_gateio')
button_futures_bitget = InlineKeyboardButton(text='Bitget ✅', callback_data='marketlist_futures_bitget')
button_futures_huobi = InlineKeyboardButton(text='Huobi ✅', callback_data='marketlist_futures_huobi')
button_futures_okx = InlineKeyboardButton(text='Okx ✅', callback_data='marketlist_futures_okx')
button_futures_binance = InlineKeyboardButton(text='Binance ✅', callback_data='marketlist_futures_binance')
button_futures_bingx = InlineKeyboardButton(text='BingX ✅', callback_data='marketlist_futures_bingx')
button_futures_bitmart = InlineKeyboardButton(text='BitMart ✅', callback_data='marketlist_futures_bitmart')
button_futures_poloniex = InlineKeyboardButton(text='Poloniex ✅', callback_data='marketlist_futures_poloniex')
button_futures_coinex = InlineKeyboardButton(text='CoinEx ✅', callback_data='marketlist_futures_coinex')
button_futures_ourbit = InlineKeyboardButton(text='Ourbit ✅', callback_data='marketlist_futures_ourbit')
button_futures_hyperliquid = InlineKeyboardButton(text='Hyperliquid ✅', callback_data='marketlist_futures_hyperliquid')
button_futures_lbank = InlineKeyboardButton(text='LBank ✅', callback_data='marketlist_futures_lbank')
#button_futures_xtcom = InlineKeyboardButton(text='XTcom ✅', callback_data='marketlist_futures_xtcom')
button_futures_dex = InlineKeyboardButton(text='DEX 🗑', callback_data='marketlist_futures_dex')
button_futures_aster = InlineKeyboardButton(text='Aster ✅', callback_data='marketlist_futures_aster')
button_futures_xt = InlineKeyboardButton(text='XT ✅', callback_data='marketlist_futures_xt')
button_futures_weex = InlineKeyboardButton(text='WEEX ✅', callback_data='marketlist_futures_weex')
button_futures_phemex = InlineKeyboardButton(text='Phemex ✅', callback_data='marketlist_futures_phemex')
button_futures_binancealpha = InlineKeyboardButton(text='BinanceAlpha 🗑', callback_data='marketlist_futures_binancealpha')

button_futures_bybit_off = InlineKeyboardButton(text='Bybit', callback_data='marketlist_futures_bybit_off')
button_futures_mexc_off = InlineKeyboardButton(text='Mexc', callback_data='marketlist_futures_mexc_off')
button_futures_kucoin_off = InlineKeyboardButton(text='Kucoin', callback_data='marketlist_futures_kucoin_off')
button_futures_gateio_off = InlineKeyboardButton(text='Gateio', callback_data='marketlist_futures_gateio_off')
button_futures_bitget_off = InlineKeyboardButton(text='Bitget', callback_data='marketlist_futures_bitget_off')
button_futures_huobi_off = InlineKeyboardButton(text='Huobi', callback_data='marketlist_futures_huobi_off')
button_futures_okx_off = InlineKeyboardButton(text='Okx', callback_data='marketlist_futures_okx_off')
button_futures_binance_off = InlineKeyboardButton(text='Binance', callback_data='marketlist_futures_binance_off')
button_futures_bingx_off = InlineKeyboardButton(text='BingX', callback_data='marketlist_futures_bingx_off')
button_futures_bitmart_off = InlineKeyboardButton(text='BitMart', callback_data='marketlist_futures_bitmart_off')
button_futures_poloniex_off = InlineKeyboardButton(text='Poloniex', callback_data='marketlist_futures_poloniex_off')
button_futures_coinex_off = InlineKeyboardButton(text='CoinEx', callback_data='marketlist_futures_coinex_off')
#button_futures_xtcom_off = InlineKeyboardButton(text='XTcom', callback_data='marketlist_futures_xtcom_off')
button_futures_ourbit_off = InlineKeyboardButton(text='Ourbit', callback_data='marketlist_futures_ourbit_off')
button_futures_hyperliquid_off = InlineKeyboardButton(text='Hyperliquid', callback_data='marketlist_futures_hyperliquid_off')
button_futures_lbank_off = InlineKeyboardButton(text='LBank', callback_data='marketlist_futures_lbank_off')
button_futures_dex_off = InlineKeyboardButton(text='DEX 🗑', callback_data='marketlist_futures_dex_off')
button_futures_aster_off = InlineKeyboardButton(text='Aster', callback_data='marketlist_futures_aster_off')
button_futures_xt_off = InlineKeyboardButton(text='XT', callback_data='marketlist_futures_xt_off')
button_futures_weex_off = InlineKeyboardButton(text='WEEX', callback_data='marketlist_futures_weex_off')
button_futures_phemex_off = InlineKeyboardButton(text='Phemex', callback_data='marketlist_futures_phemex_off')
button_futures_binancealpha_off = InlineKeyboardButton(text='BinanceAlpha 🗑', callback_data='marketlist_futures_binancealpha_off')

button_spot_bybit = InlineKeyboardButton(text='Bybit ✅', callback_data='marketlist_spot_bybit')
button_spot_mexc = InlineKeyboardButton(text='Mexc ✅', callback_data='marketlist_spot_mexc')
button_spot_kucoin = InlineKeyboardButton(text='Kucoin ✅', callback_data='marketlist_spot_kucoin')
button_spot_gateio = InlineKeyboardButton(text='Gateio ✅', callback_data='marketlist_spot_gateio')
button_spot_bitget = InlineKeyboardButton(text='Bitget ✅', callback_data='marketlist_spot_bitget')
button_spot_huobi = InlineKeyboardButton(text='Huobi ✅', callback_data='marketlist_spot_huobi')
button_spot_okx = InlineKeyboardButton(text='Okx ✅', callback_data='marketlist_spot_okx')
button_spot_binance = InlineKeyboardButton(text='Binance ✅', callback_data='marketlist_spot_binance')
button_spot_bingx = InlineKeyboardButton(text='BingX ✅', callback_data='marketlist_spot_bingx')
button_spot_bitmart = InlineKeyboardButton(text='BitMart ✅', callback_data='marketlist_spot_bitmart')
button_spot_poloniex = InlineKeyboardButton(text='Poloniex ✅', callback_data='marketlist_spot_poloniex')
button_spot_coinex = InlineKeyboardButton(text='CoinEx ✅', callback_data='marketlist_spot_coinex')
#button_spot_xtcom = InlineKeyboardButton(text='XTcom ✅', callback_data='marketlist_spot_xtcom')
button_spot_ourbit = InlineKeyboardButton(text='Ourbit ✅', callback_data='marketlist_spot_ourbit')
button_spot_hyperliquid = InlineKeyboardButton(text='Hyperliquid 🗑', callback_data='marketlist_spot_hyperliquid')
button_spot_lbank = InlineKeyboardButton(text='LBank ✅', callback_data='marketlist_spot_lbank')
button_spot_dex = InlineKeyboardButton(text='DEX ✅', callback_data='marketlist_spot_dex')
button_spot_aster = InlineKeyboardButton(text='Aster ✅', callback_data='marketlist_spot_aster')
button_spot_xt = InlineKeyboardButton(text='XT ✅', callback_data='marketlist_spot_xt')
button_spot_weex = InlineKeyboardButton(text='WEEX ✅', callback_data='marketlist_spot_weex')
button_spot_phemex = InlineKeyboardButton(text='Phemex ✅', callback_data='marketlist_spot_phemex')
button_spot_binancealpha = InlineKeyboardButton(text='BinanceAlpha ✅', callback_data='marketlist_spot_binancealpha')

button_spot_bybit_off = InlineKeyboardButton(text='Bybit', callback_data='marketlist_spot_bybit_off')
button_spot_mexc_off = InlineKeyboardButton(text='Mexc', callback_data='marketlist_spot_mexc_off')
button_spot_kucoin_off = InlineKeyboardButton(text='Kucoin', callback_data='marketlist_spot_kucoin_off')
button_spot_gateio_off = InlineKeyboardButton(text='Gateio', callback_data='marketlist_spot_gateio_off')
button_spot_bitget_off = InlineKeyboardButton(text='Bitget', callback_data='marketlist_spot_bitget_off')
button_spot_huobi_off = InlineKeyboardButton(text='Huobi', callback_data='marketlist_spot_huobi_off')
button_spot_okx_off = InlineKeyboardButton(text='Okx', callback_data='marketlist_spot_okx_off')
button_spot_binance_off = InlineKeyboardButton(text='Binance', callback_data='marketlist_spot_binance_off')
button_spot_bingx_off = InlineKeyboardButton(text='BingX', callback_data='marketlist_spot_bingx_off')
button_spot_bitmart_off = InlineKeyboardButton(text='BitMart', callback_data='marketlist_spot_bitmart_off')
button_spot_poloniex_off = InlineKeyboardButton(text='Poloniex', callback_data='marketlist_spot_poloniex_off')
button_spot_coinex_off = InlineKeyboardButton(text='CoinEx', callback_data='marketlist_spot_coinex_off')
#button_spot_xtcom_off = InlineKeyboardButton(text='XTcom', callback_data='marketlist_spot_xtcom_off')
button_spot_ourbit_off = InlineKeyboardButton(text='Ourbit', callback_data='marketlist_spot_ourbit_off')
button_spot_hyperliquid_off = InlineKeyboardButton(text='Hyperliquid 🗑', callback_data='marketlist_spot_hyperliquid_off')
button_spot_lbank_off = InlineKeyboardButton(text='LBank', callback_data='marketlist_spot_lbank_off')
button_spot_dex_off = InlineKeyboardButton(text='DEX', callback_data='marketlist_spot_dex_off')
button_spot_aster_off = InlineKeyboardButton(text='Aster', callback_data='marketlist_spot_aster_off')
button_spot_xt_off = InlineKeyboardButton(text='XT', callback_data='marketlist_spot_xt_off')
button_spot_weex_off = InlineKeyboardButton(text='WEEX', callback_data='marketlist_spot_weex_off')
button_spot_phemex_off = InlineKeyboardButton(text='Phemex', callback_data='marketlist_spot_phemex_off')
button_spot_binancealpha_off = InlineKeyboardButton(text='BinanceAlpha', callback_data='marketlist_spot_binancealpha_off')

button_restore_mon = InlineKeyboardButton(text='Прислать заново', callback_data='mon_restore')

button_add_blacklist = InlineKeyboardButton(text='Добавить', callback_data='button_add_blacklist')
button_del_blacklist = InlineKeyboardButton(text='Удалить', callback_data='button_del_blacklist')

button_mon_spread = InlineKeyboardButton(text='Фандинг', callback_data='None')
button_mon_spread_on = InlineKeyboardButton(text='вкл', callback_data='mon_spread_on')
button_mon_spread_on_act = InlineKeyboardButton(text='вкл ✅', callback_data='mon_spread_on')
button_mon_spread_off = InlineKeyboardButton(text='выкл', callback_data='mon_spread_off')
button_mon_spread_off_act = InlineKeyboardButton(text='выкл ✅', callback_data='mon_spread_off')

button_mon_course_spread = InlineKeyboardButton(text='Вход', callback_data='None')
button_mon_course_spread_on = InlineKeyboardButton(text='вкл', callback_data='mon_coursespread_on')
button_mon_course_spread_on_act = InlineKeyboardButton(text='вкл ✅', callback_data='mon_coursespread_on')
button_mon_course_spread_off = InlineKeyboardButton(text='выкл', callback_data='mon_coursespread_off')
button_mon_course_spread_off_act = InlineKeyboardButton(text='выкл ✅', callback_data='mon_coursespread_off')

# DEX
button_mon_dex_gt = InlineKeyboardButton(text='DEX >', callback_data='None')
button_mon_dex_gt_on = InlineKeyboardButton(text='вкл', callback_data='mon_dex_gt_on')
button_mon_dex_gt_on_act = InlineKeyboardButton(text='вкл ✅', callback_data='mon_dex_gt_on')
button_mon_dex_gt_off = InlineKeyboardButton(text='выкл', callback_data='mon_dex_gt_off')
button_mon_dex_gt_off_act = InlineKeyboardButton(text='выкл ✅', callback_data='mon_dex_gt_off')

button_mon_dex_lt = InlineKeyboardButton(text='DEX <', callback_data='None')
button_mon_dex_lt_on = InlineKeyboardButton(text='вкл', callback_data='mon_dex_lt_on')
button_mon_dex_lt_on_act = InlineKeyboardButton(text='вкл ✅', callback_data='mon_dex_lt_on')
button_mon_dex_lt_off = InlineKeyboardButton(text='выкл', callback_data='mon_dex_lt_off')
button_mon_dex_lt_off_act = InlineKeyboardButton(text='выкл ✅', callback_data='mon_dex_lt_off')

# DEX blacklist buttons — используй эти переменные во всём коде
button_mon_dex_black_view = InlineKeyboardButton(text='DEX ЧС ▶', callback_data='mon_dex_black_view')
button_mon_dex_black_add  = InlineKeyboardButton(text='Добавить',    callback_data='mon_dex_black_add')
button_mon_dex_black_del  = InlineKeyboardButton(text='Удалить',     callback_data='mon_dex_black_del')

button_filter_spread = InlineKeyboardButton(text='Сорт: фандинг', callback_data='page_from:spread')
button_filter_course = InlineKeyboardButton(text='Сорт: вход', callback_data='page_from:course')

button_filter_spread_spot = InlineKeyboardButton(text='Сорт: фандинг', callback_data='spot_page:spread')
button_filter_course_spot = InlineKeyboardButton(text='Сорт: вход', callback_data='spot_page:course')

button_filter_big_course = InlineKeyboardButton(text='Вход > 0 ✅', callback_data='page_from:big')
button_filter_all_course = InlineKeyboardButton(text='Вход > 0', callback_data='page_from:all')

button_filter_big_course_spot = InlineKeyboardButton(text='Вход > 0 ✅', callback_data='spot_page:big')
button_filter_all_course_spot = InlineKeyboardButton(text='Вход > 0', callback_data='spot_page:all')

# СПОТ
button_filter_current_spot = InlineKeyboardButton(text='текущая', callback_data='spot_page_from:current')
button_filter_1d_spot = InlineKeyboardButton(text='1Д', callback_data='spot_page_from:1d')
button_filter_3d_spot = InlineKeyboardButton(text='3Д', callback_data='spot_page_from:3d')
button_filter_7d_spot = InlineKeyboardButton(text='1Н', callback_data='spot_page_from:7d')
button_filter_30d_spot = InlineKeyboardButton(text='1М', callback_data='spot_page_from:30d')

button_filter_current_market_spot = InlineKeyboardButton(text='текущая', callback_data='spot_page_market:current')
button_filter_1d_market_spot = InlineKeyboardButton(text='1Д', callback_data='spot_page_market:1d')
button_filter_3d_market_spot = InlineKeyboardButton(text='3Д', callback_data='spot_page_market:3d')
button_filter_7d_market_spot = InlineKeyboardButton(text='1Н', callback_data='spot_page_market:7d')
button_filter_30d_market_spot = InlineKeyboardButton(text='1М', callback_data='spot_page_market:30d')

# ФЬЮЧЕРСЫ
button_filter_current = InlineKeyboardButton(text='текущая', callback_data='page_from:current')
button_filter_1d = InlineKeyboardButton(text='1Д', callback_data='page_from:1d')
button_filter_3d = InlineKeyboardButton(text='3Д', callback_data='page_from:3d')
button_filter_7d = InlineKeyboardButton(text='1Н', callback_data='page_from:7d')
button_filter_30d = InlineKeyboardButton(text='1М', callback_data='page_from:30d')

button_filter_current_market = InlineKeyboardButton(text='текущая', callback_data='page_market:current')
button_filter_1d_market = InlineKeyboardButton(text='1Д', callback_data='page_market:1d')
button_filter_3d_market = InlineKeyboardButton(text='3Д', callback_data='page_market:3d')
button_filter_7d_market = InlineKeyboardButton(text='1Н', callback_data='page_market:7d')
button_filter_30d_market = InlineKeyboardButton(text='1М', callback_data='page_market:30d')

# ФИЛЬТР ПО МОНЕТЕ И СТРАНИЦЕ
button_filter_coin_spot = InlineKeyboardButton(text='монета', callback_data='spot_page_from:coin')
button_filter_coin = InlineKeyboardButton(text='монета', callback_data='page_from:coin')

button_filter_page_spot = InlineKeyboardButton(text='страница', callback_data='spot_page_from:page')
button_filter_page = InlineKeyboardButton(text='страница', callback_data='page_from:page')

button_info_web = InlineKeyboardButton(text='Информация', web_app=WebAppInfo(
                    url=f'{ORIGIN}/info/'))
button_subscription_web = InlineKeyboardButton(text='Подписка', web_app=WebAppInfo(
                    url=f'{ORIGIN}/subscription/'))
button_trade_web = InlineKeyboardButton(text='Торговля', web_app=WebAppInfo(
                    url=f'{ORIGIN}/'))


# СПОТ
def get_button_filter_spread_spot(symbolFind):
    return InlineKeyboardButton(text='Сорт: фандинг', callback_data=f'spot_page_market:spread:{symbolFind}')


def get_button_filter_course_spot(symbolFind):
    return InlineKeyboardButton(text='Сорт: вход', callback_data=f'spot_page_market:course:{symbolFind}')


def get_button_filter_big_course_spot(symbolFind):
    return InlineKeyboardButton(text='Вход > 0 ✅', callback_data=f'spot_page_market:big:{symbolFind}')


def get_button_filter_all_course_spot(symbolFind):
    return InlineKeyboardButton(text='Вход > 0', callback_data=f'spot_page_market:all:{symbolFind}')


# ФЬЮЧЕРСЫ
def get_button_filter_spread(symbolFind):
    return InlineKeyboardButton(text='Сорт: фандинг', callback_data=f'page_market:spread:{symbolFind}')


def get_button_filter_course(symbolFind):
    return InlineKeyboardButton(text='Сорт: вход', callback_data=f'page_market:course:{symbolFind}')


def get_button_filter_big_course(symbolFind):
    return InlineKeyboardButton(text='Вход > 0 ✅', callback_data=f'page_market:big:{symbolFind}')


def get_button_filter_all_course(symbolFind):
    return InlineKeyboardButton(text='Вход > 0', callback_data=f'page_market:all:{symbolFind}')


# СПОТ
def get_button_filter_current_market_spot(symbolFind):
    return InlineKeyboardButton(text='текущая', callback_data=f'spot_page_market:current:{symbolFind}')


def get_button_filter_1d_market_spot(symbolFind):
    return InlineKeyboardButton(text='1Д', callback_data=f'spot_page_market:1d:{symbolFind}')


def get_button_filter_3d_market_spot(symbolFind):
    return InlineKeyboardButton(text='3Д', callback_data=f'spot_page_market:3d:{symbolFind}')


def get_button_filter_7d_market_spot(symbolFind):
    return InlineKeyboardButton(text='1Н', callback_data=f'spot_page_market:7d:{symbolFind}')


def get_button_filter_30d_market_spot(symbolFind):
    return InlineKeyboardButton(text='1М', callback_data=f'spot_page_market:30d:{symbolFind}')

# ---- DEX-specific filter buttons (libs/tgfunc.py) ----
# --- per-symbol (market page) buttons: callbacks -> dex_market:<mode>:<filter>:<symbol> ---
def get_button_filter_spread_dex(symbolFind, mode):
    return InlineKeyboardButton(text='Сорт: фандинг', callback_data=f'dex_market:{mode}:spread:{symbolFind}')

def get_button_filter_course_dex(symbolFind, mode):
    return InlineKeyboardButton(text='Сорт: вход', callback_data=f'dex_market:{mode}:course:{symbolFind}')

def get_button_filter_big_course_dex(symbolFind, mode):
    return InlineKeyboardButton(text='Вход > 0 ✅', callback_data=f'dex_market:{mode}:big:{symbolFind}')

def get_button_filter_all_course_dex(symbolFind, mode):
    return InlineKeyboardButton(text='Вход > 0', callback_data=f'dex_market:{mode}:all:{symbolFind}')


def add_filter_buttons_futures_market_dex(inline_kb1, dataSearch, symbolFind, mode):
    """
    Специальная версия фильтров для страницы по конкретной монете DEX.
    dataSearch может быть dict или JSON-string или 'no'
    mode — 'in' или 'fund'
    """
    # safe parse
    parsed = 'no'
    try:
        if dataSearch is None:
            parsed = 'no'
        elif isinstance(dataSearch, (bytes, bytearray)):
            s = dataSearch.decode('utf-8', errors='ignore')
            parsed = orjson.loads(s) if s != 'no' else 'no'
        elif isinstance(dataSearch, str):
            if dataSearch == 'no':
                parsed = 'no'
            else:
                try:
                    parsed = orjson.loads(dataSearch)
                except Exception:
                    parsed = {}
        elif isinstance(dataSearch, dict):
            parsed = dataSearch
        else:
            parsed = {}
    except Exception:
        parsed = {}

    # determine checked labels
    big_checked = (parsed != 'no' and isinstance(parsed, dict) and parsed.get('filter_big_or_all_course') == '1')
    course_mode = (parsed != 'no' and isinstance(parsed, dict) and parsed.get('filter_course_or_spread') == '1')

    # buttons: Вход toggle (big), Сорт: вход/фандинг (course/spread), Стр and Монета (page/coin)
    # ВОЗЬМИ имя кнопок: "Стр" и "Монета" (как просил)
    if big_checked:
        btn_big = InlineKeyboardButton(text='Вход > 0 ✅', callback_data=f'dex_market:{mode}:all:{symbolFind}')
    else:
        btn_big = InlineKeyboardButton(text='Вход > 0', callback_data=f'dex_market:{mode}:big:{symbolFind}')

    # Course / Spread buttons (toggle by setting filter_course_or_spread)
    btn_course = InlineKeyboardButton(text='Сорт: вход', callback_data=f'dex_market:{mode}:course:{symbolFind}')
    btn_spread = InlineKeyboardButton(text='Сорт: фандинг', callback_data=f'dex_market:{mode}:spread:{symbolFind}')

    # Page / Coin renamed to 'Стр' / 'Монета'
    btn_page = InlineKeyboardButton(text='Стр', callback_data=f'dex_page_from:page')
    btn_coin = InlineKeyboardButton(text='Монета', callback_data=f'dex_page_from:coin')

    # Layout: imitate futures-market layout (two rows)
    if course_mode:
        # course mode: show course + page/coin
        inline_kb1.row(btn_big if big_checked else btn_big, btn_course)
        inline_kb1.row(btn_page, btn_coin)
    else:
        # spread mode
        inline_kb1.row(btn_big if big_checked else btn_big, btn_spread)
        inline_kb1.row(btn_page, btn_coin)



# --- main DEX list (общая страница) кнопки: callbacks -> dex_page_from:<filter> ---
def get_button_filter_spread_dex_main():
    return InlineKeyboardButton(text='Сорт: фандинг', callback_data=f'dex_page_from:spread')

def get_button_filter_course_dex_main():
    return InlineKeyboardButton(text='Сорт: вход', callback_data=f'dex_page_from:course')

def get_button_filter_big_course_dex_main():
    return InlineKeyboardButton(text='Вход > 0 ✅', callback_data=f'dex_page_from:all')

def get_button_filter_all_course_dex_main():
    return InlineKeyboardButton(text='Вход > 0', callback_data=f'dex_page_from:big')


def add_filter_buttons_futures_dex(inline_kb1, dataSearch):
    """
    Фильтры для главной DEX-страницы (без конкретной монеты).
    Кнопки посылают 'dex_page_from:<filter>'.
    """
    button_filter_big_course = get_button_filter_big_course_dex_main()
    button_filter_course = get_button_filter_course_dex_main()
    button_filter_all_course = get_button_filter_all_course_dex_main()
    button_filter_spread = get_button_filter_spread_dex_main()

    # page/coin: для главной страницы coin не имеет смысла — используем просто page (переключает страницы)
    button_filter_page3 = InlineKeyboardButton(text='страница', callback_data=f'dex_page_from:page')
    button_filter_coin3 = InlineKeyboardButton(text='монета', callback_data=f'dex_page_from:coin')

    # parse dataSearch safely (same as others)
    parsed = 'no'
    try:
        if dataSearch is None:
            parsed = 'no'
        elif isinstance(dataSearch, (bytes, bytearray)):
            s = dataSearch.decode('utf-8', errors='ignore')
            parsed = orjson.loads(s) if s != 'no' else 'no'
        elif isinstance(dataSearch, str):
            if dataSearch == 'no':
                parsed = 'no'
            else:
                try:
                    parsed = orjson.loads(dataSearch)
                except Exception:
                    parsed = {}
        elif isinstance(dataSearch, dict):
            parsed = dataSearch
        else:
            parsed = {}
    except Exception:
        parsed = {}

    if parsed != 'no' and isinstance(parsed, dict) and 'filter_course_or_spread' in parsed:
        if parsed['filter_course_or_spread'] == '1':
            if 'filter_big_or_all_course' in parsed and parsed['filter_big_or_all_course'] == '1':
                inline_kb1.row(button_filter_big_course, button_filter_course)
            else:
                inline_kb1.row(button_filter_all_course, button_filter_course)
            inline_kb1.row(button_filter_page3, button_filter_coin3)
        else:
            if 'filter_big_or_all_course' in parsed and parsed['filter_big_or_all_course'] == '1':
                inline_kb1.row(button_filter_big_course, button_filter_spread)
            else:
                inline_kb1.row(button_filter_all_course, button_filter_spread)
            inline_kb1.row(button_filter_page3, button_filter_coin3)
    else:
        inline_kb1.row(button_filter_all_course, button_filter_spread)
        inline_kb1.row(button_filter_page3, button_filter_coin3)
# ---- end DEX-specific filter buttons ----

# ФЬЮЧЕРСЫ
def get_button_filter_current_market(symbolFind):
    return InlineKeyboardButton(text='текущая', callback_data=f'page_market:current:{symbolFind}')


def get_button_filter_1d_market(symbolFind):
    return InlineKeyboardButton(text='1Д', callback_data=f'page_market:1d:{symbolFind}')


def get_button_filter_3d_market(symbolFind):
    return InlineKeyboardButton(text='3Д', callback_data=f'page_market:3d:{symbolFind}')


def get_button_filter_7d_market(symbolFind):
    return InlineKeyboardButton(text='1Н', callback_data=f'page_market:7d:{symbolFind}')


def get_button_filter_30d_market(symbolFind):
    return InlineKeyboardButton(text='1М', callback_data=f'page_market:30d:{symbolFind}')


def button_mon_spread_count(count):
    button_mon_spread = InlineKeyboardButton(text=f'Фанд {count}%', callback_data='None')
    return button_mon_spread


def button_mon_course_spread_count(count):
    button_mon_course_spread = InlineKeyboardButton(text=f'Вход {count}%', callback_data='None')
    return button_mon_course_spread


def create_message_to_spot(bot_message, coin_cap):
    market_1 = ''
    market_2 = ''

    coin = str(bot_message[1]).replace('USDT', '')
    rating = 0
    top_coin = '🔴'
    for i in coin_cap:
        if coin == i[1]:
            rating = int(i[0])
            break
    if rating > 0 and rating <= 1000:
        top_coin = '🟢'
    elif rating > 1000 and rating <= 2000:
        top_coin = '🟡'
    else:
        top_coin = '🔴'

    if bot_message[2] == 'Bybit':
        market_1 = f'<a href="https://www.bybit.com/ru-RU/trade/spot/{str(bot_message[1]).replace("USDT", "/USDT")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Mexc':
        market_1 = f'<a href="https://www.mexc.com/ru-RU/exchange/{str(bot_message[1]).replace("USDT", "_USDT")}?_from=search_spot_trade">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Kucoin':
        market_1 = f'<a href="https://www.kucoin.com/ru/trade/{str(bot_message[1]).replace("USDT", "-USDT")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Gateio':
        market_1 = f'<a href="https://www.gate.io/ru/trade/{str(bot_message[1]).replace("USDT", "_USDT")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Bitget':
        market_1 = f'<a href="https://www.bitget.com/ru/spot/{str(bot_message[1])}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Huobi':
        market_1 = f'<a href="https://www.htx.com/trade/{str(bot_message[1]).lower().replace("usdt", "_usdt")}?type=spot">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Okx':
        market_1 = f'<a href="https://www.okx.com/ru/trade-spot/{str(bot_message[1]).lower().replace("usdt", "-usdt")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Binance':
        market_1 = f'<a href="https://www.binance.com/ru/trade/{str(bot_message[1]).replace("USDT", "_USDT")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'BingX':
        market_1 = f'<a href="https://bingx.com/ru-ru/spot/{str(bot_message[1])}/">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'BitMart':
        market_1 = f'<a href="https://www.bitmart.com/trade/ru-RU?symbol={str(bot_message[1]).replace("USDT", "_USDT")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Poloniex':
        market_1 = f'<a href="https://poloniex.com/trade/{str(bot_message[1]).replace("USDT", "_USDT")}/?type=spot">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'CoinEx':
        market_1 = f'<a href="https://www.coinex.com/ru/exchange/{str(bot_message[1]).replace("USDT", "-USDT").lower()}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Ourbit':
        market_1 = f'<a href="https://www.ourbit.com/ru-RU/exchange/{str(bot_message[1]).replace("USDT", "_USDT")}?_from=search_spot_trade">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Hyperliquid':
        market_1 = f'<a href="https://app.hyperliquid.xyz/trade/{str(bot_message[1]).replace("USDT", "")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'LBank':
        market_1 = f'<a href="https://www.lbank.com/trade/{str(bot_message[1]).lower().replace("usdt", "_usdt")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Aster':
        market_1 = f'<a href="https://www.asterdex.com/ru/trade/pro/spot/{str(bot_message[1])}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'XT':
        market_1 = f'<a href="https://www.xt.com/ru/trade/{str(bot_message[1]).lower().replace("usdt", "_usdt")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'WEEX':
        market_1 = f'<a href="https://www.weex.com/spot/{str(bot_message[1]).replace("USDT", "-USDT")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Phemex':
        market_1 = f'<a href="https://phemex.com/trade/{str(bot_message[1]).replace("USDT", "-USDT")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'BinanceAlpha':
        # Ищем контракт в Redis для построения ссылки
        _ba_meta = _load_key_from_redis(0, "BinanceAlpha:contracts") or {}
        _ba_info = _ba_meta.get(str(bot_message[1]), {})
        _ba_addr = _ba_info.get('contract_address', '')
        _ba_chain = _ba_info.get('chain_name', 'bsc')
        if _ba_addr:
            market_1 = f'<a href="https://www.binance.com/en/alpha/{_ba_chain}/{_ba_addr}">{str(bot_message[2])}</a>'
        else:
            market_1 = f'<b>{str(bot_message[2])}</b>'

    if bot_message[3] == 'Bybit':
        market_2 = f'<a href="https://www.bybit.com/trade/usdt/{str(bot_message[1])}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Mexc':
        market_2 = f'<a href="https://futures.mexc.com/ru-RU/exchange/{str(bot_message[1]).replace("USDT", "_USDT")}?type=linear_swap">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Kucoin':
        market_2 = f'<a href="https://www.kucoin.com/ru/futures/trade/{str(bot_message[1]).replace("USDT", "USDTM")}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Gateio':
        market_2 = f'<a href="https://www.gate.io/ru/futures/USDT/{str(bot_message[1]).replace("USDT", "_USDT")}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Bitget':
        market_2 = f'<a href="https://www.bitget.com/ru/futures/usdt/{str(bot_message[1])}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Huobi':
        market_2 = f'<a href="https://www.htx.com/futures/linear_swap/exchange#contract_code={str(bot_message[1]).replace("USDT", "-USDT")}&contract_type=swap&type=cross">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Okx':
        market_2 = f'<a href="https://www.okx.com/ru/trade-swap/{str(bot_message[1]).lower().replace("usdt", "-usdt-swap")}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Binance':
        market_2 = f'<a href="https://www.binance.com/ru/futures/{str(bot_message[1])}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'BingX':
        market_2 = f'<a href="https://swap.bingx.com/ru-ru/{str(bot_message[1]).replace("USDT", "-USDT")}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'BitMart':
        market_2 = f'<a href="https://derivatives.bitmart.com/ru-RU?symbol={str(bot_message[1])}&theme=dark">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Poloniex':
        market_2 = f'<a href="https://poloniex.com/futures/trade/{str(bot_message[1]).replace("USDT", "USDTPERP")}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'CoinEx':
        market_2 = f'<a href="https://www.coinex.com/ru/futures/{str(bot_message[1]).replace("USDT", "-USDT").lower()}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Ourbit':
        market_2 = f'<a href="https://futures.ourbit.com/ru-RU/exchange/{str(bot_message[1]).replace("USDT", "_USDT")}?type=linear_swap">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Hyperliquid':
        market_2 = f'<a href="https://app.hyperliquid.xyz/trade/{str(bot_message[1]).replace("USDT", "")}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'LBank':
        market_2 = f'<a href="https://www.lbank.com/futures/{str(bot_message[1]).lower()}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Aster':
        market_2 = f'<a href="https://www.asterdex.com/ru/trade/pro/futures/{str(bot_message[1])}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'XT':
        market_2 = f'<a href="https://www.xt.com/ru/futures/trade/{str(bot_message[1]).lower()}_usdt">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'WEEX':
        market_2 = f'<a href="https://www.weex.com/futures/{str(bot_message[1]).replace("USDT", "-USDT")}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Phemex':
        market_2 = f'<a href="https://phemex.com/futures/{str(bot_message[1]).replace("USDT", "-USDT")}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'BinanceAlpha':
        _ba_meta2 = _load_key_from_redis(0, "BinanceAlpha:contracts") or {}
        _ba_info2 = _ba_meta2.get(str(bot_message[1]), {})
        _ba_addr2 = _ba_info2.get('contract_address', '')
        _ba_chain2 = _ba_info2.get('chain_name', 'bsc')
        if _ba_addr2:
            market_2 = f'<a href="https://www.binance.com/en/alpha/{_ba_chain2}/{_ba_addr2}">{str(bot_message[3])}</a>'
        else:
            market_2 = f'<b>{str(bot_message[3])}</b>'

    creating_message = ''
    creating_message += '<b>' + str(bot_message[1]) + f'</b> {top_coin}\n\n'
    creating_message += f'📗|{market_1}| - BUY\n\n'
    if fmt_amount_usd(bot_message[23]) != "0":
        creating_message += f'Объем: <b>{fmt_amount_usd(bot_message[23])}$</b>\n\n\n\n'
    else:
        creating_message += '\n\n\n\n'

    creating_message += f'📕|{market_2}| - SHORT\n\n'
    creating_message += f'Текущая: <b>{bot_message[4]}%</b>\n'
    if fmt_amount_usd(bot_message[21]) != "0":
        creating_message += f'Объем: <b>{fmt_amount_usd(bot_message[21])}$</b>\n'
    if bot_message[3] in ('Mexc', 'Ourbit'):
        creating_message += f'Лимит: <b>{round(bot_message[22])}$</b>\n'
    creating_message += f'Стремится: {bot_message[13]}%\n'
    creating_message += f'🕓: <b>{round(bot_message[5])}ч</b>\n'
    if market_2 != 'BitMart' and market_2 != 'Poloniex' and bot_message[17] != '':
        creating_message += f'Накопленный 1 | 3 | 7 | 30 дней:\n (<b>{bot_message[17]}%</b> | <b>{bot_message[18]}%</b> | <b>{bot_message[19]}%</b> | <b>{bot_message[20]}%</b>)\n\n'
    else:
        creating_message += '\n'
    creating_message += f'💰 Спред:\n'
    creating_message += f'Текущий: <b>{bot_message[4]}%</b>\n'
    creating_message += f'Комиссия: <b>{round(float(bot_message[7]) + float(bot_message[8]), 2)}%</b>\n'

    creating_message += f'Спред входа: <b>{round(((float(bot_message[6]) / float(bot_message[16])) - 1) * 100, 2)}%</b> ({float(bot_message[6])} | {float(bot_message[16])})\n'
    creating_message += f'Спред выхода: <b>{round(((float(bot_message[15]) / float(bot_message[14])) - 1) * 100, 2)}%</b> ({float(bot_message[15])} | {float(bot_message[14])})\n'
    if market_2 != 'BitMart' and market_2 != 'Poloniex' and bot_message[17] != '':
        creating_message += f'Накопленный 1 | 3 | 7 | 30 дней:\n (<b>{bot_message[17]}%</b> | <b>{bot_message[18]}%</b> | <b>{bot_message[19]}%</b> | <b>{bot_message[20]}%</b>)\n'

    return creating_message


async def fetch_coin_history_mongo_async(collection_name, exchange_name, coin_symbol, mongo_db):
    """
    Асинхронно возвращает [(ask, bid, datetime), ...] из MongoDB.
    """

    collection = mongo_db[collection_name]

    cursor = collection.find(
        {"exchange_name": exchange_name, "symbol": coin_symbol},
        {"ask": 1, "bid": 1, "datetime": 1, "_id": 0}
    ).batch_size(576)

    result = []
    async for doc in cursor:
        result.append((doc['ask'], doc['bid'], doc['datetime']))

    return result


def calculate_average_spreads(spread_list, window_size):
    """Возвращает среднее по доступному количеству последних значений."""
    if not spread_list:
        return None
    if len(spread_list) < window_size:
        return statistics.mean(spread_list)
    return statistics.mean(spread_list[-window_size:])

async def analyze_spreads(table_name: str, m1: str, m2: str, post_coin: str, spread_in: float, spread_out: float):

    # Получаем исторические данные
  #  start_time = time.time()
    history_data_m1 = await fetch_coin_history_mongo_async(table_name, m1, post_coin, mongo_db)
    history_data_m2 = await fetch_coin_history_mongo_async("futures", m2, post_coin, mongo_db)

    # Создаем словари с данными по времени
    m1_dict = {entry[2]: (entry[0], entry[1]) for entry in history_data_m1}
    m2_dict = {entry[2]: (entry[0], entry[1]) for entry in history_data_m2}

    # Находим общие временные точки
    common_times = sorted(set(m1_dict.keys()) & set(m2_dict.keys()))

    # Списки спредов и времени
    spreads_in = []
    spreads_out = []
    spreads_time = []

    for time_point in common_times:
        m1_ask, m1_bid = m1_dict[time_point]
        m2_ask, m2_bid = m2_dict[time_point]

        if any(val == 0 for val in [m1_ask, m1_bid, m2_ask, m2_bid]):
            continue

        in_spread = round(((m2_bid / m1_ask) - 1) * 100, 2)
        out_spread = round(((m2_ask / m1_bid) - 1) * 100, 2)

        spreads_in.append(in_spread)
        spreads_out.append(out_spread)
        spreads_time.append(time_point)

   # end_time = time.time()
   # print(f"Function fetch_coin_historys took {end_time - start_time:.4f} seconds")
    # Временные окна
    minutes_in_hour = 60
    time_windows = {
        '6h': minutes_in_hour * 6,
        '12h': minutes_in_hour * 12,
        '48h': minutes_in_hour * 48,
    }

    # Анализ спредов
    analysis_result = {
        'latest_spread_in': spread_in,
        'latest_spread_out': spread_out,
        'deviation_in': {},
        'deviation_out': {},
        'averages_in': {},
        'averages_out': {},
        'history_minutes': len(spreads_in),
    }

    for label, window in time_windows.items():
        avg_in = calculate_average_spreads(spreads_in, window)
        avg_out = calculate_average_spreads(spreads_out, window)

        if avg_in is not None:
            analysis_result['averages_in'][label] = round(avg_in, 2)
            analysis_result['deviation_in'][label] = round(spread_in - avg_in, 2)

        if avg_out is not None:
            analysis_result['averages_out'][label] = round(avg_out, 2)
            analysis_result['deviation_out'][label] = round(spread_out - avg_out, 2)

    return analysis_result


def get_delta_circle(value, thresholds):
    if value <= thresholds['low']:
        return '🔴'
    elif thresholds['low'] < value < thresholds['high']:
        return '🟡'
    else:
        return '🟢'


def get_delta_circle_out(value, thresholds):
    if value >= thresholds['high']:
        return '🔴'
    elif thresholds['low'] < value < thresholds['high']:
        return '🟡'
    else:
        return '🟢'


def create_message_to_futures(bot_message, m1, coin_cap):
    creating_message = ''
    market_1 = ''
    market_2 = ''
    reversed_spread = False
    if bot_message[3] != m1:
        reversed_spread = True

    coin = str(bot_message[1]).replace('USDT', '')
    rating = 0
    top_coin = '🔴'
    for i in coin_cap:
        if coin == i[1]:
            rating = int(i[0])
            break
    if rating > 0 and rating <= 1000:
        top_coin = '🟢'
    elif rating > 1000 and rating <= 2000:
        top_coin = '🟡'
    else:
        top_coin = '🔴'

    if bot_message[3] == 'Bybit':
        market_1 = f'<a href="https://www.bybit.com/trade/usdt/{str(bot_message[1])}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Mexc':
        market_1 = f'<a href="https://futures.mexc.com/ru-RU/exchange/{str(bot_message[1]).replace("USDT", "_USDT")}?type=linear_swap">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Kucoin':
        market_1 = f'<a href="https://www.kucoin.com/ru/futures/trade/{str(bot_message[1]).replace("USDT", "USDTM")}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Gateio':
        market_1 = f'<a href="https://www.gate.io/ru/futures/USDT/{str(bot_message[1]).replace("USDT", "_USDT")}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Bitget':
        market_1 = f'<a href="https://www.bitget.com/ru/futures/usdt/{str(bot_message[1])}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Huobi':
        market_1 = f'<a href="https://www.htx.com/futures/linear_swap/exchange#contract_code={str(bot_message[1]).replace("USDT", "-USDT")}&contract_type=swap&type=cross">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Okx':
        market_1 = f'<a href="https://www.okx.com/ru/trade-swap/{str(bot_message[1]).lower().replace("usdt", "-usdt-swap")}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Binance':
        market_1 = f'<a href="https://www.binance.com/ru/futures/{str(bot_message[1])}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'BingX':
        market_1 = f'<a href="https://swap.bingx.com/ru-ru/{str(bot_message[1]).replace("USDT", "-USDT")}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'BitMart':
        market_1 = f'<a href="https://derivatives.bitmart.com/ru-RU?symbol={str(bot_message[1])}&theme=dark">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Poloniex':
        market_1 = f'<a href="https://poloniex.com/futures/trade/{str(bot_message[1]).replace("USDT", "USDTPERP")}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'CoinEx':
        market_1 = f'<a href="https://www.coinex.com/ru/futures/{str(bot_message[1]).replace("USDT", "-USDT").lower()}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Ourbit':
        market_1 = f'<a href="https://futures.ourbit.com/ru-RU/exchange/{str(bot_message[1]).replace("USDT", "_USDT")}?type=linear_swap">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Hyperliquid':
        market_1 = f'<a href="https://app.hyperliquid.xyz/trade/{str(bot_message[1]).replace("USDT", "")}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'LBank':
        market_1 = f'<a href="https://www.lbank.com/futures/{str(bot_message[1]).lower()}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Aster':
        market_1 = f'<a href="https://www.asterdex.com/ru/trade/pro/futures/{str(bot_message[1])}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'XT':
        market_1 = f'<a href="https://www.xt.com/ru/futures/trade/{str(bot_message[1]).lower()}_usdt">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'WEEX':
        market_1 = f'<a href="https://www.weex.com/futures/{str(bot_message[1]).replace("USDT", "-USDT")}">{str(bot_message[3])}</a>'
    elif bot_message[3] == 'Phemex':
        market_1 = f'<a href="https://phemex.com/futures/{str(bot_message[1]).replace("USDT", "-USDT")}">{str(bot_message[3])}</a>'

    if bot_message[2] == 'Bybit':
        market_2 = f'<a href="https://www.bybit.com/trade/usdt/{str(bot_message[1])}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Mexc':
        market_2 = f'<a href="https://futures.mexc.com/ru-RU/exchange/{str(bot_message[1]).replace("USDT", "_USDT")}?type=linear_swap">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Kucoin':
        market_2 = f'<a href="https://www.kucoin.com/ru/futures/trade/{str(bot_message[1]).replace("USDT", "USDTM")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Gateio':
        market_2 = f'<a href="https://www.gate.io/ru/futures/USDT/{str(bot_message[1]).replace("USDT", "_USDT")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Bitget':
        market_2 = f'<a href="https://www.bitget.com/ru/futures/usdt/{str(bot_message[1])}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Huobi':
        market_2 = f'<a href="https://www.htx.com/futures/linear_swap/exchange#contract_code={str(bot_message[1]).replace("USDT", "-USDT")}&contract_type=swap&type=cross">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Okx':
        market_2 = f'<a href="https://www.okx.com/ru/trade-swap/{str(bot_message[1]).lower().replace("usdt", "-usdt-swap")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Binance':
        market_2 = f'<a href="https://www.binance.com/ru/futures/{str(bot_message[1])}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'BingX':
        market_2 = f'<a href="https://swap.bingx.com/ru-ru/{str(bot_message[1]).replace("USDT", "-USDT")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'BitMart':
        market_2 = f'<a href="https://derivatives.bitmart.com/ru-RU?symbol={str(bot_message[1])}&theme=dark">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Poloniex':
        market_2 = f'<a href="https://poloniex.com/futures/trade/{str(bot_message[1]).replace("USDT", "USDTPERP")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'CoinEx':
        market_2 = f'<a href="https://www.coinex.com/ru/futures/{str(bot_message[1]).replace("USDT", "-USDT").lower()}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Ourbit':
        market_2 = f'<a href="https://futures.ourbit.com/ru-RU/exchange/{str(bot_message[1]).replace("USDT", "_USDT")}?type=linear_swap">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Hyperliquid':
        market_2 = f'<a href="https://app.hyperliquid.xyz/trade/{str(bot_message[1]).replace("USDT", "")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'LBank':
        market_2 = f'<a href="https://www.lbank.com/futures/{str(bot_message[1]).lower()}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Aster':
        market_2 = f'<a href="https://www.asterdex.com/ru/trade/pro/futures/{str(bot_message[1])}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'XT':
        market_2 = f'<a href="https://www.xt.com/ru/futures/trade/{str(bot_message[1]).lower()}_usdt">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'WEEX':
        market_2 = f'<a href="https://www.weex.com/futures/{str(bot_message[1]).replace("USDT", "-USDT")}">{str(bot_message[2])}</a>'
    elif bot_message[2] == 'Phemex':
        market_2 = f'<a href="https://phemex.com/futures/{str(bot_message[1]).replace("USDT", "-USDT")}">{str(bot_message[2])}</a>'

    if not reversed_spread:

        if float(bot_message[4]) >= float(bot_message[5]):
            creating_message += '<b>' + str(bot_message[1]) + f'</b> {top_coin}\n\n'
            creating_message += f'📗|{market_1}| - LONG\n\n'
            creating_message += f'Текущая: <b>{bot_message[5]}%</b>\n'
            if fmt_amount_usd(bot_message[30]) != "0":
                creating_message += f'Объем: <b>{fmt_amount_usd(bot_message[30])}$</b>\n'
            if bot_message[3] in ('Mexc', 'Ourbit'):
                creating_message += f'Лимит: <b>{round(bot_message[32])}$</b>\n'
            creating_message += f'Стремится: {bot_message[18]}%\n'
            creating_message += f'🕓: <b>{round(bot_message[7])}ч</b>\n'
            if bot_message[3] != 'BitMart' and bot_message[3] != 'Poloniex' and bot_message[25] != '':
                creating_message += f'Накопленный 1 | 3 | 7 | 30 дней:\n (<b>{bot_message[25]}%</b> | <b>{bot_message[26]}%</b> | <b>{bot_message[27]}%</b> | <b>{bot_message[28]}%</b>)\n\n'
            else:
                creating_message += '\n'
            creating_message += f'📕|{market_2}| - SHORT\n\n'
            creating_message += f'Текущая: <b>{bot_message[4]}%</b>\n'
            if fmt_amount_usd(bot_message[29]) != "0":
                creating_message += f'Объем: <b>{fmt_amount_usd(bot_message[29])}$</b>\n'
            if bot_message[2] in ('Mexc', 'Ourbit'):
                creating_message += f'Лимит: <b>{round(bot_message[31])}$</b>\n'
            creating_message += f'Стремится: {bot_message[17]}%\n'
            creating_message += f'🕓: <b>{round(bot_message[6])}ч</b>\n'
            if bot_message[2] != 'BitMart' and bot_message[2] != 'Poloniex' and bot_message[21] != '':
                creating_message += f'Накопленный 1 | 3 | 7 | 30 дней:\n (<b>{bot_message[21]}%</b> | <b>{bot_message[22]}%</b> | <b>{bot_message[23]}%</b> | <b>{bot_message[24]}%</b>)\n\n'
            else:
                creating_message += '\n'

            creating_message += f'💰 Спред:\n'
            if bot_message[2] not in ('Hyperliquid', 'Aster') and bot_message[3] not in ('Hyperliquid', 'Aster'):
                creating_message += f'Текущий: <b>{bot_message[14]}%</b>\n'
            else:
                creating_message += f'Текущий: <b>{round(bot_message[4] - bot_message[5], 4)}%</b>\n'

            creating_message += f'Комиссия: <b>{round(float(bot_message[10]) + float(bot_message[11]), 2)}%</b>\n'

            creating_message += f'Спред входа: <b>{round(((float(bot_message[8]) / float(bot_message[20])) - 1) * 100, 2)}%</b> ({float(bot_message[8])} | {float(bot_message[20])})\n'
            creating_message += f'Спред выхода: <b>{round(((float(bot_message[19]) / float(bot_message[9])) - 1) * 100, 2)}%</b> ({float(bot_message[19])} | {float(bot_message[9])})\n'
            if bot_message[2] != 'BitMart' and bot_message[2] != 'Poloniex' and bot_message[21] != '' and bot_message[25] != '':
                creating_message += f'Накопленный 1 | 3 | 7 | 30 дней:\n (<b>{round(float(bot_message[21]) - float(bot_message[25]), 2)}%</b> | <b>{round(float(bot_message[22]) - float(bot_message[26]), 2)}%</b> | <b>{round(float(bot_message[23]) - float(bot_message[27]), 2)}%</b> | <b>{round(float(bot_message[24]) - float(bot_message[28]), 2)}%</b>)\n'

    else:
        # Меняем местами market_1 и market_2
        creating_message += '<b>' + str(bot_message[1]) + f'</b> {top_coin}\n\n'

        # Теперь market_2 (была SHORT) — становится LONG
        creating_message += f'📗|{market_2}| - LONG\n\n'
        creating_message += f'Текущая: <b>{bot_message[4]}%</b>\n'
        if fmt_amount_usd(bot_message[29]) != "0":
            creating_message += f'Объем: <b>{fmt_amount_usd(bot_message[29])}$</b>\n'
        if bot_message[2] in ('Mexc', 'Ourbit'):
            creating_message += f'Лимит: <b>{round(bot_message[31])}$</b>\n'
        creating_message += f'Стремится: {bot_message[17]}%\n'
        creating_message += f'🕓: <b>{round(bot_message[6])}ч</b>\n'
        if bot_message[2] not in ['BitMart', 'Poloniex'] and bot_message[21] != '':
            creating_message += f'Накопленный 1 | 3 | 7 | 30 дней:\n (<b>{bot_message[21]}%</b> | <b>{bot_message[22]}%</b> | <b>{bot_message[23]}%</b> | <b>{bot_message[24]}%</b>)\n\n'
        else:
            creating_message += '\n'
        # А market_1 (была LONG) — теперь SHORT
        creating_message += f'📕|{market_1}| - SHORT\n\n'
        creating_message += f'Текущая: <b>{bot_message[5]}%</b>\n'
        if fmt_amount_usd(bot_message[30]) != "0":
            creating_message += f'Объем: <b>{fmt_amount_usd(bot_message[30])}$</b>\n'
        if bot_message[3] in ('Mexc', 'Ourbit'):
            creating_message += f'Лимит: <b>{round(bot_message[32])}$</b>\n'
        creating_message += f'Стремится: {bot_message[18]}%\n'
        creating_message += f'🕓: <b>{round(bot_message[7])}ч</b>\n'
        if bot_message[3] not in ['BitMart', 'Poloniex'] and bot_message[25] != '':
            creating_message += f'Накопленный 1 | 3 | 7 | 30 дней:\n (<b>{bot_message[25]}%</b> | <b>{bot_message[26]}%</b> | <b>{bot_message[27]}%</b> | <b>{bot_message[28]}%</b>)\n\n'
        else:
            creating_message += '\n'
        # Блок спредов (значения те же)
        creating_message += f'💰 Спред:\n'
        if bot_message[2] not in ('Hyperliquid', 'Aster') and bot_message[3] not in ('Hyperliquid', 'Aster'):
            creating_message += f'Текущий: <b>{round(bot_message[5] - bot_message[4],2)}%</b>\n'
        else:
            creating_message += f'Текущий: <b>{round(bot_message[5] - bot_message[4], 4)}%</b>\n'
        creating_message += f'Комиссия: <b>{round(float(bot_message[10]) + float(bot_message[11]), 2)}%</b>\n'

        # Спреды входа/выхода — местами значения
        creating_message += f'Спред входа: <b>{round(((float(bot_message[9]) / float(bot_message[19])) - 1) * 100, 2)}%</b> ({float(bot_message[9])} | {float(bot_message[19])})\n'
        creating_message += f'Спред выхода: <b>{round(((float(bot_message[20]) / float(bot_message[8])) - 1) * 100, 2)}%</b> ({float(bot_message[20])} | {float(bot_message[8])})\n'


        # Разница накопленных значений
        if bot_message[2] not in ['BitMart', 'Poloniex'] and bot_message[21] != '' and bot_message[25] != '':
            creating_message += (
                f'Накопленный 1 | 3 | 7 | 30 дней:\n '
                f'(<b>{round(float(bot_message[25]) - float(bot_message[21]), 2)}%</b> | '
                f'<b>{round(float(bot_message[26]) - float(bot_message[22]), 2)}%</b> | '
                f'<b>{round(float(bot_message[27]) - float(bot_message[23]), 2)}%</b> | '
                f'<b>{round(float(bot_message[28]) - float(bot_message[24]), 2)}%</b>)\n'
            )

    return creating_message


def add_inline_button_graphic(bot_message, m1):
    reversed_spread = False
    if bot_message[3] != m1:
        reversed_spread = True
    if not reversed_spread:
        return InlineKeyboardButton(text='График 📈', web_app=WebAppInfo(
                    url=f'{ORIGIN}/trade/futures/{bot_message[3]}/{bot_message[2]}/{bot_message[1].replace("USDT","")}/'))
    else:
        return InlineKeyboardButton(text='График 📈', web_app=WebAppInfo(
            url=f'{ORIGIN}/trade/futures/{bot_message[2]}/{bot_message[3]}/{bot_message[1].replace("USDT", "")}/'))


def add_inline_button_graphic_spot(bot_message):
    return InlineKeyboardButton(text='График 📈', web_app=WebAppInfo(
                url=f'{ORIGIN}/trade/spot/{bot_message[2]}/{bot_message[3]}/{bot_message[1].replace("USDT","")}/'))

def add_inline_button_graphic_dex(market2, symbol):
    return InlineKeyboardButton(text='График 📈', web_app=WebAppInfo(
                url=f'{ORIGIN}/trade/spot/Dex/{market2}/{symbol}/'))

def create_message_to_dex(bot_message):
    """
    Форматирует подробное сообщение по DEX-↔-CEX связке.
    bot_message tuple format (we used):
    (0, symbol, dex_market, cex_market, dex_bid, price_usd, diff, contract, chain, volume24, volume24_cex, url, cex_ask, funding_rate)
    Возвращаем HTML строку (parse_mode='HTML').
    """
    try:
        chain_show, symbol = str(bot_message[1]).split('_')
        dex_market = str(bot_message[2])
        cex_market = str(bot_message[3])
        dex_bid = bot_message[4]
        price_usd = bot_message[5]
        diff = bot_message[6]
        contract = bot_message[7] if len(bot_message) > 7 else ''
        chain = bot_message[8] if len(bot_message) > 8 else ''
        volume_dex = bot_message[9] if len(bot_message) > 9 else 0
        volume_cex = bot_message[10] if len(bot_message) > 10 else 0
        url = bot_message[11] if len(bot_message) > 11 else ''
        cex_ask = bot_message[12] if len(bot_message) > 12 else 0
        funding_rate = bot_message[13] if len(bot_message) > 13 else 0

        # Формируем ссылки по биржам — переиспользуем логику из create_message_to_spot,
        # но оставим короткие для dex (если хочешь — расширим для всех бирж)
        def make_cex_link(market, pair):
            pair_clean = str(pair)
            pair_clean_usdt = pair_clean.replace("USDT", "")
            lower = pair_clean.lower()

            if market == 'Bybit':
                return f'<a href="https://www.bybit.com/trade/usdt/{pair_clean}">{market}</a>'
            elif market == 'Mexc':
                return f'<a href="https://futures.mexc.com/ru-RU/exchange/{pair_clean.replace("USDT", "_USDT")}?type=linear_swap">{market}</a>'
            elif market == 'Kucoin':
                return f'<a href="https://www.kucoin.com/ru/futures/trade/{pair_clean.replace("USDT", "USDTM")}">{market}</a>'
            elif market == 'Gateio':
                return f'<a href="https://www.gate.io/ru/futures/USDT/{pair_clean.replace("USDT", "_USDT")}">{market}</a>'
            elif market == 'Bitget':
                return f'<a href="https://www.bitget.com/ru/futures/usdt/{pair_clean}">{market}</a>'
            elif market == 'Huobi':
                return f'<a href="https://www.htx.com/futures/linear_swap/exchange#contract_code={pair_clean.replace("USDT", "-USDT")}&contract_type=swap&type=cross">{market}</a>'
            elif market == 'Okx':
                return f'<a href="https://www.okx.com/ru/trade-swap/{lower.replace("usdt", "-usdt-swap")}">{market}</a>'
            elif market == 'Binance':
                return f'<a href="https://www.binance.com/ru/futures/{pair_clean}">{market}</a>'
            elif market == 'BingX':
                return f'<a href="https://swap.bingx.com/ru-ru/{pair_clean.replace("USDT", "-USDT")}">{market}</a>'
            elif market == 'BitMart':
                return f'<a href="https://derivatives.bitmart.com/ru-RU?symbol={pair_clean}&theme=dark">{market}</a>'
            elif market == 'Poloniex':
                return f'<a href="https://poloniex.com/futures/trade/{pair_clean.replace("USDT", "USDTPERP")}">{market}</a>'
            elif market == 'CoinEx':
                return f'<a href="https://www.coinex.com/ru/futures/{pair_clean.replace("USDT", "-USDT").lower()}">{market}</a>'
            elif market == 'Ourbit':
                return f'<a href="https://futures.ourbit.com/ru-RU/exchange/{pair_clean.replace("USDT", "_USDT")}?type=linear_swap">{market}</a>'
            elif market == 'Hyperliquid':
                return f'<a href="https://app.hyperliquid.xyz/trade/{pair_clean_usdt}">{market}</a>'
            elif market == 'LBank':
                return f'<a href="https://www.lbank.com/futures/{pair_clean.lower()}">{market}</a>'
            elif market == 'Aster':
                return f'<a href="https://www.asterdex.com/ru/trade/pro/futures/{pair_clean}">{market}</a>'
            elif market == 'XT':
                return f'<a href="https://www.xt.com/ru/futures/trade/{lower.replace("usdt", "_usdt")}">{market}</a>'
            elif market == 'WEEX':
                return f'<a href="https://www.weex.com/futures/{pair_clean.replace("USDT", "-USDT")}">{market}</a>'
            elif market == 'Phemex':
                return f'<a href="https://phemex.com/futures/{pair_clean.replace("USDT", "-USDT")}">{market}</a>'
            elif market == 'BinanceAlpha':
                # Ищем контракт в Redis
                _ba_c = _load_key_from_redis(0, "BinanceAlpha:contracts") or {}
                _ba_i = _ba_c.get(pair_clean, {})
                _ba_a = _ba_i.get('contract_address', '')
                _ba_ch = _ba_i.get('chain_name', 'bsc')
                if _ba_a:
                    return f'<a href="https://www.binance.com/en/alpha/{_ba_ch}/{_ba_a}">{market}</a>'
                return f'<b>{market}</b>'
            else:
                # fallback для неизвестных бирж
                return f'<b>{market}</b>'

        # Ссылки/названия
        cex_display = make_cex_link(cex_market, symbol) if cex_market else cex_market
        dex_display = url if url else dex_market
        # Заголовок + краткий блок
        creating_message = ''
        creating_message += f'<b>{symbol} [{chain_show}]</b>\n\n'
        # Первый блок — DEX (BUY)
        creating_message += f'📗|<a href="{url}">{dex_market}</a>| - BUY\n\n'
        if volume_dex:
            creating_message += f'Объем: <b>{fmt_amount_usd(volume_dex)}$</b>\n'
        creating_message += f'Цена: <b>{price_usd}$</b>\n'
        creating_message += '\n\n\n\n'
        # Второй блок — CEX/FUTURES (SHORT)
        creating_message += f'📕|{cex_display}| - SHORT\n\n'
        # отображаем текущие значения: diff как "спред входа"
        creating_message += f'Текущая: <b>{funding_rate}%</b>\n'
        if volume_cex:
            creating_message += f'Объем: <b>{fmt_amount_usd(volume_cex)}$</b>\n'
        creating_message += f'Цена: <b>{cex_ask}$</b>\n\n\n'
        creating_message += f'Спред входа: <b>{round(float(diff), 4)}%</b>\n'



        creating_message += '\n'
        # мета
        if contract:
            creating_message += f'Контракт: <code>{contract}</code>\n'
        if chain:
            creating_message += f'Chain: <b>{chain}</b>\n'
        if url:
            creating_message += f'\nСсылка: <a href="{url}">dexscreener</a>\n'

        return creating_message
    except Exception:
        logger.exception("create_message_to_dex failed")
        return "Ошибка формирования сообщения DEX."

def fmt_amount_usd(x):
    """
    Форматирование объёма в человекочитаемый вид:
      123 -> "123"
      1234 -> "1.23K" -> будет "1.2K" (1 decimal, trailing zeros removed)
      1_234_567 -> "1.23M" -> "1.2M"
      1_200_000 -> "1.2M"
      1000 -> "1K"
    Безопасно для строк/None: возвращает исходное значение как str, если не парсится в float.
    """
    try:
        if x is None:
            return "0"
        # если уже строка с $ или суффиксами — просто вернуть (предположим, что пользователь не прошит)
        if isinstance(x, str):
            xs = x.strip()
            # убрать знак $ в конце/начале, если есть
            if xs.endswith('$'):
                xs = xs[:-1].strip()
            # попробовать конвертировать
            val = float(xs.replace(',', '').replace(' ', ''))
        else:
            val = float(x)
    except Exception:
        # если не получилось преобразовать — вернуть оригинал как строку
        try:
            return str(x)
        except:
            return "0"

    neg = val < 0
    v = abs(val)

    def strip_trailing(s):
        # убираем лишние .0
        s = s.rstrip('0').rstrip('.') if '.' in s else s
        return s

    if v >= 1_000_000_000:
        s = f"{v / 1_000_000_000:.1f}"
        s = strip_trailing(s) + "B"
    elif v >= 1_000_000:
        s = f"{v / 1_000_000:.1f}"
        s = strip_trailing(s) + "M"
    elif v >= 1_000:
        s = f"{v / 1_000:.1f}"
        s = strip_trailing(s) + "K"
    else:
        # для маленьких — показываем целое, если возможно, иначе 2 знака
        if v == int(v):
            s = str(int(v))
        else:
            s = strip_trailing(f"{v:.2f}")

    return ("-" if neg else "") + s


def _safe_str(v, default='-'):
    if v is None:
        return default
    return str(v)

def _safe_num(v, fmt=None, default='-'):
    try:
        if v is None or v == '':
            return default
        n = float(v)
        if fmt:
            return fmt % n
        # default two decimals for percents if numeric
        return ("%.2f" % n).rstrip('0').rstrip('.') if isinstance(n, float) else str(n)
    except Exception:
        return default

def _ensure_int_page(page_val):
    try:
        if isinstance(page_val, str) and page_val.isdigit():
            return int(page_val)
    except Exception:
        pass
    return page_val

def _format_current_value(val, market_name=None):
    """
    Формат 'Текущая' по правилам:
      - по умолчанию: максимум 2 знака, минимум 1 (2 -> 2.0, 2.1 -> 2.1, 2.15 -> 2.15)
      - для Hyperliquid/Aster: точно 4 знака (например 0.1234)
    """
    try:
        n = float(val)
    except Exception:
        return _safe_str(val)

    # special markets -> 4 decimals
    if isinstance(market_name, str) and market_name in ("Hyperliquid", "Aster"):
        s = f"{n:.4f}"
        # keep exactly 4 decimals (as requested)
        return s

    # default: up to 2 decimals but at least 1
    s = f"{n:.2f}"  # always two decimals
    if s.endswith("00"):
        # integer -> show one decimal
        return f"{int(round(n))}.0"
    if s.endswith("0"):
        # x.y0 -> x.y
        return s[:-1]
    return s

def format_market_id_message(data: dict, mode: str = "futures", id_string: str = None) -> str:
    """
    Форматирует текст (HTML) для деталей спреда.
    Соответствует стилю React renderFuturesDetails / renderSpotFuturesDetails и старому create_message_to_futures.
    """
    # автоопределение режима
    if mode is None:
        if isinstance(data.get("markets"), dict) and data["markets"].get("long") and data["markets"].get("short"):
            mode = "futures"
        elif data.get("market1") or data.get("market2"):
            mode = "spot_futures"
        else:
            mode = "futures"

    out_lines = []

    # -------------------------
    # FUTURES (markets.long/short)
    # -------------------------
    if mode == "futures" and data.get("markets"):
        longm = (data.get("markets") or {}).get("long") or {}
        shortm = (data.get("markets") or {}).get("short") or {}

        coin = _safe_str(data.get("coin") or data.get("symbol") or "")
        icon = _safe_str(data.get("icon", ""))
        title = f"{html.escape(coin)} {html.escape(icon)}".strip()
        out_lines.append(f"<b>{title}</b>")
        out_lines.append("")

        # LONG card
        long_name = html.escape(_safe_str(longm.get("market") or longm.get("name") or ""))
        long_link = _safe_str(longm.get("link") or "#")
        if long_link and long_link != "#":
            out_lines.append(f'📗|<a href="{html.escape(long_link)}" target="_blank">{long_name}</a>| - LONG')
        else:
            out_lines.append(f'📗|{long_name}| - LONG')
        out_lines.append("")

        # funding_current (Текущая) — форматируем с учётом special markets
        long_market_name_raw = (longm.get("market") or longm.get("name") or "")
        long_fund_raw = longm.get("funding_current", "")
        long_fund_str = _format_current_value(long_fund_raw, market_name=long_market_name_raw)
        out_lines.append(f"Текущая: <strong>{html.escape(long_fund_str)}%</strong>")

        # Объем — используем fmt_amount_usd если возможно (без дополнительного округления)
        vol_val = longm.get("volume24", longm.get("volume24_m1", 0))
        vol_text = "0"
        try:
            if vol_val is None or vol_val == "":
                vol_text = "0"
            else:
                vol_text = fmt_amount_usd(float(vol_val))
        except Exception:
            vol_text = _safe_str(vol_val)
        if vol_text != "0":
            out_lines.append(f"Объем: <strong>{html.escape(vol_text)}$</strong>")

        # Лимит — округление как раньше
        lim = longm.get("limit", 0)
        try:
            lim_num = float(lim)
        except Exception:
            lim_num = 0.0
        if lim_num != 0:
            out_lines.append(f"Лимит: <strong>{int(round(lim_num))}$</strong>")

        out_lines.append(f"Стремится: {_safe_str(longm.get('funding_target', longm.get('tendency', '-')))}%")
        out_lines.append(f"🕓: {_safe_str(longm.get('time', '-'))}ч")
        out_lines.append("")

        # SHORT card
        short_name = html.escape(_safe_str(shortm.get("market") or shortm.get("name") or ""))
        short_link = _safe_str(shortm.get("link") or "#")
        if short_link and short_link != "#":
            out_lines.append(f'📕|<a href="{html.escape(short_link)}" target="_blank">{short_name}</a>| - SHORT')
        else:
            out_lines.append(f'📕|{short_name}| - SHORT')
        out_lines.append("")

        short_market_name_raw = (shortm.get("market") or shortm.get("name") or "")
        short_fund_raw = shortm.get("funding_current", "")
        short_fund_str = _format_current_value(short_fund_raw, market_name=short_market_name_raw)
        out_lines.append(f"Текущая: <strong>{html.escape(short_fund_str)}%</strong>")

        vol_val_s = shortm.get("volume24", shortm.get("volume24_m2", "0"))
        if vol_val_s != "0":
            out_lines.append(f"Объем: <strong>{html.escape(str(vol_val_s))}$</strong>")

        lim_s = shortm.get("limit", 0)
        try:
            lim_s_num = float(lim_s)
        except Exception:
            lim_s_num = 0.0
        if lim_s_num != 0:
            out_lines.append(f"Лимит: <strong>{int(round(lim_s_num))}$</strong>")

        out_lines.append(f"Стремится: {_safe_str(shortm.get('funding_target', shortm.get('tendency', '-')))}%")
        out_lines.append(f"🕓: {_safe_str(shortm.get('time', '-'))}ч")
        out_lines.append("")

        # Spread block
        spread = data.get("spread") or {}
        # формат текущего спреда — тоже применяем _format_current_value (без market special)
        spread_current_raw = spread.get("current", "")
        spread_current_str = _format_current_value(spread_current_raw, market_name=None)
        fee = _safe_str(spread.get("fee") or (data.get("fees") or {}).get("total", "-"))
        out_lines.append("💰 Спред:")
        out_lines.append(f"Текущий: <strong>{html.escape(spread_current_str)}%</strong>")
        out_lines.append(f"Комиссия: <strong>{html.escape(fee)}%</strong>")

        # entry / exit raw
        entry = spread.get("entry") if isinstance(spread, dict) else None
        exit_ = spread.get("exit") if isinstance(spread, dict) else None
        if entry is not None:
            entry_raw = spread.get("entry_raw") or []
            bid = _safe_str(entry_raw[0]) if isinstance(entry_raw, (list, tuple)) and len(entry_raw) > 0 else _safe_str(spread.get("entry_raw_bid", "-"))
            ask = _safe_str(entry_raw[1]) if isinstance(entry_raw, (list, tuple)) and len(entry_raw) > 1 else _safe_str(spread.get("entry_raw_ask", "-"))
            out_lines.append(f"Спред входа: <strong>{round(float(entry),2)}%</strong> ({html.escape(bid)} | {html.escape(ask)})")
        if exit_ is not None:
            exit_raw = spread.get("exit_raw") or []
            bid_e = _safe_str(exit_raw[0]) if isinstance(exit_raw, (list, tuple)) and len(exit_raw) > 0 else _safe_str(spread.get("exit_raw_bid", "-"))
            ask_e = _safe_str(exit_raw[1]) if isinstance(exit_raw, (list, tuple)) and len(exit_raw) > 1 else _safe_str(spread.get("exit_raw_ask", "-"))
            out_lines.append(f"Спред выхода: <strong>{round(float(exit_),2)}%</strong> ({html.escape(bid_e)} | {html.escape(ask_e)})")

        return "\n".join(out_lines)

    # --------------------------------
    # SPOT + FUTURES (market1 / market2)
    # --------------------------------
    if mode == "spot_futures" or data.get("market1") or data.get("market2") or data.get("spread"):
        coin = _safe_str(data.get("symbol") or data.get("coin") or "")
        top = _safe_str(data.get("top_coin", ""))
        title = f"{html.escape(coin)} {html.escape(top)}".strip()
        out_lines.append(f"<b>{title}</b>")
        out_lines.append("")

        m1 = data.get("market1", {}) or {}
        m2 = data.get("market2", {}) or {}
        spread_block = data.get("spread", {}) or {}

        # market1 (LONG)
        m1_name = html.escape(_safe_str(m1.get("name") or m1.get("market") or ""))
        m1_link = _safe_str(m1.get("link") or "#")
        if m1_link and m1_link != "#":
            out_lines.append(f'📗|<a href="{html.escape(m1_link)}" target="_blank">{m1_name}</a>| - BUY')
        else:
            out_lines.append(f'📗|{m1_name}| - BUY')
        out_lines.append("")
        vol1_val = spread_block.get("volume24_m1", 0)
        vol1_text = "0"
        try:
            if vol1_val is None or vol1_val == "":
                vol1_text = "0"
            else:
                vol1_text = fmt_amount_usd(float(vol1_val))
        except Exception:
            vol1_text = _safe_str(vol1_val)
        if vol1_text != "0":

            out_lines.append(f"Объем: <strong>{html.escape(vol1_text)}$</strong>")
            out_lines.append("")
            out_lines.append("")
            out_lines.append("")
        else:
            out_lines.append("")
            out_lines.append("")
            out_lines.append("")
            out_lines.append("")

        # market2 (SHORT)
        m2_name = html.escape(_safe_str(m2.get("name") or m2.get("market") or ""))
        m2_link = _safe_str(m2.get("link") or "#")
        if m2_link and m2_link != "#":
            out_lines.append(f'📕|<a href="{html.escape(m2_link)}" target="_blank">{m2_name}</a>| - SHORT')
        else:
            out_lines.append(f'📕|{m2_name}| - SHORT')
        out_lines.append("")
        # Текущая (используем formatting)
        if spread_block.get("current") is not None:
            cur_raw = spread_block.get("current")
            cur_str = _format_current_value(cur_raw, market_name=(m2.get("name") or m2.get("market")))
            out_lines.append(f"Текущая: <strong>{html.escape(cur_str)}%</strong>")

        vol2_val = spread_block.get("volume24_m2", 0)
        vol2_text = "0"
        try:
            if vol2_val is None or vol2_val == "":
                vol2_text = "0"
            else:
                vol2_text = fmt_amount_usd(float(vol2_val))
        except Exception:
            vol2_text = _safe_str(vol2_val)
        if vol2_text != "0":
            out_lines.append(f"Объем: <strong>{html.escape(vol2_text)}$</strong>")

        lim_val = spread_block.get("limit", 0)
        try:
            lim_num = float(lim_val)
        except Exception:
            lim_num = 0.0
        if lim_num != 0:
            out_lines.append(f"Лимит: <strong>{int(round(lim_num))}$</strong>")

        tendency = _safe_str(spread_block.get("tendency", spread_block.get("funding_target", "-")))
        if tendency != "-":
            out_lines.append(f"Стремится: {html.escape(tendency)}%")
        time_h = _safe_str(spread_block.get("time_h", "-"))
        out_lines.append(f"🕓: {html.escape(time_h)}ч")
        out_lines.append("")

        # spread/fess/entry/exit
        fees = data.get("fees", {}) or {}
        out_lines.append("💰 Спред:")
        if spread_block.get("current") is not None:
            cur_s = _format_current_value(spread_block.get("current"))
            out_lines.append(f"Текущий: <strong>{html.escape(cur_s)}%</strong>")
        if fees.get("total") is not None:
            out_lines.append(f"Комиссия: <strong>{html.escape(_safe_str(fees.get('total')))}%</strong>")

        # entry_spread / exit_spread
        entry_spread = data.get("entry_spread") or spread_block.get("entry_spread") or spread_block.get("entry")
        if entry_spread:
            val = _safe_str(entry_spread.get("value") if isinstance(entry_spread, dict) else entry_spread)
            bid = _safe_str(entry_spread.get("bid") if isinstance(entry_spread, dict) else (entry_spread[0] if isinstance(entry_spread, (list,tuple)) and len(entry_spread)>0 else "-"))
            ask = _safe_str(entry_spread.get("ask") if isinstance(entry_spread, dict) else (entry_spread[1] if isinstance(entry_spread, (list,tuple)) and len(entry_spread)>1 else "-"))
            out_lines.append(f"Спред входа: <strong>{val}%</strong> ({bid} | {ask})")
        exit_spread = data.get("exit_spread") or spread_block.get("exit_spread") or spread_block.get("exit")
        if exit_spread:
            val = _safe_str(exit_spread.get("value") if isinstance(exit_spread, dict) else exit_spread)
            bid = _safe_str(exit_spread.get("bid") if isinstance(exit_spread, dict) else (exit_spread[0] if isinstance(exit_spread, (list,tuple)) and len(exit_spread)>0 else "-"))
            ask = _safe_str(exit_spread.get("ask") if isinstance(exit_spread, dict) else (exit_spread[1] if isinstance(exit_spread, (list,tuple)) and len(exit_spread)>1 else "-"))
            out_lines.append(f"Спред выхода: <strong>{val}%</strong> ({bid} | {ask})")

        return "\n".join(out_lines)

    # fallback — raw
    pretty = html.escape(json.dumps(data, ensure_ascii=False, indent=2))
    return f"<pre>{pretty}</pre>"
