# aggregator.py
import asyncio
import os
import struct
import pickle
import time
import multiprocessing
multiprocessing.set_start_method('fork', force=True)
from core.market import MarketState
from datetime import datetime, timedelta
import redis
import pymongo
import logging
import json
from collections import defaultdict
import orjson

logger = logging.getLogger("aggregator")
logging.basicConfig(level=logging.INFO)

SOCKET_PATH = os.getenv('SOCKET_PATH', '/tmp/funding.sock')
SEARCH_INTERVAL = float(os.getenv('SEARCH_INTERVAL', '2.0'))
BIDS_WAIT = int(os.getenv('BIDS_WAIT', '10'))

REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))

MONGO_HOST = os.getenv('MONGO_HOST', 'mongodb')
MONGO_PORT = os.getenv('MONGO_PORT', '27017')

state = MarketState()

# Redis clients will be created inside write functions with appropriate db
redis_client_default = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

# Mongo
mongo_client = pymongo.MongoClient(f"mongodb://{MONGO_HOST}:{MONGO_PORT}")
mongo_db = mongo_client['funding']
futures_coll = mongo_db['futures']
spot_coll = mongo_db['spot']

# queue for mongo writer process
mongo_q = multiprocessing.Queue(maxsize=40000)

def mongo_writer_proc(q, mongo_host=MONGO_HOST, mongo_port=MONGO_PORT):
    client = pymongo.MongoClient(f"mongodb://{mongo_host}:{mongo_port}")
    db = client['funding']
    fcol = db['futures']; scol = db['spot']
    BATCH = int(os.getenv('MONGO_BATCH_SIZE','500'))
    TIMEOUT = float(os.getenv('MONGO_BATCH_TIMEOUT','1.0'))
    docs = []
    last_flush = time.time()
    while True:
        try:
            item = q.get(timeout=TIMEOUT)
            if item is None:
                break
            docs.append(item)
        except Exception:
            pass
        now = time.time()
        if len(docs) >= BATCH or (docs and (now - last_flush) >= TIMEOUT):
            futures_docs = [d['doc'] for d in docs if d.get('type') == 'futures_doc']
            spot_docs = [d['doc'] for d in docs if d.get('type') == 'spot_doc']
            try:
                if futures_docs:
                    fcol.insert_many(futures_docs, ordered=False)
                    logger.info("Inserted %d futures docs to Mongo", len(futures_docs))
            except Exception:
                logger.exception("mongo insert futures error")
            try:
                if spot_docs:
                    scol.insert_many(spot_docs, ordered=False)
                    logger.info("Inserted %d spot docs to Mongo", len(spot_docs))
            except Exception:
                logger.exception("mongo insert spot error")
            docs = []
            last_flush = now

# ----------------------------
# Redis write helpers (exactly по твоему формату)
# ----------------------------
def spot_futures_write_redis(currentUpdated, data_to_spot, full_history):
    """
    Writes all spot->futures records into Redis DB=1 as JSON under key "SpotFutures:all".
    full_history: dict[market] -> dict[symbol] -> [h1,h3,h7,h30] (strings or numbers)
    """
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=1, decode_responses=True)
    spot_futures_data = []
    counter = 0
    for data in data_to_spot:
        if data is None:
            continue
        try:
            # data expected: array as in original
            data_spread_in = round(((float(data[5]) / float(data[13])) - 1) * 100, 2)
            # data_spread_out = round(((float(data[12]) / float(data[11])) - 1) * 100, 2)
            # if abs(data_spread_in) > 10000 or abs(data_spread_out) > 10000:
            #     continue
            if abs(data_spread_in) > 10000:
                continue
        except Exception as e:
            # keep behavior: skip bad rows
            continue

        # ensure full_history has market dicts
        m2 = data[2]
        mh = full_history.get(m2, {})

        record = {
            'symbol': data[0],
            'market1': data[1],
            'market2': data[2],
            'market2funding': float(data[3]),
            'market2time': float(data[4]),
            'market2bid': float(data[5]),
            'market1fee': float(data[6]),
            'market2fee': float(data[7]),
            'market2predict': data[8],
            'spread': float(data[9]),
            'isNew': 'yes',
            'isUpdated': currentUpdated,
            'isDeviation2': float(data[10]),
            'spot1bid': float(data[11]),
            'market2ask': float(data[12]),
            'spot1ask': float(data[13]),
            'm2h1': mh.get(data[0], [''] * 4)[0],
            'm2h3': mh.get(data[0], [''] * 4)[1],
            'm2h7': mh.get(data[0], [''] * 4)[2],
            'm2h30': mh.get(data[0], [''] * 4)[3],
            'amount24m2': float(data[14]),
            'limitsm2': float(data[15]),
            'amount24spot': float(data[16]),
        }

        spot_futures_data.append(record)

    # write once
    try:
        r.set("SpotFutures:all", orjson.dumps(spot_futures_data))
        try:
            payload = orjson.dumps({"ts": time.time(), "count": len(spot_futures_data)})
            r.publish("SpotFutures:update", payload)
        except Exception:
            logger.exception("spot_futures_write_redis: publish failed")
        logger.info("Spot/Futures write complete: %d records.", len(spot_futures_data))
    except Exception:
        logger.exception("SpotFutures write to redis failed")

