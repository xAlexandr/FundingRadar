# routers/dex_page_markets.py
"""
DEX page handlers — migrated to use Go service API for data.

Go service pre-caches and pre-sorts all DEX data, making it the single
source of truth for DEX listings. Python bot only handles Telegram UI
(buttons, pagination, filter toggles).
"""
import logging
from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from libs.tgfunc import *
from libs.go_api_client import (
    get_dex_list, get_dex_pages, get_dex_id,
    api_id_to_level1_callback, api_id_to_level2_callback,
    sort_param_to_mode,
)
from copy import copy

router = Router(name=__name__)
logger = logging.getLogger("dex_page_markets")


def _get_sort_and_lt(dataSearch):
    """
    Extract sort and lt params from dataSearch for Go API.

    dataSearch can be: dict, JSON string, bytes (from orjson.dumps), or 'no'.
    Python filter_spreads_dex mapping:
      filter_course_or_spread == '1' -> sort by diff (takeCourseDex) -> Go: sort=spread
      filter_course_or_spread != '1' -> sort by funding (takeSecondDex) -> Go: sort=funding
    """
    import orjson
    sort = 'spread'
    lt = '0'

    # Parse dataSearch to dict if needed
    parsed = dataSearch
    if isinstance(parsed, (str, bytes)):
        if isinstance(parsed, bytes):
            parsed = parsed.decode('utf-8', errors='ignore')
        if parsed == 'no' or not parsed:
            return sort, lt
        try:
            parsed = orjson.loads(parsed)
        except Exception:
            try:
                parsed = json.loads(parsed)
            except Exception:
                return sort, lt
    if not isinstance(parsed, dict):
        return sort, lt

    if parsed.get('filter_course_or_spread') == '1':
        sort = 'spread'  # diff mode
    else:
        sort = 'funding'  # funding mode
    if parsed.get('filter_big_or_all_course') == '1':
        lt = '1'
    return sort, lt


def _go_items_to_telegram_buttons(items, mode='in', prev_page=0):
    """Convert Go API items [label, id] to Telegram InlineKeyboardButtons."""
    buttons = []
    for label, api_id in items:
        if api_id.startswith("dexsymbol_"):
            callback = api_id_to_level1_callback(api_id, mode, prev_page)
        elif api_id.startswith("dexid_"):
            callback = api_id_to_level2_callback(api_id, mode, prev_page)
        else:
            callback = api_id
        buttons.append(types.InlineKeyboardButton(text=label, callback_data=callback))
    return buttons


def _get_all_items(resp, page_num=None):
    """Extract all items from Go API response, optionally for a specific page."""
    if not resp or resp.get('status') != 'active':
        return []
    pages = resp.get('pages', [])
    if page_num is not None:
        for p in pages:
            if p.get('page') == page_num:
                return p.get('items', [])
        return []
    all_items = []
    for p in pages:
        all_items.extend(p.get('items', []))
    return all_items


@router.message(F.text == "DEX 🌐")
async def on_dex_text(message: types.Message):
    """
    Когда пользователь нажал KeyboardButton("DEX") — показать первую страницу DEX.
    """
    try:
        user_id = message.from_user.id
        page_start = 0
        await show_dex_page(user_id, page_start, message)
    except Exception:
        logger.exception("on_dex_text error")


