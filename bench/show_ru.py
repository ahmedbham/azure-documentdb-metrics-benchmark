import json
d = json.load(open("/opt/app/results_ru.json"))
print(d["run_start"], d["run_end"])
for r in d["results"]:
    w = r.get("warm", {})
    print("%-30s %-4s run1=%7.3fs med=%s RU_med=%s RU_cold=%s RU=%s thr=%s slices=%s err=%s" % (
        r["scenario"], r["window"], r["seconds"], w.get("median", "-"), r.get("ru_median", "-"), r.get("ru_cold", "-"),
        r.get("ru", "-"), r.get("throttled_retries"), r.get("slices", "-"), (r["error"] or "")[:80]))
t = d["tiles"]
ks = sorted({k.split("_", 1)[1] for k in t})
for k in ks:
    v = [json.dumps(t[f"{p}_{k}"], sort_keys=True) for p in ("raw", "summary", "buckets") if f"{p}_{k}" in t]
    print("TILES", k, "equal" if len(set(v)) == 1 else "DIFF", len(v))
