"""Generate synthetic TransactionLogs from the two customer samples and load into DocumentDB.

usage: python datagen_load.py <target_event_docs> [workers] [--drop]
"""
import os, sys, random, copy, datetime as dt, time
from multiprocessing import Pool
from bson import ObjectId
from common import client, load_samples, DB

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAYS = 30
END = dt.datetime(2026, 10, 14, 15, 0, 0)
START = END - dt.timedelta(days=DAYS)

TYPES = [  # (type, share, partners, event_supplement)
    ("Portal 270", 0.35, ["PWEBPORTAL"], "270 Portal"),
    ("Real Time 270 SOAP", 0.40, ["276PASSPORT", "AVAILITY", "CHANGEHC", "WAYSTAR", "OPTUM", "TRIZETTO"], "SOAP 270"),
    ("Real Time 276 SOAP", 0.15, ["AVAILITY", "CHANGEHC", "WAYSTAR", "OPTUM"], "SOAP 276"),
    ("Real Time 270 MIME", 0.10, ["TRIZETTO", "OPTUM", "276PASSPORT"], "MIME 270"),
]
P_DEFAULT = 0.0003
P_FAILED = 0.004
P_NO_LAST = 0.01
P_BIG_PAYLOAD = 0.05


def prep_pools(samples):
    first_pool, last_pool, prog_small, prog_big = [], [], [], []
    for s in samples:
        for d in s:
            fl = d["data"]["event_flag"]
            if fl == "First":
                first_pool.append(d)
            elif fl == "Last":
                last_pool.append(d)
            elif len(str(d)) > 20000:
                prog_big.append(d)
            else:
                prog_small.append(d)
    return first_pool, last_pool, prog_small, prog_big


def duration_s(r):
    x = r.random()
    if x < 0.55: return r.uniform(0.3, 10)
    if x < 0.80: return r.uniform(10, 20)
    if x < 0.93: return r.uniform(20, 45)
    if x < 0.975: return r.uniform(45, 60)
    return r.uniform(60, 240)


def make_txn_docs(r, pools, t0):
    first_pool, last_pool, prog_small, prog_big = pools
    typ, _, partners, supp = r.choices(TYPES, weights=[t[1] for t in TYPES])[0]
    partner = r.choice(partners)
    tid = "AZ-%s-%d" % (t0.strftime("%Y%m%d%H%M%S%f")[:16], r.randrange(10**9, 10**10))
    n = r.randint(7, 15)
    dur = duration_s(r)
    offs = sorted([0.0] + [r.uniform(0, dur) for _ in range(n - 2)] + [dur])
    has_last = r.random() > P_NO_LAST
    failed = r.random() < P_FAILED
    default = r.random() < P_DEFAULT
    docs = []
    for i in range(n):
        if i == 0:
            d = copy.deepcopy(r.choice(first_pool))
        elif i == n - 1:
            d = copy.deepcopy(r.choice(last_pool))
        else:
            big = bool(prog_big) and r.random() < P_BIG_PAYLOAD / max(n - 2, 1)
            d = copy.deepcopy(r.choice(prog_big if big else prog_small))
        t = t0 + dt.timedelta(seconds=offs[i])
        x = d["data"]
        x["transaction_id"] = tid
        x["transmission_id"] = tid
        d["type"] = typ
        d["time"] = t
        d["timestamp"] = t
        d["id"] = "AZ-Event-%s-%d" % (t.strftime("%Y%m%d%H%M%S%f")[:16], r.randrange(10**9, 10**10))
        d["_id"] = ObjectId(ObjectId.from_datetime(t).binary[:4] + os.urandom(8))
        x["partner"] = partner if i in (0, n - 1) else ""
        if i == 0:
            x["event_supplement"] = supp
        if i == n - 1:
            if has_last:
                x["transaction_output_type"] = "Default 271" if default else "271"
                x["event_supplement"] = "Default 271" if default else "SOAP 271"
                x["transaction_stauts"] = r.choice(["270 Local TP", "271 Delivered", "Local"])
            else:
                x["event_flag"] = "Progress"
                x["event"] = "Sending Response"
                x.pop("transaction_stauts", None)
        elif i > 0:
            x.pop("transaction_stauts", None)
        if failed and i == n - 1:
            x["event"] = "Failed Process"
        docs.append(d)
    return docs


def safe_insert(col, docs):
    """insert_many that retries throttled (429 / code 16500) writes, for RU-based accounts."""
    from pymongo.errors import BulkWriteError, OperationFailure
    while docs:
        try:
            col.insert_many(docs, ordered=False)
            return
        except BulkWriteError as e:
            errs = e.details.get("writeErrors", [])
            bad = [x for x in errs if x.get("code") not in (16500, 429, 11000)]
            if bad:
                raise
            docs = [docs[x["index"]] for x in errs if x.get("code") in (16500, 429)]
            time.sleep(0.5)
        except OperationFailure as e:
            if e.code not in (16500, 429):
                raise
            time.sleep(1)


def gen_slice(args):
    wid, s, e, target = args
    r = random.Random(1000 + wid)
    pools = prep_pools(load_samples(BASE))
    col = client(maxPoolSize=4)[DB]["TransactionLogs"]
    span = (e - s).total_seconds()
    inserted, buf = 0, []
    while inserted < target:
        ts = []
        for _ in range(500):
            t = s + dt.timedelta(seconds=r.uniform(0, span))
            h = t.hour
            if not (14 <= h <= 23 or h <= 1) and r.random() > 0.45:
                continue
            ts.append(t)
        for t in sorted(ts):
            buf.extend(make_txn_docs(r, pools, t))
            if len(buf) >= 1500:
                safe_insert(col, buf)
                inserted += len(buf)
                buf = []
                if inserted >= target:
                    break
    if buf:
        safe_insert(col, buf)
        inserted += len(buf)
    return wid, inserted


if __name__ == "__main__":
    total = int(sys.argv[1])
    workers = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 8
    col = client()[DB]["TransactionLogs"]
    if "--drop" in sys.argv:
        col.drop()
    step = (END - START) / workers
    per = total // workers
    jobs = [(i, START + step * i, START + step * (i + 1), per) for i in range(workers)]
    t = time.time()
    with Pool(workers) as p:
        for wid, n in p.imap_unordered(gen_slice, jobs):
            print("worker", wid, "inserted", n, "elapsed %.0fs" % (time.time() - t), flush=True)
    print("count", col.estimated_document_count(), "elapsed %.0fs" % (time.time() - t))