@router.callback_query(F.data.startswith("dex_page_from"))
async def callbacks_dex_page(call: types.CallbackQuery):
    try:
        logger.info(f"DEX_PAGE_FROM callback={call.data}")

        parts = call.data.split(':')
        arg1 = parts[1] if len(parts) > 1 else '0'

        # По умолчанию считаем, что это страница (а не фильтр)
        is_filter = arg1 in ('spread', 'course', 'big', 'all')
        page_start = 0

        if is_filter:
            # Это фильтр — переключаем
            accounts = fetch_accounts_from_db()
            dataSearch = next((a[4] for a in accounts if str(a[2]) == str(call.from_user.id)), 'no')
            try:
                if arg1 == 'course':
                    _, dataSearch = change_to_course(accounts, dataSearch, call.from_user.id)
                elif arg1 == 'spread':
                    _, dataSearch = change_to_spread(accounts, dataSearch, call.from_user.id)
                elif arg1 == 'big':
                    _, dataSearch = change_to_big(accounts, dataSearch, call.from_user.id)
                elif arg1 == 'all':
                    _, dataSearch = change_to_all(accounts, dataSearch, call.from_user.id)
            except Exception:
                logger.exception("callbacks_dex_page: change_to_* failed")
        else:
            # Это номер страницы — НЕ СБРАСЫВАЕМ!
            try:
                page_start = int(arg1)
            except Exception:
                page_start = 0
            dataSearch = None

        # Parse dataSearch from DB if not provided by filter change
        if dataSearch is None:
            accounts = fetch_accounts_from_db()
            for acc in accounts:
                if str(acc[2]) == str(call.from_user.id):
                    dataSearch = acc[4]
                    break

        sort, lt = _get_sort_and_lt(dataSearch)

        # Call Go API instead of Python filter_spreads_dex
        resp = get_dex_list(call.from_user.id, page=1, items=500, sort=sort, lt=lt)

        if not resp:
            await call.message.answer("Сервис обновляется, подождите.")
            return

        if resp.get('status') == 'no_sub':
            await call.message.answer("Ваша подписка неактивна.")
            return

        all_items = _get_all_items(resp)
        if not all_items:
            await call.message.answer("Список DEX пуст.")
            return

        # Determine mode from sort param
        mode = sort_param_to_mode(sort)

        # Convert to Telegram buttons
        inlines_spreads = _go_items_to_telegram_buttons(all_items, mode=mode)

        inline_kb1 = create_pagination_buttons(
            inlines_spreads, InlineKeyboardBuilder(),
            type='dex_page_from', page_start=page_start
        )
        add_filter_buttons_futures_dex(inline_kb1, dataSearch)
        await call.message.edit_text(text='Список DEX-спредов', reply_markup=inline_kb1.as_markup())

    except Exception:
        logger.exception("callbacks_dex_page error")



async def show_dex_page(user_id: int, page_start: int, message: types.Message):
    """
    Показать страницу DEX (вызов из message handler).
    """
    try:
        # Get user's dataSearch from DB for sort/filter params
        dataSearch = None
        accounts = fetch_accounts_from_db()
        for acc in accounts:
            if str(acc[2]) == str(user_id):
                dataSearch = acc[4]
                break

        sort, lt = _get_sort_and_lt(dataSearch)

        # Call Go API
        resp = get_dex_list(user_id, page=1, items=500, sort=sort, lt=lt)

        inline_kb1 = InlineKeyboardBuilder()
        if resp and resp.get('status') == 'active':
            all_items = _get_all_items(resp)
            if all_items:
                mode = sort_param_to_mode(sort)
                inlines_spreads = _go_items_to_telegram_buttons(all_items, mode=mode)
                inline_kb1 = create_pagination_buttons(
                    inlines_spreads, inline_kb1, type='dex_page_from', page_start=page_start
                )
                add_filter_buttons_futures_dex(inline_kb1, dataSearch)
                await message.answer(text='Список DEX-спредов', reply_markup=inline_kb1.as_markup())
            else:
                await message.answer(text='DEX: список пуст или бот обновляется, подождите немного.')
        elif resp and resp.get('status') == 'no_sub':
            await message.answer(text='Ваша подписка неактивна.')
        else:
            await message.answer(text='DEX: сервис обновляется, подождите немного.')
    except Exception:
        logger.exception("show_dex_page error")

