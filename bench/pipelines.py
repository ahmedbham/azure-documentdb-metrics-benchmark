"""Pipelines: customer raw query, summary-based, and bucket-based dashboard queries."""
import datetime as dt

OBJ = lambda: {
    "time": "$time", "partner": "$data.partner", "eventFlag": "$data.event_flag", "event": "$data.event",
    "outputType": "$data.transaction_output_type", "outputStatus": "$data.transaction_stauts",
    "type": "$type", "transmissionId": "$data.transmission_id"}


def _first(f): return {"$cond": [{"$eq": ["$first.eventFlag", "First"]}, "$last." + f, "$first." + f]}


def txn_stages():
    """Customer's per-transaction derivation (verbatim semantics)."""
    return [
        {"$project": {"time": 1, "type": 1, "data.transaction_id": 1, "data.transmission_id": 1,
                      "data.event_flag": 1, "data.partner": 1, "data.event": 1,
                      "data.transaction_output_type": 1, "data.transaction_stauts": 1}},
        {"$group": {"_id": "$data.transaction_id", "first": {"$min": OBJ()}, "last": {"$max": OBJ()}}},
        {"$addFields": {"type": "$first.type", "TransmissionID": "$first.transmissionId",
                        "firstEventFlag": "$first.eventFlag", "firstEvent": "$first.event",
                        "lastEventFlag": "$last.eventFlag", "lastEvent": "$last.event"}},
        {"$match": {"$or": [{"firstEventFlag": "First", "lastEventFlag": "Last"},
                            {"firstEventFlag": "Last", "lastEventFlag": "First"}]}},
        {"$addFields": {
            "_dashboardOutputStauts": {"$ifNull": [_first("outputStatus"), "Local"]},
            "_dashboardOutputType": {"$ifNull": [_first("outputType"), ""]},
            "_dashboardIsFailed": {"$or": [{"$eq": ["$firstEvent", "Failed Process"]},
                                           {"$eq": ["$lastEvent", "Failed Process"]}]},
            "_dashboardStartTime": {"$cond": [{"$eq": ["$first.eventFlag", "First"]}, "$first.time", "$last.time"]},
            "_dashboardPartner": {"$ifNull": ["$first.partner", "$last.partner"]},
            "_dashboardDurationSeconds": {"$divide": [{"$abs": {"$subtract": ["$last.time", "$first.time"]}}, 1000]},
            "_dashboardIsDefault": {"$gte": [{"$indexOfCP": [{"$ifNull": [_first("outputType"), ""]}, "Default"]}, 0]}}}]


RANGE_SWITCH = {"$switch": {"branches": [
    {"case": {"$lte": ["$DUR", 10]}, "then": "0-10s"}, {"case": {"$lte": ["$DUR", 20]}, "then": "11-20s"},
    {"case": {"$lte": ["$DUR", 45]}, "then": "21-45s"}, {"case": {"$lte": ["$DUR", 60]}, "then": "46-60s"}],
    "default": "60+s"}}


def range_expr(dur):
    import json
    return json.loads(json.dumps(RANGE_SWITCH).replace("$DUR", dur))


def facet_stage():
    """Original facet over per-transaction docs (_dashboard* fields)."""
    return {"$facet": {
        "summary": [
            {"$group": {"_id": None, "transactionCount": {"$sum": 1}, "fileIds": {"$addToSet": "$TransmissionID"},
                        "failedTransactions": {"$sum": {"$cond": ["$_dashboardIsFailed", 1, 0]}},
                        "defaultTransactions": {"$sum": {"$cond": ["$_dashboardIsDefault", 1, 0]}},
                        "closeoutTransactions": {"$sum": {"$cond": [{"$ne": ["$firstEventFlag", "$lastEventFlag"]}, 1, 0]}},
                        "totalResponseTimeSeconds": {"$sum": "$_dashboardDurationSeconds"}}},
            {"$project": {"_id": 0, "transactionCount": 1, "failedTransactions": 1, "defaultTransactions": 1,
                          "closeoutTransactions": 1, "totalResponseTimeSeconds": 1,
                          "fileCount": {"$size": {"$filter": {"input": "$fileIds", "as": "f",
                                                              "cond": {"$and": [{"$ne": ["$$f", None]}, {"$ne": ["$$f", ""]}]}}}}}}],
        "typeBreakdown": [{"$group": {"_id": {"type": "$type", "outputStauts": "$_dashboardOutputStauts",
                                              "outputType": "$_dashboardOutputType", "failed": "$_dashboardIsFailed",
                                              "defaulted": "$_dashboardIsDefault"},
                                      "totalCount": {"$sum": 1},
                                      "totalResponseTimeSeconds": {"$sum": "$_dashboardDurationSeconds"}}}],
        "chart": [{"$group": {"_id": {"time": {"$dateToString": {"format": "%Y-%m-%d", "date": "$_dashboardStartTime"}},
                                      "failed": "$_dashboardIsFailed"}, "count": {"$sum": 1}}}],
        "partners": [{"$match": {"_dashboardPartner": {"$nin": [None, ""]}}},
                     {"$group": {"_id": "$_dashboardPartner", "count": {"$sum": 1}}}],
        "rawTypes": [{"$group": {"_id": "$type", "count": {"$sum": 1}}}],
        "responseTimeRanges": [{"$group": {"_id": range_expr("$_dashboardDurationSeconds"), "count": {"$sum": 1}}}]}}


