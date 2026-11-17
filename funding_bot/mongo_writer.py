# mongo_writer.py
import os, time, pymongo, logging

logger = logging.getLogger("mongo_writer")
logging.basicConfig(level=logging.INFO)

MONGO_HOST = os.getenv('MONGO_HOST', 'mongodb')
MONGO_PORT = os.getenv('MONGO_PORT', '27017')

def mongo_writer_main(q):
    client = pymongo.MongoClient(f"mongodb://{MONGO_HOST}:{MONGO_PORT}")
    db = client['funding']
    fcol = db['futures']; scol = db['spot']
    BATCH = int(os.getenv('MONGO_BATCH_SIZE','500'))
    TIMEOUT = float(os.getenv('MONGO_BATCH_TIMEOUT','1.0'))
    docs = []
    last = time.time()
    while True:
        try:
            item = q.get(timeout=TIMEOUT)
            if item is None:
                break
            docs.append(item)
        except Exception:
            pass
        now = time.time()
        if len(docs) >= BATCH or (docs and (now - last) >= TIMEOUT):
            futures_docs = [d['doc'] for d in docs if d.get('type') == 'futures_doc']
            spot_docs = [d['doc'] for d in docs if d.get('type') == 'spot_doc']
            try:
                if futures_docs:
                    fcol.insert_many(futures_docs, ordered=False)
                    logger.info("Inserted %d futures docs", len(futures_docs))
            except Exception:
                logger.exception("mongo insert futures error")
            try:
                if spot_docs:
                    scol.insert_many(spot_docs, ordered=False)
                    logger.info("Inserted %d spot docs", len(spot_docs))
            except Exception:
                logger.exception("mongo insert spot error")
            docs = []
            last = now

if __name__ == '__main__':
    # debug run example (not used when aggregator spawns it)
    from multiprocessing import Queue
    q = Queue()
    mongo_writer_main(q)
