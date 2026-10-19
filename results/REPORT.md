# Precomputed metrics vs. live aggregation – benchmark results

**Environment**: Azure DocumentDB (MongoDB vCore) `{YOUR_VCORE_CLUSTER_NAME}` (M30, 1 shard, Mongo 8.0, westus2). The client VM is `{YOUR_VM_NAME}` in the same region. Database: `contoso_benchmark`.

**Data**: 1,505,239 synthetic event docs / ~137K transactions (≈11 events each, 7–15), 30-day spread, built from the two sample files (avg doc 1.1 KB, 1.8 GB). Raw indexes: `time`, `data.transaction_id`, `{data.event_flag,time}`.

The benchmark records are generated synthetically from local sample templates. The generator copies fields from those templates, so use only sanitized inputs and do not publish the sample files.

**Precomputed collections** (built with `$merge` from the raw logs, same formulas as the customer query):
| Collection | Docs | Build time |
|---|---|---|
| `TransactionMetricSummary` (1 doc/transaction, no payload) | 135,484 | 21 s (hourly windows, 8 threads) + 7 s indexes |
| `MetricBucketsHourly` (hour × type × partner × status × output type × failed × default × duration range; additive counts/sums) | 59,369 | 10 s (from summary) |

DB size grew 2.26 GB → 2.73 GB incl. indexes (~+20 %, summary+buckets+indexes).

## Response time (seconds, full dashboard payload: 7 tiles + 5 breakdowns)
Summary/bucket: median of 10 warm runs. Raw: single run.

| Window | Raw customer query (1 request) | Raw, PDF Exp.2 compact | Raw, 2h slices ×12 parallel (customer workaround) | Summary collection | Hourly buckets |
|---|---|---|---|---|---|
| 1 day | 0.30 | 0.44 | 0.41 | 0.10 | **0.025** |
| 7 days | 2.33 | 3.51 | 2.75 | 0.71 | **0.16** |
| 30 days | 10.19 | 14.82 | 11.10 | 3.14 | **0.65** |

Speed-up at 30 d vs. raw single query: summary 3.2×, buckets **15.6×**. With filters (30 d): partner=AVAILITY → summary 0.31 s, buckets 0.09 s; type=Portal 270 → summary 1.09 s, buckets 0.095 s (raw filtered not run).

Output payload: ~10 KB (raw/summary/buckets all identical shape). Client-side slicing returns 360 × ~3 KB docs (1.15 MB) for 30 d and needs 360 round trips.

## Correctness
Tiles are identical for 1 d / 7 d / 30 d across raw, summary and buckets (30 d: File Count 135,484; Transactions 135,484; Failed 534; Default 39; Avg time 16.949 s; Closeouts 100 %; Default Response % 0.02879).

## Resource usage
- vCore Azure DocumentDB has **no RUs**; compute is provisioned. Azure Monitor `CpuPercent` during the run: raw 30-day scans drove the M30 to ~57 % avg CPU; the precomputed queries were ≤ ~30 % even while running 10 repeats back-to-back.
- Raw queries scan ~1.5M events (30 d); summary reads ~135K docs; buckets ~59K docs (a ~25× / ~2.5× reduction in docs read).

## Findings / caveats
1. **Absolute times here are ~18× faster than the customer's** (customer: ~6 s per 50K docs → ~3 min for 1.5M; here raw 30 d = 10 s). Their cluster tier, index set, document size/payload, and concurrency differ, so use the **ratios** and re-run `bench/` on their tier. Assuming linear scaling, the customer's raw 30 d (≈3 min) would map to roughly 10–15 s for the summary and ~2–3 s for buckets.
2. Summary-per-transaction cost is still linear in transaction count (customer: ~1.8M txns / 30 d ⇒ expect ~13× this dataset). Buckets scale with the number of distinct bucket keys, not transactions; their high cardinality here (59K buckets for 135K txns, caused by per-hour × partner × status × output type × duration range) limits gains – a **daily** bucket (or dropping `outputStatus`/`outputType` into coarser flags) would shrink it further, and a hybrid (daily buckets for full days + hourly/summary for the partial edge) is the production pattern.
3. File Count in buckets is exact only when a file's transactions fall in the same bucket (here transmission_id = transaction_id). With multi-transaction files, attribute each file to its first transaction's hour or keep a separate distinct-file collection.
4. PDF Experiment 2 (compact server-side metrics) was **slower** than the transaction-level query (14.8 s vs 10.2 s) – output size is not the bottleneck; scanning/grouping raw logs is, supporting precomputation.
5. Late/duplicate events: build uses idempotent `$merge` (`replace` on `_id`), so re-running an hour is safe; 5-minute pad handles transactions spanning window edges. Transactions without a Last event (1 % in synthetic data) are excluded, as in the customer query.
6. Not measured: change-stream/near-real-time refresh, Redis cache, 18M-event (~1.8M txn) production-scale run.