def raw_pipeline(start, end, partner=None, typ=None):
    m = {"time": {"$gte": start, "$lt": end}, "data.event_flag": {"$in": ["First", "Last"]}}
    if partner: m["data.partner"] = partner
    if typ: m["type"] = typ
    return [{"$match": m}] + txn_stages() + [facet_stage()]


def raw_compact_pipeline(start, end):
    """Experiment 2 from the PDF: collapse to a single metrics doc server side (uses customer formulas)."""
    return [{"$match": {"time": {"$gte": start, "$lt": end}, "data.event_flag": {"$in": ["First", "Last"]}}}] + txn_stages() + [
        {"$group": {"_id": None, "transactionCount": {"$sum": 1}, "fileIds": {"$addToSet": "$TransmissionID"},
                    "failed": {"$sum": {"$cond": ["$_dashboardIsFailed", 1, 0]}},
                    "default": {"$sum": {"$cond": ["$_dashboardIsDefault", 1, 0]}},
                    "closeout": {"$sum": {"$cond": [{"$ne": ["$firstEventFlag", "$lastEventFlag"]}, 1, 0]}},
                    "dur": {"$sum": "$_dashboardDurationSeconds"}}},
        {"$project": {"_id": 0, "transactionCount": 1, "failed": 1, "default": 1, "closeout": 1, "dur": 1,
                      "fileCount": {"$size": "$fileIds"}}}]


def summary_build_pipeline(start, end, pad_minutes=5):
    """Builds TransactionMetricSummary docs for transactions that START in [start, end)."""
    pad = dt.timedelta(minutes=pad_minutes)
    return [{"$match": {"time": {"$gte": start, "$lt": end + pad}, "data.event_flag": {"$in": ["First", "Last"]}}}] \
        + txn_stages() + [
        {"$match": {"_dashboardStartTime": {"$gte": start, "$lt": end}}},
        {"$project": {
            "_id": 1, "startTime": "$_dashboardStartTime", "type": 1, "partner": "$_dashboardPartner",
            "transmissionId": "$TransmissionID", "outputStatus": "$_dashboardOutputStauts",
            "outputType": "$_dashboardOutputType", "isFailed": "$_dashboardIsFailed",
            "isDefault": "$_dashboardIsDefault",
            "isCloseout": {"$ne": ["$firstEventFlag", "$lastEventFlag"]},
            "durationSec": "$_dashboardDurationSeconds",
            "updatedAt": "$$NOW"}},
        {"$merge": {"into": "TransactionMetricSummary", "on": "_id", "whenMatched": "replace", "whenNotMatched": "insert"}}]


