import pprint
from common import client, DB
c = client()[DB]["TransactionLogs"]
d = c.find_one({"data.event_flag": "Last"})
d["data"].pop("payload", None)
pprint.pprint(d)
s = c.database.command("collstats", "TransactionLogs")
print("count", s["count"], "avgObjSize", s["avgObjSize"], "size", s["size"])
