import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

import pytest
import json
import re
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import CryptoTGbot
from CryptoTGbot import list_markets, marketlist_call
import libs.tgfunc as tgfunc

# ---------- Фикстуры ----------
@pytest.fixture
def mock_message():
    """Создаёт мок объекта Message."""
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock()
    msg.from_user.id = 123456
    msg.text = "Биржи ⚙️"
    msg.answer = AsyncMock()
    return msg


@pytest.fixture
def mock_db_connection():
    """Мокает mysql.connector.connect и возвращает курсор."""
    with patch('mysql.connector.connect') as mock_connect:
        mock_cursor = MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        yield mock_cursor


@pytest.fixture
def sample_user_data():
    """Возвращает тестовые данные пользователя, используя список бирж из CryptoTGbot."""
    # Извлекаем marketsliststart из CryptoTGbot.py
    cryptotg_path = ROOT / "CryptoTGbot.py"
    content = cryptotg_path.read_text(encoding='utf-8')
    match = re.search(r'marketsliststart\s*=\s*json\.dumps\((\[.*?\])\)', content, re.DOTALL)
    if not match:
        raise ValueError("Не найдено marketsliststart в CryptoTGbot.py")
    list_str = match.group(1)
    items = re.findall(r"'([^']+)'", list_str)
    # items уже содержит строки вида 'Bybit_1', 'Mexc_1' и т.д.
    # Преобразуем в JSON-строку для хранения в БД
    marketslist = json.dumps(items)
    marketslistfutures = marketslist
    marketslistspot = marketslist
    return (123456, 'test_user', 123456, 0, 'no', marketslistfutures, marketslistspot, b'no', b'no',
            0, 2, 'no', 'no', 'no', 0, 'no', b'no', 'memo123')

# ---------- Тесты ----------
@pytest.mark.asyncio
async def test_list_markets(mock_message, mock_db_connection, sample_user_data):
    """
    Тестирует формирование клавиатуры со списком бирж.
    Проверяет, что для каждой биржи из данных пользователя создаётся строка с двумя кнопками,
    и текст соответствует статусу (включена/выключена).
    """
    # Настраиваем мок курсора
    mock_db_connection.execute = MagicMock()
    mock_db_connection.fetchall.return_value = [sample_user_data]

    # Извлекаем список бирж из данных пользователя (фьючерсный список)
    futures_list = json.loads(sample_user_data[5])
    expected_status = {}
    for item in futures_list:
        name, status = item.split('_')
        expected_status[name.lower()] = status  # '1' или '0'

    # Создаём реальные кнопки для всех бирж из списка в глобальной области CryptoTGbot
    for name in expected_status.keys():
        setattr(CryptoTGbot, f'button_futures_{name}',
                InlineKeyboardButton(text=f'{name.capitalize()} ✅', callback_data=f'marketlist_futures_{name}'))
        setattr(CryptoTGbot, f'button_spot_{name}',
                InlineKeyboardButton(text=f'{name.capitalize()} ✅', callback_data=f'marketlist_spot_{name}'))
        setattr(CryptoTGbot, f'button_futures_{name}_off',
                InlineKeyboardButton(text=f'{name.capitalize()}', callback_data=f'marketlist_futures_{name}_off'))
        setattr(CryptoTGbot, f'button_spot_{name}_off',
                InlineKeyboardButton(text=f'{name.capitalize()}', callback_data=f'marketlist_spot_{name}_off'))

    # Вызываем функцию
    await list_markets(mock_message)

    # Проверяем, что message.answer вызван с правильными параметрами
    mock_message.answer.assert_called_once()
    args, kwargs = mock_message.answer.call_args
    assert kwargs.get('text') == 'Список бирж (фьючерсы | спот)'
    reply_markup = kwargs.get('reply_markup')
    assert isinstance(reply_markup, InlineKeyboardMarkup)

    keyboard = reply_markup.inline_keyboard
    assert len(keyboard) == len(expected_status)

    for row in keyboard:
        assert len(row) == 2
        fut_btn, spot_btn = row

        name_candidate = fut_btn.text.replace(' ✅', '')
        assert name_candidate.lower() in expected_status

        if expected_status[name_candidate.lower()] == '1':
            assert '✅' in fut_btn.text
            assert '✅' in spot_btn.text
            assert fut_btn.callback_data == f'marketlist_futures_{name_candidate.lower()}'
            assert spot_btn.callback_data == f'marketlist_spot_{name_candidate.lower()}'
        else:
            assert '✅' not in fut_btn.text
            assert '✅' not in spot_btn.text
            assert fut_btn.callback_data == f'marketlist_futures_{name_candidate.lower()}_off'
            assert spot_btn.callback_data == f'marketlist_spot_{name_candidate.lower()}_off'


