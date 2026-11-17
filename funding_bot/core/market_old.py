# core/market.py
import os
import time
import threading
import logging
import orjson

logger = logging.getLogger("core.market")
logging.basicConfig(level=logging.INFO)

class MarketState:
    def __init__(self):
        try:
            self.data_max_age = float(os.getenv('DATA_MAX_AGE', '15.0'))
        except Exception:
            self.data_max_age = 10.0

        self.data_usdt = {}
        self.data_spot_usdt = {}
        self.data_spot_source = {}
        self.data_spot_usdt_global = {}
        self.data_to_db = []
        self.data_to_spot = []
        self.bids_asks_futures_all = {}
        self.bids_asks_spot_all = {}
        self.bids_asks_dex_all = {}  # NEW: per-minute snapshot for dex
        self.dex_data = {}  # symbol -> last price (float), key = full dex key (e.g. ETH_TONUSDT)
        self.dex_meta = {}  # symbol -> meta dict from dexscreener (keys are full dex keys)
        self.dex_changed = set()  # symbols updated on DEX since last scan (full dex keys)
        self.dex_pairs = []
        self.dex_last_written = {}  # symbol -> last price written to mongo (float)
        self.dex_index = {}  # base_sym (TONUSDT) -> set(full_keys)  (helpful if needed)

        self.last_seen = {}
        self.extra_meta_per_market = {}
        self.timer_time_to_add = None

        # optimization flags
        self.dirty = False  # пометка, что пришли новые данные и нужно перестроить глобальные объединения
        self.dirty_markets = set()  # какие рынки поменялись (необязательно, но полезно для логов/диагностики)



        self.markets = ['Bybit', 'Mexc', 'Kucoin', 'Gateio', 'Bitget', 'Huobi', 'Okx',
                        'Binance', 'BingX', 'BitMart', 'Ourbit', 'Hyperliquid', 'LBank', 'Aster', 'XT', 'CoinEx', 'WEEX', 'Phemex']
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
        }
        self.market_spot = {
            'Bybit': [1, 2],
            'Mexc': [3, 4],
            'Kucoin': [5, 6],
            'Gateio': [7, 8],
            'Bitget': [9, 10],
            'Huobi': [11, 12],
            'Okx': [13, 14],
            'Binance': [15, 16],
            'BingX': [17, 18],
            'BitMart': [19, 20],
            'Ourbit': [21, 22],
            'Hyperliquid': [23, 24],
            'LBank': [25, 26],
            'Aster': [27, 28],
            'XT': [29, 30],
            'CoinEx': [31, 32],
            'WEEX': [33, 34],
            'Phemex': [35, 36],
        }
        self.data_usdt_len_massiv = 127
        self.data_to_spot_len_massiv = 37
        self.len_data_usdt = 129

        self.fees = {
            'Bybit': 0.1, 'Mexc': 0.1, 'Kucoin': 0.1, 'Gateio': 0.2, 'Bitget': 0.1,
            'Huobi': 0.2, 'Okx': 0.1, 'Binance': 0.1, 'BingX': 0.1, 'BitMart': 0.1,
            'Ourbit': 0, 'Hyperliquid': 0.045, 'LBank': 0.1, 'Aster': 0.035, 'XT': 0.2,
            'CoinEx': 0.2, 'WEEX': 0.1, 'Phemex': 0.1,
        }

        self.fees_fut = {
            'Bybit': 0.1,  # compute_bybit_meta used 0.1
            'Mexc': 0.02,  # compute_mexc_meta used 0.02
            'Kucoin': 0.06,  # kucoin defaults ~0.06
            'Gateio': 0.05,  # gateio used 0.05 in market_meta
            'Bitget': 0.06,  # bitget used 0.06
            'Huobi': 0.05,  # huobi code used 0.05
            'Okx': 0.05,  # okx used 0.05
            'Binance': 0.05,  # binance used 0.05
            'BingX': 0.05,  # bingx used 0.05
            'BitMart': 0.06,  # fallback
            'Ourbit': 0.04,  # ourbit meta used 0.04
            'Hyperliquid': 0.1,  # hyperliquid earlier used 0.1 in our adapter
            'LBank': 0.06,  # LBank old code returned 0.06
            'Aster': 0.035,
            'XT': 0.06,
            'CoinEx': 0.05,
            'WEEX': 0.08,
            'Phemex': 0.06,
        }

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

    # normalize symbols to canonical form (used for exchanges' futures/spot symbols)
    def _norm_sym(self, s):
        if not isinstance(s, str):
            return s
        return s.replace('_', '').replace('-', '').upper()

    # dex helper: extract base symbol (remove chain prefix if exists)
    # e.g. 'ETH_TONUSDT' -> 'TONUSDT', 'TONUSDT' -> 'TONUSDT'
    def _dex_base(self, s):
        try:
            if not isinstance(s, str):
                return s
            if '_' in s:
                return s.split('_', 1)[1]
            return s
        except Exception:
            return s

    # freshness helper
    def _is_fresh(self, symbol, market, spot=False):
        key = (symbol, market + ('_spot' if spot else ''))
        ts = self.last_seen.get(key)
        if ts is None:
            return False
        return (time.time() - ts) <= self.data_max_age

    def apply_collector_batch(self, msg):
        mname = msg.get('market')
        ts = msg.get('ts', time.time())
        if not mname:
            return

        # === DEX branch: keep full dex keys (CHAIN_SYMUSDT) intact and also keep base mapping ===
        if mname == 'Dex':
            with self.lock:
                data_spot = msg.get('data_spot') or {}
                meta_all = msg.get('market_meta') or {}
                ts = msg.get('ts', time.time())

                for raw_sym, arr in data_spot.items():
                    try:
                        # raw_sym is expected to be like "ETH_TONUSDT" (as we now produce in dexscreener)
                        full_key = str(raw_sym).upper()
                        # determine base symbol (after underscore) - this matches futures keys like "TONUSDT"
                        base_sym = self._dex_base(full_key)

                        # meta may contain priceUsd, else arr[1]
                        meta_entry = meta_all.get(raw_sym) or meta_all.get(full_key) or {}
                        price = meta_entry.get('priceUsd', arr[1] if len(arr) > 1 else 0)
                        try:
                            price = float(price or 0)
                        except Exception:
                            price = 0.0

                        if price <= 0:
                            continue

                        # store DEX spot entry keyed by full_key (preserve chain prefix)
                        self.data_spot_usdt[full_key] = [full_key, price, price]

                        # mark source market and freshness for the full_key
                        self.data_spot_source[full_key] = mname
                        self.last_seen[(full_key, mname + '_spot')] = ts

                        # dex specific structures
                        self.dex_data[full_key] = price
                        self.dex_index.setdefault(base_sym, set()).add(full_key)
                        self.dex_changed.add(full_key)

                        # write minute snapshot for dex
                        self.bids_asks_dex_all.setdefault('Dex', {})[full_key] = [[price, price, ts]]
                    except Exception:
                        logger.exception("Error in Dex apply_collector_batch for %s", raw_sym)
                        continue

                # update dex_meta and also extra_meta_per_market['Dex'] using FULL keys (don't strip underscore)
                if meta_all:
                    normalized = {}
                    for k, v in meta_all.items():
                        try:
                            normalized[str(k).upper()] = v
                        except Exception:
                            continue
                    # dex_meta is separate store keyed by full dex keys
                    self.dex_meta.update(normalized)
                    # keep extra_meta_per_market for 'Dex' too (if other code relies on it)
                    self.extra_meta_per_market.setdefault('Dex', {}).update(normalized)

                # отметим rebuild
                self.dirty = True
                self.dirty_markets.add('Dex')
            return

        # === Normal (non-dex) markets processing (futures/spot collectors) ===
        with self.lock:
            for rec in msg.get('data_usdt', []):
                if not rec:
                    continue
                raw_sym = rec[0]
                sym = self._norm_sym(raw_sym)   # futures keys are normalized to e.g. TONUSDT
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
                # mark last seen for futures (key is base futures sym)
                self.last_seen[(sym, mname)] = ts

                # per-batch minute snapshot (use rec values)
                try:
                    bb = float(rec[2] or 0)
                    ba = float(rec[6] or 0)
                    if bb and ba:
                        self.bids_asks_futures_all.setdefault(mname, {})[sym] = [[ba, bb, ts]]
                except Exception:
                    pass

            # Spot entries for regular CEX spot collectors (unrelated to Dex) - keep old behaviour
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

            # mark rebuild needed
            self.dirty = True
            self.dirty_markets.add(mname)

    def rebuild_spot_global(self):
        """
        Robust rebuild:
        - Start from the existing global table to preserve previously-known values.
        - For every symbol present in either data_usdt or data_spot_usdt:
            * merge fresher per-market futures fields when last_seen for that (symbol,market) exists
            * set spot bid/ask only for the source_market if spot last_seen exists
        - Use last_seen timestamps to avoid overwriting newer values with older ones.

        Important: support DEX keys with chain prefix (e.g. ETH_TONUSDT).
        If there is a DEX-key, but no direct futures entry for that full key, we try to use base symbol
        (the part after first underscore) to pull futures fields.
        """
        with self.lock:
            if not self.dirty:
                return

            now = time.time()

            # start from previous global to preserve fields that are still valid
            base_global = {}
            # shallow copy previous global rows (so we don't mutate original objects in-place)
            for k, v in (self.data_spot_usdt_global or {}).items():
                base_global[k] = v.copy()

            new_global = {}

            # union of symbols
            all_symbols = set(self.data_usdt.keys()) | set(self.data_spot_usdt.keys()) | set(base_global.keys())

            for symbol in all_symbols:
                # start from base if present (preserve old merged row), else new empty
                if symbol in base_global:
                    data = base_global[symbol].copy()
                else:
                    data = [0] * (self.len_data_usdt + 1)
                    data[0] = symbol

                # Determine base_sym for potential futures lookup (handles dex full keys)
                base_sym = self._dex_base(symbol)

                # if we have a futures row for the (symbol OR base_sym), merge per-market fields using last_seen
                fut_row = self.data_usdt.get(symbol)
                if not fut_row:
                    fut_row = self.data_usdt.get(base_sym)

                if fut_row:
                    for mname in self.market.keys():
                        # check last_seen for either full-symbol (unlikely for futures) or base_sym
                        ts_fut = self.last_seen.get((symbol, mname)) or self.last_seen.get((base_sym, mname))
                        if not ts_fut:
                            # no known value from this market — skip
                            continue
                        mapping = self.market[mname]
                        # copy all mapping indices for this market from fut_row if they exist and non-zero
                        for i in range(1, len(mapping)):
                            idx = mapping[i]
                            if idx < len(data) and idx < len(fut_row):
                                val = fut_row[idx]
                                if val not in (0, None):
                                    # overwrite only if we have ts_fut (we do) — this keeps fresher values
                                    data[idx] = val

                # spot: if spot exists, write ask/bid into SOURCE_MARKET slots only,
                # but only if we have spot last_seen for that source_market
                spot_row = self.data_spot_usdt.get(symbol)
                if spot_row:
                    source_market = self.data_spot_source.get(symbol)
                    source_ts = self.last_seen.get((symbol, (source_market + '_spot') if source_market else None))
                    if source_market and source_market in self.market and source_ts:
                        try:
                            idx_ask = self.market[source_market][5]
                            idx_bid = self.market[source_market][7]
                            if idx_ask < len(data):
                                data[idx_ask] = spot_row[2]
                            if idx_bid < len(data):
                                data[idx_bid] = spot_row[1]
                            # make sure spot last_seen key exists (we already set it in apply_collector_batch)
                            # nothing else to do
                        except Exception:
                            logger.exception("rebuild_spot_global: error writing spot for %s @ %s", symbol,
                                             source_market)

                new_global[symbol] = data

            # atomic swap
            self.data_spot_usdt_global = new_global

            # mark rebuilt
            self.dirty = False
            self.dirty_markets.clear()

    # copy spot-only coins into global table; propagate source_ts
    def add_spot_only_coins(self):
        with self.lock:
            for symbol, spot_data in self.data_spot_usdt.items():
                source_market = self.data_spot_source.get(symbol)
                if not source_market:
                    continue

                if symbol not in self.data_spot_usdt_global:
                    data = [0] * (self.len_data_usdt + 1)
                    data[0] = symbol
                    self.data_spot_usdt_global[symbol] = data
                data = self.data_spot_usdt_global[symbol]

                # Только в source_market ставим bid/ask
                try:
                    idx_ask = self.market[source_market][5]
                    idx_bid = self.market[source_market][7]
                    data[idx_ask] = spot_data[2]
                    data[idx_bid] = spot_data[1]
                    ts = self.last_seen.get((symbol, source_market + '_spot'))
                    if ts:
                        self.last_seen[(symbol, source_market + '_spot')] = ts
                except Exception:
                    continue

    def search_dex_vs_futures(self):
        """
        Process only DEX symbols that were updated since last run (self.dex_changed).
        For each updated DEX symbol (full_key like 'ETH_TONUSDT'), compare its price with all fresh futures markets
        and append entries to self.data_to_spot (one per futures market).
        We write computed spread into index 9 of the entry (so downstream writer uses it).

        Important: base_sym = part after '_' (TONUSDT) is used to lookup futures rows in self.data_usdt.
        The output 'symbol' in the created entry is the full dex symbol (e.g. 'ETH_TONUSDT').
        """
        with self.lock:
            # snapshot which symbols changed and clear as we process
            symbols_to_process = list(self.dex_changed)
            if not symbols_to_process:
                return
            # we'll remove processed ones after loop
            for full_sym in symbols_to_process:
                try:
                    last_price = self.dex_data.get(full_sym)
                    if not last_price or last_price == 0:
                        # nothing to compare
                        self.dex_changed.discard(full_sym)
                        continue

                    # require dex data to be fresh (check using full_sym key)
                    if not self._is_fresh(full_sym, 'Dex', spot=True) and not self._is_fresh(full_sym, 'Dex', spot=False):
                        # stale dex value; skip
                        self.dex_changed.discard(full_sym)
                        continue

                    # FUT: find futures row by base symbol (part after the first underscore)
                    base_sym = self._dex_base(full_sym)
                    fut_row = self.data_usdt.get(base_sym)
                    if not fut_row:
                        # no matching futures data for this base symbol
                        self.dex_changed.discard(full_sym)
                        continue

                    # for each futures market check freshness and create entry
                    for fut_market in self.markets:
                        # is futures data fresh? use base_sym for freshness check
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
                        fundingInterval_m2 = self._get_funding_interval(fut_market, base_sym, fut_row)
                        fee_m2 = self.fees_fut.get(fut_market, self.fees.get(fut_market, 0.0))
                        fee_m1 = 0.0
                        predict_m2 = '-'
                        m1 = 'Dex'
                        m2 = fut_market

                        # compute percent diff = (futBid / dexPrice - 1) * 100
                        try:
                            diff = round(((float(bestBid_m2) / float(last_price)) - 1) * 100, 2)
                        except Exception:
                            diff = 0.0

                        # get cex 24h volume (reuse helper) - use base_sym here
                        amount24_m2 = self._get_amount24(fut_market, base_sym, fut_row)  # float
                        limits_usdt_m2 = self._get_limits_usdt(fut_market, base_sym, fut_row)
                        amount24_spot = self._get_amount24_spot(fut_market, base_sym, fut_row)
                        # Build entry with same layout as finder_spot expects.
                        # Add amount24_m2 and limits_usdt_m2 at the end so length matches finder_spot.
                        try:



                                # cex bid — bestBid_m2, dex price — last_price, diff already computed
                                self.dex_pairs.append({
                                    'symbol': full_sym,
                                    'market2': m2,
                                    'cex_bid': float(bestBid_m2 or 0),
                                    'diff': float(diff or 0),
                                    'volume24_cex': float(amount24_m2 or 0),
                                    'cex_ask': float(bestAsk_m2 or 0),
                                    'funding_rate': round(float(funding_rate or 0), 2),
                                })

                        except Exception:
                            continue

                    # processed this dex symbol (do not reprocess until next dex update)
                    self.dex_changed.discard(full_sym)
                except Exception:
                    logger.exception("search_dex_vs_futures error for %s", full_sym)

    def dex_write_redis(self, currentUpdated):
        """
        Безопасная запись: не перезаписываем Redis пустым списком.
        Пишем:
          - Dex:all  — только если есть записи
          - Dex:last_update — unix timestamp последней записи (включая count)
          - Dex:last_count  — число записей в последней успешной записи
        """
        try:
            import redis, json, os, time
            r = redis.Redis(host=os.getenv('REDIS_HOST', 'redis'),
                            port=int(os.getenv('REDIS_PORT', '6379')), db=2, decode_responses=True)
            out = []
            with self.lock:
                # Сформировать out из self.dex_pairs
                for p in list(self.dex_pairs):
                    try:
                        sym = p.get('symbol')  # full_sym like ETH_TONUSDT
                        m2 = p.get('market2')
                        cex_bid = float(p.get('cex_bid') or 0)
                        diff = float(p.get('diff') or 0)
                        dex_price = float(self.dex_data.get(sym) or 0)
                        cex_ask = float(p.get('cex_ask') or 0)
                        funding_rate = float(p.get('funding_rate') or 0)
                        meta = self.dex_meta.get(sym) or {}
                        price_usd = meta.get('priceUsd') if meta.get('priceUsd') is not None else dex_price
                        try:
                            price_usd = float(price_usd or dex_price or 0)
                        except Exception:
                            price_usd = float(dex_price or 0)

                        # cex volume: prefer stored value on pair, fallback to market helper using base_sym
                        cex_volume = float(p.get('volume24_cex') or 0)
                        if not cex_volume:
                            base_sym = self._dex_base(sym)
                            cex_volume = float(self._get_amount24(m2, base_sym, self.data_usdt.get(base_sym) or []) or 0)

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
                        # пропускаем невалидные пары, но не падаем
                        logger.exception("dex_write_redis: skip bad pair %s", p)
                        continue

                # Очистим self.dex_pairs чтобы не дублировать
                self.dex_pairs.clear()

            # Если out пуст — НЕ перезаписываем ключ Dex:all
            if not out:
                # логируем и обновим вспомогательный ключ о попытке записи
                try:
                    ts = time.time()
                    r.hset("Dex:meta", mapping={"last_try": ts, "last_count": 0})
                except Exception:
                    pass
                logger.info("Dex write skipped: no pairs to write (will not overwrite existing Redis key).")
                return

            # Иначе — сериализуем и записываем
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

    # funding interval helper (meta first, then fallback)
    def _get_funding_interval(self, market, symbol, data):
        meta = self.extra_meta_per_market.get(market, {}).get(symbol, {})
        if isinstance(meta, dict):
            fi = meta.get('fundingInterval')
            if fi:
                try:
                    return int(fi)
                except:
                    pass
        try:
            idx = self.market[market][3]
            if idx < len(data):
                v = data[idx]
                if v:
                    try:
                        return int(v)
                    except:
                        pass
        except Exception:
            pass
        return 8

    def _get_amount24(self, market, symbol, data):
        meta = self.extra_meta_per_market.get(market, {}).get(symbol, {})
        if isinstance(meta, dict):
            amount24 = meta.get('amount24')
            if amount24:
                try:
                    return float(amount24)
                except:
                    return 0
        return 0

    def _get_amount24_spot(self, market, symbol, data):
        meta = self.extra_meta_per_market.get(market, {}).get(symbol, {})
        if isinstance(meta, dict):
            amount24 = meta.get('amount24_spot')
            if amount24:
                try:
                    return float(amount24)
                except:
                    return 0
        return 0

    def _get_limits_usdt(self, market, symbol, data):
        meta = self.extra_meta_per_market.get(market, {}).get(symbol, {})
        if isinstance(meta, dict):
            limits_usdt = meta.get('limits_usdt')
            if limits_usdt:
                try:
                    return float(limits_usdt)
                except:
                    return 0
        return 0

    # finder for futures pairs
    def finder(self, market1, market2, data):
        try:
            m1 = market1; m2 = market2
            symbol = data[0]

            if not self._is_fresh(symbol, m1, spot=False) or not self._is_fresh(symbol, m2, spot=False):
                return

            try:
                funding_rate_m1 = data[self.market[m1][1]]
            except Exception:
                funding_rate_m1 = None
            try:
                funding_rate_m2 = data[self.market[m2][1]]
            except Exception:
                funding_rate_m2 = None

            fundingInterval_m1 = self._get_funding_interval(m1, symbol, data)
            fundingInterval_m2 = self._get_funding_interval(m2, symbol, data)
            amount24_m1 = self._get_amount24(m1, symbol, data)
            amount24_m2 = self._get_amount24(m2, symbol, data)
            limits_usdt_m1 = self._get_limits_usdt(m1, symbol, data)
            limits_usdt_m2 = self._get_limits_usdt(m2, symbol, data)

            fee_m1 = self.fees_fut.get(m1, self.fees.get(m1))
            fee_m2 = self.fees_fut.get(m2, self.fees.get(m2))
            predict_m1 = '-'
            predict_m2 = '-'

            bestBid_m1 = data[self.market[m1][2]]
            bestAsk_m1 = data[self.market[m1][6]]
            index_m1 = data[self.market[m1][4]]

            bestBid_m2 = data[self.market[m2][2]]
            bestAsk_m2 = data[self.market[m2][6]]
            index_m2 = data[self.market[m2][4]]

            not_blacklist = (symbol, frozenset([m1, m2])) not in self.blacklist_futures

            if not_blacklist:
                try:
                    if (bestBid_m1 is None and (m1 == 'Gateio')) or (bestAsk_m1 is None and (m1 == 'Gateio')) or \
                       (bestBid_m2 is None and (m2 == 'Gateio')) or (bestAsk_m2 is None and (m2 == 'Gateio')) or \
                       (float(self._safe_access(data, self.market[m1][2])) == 0 or float(self._safe_access(data, self.market[m2][2])) == 0) or \
                       (float(self._safe_access(data, self.market[m1][6])) == 0 or float(self._safe_access(data, self.market[m2][6])) == 0):
                        return
                    else:
                        create_message = [
                            symbol, m1, m2,
                            str(float(funding_rate_m1) + 0.0) if funding_rate_m1 is not None else '',
                            str(float(funding_rate_m2) + 0.0) if funding_rate_m2 is not None else '',
                            fundingInterval_m1, fundingInterval_m2,
                            data[self.market[m1][2]], data[self.market[m2][2]],
                            fee_m1, fee_m2, predict_m1, predict_m2,
                            str(float(round(float(str(funding_rate_m1 or 0)) - float(str(funding_rate_m2 or 0)), 4)) + 0.0),
                            str(float(data[self.market[m1][4]]) + 0.0), str(float(data[self.market[m2][4]]) + 0.0),
                            data[self.market[m1][6]], data[self.market[m2][6]],
                            amount24_m1, amount24_m2,
                            limits_usdt_m1, limits_usdt_m2
                        ]
                        self.data_to_db.append([create_message])
                except Exception:
                    logger.exception("finder inner exception for %s %s %s", symbol, m1, m2)
        except Exception:
            logger.exception("finder outer exception")

    # finder for spot -> futures pairs (restore original ordering)
    def finder_spot(self, market1, market2, data):
        try:
            m1 = market1; m2 = market2
            symbol = data[0]

            if not self._is_fresh(symbol, m1, spot=True) or not self._is_fresh(symbol, m2, spot=False):
                return

            fundingInterval_m2 = self._get_funding_interval(m2, symbol, data)
            amount24_m2 = self._get_amount24(m2, symbol, data)
            amount24_spot = self._get_amount24_spot(m1, symbol, data)
            limits_usdt_m2 = self._get_limits_usdt(m2, symbol, data)

            fee_m2 = self.fees_fut.get(m2, self.fees.get(m2))
            predict_m2 = '-'

            fut_row = self.data_usdt.get(symbol)

            if fut_row:
                funding_rate = fut_row[self.market[m2][1]]
                bestBid_m2 = fut_row[self.market[m2][2]]
                bestAsk_m2 = fut_row[self.market[m2][6]]
                index_m2 = fut_row[self.market[m2][4]]
            else:
                # If symbol is a DEX full_key (e.g. ETH_TONUSDT), fut_row might be present for base_sym
                base_sym = self._dex_base(symbol)
                fut_row_fallback = self.data_usdt.get(base_sym)
                if fut_row_fallback:
                    funding_rate = fut_row_fallback[self.market[m2][1]]
                    bestBid_m2 = fut_row_fallback[self.market[m2][2]]
                    bestAsk_m2 = fut_row_fallback[self.market[m2][6]]
                    index_m2 = fut_row_fallback[self.market[m2][4]]
                else:
                    funding_rate = data[self.market[m2][1]]
                    bestBid_m2 = data[self.market[m2][2]]
                    bestAsk_m2 = data[self.market[m2][6]]
                    index_m2 = data[self.market[m2][4]]

            # === ORIGINAL: ask = data[market1][5], bid = data[market1][7] ===
            ask = data[self.market[market1][5]]
            bid = data[self.market[market1][7]]

            if (fee_m2 is not None and fundingInterval_m2 is not None and ask is not None and bid is not None and float(ask) != 0 and float(bid) != 0):
                not_blacklist = (symbol, frozenset([m1, m2])) not in self.blacklist_spot
                if not_blacklist:
                    if (bestBid_m2 is None and (m2 == 'Gateio')) or (bestAsk_m2 is None and (m2 == 'Gateio')) or (float(bestBid_m2) == 0) or (float(bestAsk_m2) == 0):
                        return
                    else:
                        fee_m1 = self.fees.get(m1, 0)
                        self.data_to_spot.append(
                            [data[0], m1, m2, str(float(funding_rate) + 0.0), fundingInterval_m2, bestBid_m2,
                             fee_m1, fee_m2, predict_m2, str(float(funding_rate) + 0.0), str(float(index_m2) + 0.0),
                             str(data[self.market[m1][7]]), bestAsk_m2, str(data[self.market[m1][5]]),
                             amount24_m2, limits_usdt_m2, amount24_spot]
                        )
        except Exception:
            logger.exception("finder_spot exception")

    def search_futures(self):
        start_time = time.time(); counter_tasks = 0
        market_indices = [(market, self.market[market][1]) for market in self.markets]
        try:
            for data in list(self.data_usdt.values()):
                for i, (market1, index1) in enumerate(market_indices):
                    try:
                        value1 = data[index1]
                    except Exception:
                        value1 = 0
                    for j in range(i + 1, len(market_indices)):
                        market2, index2 = market_indices[j]
                        try:
                            value2 = data[index2]
                        except Exception:
                            value2 = 0
                        if value1 >= value2:
                            self.finder(market1, market2, data)
                        else:
                            self.finder(market2, market1, data)
                        counter_tasks += 1
        except Exception:
            logger.exception("search_futures error")
        logger.info("search_futures done tasks=%d time=%.4f", counter_tasks, time.time()-start_time)

    def search_spot(self):
        start_time = time.time(); counter_tasks = 0
        self.add_spot_only_coins()
        market_indices = [(market, self.market[market][1]) for market in self.markets]
        try:
            for data in list(self.data_spot_usdt_global.values()):
                for spot_market, spot_index in market_indices:
                    try:
                        # ORIGINAL: index 5 -> ASK, index 7 -> BID
                        ask_index = self.market[spot_market][5]
                        bid_index = self.market[spot_market][7]
                        if bid_index >= len(data) or ask_index >= len(data):
                            continue
                        if data[ask_index] == 0 or data[bid_index] == 0:
                            continue
                        for futures_market, futures_index in market_indices:
                            self.finder_spot(spot_market, futures_market, data)
                            counter_tasks += 1
                    except Exception:
                        continue
        except Exception:
            logger.exception("search_spot error")
        logger.info("search_spot done tasks=%d time=%.4f", counter_tasks, time.time()-start_time)

    def _safe_access(self, row, idx):
        try:
            return row[idx]
        except Exception:
            return 0
