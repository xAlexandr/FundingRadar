import hashlib
import hmac
import datetime
import asyncio
import pickle
import time
import threading
import select
import os
from django.shortcuts import render
import json
from django.http import HttpResponse, JsonResponse
import sys
import socket
import logging
import mysql.connector
sys.path.append("..")
from gunicorn.http.errors import InvalidHTTPVersion
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.views import TokenViewBase
from rest_framework_simplejwt.tokens import OutstandingToken
from django.utils import timezone
from .models import User, UserLoginRecord, DeviceRecord, SubscriptionSetting
from .serializers import (
    TelegramTokenObtainSerializer
)
import redis
import zlib
import requests
import re
import base64
import binascii
import json
from urllib.parse import parse_qs, quote_plus, unquote_plus, urlparse, urlunparse
from datetime import timedelta

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))

IS_DEBUG = os.getenv('DEBUG', 'False') == 'True'

MYSQL_ROOT_PASSWORD = os.getenv('MYSQL_ROOT_PASSWORD', '')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'funding')
MYSQL_USER = os.getenv('MYSQL_USER', 'username')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'password')
DB_HOST = os.getenv('DB_HOST', 'mysql')
DB_PORT = os.getenv('DB_PORT', '3306')

FILTER_HOST = os.getenv('FILTER_HOST', 'localhost')

history_futures = {}
history_spot = {}
runUpdatePickle = False
coins_list_full = {}

with open('rating_coins_full.pickle', 'rb') as f:
    if f != None:
        data_coins = pickle.load(f)

counter = 0
coin_cap = []
for i in data_coins[0]:
    counter += 1
    coin_cap.append([counter, i['symbol']])


def update_coins_list_full():
    global coins_list_full
    while True:
        print('Updating coins list full...')
        with open("./trading/all_coins.pickle", "rb") as file:
            coins_list_full = pickle.load(file)
        print('Coins list updated!')
        time.sleep(180)


def get_referrals_from_db(telegram_id):
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor(dictionary=True)  # dictionary=True, чтобы получить данные в виде словаря

        query = "SELECT username, tgid, isActiveAdmin, testActive, timeTest FROM Users WHERE referral = %s"
        cursor.execute(query, (telegram_id,))
        user_data = cursor.fetchall()

        cursor.close()
        connection.close()

        return user_data

    except mysql.connector.Error as err:
        print(f"Ошибка подключения к MySQL: {err}")
        return None

def fetch_spreads_accounts_from_db():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE
    )
    cursor = connection.cursor()

    raw = r.get("Spreads:all")
    if not raw:
        return []

    spreads_data = json.loads(raw)
    spreads = []

    for data in spreads_data:
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
            )
            spreads.append(spread)
        except Exception as e:
            print("Error in record, skipping:", e)

    cursor.execute('SELECT * FROM Users')
    accounts = cursor.fetchall()
    connection.close()
    return spreads, accounts


# GET FUTURES
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_futures(request):
    user = request.user

    sorting = request.GET.get("sort", "spread")
    sorting_lt = request.GET.get("lt", "0")

    is_active_sub = False
    if user.test_active or user.subscribe_active:
        is_active_sub = True
    if is_active_sub and user.telegram_id:
        try:
            resp = requests.get(f"http://{FILTER_HOST}:8081/api/futures", params={"user_id": user.telegram_id, "page": request.GET.get("page", "1"), "items": request.GET.get("items", "7"), "sort": sorting, "lt": sorting_lt})
            return JsonResponse(resp.json())
        except Exception:
            return JsonResponse({"status": "empty"})
    else:
        response_data = {
            "status": "no_sub",
        }
        return JsonResponse(response_data)


def fetch_spot_spreads_accounts_from_db():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=1, decode_responses=True)
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE
    )
    cursor = connection.cursor()

    raw = r.get("SpotFutures:all")
    if not raw:
        return []

    spreads_data = json.loads(raw)
    spreads = []

    for data in spreads_data:
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
            )
            spreads.append(spread)
        except Exception as e:
            print("Error in record, skipping:", e)

    cursor.execute('SELECT * FROM Users')
    accounts = cursor.fetchall()
    connection.close()
    return spreads, accounts


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_spot(request):
    user = request.user
    sorting = request.GET.get("sort", "spread")
    sorting_lt = request.GET.get("lt", "0")

    is_active_sub = False
    if user.test_active or user.subscribe_active:
        is_active_sub = True

    if is_active_sub and user.telegram_id:
        try:
            resp = requests.get(f"http://{FILTER_HOST}:8081/api/spot",
                                params={"user_id": user.telegram_id, "page": request.GET.get("page", "1"),
                                        "items": request.GET.get("items", "7"), "sort": sorting, "lt": sorting_lt})
            return JsonResponse(resp.json())
        except Exception:
            return JsonResponse({"status": "empty"})
    else:
        response_data = {
            "status": "no_sub",
        }
        return JsonResponse(response_data)
