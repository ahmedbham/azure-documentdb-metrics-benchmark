import time
from common import client, DB

col = client(socketTimeoutMS=3600000)[DB]["TransactionLogs"]
for keys, name in [([("time", 1)], "time_1"), ([("data.transaction_id", 1)], "data.transaction_id_1"),
                   ([("data.event_flag", 1), ("time", 1)], "event_flag_1_time_1")]:
    t = time.time()
    for attempt in range(200):
        try:
            col.create_index(keys, name=name)
            break
        except Exception as e:
            if getattr(e, "code", None) in (16500, 429):
                time.sleep(2)
                continue
            raise
    print("index", name, "%.0fs" % (time.time() - t), "attempts", attempt + 1, flush=True)
print("indexes", [i["name"] for i in col.list_indexes()])
print("docs", col.count_documents({}))
print(col.database.command("dbStats"))