# handler_dex_market
@router.callback_query(F.data.startswith("dex_market:"))
async def handler_dex_market(call: types.CallbackQuery):
    try:
        parts = call.data.split(':')
        if len(parts) < 3:
            return

        mode = parts[1]
        prev_page = 0
        dataSearch = None

        accounts = fetch_accounts_from_db()
        for acc in accounts:
            if str(acc[2]) == str(call.from_user.id):
                dataSearch = acc[4]
                break
        if dataSearch is None:
            dataSearch = 'no'

        # formats:
        # dex_market:<mode>:<symbol>
        # dex_market:<mode>:<filter>:<symbol>
        # dex_market:<mode>:<symbol>:<prev_page>
        if len(parts) == 4 and parts[1] == 'in':
            mode = parts[1]
            symbol = parts[2]
            try:
                prev_page = int(parts[3])
            except Exception:
                prev_page = 0
        elif len(parts) == 4:
            if parts[2] in ('course', 'spread', 'big', 'all'):
                filter_type = parts[2]
                symbol = parts[3]
                try:
                    if filter_type == 'course':
                        _, dataSearch = change_to_course(accounts, dataSearch, call.from_user.id)
                    elif filter_type == 'spread':
                        _, dataSearch = change_to_spread(accounts, dataSearch, call.from_user.id)
                    elif filter_type == 'big':
                        _, dataSearch = change_to_big(accounts, dataSearch, call.from_user.id)
                    elif filter_type == 'all':
                        _, dataSearch = change_to_all(accounts, dataSearch, call.from_user.id)
                except Exception:
                    logger.exception("handler_dex_market: change_to_* failed")
                accounts = fetch_accounts_from_db()
                for acc in accounts:
                    if str(acc[2]) == str(call.from_user.id):
                        dataSearch = acc[4]
                        break
                prev_page = None
            else:
                symbol = parts[2]
                try:
                    prev_page = int(parts[3])
                except Exception:
                    prev_page = 0
        else:
            symbol = parts[2]
            try:
                prev_page = int(parts[4]) if len(parts) > 4 else None
            except Exception:
                prev_page = 0

        sort, lt = _get_sort_and_lt(dataSearch)

        # Call Go API for level 2 (market pairs)
        resp = get_dex_pages(call.from_user.id, symbol, items=500, sort=sort, lt=lt)

        if not resp or resp.get('status') != 'active':
            await call.message.answer(text=f"Нет записей DEX для {symbol.split('_')[1] if '_' in symbol else symbol}")
            return

        all_items = _get_all_items(resp)
        display_name = resp.get('displayName', symbol)

        # Convert to Telegram buttons
        market_buttons = _go_items_to_telegram_buttons(all_items, mode=mode, prev_page=prev_page or 0)

        inline_kb = InlineKeyboardBuilder()
        # pass main_prev into symbolFind so pagination keeps it
        inline_kb = create_pagination_buttons(
            market_buttons, inline_kb, type='dex_market_page',
            page_start=0, symbolFind=f"{mode}:{symbol}", main_prev=prev_page or 0
        )

        add_filter_buttons_futures_market_dex(inline_kb, dataSearch, symbol, mode)

        back_page = prev_page if (prev_page is not None) else 0
        inline_kb.row(types.InlineKeyboardButton(text="Назад", callback_data=f"dex_page_from:{back_page}"))

        try:
            await call.message.edit_text(
                text=f"DEX — {display_name}",
                reply_markup=inline_kb.as_markup()
            )
        except TelegramBadRequest:
            await call.message.answer(
                text=f"DEX — {display_name}",
                reply_markup=inline_kb.as_markup()
            )
    except Exception:
        logger.exception("Error in handler_dex_market")


