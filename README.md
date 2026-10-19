# Contoso Transaction Metrics Benchmark

This repository contains scripts and analysis for comparing live MongoDB aggregation with precomputed transaction summaries and hourly metric buckets. It is a reproducible benchmark example for an X12 transaction-metrics dashboard; it does not deploy or configure Azure resources.

The benchmark measures query latency, output size, and (for Azure Cosmos DB for MongoDB RU) request-unit consumption over 1-, 7-, and 30-day windows. The analysis discusses scalability, query patterns, and trade-offs between raw-event queries, per-transaction summaries, and additive hourly buckets.

## Repository contents

- `bench/` — scripts to generate synthetic events from local sample inputs, create indexes, build summary/bucket collections, and run latency and RU benchmarks.
- `results/REPORT.md` — benchmark results, methodology, caveats, and reproduction sequence.
- `results/make_pdf.py` — optional script to generate a PDF report from the benchmark results.
- `inline-metric-compute-query.json` — example aggregation pipeline/query document.

Private or customer-provided sample inputs, screenshots, and PDF artifacts are intentionally excluded from the public repository. The data-generation script expects two sanitized JSON sample files named `TransactionLogs_QA.json` and `TransactionLogs_QA_2.json` in the repository root. Do not add customer data, credentials, connection strings, or production identifiers to a public checkout.

## Prerequisites

- Python 3.10 or later.
- A MongoDB-compatible target, such as Azure DocumentDB or Azure Cosmos DB for MongoDB, with enough capacity for the chosen data volume.
- A configured `MONGO_URI` environment variable for the target database.
- Access to sanitized input files as described above.

Install the Python dependencies:

```shell
python -m pip install pymongo reportlab
```

The benchmark writes and modifies data in the database named `contoso_benchmark` by default. Review each script before running it against a shared or production resource. In particular, `--drop` deletes target collections.

## Configure and run

1. Create or select the Azure resources you intend to use, then replace the placeholders in your own notes and configuration with your Azure resource names and resource IDs:
   - Azure resource name: `{YOUR_AZURE_RESOURCE_NAME}`
   - Azure resource ID: `{YOUR_AZURE_RESOURCE_ID}`
   - Resource group name: `{YOUR_RESOURCE_GROUP_NAME}`
   - MongoDB vCore cluster name: `{YOUR_VCORE_CLUSTER_NAME}`
   - RU-based MongoDB account name (if applicable): `{YOUR_COSMOS_MONGO_ACCOUNT_NAME}`
   - Client VM name (if applicable): `{YOUR_VM_NAME}`

   Resource IDs and names are environment-specific; this repository deliberately contains no real Azure resource identifiers. Do not use the placeholders as literal values when creating resources.

2. Set `MONGO_URI` in your shell. Keep credentials out of source files and shell history. For example, in PowerShell:

   ```powershell
   $env:MONGO_URI = "<your-mongodb-connection-string>"
   ```

3. Place sanitized sample documents in the repository root as `TransactionLogs_QA.json` and `TransactionLogs_QA_2.json`. The scripts use these as templates to generate synthetic events.

4. From the repository root, run the benchmark stages in order:

   ```shell
   python bench/datagen_load.py <target_event_documents> [workers]
   python bench/fix_and_index.py
   python bench/build_precompute.py
   python bench/bench_run.py
   ```

   Example scale-up input: `18000000` event documents. This can consume substantial time, storage, compute, and cloud charges. Start with a small volume and confirm resource limits and costs before scaling up. Use `--drop` only when you intend to remove the corresponding data or derived collections.

5. For an RU-based Cosmos DB for MongoDB account, run the RU-aware benchmark instead:

   ```shell
   python bench/bench_ru.py [warm_runs]
   ```

6. To create the optional PDF report, run:

   ```shell
   python results/make_pdf.py
   ```

   It writes `results/Precomputed_Metrics_Benchmark_Report.pdf`. PDF output is ignored by Git because generated reports may contain environment-specific details.

## Safety and interpretation

- Use synthetic or explicitly sanitized sample inputs only. The generator copies fields from the sample records into generated events, so sensitive fields in the templates can carry through.
- The benchmark scripts write to `contoso_benchmark`; inspect scripts and connection targets before execution. Never point a destructive test at a production database.
- Azure resources are not provisioned by these scripts. Resource creation, network access, authentication, and cleanup are the operator's responsibility.
- The report's timings are environment-specific measurements, not service guarantees. Re-run on the intended tier and dataset before making design decisions.
- Cost can continue after a test finishes if cloud resources remain provisioned. Review and remove temporary resources when appropriate.