def test_base_markets_consistency():
    """
    Проверяет, что список бирж, захардкоженный в CryptoTGbot (в переменной marketsliststart),
    совпадает со списком base_markets из файла add_market_to_db.py (на уровень выше).
    """
    # 1. Извлекаем marketsliststart из CryptoTGbot.py
    cryptotg_path = ROOT / "CryptoTGbot.py"
    assert cryptotg_path.exists(), f"Файл {cryptotg_path} не найден"
    content = cryptotg_path.read_text(encoding='utf-8')
    match = re.search(r'marketsliststart\s*=\s*json\.dumps\((\[.*?\])\)', content, re.DOTALL)
    assert match, "Не найдено определение marketsliststart в CryptoTGbot.py"
    list_str = match.group(1)
    items = re.findall(r"'([^']+)'", list_str)
    cryptobot_names = set()
    for item in items:
        if item.endswith('_1'):
            cryptobot_names.add(item[:-2])
        else:
            cryptobot_names.add(item)

    # 2. Извлекаем base_markets из add_market_to_db.py
    add_market_path = ROOT / "add_market_to_db.py"
    assert add_market_path.exists(), f"Файл {add_market_path} не найден"
    content_db = add_market_path.read_text(encoding='utf-8')
    match_db = re.search(r'base_markets\s*=\s*\[([^\]]+)\]', content_db, re.DOTALL)
    assert match_db, "Не найдено определение base_markets в add_market_to_db.py"
    list_str_db = match_db.group(1)
    items_db = re.findall(r"'([^']+)'", list_str_db)
    db_names = set()
    for item in items_db:
        if item.endswith('_1'):
            db_names.add(item[:-2])
        else:
            db_names.add(item)

    # 3. Сравниваем наборы (исключая DEX)
    cryptobot_normal = {name for name in cryptobot_names if name.upper() != 'DEX'}
    db_normal = {name for name in db_names if name.upper() != 'DEX'}

    missing_in_db = cryptobot_normal - db_normal
    missing_in_bot = db_normal - cryptobot_normal

    assert not missing_in_db, f"Биржи из CryptoTGbot отсутствуют в base_markets: {missing_in_db}"
    assert not missing_in_bot, f"Биржи из base_markets отсутствуют в CryptoTGbot: {missing_in_bot}"