# handler_dex_market_from
@router.callback_query(F.data.startswith("dex_market_from:"))
async def handler_dex_market_from(call: types.CallbackQuery):
    try:
        parts = call.data.split(':')
        if len(parts) < 5:
            if len(parts) == 4:
                parts.append('0')
            else:
                return
        page_raw = parts[1]
        mode = parts[2]
        symbol = parts[3]
        try:
            main_prev = int(parts[4])
        except Exception:
            main_prev = 0

        try:
            page_start = int(page_raw)
        except Exception:
            page_start = 0

        dataSearch = None
        accounts = fetch_accounts_from_db()
        for acc in accounts:
            if str(acc[2]) == str(call.from_user.id):
                dataSearch = acc[4]
                break
        if dataSearch is None:
            dataSearch = 'no'

        sort, lt = _get_sort_and_lt(dataSearch)

        # Call Go API
        resp = get_dex_pages(call.from_user.id, symbol, items=500, sort=sort, lt=lt)

        if not resp or resp.get('status') != 'active':
            await call.message.answer(text=f"Нет записей DEX для {symbol}")
            return

        all_items = _get_all_items(resp)
        display_name = resp.get('displayName', symbol)

        # Convert to Telegram buttons
        market_buttons = _go_items_to_telegram_buttons(all_items, mode=mode, prev_page=main_prev)

        inline_kb = InlineKeyboardBuilder()
        inline_kb = create_pagination_buttons(
            market_buttons, inline_kb, type='dex_market_page',
            page_start=page_start, symbolFind=f"{mode}:{symbol}", main_prev=main_prev
        )

        add_filter_buttons_futures_market_dex(inline_kb, dataSearch, symbol, mode)

        inline_kb.row(types.InlineKeyboardButton(text="Назад", callback_data=f"dex_page_from:{main_prev}"))
        await call.message.edit_text(text=f"DEX — {display_name}", reply_markup=inline_kb.as_markup())
    except Exception:
        logger.exception("Error in handler_dex_market_from")


# handler_dex_pair
@router.callback_query(F.data.startswith("dex_pair:"))
async def handler_dex_pair(call: types.CallbackQuery):
    try:
        logger.info(f"HANDLER_DEX_PAIR callback={call.data}")
        parts = call.data.split(':')
        # format: dex_pair:<mode>:<symbol>:<market2>[:<main_prev>]
        if len(parts) < 4:
            return
        mode = parts[1]
        symbol = parts[2]
        market2 = parts[3]
        main_prev = int(parts[4]) if len(parts) > 4 else 0

        # Call Go API for level 3 (pair details)
        resp = get_dex_id(call.from_user.id, symbol, market2)

        if not resp or resp.get('status') != 'ok':
            await call.message.answer(text=f"Не найдена запись DEX для {symbol.split('_')[1] if '_' in symbol else symbol} на {market2}")
            return

        dex_rec = resp.get('data', {})

        bot_tuple = (
            0,
            symbol,
            'DEX',
            market2,
            float(dex_rec.get('bid') or 0),
            float(dex_rec.get('priceUsd') or 0),
            float(dex_rec.get('diff') or 0),
            dex_rec.get('contract', ''),
            dex_rec.get('chain', ''),
            float(dex_rec.get('volume24') or 0),
            float(dex_rec.get('volume24Cex') or 0),
            dex_rec.get('url', ''),
            float(dex_rec.get('cexAsk') or 0),
            float(dex_rec.get('fundingRate') or 0)
        )
        details = create_message_to_dex(bot_tuple)

        update_btn = types.InlineKeyboardButton(
            text="Обновить",
            callback_data=f'dex_pair_update:{mode}:{symbol}:{market2}:{main_prev}'
        )
        to_graph_sym = copy(symbol)
        graph_btn = add_inline_button_graphic_dex(market2, to_graph_sym.replace('USDT', ''))
        back_btn = types.InlineKeyboardButton(text="Назад", callback_data=f'dex_market:{mode}:{symbol}:{main_prev}')

        inline_kb = InlineKeyboardBuilder()
        inline_kb.row(update_btn, graph_btn)
        inline_kb.row(back_btn)

        await call.message.answer(details, reply_markup=inline_kb.as_markup(), parse_mode='HTML', disable_web_page_preview=True)
    except Exception:
        logger.exception("Error in handler_dex_pair")