# --------------


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_futures_pages(request):
    user = request.user
    sorting = request.GET.get("sort", "spread")
    sorting_lt = request.GET.get("lt", "0")

    if not (user.test_active or user.subscribe_active):
        return JsonResponse({"status": "no_sub"})
    try:
        try:
            resp = requests.get(f"http://{FILTER_HOST}:8081/api/futures_pages",
                                params={"user_id": user.telegram_id, "symbol": request.GET.get("symbol", "ETHUSDT"),
                                        "items": request.GET.get("items", "7"), "sort": sorting, "lt": sorting_lt})
            return JsonResponse(resp.json())
        except Exception:
            return JsonResponse({"status": "empty"})
    except Exception as e:
        print('Ошибка в get_markets:', e)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_spot_pages(request):
    user = request.user
    sorting = request.GET.get("sort", "spread")
    sorting_lt = request.GET.get("lt", "0")

    if not (user.test_active or user.subscribe_active):
        return JsonResponse({"status": "no_sub"})

    try:
        try:
            resp = requests.get(f"http://{FILTER_HOST}:8081/api/spot_pages",
                                params={"user_id": user.telegram_id, "symbol": request.GET.get("symbol", "ETHUSDT"),
                                        "items": request.GET.get("items", "7"), "sort": sorting, "lt": sorting_lt})
            return JsonResponse(resp.json())
        except Exception:
            return JsonResponse({"status": "empty"})
    except Exception as e:
        print('Ошибка в get_markets:', e)


def get_spread_by_symbol_and_markets(symbol, market1, market2):
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    raw = r.get("Spreads:all")
    if not raw:
        return None

    try:
        all_spreads = json.loads(raw)
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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_futures_id(request):
    global coin_cap
    user = request.user
    find_symbol = request.GET.get("symbol", "ETH")
    find_m1 = request.GET.get("m1", "Bybit")
    find_m2 = request.GET.get("m2", "Bitget")

    if not (user.test_active or user.subscribe_active):
        return JsonResponse({"status": "no_sub"})
    try:
        resp = requests.get(f"http://{FILTER_HOST}:8081/api/futures_id",
                            params={"user_id": user.telegram_id, "symbol": find_symbol,
                                    "m1": find_m1, "m2": find_m2})
        return JsonResponse(resp.json())
    except Exception:
        return JsonResponse({"status": "empty"})


def get_spot_spread_by_symbol_and_markets(symbol, market1, market2):
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=1, decode_responses=True)
    raw = r.get("SpotFutures:all")
    if not raw:
        return None

    try:
        all_spreads = json.loads(raw)
    except Exception as e:
        print("Ошибка при загрузке JSON:", e)
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

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_spot_id(request):
    global coin_cap
    user = request.user
    find_symbol = request.GET.get("symbol", "ETH")
    find_m1 = request.GET.get("m1", "Bybit")
    find_m2 = request.GET.get("m2", "Bitget")

    if not (user.test_active or user.subscribe_active):
        return JsonResponse({"status": "no_sub"})
    try:
        resp = requests.get(f"http://{FILTER_HOST}:8081/api/spot_id",
                            params={"user_id": user.telegram_id, "symbol": find_symbol,
                                    "m1": find_m1, "m2": find_m2})
        return JsonResponse(resp.json())
    except Exception:
        return JsonResponse({"status": "empty"})

# ---------- DEX API PROXY --------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_dex(request):
    user = request.user
    sorting = request.GET.get("sort", "spread")
    sorting_lt = request.GET.get("lt", "0")
    if not (user.test_active or user.subscribe_active):
        return JsonResponse({"status": "no_sub"})
    try:
        resp = requests.get(f"http://{FILTER_HOST}:8081/api/dex",
                            params={"user_id": user.telegram_id, "page": request.GET.get("page", "1"),
                                    "items": request.GET.get("items", "7"), "sort": sorting, "lt": sorting_lt})
        return JsonResponse(resp.json())
    except Exception:
        return JsonResponse({"status": "empty"})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_dex_pages(request):
    user = request.user
    sorting = request.GET.get("sort", "spread")
    sorting_lt = request.GET.get("lt", "0")
    if not (user.test_active or user.subscribe_active):
        return JsonResponse({"status": "no_sub"})
    try:
        resp = requests.get(f"http://{FILTER_HOST}:8081/api/dex_pages",
                            params={"user_id": user.telegram_id, "symbol": request.GET.get("symbol", ""),
                                    "items": request.GET.get("items", "7"), "sort": sorting, "lt": sorting_lt})
        return JsonResponse(resp.json())
    except Exception:
        return JsonResponse({"status": "empty"})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_dex_id(request):
    user = request.user
    if not (user.test_active or user.subscribe_active):
        return JsonResponse({"status": "no_sub"})
    try:
        resp = requests.get(f"http://{FILTER_HOST}:8081/api/dex_id",
                            params={"user_id": user.telegram_id, "symbol": request.GET.get("symbol", ""),
                                    "market": request.GET.get("market", "")})
        return JsonResponse(resp.json())
    except Exception:
        return JsonResponse({"status": "empty"})


@api_view(['GET'])
@permission_classes([AllowAny])
def get_top_funding(request):
    try:
        resp = requests.get(f"http://{FILTER_HOST}:8081/api/top_funding", timeout=5)
        return JsonResponse(resp.json())
    except Exception:
        return JsonResponse({"status": "empty"})


@api_view(['GET'])
@permission_classes([AllowAny])
def get_top_funding_spot(request):
    try:
        resp = requests.get(f"http://{FILTER_HOST}:8081/api/top_funding_spot", timeout=5)
        return JsonResponse(resp.json())
    except Exception:
        return JsonResponse({"status": "empty"})

