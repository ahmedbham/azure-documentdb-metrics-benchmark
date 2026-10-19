import time, json, datetime as dt
from common import client, DB
from pipelines import *

db = client(maxPoolSize=1, socketTimeoutMS=600000)[DB]
raw = db["TransactionLogs"]
print("indexes", [i["name"] for i in raw.list_indexes()])
s = dt.datetime(2026, 10, 14, 14, 0); e = dt.datetime(2026, 10, 14, 15, 0)


def go(label, fn):
    t = time.time()
    try:
        out = fn()
        print(label, "OK %.2fs" % (time.time() - t), "RU", db.command("getLastRequestStatistics").get("RequestCharge"), str(out)[:150], flush=True)
    except Exception as ex:
        print(label, "ERR %.2fs" % (time.time() - t), str(ex)[:300].replace("\n", " "), flush=True)


go("raw_1h", lambda: [len(str(d)) for d in raw.aggregate(raw_pipeline(s, e), maxTimeMS=300000)])
go("raw_1d", lambda: [len(str(d)) for d in raw.aggregate(raw_pipeline(e - dt.timedelta(days=1), e), maxTimeMS=300000)])
db["TransactionMetricSummary"].drop()
go("summary_build_1h", lambda: list(raw.aggregate(summary_build_pipeline(s, e), maxTimeMS=300000)))
go("summary_count", lambda: db["TransactionMetricSummary"].estimated_document_count())