# handler_dex_pair_update
@router.callback_query(F.data.startswith("dex_pair_update:"))
async def handler_dex_pair_update(call: types.CallbackQuery):
    try:
        parts = call.data.split(':')
        if len(parts) < 4:
            return
        mode = parts[1]
        symbol = parts[2]
        market2 = parts[3]
        main_prev = int(parts[4]) if len(parts) > 4 else 0

        # Call Go API for fresh data
        resp = get_dex_id(call.from_user.id, symbol, market2)
        if not resp or resp.get('status') != 'ok':
            return

        dex_rec = resp.get('data', {})

        bot_tuple = (
            0,
            symbol,
            'DEX',
            market2,
            float(dex_rec.get('bid') or 0),
            float(dex_rec.get('priceUsd') or 0),
            float(dex_rec.get('diff') or 0),
            dex_rec.get('contract', ''),
            dex_rec.get('chain', ''),
            float(dex_rec.get('volume24') or 0),
            float(dex_rec.get('volume24Cex') or 0),
            dex_rec.get('url', ''),
            float(dex_rec.get('cexAsk') or 0),
            float(dex_rec.get('fundingRate') or 0)
        )
        details = create_message_to_dex(bot_tuple)

        update_btn = types.InlineKeyboardButton(
            text="Обновить",
            callback_data=f'dex_pair_update:{mode}:{symbol}:{market2}:{main_prev}'
        )
        to_graph_sym = copy(symbol)
        graph_btn = add_inline_button_graphic_dex(market2, to_graph_sym.replace('USDT', ''))
        back_btn = types.InlineKeyboardButton(text="Назад", callback_data=f'dex_market:{mode}:{symbol}:{main_prev}')

        inline_kb = InlineKeyboardBuilder()
        inline_kb.row(update_btn, graph_btn)
        inline_kb.row(back_btn)

        try:
            await call.message.edit_text(details, reply_markup=inline_kb.as_markup(), parse_mode='HTML', disable_web_page_preview=True)
        except Exception:
            logger.debug("dex_pair_update: edit failed (message too old?)")
    except Exception:
        logger.exception("Error in handler_dex_pair_update")



@router.callback_query(F.data.startswith("dex_graph:"))
async def handler_dex_graph(call: types.CallbackQuery):
    try:
        parts = call.data.split(':')
        if len(parts) < 3:
            await call.answer("Неправильный callback.", show_alert=True)
            return
        symbol = parts[1]
        market2 = parts[2]
        await call.answer("График пока не реализован.", show_alert=True)
    except Exception:
        logger.exception("Error in handler_dex_graph")


@router.callback_query(F.data.startswith("dex_send:"))
async def handler_dex_send(call: types.CallbackQuery):
    try:
        parts = call.data.split(':')
        if len(parts) < 3:
            await call.answer("Неправильный callback.", show_alert=True)
            return
        symbol = parts[1]
        market2 = parts[2]

        resp = get_dex_id(call.from_user.id, symbol, market2)
        if not resp or resp.get('status') != 'ok':
            await call.message.answer(text=f"Не найдена запись DEX для {symbol.split('_')[1] if '_' in symbol else symbol} на {market2}")
            return

        dex_rec = resp.get('data', {})
        text_lines = [
            f"Пара: {symbol} — DEX ↔ {market2}",
            f"DEX bid: {dex_rec.get('bid')}",
            f"priceUsd: {dex_rec.get('priceUsd')}",
            f"diff: {dex_rec.get('diff')}",
            f"cex_ask: {dex_rec.get('cexAsk')}",
            f"funding_rate: {dex_rec.get('fundingRate')}",
        ]
        if dex_rec.get('url'):
            text_lines.append(f"URL: {dex_rec.get('url')}")

        await call.message.answer("\n".join(text_lines))
        await call.answer("Отправлено в чат.")
    except Exception:
        logger.exception("Error in handler_dex_send")
