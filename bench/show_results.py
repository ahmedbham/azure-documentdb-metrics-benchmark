import json
d = json.load(open("/opt/app/results.json"))
print(d["run_start"], d["run_end"])
for r in d["results"]:
    w = r.get("warm")
    print("%-34s %-4s run1=%8.3fs warm(med/p95)=%s out=%d docs/%d B slices=%s err=%s" % (
        r["scenario"], r["window"], r["seconds"], ("%s/%s" % (w["median"], w["p95"])) if w else "-",
        r["out_docs"], r["out_bytes"], r.get("slices", "-"), r["error"]))