# ---------- ДО СЮДА НУЖНО ПЕРЕПИСАТЬ НА GO --------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_subscribe(request):
    user = request.user

    is_active_sub = False
    if user.test_active or user.subscribe_active:
        is_active_sub = True

    referrals_from_db = get_referrals_from_db(user.telegram_id)

    # Вычисляем дату окончания подписки
    test_end_date = user.test_start_date + datetime.timedelta(days=1) if user.test_start_date else None
    subscribe_end_date = user.subscribe_start_date + datetime.timedelta(days=30) if user.subscribe_start_date else None

    response_data = {
        "telegram_id": user.telegram_id,
        "is_active_sub": is_active_sub,
        "test_active": user.test_active,
        "test_start_date": user.test_start_date.isoformat() if user.test_start_date else None,
        "subscribe_active": user.subscribe_active,
        "subscribe_start_date": user.subscribe_start_date.isoformat() if user.subscribe_start_date else None,
        "test_end_date": test_end_date.isoformat() if test_end_date else None,
        "subscribe_end_date": subscribe_end_date.isoformat() if subscribe_end_date else None,
        "referrals": referrals_from_db,  # Список приглашенных пользователей
        "memo": user.memo
    }

    return JsonResponse(response_data)


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
        data_s = json.dumps(dataSearch)
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
        dataSearch = json.dumps(dataSearch)
    elif dataSearch != 'no':
        dataSearch = json.loads(dataSearch)
        dataSearch['filter_course_or_spread'] = '1'
        data_s = json.dumps(dataSearch)
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
        dataSearch = json.dumps(dataSearch)



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
        data_s = json.dumps(dataSearch)
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
        dataSearch = json.dumps(dataSearch)
    elif dataSearch != 'no':
        dataSearch = json.loads(dataSearch)
        dataSearch['filter_course_or_spread'] = '0'
        data_s = json.dumps(dataSearch)
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
        dataSearch = json.dumps(dataSearch)


def change_to_big(accounts, dataSearch, id):

    # Ищем аккаунт и берем dataSearch, если он есть
    if len(accounts) > 0:
        for acc in accounts:
            if str(acc[2]) == str(id):
                dataSearch = acc[4]
                break

    # Если данных нет
    if dataSearch == 'no' or not dataSearch:
        dataSearch = {}
        new_value = 1  # по умолчанию ставим 1
        dataSearch['filter_big_or_all_course'] = str(new_value)
        dataSearch['spread'] = 'no'
        dataSearch['course_spread'] = 'no'
    else:
        # Есть данные, превращаем из JSON в dict
        dataSearch = json.loads(dataSearch)
        # Переключатель
        current_value = dataSearch.get('filter_big_or_all_course', '1')
        new_value = 0 if current_value == '1' else 1
        dataSearch['filter_big_or_all_course'] = str(new_value)

    # Сохраняем обратно в JSON
    data_s = json.dumps(dataSearch)

    # Обновляем базу
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

    return new_value  # возвращаем 0 или 1 как число


# GET SPREAD AND BIG
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_data_settings(request):
    user = request.user

    # проверка подписки
    if not (user.test_active or user.subscribe_active):
        return JsonResponse({"status": "no_sub"})

    try:
        # подключение к MySQL
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor()

        # достаем dataSearch для текущего пользователя
        cursor.execute("SELECT dataSearch FROM Users WHERE tgid=%s", (user.telegram_id,))
        result = cursor.fetchone()

        if not result or not result[0] or result[0] == 'no':
            # если пользователя нет или dataSearch пустой
            connection.close()
            return JsonResponse({
                "status": "empty",
                "filter_course_or_spread": None,
                "filter_big_or_all_course": None
            })

        # парсим существующие настройки
        dataSearch = json.loads(result[0])

        connection.close()

        response_data = {
            "status": "ok",
            "filter_course_or_spread": dataSearch.get("filter_course_or_spread"),
            "filter_big_or_all_course": dataSearch.get("filter_big_or_all_course")
        }

        return JsonResponse(response_data)

    except Exception as e:
        print("Error get_data_settings:", e)
        return JsonResponse({"status": "error"})

# CHANGE TO SPREAD
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_change_to_spread(request):
    user = request.user

    if not (user.test_active or user.subscribe_active):
        return JsonResponse({"status": "no_sub"})

    try:
        spreads, accounts = fetch_spreads_accounts_from_db()
        change_to_spread(accounts, None, user.telegram_id)

        return JsonResponse({"status": "ok"})
    except Exception:
        pass

# CHANGE TO COURSE
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_change_to_course(request):
    user = request.user

    if not (user.test_active or user.subscribe_active):
        return JsonResponse({"status": "no_sub"})

    try:
        spreads, accounts = fetch_spreads_accounts_from_db()
        change_to_course(accounts, None, user.telegram_id)

        return JsonResponse({"status": "ok"})
    except Exception:
        pass


# CHANGE TO BIG
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_change_to_big(request):
    user = request.user

    if not (user.test_active or user.subscribe_active):
        return JsonResponse({"status": "no_sub"})

    try:
        spreads, accounts = fetch_spreads_accounts_from_db()
        result = change_to_big(accounts, None, user.telegram_id)

        return JsonResponse({"status": "ok", "result": result})
    except Exception:
        pass

runUpdateCoins = False


@api_view(['GET'])
@permission_classes([IsAuthenticated])  # Только авторизованные
def get_coins(request):
    global runUpdateCoins, coins_list_full

    if runUpdateCoins is False:
        update_coins_list_thread = threading.Thread(target=update_coins_list_full)
        update_coins_list_thread.daemon = True
        update_coins_list_thread.start()
        runUpdateCoins = True

    return HttpResponse(
        json.dumps({
            "coins": coins_list_full,
        }),
        content_type="application/json"
    )


async def index(request, sp_or_ft, market1, market2, coin):
    return render(request, 'main/index.html', {'coins_list_full': coins_list_full})