def test_buttons_exist_for_all_markets():
    """
    Проверяет, что для каждой биржи из marketsliststart в модуле tgfunc
    определены кнопки (futures, spot, on/off).
    """
    # Извлекаем список бирж из CryptoTGbot
    cryptotg_path = ROOT / "CryptoTGbot.py"
    content = cryptotg_path.read_text(encoding='utf-8')
    match = re.search(r'marketsliststart\s*=\s*json\.dumps\((\[.*?\])\)', content, re.DOTALL)
    assert match, "Не найдено marketsliststart в CryptoTGbot.py"
    list_str = match.group(1)
    items = re.findall(r"'([^']+)'", list_str)
    # Извлекаем имена бирж без суффикса _1 (и без DEX)
    market_names = set()
    for item in items:
        if item.endswith('_1'):
            name = item[:-2]
        else:
            name = item
        # Пропускаем DEX, так как для него могут быть особые кнопки
        if name.upper() != 'DEX' and name.upper() != 'BINANCEALPHA':
            market_names.add(name)

    # Проверяем для каждого имени
    for name in market_names:
        # Нормализуем имя для использования в именах переменных (lowercase)
        var_name = name.lower()
        # Проверяем futures on
        fut_on = getattr(tgfunc, f'button_futures_{var_name}', None)
        assert fut_on is not None, f"Отсутствует button_futures_{var_name} в tgfunc"
        assert isinstance(fut_on, InlineKeyboardButton), f"button_futures_{var_name} не является InlineKeyboardButton"
        assert fut_on.text == f'{name} ✅', f"Некорректный текст для button_futures_{var_name}: {fut_on.text}"
        assert fut_on.callback_data == f'marketlist_futures_{var_name}', f"Некорректный callback для button_futures_{var_name}"

        # Проверяем futures off
        fut_off = getattr(tgfunc, f'button_futures_{var_name}_off', None)
        assert fut_off is not None, f"Отсутствует button_futures_{var_name}_off в tgfunc"
        assert isinstance(fut_off, InlineKeyboardButton), f"button_futures_{var_name}_off не является InlineKeyboardButton"
        assert fut_off.text == f'{name}', f"Некорректный текст для button_futures_{var_name}_off: {fut_off.text}"
        assert fut_off.callback_data == f'marketlist_futures_{var_name}_off', f"Некорректный callback для button_futures_{var_name}_off"

        # Проверяем spot on
        spot_on = getattr(tgfunc, f'button_spot_{var_name}', None)
        assert spot_on is not None, f"Отсутствует button_spot_{var_name} в tgfunc"
        assert isinstance(spot_on, InlineKeyboardButton), f"button_spot_{var_name} не является InlineKeyboardButton"
        # Для спота может быть мусорный символ 🗑, поэтому проверяем только наличие имени и callback
        assert name in spot_on.text, f"Некорректный текст для button_spot_{var_name}: {spot_on.text}"
        assert spot_on.callback_data == f'marketlist_spot_{var_name}', f"Некорректный callback для button_spot_{var_name}"

        # Проверяем spot off
        spot_off = getattr(tgfunc, f'button_spot_{var_name}_off', None)
        assert spot_off is not None, f"Отсутствует button_spot_{var_name}_off в tgfunc"
        assert isinstance(spot_off, InlineKeyboardButton), f"button_spot_{var_name}_off не является InlineKeyboardButton"
        assert name in spot_off.text, f"Некорректный текст для button_spot_{var_name}_off: {spot_off.text}"
        assert spot_off.callback_data == f'marketlist_spot_{var_name}_off', f"Некорректный callback для button_spot_{var_name}_off"