def bucket_build_pipeline(start, end):
    """Hourly additive buckets from the summary collection (hours fully inside [start, end))."""
    return [
        {"$match": {"startTime": {"$gte": start, "$lt": end}}},
        {"$group": {"_id": {"hour": {"$dateFromParts": {"year": {"$year": "$startTime"}, "month": {"$month": "$startTime"},
                                                        "day": {"$dayOfMonth": "$startTime"}, "hour": {"$hour": "$startTime"}}},
                            "type": "$type", "partner": "$partner", "outputStatus": "$outputStatus",
                            "outputType": "$outputType", "failed": "$isFailed", "defaulted": "$isDefault",
                            "range": range_expr("$durationSec")},
                    "txnCount": {"$sum": 1}, "closeouts": {"$sum": {"$cond": ["$isCloseout", 1, 0]}},
                    "sumDurationSec": {"$sum": "$durationSec"}, "files": {"$addToSet": "$transmissionId"}}},
        {"$project": {"_id": 0, "hour": "$_id.hour", "type": "$_id.type", "partner": "$_id.partner",
                      "outputStatus": "$_id.outputStatus", "outputType": "$_id.outputType",
                      "failed": "$_id.failed", "defaulted": "$_id.defaulted", "range": "$_id.range",
                      "txnCount": 1, "closeouts": 1, "sumDurationSec": 1,
                      "fileCount": {"$size": "$files"}}},
        {"$merge": {"into": "MetricBucketsHourly", "on": ["hour", "type", "partner", "outputStatus", "outputType",
                                                           "failed", "defaulted", "range"],
                    "whenMatched": "replace", "whenNotMatched": "insert"}}]


def summary_query_pipeline(start, end, partner=None, typ=None):
    m = {"startTime": {"$gte": start, "$lt": end}}
    if partner: m["partner"] = partner
    if typ: m["type"] = typ
    return [{"$match": m},
            {"$addFields": {"TransmissionID": "$transmissionId", "_dashboardOutputStauts": "$outputStatus",
                            "_dashboardOutputType": "$outputType", "_dashboardIsFailed": "$isFailed",
                            "_dashboardIsDefault": "$isDefault", "_dashboardStartTime": "$startTime",
                            "_dashboardPartner": "$partner", "_dashboardDurationSeconds": "$durationSec",
                            "firstEventFlag": "First",
                            "lastEventFlag": {"$cond": ["$isCloseout", "Last", "First"]}}},
            facet_stage()]


def bucket_query_pipeline(start, end, partner=None, typ=None):
    m = {"hour": {"$gte": start, "$lt": end}}
    if partner: m["partner"] = partner
    if typ: m["type"] = typ
    return [{"$match": m}, {"$facet": {
        "summary": [{"$group": {"_id": None, "transactionCount": {"$sum": "$txnCount"},
                                "failedTransactions": {"$sum": {"$cond": ["$failed", "$txnCount", 0]}},
                                "defaultTransactions": {"$sum": {"$cond": ["$defaulted", "$txnCount", 0]}},
                                "closeoutTransactions": {"$sum": "$closeouts"},
                                "totalResponseTimeSeconds": {"$sum": "$sumDurationSec"},
                                "fileCount": {"$sum": "$fileCount"}}},
                    {"$project": {"_id": 0}}],
        "typeBreakdown": [{"$group": {"_id": {"type": "$type", "outputStauts": "$outputStatus",
                                              "outputType": "$outputType", "failed": "$failed",
                                              "defaulted": "$defaulted"},
                                      "totalCount": {"$sum": "$txnCount"},
                                      "totalResponseTimeSeconds": {"$sum": "$sumDurationSec"}}}],
        "chart": [{"$group": {"_id": {"time": {"$dateToString": {"format": "%Y-%m-%d", "date": "$hour"}},
                                      "failed": "$failed"}, "count": {"$sum": "$txnCount"}}}],
        "partners": [{"$match": {"partner": {"$nin": [None, ""]}}},
                     {"$group": {"_id": "$partner", "count": {"$sum": "$txnCount"}}}],
        "rawTypes": [{"$group": {"_id": "$type", "count": {"$sum": "$txnCount"}}}],
        "responseTimeRanges": [{"$group": {"_id": "$range", "count": {"$sum": "$txnCount"}}}]}}]


def dashboard_metrics(facet_doc):
    """Derive the 7 dashboard tiles from the summary facet."""
    s = facet_doc["summary"][0] if facet_doc["summary"] else {}
    tc = s.get("transactionCount", 0)
    return {
        "File Count": s.get("fileCount", 0), "Transaction Count": tc,
        "Failed Transactions": s.get("failedTransactions", 0),
        "Default Transactions": s.get("defaultTransactions", 0),
        "Average Time Taken": round(s.get("totalResponseTimeSeconds", 0) / tc, 3) if tc else 0,
        "Closeouts %": round(s.get("closeoutTransactions", 0) / tc * 100, 5) if tc else 0,
        "Default Response %": round(s.get("defaultTransactions", 0) / tc * 100, 5) if tc else 0}
