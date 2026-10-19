from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted, PageBreak
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend

OUT = Path(__file__).resolve().parent / "Precomputed_Metrics_Benchmark_Report.pdf"
BLUE = colors.HexColor("#0F6CBD")
ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], textColor=BLUE, fontSize=16, spaceBefore=14, spaceAfter=6)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], textColor=BLUE, fontSize=12, spaceBefore=8, spaceAfter=4)
B = ParagraphStyle("B", parent=ss["BodyText"], fontSize=9.5, leading=13)
BL = ParagraphStyle("BL", parent=B, leftIndent=14, bulletIndent=4)
SM = ParagraphStyle("SM", parent=B, fontSize=8, leading=10, textColor=colors.HexColor("#555555"))
CODE = ParagraphStyle("CODE", fontName="Courier", fontSize=7.2, leading=8.6, backColor=colors.HexColor("#F3F3F3"),
                      borderPadding=4, spaceAfter=6)
CELL = ParagraphStyle("CELL", parent=B, fontSize=8.3, leading=10)


def P(t, s=B): return Paragraph(t, s)
def bullets(items): return [Paragraph(i, BL, bulletText="\u2022") for i in items]
def code(t): return Preformatted(t.strip("\n"), CODE)


def table(rows, widths, hdr=True, bold_last_col=False):
    data = [[Paragraph(str(c), CELL) for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1 if hdr else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if hdr:
        st += [("BACKGROUND", (0, 0), (-1, 0), BLUE)]
        for i, c in enumerate(data[0]):
            c.style = ParagraphStyle("h", parent=CELL, textColor=colors.white, fontName="Helvetica-Bold")
    t.setStyle(TableStyle(st))
    return t


def chart(title, cats, series, names, colors_, maxv, w=470, h=200):
    d = Drawing(w, h + 30)
    d.add(String(w / 2, h + 15, title, textAnchor="middle", fontSize=10, fontName="Helvetica-Bold"))
    c = VerticalBarChart()
    c.x, c.y, c.width, c.height = 45, 35, w - 70, h - 50
    c.data = series
    c.categoryAxis.categoryNames = cats
    c.categoryAxis.labels.fontSize = 8
    c.valueAxis.valueMin, c.valueAxis.valueMax = 0, maxv
    c.valueAxis.labels.fontSize = 8
    c.barLabelFormat = "%.1f"
    c.barLabels.fontSize = 6.5
    c.barLabels.nudge = 6
    c.groupSpacing = 10
    for i, col in enumerate(colors_): c.bars[i].fillColor = col
    d.add(c)
    lg = Legend()
    lg.x, lg.y, lg.fontSize, lg.alignment = 60, 22, 7.5, "right"
    lg.columnMaximum = 1
    lg.deltax = 105
    lg.colorNamePairs = list(zip(colors_, names))
    d.add(lg)
    return d


S = []
S.append(P("Precomputing Dashboard Metrics in Azure Cosmos DB for MongoDB", ParagraphStyle("T", parent=ss["Title"], fontSize=20, textColor=BLUE)))
S.append(P("Benchmark of live aggregation versus precomputed collections for the X12 transaction-metrics dashboard", ParagraphStyle("st", parent=B, fontSize=11, alignment=1)))
S.append(Spacer(1, 6))

# 1 Executive summary
S.append(P("1. Executive summary", H1))
S.append(P("The dashboard computes seven aggregated metrics from raw X12 event logs. Today the 30-day query times out, so the "
           "front end issues many 2-hour slice queries in parallel and merges the results. We tested the precomputation strategy "
           "on synthetic data modelled on two sample records, at two scales: <b>1.5M</b> event documents and <b>18M</b> event documents "
           "(about 1.62M transactions)."))
S.append(Spacer(1, 4))
S.append(table([
    ["30-day dashboard query, 18M events", "Response time", "Speed-up vs. raw single query"],
    ["Raw query (customer query, one request)", "324.7 s", "1x"],
    ["Raw query, 2-hour slices, 12 in parallel (today's workaround)", "220.6 s", "1.5x"],
    ["Precomputed per-transaction summary collection", "37.7 s", "8.6x"],
    ["<b>Precomputed hourly bucket collection</b>", "<b>1.55 s</b>", "<b>~210x</b>"]],
    [3.3 * inch, 1.2 * inch, 2.2 * inch]))
S.append(Spacer(1, 4))
S += bullets([
    "<b>Hourly pre-aggregated buckets are the recommended design.</b> They answer a 30-day dashboard request in about 1.5 s "
    "with a single query, and they grew only 2.4x when the data grew 12x.",
    "The live query degrades faster than the data grows (32x slower for 12x more data) and is not viable at 18M events without slicing.",
    "The per-transaction summary scales linearly with transaction count. It is a good drill-down layer but not fast enough for the main view at scale.",
    "All seven metrics returned identical values from raw, summary and bucket queries on the 1.5M dataset; on the 18M dataset the response sizes were identical.",
    "Absolute times depend on cluster tier and data shape. Use the ratios and re-run the supplied scripts on the production tier to confirm."])

# 2 Goals
S.append(P("2. Goals, objectives and scope", H1))
S += bullets([
    "<b>Goal:</b> measure the response-time benefit of serving the dashboard from precomputed collections instead of aggregating raw X12 events at request time.",
    "<b>Objectives:</b> (a) reproduce the customer workload with realistic synthetic data; (b) build the precomputed collections; "
    "(c) compare latency, documents read, CPU and payload for raw versus precomputed queries; (d) test at 1.5M and 18M events on vCore, and measure request units (RU) at 1.5M on an RU-based account.",
    "<b>In scope:</b> the seven dashboard metrics over 1, 7 and 30-day windows, with and without partner / transaction-type filters; build cost and storage overhead of the precomputed collections.",
    "<b>Out of scope:</b> refresh scheduling in production (change streams, late-arriving events), caching layers, front-end changes, and tuning of the customer's production cluster."])
S.append(P("Dashboard metrics: File Count, Transaction Count, Failed Transactions, Default Transactions, Average Time Taken, Closeouts %, Default Response %, plus the breakdown charts (type, partner, response-time ranges, daily trend)."))
# 3 Method
S.append(P("3. Method and approach", H1))
S += bullets([
    "<b>Synthetic data.</b> Generated from two local sample templates (7 and 14 events); fields from those templates are copied into generated events, so use sanitized inputs only. Each transaction has 7-15 events, a First and a Last flagged event, "
    "mixed transaction types and trading partners, and event times spread across 30 days. About 0.4% of transactions fail, ~0.03% are Default responses, "
    "1% lack a Last event (excluded, as in the customer query) and 5% carry a large payload.",
    "<b>Load.</b> Multi-process bulk insert from a VM in the same region as the cluster. Raw indexes: <font face='Courier'>time</font>, "
    "<font face='Courier'>data.transaction_id</font>, <font face='Courier'>{data.event_flag, time}</font>.",
    "<b>Precomputation.</b> Two collections built with idempotent <font face='Courier'>$merge</font> pipelines using the customer's own formulas: "
    "(1) <i>TransactionMetricSummary</i>, one small document per transaction, built in hourly windows with a 5-minute pad for transactions straddling a window edge; "
    "(2) <i>MetricBucketsHourly</i>, additive counts and sums per hour and dimension combination, built from the summary.",
    "<b>Measurement.</b> Same dashboard payload from each approach. Precomputed queries: 1 cold + 10 warm runs, median reported. Raw queries: single run "
    "(too long to repeat at 18M). The 2-hour sliced scenario replays the customer workaround with 12 parallel clients. We also captured explain plans, response size and Azure Monitor CPU.",
    "<b>Correctness.</b> Dashboard tiles compared across the three approaches. Example (30 days, 1.5M run): File Count 135,484; Failed 534; Default 39; Avg time 16.949 s; Closeouts 100%; Default Response 0.02879%.",
    "<b>RU note.</b> vCore-based Azure DocumentDB / Cosmos DB for MongoDB is billed on provisioned compute and storage and has no Request Units, so cost is compared via latency, documents read and CPU rather than RU."])

# 4 Infra
S.append(P("4. Azure infrastructure setup", H1))
S.append(table([
    ["Component", "Configuration"],
    ["Database", "Azure DocumentDB (MongoDB vCore) cluster <font face='Courier'>{YOUR_VCORE_CLUSTER_NAME}</font>; M30 tier, 1 shard, 128 GB storage, MongoDB 8.0, region West US 2, native authentication"],
    ["Client", "<font face='Courier'>{YOUR_VM_NAME}</font>: Standard_D8s_v5 (8 vCPU), Ubuntu 22.04, Python with pymongo, same region and resource group; its public IP allow-listed in the cluster firewall"],
    ["RU-based account (added test)", "Azure Cosmos DB for MongoDB (RU) <font face='Courier'>{YOUR_COSMOS_MONGO_ACCOUNT_NAME}</font>; API 7.0, West US 2, 20,000 RU/s manual database-level throughput, unsharded collections, private endpoint from the VM VNet"],
    ["Resource group", "<font face='Courier'>{YOUR_RESOURCE_GROUP_NAME}</font> (subscription <font face='Courier'>{YOUR_AZURE_RESOURCE_ID}</font>)"],
    ["Database / collections", "<font face='Courier'>contoso_benchmark</font>: TransactionLogs, TransactionMetricSummary, MetricBucketsHourly"],
    ["Note", "Replace resource placeholders with your Azure resource names and IDs. The production tier and index set may differ; "
             "use benchmark ratios and re-run on the target tier."]],
    [1.5 * inch, 5.2 * inch]))

# 5 Schema
S.append(P("5. Data schema and size", H1))
S.append(P("Raw collection: TransactionLogs (one document per event)", H2))
S.append(code("""{
  "_id": ObjectId, "time": ISODate, "type": "Portal 270",
  "data": {
    "transaction_id": "...", "transmission_id": "...",
    "event": "Failed Process | ...", "event_flag": "First | Last | <other>",
    "partner": "AVAILITY", "transaction_output_type": "...Default...",
    "transaction_stauts": "...", ...x12 payload / metadata...
  }
}"""))
S.append(P("Summary collection: TransactionMetricSummary (one document per transaction, no payload)", H2))
S.append(code("""{ "_id": transaction_id, "startTime": ISODate, "type": "...", "partner": "...",
  "transmissionId": "...", "outputStatus": "...", "outputType": "...",
  "isFailed": bool, "isDefault": bool, "isCloseout": bool,
  "durationSec": double, "updatedAt": ISODate }
Index: startTime, {partner,startTime}, {type,startTime}"""))
S.append(P("Bucket collection: MetricBucketsHourly (additive, one document per hour x dimension combination)", H2))
S.append(code("""{ "hour": ISODate, "type": "...", "partner": "...", "outputStatus": "...", "outputType": "...",
  "failed": bool, "defaulted": bool, "range": "0-10s|11-20s|21-45s|46-60s|60+s",
  "txnCount": int, "closeouts": int, "sumDurationSec": double, "fileCount": int }
Compound index on all dimension fields (merge key); indexes: hour, {partner,hour}, {type,hour}"""))
S.append(P("Sizes", H2))
S.append(table([
    ["", "1.5M-event run", "18M-event run"],
    ["TransactionLogs documents", "1,505,239", "~18,000,000"],
    ["Transactions represented", "~135,000", "~1,620,000"],
    ["Raw avg. document size", "~1.1 KB", "~0.7 KB avg. across DB (mix of small events and 5% large payloads)"],
    ["TransactionMetricSummary documents", "135,484", "1,619,502"],
    ["MetricBucketsHourly documents", "59,369", "137,270"],
    ["Database data size", "1.8 GB raw (2.26 GB total before precompute, 2.73 GB after)", "13.8 GB data, 5.4 GB indexes, 32 GB total allocated (incl. all three collections)"],
    ["Build time: summary", "21 s (+7 s indexes)", "320 s (+52 s indexes)"],
    ["Build time: buckets", "10 s", "35 s"],
    ["Raw index build", "-", "time 446 s; transaction_id 259 s; event_flag+time 386 s"]],
    [2.1 * inch, 2.1 * inch, 2.5 * inch]))
S.append(P("Precomputed collections added about 20% to the database size in the 1.5M run. The 18M-event total includes both precomputed collections.", SM))

# 6 Queries
S.append(P("6. Queries", H1))
S.append(P("Every approach returns the same dashboard payload (summary tiles, type breakdown, daily chart, partners, raw types, response-time ranges) in one <font face='Courier'>$facet</font> stage.", B))
S.append(P("A. Raw (customer) query - per-transaction derivation over events", H2))
S.append(code("""[ {$match: {time: {$gte: start, $lt: end}, "data.event_flag": {$in: ["First","Last"]}}},
  {$project: { time, type, data.transaction_id, data.transmission_id, data.event_flag,
               data.partner, data.event, data.transaction_output_type, data.transaction_stauts }},
  {$group: {_id: "$data.transaction_id", first: {$min: {time,partner,eventFlag,event,...}},
                                          last:  {$max: {time,partner,eventFlag,event,...}}}},
  {$match: first/last flags are First+Last (either order)},
  {$addFields: _dashboardIsFailed, _dashboardIsDefault, _dashboardStartTime,
               _dashboardPartner, _dashboardDurationSeconds, ...},
  {$facet: { summary, typeBreakdown, chart, partners, rawTypes, responseTimeRanges }} ]"""))
S.append(P("B. Precomputed summary query - same facet over one small document per transaction", H2))
S.append(code("""[ {$match: {startTime: {$gte: start, $lt: end}, partner?: P, type?: T}},
  {$addFields: map summary fields to _dashboard* names},
  {$facet: { ...same facet as A... }} ]"""))
S.append(P("C. Precomputed bucket query (recommended) - sums additive counts", H2))
S.append(code("""[ {$match: {hour: {$gte: start, $lt: end}, partner?: P, type?: T}},
  {$facet: {
     summary: [{$group: {_id: null, transactionCount: {$sum: "$txnCount"},
                failedTransactions: {$sum: {$cond: ["$failed", "$txnCount", 0]}},
                defaultTransactions: {$sum: {$cond: ["$defaulted", "$txnCount", 0]}},
                closeoutTransactions: {$sum: "$closeouts"},
                totalResponseTimeSeconds: {$sum: "$sumDurationSec"},
                fileCount: {$sum: "$fileCount"}}}],
     typeBreakdown, chart, partners, rawTypes, responseTimeRanges: group by dimension, $sum: "$txnCount" }} ]
Tiles: Avg Time = totalResponseTimeSeconds / transactionCount; Closeouts % and Default % = count / transactionCount."""))
S.append(P("D. Build (refresh) pipelines", H2))
S.append(code("""summary: raw $match(hour window + 5 min pad) -> per-transaction derivation -> keep txns starting in window
         -> $project compact fields -> $merge into TransactionMetricSummary on _id (replace)
buckets: summary $match(day window) -> $group(hour, type, partner, status, outputType, failed,
         defaulted, range) with $sum / $addToSet(file) -> $merge into MetricBucketsHourly (replace)"""))
S.append(P("Full pipeline source: <font face='Courier'>bench/pipelines.py</font>.", SM))

# 7 Results
S.append(P("7. Results", H1))
S.append(P("7.1 18M-event dataset (about 1.62M transactions)", H2))
S.append(table([
    ["Scenario (all partners / types)", "1 day", "7 days", "30 days"],
    ["Raw customer query, single request", "13.7 s", "115.2 s", "324.7 s"],
    ["Raw compact (recommendation Exp. 2)", "6.2 s", "111.7 s", "368.2 s"],
    ["Raw, 2h slices x12 parallel (current workaround)", "8.6 s (12 slices)", "49.1 s (84)", "220.6 s (360)"],
    ["Precomputed summary", "1.24 s", "8.9 s", "37.7 s"],
    ["<b>Precomputed hourly buckets</b>", "<b>0.05 s</b>", "<b>0.35 s</b>", "<b>1.55 s</b>"]],
    [3.0 * inch, 1.2 * inch, 1.2 * inch, 1.3 * inch]))
S.append(P("Precomputed rows: median of 10 warm runs (cold first run within ~5% of warm for buckets, e.g. 1.53 s at 30 days). Raw rows: single run. Raw single-request 30-day query completed only because the server time limit was raised for the test.", SM))
S.append(Spacer(1, 4))
S.append(chart("30-day response time, 18M events (seconds)", ["Raw single", "Raw sliced x12", "Summary", "Hourly buckets"],
               [[324.7, 220.6, 37.7, 1.55]], ["Seconds"], [BLUE], 360))
S.append(P("With filters, 30 days, 18M events", H2))
S.append(table([
    ["Filter", "Summary", "Hourly buckets"],
    ["partner = AVAILITY", "3.9 s", "0.21 s"],
    ["type = Portal 270", "13.9 s", "0.14 s"]], [3.0 * inch, 1.8 * inch, 1.9 * inch]))
S.append(P("7.2 1.5M-event dataset (about 135K transactions)", H2))
S.append(table([
    ["Scenario (all partners / types)", "1 day", "7 days", "30 days"],
    ["Raw customer query, single request", "0.30 s", "2.33 s", "10.19 s"],
    ["Raw compact (recommendation Exp. 2)", "0.44 s", "3.51 s", "14.82 s"],
    ["Raw, 2h slices x12 parallel", "0.41 s", "2.75 s", "11.10 s"],
    ["Precomputed summary", "0.10 s", "0.71 s", "3.14 s"],
    ["<b>Precomputed hourly buckets</b>", "<b>0.025 s</b>", "<b>0.16 s</b>", "<b>0.65 s</b>"]],
    [3.0 * inch, 1.2 * inch, 1.2 * inch, 1.3 * inch]))
S.append(Spacer(1, 4))
S.append(chart("30-day response time: scaling from 1.5M to 18M events (seconds)", ["Raw single", "Summary", "Hourly buckets"],
               [[10.19, 3.14, 0.65], [324.7, 37.7, 1.55]], ["1.5M events", "18M events"],
               [colors.HexColor("#8FB8DE"), BLUE], 340))
S.append(P("7.3 Scaling behaviour (12x more data)", H2))
S.append(table([
    ["Approach (30 days)", "1.5M events", "18M events", "Growth", "Why"],
    ["Raw single query", "10.2 s", "324.7 s", "32x", "Super-linear: working set no longer fits memory; scans and groups ~18M events"],
    ["Summary", "3.1 s", "37.7 s", "12x", "Linear in transaction count"],
    ["Hourly buckets", "0.65 s", "1.55 s", "2.4x", "Scales with distinct bucket keys (2.3x), not transactions"]],
    [1.3 * inch, 0.9 * inch, 0.9 * inch, 0.6 * inch, 3.0 * inch]))
S.append(P("7.4 Other measurements", H2))
S += bullets([
    "<b>Documents read (30 days, 1.5M run):</b> raw ~1.5M events, summary ~135K, buckets ~59K. At 18M: raw ~18M, summary ~1.6M, buckets ~137K.",
    "<b>CPU:</b> during the 1.5M run, raw 30-day scans drove the M30 to ~57% average CPU while precomputed queries stayed at or below ~30% even with 10 back-to-back repeats.",
    "<b>Round trips and payload:</b> each precomputed query is one request returning ~10 KB. The sliced workaround needs 360 round trips and returns ~1.1-1.6 MB for 30 days.",
    "<b>Recommendation Exp. 2 (compact server-side metrics):</b> not faster than the original query (368 s vs 325 s at 18M), so output size is not the bottleneck; scanning and grouping raw events is.",
    "<b>Correctness:</b> tiles identical across raw, summary and buckets at 1.5M (1/7/30 days). At 18M, payload sizes matched exactly (6,822 / 7,884 / 10,807 bytes for 1/7/30 days)."])

S.append(P("8. Results on RU-based Azure Cosmos DB for MongoDB (request units)", H1))
S.append(P("The same 1.5M-event dataset and the same three query approaches were then run on an RU-based <i>Azure Cosmos DB for MongoDB</i> account. "
           "RU is the request charge reported by the service (<font face='Courier'>getLastRequestStatistics</font>) for each query. "
           "Account: <font face='Courier'>{YOUR_COSMOS_MONGO_ACCOUNT_NAME}</font>, MongoDB API 7.0, West US 2, 20,000 RU/s manual (database-level), "
           "reached from the same VM through a private endpoint. Data: 1,505,239 raw events, 135,484 summary documents, 59,369 hourly buckets "
           "(identical counts to the vCore run). Precomputed queries: 1 cold + 10 warm runs (median); raw queries: single run. No request was throttled (429)."))
S.append(P("8.1 Latency and RU per dashboard query (all partners / types)", H2))
S.append(table([
    ["Approach", "1 day", "7 days", "30 days"],
    ["Raw customer query, single request", "0.92 s / 646 RU", "6.2 s / 4,623 RU", "27.6 s / 19,366 RU"],
    ["Raw compact (recommendation Exp. 2)", "0.85 s / 646 RU", "6.0 s / 4,623 RU", "25.0 s / 19,368 RU"],
    ["Raw, 2h slices x12 parallel (current workaround)", "0.49 s / 798 RU", "0.85 s / 4,994 RU", "2.6 s / 20,602 RU"],
    ["Precomputed summary", "0.22 s / 255 RU", "1.56 s / 1,804 RU", "5.6 s / 7,522 RU"],
    ["<b>Precomputed hourly buckets</b>", "<b>0.08 s / 113 RU</b>", "<b>0.51 s / 781 RU</b>", "<b>2.2 s / 3,288 RU</b>"]],
    [2.7 * inch, 1.3 * inch, 1.35 * inch, 1.35 * inch]))
S.append(P("Each cell is latency / request charge. 30-day buckets query: 3,288 RU versus 19,366 RU for the raw query (5.9x fewer RU) and 7,522 RU for the summary (2.6x fewer).", SM))
S.append(Spacer(1, 4))
S.append(chart("30-day request charge, 1.5M events (RU per dashboard request)", ["Raw single", "Raw sliced x12", "Summary", "Hourly buckets"],
               [[19366, 20602, 7522, 3288]], ["RU"], [BLUE], 24000))
S.append(P("8.2 Filtered queries, 30 days", H2))
S.append(table([
    ["Filter", "Summary", "Hourly buckets"],
    ["partner = AVAILITY", "0.70 s / 873 RU", "0.30 s / 495 RU"],
    ["type = Portal 270", "2.35 s / 2,927 RU", "0.31 s / 536 RU"]], [3.0 * inch, 1.8 * inch, 1.9 * inch]))
S.append(P("8.3 Capacity view: dashboard refreshes per second at 20,000 RU/s", H2))
S.append(table([
    ["30-day dashboard request", "RU per request", "Requests/s the 20,000 RU/s can sustain"],
    ["Raw query", "~19,400", "~1.0"],
    ["Precomputed summary", "~7,500", "~2.7"],
    ["Precomputed hourly buckets", "~3,300", "~6.1"],
    ["Hourly buckets, one partner", "~500", "~40"]], [2.4 * inch, 1.6 * inch, 2.7 * inch]))
S.append(P("8.4 Observations", H2))
S += bullets([
    "<b>RU confirms the same ranking as latency.</b> Reading pre-aggregated data costs 2.6x (summary) to 5.9x (buckets) fewer RU than recomputing from raw events for a 30-day view, and filtered buckets queries cost 495-536 RU.",
    "<b>Latency on RU is dominated by provisioned throughput.</b> With 20,000 RU/s, the sliced raw workaround finished 30 days in 2.6 s because 12 parallel slices spread ~20,600 RU across the available throughput; "
    "that same RU spend would be rate-limited when several users load the dashboard at once. The single-request buckets query uses ~6x fewer RU, so many more users fit within the same provisioned throughput.",
    "<b>Cost lens.</b> RU/s is the billing unit: lowering RU per dashboard view lets the same dashboard run on a smaller provisioned (or autoscale) throughput. Precompute refresh cost is separate: building the summary took 478 s plus 49 s for indexes, and buckets 121 s, at 20,000 RU/s.",
    "<b>Raw RU is the same for single and compact forms</b> (~19.4K at 30 days): the charge is driven by reading the First/Last events, not by output size.",
    "<b>Correctness:</b> tiles identical across raw, summary and buckets for 1, 7 and 30 days (30 days: 135,484 transactions, 534 failed, 39 default, 16.949 s average).",
    "<b>API differences to plan for:</b> <font face='Courier'>$dateTrunc</font> is not supported (use <font face='Courier'>$dateFromParts</font>); a $merge of a full day of bucket output exceeded the service's 512K-character query limit, so buckets are built in hourly windows; "
    "indexes must be created explicitly (only _id by default); clients should retry on error 16500 (429) for bulk loads and builds.",
    "<b>Not measured on RU:</b> the 18M-event scale (it needs roughly 12x the storage and throughput; RU per query would be expected to scale accordingly for raw and summary and much less for buckets)."])

S.append(P("9. Conclusions and recommendations", H1))
S += bullets([
    "Serve the dashboard from <b>pre-aggregated bucket documents</b>. Expect low-single-digit-second responses for 30-day windows in a single request, removing the need for 2-hour slicing and front-end merging.",
    "Keep the per-transaction summary collection for drill-down and for rebuilding buckets; it also supports filtered views in seconds.",
    "Consider <b>daily</b> buckets (with hourly or summary data for the partial current day) to reduce bucket cardinality further.",
    "Refresh with idempotent <font face='Courier'>$merge</font> jobs on a schedule (hourly), with a short overlap window to absorb late events; consider change streams for near-real-time.",
    "File Count is exact in buckets only when a file's transactions fall in one bucket. For multi-transaction files, attribute each file to its first transaction's hour or keep a separate distinct-file collection.",
    "Re-run the benchmark scripts on the production tier and real data before finalizing; absolute numbers will differ from this environment."])
S.append(P("Reproduction scripts: bench/datagen_load.py, bench/make_indexes.py, bench/build_precompute.py, bench/bench_run.py, bench/pipelines.py. "
           "Generated records are synthetic; use sanitized sample templates and do not publish them.", SM))


def footer(c, d):
    c.saveState(); c.setFont("Helvetica", 7.5); c.setFillColor(colors.grey)
    c.drawString(0.7 * inch, 0.45 * inch, "Precomputed metrics benchmark - Azure Cosmos DB for MongoDB")
    c.drawRightString(letter[0] - 0.7 * inch, 0.45 * inch, f"Page {d.page}")
    c.restoreState()


SimpleDocTemplate(str(OUT), pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch, topMargin=0.7 * inch,
                  bottomMargin=0.75 * inch, title="Precomputed Metrics Benchmark").build(S, onFirstPage=footer, onLaterPages=footer)
print(OUT)
