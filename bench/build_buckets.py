"""Rebuild only MetricBucketsHourly from the existing TransactionMetricSummary."""
import time, json, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from common import client, DB
from pipelines import bucket_build_pipeline

START = dt.datetime(2026, 9, 14, 15, 0, 0)
END = dt.datetime(2026, 10, 14, 16, 0, 0)
db = client(maxPoolSize=16, socketTimeoutMS=3600000)[DB]
S, B = db["TransactionMetricSummary"], db["MetricBucketsHourly"]
B.drop()
db.create_collection("MetricBucketsHourly")
B.create_index([("hour", 1), ("type", 1), ("partner", 1), ("outputStatus", 1), ("outputType", 1),
                ("failed", 1), ("defaulted", 1), ("range", 1)], unique=True, name="bucket_key")
B.create_index([("hour", 1)], name="hour_1")
B.create_index([("partner", 1), ("hour", 1)], name="partner_hour")
B.create_index([("type", 1), ("hour", 1)], name="type_hour")


def retry(fn):
    for _ in range(300):
        try:
            return fn()
        except Exception as e:
            if getattr(e, "code", None) in (16500, 429):
                time.sleep(0.5)
                continue
            raise
    raise RuntimeError("too many throttles")


def build_day(d):  # hourly windows: day-sized output exceeds Cosmos's 512K-char SQL limit
    retry(lambda: list(S.aggregate(bucket_build_pipeline(d, d + dt.timedelta(hours=1)), maxTimeMS=3000000)))


days, d = [], START
while d < END:
    days.append(d); d += dt.timedelta(hours=1)
t0 = time.time()
with ThreadPoolExecutor(4) as ex:
    list(ex.map(build_day, days))
secs = time.time() - t0
print(json.dumps({"bucket_build_s": secs, "summary_docs": retry(lambda: S.count_documents({})),
                  "bucket_docs": retry(lambda: B.count_documents({})), "dbStats": db.command("dbStats")}, default=str))

