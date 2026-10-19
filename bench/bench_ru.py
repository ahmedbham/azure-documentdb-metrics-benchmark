"""RU benchmark for Azure Cosmos DB for MongoDB (RU-based). Same scenarios as bench_run.py, adds request charge (RU)."""
import sys, time, json, statistics, threading, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from bson import BSON
from common import client, DB
from pipelines import *

END = dt.datetime(2026, 10, 14, 15, 0, 0)
WINDOWS = {"1d": 1, "7d": 7, "30d": 30}
WARM = int(sys.argv[1]) if len(sys.argv) > 1 else 5
tl = threading.local()
results, metrics_out = [], {}


def cols():
    """One single-connection client per thread so getLastRequestStatistics hits the same connection."""
    if not hasattr(tl, "db"):
        tl.db = client(maxPoolSize=1, socketTimeoutMS=3600000, serverSelectionTimeoutMS=60000)[DB]
    return tl.db


def last_ru():
    try:
        return float(cols().command("getLastRequestStatistics").get("RequestCharge", 0))
    except Exception:
        return 0.0


def timed(name, pipe, **kw):
    """Returns (seconds incl. retries, output, error, RU of successful attempt, throttled retries)."""
    t = time.perf_counter()
    throttled = 0
    while True:
        try:
            out = list(cols()[name].aggregate(pipe, maxTimeMS=600000, **kw))
            ru = last_ru()
            return time.perf_counter() - t, out, None, ru, throttled
        except Exception as e:
            code = getattr(e, "code", None)
            if code in (16500, 429) and throttled < 200:
                throttled += 1
                time.sleep(0.3)
                continue
            return time.perf_counter() - t, [], str(e)[:250], last_ru(), throttled


def rec(name, window, secs, out, err=None, extra=None):
    r = {"scenario": name, "window": window, "seconds": round(secs, 3), "out_docs": len(out),
         "out_bytes": sum(len(BSON.encode(d)) for d in out) if out else 0, "error": err}
    if extra: r.update(extra)
    results.append(r)
    print(json.dumps(r), flush=True)


def stats(v):
    v = sorted(v)
    return {"min": round(v[0], 3), "median": round(statistics.median(v), 3), "max": round(v[-1], 3), "n": len(v)}


def window(n): return END - dt.timedelta(days=n), END


run_start = dt.datetime.utcnow().isoformat() + "Z"

for label, partner, typ in [("all", None, None), ("partner=AVAILITY", "AVAILITY", None), ("type=Portal 270", None, "Portal 270")]:
    for w, n in WINDOWS.items():
        s, e = window(n)
        for nm, col, fn in [("summary", "TransactionMetricSummary", summary_query_pipeline),
                            ("buckets", "MetricBucketsHourly", bucket_query_pipeline)]:
            times, rus, last, err, thr = [], [], None, None, 0
            for i in range(WARM + 1):
                secs, out, err, ru, th = timed(col, fn(s, e, partner, typ))
                times.append(secs); rus.append(ru); thr += th
                if out: last = out
            rec(f"{nm}[{label}]", w, times[0], last or [], err,
                {"cold_s": round(times[0], 3), "warm": stats(times[1:]), "ru_median": round(statistics.median(rus[1:]), 2),
                 "ru_cold": round(rus[0], 2), "throttled_retries": thr})
            if label == "all" and last:
                metrics_out[f"{nm}_{w}"] = dashboard_metrics(last[0])

for w, n in WINDOWS.items():
    s, e = window(n)
    secs, out, err, ru, th = timed("TransactionLogs", raw_pipeline(s, e))
    rec("raw_customer_single", w, secs, out, err, {"ru": round(ru, 2), "throttled_retries": th})
    if out: metrics_out[f"raw_{w}"] = dashboard_metrics(out[0])
    secs, out, err, ru, th = timed("TransactionLogs", raw_compact_pipeline(s, e))
    rec("raw_compact_pdf_exp2", w, secs, out, err, {"ru": round(ru, 2), "throttled_retries": th})

for w, n in WINDOWS.items():
    s, e = window(n)
    slices, t = [], s
    while t < e:
        slices.append((t, min(t + dt.timedelta(hours=2), e))); t += dt.timedelta(hours=2)
    t0 = time.perf_counter()
    errs = tot = nbytes = thr = 0
    ru_sum = 0.0

    def one(sl):
        secs, out, err, ru, th = timed("TransactionLogs", raw_pipeline(*sl))
        return out, err, ru, th
    with ThreadPoolExecutor(12) as ex:
        for out, err, ru, th in ex.map(one, slices):
            ru_sum += ru; thr += th
            if err: errs += 1
            elif out:
                nbytes += len(BSON.encode(out[0]))
                tot += out[0]["summary"][0]["transactionCount"] if out[0]["summary"] else 0
    rec("raw_sliced_2h_parallel12", w, time.perf_counter() - t0, [], f"{errs} slice errors" if errs else None,
        {"slices": len(slices), "txn_count_merged": tot, "out_bytes": nbytes, "ru": round(ru_sum, 1), "throttled_retries": thr})

run_end = dt.datetime.utcnow().isoformat() + "Z"
print("TILES", json.dumps(metrics_out, indent=1))
json.dump({"run_start": run_start, "run_end": run_end, "results": results, "tiles": metrics_out},
          open("/opt/app/results_ru.json", "w"), indent=1, default=str)
print("DONE", run_start, run_end)