def futures_write_redis(currentUpdated, data_to_db, full_history):
    """
    Writes all futures spreads into Redis DB=0 as JSON under key "Spreads:all".
    data_to_db expected: list of items where data = item[0] (as in your original code).
    """
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    spreads_data = []

    for item in data_to_db:
        try:
            data = item[0]
        except Exception:
            continue

        try:
            spread_in = round(((float(data[7]) / float(data[17])) - 1) * 100, 2)
          #  spread_out = round(((float(data[16]) / float(data[8])) - 1) * 100, 2)
          #   if abs(spread_in) > 10000 or abs(spread_out) > 10000:
          #       continue
            if abs(spread_in) > 10000:
                continue
        except Exception:
            continue

        m1 = data[1]; m2 = data[2]
        mh1 = full_history.get(m1, {})
        mh2 = full_history.get(m2, {})

        spread = {
            'symbol': data[0],
            'market1': data[1],
            'market2': data[2],
            'market1funding': float(data[3]),
            'market2funding': float(data[4]),
            'market1time': float(data[5]),
            'market2time': float(data[6]),
            'market1bid': float(data[7]),
            'market2bid': float(data[8]),
            'market1fee': float(data[9]),
            'market2fee': float(data[10]),
            'market1predict': data[11],
            'market2predict': data[12],
            'spread': float(data[13]),
            'isNew': 'yes',
            'isUpdated': currentUpdated,
            'isDeviation1': float(data[14]),
            'isDeviation2': float(data[15]),
            'market1ask': float(data[16]),
            'market2ask': float(data[17]),
            'm1h1': mh1.get(data[0], [''] * 4)[0],
            'm1h3': mh1.get(data[0], [''] * 4)[1],
            'm1h7': mh1.get(data[0], [''] * 4)[2],
            'm1h30': mh1.get(data[0], [''] * 4)[3],
            'm2h1': mh2.get(data[0], [''] * 4)[0],
            'm2h3': mh2.get(data[0], [''] * 4)[1],
            'm2h7': mh2.get(data[0], [''] * 4)[2],
            'm2h30': mh2.get(data[0], [''] * 4)[3],
            'amount24m1': float(data[18]),
            'amount24m2': float(data[19]),
            'limitsm1': float(data[20]),
            'limitsm2': float(data[21])
        }

        spreads_data.append(spread)

    # write once
    try:
        r.set("Spreads:all", orjson.dumps(spreads_data))
        try:
            payload = orjson.dumps({"ts": time.time(), "count": len(spreads_data)})
            r.publish("Spreads:update", payload)
        except Exception:
            logger.exception("futures_write_redis: publish failed")
        logger.info("Spreads write complete: %d spreads.", len(spreads_data))
    except Exception:
        logger.exception("Spreads write to redis failed")

# ----------------------------
# Socket handling & main loops (unchanged behavior)
# ----------------------------
async def handle_client(reader, writer):
    try:
        hdr = await reader.readexactly(4)
        length = struct.unpack('>I', hdr)[0]
        data = await reader.readexactly(length)
        msg = pickle.loads(data)
        state.apply_collector_batch(msg)
    except Exception:
        logger.exception("handle_client error")
    finally:
        try:
            writer.close(); await writer.wait_closed()
        except Exception:
            pass