def test_special_markets_handling_in_marketlist_call():
    """
    Проверяет, что для всех бирж с нестандартным написанием (где текст кнопки _off
    отличается от market.capitalize()) в marketlist_call есть обработка во всех 4 блоках
    (futures on, spot on, futures off, spot off).
    """
    # 1. Собираем особые биржи из tgfunc
    special_markets = {}
    for attr_name in dir(tgfunc):
        if attr_name.startswith('button_futures_') and attr_name.endswith('_off'):
            var_name = attr_name[len('button_futures_'):-len('_off')]
            if var_name == 'dex':
                continue
            button = getattr(tgfunc, attr_name)
            if not isinstance(button, InlineKeyboardButton):
                continue
            button_text = button.text.strip()
            # Убираем '🗑' и пробелы
            button_text = re.sub(r'[🗑\s]', '', button_text)
            if button_text != var_name.capitalize():
                special_markets[var_name] = button_text

    if not special_markets:
        return  # нет особых бирж

    # 2. Читаем CryptoTGbot.py и ищем тело функции marketlist_call
    cryptotg_path = ROOT / "CryptoTGbot.py"
    content = cryptotg_path.read_text(encoding='utf-8')
    func_match = re.search(r'async def marketlist_call\(.*?\):(.*?)(?=\n\s*async def|\Z)', content, re.DOTALL)
    assert func_match, "Не найдена функция marketlist_call"
    func_body = func_match.group(1)

    # 3. Для каждой особой биржи проверяем, что условие встречается ровно 4 раза
    for var_name, correct_text in special_markets.items():
        expected_condition = var_name.capitalize()
        pattern = re.compile(rf"market\.capitalize\(\)\s*==\s*['\"]{re.escape(expected_condition)}['\"]")
        matches = pattern.findall(func_body)
        assert len(matches) == 4, \
            f"Для биржи {correct_text} (переменная {var_name}) найдено {len(matches)} условий " \
            f"'market.capitalize() == '{expected_condition}'', ожидается 4. " \
            f"Добавьте это условие во все 4 блока: futures on, spot on, futures off, spot off."


def test_create_message_to_spot_has_links_for_all_markets():
    """
    Проверяет, что в функции create_message_to_spot для каждой биржи (кроме DEX)
    есть условия для формирования ссылок как для market_1 (спот), так и для market_2 (фьючерс).
    """
    # Получаем ожидаемые имена бирж
    cryptotg_path = ROOT / "CryptoTGbot.py"
    content = cryptotg_path.read_text(encoding='utf-8')
    match = re.search(r'marketsliststart\s*=\s*json\.dumps\((\[.*?\])\)', content, re.DOTALL)
    assert match, "Не найдено marketsliststart в CryptoTGbot.py"
    list_str = match.group(1)
    items = re.findall(r"'([^']+)'", list_str)
    market_names = set()
    for item in items:
        if item.endswith('_1'):
            name = item[:-2]
        else:
            name = item
        if name.upper() != 'DEX':
            market_names.add(name)

    # Читаем tgfunc.py
    tgfunc_path = ROOT / "libs" / "tgfunc.py"
    assert tgfunc_path.exists(), f"Файл {tgfunc_path} не найден"
    tg_content = tgfunc_path.read_text(encoding='utf-8')

    # Ищем функцию create_message_to_spot
    func_match = re.search(r'def create_message_to_spot\(.*?\):(.*?)(?=\n\s*def |\Z)', tg_content, re.DOTALL)
    assert func_match, "Не найдена функция create_message_to_spot"
    func_body = func_match.group(1)

    # Собираем условия для bot_message[2] (market_1)
    market1_conditions = set(re.findall(r"(?:if|elif)\s+bot_message\[2\]\s*==\s*['\"]([^'\"]+)['\"]", func_body))
    # Собираем условия для bot_message[3] (market_2)
    market2_conditions = set(re.findall(r"(?:if|elif)\s+bot_message\[3\]\s*==\s*['\"]([^'\"]+)['\"]", func_body))

    missing_in_market1 = market_names - market1_conditions
    missing_in_market2 = market_names - market2_conditions

    assert not missing_in_market1, f"В create_message_to_spot для market_1 (спот) отсутствуют условия для бирж: {missing_in_market1}"
    assert not missing_in_market2, f"В create_message_to_spot для market_2 (фьючерс) отсутствуют условия для бирж: {missing_in_market2}"