## Reproduce
`bench/datagen_load.py` → `bench/fix_and_index.py` → `bench/build_precompute.py` → `bench/bench_run.py` (pipelines in `bench/pipelines.py`; run from a VM in the cluster's region with `MONGO_URI` set).


---
# Scale-up run: ~18M event documents (~1.62M transactions)

"18M files" was interpreted as 18M event documents (about 1.62M transactions, 7-15 events each). Raw collection: ~18M docs, ~13.8 GB data, ~5.4 GB indexes (DB total 32 GB). Same M30 vCore cluster, 12x-parallel client on a D8s VM in the same region.

Build: summary 320 s (1,619,502 docs) + 52 s indexes; hourly buckets 35 s (137,270 docs). Raw indexes: time 446 s, transaction_id 259 s, event_flag+time 386 s.

| Scenario (all partners/types) | 1d | 7d | 30d |
|---|---|---|---|
| Raw customer query, single | 13.7 s | 115.2 s | **324.7 s** |
| Raw compact (PDF Exp-2) | 6.2 s | 111.7 s | 368.2 s |
| Raw sliced 2h x12 parallel (customer workaround) | 8.6 s | 49.1 s | 220.6 s |
| Precomputed summary (per-txn) | 1.24 s | 8.9 s | 37.7 s |
| Precomputed hourly buckets | **0.05 s** | **0.35 s** | **1.55 s** |

Filtered (partner=AVAILITY, 30d): summary 3.9 s, buckets 0.21 s. Type=Portal 270, 30d: summary 13.9 s, buckets 0.14 s.

Speedup at 30d vs raw single: summary 8.6x, buckets ~210x. vs the customer's sliced workaround: summary 5.8x, buckets ~140x.

Scaling 1.5M -> 18M events (12x data): raw 30d 10.2 s -> 325 s (32x, super-linear: working set no longer fits cache); summary 3.1 s -> 37.7 s (12x, linear); buckets 0.65 s -> 1.55 s (2.4x, bucket count grew only 2.3x). Raw single at 30d completes here only because maxTimeMS was raised; the customer's timeout would hit it.

Correctness: response payload sizes are identical across raw, summary and buckets for 1d/7d/30d (6822/7884/10807 B); tile values were compared in the harness (TILES in the job log).

Conclusion: summary-per-transaction scans scale with transaction count, so use it only for drill-down. Hourly (or coarser, daily) buckets keep dashboard queries in the low seconds regardless of raw size and are the recommended design. Cost metric: vCore has no RUs; compare latency and CPU/IOPS.

The benchmark cluster `{YOUR_VCORE_CLUSTER_NAME}` may continue to incur charges; delete it when no longer needed. The client VM `{YOUR_VM_NAME}` should be deallocated when idle.


---
# RU-based Cosmos DB for MongoDB ({YOUR_COSMOS_MONGO_ACCOUNT_NAME}, 20,000 RU/s, 1.5M events)

Note: the supplied account `{YOUR_EXISTING_NOSQL_ACCOUNT_NAME}` is a NoSQL API account (no EnableMongo capability), so a separate RU-based MongoDB API account `{YOUR_COSMOS_MONGO_ACCOUNT_NAME}` (7.0) was used. Public access is disabled by policy; the VM connects through a private endpoint.

| Approach (latency / RU) | 1d | 7d | 30d |
|---|---|---|---|
| Raw single | 0.92 s / 646 | 6.2 s / 4,623 | 27.6 s / 19,366 |
| Raw compact | 0.85 s / 646 | 6.0 s / 4,623 | 25.0 s / 19,368 |
| Raw sliced 2h x12 | 0.49 s / 798 | 0.85 s / 4,994 | 2.6 s / 20,602 |
| Summary | 0.22 s / 255 | 1.56 s / 1,804 | 5.6 s / 7,522 |
| Hourly buckets | 0.08 s / 113 | 0.51 s / 781 | 2.2 s / 3,288 |

Filtered 30d: AVAILITY summary 873 RU, buckets 495 RU; Portal 270 summary 2,927 RU, buckets 536 RU. Tiles equal across approaches. No 429s. Build: summary 478 s + 49 s indexes, buckets 121 s. API gaps: no $dateTrunc (use $dateFromParts); build buckets in hourly windows (512K-char query limit).