async def start_unix_server(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except:
        pass
    server = await asyncio.start_unix_server(handle_client, path=path)
    logger.info("Aggregator listening on %s", path)
    async with server:
        await server.serve_forever()

async def periodic_search():
    await asyncio.sleep(1.0)
    # full_history placeholder: market -> { symbol: [h1,h3,h7,h30] }
    # We'll default to empty dicts so code doesn't crash; you can replace with a real loader.
    full_history = defaultdict(dict)

    while True:
        logger.info("Start searching aggregator")
        t0 = time.time()
        try:
            state.rebuild_spot_global()
            # NEW: search dex vs futures first to create spot->futures entries for DEX updates
            try:
                state.search_dex_vs_futures()
            except Exception:
                logger.exception("dex vs futures search error")
            state.search_futures()
            state.search_spot()
        except Exception:
            logger.exception("search error")
        with state.lock:
            db_rows = list(state.data_to_db)
            spot_rows = list(state.data_to_spot)
            state.data_to_db.clear()
            state.data_to_spot.clear()

        # currentUpdated - use single flag from state or timestamp
        currentUpdated = getattr(state, 'currentUpdated', 'updated2')

        # write aggregated results to Redis in bulk (db0 & db1), using your functions
        try:
            # for safety, ensure full_history has empty dicts for each market
            for m in state.market.keys():
                if m not in full_history:
                    full_history[m] = {}
            futures_write_redis(currentUpdated, db_rows, full_history)
            spot_futures_write_redis(currentUpdated, spot_rows, full_history)
            try:
                state.dex_write_redis(currentUpdated)
            except Exception:
                logger.exception("dex redis write error")

            # Сохраняем контракты BinanceAlpha для построения ссылок
            try:
                ba_meta = state.extra_meta_per_market.get('BinanceAlpha', {})
                if ba_meta:
                    contracts_map = {}
                    for sym, meta in ba_meta.items():
                        if isinstance(meta, dict) and meta.get('contract_address'):
                            contracts_map[sym] = {
                                'contract_address': meta['contract_address'],
                                'chain_name': meta.get('chain_name', 'bsc'),
                                'alpha_id': meta.get('alpha_id', ''),
                            }
                    if contracts_map:
                        redis_client_default.set("BinanceAlpha:contracts", orjson.dumps(contracts_map))
            except Exception:
                logger.exception("BinanceAlpha contracts write error")
        except Exception:
            logger.exception("redis bulk write error")

        elapsed = time.time() - t0
        await asyncio.sleep(max(0.01, SEARCH_INTERVAL - elapsed))

async def minute_bids_snapshot_loop():
    await asyncio.sleep(1.0)
    while True:
        now = datetime.now()
        rounded_time = now.replace(second=0, microsecond=0)
        with state.lock:
            state.timer_time_to_add = rounded_time
        await asyncio.sleep(BIDS_WAIT)
        futures_docs = []; spot_docs = []
        with state.lock:
            for market, symbols in state.bids_asks_futures_all.items():
                for symbol, data in list(symbols.items()):
                    if data:
                        try:
                            ask, bid, _ = data[0]
                            futures_docs.append({"exchange_name": market, "symbol": symbol, "datetime": rounded_time, "ask": ask, "bid": bid})
                            del state.bids_asks_futures_all[market][symbol]
                        except Exception:
                            logger.exception("Error processing futures bids_asks for %s %s", market, symbol)
            for market, symbols in state.bids_asks_spot_all.items():
                for symbol, data in list(symbols.items()):
                    if data:
                        try:
                            ask, bid, _ = data[0]
                            spot_docs.append({"exchange_name": market, "symbol": symbol, "datetime": rounded_time, "ask": ask, "bid": bid})
                            del state.bids_asks_spot_all[market][symbol]
                        except Exception:
                            logger.exception("Error processing spot bids_asks for %s %s", market, symbol)
            for market, symbols in state.bids_asks_dex_all.items():
                for symbol, data in list(symbols.items()):
                    if not data:
                        continue
                    try:
                        ask, bid, ts = data[0]
                        price = float(ask or bid or 0)
                        if price <= 0:
                            del state.bids_asks_dex_all[market][symbol]
                            continue

                        doc = {
                            "exchange_name": "Dex",
                            "symbol": symbol,
                            "datetime": rounded_time,
                            "ask": price,
                            "bid": price
                        }
                        spot_docs.append(doc)
                        state.dex_last_written[symbol] = price
                        del state.bids_asks_dex_all[market][symbol]
                    except Exception:
                        logger.exception("Error processing DEX snapshot for %s", symbol)
                        continue
        try:
            for d in futures_docs:
                mongo_q.put_nowait({"type":"futures_doc", "doc": d})
            for d in spot_docs:
                mongo_q.put_nowait({"type":"spot_doc", "doc": d})
            logger.info("Queued %d futures docs and %d spot docs for minute %s", len(futures_docs), len(spot_docs), rounded_time.isoformat())
        except Exception:
            logger.exception("mongo_q put error")
        now2 = datetime.now()
        next_min = (rounded_time + timedelta(minutes=1))
        sleep_dur = (next_min - now2).total_seconds()
        if sleep_dur > 0:
            await asyncio.sleep(sleep_dur)
        else:
            await asyncio.sleep(1)

def main():
    mw = multiprocessing.Process(target=mongo_writer_proc, args=(mongo_q,))
    mw.start()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(asyncio.gather(start_unix_server(SOCKET_PATH), periodic_search(), minute_bids_snapshot_loop()))
    except KeyboardInterrupt:
        logger.info("Aggregator stopped by user")
    finally:
        try:
            mongo_q.put(None)
        except Exception:
            pass
        mw.join(timeout=2)

if __name__ == '__main__':
    main()
