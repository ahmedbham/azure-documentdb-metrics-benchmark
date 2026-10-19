import sys, time, json, statistics, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from bson import BSON
from common import client, DB
from pipelines import *

END = dt.datetime(2026, 10, 14, 15, 0, 0)
WINDOWS = {"1d": 1, "7d": 7, "30d": 30}
db = client(maxPoolSize=32, socketTimeoutMS=3600000)[DB]
raw, S, B = db["TransactionLogs"], db["TransactionMetricSummary"], db["MetricBucketsHourly"]
results = []
metrics_out = {}


def timed(col, pipe, **kw):
    t = time.perf_counter()
    try:
        out = list(col.aggregate(pipe, allowDiskUse=True, maxTimeMS=3000000, **kw))
        return time.perf_counter() - t, out, None
    except Exception as e:
        return time.perf_counter() - t, [], str(e)[:200]


def rec(name, window, secs, out, err=None, extra=None):
    r = {"scenario": name, "window": window, "seconds": round(secs, 3),
         "out_docs": len(out), "out_bytes": sum(len(BSON.encode(d)) for d in out) if out else 0, "error": err}
    if extra: r.update(extra)
    results.append(r)
    print(json.dumps(r), flush=True)
    return r


def stats(vals):
    v = sorted(vals)
    return {"min": round(v[0], 3), "median": round(statistics.median(v), 3),
            "p95": round(v[min(len(v) - 1, int(round(0.95 * (len(v) - 1))))], 3), "max": round(v[-1], 3), "n": len(v)}


def window(n): return END - dt.timedelta(days=n), END


run_start = dt.datetime.utcnow().isoformat() + "Z"

# ---- precomputed: repeated runs ----
for label, partner, typ in [("all", None, None), ("partner=AVAILITY", "AVAILITY", None),
                            ("type=Portal 270", None, "Portal 270")]:
    for w, n in WINDOWS.items():
        s, e = window(n)
        for nm, col, fn in [("summary", S, summary_query_pipeline), ("buckets", B, bucket_query_pipeline)]:
            times, last = [], None
            for i in range(11):
                secs, out, err = timed(col, fn(s, e, partner, typ))
                times.append(secs)
                if out: last = out
            st = stats(times[1:])
            rec(f"{nm}[{label}]", w, times[0], last or [], err,
                {"cold_s": round(times[0], 3), "warm": st})
            if label == "all" and last:
                metrics_out[f"{nm}_{w}"] = dashboard_metrics(last[0])

# ---- raw: customer query as one request ----
for w, n in WINDOWS.items():
    s, e = window(n)
    secs, out, err = timed(raw, raw_pipeline(s, e))
    rec("raw_customer_single", w, secs, out, err)
    if out: metrics_out[f"raw_{w}"] = dashboard_metrics(out[0])
    secs, out, err = timed(raw, raw_compact_pipeline(s, e))
    rec("raw_compact_pdf_exp2", w, secs, out, err)

# ---- raw: customer workaround, 2h slices in parallel, merged client side ----
for w, n in WINDOWS.items():
    s, e = window(n)
    slices = []
    t = s
    while t < e:
        slices.append((t, min(t + dt.timedelta(hours=2), e))); t += dt.timedelta(hours=2)
    for par in (12,):
        t0 = time.perf_counter()
        errs, tot, nbytes = 0, 0, 0

        def one(sl):
            secs, out, err = timed(raw, raw_pipeline(*sl))
            return out, err
        with ThreadPoolExecutor(par) as ex:
            for out, err in ex.map(one, slices):
                if err: errs += 1
                elif out:
                    nbytes += len(BSON.encode(out[0]))
                    tot += out[0]["summary"][0]["transactionCount"] if out[0]["summary"] else 0
        rec(f"raw_sliced_2h_parallel{par}", w, time.perf_counter() - t0, [], f"{errs} slice errors" if errs else None,
            {"slices": len(slices), "txn_count_merged": tot, "out_bytes": nbytes})

# ---- explain ----
for nm, col, pipe in [("raw_1d", raw, raw_pipeline(*window(1))), ("summary_30d", S, summary_query_pipeline(*window(30))),
                      ("buckets_30d", B, bucket_query_pipeline(*window(30)))]:
    try:
        ex = db.command("aggregate", col.name, pipeline=pipe, explain=True)
        print("EXPLAIN", nm, json.dumps(ex, default=str)[:1500])
    except Exception as e:
        print("EXPLAIN", nm, "n/a", str(e)[:200])

run_end = dt.datetime.utcnow().isoformat() + "Z"
print("TILES", json.dumps(metrics_out, indent=1))
json.dump({"run_start": run_start, "run_end": run_end, "results": results, "tiles": metrics_out},
          open("/opt/app/results.json", "w"), indent=1, default=str)
print("DONE", run_start, run_end)
