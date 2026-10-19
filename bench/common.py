import os, re, json
from pymongo import MongoClient

DB = "contoso_benchmark"


def client(**kw):
    return MongoClient(os.environ["MONGO_URI"], **kw)


def load_samples(base):
    out = []
    for f in ("TransactionLogs_QA.json", "TransactionLogs_QA_2.json"):
        t = open(os.path.join(base, f), encoding="utf8").read()
        t = re.sub(r"^\s*//.*$", "", t, flags=re.M)
        out.append(json.loads(t))
    return out