def verify_telegram_auth(init_data_string, bot_token, max_age=86400):
    # Парсим входную строку в словарь, аналогично URLSearchParams в JS
    data = parse_qs(init_data_string)

    # Преобразуем значения в строки (по умолчанию они будут списками)
    data = {k: v[0] for k, v in data.items()}

    # Извлекаем hash и удаляем его из параметров
    check_hash = data.pop('hash', None)

    # Создаем строку data_check_string
    sorted_params = sorted([f"{key}={data[key]}" for key in data])
    data_check_string = "\n".join(sorted_params)

    # Генерация секретного ключа
    secret_key = hmac.new(
        key=b"WebAppData",  # Важно поменять порядок аргументов
        msg=bot_token.encode(),  # Теперь bot_token будет сообщением
        digestmod=hashlib.sha256
    ).hexdigest()

    # Вычисляем конечный хэш
    calculated_hash = hmac.new(
        key=bytes.fromhex(secret_key),  # Преобразуем hex в байты
        msg=data_check_string.encode(),  # Строка, которую мы проверяем
        digestmod=hashlib.sha256
    ).hexdigest()

    # Проверка времени (optional but recommended)
    # комментировать для тестов
    if not IS_DEBUG:
        auth_date = data.get('auth_date')
        if auth_date:
            try:
                auth_ts = int(auth_date)
                now = int(time.time())
                if abs(now - auth_ts) > int(max_age):
                    # слишком старый — отклоняем
                    return False
            except Exception:
                return False

    # Отладочные выводы для проверки
  #  print("Data Check String:", data_check_string)
  #  print("Expected Hash:", check_hash)
   # print("Calculated Hash:", calculated_hash)
   # print(hmac.compare_digest(calculated_hash, check_hash))
    # Сравниваем хэши
    return hmac.compare_digest(calculated_hash, check_hash)


def check_subscription_in_mysql(telegram_id):
    """Подключение к MySQL и проверка подписки"""
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        cursor = connection.cursor(dictionary=True)  # dictionary=True, чтобы получить данные в виде словаря

        query = "SELECT isActive, isActiveAdmin, testActive, timeTest, timeActiveAdmin, referral, memoAccount FROM Users WHERE tgid = %s"
        cursor.execute(query, (telegram_id,))
        user_data = cursor.fetchone()

        cursor.close()
        connection.close()

        return user_data

    except mysql.connector.Error as err:
        print(f"Ошибка подключения к MySQL: {err}")
        return None


@api_view(['POST'])
@permission_classes([AllowAny])
def telegram_login(request):
    try:
        init_data_string = request.body.decode('utf-8')  # Декодируем байтовую строку
        if not verify_telegram_auth(init_data_string, settings.TELEGRAM_BOT_TOKEN):
            return Response({"detail": "Invalid Telegram data"}, status=400)

        data = parse_qs(init_data_string)
        data = {k: v[0] for k, v in data.items()}
        user_info = json.loads(data.get('user', '{}'))
        user_id = user_info.get('id')
        username = user_info.get('username', f"tg_user_{user_id}")

        # Проверяем подписку
        subscription_data = check_subscription_in_mysql(user_id)

        if not subscription_data:
            subscription_data = {
                "isActive": "0",
                "isActiveAdmin": "0",
                "testActive": "0",
                "timeTest": "no",
                "timeActiveAdmin": "no",
                "memoAccount": "error"
            }

        # Проверяем, есть ли пользователь в Django БД
        user, created = User.objects.get_or_create(
            telegram_id=user_id,
            defaults={
                'username': username,
                'subscribe_active': False,  # Подписки нет, так как его не было в MySQL
                'test_active': False,
                'subscribe_start_date': None,
                'test_start_date': None,
            }
        )

        # Если это новый юзер и есть `referral_id`, записываем его
        if created and subscription_data["referral"] != 'no':
            user.referral = subscription_data["referral"]  # Связываем с реферером
            user.save(update_fields=['referral'])

        # Получаем IP-адрес пользователя
        ip_address = request.META.get('REMOTE_ADDR')

        # Записываем новый лог входа
        UserLoginRecord.objects.create(user=user, ip_address=ip_address, timestamp=timezone.now())

        # Проверка активности подписки
        is_blocked_user = subscription_data["isActiveAdmin"] == '0'
        is_active_admin = subscription_data["isActiveAdmin"] == '1'
        is_active = subscription_data["isActive"] == '1'
        test_active = subscription_data["testActive"] == '1'

        if user.subscribe_start_date != subscription_data["timeActiveAdmin"]:
            user.subscribe_start_date = None if subscription_data["timeActiveAdmin"] == 'no' else subscription_data["timeActiveAdmin"]
            user.save(update_fields=['subscribe_start_date'])
        if user.test_start_date != subscription_data["timeTest"]:
            user.test_start_date = None if subscription_data["timeTest"] == 'no' else subscription_data["timeTest"]
            user.save(update_fields=['test_start_date'])
        if not user.subscribe_active and is_active_admin and not is_blocked_user:
            user.subscribe_active = True
            user.save(update_fields=['subscribe_active'])
        if user.subscribe_active and not is_active_admin and not is_blocked_user:
            user.subscribe_active = False
            user.save(update_fields=['subscribe_active'])
        if not user.test_active and test_active and not is_blocked_user:
            user.test_active = True
            user.save(update_fields=['test_active'])
        if user.test_active and not test_active and not is_blocked_user:
            user.test_active = False
            user.save(update_fields=['test_active'])
        # Если подписка закончилась, делаем пользователя неактивным и удаляем токены
        if is_blocked_user:
            user.subscribe_active = False
            user.test_active = False
            user.save(update_fields=['test_active', 'subscribe_active'])
        if not (is_active or is_active_admin or test_active):
            user.subscribe_active = False
            user.test_active = False
            user.save(update_fields=['test_active', 'subscribe_active'])
        if subscription_data["memoAccount"] != 'error':
            user.memo = subscription_data["memoAccount"]
            user.save(update_fields=['memo'])

         #  return Response({"detail": "Доступ запрещен: нет активной подписки"}, status=403)

        # Обновляем дату последнего входа
        user.last_login_time = timezone.now()
        user.save(update_fields=['last_login_time'])

        # Проверяем, есть ли активный refresh-токен для пользователя
        existing_tokens = OutstandingToken.objects.filter(user=user)

        if existing_tokens.exists():
            # Получаем строку токена
            refresh_str = existing_tokens.first().token
            try:
                # Преобразуем в объект RefreshToken
                refresh = RefreshToken(refresh_str)
            except Exception:
                # Если токен невалидный, создаём новый
                refresh = RefreshToken.for_user(user)
        else:
            # Создаём новый токен, если старых нет
            refresh = RefreshToken.for_user(user)

        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        })

    except Exception as e:
        print('e', e)
        return Response({"detail": "Invalid data"}, status=401)


