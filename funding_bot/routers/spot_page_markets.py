import logging
import os
import aiohttp
import orjson
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from libs.tgfunc import *

router = Router(name=__name__)
logger = logging.getLogger("spot_page_markets")

FILTER_HOST = os.getenv('FILTER_HOST', 'localhost')
GO_BASE = f"http://{FILTER_HOST}:8081"
ORIGIN = os.getenv('ORIGIN', '').rstrip('/')


# -----------------------
# helpers: запросы к Go
# -----------------------
async def fetch_go_spot(user_id: int, page: int = 1, items: int = 5,
                        sort: str = "spread", lt: int = 0, timeout=5):
    url = f"{GO_BASE}/api/spot"
    params = {
        "user_id": str(user_id),
        "page": str(page),
        "items": str(items),
        "sort": sort,
        "lt": str(lt),
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.json()


async def fetch_go_spot_pages(user_id: int, symbol: str, page: int = 1, items: int = 5,
                              sort: str = "spread", lt: int = 0, timeout=5):
    url = f"{GO_BASE}/api/spot_pages"
    params = {
        "user_id": str(user_id),
        "symbol": symbol,
        "page": str(page),
        "items": str(items),
        "sort": sort,
        "lt": str(lt),
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.json()


async def fetch_go_spot_id(user_id: int, m1: str, m2: str, symbol: str, timeout=5):
    url = f"{GO_BASE}/api/spot_id"
    params = {"user_id": str(user_id), "m1": m1, "m2": m2, "symbol": symbol}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.json()


# -----------------------
# helpers: обработка dataSearch
# -----------------------
def _extract_user_filters_from_accounts(accounts, user_id):
    for acc in accounts:
        if str(acc[2]) == str(user_id) and any(x == '1' for x in [acc[9], acc[10], acc[14]]):
            data_raw = acc[4] if acc[4] is not None else 'no'
            try:
                if data_raw == 'no':
                    return True, {}
                if isinstance(data_raw, (bytes, bytearray)):
                    return True, orjson.loads(data_raw)
                return True, orjson.loads(data_raw)
            except Exception:
                return True, {}
    return False, {}


def _map_dataSearch_to_service_params(dataSearch):
    sort = "spread" if dataSearch.get("filter_course_or_spread") == "1" else "funding"
    lt = 1 if dataSearch.get("filter_big_or_all_course") == "1" else 0
    return sort, lt


def build_inline_from_service_page(builder: InlineKeyboardBuilder, page_obj):
    for item in page_obj.get("items", []):
        text, ident = item[0], item[1]
        builder.row(InlineKeyboardButton(text=text, callback_data=f"spot_id:{ident}"))

def add_pagination_buttons_from_service(builder: InlineKeyboardBuilder, service_response: dict, prefix: str = "spot"):
    """
    Универсальная пагинация для spot/futures ответов.
    prefix: 'spot' -> callbacks spot_page:N
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

def add_pagination_buttons_from_service_market(builder: InlineKeyboardBuilder, requested_page0: int,
                                               total_pages: int, symbol: str):
    """
    Prev | current/total (-> first) | Next
    callbacks: spot_page_market:OFFSET:SYMBOL
    """
    current = max(0, min(requested_page0, max(0, total_pages - 1)))
    prev_offset = max(0, current - 1)
    next_offset = min(total_pages - 1, current + 1)

    prev_button = InlineKeyboardButton(text="<", callback_data=f"spot_page_market:{prev_offset}:{symbol}")
    center_button = InlineKeyboardButton(text=f"{current+1}/{total_pages}", callback_data=f"spot_page_market:0:{symbol}")
    next_button = InlineKeyboardButton(text=">", callback_data=f"spot_page_market:{next_offset}:{symbol}")
    builder.row(prev_button, center_button, next_button)


# -----------------------
# spot_id / reload
# -----------------------
@router.callback_query(F.data.startswith("spot_id:"))
async def handle_spot_id(call: types.CallbackQuery):
    await call.answer()
    try:
        _, id_string = call.data.split(":", 1)
        parts = id_string.split("_")
        if len(parts) < 4:
            await call.message.answer("Неправильный формат id.")
            return
        _, m1, m2, symbol = parts[:4]
        user_id = call.from_user.id

        resp = await fetch_go_spot_id(user_id, m1, m2, symbol)
        if resp.get("status") in ("no_sub", "inactive"):
            await call.message.answer("Нет активной подписки.")
            return
        if resp.get("status") == "empty":
            await call.message.answer("Нет данных для этой пары.")
            return

        data = resp.get("data") or {}
        msg = format_market_id_message(data, mode="spot_futures", id_string=id_string)
        kb = InlineKeyboardBuilder()
        if ORIGIN:
            chart_url = f"{ORIGIN}/trade/spot/{m1}/{m2}/{symbol.replace('USDT','')}/"
            kb.row(InlineKeyboardButton(text="Обновить", callback_data=f"spot_id_reload:{id_string}"), InlineKeyboardButton(text="График 📈", web_app=WebAppInfo(url=chart_url)))
        await call.message.answer(msg, parse_mode="HTML",
                                  reply_markup=kb.as_markup(),
                                  disable_web_page_preview=True)
    except Exception:
        logger.exception("Error in handle_spot_id")
        await call.message.answer("Ошибка при обработке запроса.")


@router.callback_query(F.data.startswith("spot_id_reload:"))
async def handle_spot_id_reload(call: types.CallbackQuery):
    await call.answer()
    try:
        _, id_string = call.data.split(":", 1)
        parts = id_string.split("_")
        if len(parts) < 4:
            await call.message.answer("Неправильный формат id.")
            return
        _, m1, m2, symbol = parts[:4]
        user_id = call.from_user.id

        resp = await fetch_go_spot_id(user_id, m1, m2, symbol)
        if resp.get("status") in ("no_sub", "inactive"):
            await call.message.answer("Нет активной подписки.")
            return
        if resp.get("status") == "empty":
            await call.message.answer("Нет данных для этой пары.")
            return

        data = resp.get("data") or {}
        msg = format_market_id_message(data, mode="spot_futures", id_string=id_string)
        kb = InlineKeyboardBuilder()
        if ORIGIN:
            chart_url = f"{ORIGIN}/trade/spot/{m1}/{m2}/{symbol.replace('USDT','')}/"
            kb.row(InlineKeyboardButton(text="Обновить", callback_data=f"spot_id_reload:{id_string}"), InlineKeyboardButton(text="График 📈", web_app=WebAppInfo(url=chart_url)))
        try:
            await call.message.edit_text(msg, parse_mode="HTML",
                                         reply_markup=kb.as_markup(),
                                         disable_web_page_preview=True)
        except TelegramBadRequest:
            pass
    except Exception:
        logger.exception("Error in handle_spot_id_reload")
        await call.message.answer("Ошибка при обновлении данных.")


@router.callback_query(F.data.startswith("spot_market"))
async def get_spot_market(call: types.CallbackQuery):
    """
    Нажали на монету: открывает первую страницу /api/spot_pages.
    """
    try:
        parts = call.data.split(":")
        if len(parts) < 2:
            await call.answer("Неверный callback.", show_alert=True)
            return
        symbolFind = parts[1]
        user_id = call.from_user.id
        accounts = fetch_accounts_from_db()
        active, dataSearch = _extract_user_filters_from_accounts(accounts, user_id)
        if not active:
            await call.answer("Ваша подписка неактивна", show_alert=True)
            return

        sort, lt = _map_dataSearch_to_service_params(dataSearch)
        resp = await fetch_go_spot_pages(user_id=user_id, symbol=symbolFind, page=1, items=5, sort=sort, lt=lt)
        if resp.get("status") in ("no_sub", "inactive"):
            await call.answer("Нет активной подписки.", show_alert=True)
            return

        pages = resp.get("pages", [])
        total_pages = int(resp.get("total_pages", len(pages) if pages else 1))
        if not pages:
            await call.message.answer("Нет данных.")
            return

        first_page = pages[0]
        kb = InlineKeyboardBuilder()
        build_inline_from_service_page(kb, first_page)
        add_pagination_buttons_from_service_market(kb, requested_page0=0, total_pages=total_pages, symbol=symbolFind)
        add_filter_buttons_spot_market(kb, dataSearch, symbolFind)
        await call.message.answer(f"Список спот/фьючерсы по {symbolFind}", reply_markup=kb.as_markup())
    except Exception:
        logger.exception("Error in get_spot_market")
        await call.message.answer("Ошибка при загрузке данных.")


@router.callback_query(F.data.startswith("spot_page_market"))
async def get_spot_pages(call: types.CallbackQuery):
    """
    Аналог page_market из фьючерсов.
    Обрабатывает пагинацию и фильтры (all/big/spread/course).
    НЕ делает второй запрос к БД после change_to_* — использует snapshot accounts и данные из change_to_*.
    """
    try:
        parts = call.data.split(":")
        if len(parts) < 3:
            await call.answer("Неправильный callback.", show_alert=True)
            return

        raw_page_start, symbolFind = parts[1], parts[2]
        user_id = call.from_user.id

        # snapshot accounts и начальные dataSearch/active (используем этот snapshot везде)
        accounts = fetch_accounts_from_db()
        active, dataSearch_db = _extract_user_filters_from_accounts(accounts, user_id)

        dataSearch_from_change = None
        is_command = False

        # обработка change_to_* — эти функции могут вернуть (page_start, dataSearch)
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
        except Exception:
            logger.exception("Error processing change_to_* in spot_page_market")

        # нормализатор dataSearch (может быть bytes/str/dict)
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
                logger.exception("Failed to normalize dataSearch")
            return {}

        if is_command:
            # Приоритет: dataSearch из change_to_* (если валидна), иначе fallback на dataSearch из snapshot accounts
            normalized = _normalize(dataSearch_from_change)
            dataSearch = normalized or (dataSearch_db or {})
            page_offset = 0
            service_page = 1
        else:
            # навигация — raw_page_start это 0-based offset
            try:
                page_offset = int(raw_page_start)
            except Exception:
                page_offset = 0
            service_page = max(1, page_offset + 1)
            # используем dataSearch из snapshot accounts
            dataSearch = dataSearch_db or {}

        # проверка подписки
        if not active:
            await call.message.answer("Ваша подписка неактивна.")
            return

        # гарантируем dict
        if not isinstance(dataSearch, dict):
            dataSearch = _normalize(dataSearch) or {}

        # map params -> sort, lt
        sort, lt = _map_dataSearch_to_service_params(dataSearch)

        # запрос к Go (pages для конкретной монеты)
        try:
            resp = await fetch_go_spot_pages(user_id, symbolFind, page=service_page, items=5, sort=sort, lt=lt)
        except Exception as e:
            logger.exception("fetch_go_spot_pages error: %s", e)
            await call.message.answer(text='Ошибка получения данных от сервиса. Повторите позже.')
            return

        if resp.get("status") in ("no_sub", "inactive"):
            await call.message.answer("Нет активной подписки.")
            return

        pages = resp.get("pages", [])
        total_pages = int(resp.get("total_pages", len(pages) or 1))

        page_obj = next((p for p in pages if int(p.get("page", 0)) == service_page),
                        pages[0] if pages else None)
        if not page_obj:
            await call.message.edit_text("Нет данных на этой странице.")
            return

        kb = InlineKeyboardBuilder()
        build_inline_from_service_page(kb, page_obj)
        add_pagination_buttons_from_service_market(kb, requested_page0=page_offset, total_pages=total_pages, symbol=symbolFind)
        add_filter_buttons_spot_market(kb, dataSearch, symbolFind)
        try:
            await call.message.edit_text(f"Список спот/фьючерсы по {symbolFind}", reply_markup=kb.as_markup())
        except TelegramBadRequest:
            pass

    except Exception:
        logger.exception("Error in get_spot_pages")
        await call.message.answer("Ошибка при загрузке данных.")


@router.callback_query(F.data.startswith("spot_page:"))
async def handle_spot_page(call: types.CallbackQuery):
    """
    Общая пагинация spot_page:N
    Поддерживает команды переключения режимов: spot_page:all, spot_page:big, spot_page:spread, spot_page:course
    (использует change_to_* и НЕ делает лишнего повторного запроса accounts).
    """
   # await call.answer()
    try:
        parts = call.data.split(":")
        page_str = parts[1] if len(parts) > 1 else "1"
        user_id = call.from_user.id

        # начальный снимок accounts + проверка подписки (используем для change_to_* и dataSearch)
        accounts = fetch_accounts_from_db()
        active, dataSearch = _extract_user_filters_from_accounts(accounts, user_id)
        if not active:
            await call.message.answer("Ваша подписка неактивна.")
            return

        # обработка команд change_to_*
        dataSearch_from_change = None
        is_command = False
        try:
            if page_str == 'all':
                is_command = True
                _, dataSearch_from_change = change_to_big(accounts, None, user_id)
            elif page_str == 'big':
                is_command = True
                _, dataSearch_from_change = change_to_all(accounts, None, user_id)
            elif page_str == 'spread':
                is_command = True
                _, dataSearch_from_change = change_to_spread(accounts, None, user_id)
            elif page_str == 'course':
                is_command = True
                _, dataSearch_from_change = change_to_course(accounts, None, user_id)
        except Exception:
            logger.exception("Error processing change_to_* in handle_spot_page")

        # нормализатор dataSearch (может быть str/bytes/dict)
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
                logger.exception("Failed to normalize dataSearch")
            return {}

        if is_command:
            # change_to_* вернул dataSearch (сериализованный) — используем его, иначе — текущий из БД (dataSearch)
            normalized = _normalize(dataSearch_from_change)
            dataSearch = normalized or (dataSearch or {})
            req_page = 1
        else:
            # навигация по номеру страницы (в callback передаём 1-based page)
            try:
                req_page = max(1, int(page_str))
            except Exception:
                req_page = 1

        # маппинг параметров сортировки/lt
        sort, lt = _map_dataSearch_to_service_params(dataSearch)

        # запрос к Go (API ожидает 1-based page)
        try:
            resp = await fetch_go_spot(user_id, page=req_page, items=5, sort=sort, lt=lt)
        except Exception as e:
            logger.exception("fetch_go_spot error in handle_spot_page: %s", e)
            await call.message.answer("Ошибка получения данных от сервиса. Повторите позже.")
            return

        if not isinstance(resp, dict):
            await call.message.answer("Ответ сервиса в неверном формате.")
            return

        if resp.get("status") in ("no_sub", "inactive"):
            await call.message.answer("Нет активной подписки.")
            return

        pages = resp.get("pages", [])
        if not pages:
            await call.message.answer("Нет данных.")
            return

        total_pages = int(resp.get("total_pages", len(pages) if pages else 1))

        # Найдём объект страницы (1-based) — поведение как у фьючерсов
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
            await call.message.edit_text("Нет данных на этой странице.")
            return

        # построение клавиатуры — как у тебя было
        kb = InlineKeyboardBuilder()
        for itm in page_obj.get("items", []):
            text = itm[0]
            symbol = itm[1]
            kb.row(InlineKeyboardButton(text=text, callback_data=f"spot_market:{symbol}"))

        # пагинация и фильтры — используем текущий resp + dataSearch
        add_pagination_buttons_from_service(kb, resp, prefix="spot")
        add_filter_buttons_spot(kb, dataSearch)

        try:
            await call.message.edit_text("Список спот/фьючерсы", reply_markup=kb.as_markup())
        except TelegramBadRequest:
            # иногда нельзя редактировать старое мессаge — молча пропускаем
            pass

    except Exception:
        logger.exception("Error in handle_spot_page")


# -----------------------
# вспомогательные вызовы для CryptoTGbot
# -----------------------
async def get_spot_markets_callback(user_id: int, symbolFind: str, message: types.Message):
    try:
        accounts = fetch_accounts_from_db()
        active, dataSearch = _extract_user_filters_from_accounts(accounts, user_id)
        if not active:
            await message.answer("Ваша подписка неактивна.")
            return

        sort, lt = _map_dataSearch_to_service_params(dataSearch)
        resp = await fetch_go_spot_pages(user_id, symbolFind, page=1, items=5, sort=sort, lt=lt)
        if resp.get("status") in ("no_sub", "inactive"):
            await message.answer("Нет активной подписки.")
            return
        if resp.get("status") == "empty":
            await message.answer("Нет данных для этой монеты.")
            return

        pages = resp.get("pages", [])
        if not pages:
            await message.answer("Нет данных.")
            return

        total_pages = int(resp.get("total_pages", len(pages)))
        kb = InlineKeyboardBuilder()
        build_inline_from_service_page(kb, pages[0])
        add_pagination_buttons_from_service_market(kb, 0, total_pages, symbolFind)
        add_filter_buttons_spot_market(kb, dataSearch, symbolFind)
        await message.answer(f"Список спот/фьючерсы по {symbolFind}", reply_markup=kb.as_markup())
    except Exception:
        logger.exception("Error in get_spot_markets_callback")
        await message.answer("Ошибка при поиске монеты.")


async def show_spot_page(user_id: int, page_start: int, message: types.Message):
    """
    Показать страницу общего списка спот/фьючерсов.
    page_start — 0-based (как у FSM), сервис ожидает 1-based.
    """
    try:
        # Получаем аккаунты, проверяем подписку
        accounts = fetch_accounts_from_db()
        active, dataSearch = _extract_user_filters_from_accounts(accounts, user_id)
        if not active:
            await message.answer("Ваша подписка неактивна.")
            return

        # Map dataSearch -> sort, lt
        sort, lt = _map_dataSearch_to_service_params(dataSearch)
        req_page = max(1, int(page_start) + 1)

        # Запрос к Go
        try:
            resp = await fetch_go_spot(user_id, page=req_page, items=5, sort=sort, lt=lt)
        except Exception as e:
            logger.exception("fetch_go_spot error: %s", e)
            await message.answer("Ошибка получения данных от сервиса. Повторите позже.")
            return

        if not isinstance(resp, dict):
            await message.answer("Ответ сервиса в неверном формате.")
            return

        if resp.get("status") in ("no_sub", "inactive"):
            await message.answer("Ваша подписка неактивна.")
            return

        pages = resp.get("pages", [])
        total_pages = int(resp.get("total_pages", len(pages) if pages else 1))

        # Найдём объект страницы (1-based) так же как для фьючерсов
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

        # Строим клавиатуру
        kb = InlineKeyboardBuilder()
        build_inline_from_service_page(kb, page_obj)
        add_pagination_buttons_from_service(kb, resp, prefix="spot")
        try:
            add_filter_buttons_spot(kb, dataSearch)
        except Exception:
            pass  # оставляем как есть

        await message.answer("Список спот/фьючерсы", reply_markup=kb.as_markup())

    except Exception:
        logger.exception("Error in show_spot_page")
        await message.answer("Ошибка при показе страницы.")
