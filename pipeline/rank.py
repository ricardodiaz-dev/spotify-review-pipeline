"""Stage 5 - Rank (code only, no model). Recomputes everything from saved records + membership.csv.

priority(issue) = complaint_count x mean_severity = severity_sum (integer arithmetic; mean exported with
6-decimal half-up rounding). Sort: score desc, issue_id asc. Also writes topic- and product-area-level
aggregates and a monthly complaint-share trend with denominators.
"""
import csv
import json
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal

from .common import TOPICS, log_event, write_json
from .records import iter_records

AREAS = {"access": "access", "usability": "usability", "playback": "playback", "downloads": "playback",
         "billing": "billing/support", "support": "billing/support", "catalog": "catalog", "other": "other"}


def mean6(total, n):
    return str((Decimal(total) / Decimal(n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def run(state_dir):
    recs = {}
    status = Counter()
    month_total, month_topic = Counter(), defaultdict(Counter)
    topic_stats = defaultdict(Counter)
    for r in iter_records(state_dir, internal=True):
        status[r["status"]] += 1
        if r["status"] != "completed":
            continue
        recs[r["review_id"]] = r
        m = r["review_timestamp"][:7]
        month_total[m] += 1
        t = topic_stats[r["topic"]]
        t["records"] += 1
        if r["intent"] in ("complaint", "cancellation"):
            month_topic[m][r["topic"]] += 1
            t["complaints"] += 1
            t["severity_sum"] += r["severity"]
            t["cancellation"] += r["intent"] == "cancellation"
            t["sev_ge4"] += r["severity"] >= 4
            t["needs_review"] += r["needs_review"]
    members = defaultdict(list)
    with open(state_dir / "membership.csv", newline="") as f:
        for row in csv.DictReader(f):
            members[row["issue_id"]].append(row["review_id"])
    issues_meta = {}
    if (state_dir / "issues.json").exists():
        issues_meta = {i["issue_id"]: i for i in json.loads((state_dir / "issues.json").read_text())["issues"]}
    rows = []
    for iid, ids in members.items():
        sev = [recs[r]["severity"] for r in ids]
        rows.append({"issue_id": iid, "complaint_count": len(ids), "severity_sum": sum(sev),
                     "mean_severity": mean6(sum(sev), len(ids)), "priority_score": sum(sev),
                     "cancellation_count": sum(recs[r]["intent"] == "cancellation" for r in ids),
                     "severity_ge4_count": sum(s >= 4 for s in sev),
                     "needs_review_count": sum(recs[r]["needs_review"] for r in ids),
                     "topic": recs[ids[0]]["topic"], "name": issues_meta.get(iid, {}).get("name", "")})
    rows.sort(key=lambda x: (-x["priority_score"], x["issue_id"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    with open(state_dir / "ranking.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score"])
        for r in rows:
            w.writerow([r["rank"], r["issue_id"], r["complaint_count"], r["severity_sum"], r["mean_severity"], r["priority_score"]])
    cols = ["rank", "issue_id", "name", "topic", "complaint_count", "severity_sum", "mean_severity", "priority_score",
            "cancellation_count", "severity_ge4_count", "needs_review_count"]
    with open(state_dir / "aggregates.csv", "w", newline="") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    topics = []
    for t in TOPICS:
        s = topic_stats[t]
        topics.append({"topic": t, "product_area": AREAS[t], "completed_records": s["records"], "complaints": s["complaints"],
                       "severity_sum": s["severity_sum"], "mean_severity": mean6(s["severity_sum"], s["complaints"]) if s["complaints"] else "",
                       "cancellation_count": s["cancellation"], "severity_ge4_count": s["sev_ge4"], "needs_review_count": s["needs_review"]})
    areas = defaultdict(Counter)
    for t in topics:
        a = areas[t["product_area"]]
        for k in ("complaints", "severity_sum", "cancellation_count", "severity_ge4_count"):
            a[k] += t[k]
    area_rows = sorted([{"product_area": k, **v, "mean_severity": mean6(v["severity_sum"], v["complaints"]) if v["complaints"] else ""}
                        for k, v in areas.items()], key=lambda x: (-x["severity_sum"], x["product_area"]))
    trend = [{"month": m, "completed_records": month_total[m],
              **{f"{t}_complaints": month_topic[m][t] for t in TOPICS},
              "partial_month": m in (min(month_total), max(month_total))} for m in sorted(month_total)]
    summary = {"record_status": dict(status), "completed": len(recs),
               "complaint_or_cancellation": sum(len(v) for v in members.values()), "issues": len(rows),
               "topics": topics, "product_areas": area_rows, "monthly_trend": trend}
    write_json(state_dir / "aggregates.json", summary)
    log_event(state_dir, "rank", issues=len(rows), top=[r["issue_id"] for r in rows[:5]])
    print(f"rank: {len(rows)} issues; top 5: " + ", ".join(f"{r['issue_id']}={r['priority_score']}" for r in rows[:5]))
    return rows, summary
