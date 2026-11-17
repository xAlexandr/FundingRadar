# файл: page_markets.py
import json
import logging
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from libs.tgfunc import *
import os
import aiohttp
import orjson
import html  # для безопасного вывода, если нужно
import math
from aiogram.types import WebAppInfo

router = Router(name=__name__)
logger = logging.getLogger("page_markets")

FILTER_HOST = os.getenv('FILTER_HOST', 'localhost')
GO_BASE = f"http://{FILTER_HOST}:8081"
ORIGIN = os.getenv('ORIGIN')

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

async def fetch_go_futures(user_id: int, page: int = 1, items: int = 5, sort: str = "spread", lt: int = 0, timeout=5):
    """
    Запрос к /api/futures — общий список (главная таблица).
    Возвращает JSON как у фронтенда: { status, pages: [...], current_page, total_pages, ... }
    """
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

def add_pagination_buttons_from_service(builder: InlineKeyboardBuilder, service_response: dict, prefix: str = "futures"):
    """
    Универсальная пагинация для ответа сервиса.
    prefix: 'futures' -> callbacks futures_page:N
            'spot'    -> callbacks spot_page:N
    service_response ожидается с current_page и total_pages (fallbacks handled)
    """
    current_page = int(service_response.get("current_page") or service_response.get("start_page") or 1)
    total_pages = int(service_response.get("total_pages") or service_response.get("end_page") or current_page)

    prev_page = max(1, current_page - 1)
    next_page = min(total_pages, current_page + 1)

    if prefix == "spot":
        prev_cb = f"spot_page:{prev_page}"
        center_cb = f"spot_page:1"
        next_cb = f"spot_page:{next_page}"
    else:
        prev_cb = f"futures_page:{prev_page}"
        center_cb = f"futures_page:1"
        next_cb = f"futures_page:{next_page}"

    prev_button = InlineKeyboardButton(text="<", callback_data=prev_cb)
    center_button = InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data=center_cb)
    next_button = InlineKeyboardButton(text=">", callback_data=next_cb)

    builder.row(prev_button, center_button, next_button)

async def fetch_go_futures_id(user_id: int, market1: str, market2: str, symbol: str, timeout=5):
    """
    Запрос к /api/futures_id
    Ожидаемые параметры: user_id, market1, market2, symbol
    """
    params = {
        "user_id": str(user_id),
        "m1": market1,
        "m2": market2,
        "symbol": symbol,
    }
    url = f"{GO_BASE}/api/futures_id"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.json()

def build_id_buttons(id_string: str, data: dict):
    """
    Возвращает InlineKeyboardBuilder с кнопками:
      [Обновить (callback -> market_id_reload:{id_string})]
      [График 📈 (WebApp -> ORIGIN/trade/futures/{market1}/{market2}/{symbol}/)]
    Ссылки всегда строятся от ORIGIN, не из данных Go.
    """
    builder = InlineKeyboardBuilder()

    # Кнопка обновления
    btn_update = InlineKeyboardButton(
        text="Обновить",
        callback_data=f"market_id_reload:{id_string}"
    )

    # Разбираем id_string
    # формат ожидается: id{num}_{market1}_{market2}_{symbol}
    parts = id_string.split("_")
    p_m1 = parts[1] if len(parts) > 1 else None
    p_m2 = parts[2] if len(parts) > 2 else None
    p_sym = parts[3] if len(parts) > 3 else None

    btn_graph = None
    if p_m1 and p_m2 and p_sym:
        sym_clean = p_sym.replace("USDT", "")
        chart_url = f"{ORIGIN.rstrip('/')}/trade/futures/{p_m1}/{p_m2}/{sym_clean}/"
        # Кнопка графика (WebApp)
        btn_graph = InlineKeyboardButton(
            text="График 📈",
            web_app=WebAppInfo(url=chart_url)
        )

    # Добавляем кнопки в строку
    if btn_graph:
        builder.row(btn_update, btn_graph)
    else:
        builder.row(btn_update)

    return builder


