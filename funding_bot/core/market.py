# core/market.py
import os
import time
import threading
import logging
import orjson
import numpy as np

logger = logging.getLogger("core.market")
logging.basicConfig(level=logging.INFO)


class MarketState:
    def __init__(self):
        try:
            self.data_max_age = float(os.getenv('DATA_MAX_AGE', '15.0'))
        except Exception:
            self.data_max_age = 10.0

        # ---- Словари для обратной совместимости ----
        self.data_usdt = {}
        self.data_spot_usdt = {}
        self.data_spot_source = {}
        self.data_spot_usdt_global = {}      # больше не используется для поиска, оставлен для совместимости
        self.data_to_db = []
        self.data_to_spot = []
        self.bids_asks_futures_all = {}
        self.bids_asks_spot_all = {}
        self.bids_asks_dex_all = {}
        self.dex_data = {}
        self.dex_meta = {}
        self.dex_changed = set()
        self.dex_pairs = []
        self.dex_last_written = {}
        self.dex_index = {}
        self.last_seen = {}
        self.extra_meta_per_market = {}
        self.timer_time_to_add = None
        self.dirty = False
        self.dirty_markets = set()

        self.markets = ['Bybit', 'Mexc', 'Kucoin', 'Gateio', 'Bitget', 'Huobi', 'Okx',
                        'Binance', 'BingX', 'BitMart', 'Ourbit', 'Hyperliquid', 'LBank',
                        'Aster', 'XT', 'CoinEx', 'WEEX', 'Phemex', 'BinanceAlpha']

        self.market = {
            'Bybit': ['Bybit', 1, 2, 3, 4, 5, 6, 7],
            'Mexc': ['Mexc', 8, 9, 10, 11, 12, 13, 14],
            'Kucoin': ['Kucoin', 15, 16, 17, 18, 19, 20, 21],
            'Gateio': ['Gateio', 22, 23, 24, 25, 26, 27, 28],
            'Bitget': ['Bitget', 29, 30, 31, 32, 33, 34, 35],
            'Huobi': ['Huobi', 36, 37, 38, 39, 40, 41, 42],
            'Okx': ['Okx', 43, 44, 45, 46, 47, 48, 49],
            'Binance': ['Binance', 50, 51, 52, 53, 54, 55, 56],
            'BingX': ['BingX', 57, 58, 59, 60, 61, 62, 63],
            'BitMart': ['BitMart', 64, 65, 66, 67, 68, 69, 70],
            'Ourbit': ['Ourbit', 71, 72, 73, 74, 75, 76, 77],
            'Hyperliquid': ['Hyperliquid', 78, 79, 80, 81, 82, 83, 84],
            'LBank': ['LBank', 85, 86, 87, 88, 89, 90, 91],
            'Aster': ['Aster', 92, 93, 94, 95, 96, 97, 98],
            'XT': ['XT', 99, 100, 101, 102, 103, 104, 105],
            'CoinEx': ['CoinEx', 106, 107, 108, 109, 110, 111, 112],
            'WEEX': ['WEEX', 113, 114, 115, 116, 117, 118, 119],
            'Phemex': ['Phemex', 120, 121, 122, 123, 124, 125, 126],
            'BinanceAlpha': ['BinanceAlpha', 127, 128, 129, 130, 131, 132, 133],
        }
        self.market_spot = {
            'Bybit': [1, 2], 'Mexc': [3, 4], 'Kucoin': [5, 6], 'Gateio': [7, 8],
            'Bitget': [9, 10], 'Huobi': [11, 12], 'Okx': [13, 14], 'Binance': [15, 16],
            'BingX': [17, 18], 'BitMart': [19, 20], 'Ourbit': [21, 22], 'Hyperliquid': [23, 24],
            'LBank': [25, 26], 'Aster': [27, 28], 'XT': [29, 30], 'CoinEx': [31, 32],
            'WEEX': [33, 34], 'Phemex': [35, 36], 'BinanceAlpha': [37, 38],
        }
        self.data_usdt_len_massiv = 134
        self.data_to_spot_len_massiv = 39
        self.len_data_usdt = 136

        self.fees = {
            'Bybit': 0.1, 'Mexc': 0.1, 'Kucoin': 0.1, 'Gateio': 0.2, 'Bitget': 0.1,
            'Huobi': 0.2, 'Okx': 0.1, 'Binance': 0.1, 'BingX': 0.1, 'BitMart': 0.1,
            'Ourbit': 0, 'Hyperliquid': 0.045, 'LBank': 0.1, 'Aster': 0.04, 'XT': 0.2,
            'CoinEx': 0.2, 'WEEX': 0.1, 'Phemex': 0.1, 'BinanceAlpha': 0.15,
        }
        self.fees_fut = {
            'Bybit': 0.1, 'Mexc': 0.02, 'Kucoin': 0.06, 'Gateio': 0.05, 'Bitget': 0.06,
            'Huobi': 0.05, 'Okx': 0.05, 'Binance': 0.05, 'BingX': 0.05, 'BitMart': 0.06,
            'Ourbit': 0.04, 'Hyperliquid': 0.1, 'LBank': 0.06, 'Aster': 0.035,
            'XT': 0.06, 'CoinEx': 0.05, 'WEEX': 0.08, 'Phemex': 0.06, 'BinanceAlpha': 0.0,
        }

        # чёрные списки (оставлены без изменений)
        self.blacklist_futures = {
            (symbol, frozenset((m1, m2)))
            for symbol, m1, m2 in [
                ('GPTUSDT', 'Mexc', 'Gateio'), ('GPTUSDT', 'Mexc', 'Okx'),
                ('GPTUSDT', 'Bybit', 'Okx'), ('GPTUSDT', 'Bybit', 'Gateio'),
                ('DEGENUSDT', 'Mexc', 'Mexc'), ('DEGENUSDT', 'Mexc', 'Bybit'),
                ('REEFUSDT', 'Gateio', 'Bybit'), ('NEIROUSDT', 'Okx', 'Kucoin'),
                ('REEFUSDT', 'Bybit', 'Mexc'), ('NEIROUSDT', 'Okx', 'Gateio'),
                ('REEFUSDT', 'Bybit', 'BitMart'), ('NEIROUSDT', 'BitMart', 'Gateio'),
                ('REEFUSDT', 'Bitget', 'Bybit'), ('TRUMPUSDT', 'Mexc', 'Kucoin'),
                ('REEFUSDT', 'Kucoin', 'Bybit'), ('TRUMPUSDT', 'Mexc', 'Gateio'),
                ('REEFUSDT', 'Kucoin', 'Gateio'), ('TRUMPUSDT', 'Mexc', 'Huobi'),
                ('REEFUSDT', 'Bybit', 'Binance'), ('TRUMPUSDT', 'Mexc', 'Bitget'),
                ('CLVUSDT', 'Gateio', 'Mexc'), ('TRUMPUSDT', 'Mexc', 'Okx'),
                ('TRUMPUSDT', 'Mexc', 'Bybit'), ('TRUMPUSDT', 'Mexc', 'BitMart'),
                ('ZKUSDT', 'Bybit', 'Bitget'), ('ZKUSDT', 'Gateio', 'Bitget'),
                ('ZKUSDT', 'Kucoin', 'Bitget'), ('VELOUSDT', 'Bybit', 'Bitget'),
                ('VELOUSDT', 'Mexc', 'Bitget'), ('VELOUSDT', 'Gateio', 'Bitget'),
                ('NEIROUSDT', 'Gateio', 'Bitget'), ('TRUMPUSDT', 'Mexc', 'Binance'),
                ('VELOUSDT', 'Okx', 'Bitget'), ('ZKUSDT', 'Okx', 'Bitget'),
                ('ZKUSDT', 'Binance', 'Bitget'), ('ZKUSDT', 'BingX', 'Bitget'),
                ('ZKUSDT', 'Huobi', 'Bitget'), ('NEIROUSDT', 'Okx', 'Bitget'),
                ('NEIROUSDT', 'Binance', 'Bitget'), ('NEIROUSDT', 'Binance', 'Gateio'),
                ('NEIROUSDT', 'BitMart', 'Kucoin'), ('NEIROUSDT', 'Gateio', 'Kucoin'),
                ('ZKUSDT', 'BitMart', 'Bitget'), ('NEIROUSDT', 'Binance', 'Kucoin'),
                ('ALTCOINUSDT', 'Mexc', 'BingX'), ('TRUMPUSDT', 'Mexc', 'Hyperliquid'),
                ('LIGHTUSDT', 'LBank', 'Huobi'), ('LIGHTUSDT', 'LBank', 'Bybit'),
                ('LIGHTUSDT', 'LBank', 'Bitget'), ('LIGHTUSDT', 'LBank', 'Gateio'),
                ('MEMECOINUSDT', 'Mexc', 'LBank'), ('MEMECOINUSDT', 'LBank', 'Mexc'),
                ('LIGHTUSDT', 'LBank', 'Mexc'), ('LIGHTUSDT', 'LBank', 'Ourbit'),
                ('LIGHTUSDT', 'LBank', 'BitMart'), ('FUNUSDT', 'Mexc', 'Okx'),
                ('FUNUSDT', 'Binance', 'Okx'), ('FUNUSDT', 'Mexc', 'Aster'),
                ('FUNUSDT', 'Binance', 'Aster'), ('FUNUSDT', 'Mexc', 'Bitget'),
                ('FUNUSDT', 'Mexc', 'Gateio'), ('FUNUSDT', 'Binance', 'Gateio'),
                ('FUNUSDT', 'Binance', 'Bitget'), ('FUNUSDT', 'LBank', 'Okx'),
                ('FUNUSDT', 'BitMart', 'Okx'), ('FUNUSDT', 'LBank', 'Bitget'),
                ('FUNUSDT', 'LBank', 'Gateio'), ('FUNUSDT', 'LBank', 'Aster'),
                ('FUNUSDT', 'BitMart', 'Aster'), ('FUNUSDT', 'BitMart', 'Gateio'),
                ('FUNUSDT', 'BitMart', 'Bitget'), ('CATUSDT', 'LBank', 'XT'),
                ('CATUSDT', 'Mexc', 'Bitmart'), ('CATUSDT', 'Ourbit', 'Bitmart'),
                ('CATUSDT', 'LBank', 'Bitmart'), ('CATUSDT', 'Mexc', 'Bitget'),
                ('CATUSDT', 'Ourbit', 'Bitget'), ('CATUSDT', 'LBank', 'Binance'),
                ('CATUSDT', 'Mexc', 'Binance'), ('CATUSDT', 'Ourbit', 'Binance'),
                ('CATUSDT', 'Mexc', 'XT'), ('CATUSDT', 'Ourbit', 'XT'),

            ]
        }
        self.blacklist_spot = {
            (symbol, frozenset((m1, m2)))
            for symbol, m1, m2 in [
                ('ACEUSDT', 'Kucoin', 'Gateio'), ('DEGENUSDT', 'Mexc', 'Mexc'),
                ('DEGENUSDT', 'Mexc', 'Gateio'), ('GASUSDT', 'Mexc', 'Okx'),
                ('AIUSDT', 'Kucoin', 'Kucoin'), ('MDTUSDT', 'Mexc', 'Kucoin'),
                ('DEGENUSDT', 'Mexc', 'CoinEx'), ('ALTUSDT', 'Kucoin', 'Gateio'),
                ('MDTUSDT', 'Mexc', 'Mexc'), ('MDTUSDT', 'Mexc', 'BingX'),
                ('MDTUSDT', 'Mexc', 'Binance'), ('MDTUSDT', 'Mexc', 'Bybit'),
                ('GASUSDT', 'Mexc', 'BingX'), ('DEGENUSDT', 'Mexc', 'Bybit'),
                ('DEGENUSDT', 'Mexc', 'BingX'), ('QIUSDT', 'Mexc', 'Bybit'),
                ('QIUSDT', 'Mexc', 'Mexc'), ('ALTUSDT', 'Kucoin', 'CoinEx'),
                ('ALTUSDT', 'Mexc', 'CoinEx'), ('DASHUSDT', 'Bybit', 'Mexc'),
                ('FBUSDT', 'Bybit', 'Mexc'), ('DASHUSDT', 'Bybit', 'Bybit'),
                ('DASHUSDT', 'Bybit', 'Binance'), ('DASHUSDT', 'Bybit', 'Kucoin'),
                ('GRASSUSDT', 'BitMart', 'BitMart'), ('BIDUSDT', 'BitMart', 'BitMart'),
                ('CLVUSDT', 'Gateio', 'Gateio'), ('BIDUSDT', 'BitMart', 'Gateio'),
                ('BIDUSDT', 'BitMart', 'Mexc'), ('BIDUSDT', 'BitMart', 'BingX'),
                ('BIDUSDT', 'BitMart', 'Bitget'), ('SNSUSDT', 'Gateio', 'Mexc'),
                ('SNSUSDT', 'Kucoin', 'Mexc'), ('BIDUSDT', 'Gateio', 'BitMart'),
                ('BIDUSDT', 'Mexc', 'BitMart'), ('BIDUSDT', 'BitMart', 'Binance'),
                ('WHITEUSDT', 'Gateio', 'Mexc'), ('WHITEUSDT', 'BingX', 'Mexc'),
                ('BIDUSDT', 'BitMart', 'Huobi'), ('BIDUSDT', 'BitMart', 'Ourbit'),
                ('FLOKIUSDT', 'BitMart', 'Bitget'), ('FLOKIUSDT', 'BitMart', 'Mexc'),
                ('FLOKIUSDT', 'BitMart', 'Gateio'), ('FLOKIUSDT', 'BitMart', 'Okx'),
                ('FLOKIUSDT', 'BitMart', 'BingX'), ('FLOKIUSDT', 'BitMart', 'Huobi'),
                ('FLOKIUSDT', 'BitMart', 'BitMart'), ('UUSDT', 'BitMart', 'Gateio'),
                ('UUSDT', 'BitMart', 'Mexc'), ('UUSDT', 'BitMart', 'Bitget'),
                ('UUSDT', 'BitMart', 'Ourbit'), ('ZECUSDT', 'Huobi', 'Bybit'),
                ('ZECUSDT', 'Huobi', 'Mexc'), ('ZECUSDT', 'Huobi', 'Ourbit'),
                ('MEMECOINUSDT', 'Mexc', 'LBank'), ('MEMECOINUSDT', 'Bitget', 'LBank'),
                ('MEMECOINUSDT', 'LBank', 'LBank'), ('MEMECOINUSDT', 'Bitget', 'Mexc'),
                ('ZKUSDT', 'Huobi', 'Bitget'), ('UUSDT', 'LBank', 'Gateio'),
                ('UUSDT', 'LBank', 'Ourbit'), ('UUSDT', 'LBank', 'Mexc'),
                ('UUSDT', 'LBank', 'Bitget'), ('FLOKIUSDT', 'BitMart', 'LBank'),
                ('ZECUSDT', 'Huobi', 'LBank'), ('KLAYUSDT', 'LBank', 'Bitget'),
                ('BIDUSDT', 'BitMart', 'LBank'), ('XBTUSDT', 'LBank', 'Kucoin'),
                ('APPUSDT', 'Mexc', 'Bitget'), ('APPUSDT', 'Kucoin', 'Bitget'),
                ('APPUSDT', 'Gateio', 'Bitget'), ('MAUSDT', 'Mexc', 'Bitget'),
                ('MAUSDT', 'Gateio', 'Bitget'), ('PEPUSDT', 'Mexc', 'Bitget'),
                ('GMEUSDT', 'Gateio', 'Bitget'), ('GMEUSDT', 'LBank', 'Bitget'),
                ('GMEUSDT', 'Ourbit', 'Bitget'), ('GMEUSDT', 'Mexc', 'Bitget'),
                ('ARCUSDT', 'Mexc', 'Bitget'), ('ARCUSDT', 'Mexc', 'Huobi'),
                ('ARCUSDT', 'Mexc', 'Binance'), ('ARCUSDT', 'Mexc', 'Bybit'),
                ('ARCUSDT', 'Mexc', 'Kucoin'), ('ARCUSDT', 'Mexc', 'Gateio'),
                ('FUNUSDT', 'Binance', 'Bitget'), ('FUNUSDT', 'Binance', 'Okx'),
                ('FUNUSDT', 'Binance', 'Aster'), ('FUNUSDT', 'Binance', 'Gateio'),
                ('METAUSDT', 'LBank', 'Ourbit'), ('METAUSDT', 'LBank', 'Aster'),
                ('TSTUSDT', 'Gateio', 'BingX'), ('TSTUSDT', 'Gateio', 'Hyperliquid'),
                ('TSTUSDT', 'Gateio', 'BitMart'), ('TSTUSDT', 'Gateio', 'Mexc'),
                ('TSTUSDT', 'Gateio', 'Binance'), ('TSTUSDT', 'Gateio', 'Ourbit'),
                ('TSTUSDT', 'Gateio', 'LBank'), ('FIGHTUSDT', 'LBank', 'Kucoin'),
                ('FIGHTUSDT', 'LBank', 'Bybit'), ('FIGHTUSDT', 'LBank', 'Bitget'),
                ('FIGHTUSDT', 'LBank', 'Aster'), ('FIGHTUSDT', 'LBank', 'Mexc'),
                ('FIGHTUSDT', 'LBank', 'BitMart'), ('FIGHTUSDT', 'LBank', 'Aster'),
                ('FIGHTUSDT', 'LBank', 'Binance'), ('FIGHTUSDT', 'LBank', 'Ourbit'),
                ('ARCUSDT', 'Mexc', 'BitMart'), ('ARCUSDT', 'Mexc', 'Ourbit'),
                ('ARCUSDT', 'Mexc', 'LBank'), ('FUNUSDT', 'LBank', 'Aster'),
                ('FUNUSDT', 'LBank', 'Gateio'), ('FUNUSDT', 'LBank', 'Bitget'),
                ('FUNUSDT', 'LBank', 'Okx'), ('FUNUSDT', 'Huobi', 'Aster'),
                ('FUNUSDT', 'Huobi', 'Gateio'), ('FUNUSDT', 'Huobi', 'Okx'),
                ('FUNUSDT', 'Huobi', 'Bitget'), ('ZKPUSDT', 'BitMart', 'Bybit'),
                ('ZKPUSDT', 'BitMart', 'Gateio'), ('ZKPUSDT', 'BitMart', 'Kucoin'),
                ('ZKPUSDT', 'BitMart', 'BingX'), ('ZKPUSDT', 'BitMart', 'Bitget'),
                ('ZKPUSDT', 'BitMart', 'Okx'), ('ZKPUSDT', 'BitMart', 'Mexc'),
                ('ZKPUSDT', 'BitMart', 'Ourbit'), ('ZKPUSDT', 'BitMart', 'Huobi'),
                ('ZKPUSDT', 'BitMart', 'Aster'), ('ZKPUSDT', 'BitMart', 'LBank'),
                ('ZKPUSDT', 'BitMart', 'BitMart'), ('ZKPUSDT', 'BitMart', 'Binance'),
                ('AINUSDT', 'LBank', 'BitMart'), ('AINUSDT', 'LBank', 'Binance'),
                ('AINUSDT', 'LBank', 'Ourbit'), ('AINUSDT', 'LBank', 'Mexc'),
                ('AINUSDT', 'LBank', 'Bybit'), ('AINUSDT', 'LBank', 'BingX'),
                ('AINUSDT', 'LBank', 'Bitget'), ('AINUSDT', 'LBank', 'Gateio'),
                ('AINUSDT', 'LBank', 'Kucoin'), ('MONUSDT', 'Huobi', 'BitMart'),
                ('MONUSDT', 'Huobi', 'Aster'), ('MONUSDT', 'Huobi', 'Hyperliquid'),
                ('MONUSDT', 'Huobi', 'Kucoin'), ('MONUSDT', 'Huobi', 'Binance'),
                ('MONUSDT', 'Huobi', 'LBank'), ('MONUSDT', 'Huobi', 'Ourbit'),
                ('MONUSDT', 'Huobi', 'Bybit'), ('MONUSDT', 'Huobi', 'Gateio'),
                ('MONUSDT', 'Huobi', 'Okx'), ('MONUSDT', 'Huobi', 'Bitget'),
                ('SCUSDT', 'LBank', 'Gateio'), ('SCUSDT', 'LBank', 'Bybit'),
                ('SCUSDT', 'LBank', 'Ourbit'), ('SCUSDT', 'LBank', 'Mexc'),
                ('BUTTCOINUSDT', 'LBank', 'BingX'), ('1USDT', 'LBank', 'Gateio'),
                ('1USDT', 'LBank', 'Mexc'), ('METAUSDT', 'LBank', 'Bitget'),
                ('FIGHTUSDT', 'LBank', 'Gateio'), ('AIAUSDT', 'XT', 'Gateio'),
                ('AIAUSDT', 'XT', 'BitMart'), ('AIAUSDT', 'XT', 'Mexc'),
                ('AIAUSDT', 'XT', 'Binance'), ('AIAUSDT', 'XT', 'XT'),
                ('AIAUSDT', 'XT', 'BingX'), ('AIAUSDT', 'XT', 'Aster'),
                ('ASTEROIDUSDT', 'Mexc', 'LBank'), ('ZKPUSDT', 'BitMart', 'XT'),
                ('FUNUSDT', 'CoinEx', 'Aster'),
            ]
        }

        for m in self.market.keys():
            self.bids_asks_futures_all[m] = {}
            self.bids_asks_spot_all[m] = {}
            self.extra_meta_per_market[m] = {}

        self.lock = threading.RLock()
        self.currentUpdated = 'updated2'

        # ---- NumPy структуры ----
        self.M_fut = len(self.markets)
        self.market_to_idx = {name: i for i, name in enumerate(self.markets)}
        self.market_to_idx['Dex'] = self.M_fut
        self.M_total = self.M_fut + 1

        self.symbols_fut = []
        self.sym_to_idx_fut = {}
        self.symbols_global = []
        self.sym_to_idx_global = {}

        self.fut_funding = np.zeros((0, self.M_total), dtype=np.float64)
        self.fut_bid = np.zeros((0, self.M_total), dtype=np.float64)
        self.fut_ask = np.zeros((0, self.M_total), dtype=np.float64)
        self.fut_index = np.zeros((0, self.M_total), dtype=np.float64)
        self.fut_interval = np.zeros((0, self.M_total), dtype=np.int32)
        self.fut_amount24 = np.zeros((0, self.M_total), dtype=np.float64)
        self.fut_limits = np.zeros((0, self.M_total), dtype=np.float64)
        self.fut_fresh = np.zeros((0, self.M_total), dtype=np.bool_)

        self.glob_funding = np.zeros((0, self.M_total), dtype=np.float64)
        self.glob_fut_bid = np.zeros((0, self.M_total), dtype=np.float64)
        self.glob_fut_ask = np.zeros((0, self.M_total), dtype=np.float64)
        self.glob_index = np.zeros((0, self.M_total), dtype=np.float64)
        self.glob_spot_ask = np.zeros((0, self.M_total), dtype=np.float64)
        self.glob_spot_bid = np.zeros((0, self.M_total), dtype=np.float64)
        self.glob_interval = np.zeros((0, self.M_total), dtype=np.int32)
        self.glob_amount24 = np.zeros((0, self.M_total), dtype=np.float64)
        self.glob_limits = np.zeros((0, self.M_total), dtype=np.float64)
        self.glob_amount24_spot = np.zeros((0, self.M_total), dtype=np.float64)
        self.glob_fresh_fut = np.zeros((0, self.M_total), dtype=np.bool_)
        self.spot_source_idx = np.zeros(0, dtype=np.int32)

        self.last_seen_fut = np.zeros((0, self.M_total), dtype=np.float64)
        self.last_seen_spot = np.zeros((0, self.M_total), dtype=np.float64)

        self._capacity = 0
        self._num_fut = 0
        self._num_glob = 0
        self._ensure_capacity(1024)
        self._prepare_blacklists()
        # оптимизация: словарь символ -> set упакованных пар (i,j) для быстрой проверки blacklist
        self.blacklist_fut_dict = {}
        for sym, i, j in self.blacklist_fut_set:
            packed = i * self.M_fut + j
            self.blacklist_fut_dict.setdefault(sym, set()).add(packed)

    # Вспомогательные методы (без изменений)
    def _normalize_market_name(self, name):
        name = name.strip().title()
        if name == 'Bitmart':
            return 'BitMart'
        return name

    def _prepare_blacklists(self):
        self.blacklist_fut_set = set()
        for sym, froz in self.blacklist_futures:
            items = tuple(froz)
            if len(items) == 1:
                m = items[0]
                i = self.market_to_idx.get(m)
                if i is not None:
                    self.blacklist_fut_set.add((sym, i, i))
                continue
            m1, m2 = items[0], items[1]
            i = self.market_to_idx.get(m1)
            j = self.market_to_idx.get(m2)
            if i is not None and j is not None and i != j:
                self.blacklist_fut_set.add((sym, min(i, j), max(i, j)))

        self.blacklist_spot_set = set()
        for sym, froz in self.blacklist_spot:
            items = tuple(froz)
            if len(items) == 1:
                m = items[0]
                i = self.market_to_idx.get(m)
                if i is not None:
                    self.blacklist_spot_set.add((sym, i, i))
                continue
            m1, m2 = items[0], items[1]
            i = self.market_to_idx.get(m1)
            j = self.market_to_idx.get(m2)
            if i is not None and j is not None and i != j:
                self.blacklist_spot_set.add((sym, i, j))
                self.blacklist_spot_set.add((sym, j, i))

    def _ensure_capacity(self, capacity):
        if capacity <= self._capacity:
            return
        for arr_name in ['fut_funding', 'fut_bid', 'fut_ask', 'fut_index', 'fut_interval',
                         'fut_amount24', 'fut_limits', 'fut_fresh', 'last_seen_fut']:
            arr = getattr(self, arr_name)
            if arr.shape[0] < capacity:
                new_arr = np.zeros((capacity, self.M_total), dtype=arr.dtype)
                new_arr[:arr.shape[0]] = arr
                setattr(self, arr_name, new_arr)
        for arr_name in ['glob_funding', 'glob_fut_bid', 'glob_fut_ask', 'glob_index',
                         'glob_spot_ask', 'glob_spot_bid', 'glob_interval', 'glob_amount24',
                         'glob_limits', 'glob_amount24_spot', 'glob_fresh_fut', 'last_seen_spot']:
            arr = getattr(self, arr_name)
            if arr.shape[0] < capacity:
                new_arr = np.zeros((capacity, self.M_total), dtype=arr.dtype)
                new_arr[:arr.shape[0]] = arr
                setattr(self, arr_name, new_arr)
        if len(self.spot_source_idx) < capacity:
            self.spot_source_idx = np.append(self.spot_source_idx, np.full(capacity - len(self.spot_source_idx), -1, dtype=np.int32))
        self._capacity = capacity

    def _add_fut_symbol(self, symbol):
        if symbol in self.sym_to_idx_fut:
            return self.sym_to_idx_fut[symbol]
        idx = self._num_fut
        self._num_fut += 1
        if self._num_fut > self._capacity:
            self._ensure_capacity(self._capacity * 2)
        self.symbols_fut.append(symbol)
        self.sym_to_idx_fut[symbol] = idx
        return idx

    def _add_global_symbol(self, symbol):
        if symbol in self.sym_to_idx_global:
            return self.sym_to_idx_global[symbol]
        idx = self._num_glob
        self._num_glob += 1
        if self._num_glob > self._capacity:
            self._ensure_capacity(self._capacity * 2)
        self.symbols_global.append(symbol)
        self.sym_to_idx_global[symbol] = idx
        self.spot_source_idx[idx] = -1
        return idx

    def _update_fut_freshness(self):
        now = time.time()
        N = self._num_fut
        if N == 0:
            return
        fresh = (now - self.last_seen_fut[:N]) <= self.data_max_age
        self.fut_fresh[:N] = fresh

    def _update_glob_freshness(self):
        now = time.time()
        N = self._num_glob
        if N == 0:
            return
        fut_fresh = np.zeros((N, self.M_total), dtype=np.bool_)
        for k in range(N):
            sym = self.symbols_global[k]
            fut_idx = self.sym_to_idx_fut.get(sym)
            if fut_idx is not None:
                fut_fresh[k] = (now - self.last_seen_fut[fut_idx]) <= self.data_max_age
        self.glob_fresh_fut[:N] = fut_fresh

    def _norm_sym(self, s):
        if not isinstance(s, str):
            return s
        return s.replace('_', '').replace('-', '').upper()

    def _dex_base(self, s):
        try:
            if not isinstance(s, str):
                return s
            if '_' in s:
                return s.split('_', 1)[1]
            return s
        except Exception:
            return s

    def _is_fresh(self, symbol, market, spot=False):
        key = (symbol, market + ('_spot' if spot else ''))
        ts = self.last_seen.get(key)
        if ts is None:
            return False
        return (time.time() - ts) <= self.data_max_age

    def _get_funding_interval(self, market, symbol, data=None):
        meta = self.extra_meta_per_market.get(market, {}).get(symbol, {})
        if isinstance(meta, dict):
            fi = meta.get('fundingInterval')
            if fi:
                try:
                    return int(fi)
                except:
                    pass
        return 8

    def _get_amount24(self, market, symbol, data=None):
        meta = self.extra_meta_per_market.get(market, {}).get(symbol, {})
        if isinstance(meta, dict):
            amount24 = meta.get('amount24')
            if amount24:
                try:
                    return float(amount24)
                except:
                    return 0
        return 0

    def _get_amount24_spot(self, market, symbol, data=None):
        meta = self.extra_meta_per_market.get(market, {}).get(symbol, {})
        if isinstance(meta, dict):
            amount24 = meta.get('amount24_spot')
            if amount24:
                try:
                    return float(amount24)
                except:
                    return 0
        return 0

    def _get_limits_usdt(self, market, symbol, data=None):
        meta = self.extra_meta_per_market.get(market, {}).get(symbol, {})
        if isinstance(meta, dict):
            limits_usdt = meta.get('limits_usdt')
            if limits_usdt:
                try:
                    return float(limits_usdt)
                except:
                    return 0
        return 0

    # ---------- Приём данных (без изменений) ----------
    def apply_collector_batch(self, msg):
        mname = msg.get('market')
        ts = msg.get('ts', time.time())
        if not mname:
            return

        if mname == 'Dex':
            with self.lock:
                data_spot = msg.get('data_spot') or {}
                meta_all = msg.get('market_meta') or {}
                for raw_sym, arr in data_spot.items():
                    try:
                        full_key = str(raw_sym).upper()
                        base_sym = self._dex_base(full_key)
                        meta_entry = meta_all.get(raw_sym) or meta_all.get(full_key) or {}
                        price = meta_entry.get('priceUsd', arr[1] if len(arr) > 1 else 0)
                        try:
                            price = float(price or 0)
                        except Exception:
                            price = 0.0
                        if price <= 0:
                            continue
                        self.data_spot_usdt[full_key] = [full_key, price, price]
                        self.data_spot_source[full_key] = mname
                        self.last_seen[(full_key, mname + '_spot')] = ts
                        self.dex_data[full_key] = price
                        self.dex_index.setdefault(base_sym, set()).add(full_key)
                        self.dex_changed.add(full_key)
                        self.bids_asks_dex_all.setdefault('Dex', {})[full_key] = [[price, price, ts]]
                    except Exception:
                        logger.exception("Error in Dex apply_collector_batch for %s", raw_sym)
                        continue

                if meta_all:
                    normalized = {}
                    for k, v in meta_all.items():
                        try:
                            normalized[str(k).upper()] = v
                        except Exception:
                            continue
                    self.dex_meta.update(normalized)
                    self.extra_meta_per_market.setdefault('Dex', {}).update(normalized)

                self.dirty = True
                self.dirty_markets.add('Dex')
            return

        with self.lock:
            for rec in msg.get('data_usdt', []):
                if not rec:
                    continue
                sym = self._norm_sym(rec[0])
                if sym not in self.data_usdt:
                    self.data_usdt[sym] = [0] * self.data_usdt_len_massiv
                    self.data_usdt[sym][0] = sym
                mapping = self.market.get(mname)
                if mapping:
                    row = self.data_usdt[sym]
                    try:
                        row[mapping[1]] = rec[1]
                        row[mapping[2]] = rec[2]
                        row[mapping[3]] = rec[3]
                        row[mapping[4]] = rec[4]
                        row[mapping[6]] = rec[6]
                    except Exception:
                        pass
                self.last_seen[(sym, mname)] = ts
                try:
                    bb = float(rec[2] or 0)
                    ba = float(rec[6] or 0)
                    if bb and ba:
                        self.bids_asks_futures_all.setdefault(mname, {})[sym] = [[ba, bb, ts]]
                except Exception:
                    pass

                m_idx = self.market_to_idx.get(mname)
                if m_idx is not None:
                    idx = self._add_fut_symbol(sym)
                    self.fut_funding[idx, m_idx] = float(rec[1] or 0)
                    self.fut_bid[idx, m_idx] = float(rec[2] or 0)
                    self.fut_ask[idx, m_idx] = float(rec[6] or 0)
                    self.fut_index[idx, m_idx] = float(rec[4] or 0)
                    self.last_seen_fut[idx, m_idx] = ts

            for raw_sym, arr in msg.get('data_spot', {}).items():
                norm_sym = self._norm_sym(raw_sym)
                try:
                    bid = float(arr[1] or 0)
                    ask = float(arr[2] or 0)
                    self.data_spot_usdt[norm_sym] = [norm_sym, bid, ask]
                except Exception:
                    self.data_spot_usdt[norm_sym] = [norm_sym, 0, 0]
                self.data_spot_source[norm_sym] = mname
                self.last_seen[(norm_sym, mname + '_spot')] = ts
                try:
                    if bid and ask:
                        self.bids_asks_spot_all.setdefault(mname, {})[norm_sym] = [[ask, bid, ts]]
                except Exception:
                    pass

            mm = msg.get('market_meta', {}) or {}
            if mm:
                normalized = {}
                for k, v in mm.items():
                    try:
                        normalized[self._norm_sym(k)] = v
                    except Exception:
                        continue
                self.extra_meta_per_market.setdefault(mname, {}).update(normalized)

                m_idx = self.market_to_idx.get(mname)
                if m_idx is not None:
                    for sym, meta in normalized.items():
                        idx = self.sym_to_idx_fut.get(sym)
                        if idx is not None:
                            fi = meta.get('fundingInterval')
                            if fi:
                                try:
                                    self.fut_interval[idx, m_idx] = int(fi)
                                except:
                                    pass
                            amt = meta.get('amount24')
                            if amt:
                                try:
                                    self.fut_amount24[idx, m_idx] = float(amt)
                                except:
                                    pass
                            lim = meta.get('limits_usdt')
                            if lim:
                                try:
                                    self.fut_limits[idx, m_idx] = float(lim)
                                except:
                                    pass
            self.dirty = True
            self.dirty_markets.add(mname)

    # ---------- Перестроение глобальной таблицы ----------
    def rebuild_spot_global(self):
        with self.lock:
            if not self.dirty:
                return

            old_symbols = list(self.symbols_global)
            old_idx_map = {sym: i for i, sym in enumerate(old_symbols)}
            old_N = self._num_glob

            old_glob_funding = self.glob_funding[:old_N].copy()
            old_glob_fut_bid = self.glob_fut_bid[:old_N].copy()
            old_glob_fut_ask = self.glob_fut_ask[:old_N].copy()
            old_glob_index = self.glob_index[:old_N].copy()
            old_glob_spot_ask = self.glob_spot_ask[:old_N].copy()
            old_glob_spot_bid = self.glob_spot_bid[:old_N].copy()
            old_glob_interval = self.glob_interval[:old_N].copy()
            old_glob_amount24 = self.glob_amount24[:old_N].copy()
            old_glob_limits = self.glob_limits[:old_N].copy()
            old_glob_amount24_spot = self.glob_amount24_spot[:old_N].copy()
            old_spot_source_idx = self.spot_source_idx[:old_N].copy()
            old_last_seen_spot = self.last_seen_spot[:old_N].copy()

            all_symbols = set(old_symbols) | set(self.data_usdt.keys()) | set(self.data_spot_usdt.keys())

            self.symbols_global = []
            self.sym_to_idx_global = {}
            self._num_glob = 0
            new_capacity = max(self._capacity, len(all_symbols))
            self._ensure_capacity(new_capacity)
            for arr_name in ['glob_funding', 'glob_fut_bid', 'glob_fut_ask', 'glob_index',
                             'glob_spot_ask', 'glob_spot_bid', 'glob_interval', 'glob_amount24',
                             'glob_limits', 'glob_amount24_spot', 'last_seen_spot']:
                arr = getattr(self, arr_name)
                arr[:] = 0
            self.spot_source_idx[:] = -1

            for sym in all_symbols:
                idx = self._add_global_symbol(sym)
                if sym in old_idx_map:
                    old_i = old_idx_map[sym]
                    self.glob_funding[idx, :] = old_glob_funding[old_i, :]
                    self.glob_fut_bid[idx, :] = old_glob_fut_bid[old_i, :]
                    self.glob_fut_ask[idx, :] = old_glob_fut_ask[old_i, :]
                    self.glob_index[idx, :] = old_glob_index[old_i, :]
                    self.glob_spot_ask[idx, :] = old_glob_spot_ask[old_i, :]
                    self.glob_spot_bid[idx, :] = old_glob_spot_bid[old_i, :]
                    self.glob_interval[idx, :] = old_glob_interval[old_i, :]
                    self.glob_amount24[idx, :] = old_glob_amount24[old_i, :]
                    self.glob_limits[idx, :] = old_glob_limits[old_i, :]
                    self.glob_amount24_spot[idx, :] = old_glob_amount24_spot[old_i, :]
                    self.spot_source_idx[idx] = old_spot_source_idx[old_i]
                    self.last_seen_spot[idx, :] = old_last_seen_spot[old_i, :]

            for sym in all_symbols:
                fut_sym = sym
                if sym not in self.data_usdt:
                    base_sym = self._dex_base(sym)
                    if base_sym in self.data_usdt:
                        fut_sym = base_sym
                    else:
                        continue
                fut_idx = self.sym_to_idx_fut.get(fut_sym)
                if fut_idx is None:
                    continue
                idx = self.sym_to_idx_global[sym]
                for m_idx in range(self.M_fut):
                    ts = self.last_seen_fut[fut_idx, m_idx]
                    if ts > 0:
                        self.glob_funding[idx, m_idx] = self.fut_funding[fut_idx, m_idx]
                        self.glob_fut_bid[idx, m_idx] = self.fut_bid[fut_idx, m_idx]
                        self.glob_fut_ask[idx, m_idx] = self.fut_ask[fut_idx, m_idx]
                        self.glob_index[idx, m_idx] = self.fut_index[fut_idx, m_idx]
                        self.glob_interval[idx, m_idx] = self.fut_interval[fut_idx, m_idx]
                        self.glob_amount24[idx, m_idx] = self.fut_amount24[fut_idx, m_idx]
                        self.glob_limits[idx, m_idx] = self.fut_limits[fut_idx, m_idx]

            for sym in all_symbols:
                if sym not in self.data_spot_usdt:
                    continue
                spot_row = self.data_spot_usdt[sym]
                source = self.data_spot_source.get(sym)
                if not source:
                    continue
                s_idx = self.market_to_idx.get(source)
                if s_idx is None:
                    continue
                ts = self.last_seen.get((sym, source + '_spot'))
                if ts:
                    idx = self.sym_to_idx_global[sym]
                    self.glob_spot_ask[idx, s_idx] = float(spot_row[2] or 0)
                    self.glob_spot_bid[idx, s_idx] = float(spot_row[1] or 0)
                    self.spot_source_idx[idx] = s_idx
                    self.last_seen_spot[idx, s_idx] = ts
                    amt_spot = self._get_amount24_spot(source, sym)
                    self.glob_amount24_spot[idx, s_idx] = amt_spot

            for sym in all_symbols:
                idx = self.sym_to_idx_global.get(sym)
                if idx is None:
                    continue
                for m_name in self.markets:
                    m_idx = self.market_to_idx.get(m_name)
                    if m_idx is None:
                        continue
                    key = (sym, m_name + '_spot')
                    ts = self.last_seen.get(key)
                    if ts is not None and ts > self.last_seen_spot[idx, m_idx]:
                        self.last_seen_spot[idx, m_idx] = ts

            self.dirty = False
            self.dirty_markets.clear()

    # ---------- DEX vs Futures ----------
    def search_dex_vs_futures(self):
        with self.lock:
            symbols_to_process = list(self.dex_changed)
            if not symbols_to_process:
                return
            for full_sym in symbols_to_process:
                try:
                    last_price = self.dex_data.get(full_sym)
                    if not last_price or last_price == 0:
                        self.dex_changed.discard(full_sym)
                        continue
                    if not self._is_fresh(full_sym, 'Dex', spot=True) and not self._is_fresh(full_sym, 'Dex', spot=False):
                        self.dex_changed.discard(full_sym)
                        continue
                    base_sym = self._dex_base(full_sym)
                    fut_row = self.data_usdt.get(base_sym)
                    if not fut_row:
                        self.dex_changed.discard(full_sym)
                        continue
                    for fut_market in self.markets:
                        if not self._is_fresh(base_sym, fut_market, spot=False):
                            continue
                        try:
                            bestBid_m2 = float(fut_row[self.market[fut_market][2]] or 0)
                            bestAsk_m2 = float(fut_row[self.market[fut_market][6]] or 0)
                        except Exception:
                            continue
                        if bestBid_m2 == 0 or bestAsk_m2 == 0:
                            continue
                        funding_rate = fut_row[self.market[fut_market][1]] if len(fut_row) > self.market[fut_market][1] else ''
                        fee_m2 = self.fees_fut.get(fut_market, self.fees.get(fut_market, 0.0))
                        fee_m1 = 0.0
                        predict_m2 = '-'
                        m1 = 'Dex'
                        m2 = fut_market

                        try:
                            diff = round(((float(bestBid_m2) / float(last_price)) - 1) * 100, 2)
                        except Exception:
                            diff = 0.0

                        amount24_m2 = self._get_amount24(fut_market, base_sym, fut_row)
                        limits_usdt_m2 = self._get_limits_usdt(fut_market, base_sym, fut_row)
                        amount24_spot = self._get_amount24_spot(fut_market, base_sym, fut_row)
                        fundingInterval_m2 = self._get_funding_interval(fut_market, base_sym, fut_row)
                        index_m2 = float(fut_row[self.market[fut_market][4]] or 0)

                        record = [
                            full_sym, m1, m2,
                            str(funding_rate), fundingInterval_m2, bestBid_m2,
                            fee_m1, fee_m2, predict_m2, str(diff),
                            index_m2,
                            str(bestBid_m2), bestAsk_m2, str(last_price),
                            amount24_m2, limits_usdt_m2, amount24_spot
                        ]
                        self.data_to_spot.append(record)
                        self.dex_pairs.append({
                            'symbol': full_sym,
                            'market2': m2,
                            'cex_bid': float(bestBid_m2 or 0),
                            'diff': float(diff or 0),
                            'volume24_cex': float(amount24_m2 or 0),
                            'cex_ask': float(bestAsk_m2 or 0),
                            'funding_rate': round(float(funding_rate or 0), 2),
                        })
                    self.dex_changed.discard(full_sym)
                except Exception:
                    logger.exception("search_dex_vs_futures error for %s", full_sym)

    def dex_write_redis(self, currentUpdated):
        try:
            import redis
            r = redis.Redis(host=os.getenv('REDIS_HOST', 'redis'),
                            port=int(os.getenv('REDIS_PORT', '6379')), db=2, decode_responses=True)
            out = []
            with self.lock:
                for p in list(self.dex_pairs):
                    try:
                        sym = p['symbol']
                        m2 = p['market2']
                        cex_bid = float(p['cex_bid'] or 0)
                        diff = float(p['diff'] or 0)
                        dex_price = float(self.dex_data.get(sym) or 0)
                        cex_ask = float(p['cex_ask'] or 0)
                        funding_rate = float(p['funding_rate'] or 0)
                        meta = self.dex_meta.get(sym) or {}
                        price_usd = meta.get('priceUsd') if meta.get('priceUsd') is not None else dex_price
                        try:
                            price_usd = float(price_usd or dex_price or 0)
                        except Exception:
                            price_usd = float(dex_price or 0)
                        cex_volume = float(p.get('volume24_cex') or 0)
                        if not cex_volume:
                            base_sym = self._dex_base(sym)
                            cex_volume = float(self._get_amount24(m2, base_sym) or 0)
                        out.append({
                            'symbol': sym,
                            'market2': m2,
                            'bid': float(cex_bid),
                            'priceUsd': price_usd,
                            'diff': float(diff),
                            'contract': meta.get('contract') or meta.get('pairAddress'),
                            'chain': meta.get('chain'),
                            'volume24': float(meta.get('volume24') or 0),
                            'volume24_cex': cex_volume,
                            'dexId': meta.get('dexId'),
                            'url': meta.get('url'),
                            'cex_ask': cex_ask,
                            'funding_rate': funding_rate,
                            'isUpdated': currentUpdated
                        })
                    except Exception:
                        logger.exception("dex_write_redis: skip bad pair %s", p)
                        continue
                self.dex_pairs.clear()
            if not out:
                try:
                    ts = time.time()
                    r.hset("Dex:meta", mapping={"last_try": ts, "last_count": 0})
                except Exception:
                    pass
                logger.info("Dex write skipped: no pairs to write")
                return
            r.set("Dex:all", orjson.dumps(out))
            try:
                r.hset("Dex:meta", mapping={"last_update": time.time(), "last_count": len(out)})
            except Exception:
                pass
            try:
                payload = orjson.dumps({"ts": time.time(), "count": len(out)})
                r.publish("Dex:update", payload)
            except Exception:
                logger.exception("dex_write_redis: publish failed")
            logger.info("Dex write complete: %d pair-records", len(out))
        except Exception:
            logger.exception("dex write to redis failed")

        # ---------- Формирование записей (исправлено) ----------

    @staticmethod
    def _to_compatible_number(value):
        """Возвращает int 0 если значение 0.0, иначе исходный float (для совместимости со старым кодом)."""
        if isinstance(value, float) and value == 0.0:
            return 0
        return value  # оставляем как float (даже целые числа будут с .0)

    def _build_fut_record(self, symbol, m1, m2, funding1, funding2, interval1, interval2,
                          bid1, bid2, fee1, fee2, index1, index2, ask1, ask2,
                          amount24_1, amount24_2, limits1, limits2):
        return [
            symbol, m1, m2,
            str(funding1), str(funding2),
            interval1, interval2,
            bid1, bid2,
            fee1, fee2, '-', '-',
            str(round(funding1 - funding2, 4)),
            index1, index2,
            ask1, ask2,
            self._to_compatible_number(amount24_1),
            self._to_compatible_number(amount24_2),
            self._to_compatible_number(limits1),
            self._to_compatible_number(limits2)
        ]

    def _build_spot_record(self, symbol, m1, m2, funding, interval, fut_bid,
                           fee_spot, fee_fut, predict, index, spot_bid,
                           fut_ask, spot_ask, amount24_fut, limits_fut, amount24_spot):
        return [
            symbol, m1, m2,
            str(funding), interval, fut_bid,
            fee_spot, fee_fut, predict,
            str(funding),
            index,
            str(spot_bid), fut_ask, str(spot_ask),
            self._to_compatible_number(amount24_fut),
            self._to_compatible_number(limits_fut),
            self._to_compatible_number(amount24_spot)
        ]

    # ---------- Поиск фьючерсных связок ----------
    def search_futures(self):
        with self.lock:
            self.data_to_db.clear()
            start_time = time.time()
            self._update_fut_freshness()

            N = self._num_fut
            if N == 0:
                logger.info("search_futures: no symbols")
                return

            funding = self.fut_funding
            bid = self.fut_bid
            ask = self.fut_ask
            index_corr = self.fut_index
            interval = self.fut_interval
            amount24 = self.fut_amount24
            limits = self.fut_limits
            fresh = self.fut_fresh[:N]
            symbols = self.symbols_fut
            M = self.M_fut
            market_names = self.markets
            fees = [self.fees_fut.get(m, 0.0) for m in market_names]

            # словарь (i,j) -> множество индексов запрещённых символов
            banned_by_pair = {}
            for sym, i, j in self.blacklist_fut_set:
                idx = self.sym_to_idx_fut.get(sym)
                if idx is not None:
                    banned_by_pair.setdefault((i, j), set()).add(idx)

            counter = 0
            # используем getitem для ускорения доступа к символам
            sym_getter = symbols.__getitem__

            for i in range(M):
                for j in range(i + 1, M):
                    mask = (fresh[:, i] & fresh[:, j] &
                            (bid[:N, i] > 0) & (ask[:N, i] > 0) &
                            (bid[:N, j] > 0) & (ask[:N, j] > 0))

                    banned = banned_by_pair.get((i, j))
                    if banned is not None:
                        valid = np.ones(N, dtype=bool)
                        for ban_idx in banned:
                            valid[ban_idx] = False
                        mask = mask & valid

                    k_idx = np.flatnonzero(mask)  # <-- быстрее, чем np.where(mask)[0]
                    if k_idx.size == 0:
                        continue

                    # одномерные срезы
                    fi = funding[k_idx, i]
                    fj = funding[k_idx, j]
                    bi = bid[k_idx, i]
                    bj = bid[k_idx, j]
                    ai = ask[k_idx, i]
                    aj = ask[k_idx, j]
                    ii = interval[k_idx, i]
                    ij = interval[k_idx, j]
                    idxi = index_corr[k_idx, i]
                    idxj = index_corr[k_idx, j]
                    amti = amount24[k_idx, i]
                    amtj = amount24[k_idx, j]
                    limi = limits[k_idx, i]
                    limj = limits[k_idx, j]

                    # символы через map – чуть быстрее list comprehension
                    k_symbols = list(map(sym_getter, k_idx))

                    for sym, f_i, f_j, b_i, b_j, a_i, a_j, int_i, int_j, idx_i, idx_j, amt_i, amt_j, lim_i, lim_j in zip(
                            k_symbols, fi, fj, bi, bj, ai, aj, ii, ij, idxi, idxj, amti, amtj, limi, limj):
                        amt_i_out = amt_i if amt_i != 0.0 else 0
                        amt_j_out = amt_j if amt_j != 0.0 else 0
                        lim_i_out = lim_i if lim_i != 0.0 else 0
                        lim_j_out = lim_j if lim_j != 0.0 else 0

                        if f_i >= f_j:
                            rec = [
                                sym, market_names[i], market_names[j],
                                str(f_i), str(f_j),
                                int_i, int_j,
                                b_i, b_j,
                                fees[i], fees[j], '-', '-',
                                str(round(f_i - f_j, 4)),
                                idx_i, idx_j,
                                a_i, a_j,
                                amt_i_out, amt_j_out,
                                lim_i_out, lim_j_out
                            ]
                        else:
                            rec = [
                                sym, market_names[j], market_names[i],
                                str(f_j), str(f_i),
                                int_j, int_i,
                                b_j, b_i,
                                fees[j], fees[i], '-', '-',
                                str(round(f_j - f_i, 4)),
                                idx_j, idx_i,
                                a_j, a_i,
                                amt_j_out, amt_i_out,
                                lim_j_out, lim_i_out
                            ]
                        self.data_to_db.append([rec])
                        counter += 1

            logger.info("search_futures done tasks=%d time=%.4f", counter, time.time() - start_time)

    # ---------- Поиск спотовых связок ----------
    def search_spot(self):
        with self.lock:
            self.data_to_spot.clear()
            start_time = time.time()
            if self.dirty:
                self.rebuild_spot_global()
            self._update_glob_freshness()

            N = self._num_glob
            if N == 0:
                logger.info("search_spot: no symbols")
                return

            now = time.time()
            funding = self.glob_funding
            fut_bid = self.glob_fut_bid
            fut_ask = self.glob_fut_ask
            index_corr = self.glob_index
            spot_ask = self.glob_spot_ask
            spot_bid = self.glob_spot_bid
            interval = self.glob_interval
            amount24 = self.glob_amount24
            limits = self.glob_limits
            amount24_spot = self.glob_amount24_spot
            fresh_fut = self.glob_fresh_fut[:N]
            last_seen_spot = self.last_seen_spot[:N]
            symbols = self.symbols_global
            M = self.M_fut
            market_names = self.markets
            fees_fut = [self.fees_fut.get(m, 0.0) for m in market_names]
            fees_spot = [self.fees.get(m, 0.0) for m in market_names]

            spot_fresh = (now - last_seen_spot) <= self.data_max_age

            banned_by_pair = {}
            for sym, i, j in self.blacklist_spot_set:
                idx = self.sym_to_idx_global.get(sym)
                if idx is not None:
                    banned_by_pair.setdefault((i, j), set()).add(idx)

            sym_getter = symbols.__getitem__
            counter = 0

            for s in range(M):
                for j in range(M):
                    mask = (spot_fresh[:, s] &
                            (spot_bid[:N, s] > 0) & (spot_ask[:N, s] > 0) &
                            fresh_fut[:, j] &
                            (fut_bid[:N, j] > 0) & (fut_ask[:N, j] > 0))

                    banned = banned_by_pair.get((s, j))
                    if banned is not None:
                        valid = np.ones(N, dtype=bool)
                        for ban_idx in banned:
                            valid[ban_idx] = False
                        mask = mask & valid

                    k_idx = np.flatnonzero(mask)
                    if k_idx.size == 0:
                        continue

                    spot_b = spot_bid[k_idx, s]
                    spot_a = spot_ask[k_idx, s]
                    fut_b = fut_bid[k_idx, j]
                    fut_a = fut_ask[k_idx, j]
                    fund = funding[k_idx, j]
                    inter = interval[k_idx, j]
                    idx_arr = index_corr[k_idx, j]
                    amt24 = amount24[k_idx, j]
                    lim = limits[k_idx, j]
                    amt24_spot_s = amount24_spot[k_idx, s]
                    k_symbols = list(map(sym_getter, k_idx))

                    fee_s = fees_spot[s]
                    fee_j = fees_fut[j]

                    for sym, f_j, int_j, b_j, a_j, idx_j, s_b, s_a, amt_j, lim_j, amt_s in zip(
                            k_symbols, fund, inter, fut_b, fut_a, idx_arr,
                            spot_b, spot_a, amt24, lim, amt24_spot_s):
                        amt_j_out = amt_j if amt_j != 0.0 else 0
                        lim_j_out = lim_j if lim_j != 0.0 else 0
                        amt_s_out = amt_s if amt_s != 0.0 else 0

                        rec = [
                            sym, market_names[s], market_names[j],
                            str(f_j), int_j, b_j,
                            fee_s, fee_j, '-',
                            str(f_j),
                            idx_j,
                            str(s_b), a_j, str(s_a),
                            amt_j_out, lim_j_out, amt_s_out
                        ]
                        self.data_to_spot.append(rec)
                        counter += 1

            logger.info("search_spot done tasks=%d time=%.4f", counter, time.time() - start_time)