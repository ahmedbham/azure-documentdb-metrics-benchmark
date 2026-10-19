"""Post-load fix-up (data was loaded before the failed-flag placement was corrected) + indexes."""
import time
from common import client, DB

col = client()[DB]["TransactionLogs"]
t = time.time()
tids = [d["_id"] for d in col.aggregate([
    {"$match": {"data.event": "Failed Process", "data.event_flag": "Progress"}},
    {"$group": {"_id": "$data.transaction_id"}}], allowDiskUse=True)]
print("failed txns to fix", len(tids))
for i in range(0, len(tids), 500):
    chunk = tids[i:i + 500]
    col.update_many({"data.transaction_id": {"$in": chunk}, "data.event_flag": "Last"},
                    {"$set": {"data.event": "Failed Process"}})
    col.update_many({"data.transaction_id": {"$in": chunk}, "data.event": "Failed Process", "data.event_flag": "Progress"},
                    {"$set": {"data.event": "Sending Response"}})
print("fixed %.0fs" % (time.time() - t))

for keys, name in [([("time", 1)], "time_1"), ([("data.transaction_id", 1)], "data.transaction_id_1"),
                   ([("data.event_flag", 1), ("time", 1)], "event_flag_1_time_1")]:
    t = time.time()
    col.create_index(keys, name=name)
    print("index", name, "%.0fs" % (time.time() - t))
print(col.index_information().keys())
print("docs", col.count_documents({}), "txns(First)", col.count_documents({"data.event_flag": "First"}))
db = col.database
print(db.command("dbStats"))
