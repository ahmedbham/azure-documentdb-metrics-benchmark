import time, json
from common import client, DB

db = client()[DB]
for _ in range(3):
    try:
        print(json.dumps(db.client.admin.command("currentOp"), default=str)[:800])
    except Exception as e:
        print("err", str(e)[:200])
    time.sleep(5)