# обработчик перезагрузки (редактирует текущее сообщение)
@router.callback_query(F.data.startswith("market_id_reload:"))
async def handle_market_id_reload(call: types.CallbackQuery):
    await call.answer()  # убрать "крутилку" у клиента

    try:
        payload = call.data.split(":", 1)
        if len(payload) < 2:
            await call.message.answer("Неправильный callback id.")
            return
        id_string = payload[1]
        parts = id_string.split("_")
        if len(parts) < 4:
            await call.message.answer("Неправильный формат id.")
            return

        market1 = parts[1]
        market2 = parts[2]
        symbol = parts[3]
        user_id = call.from_user.id

        # запрос к Go
        try:
            resp = await fetch_go_futures_id(user_id=user_id, market1=market1, market2=market2, symbol=symbol)
        except Exception as e:
            logger.exception("fetch_go_futures_id error (reload): %s", e)
            try:
                await call.message.answer("Ошибка получения подробностей спреда. Повторите позже.")
            except Exception:
                pass
            return

        if not isinstance(resp, dict):
            await call.message.answer("Ответ сервиса в неверном формате.")
            return

        status = resp.get("status")
        if status in ("no_sub", "inactive"):
            await call.message.answer("Нет активной подписки.")
            return
        if status == "empty":
            await call.message.answer("Нет данных для этой пары.")
            return

        data = resp.get("data")
        if not data:
            await call.message.answer("Данные недоступны.")
            return

        # определяем режим и форматируем текст
        mode = None
        if isinstance(data.get("markets"), dict) and data["markets"].get("long") and data["markets"].get("short"):
            mode = "futures"
        elif data.get("market1") or data.get("market2"):
            mode = "spot_futures"

        msg = format_market_id_message(data, mode=mode, id_string=id_string)
        if not msg:
            await call.message.answer("Нет данных для отображения.")
            return

        # клавиатура
        kb = build_id_buttons(id_string, data)

        # пытаемся редактировать текущее сообщение (чтобы не спамить)
        try:
            await call.message.edit_text(text=msg, parse_mode="HTML", reply_markup=kb.as_markup(), disable_web_page_preview=True)
        except TelegramBadRequest:
            pass

    except Exception:
        logger.exception("Error in handle_market_id_reload")
        try:
            await call.message.answer("Произошла ошибка при перезагрузке данных.")
        except Exception:
            pass

# короткий handle — использует format_market_id_message
@router.callback_query(F.data.startswith("market_id:"))
async def handle_market_id(call: types.CallbackQuery):
    await call.answer()  # убрать "крутилку"
    try:
        payload = call.data.split(":", 1)
        if len(payload) < 2:
            await call.message.answer("Неправильный callback id.")
            return
        id_string = payload[1]
        parts = id_string.split("_")
        if len(parts) < 4:
            await call.message.answer("Неправильный формат id.")
            return

        market1 = parts[1]
        market2 = parts[2]
        symbol = parts[3]
        user_id = call.from_user.id

        # запрос к Go
        try:
            resp = await fetch_go_futures_id(user_id=user_id, market1=market1, market2=market2, symbol=symbol)
        except Exception as e:
            logger.exception("fetch_go_futures_id error: %s", e)
            await call.message.answer("Ошибка получения подробностей спреда. Повторите позже.")
            return

        if not isinstance(resp, dict):
            await call.message.answer("Ответ сервиса в неверном формате.")
            return

        status = resp.get("status")
        if status == "no_sub" or status == "inactive":
            await call.message.answer("Нет активной подписки.")
            return
        if status == "empty":
            await call.message.answer("Нет данных для этой пары.")
            return

        data = resp.get("data")
        if not data:
            await call.message.answer("Данные недоступны.")
            return

        # Определим режим по структуре данных (как в React)
        mode = None
        if isinstance(data.get("markets"), dict) and data["markets"].get("long") and data["markets"].get("short"):
            mode = "futures"
        elif data.get("market1") or data.get("market2"):
            mode = "spot_futures"

        msg = format_market_id_message(data, mode=mode, id_string=id_string)
        if not msg:
            await call.message.answer("Нет данных для отображения.")
            return

      #  await call.message.answer(text=msg, parse_mode="HTML", disable_web_page_preview=True)
        kb = build_id_buttons(id_string, data)
        await call.message.answer(text=msg, parse_mode="HTML", reply_markup=kb.as_markup(), disable_web_page_preview=True)
    except Exception:
        logger.exception("Error in handle_market_id")
        try:
            await call.message.answer("Произошла ошибка при обработке запроса.")
        except Exception:
            pass
