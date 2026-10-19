"""Build TransactionMetricSummary (per transaction) and MetricBucketsHourly (hourly additive) collections."""
import sys, time, json, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from common import client, DB
from pipelines import summary_build_pipeline, bucket_build_pipeline

START = dt.datetime(2026, 9, 14, 15, 0, 0)
END = dt.datetime(2026, 10, 14, 16, 0, 0)

db = client(maxPoolSize=16, socketTimeoutMS=3600000)[DB]
raw = db["TransactionLogs"]
if "--drop" in sys.argv:
    db["TransactionMetricSummary"].drop(); db["MetricBucketsHourly"].drop()
    db.create_collection("TransactionMetricSummary"); db.create_collection("MetricBucketsHourly")

# indexes up-front so $merge on _id / bucket key is efficient
db["MetricBucketsHourly"].create_index([("hour", 1), ("type", 1), ("partner", 1), ("outputStatus", 1), ("outputType", 1),
                                        ("failed", 1), ("defaulted", 1), ("range", 1)], unique=True, name="bucket_key")
db["MetricBucketsHourly"].create_index([("hour", 1)], name="hour_1")
db["MetricBucketsHourly"].create_index([("partner", 1), ("hour", 1)], name="partner_hour")
db["MetricBucketsHourly"].create_index([("type", 1), ("hour", 1)], name="type_hour")


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


def build_hour(h):
    retry(lambda: list(raw.aggregate(summary_build_pipeline(h, h + dt.timedelta(hours=1)), allowDiskUse=True, maxTimeMS=3000000)))
    return h


hours = []
h = START
while h < END:
    hours.append(h); h += dt.timedelta(hours=1)

t0 = time.time()
with ThreadPoolExecutor(8) as ex:
    for i, _ in enumerate(ex.map(build_hour, hours)):
        if i % 100 == 0:
            print("summary hours done", i, "%.0fs" % (time.time() - t0), flush=True)
summary_secs = time.time() - t0
S = db["TransactionMetricSummary"]
print("SUMMARY build: %.1fs, docs=%d" % (summary_secs, S.count_documents({})), flush=True)

t0 = time.time()
S.create_index([("startTime", 1)], name="startTime_1")
S.create_index([("partner", 1), ("startTime", 1)], name="partner_startTime")
S.create_index([("type", 1), ("startTime", 1)], name="type_startTime")
print("summary indexes: %.1fs" % (time.time() - t0), flush=True)


def build_bucket_day(d):
    retry(lambda: list(S.aggregate(bucket_build_pipeline(d, d + dt.timedelta(days=1)), allowDiskUse=True, maxTimeMS=3000000)))


days = []
d = START
while d < END:
    days.append(d); d += dt.timedelta(days=1)
t0 = time.time()
with ThreadPoolExecutor(4) as ex:
    list(ex.map(build_bucket_day, days))
bucket_secs = time.time() - t0
B = db["MetricBucketsHourly"]
print("BUCKET build: %.1fs, docs=%d" % (bucket_secs, B.count_documents({})), flush=True)
st = db.command("dbStats")
print(json.dumps({"summary_build_s": summary_secs, "bucket_build_s": bucket_secs,
                  "summary_docs": S.count_documents({}), "bucket_docs": B.count_documents({}), "dbStats": st}, default=str))