class TelegramTokenObtainPairView(TokenViewBase):
    serializer_class = TelegramTokenObtainSerializer


@api_view(['POST'])
@permission_classes([IsAuthenticated])  # Доступ только аутентифицированным пользователям
def update_depth_value(request):
    user = request.user  # Получаем пользователя из токена
    new_depth_value = request.data.get('depth_value')  # Извлекаем значение из запроса

    if new_depth_value is None:
        return Response({"detail": "Поле 'depth_value' обязательно"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        new_depth_value = int(new_depth_value)
        if new_depth_value < 0:
            return Response({"detail": "depth_value не может быть отрицательным"}, status=status.HTTP_400_BAD_REQUEST)
    except ValueError:
        return Response({"detail": "Некорректное значение depth_value"}, status=status.HTTP_400_BAD_REQUEST)

    user.depth_value = new_depth_value
    user.save(update_fields=['depth_value'])

    return Response({"detail": "depth_value обновлен", "depth_value": user.depth_value}, status=status.HTTP_200_OK)

# ==============================
# Конфигурация
# ==============================
# -------------- 3X-UI ----------------------
PUBLIC_HOST = getattr(settings, "PUBLIC_HOST", "fundingradar.ru")
PUBLIC_PORT = int(getattr(settings, "PUBLIC_PORT", 443))
ORIG_SUB_TEMPLATE = getattr(settings, "ORIG_SUB_TEMPLATE", None)
THIRD_PARTY_HEADERS = getattr(settings, "THIRD_PARTY_HEADERS", {}) or {}
SUB_FETCH_TIMEOUT = getattr(settings, "SUB_FETCH_TIMEOUT", 10)
# limit devices per subscription (по умолчанию 2)
MAX_DEVICES_PER_SUB = int(getattr(settings, 'MAX_DEVICES_PER_SUB', 2))
# считать устройство "активным" если было seen в последние N дней
DEVICE_ACTIVE_DAYS = int(getattr(settings, 'DEVICE_ACTIVE_DAYS', 30))

# Регекс для поиска URI (берёт до пробела/перехода строки)
URI_RE = re.compile(r'\b(vless|vmess|trojan)://[^\s\r\n]+', re.IGNORECASE)

ALLOWED_RESPONSE_HEADERS = {
    "Content-Type",
    "Profile-Title",
    "Profile-Update-Interval",
    "Subscription-Userinfo",
    "Date",
    "Content-Length",
    "Connection",
}

# Маппинг lower->canonical (чтобы сохранять аккуратный вид заголовков)
ALLOWED_LOWER_TO_CANONICAL = {h.lower(): h for h in ALLOWED_RESPONSE_HEADERS}


# ------------- Доп. настройки (в settings.py можно переопределить) -------------
# Блокировать известных роботов по UA (подстроки, регекспы)

# Настройки (можно переопределить в settings.py)
BROWSER_ACCEPT_CHECK = getattr(settings, "BROWSER_ACCEPT_CHECK", True)
BROWSER_UA_SUBSTRINGS = getattr(settings, "BROWSER_UA_SUBSTRINGS", [
    "mozilla", "chrome", "safari", "firefox", "edge", "msie", "trident"
])
# Исключения — если UA содержит любой из этих, то он НЕ считается браузером
KNOWN_CLIENT_UA_SUBSTRINGS = getattr(settings, "KNOWN_CLIENT_UA_SUBSTRINGS", [
    "v2rayng", "v2box", "sing-box", "singbox", "v2raytun", "npvtunnel", "happ",
    "v2ray", "xray", "clash", "okhttp"
])

BOT_UA_SUBSTRINGS = getattr(settings, "BOT_UA_SUBSTRINGS", [
    "telegrambot", "twitterbot", "facebookexternalhit", "discordbot",
    "python-requests", "curl/", "wget", "httpclient", "okhttp", "libwww-perl",
    "scanner", "bot", "spider", "crawl"
])
# Регекспы для явного блокирования (необязательно)
BOT_UA_REGEXPS = getattr(settings, "BOT_UA_REGEXPS", [
    r"^bot", r"spider", r"crawl"
])

# Альтернативный режим: разрешать только "плейлист" известных клиентов (если включено)
# Например: v2rayng, v2box, sing-box, v2raytun, npvtunnel, happ, Sing-box и др.
REQUIRE_KNOWN_CLIENT_UA = getattr(settings, "REQUIRE_KNOWN_CLIENT_UA", False)
KNOWN_CLIENT_UA_SUBSTRINGS = getattr(settings, "KNOWN_CLIENT_UA_SUBSTRINGS", [
    "v2rayng", "v2box", "sing-box", "singbox", "v2raytun", "npvtunnel", "happ",
    "v2ray", "xray", "clash"
])

# Если True — жёстко требовать HWID (иначе будет fallback по UA hash)
REQUIRE_HWID = getattr(settings, "REQUIRE_HWID", False)

# ------------- Функции детекции -------------
def get_max_devices_for_sub(sub_id: str) -> int:
    """
    Вернуть max_devices для конкретного sub_id.
    Если записи нет — вернуть глобальный DEFAULT из settings (MAX_DEVICES_PER_SUB).
    """
    default = int(getattr(settings, "MAX_DEVICES_PER_SUB", 2))
    if not sub_id:
        return default
    try:
        s = SubscriptionSetting.objects.filter(sub_id=sub_id).only("max_devices").first()
        if s and s.max_devices and int(s.max_devices) > 0:
            return int(s.max_devices)
    except Exception:
        # на случай ошибок БД — fallback к default
        pass
    return default

def is_browser_request(request) -> bool:
    """
    Детектируем явный браузерный запрос:
      - основной признак: Accept содержит 'text/html'
      - запасной: UA содержит браузерные маркеры И при этом не содержит известных клиентов/ботов
    """
    ua = (request.headers.get("User-Agent") or request.headers.get("user-agent") or "").lower()
    accept = (request.headers.get("Accept") or request.headers.get("accept") or "").lower()

    # 1) Accept -> text/html
    if BROWSER_ACCEPT_CHECK and "text/html" in accept:
        return True

    # 2) если Accept не помогает — смотрим UA: содержит ли браузерный маркер?
    ua_is_browser_like = False
    for s in BROWSER_UA_SUBSTRINGS:
        if s in ua:
            ua_is_browser_like = True
            break

    if not ua_is_browser_like:
        return False

    # Если UA содержит любой KNOWN_CLIENT_UA_SUBSTRINGS — это не браузер (например v2ray clients)
    for s in KNOWN_CLIENT_UA_SUBSTRINGS:
        if s.lower() in ua:
            return False

    # Также не считаем браузером, если он явно выглядит как бот (наш bot-detector)
    if is_probable_bot_ua(ua):
        return False

    # Иначе — считаем браузером
    return True

def _contains_any(substr_list, text: str) -> bool:
    if not text:
        return False
    tl = text.lower()
    for s in substr_list:
        if s.lower() in tl:
            return True
    return False

def is_probable_bot_ua(ua: str) -> bool:
    """Возвращает True, если ЮА выглядит как бот/сканер (настроиваемо)."""
    if not ua:
        return False
    if _contains_any(BOT_UA_SUBSTRINGS, ua):
        return True
    for rx in BOT_UA_REGEXPS:
        if re.search(rx, ua, re.IGNORECASE):
            return True
    return False

def is_known_client_ua(ua: str) -> bool:
    """Если включён REQUIRE_KNOWN_CLIENT_UA — проверяем, содержит ли UA один из известных клиентов."""
    if not ua:
        return False
    return _contains_any(KNOWN_CLIENT_UA_SUBSTRINGS, ua)

# ------------- Обновлённая get_client_identifier (не меняет API) -------------
def get_client_identifier(request) -> (str, dict):
    headers = {k.lower(): v for k, v in request.headers.items()}
    hwid = headers.get("x-hwid") or headers.get("x-device-id") or headers.get("x-hwid-client")
    ua = headers.get("user-agent", "") or ""
    device_model = headers.get("x-device-model", "")
    app_ver = headers.get("x-app-version", "") or headers.get("x-ver-os", "")
    device_os = headers.get("x-device-os", "")

    # Флаг — обнаружен ли бот по UA
    bot_detected = is_probable_bot_ua(ua)

    if hwid:
        client_id = hwid.strip()
        client_source = "hwid"
    else:
        # fallback: комбинируем и хешируем
        base = f"{ua}|{device_model}|{device_os}|{app_ver}"
        h = hashlib.sha256(base.encode("utf-8")).hexdigest()
        client_id = f"auto-{h[:24]}"
        client_source = "fallback"

    meta = {
        "ua": ua,
        "device_model": device_model,
        "app_version": app_ver,
        "device_os": device_os,
        "client_source": client_source,
        "bot_detected": bot_detected,
        "raw_headers": {k: v for k, v in request.headers.items() if k.lower() in ("x-hwid","x-device-model","x-device-os","x-app-version","x-ver-os")}
    }
    return client_id, meta

def prune_inactive_devices(sub_id: str):
    """
    Удалять/деактивировать старые записи — опционально.
    Здесь можно пометить как не-активные или удалить.
    """
    days = getattr(settings, "DEVICE_ACTIVE_DAYS", 30)
    cutoff = timezone.now() - timedelta(days=days)
    DeviceRecord.objects.filter(sub_id=sub_id, last_seen__lt=cutoff).delete()

# ------------- Интеграция в check_and_register_device -------------
def check_and_register_device(request, sub_id: str) -> (bool, str):
    """
    Возвращает (allowed: bool, reason:str)
    Возможные reason: ok, registered, limit_exceeded, device_blocked, bot_detected, missing_hwid
    """
    # --- новоe: блокируем браузерные запросы ---
    if is_browser_request(request):
        logger.info("Blocked browser request for sub=%s from UA=%s", sub_id, request.headers.get("User-Agent"))
        return False, "browser_request"

    max_devices = getattr(settings, "MAX_DEVICES_PER_SUB", 2)

    client_id, meta = get_client_identifier(request)

    # Если включена политика "только известные клиенты" — отклоняем неизвестных UA
    if REQUIRE_KNOWN_CLIENT_UA:
        if not is_known_client_ua(meta.get("ua", "")):
            logger.warning("Blocked unknown client UA for sub=%s ua=%s", sub_id, meta.get("ua"))
            return False, "unknown_client_ua"

    # Если включено требование HWID и клиент использует fallback -> блокируем
    if REQUIRE_HWID and meta.get("client_source") != "hwid":
        logger.warning("Blocked device without HWID for sub=%s (ua=%s)", sub_id, meta.get("ua"))
        return False, "missing_hwid"

    # Блокировка очевидных ботов по UA
    if meta.get("bot_detected"):
        logger.info("Blocked probable bot UA for sub=%s ua=%s", sub_id, meta.get("ua"))
        return False, "bot_detected"

    # Очистка старых записей для этого sub (опционально)
    prune_inactive_devices(sub_id)

    try:
        dev = DeviceRecord.objects.get(sub_id=sub_id, client_id=client_id)
        # Уже зарегистрировано — обновляем last_seen
        dev.ua = meta.get("ua")[:512] if meta.get("ua") else dev.ua
        dev.hw_info = meta.get("raw_headers") or dev.hw_info
        dev.touch()
        if dev.blocked:
            return False, "device_blocked"
        return True, "ok"
    except DeviceRecord.DoesNotExist:
        max_devices = get_max_devices_for_sub(sub_id)  # <- индивидуальный лимит здесь
        # сколько активных устройств сейчас?
        active_count = DeviceRecord.objects.filter(sub_id=sub_id, blocked=False).count()
        if active_count < max_devices:
            # создаём запись
            DeviceRecord.objects.create(
                sub_id=sub_id,
                client_id=client_id,
                ua=meta.get("ua")[:512],
                hw_info=meta.get("raw_headers") or {},
            )
            logger.info("Registered new device for sub=%s client=%s ua=%s", sub_id, client_id, meta.get("ua"))
            return True, "registered"
        else:
            # лимит исчерпан
            logger.info("Device limit exceeded for sub=%s client=%s ua=%s (active=%s max=%s)", sub_id, client_id, meta.get("ua"), max_devices)
            return False, "limit_exceeded"

def try_base64_decode_bytes(data: bytes) -> str | None:
    """Попытка декодировать "весь" ответ как base64 и вернуть текст (если внутри vless/vmess/... )"""
    s = data.decode("utf-8", errors="ignore").strip()
    padded = s + "=" * (-len(s) % 4)
    try:
        dec = base64.b64decode(padded, validate=False)
        txt = dec.decode("utf-8", errors="ignore")
        if txt.startswith(("vless://", "vmess://", "trojan://")):
            return txt
    except Exception:
        return None
    return None

def replace_uri_match(m: re.Match) -> str:
    """
    Безопасная замена host:port в URI-строках.
    Для vmess: раскодируем base64 -> тектовая JSON-строка -> заменим только "add" и "port" регекспом -> рекодируем.
    Для vless/trojan: парсим через urlparse и аккуратно заменяем netloc (userinfo@host:port).
    """
    uri = m.group(0)
    scheme = uri.split("://", 1)[0].lower()

    if scheme == "vmess":
        # vmess://BASE64
        b64 = uri[len("vmess://"):]
        # корректный паддинг для декодирования
        padded = b64 + "=" * (-len(b64) % 4)
        try:
            decoded = base64.b64decode(padded)
            txt = decoded.decode("utf-8", errors="ignore")

            # Заменим поля "add": "..." и "port": xxx только текстово, чтобы не менять форматирование JSON
            # 1) replace add
            txt2 = re.sub(r'("add"\s*:\s*)"[^"]+"', r'\1"{}"'.format(PUBLIC_HOST), txt, count=1)
            # 2) replace port (число)
            txt2 = re.sub(r'("port"\s*:\s*)(\d+)', r'\1{}'.format(PUBLIC_PORT), txt2, count=1)

            # Если ничего не поменялось (редко), всё равно используем txt2
            new_b64 = base64.b64encode(txt2.encode("utf-8")).decode('utf-8').rstrip('=')
            return "vmess://" + new_b64
        except Exception:
            # в случае ошибки — возвращаем оригинальную URI без изменений
            return uri

    else:
        # vless:// или trojan:// — аккуратно заменить netloc через urlparse/urlunparse
        try:
            parsed = urlparse(uri)
            netloc = parsed.netloc  # userinfo@host:port  или host:port
            if "@" in netloc:
                userinfo, rest = netloc.split("@", 1)
                new_netloc = f"{userinfo}@{PUBLIC_HOST}:{PUBLIC_PORT}"
            else:
                new_netloc = f"{PUBLIC_HOST}:{PUBLIC_PORT}"

            new_parsed = parsed._replace(netloc=new_netloc)
            new_uri = urlunparse(new_parsed)
            return new_uri
        except Exception:
            # fallback — простая регексп-замена первого @host:port
            return re.sub(r'@[^:\/\s]+:\d+', f'@{PUBLIC_HOST}:{PUBLIC_PORT}', uri, count=1)


def detect_base64_subscription(resp: requests.Response):
    """Определяем, base64-ли ответ; возвращаем (decoded_text, is_base64)."""
    raw = resp.content
    # 1) Попробовать декодировать весь ответ как base64
    decoded = try_base64_decode_bytes(raw)
    if decoded is not None:
        return decoded, True
    # 2) Иначе считаем, что это plain text (возможно уже список URI)
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        text = ""
    return text, False

@api_view(["GET"])
@permission_classes([AllowAny])
def proxy_subscription(request, user: str = None):
    """
    /subs/proxy/<user>/  или  /subs/proxy/?url=...
    Запрашиваем подписку у origin (3x-ui), подставляем PUBLIC_HOST:PUBLIC_PORT в URI-ы,
    и возвращаем тело + только нужные заголовки (ALLOWED_RESPONSE_HEADERS).
    Также при запросе к origin пробрасываем заголовки от клиента + THIRD_PARTY_HEADERS.
    """
    sub_id = user or request.GET.get("sub") or request.GET.get("user")
    if not sub_id:
        return Response({"detail": "No sub id"}, status=400)

    # Проверяем / регистрируем устройство
    allowed, reason = check_and_register_device(request, sub_id)
    if not allowed:
        if reason == "limit_exceeded":
            return Response({"detail": "Device limit exceeded for this subscription"}, status=403)
        elif reason == "device_blocked":
            return Response({"detail": "This device is blocked"}, status=403)
        elif reason == "browser_request":
            return Response({"detail": "Browser requests are not allowed for subscriptions"}, status=403)
        else:
            return Response({"detail": "Access denied"}, status=403)

    orig_url = request.GET.get("url")
    if not orig_url:
        if ORIG_SUB_TEMPLATE and user:
            orig_url = ORIG_SUB_TEMPLATE.format(user=user)
        else:
            return Response({"detail": "Не указан ?url=... и нет ORIG_SUB_TEMPLATE"}, status=400)
    # --- подготовим заголовки для запроса к origin (берём заголовки клиента + допы) ---
    forward_headers = {}
    # копируем клиентские заголовки
    for k, v in request.headers.items():
        forward_headers[k] = v

    # дополняем X-Forwarded-For
    client_ip = request.META.get("REMOTE_ADDR")
    if client_ip:
        existing_xff = forward_headers.get("X-Forwarded-For")
        if existing_xff:
            forward_headers["X-Forwarded-For"] = f"{existing_xff}, {client_ip}"
        else:
            forward_headers["X-Forwarded-For"] = client_ip

    # ставим Host как в orig_url (чтобы 3x-ui правильно генерировал свои JSON/заголовки)
    try:
        parsed_orig = urlparse(orig_url)
        if parsed_orig.netloc:
            forward_headers["Host"] = parsed_orig.netloc
    except Exception:
        pass

    # добавляем THIRD_PARTY_HEADERS, если задано (но не перезаписываем клиентские явно)
    if isinstance(THIRD_PARTY_HEADERS, dict):
        for k, v in THIRD_PARTY_HEADERS.items():
            if k not in forward_headers:
                forward_headers[k] = v

    # --- запрос к origin ---
    try:
        logger.info("Proxy request to %s for sub=%s", orig_url, sub_id)
        r = requests.get(orig_url, headers=forward_headers, timeout=SUB_FETCH_TIMEOUT, verify=False)
        logger.info("Proxy response: status=%d, content_length=%d", r.status_code, len(r.content))
    except Exception as e:
        logger.exception("Proxy request failed for sub=%s url=%s", sub_id, orig_url)
        return Response({"error": str(e)}, status=502)

    if r.status_code != 200:
        logger.warning("Origin returned %d for sub=%s url=%s", r.status_code, sub_id, orig_url)
        return Response({"error": f"Origin returned {r.status_code}"}, status=502)

    # --- обработка тела ---
    decoded_text, was_base64 = detect_base64_subscription(r)

    try:
        final_decoded = URI_RE.sub(lambda m: replace_uri_match(m), decoded_text)
    except Exception:
        final_decoded = decoded_text

    # --- формирование тела ответа клиенту ---
    if was_base64:
        out_b = base64.b64encode(final_decoded.encode("utf-8")).decode().rstrip("=")
        content_bytes = out_b.encode("utf-8")
    else:
        content_bytes = final_decoded.encode("utf-8")

    resp = HttpResponse(content=content_bytes, status=r.status_code)

    # Content-Type — как у origin, иначе text/plain
    content_type = r.headers.get("Content-Type")
    if content_type:
        resp["Content-Type"] = content_type
    else:
        resp["Content-Type"] = "text/plain; charset=utf-8"

    # --- Копируем ТОЛЬКО разрешённые заголовки, корректно по регистру ---
    # Используем case-insensitive проверку на r.headers (requests supports that)
    # и в ответ проставляем canonical имена заголовков из ALLOWED_LOWER_TO_CANONICAL.
    for hk, hv in r.headers.items():
        lower = hk.lower()
        if lower in ALLOWED_LOWER_TO_CANONICAL and lower != "content-length":
            canonical = ALLOWED_LOWER_TO_CANONICAL[lower]
            resp[canonical] = hv

    # Если origin отдал Connection но с не-'Connection' ключом (редко), обеспечим копию:
    # requests' r.headers.get is case-insensitive, проверим и установим
    conn_val = r.headers.get("Connection")
    if conn_val:
        resp["Connection"] = conn_val

    # корректный Content-Length (по фактическому телу ответа)
    resp["Content-Length"] = str(len(content_bytes))

    return resp