# -----------------------
# helpers: запросы к Go
# -----------------------
async def fetch_go_futures_pages(user_id: int, symbol: str, page: int = 1, items: int = 5,
                                 sort: str = "spread", lt: int = 0, timeout=5):
    """
    Запрос к /api/futures_pages
    service expects 1-based page
    """
    params = {
        "user_id": str(user_id),
        "symbol": symbol,
        "page": str(page),
        "items": str(items),
        "sort": sort,
        "lt": str(lt),
    }
    url = f"{GO_BASE}/api/futures_pages"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.json()


def _extract_user_filters_from_accounts(accounts, user_id):
    """
    Возвращает (active: bool, dataSearch: dict)
    """
    for acc in accounts:
        if str(acc[2]) == str(user_id) and any(x == '1' for x in [acc[9], acc[10], acc[14]]):
            dataSearch_raw = acc[4] if acc[4] is not None else 'no'
            try:
                if dataSearch_raw == 'no':
                    dataSearch = {}
                else:
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
    Map dataSearch -> sort, lt
    Подправь логику, если у тебя другие поля.
    """
    sort = "spread"
    lt = 0

    if dataSearch.get("filter_course_or_spread") == "1":
        sort = "spread"
    else:
        sort = "funding"

    # lt: если включён "Вход > 0" — это у тебя в dataSearch как 'filter_big_or_all_course' == '1'
    if dataSearch.get("filter_big_or_all_course") == "1":
        lt = 1
    else:
        lt = 0

    return sort, lt


# -----------------------
# helpers: билд клавиатуры
# -----------------------
# --- вставьте рядом с другими helpers вверху файла ---

def add_page_from_pagination(builder: InlineKeyboardBuilder, current_page: int, total_pages: int, cb_prefix: str = "page_from"):
    """
    Построить строку Prev | current/total (-> first) | Next для page_from-пагинации.
    current_page: 1-based
    total_pages: 1-based
    cb_prefix: 'page_from' (обычно) — функция формирует callbacks вида "{cb_prefix}:{offset}"
    offset — 0-based page index.
    Логика offset'ов совпадает с предыдущей: prev_offset = max(0, current_page-2), next_offset = min(total_pages-1, current_page)
    """
    try:
        cur = max(1, int(current_page))
    except Exception:
        cur = 1
    try:
        tp = max(1, int(total_pages))
    except Exception:
        tp = 1

    prev_offset = max(0, cur - 2)
    next_offset = min(max(0, tp - 1), cur)  # next offset = current_page (0-based)
    center_cb = f"{cb_prefix}:0"

    prev_button = InlineKeyboardButton(text="<", callback_data=f"{cb_prefix}:{prev_offset}")
    center_button = InlineKeyboardButton(text=f"{cur}/{tp}", callback_data=center_cb)
    next_button = InlineKeyboardButton(text=">", callback_data=f"{cb_prefix}:{next_offset}")

    builder.row(prev_button, center_button, next_button)


def build_market_buttons_from_service_page(builder: InlineKeyboardBuilder, page_obj):
    """
    Построение кнопок вида market:SYMBOL из page_obj (items: [text, symbol]).
    Используется для основного списка (список рынков) — callback 'market:SYMBOL'.
    """
    for item in page_obj.get("items", []):
        try:
            text = item[0]
            symbol = item[1]
            builder.row(InlineKeyboardButton(text=text, callback_data=f"market:{symbol}"))
        except Exception:
            # если элемент неожиданного формата — пропустить
            continue

def build_inline_from_service_page(builder: InlineKeyboardBuilder, page_obj):
    """
    page_obj: dict with keys 'page' and 'items' (items is list of [text, id_string])
    Добавляет строки с кнопками (market_id callbacks)
    """
    for item in page_obj.get("items", []):
        text = item[0]
        id_string = item[1]
        # callback for selecting specific spread: reuse your existing handler for id clicks (it expects id_string like id0_Market1_Market2_SYMBOL)
        builder.row(InlineKeyboardButton(text=text, callback_data=f"market_id:{id_string}"))


def add_pagination_buttons_from_service_market(builder: InlineKeyboardBuilder, requested_page0: int,
                                               total_pages: int, symbol: str):
    """
    Prev | current/total (-> first) | Next
    requested_page0: 0-based page index (what we treat internally)
    total_pages: total pages (1-based count)
    callbacks: page_market:OFFSET:SYMBOL  (OFFSET is 0-based index page_start like your create_pagination_buttons)
    """
    # clamp
    current = max(0, min(requested_page0, max(0, total_pages - 1)))
    prev_offset = max(0, current - 1)
    next_offset = min(total_pages - 1, current + 1)

    # callbacks use 0-based offsets
    prev_button = InlineKeyboardButton(text="<", callback_data=f"page_market:{prev_offset}:{symbol}")
    center_button = InlineKeyboardButton(text=f"{current+1}/{total_pages}", callback_data=f"page_market:0:{symbol}")
    next_button = InlineKeyboardButton(text=">", callback_data=f"page_market:{next_offset}:{symbol}")

    builder.row(prev_button, center_button, next_button)


@router.callback_query(F.data.startswith("page_market"))
async def get_markets_pages(call: types.CallbackQuery):
    """
    Обработка Prev / Next / Center / фильтров для страницы конкретной монеты.
    callback format: page_market:OFFSET_OR_CMD:SYMBOL
    """
    logger.info('GOOOD!! PAGE_MARKET!')
    try:
        parts = str(call.data).split(':')
        if len(parts) < 3:
            logger.warning("page_market: bad callback data: %s", call.data)
            await call.message.answer("Неправильный callback.")
            return

        raw_page_start = parts[1]   # '0','1',... или 'spread','course','all','big'
        symbolFind = parts[2]
        user_id = call.from_user.id

        logger.info("page_market called: raw_page_start=%s symbol=%s user=%s", raw_page_start, symbolFind, user_id)

        # Получим snapshot accounts (нужны для change_to_* и для извлечения dataSearch)
        accounts = fetch_accounts_from_db()
        active, dataSearch_db = _extract_user_filters_from_accounts(accounts, user_id)

        dataSearch_from_change = None
        is_command = False

        # Обрабатываем командные значения (фильтры) — они могут изменить БД
        try:
            if raw_page_start == 'all':
                is_command = True
                _, dataSearch_from_change = change_to_big(accounts, None, user_id)
            elif raw_page_start == 'big':
                is_command = True
                _, dataSearch_from_change = change_to_all(accounts, None, user_id)
            elif raw_page_start == 'spread':
                is_command = True
                _, dataSearch_from_change = change_to_spread(accounts, None, user_id)
            elif raw_page_start == 'course':
                is_command = True
                _, dataSearch_from_change = change_to_course(accounts, None, user_id)
            # иначе — навигация, ничего не меняем
        except Exception:
            logger.exception("Error processing change_to_* in page_market")
            # продолжаем дальше — не фатально

        # helper для приведения dataSearch -> dict
        def _normalize_dataSearch(ds):
            if ds is None:
                return None
            try:
                if isinstance(ds, (bytes, bytearray)):
                    return orjson.loads(ds)
                if isinstance(ds, str):
                    if ds == 'no':
                        return {}
                    try:
                        return orjson.loads(ds)
                    except Exception:
                        # строка, которую не парсить — вернуть пустой dict
                        return {}
                if isinstance(ds, dict):
                    return ds
            except Exception:
                logger.exception("Failed to normalize dataSearch (from change_to_*).")
            return {}

        # Если была команда — перезагрузим accounts и используем свежие dataSearch (приоритет: результат change_to_* если валиден)
        if is_command:
            normalized = _normalize_dataSearch(dataSearch_from_change)
            # если change_to_* вернул что-то валидное — используем это, иначе используем то, что лежит в snapshot Accounts
            dataSearch = normalized if (normalized is not None and normalized != {}) else (dataSearch_db or {})
            page_offset = 0
            service_page = 1
        else:
            # навигация — это 0-based offset
            try:
                page_offset = int(_ensure_int_page(raw_page_start))
            except Exception:
                page_offset = 0
            service_page = max(1, page_offset + 1)

            # используем dataSearch из snapshot accounts (dataSearch_db)
            dataSearch = dataSearch_db or {}

        # Проверяем подписку — если нет, отправляем сообщение пользователю
        if not active:
            try:
                await call.message.answer("Ваша подписка неактивна")
            except Exception:
                logger.warning("Failed to send 'subscription inactive' message")
            return

        # гарантируем, что dataSearch — dict
        if not isinstance(dataSearch, dict):
            dataSearch = _normalize_dataSearch(dataSearch) or {}

        # map params
        sort, lt = _map_dataSearch_to_service_params(dataSearch)

        logger.info(
            "Fetching futures_pages for user=%s symbol=%s page=%s sort=%s lt=%s (page_offset=%s)",
            user_id, symbolFind, service_page, sort, lt, page_offset
        )

        # запрос к Go
        try:
            resp = await fetch_go_futures_pages(user_id=user_id, symbol=symbolFind,
                                               page=service_page, items=5, sort=sort, lt=lt)
        except Exception as e:
            logger.exception("fetch_go_futures_pages error: %s", e)
            await call.message.answer(text='Ошибка получения данных от сервиса. Повторите позже.')
            return

        # если сервис вернул, что подписки нет — уведомляем
        if resp.get("status") in ("no_sub", "inactive"):
            await call.message.answer("Ваша подписка неактивна")
            return

        pages = resp.get("pages", [])
        total_pages = int(resp.get("total_pages", len(pages) if pages else 1))

        # Найдем объект страницы в ответе (service_page), fallback -> pages[0]
        page_obj = None
        for p in pages:
            try:
                if int(p.get("page", 0)) == service_page:
                    page_obj = p
                    break
            except Exception:
                continue
        if page_obj is None and pages:
            page_obj = pages[0]

        if not page_obj:
            await call.message.edit_text("Нет данных на этой странице.")
            return

        # Построим клавиатуру
        inline_kb1 = InlineKeyboardBuilder()
        build_inline_from_service_page(inline_kb1, page_obj)
        add_pagination_buttons_from_service_market(
            inline_kb1,
            requested_page0=page_offset,
            total_pages=total_pages,
            symbol=symbolFind
        )
        add_filter_buttons_futures_market(inline_kb1, dataSearch, symbolFind)

        try:
            await call.message.edit_text(text=f'Список спредов по {symbolFind}', reply_markup=inline_kb1.as_markup())
        except TelegramBadRequest:
            logger.warning("TelegramBadRequest when editing message (maybe too old)")

    except Exception:
        logger.exception("Error in get_markets_pages")


async def get_markets_callback(user_id: int, symbolFind: str, message: types.Message):
    """
    Обрабатывает поиск по монете (вызывается из FSM / CryptoTGbot).
    Предпочтительно использует Go /api/futures_pages, fallback — локальная БД.
    """
    try:
        # Сначала получаем snapshot accounts, проверяем подписку и dataSearch
        accounts = fetch_accounts_from_db()
        active, dataSearch = _extract_user_filters_from_accounts(accounts, user_id)

        if not active:
            await message.answer(text='Ваша подписка неактивна')
            return

        # маппим параметры на сервис
        sort, lt = _map_dataSearch_to_service_params(dataSearch)

        # Попытка получить данные из Go
        try:
            resp = await fetch_go_futures_pages(user_id=user_id, symbol=symbolFind, page=1, items=5, sort=sort, lt=lt)
        except Exception as e:
            logger.exception("fetch_go_futures_pages failed in get_markets_callback: %s", e)
            resp = None
        # Если ответ от Go есть и валиден — используем его
        if isinstance(resp, dict) and resp.get("status") not in ("no_sub", "inactive"):
            pages = resp.get("pages", [])
            total_pages = int(resp.get("total_pages", len(pages) if pages else 1))

            if not pages:
                # нет страниц — сообщим
                await message.answer(text='Нет данных для отображения.')
                return

            inline_kb1 = InlineKeyboardBuilder()
            # используем первую страницу (обычно pages[0] — это page 1)
            first_page_obj = pages[0]
            build_inline_from_service_page(inline_kb1, first_page_obj)

            # пагинация — используем твою существующую функцию
            add_pagination_buttons_from_service_market(inline_kb1, requested_page0=0, total_pages=total_pages, symbol=symbolFind)

            # добавляем кнопки-фильтры (если функция ожидает (builder, dataSearch, symbol))
            try:
                add_filter_buttons_futures_market(inline_kb1, dataSearch, symbolFind)
            except Exception:
                # если такой функции нет или сигнатура другая — пропускаем
                pass

            await message.answer(text=f'Список спредов по {symbolFind}', reply_markup=inline_kb1.as_markup())
            return

        # Если Go вернул, что подписка неактивна — уведомим
        if isinstance(resp, dict) and resp.get("status") in ("no_sub", "inactive"):
            await message.answer(text='Ваша подписка неактивна')
            return

    except Exception as e:
        logger.exception("Ошибка в get_markets_callback")
        try:
            await message.answer(text='Произошла ошибка при поиске монеты.')
        except Exception:
            pass


@router.callback_query(F.data.startswith("market"))
async def get_markets(call: types.CallbackQuery):
    """
    Нажали на кнопку с монетой (market:SYMBOL).
    Будем делать запрос к Go -> /api/futures_pages?symbol=SYMBOL&page=1...
    Если сервис упадёт — fallback к старой логике (fetch_spreads_symbol_from_db).
    """
    try:
        parts = str(call.data).split(':')
        if len(parts) < 2:
            await call.answer("Неправильный callback.", show_alert=True)
            return
        symbolFind = parts[1]
        logger.info("market called for symbol=%s user=%s", symbolFind, call.from_user.id)

        # получаем аккаунты только чтобы получить dataSearch и проверить подписку
        accounts = fetch_accounts_from_db()
        active, dataSearch = _extract_user_filters_from_accounts(accounts, call.from_user.id)

        if not active:
            await call.answer("Ваша подписка неактивна", show_alert=True)
            return

        # маппим параметры на сервис
        sort, lt = _map_dataSearch_to_service_params(dataSearch)

        try:
            resp = await fetch_go_futures_pages(user_id=call.from_user.id, symbol=symbolFind, page=1,
                                               items=5, sort=sort, lt=lt)
        except Exception as e:
            logger.exception("fetch_go_futures_pages failed, falling back to local DB: %s", e)
            await call.message.answer(text='Список спредов пуст или подписка неактивна')
            return

        # сервис вернул данные
        if resp.get("status") in ("no_sub", "inactive"):
            await call.answer("Ваша подписка неактивна", show_alert=True)
            return

        pages = resp.get("pages", [])
        total_pages = int(resp.get("total_pages", len(pages) if pages else 1))

        if not pages:
            await call.message.answer(text='Нет данных для отображения.')
            return

        inline_kb1 = InlineKeyboardBuilder()
        # используем первую страницу из ответа
        first_page_obj = pages[0]
        build_inline_from_service_page(inline_kb1, first_page_obj)
        add_pagination_buttons_from_service_market(inline_kb1, requested_page0=0, total_pages=total_pages, symbol=symbolFind)
        # фильтры специально для market view (если есть)
        add_filter_buttons_futures_market(inline_kb1, dataSearch, symbolFind)

        await call.message.answer(text=f'Список спредов по {symbolFind}', reply_markup=inline_kb1.as_markup())

    except Exception:
        logger.exception("Error in get_markets")


# --- замените старую функцию callbacks_num полностью на этот блок ---

@router.callback_query(F.data.startswith("page_from"))
async def callbacks_num(call: types.CallbackQuery):
    try:
        parts = call.data.split(':')
        page_start = parts[1] if len(parts) > 1 else '0'
       # logger.info('YEEEEEEEEEEEP IS PAGE FROM!!!!!!')

        # Нам нужен snapshot accounts чтобы проверить подписку и передать в change_to_*
        accounts = fetch_accounts_from_db()

        dataSearch_from_change = None
        is_command = False

        # Обрабатываем входную команду (date/filter/other)
        try:
            # фильтры all/big/spread/course
            if page_start == 'all':
                is_command = True
                page_start, dataSearch_from_change = change_to_big(accounts, None, call.from_user.id)
            elif page_start == 'big':
                is_command = True
                page_start, dataSearch_from_change = change_to_all(accounts, None, call.from_user.id)
            elif page_start == 'spread':
                is_command = True
                page_start, dataSearch_from_change = change_to_spread(accounts, None, call.from_user.id)
            elif page_start == 'course':
                is_command = True
                page_start, dataSearch_from_change = change_to_course(accounts, None, call.from_user.id)
            else:
                # навигация по номеру страницы
                page_start = _ensure_int_page(page_start)
        except Exception:
            logger.exception("Error processing page_start in callbacks_num")

        # helper: нормализатор для dataSearch, может быть bytes/str/dict
        def _normalize(ds):
            if ds is None:
                return {}
            try:
                if isinstance(ds, (bytes, bytearray)):
                    return orjson.loads(ds)
                if isinstance(ds, str):
                    return orjson.loads(ds) if ds != "no" else {}
                if isinstance(ds, dict):
                    return ds
            except Exception:
                logger.exception("Failed to normalize dataSearch in callbacks_num")
            return {}

        # Из snapshot accounts извлекаем active + dataSearch_db (используем snapshot, не делаем новый запрос)
        active, dataSearch_db = _extract_user_filters_from_accounts(accounts, call.from_user.id)

        # Решаем, какой dataSearch использовать: приоритет — результат change_to_* (если валиден), иначе snapshot
        if is_command:
            normalized = _normalize(dataSearch_from_change)
            dataSearch = normalized if (normalized and isinstance(normalized, dict)) else (dataSearch_db or {})
            # при командах мы хотим показать первую страницу сервиса
            req_page = 1
        else:
            # page_start здесь — 0-based offset
            try:
                offset = int(page_start)
            except Exception:
                offset = 0
            # сервис ожидает 1-based
            req_page = max(1, offset + 1)
            dataSearch = dataSearch_db or {}

        # Проверка подписки
        if not active:
            await call.message.answer(text='Ваша подписка неактивна')
            return

        # Убедимся, что dataSearch — dict
        if not isinstance(dataSearch, dict):
            dataSearch = _normalize(dataSearch) or {}

        # Map dataSearch -> sort, lt
        sort, lt = _map_dataSearch_to_service_params(dataSearch)

        # Запросим данные у Go (общая таблица фьючерсов), используем req_page
        try:
            resp = await fetch_go_futures(user_id=call.from_user.id, page=req_page, items=5, sort=sort, lt=lt)
        except Exception as e:
            logger.exception("fetch_go_futures error in callbacks_num: %s", e)
            await call.message.answer(text='Ошибка получения данных от сервиса. Повторите позже.')
            return

        if not isinstance(resp, dict):
            await call.message.answer(text='Ответ сервиса в неверном формате.')
            return

        if resp.get("status") in ("no_sub", "inactive"):
            await call.message.answer(text='Ваша подписка неактивна')
            return

        pages = resp.get("pages", [])
        total_pages = int(resp.get("total_pages", len(pages) if pages else 1))

        # Найдём объект страницы (1-based) — поведение как в других местах
        page_obj = None
        for p in pages:
            try:
                if int(p.get("page", 0)) == req_page:
                    page_obj = p
                    break
            except Exception:
                continue
        if page_obj is None and pages:
            page_obj = pages[0]

        if not page_obj:
            try:
                # как раньше: если нет данных — информируем пользователя
                await call.message.answer(text='Нет данных для отображения.')
            except Exception:
                pass
            return

        # Построим клавиатуру из ответа сервиса, но кнопки — market:SYMBOL (для первого уровня)
        inline_kb1 = InlineKeyboardBuilder()
        build_market_buttons_from_service_page(inline_kb1, page_obj)

        # Добавим строку пагинации (используем вынесенную функцию)
        current_page = int(resp.get("current_page") or req_page)
        add_page_from_pagination(inline_kb1, current_page=current_page, total_pages=total_pages, cb_prefix="page_from")

        # Добавляем кнопки фильтров как раньше
        try:
            add_filter_buttons_futures(inline_kb1, dataSearch)
        except Exception:
            # если функция другая — пропускаем
            pass

        # Попытка обновить UI — как и раньше, стараемся редактировать только reply_markup
        try:
            # предпочитаем обновить только клавиатуру (чтобы не перезаписывать текст)
            await call.message.edit_reply_markup(reply_markup=inline_kb1.as_markup())
        except TelegramBadRequest:
            # если редактирование не удалось (старое сообщение) — пробуем отредактировать текст целиком
            try:
                await call.message.edit_text(text='Список фьючерс/фьючерс', reply_markup=inline_kb1.as_markup())
            except TelegramBadRequest:
                logger.warning("TelegramBadRequest when editing message in callbacks_num (maybe message is too old)")

    except Exception:
        logger.exception("Error in callbacks_num")
        try:
            await call.message.answer("Ошибка при обработке запроса.")
        except Exception:
            pass

# --- конец замены callbacks_num ---



async def show_futures_page(user_id: int, page_start: int, message: types.Message):
    """
    Показать страницу общего списка фьючерсов.
    page_start — 0-based (как у твоего FSM), сервис ожидает 1-based.
    """
    try:
        # получаем аккаунты, чтобы взять dataSearch и проверить подписку
        accounts = fetch_accounts_from_db()
        active, dataSearch = _extract_user_filters_from_accounts(accounts, user_id)

        if not active:
            await message.answer(text='Ваша подписка неактивна.')
            return

        # map params
        sort, lt = _map_dataSearch_to_service_params(dataSearch)
        req_page = max(1, int(page_start) + 1)

        try:
            resp = await fetch_go_futures(user_id=user_id, page=req_page, items=5, sort=sort, lt=lt)
        except Exception as e:
            logger.exception("fetch_go_futures error: %s", e)
            await message.answer(text="Ошибка получения данных от сервиса. Повторите позже.")
            return

        if not isinstance(resp, dict):
            await message.answer("Ответ сервиса в неверном формате.")
            return

        if resp.get("status") in ("no_sub", "inactive"):
            await message.answer("Ваша подписка неактивна")
            return

        pages = resp.get("pages", [])
        total_pages = int(resp.get("total_pages", len(pages) if pages else 1))

        # Найдём объект страницы (1-based)
        page_obj = None
        for p in pages:
            try:
                if int(p.get("page", 0)) == req_page:
                    page_obj = p
                    break
            except Exception:
                continue
        if page_obj is None and pages:
            page_obj = pages[0]

        if not page_obj:
            await message.answer("Нет данных на этой странице.")
            return

        inline_kb1 = InlineKeyboardBuilder()
        build_inline_from_service_page(inline_kb1, page_obj)
        add_pagination_buttons_from_service(inline_kb1, resp, prefix="futures")
        # add_filter_buttons_futures_market / add_filter_buttons_futures — в зависимости от UI
        try:
            add_filter_buttons_futures(inline_kb1, dataSearch)
        except Exception:
            # если у тебя другая функция — оставляем просто
            pass

        await message.answer(text='Список фьючерс/фьючерс', reply_markup=inline_kb1.as_markup())

    except Exception:
        logger.exception("Error in show_futures_page")
        try:
            await message.answer("Произошла ошибка при показе страницы.")
        except Exception:
            pass