def test_create_message_to_futures_has_links_for_all_markets():
    """
    Проверяет, что в функции create_message_to_futures для каждой биржи (кроме DEX)
    есть условия для формирования ссылок как для первого, так и для второго рынка (оба фьючерсные).
    """
    # Получаем ожидаемые имена бирж
    cryptotg_path = ROOT / "CryptoTGbot.py"
    content = cryptotg_path.read_text(encoding='utf-8')
    match = re.search(r'marketsliststart\s*=\s*json\.dumps\((\[.*?\])\)', content, re.DOTALL)
    assert match, "Не найдено marketsliststart в CryptoTGbot.py"
    list_str = match.group(1)
    items = re.findall(r"'([^']+)'", list_str)
    market_names = set()
    for item in items:
        if item.endswith('_1'):
            name = item[:-2]
        else:
            name = item
        if name.upper() != 'DEX' and name.upper() != 'BINANCEALPHA':
            market_names.add(name)

    # Читаем tgfunc.py
    tgfunc_path = ROOT / "libs" / "tgfunc.py"
    assert tgfunc_path.exists(), f"Файл {tgfunc_path} не найден"
    tg_content = tgfunc_path.read_text(encoding='utf-8')

    # Ищем функцию create_message_to_futures
    func_match = re.search(r'def create_message_to_futures\(.*?\):(.*?)(?=\n\s*def |\Z)', tg_content, re.DOTALL)
    assert func_match, "Не найдена функция create_message_to_futures"
    func_body = func_match.group(1)

    # Собираем условия для bot_message[3] (первый рынок)
    market1_conditions = set(re.findall(r"(?:if|elif)\s+bot_message\[3\]\s*==\s*['\"]([^'\"]+)['\"]", func_body))
    # Собираем условия для bot_message[2] (второй рынок)
    market2_conditions = set(re.findall(r"(?:if|elif)\s+bot_message\[2\]\s*==\s*['\"]([^'\"]+)['\"]", func_body))

    missing_in_market1 = market_names - market1_conditions
    missing_in_market2 = market_names - market2_conditions

    assert not missing_in_market1, f"В create_message_to_futures для первого рынка отсутствуют условия для бирж: {missing_in_market1}"
    assert not missing_in_market2, f"В create_message_to_futures для второго рынка отсутствуют условия для бирж: {missing_in_market2}"


def test_create_message_to_dex_has_links_for_all_markets():
    """
    Проверяет, что:

    1. В make_cex_link есть ссылки для всех бирж,
       кроме XT.

    2. create_message_to_dex использует url для DEX.

    3. Есть ссылка на dexscreener.
    """

    # ---------- список бирж ----------
    cryptotg_path = ROOT / "CryptoTGbot.py"
    content = cryptotg_path.read_text(encoding="utf-8")

    match = re.search(
        r"marketsliststart\s*=\s*json\.dumps\((\[.*?\])\)",
        content,
        re.DOTALL,
    )
    assert match

    items = re.findall(r"'([^']+)'", match.group(1))

    market_names = {
        item[:-2] if item.endswith("_1") else item
        for item in items
        if (item[:-2] if item.endswith("_1") else item).upper() != "DEX"
    }

    # ---------- читаем tgfunc ----------
    tgfunc_path = ROOT / "libs" / "tgfunc.py"
    tg_content = tgfunc_path.read_text(encoding="utf-8")

    # ---------- ищем именно make_cex_link ----------
    make_link = re.search(
        r"def make_cex_link\(market,\s*pair\):(.*?)(?=\n\s*# Ссылки/названия)",
        tg_content,
        re.DOTALL,
    )

    assert make_link, "Не найдена функция make_cex_link"

    make_link_body = make_link.group(1)

    found_markets = set(
        re.findall(
            r"(?:if|elif)\s+market\s*==\s*['\"]([^'\"]+)['\"]",
            make_link_body,
        )
    )

    missing = market_names - found_markets

    assert not missing, (
        "В make_cex_link отсутствуют ссылки для бирж: "
        f"{sorted(missing)}"
    )

    # ---------- проверяем DEX ----------
    assert '<a href="{url}">{dex_market}</a>' in tg_content, \
        "Не используется ссылка url для DEX."

    assert '<a href="{url}">dexscreener</a>' in tg_content, \
        "Отсутствует ссылка на dexscreener."