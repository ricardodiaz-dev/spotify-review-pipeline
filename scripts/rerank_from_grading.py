#!/usr/bin/env python3
"""Regenerate the baseline ranking using ONLY grading/records.jsonl(.gz) + grading/membership.csv. No model, no key.

  python3 scripts/rerank_from_grading.py [--grading grading] [--out outputs/ranking_regenerated.csv]
Prints whether the result is byte-identical to grading/ranking.csv.
"""
import argparse, csv, gzip, io, json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--grading", default="grading")
ap.add_argument("--out", default="outputs/ranking_regenerated.csv")
a = ap.parse_args()
g = Path(a.grading)
p = g / "records.jsonl"
f = p.open(encoding="utf-8") if p.exists() else gzip.open(str(p) + ".gz", "rt", encoding="utf-8")
sev = {}
for line in f:
    r = json.loads(line)
    if r["status"] == "completed" and r["intent"] in ("complaint", "cancellation"):
        sev[r["review_id"]] = r["severity"]
members = {}
for row in csv.DictReader(open(g / "membership.csv")):
    members.setdefault(row["issue_id"], []).append(sev[row["review_id"]])
rows = sorted(((iid, len(v), sum(v)) for iid, v in members.items()), key=lambda x: (-x[2], x[0]))
buf = io.StringIO()
w = csv.writer(buf, lineterminator="\n")
w.writerow(["rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score"])
for i, (iid, n, s) in enumerate(rows, 1):
    w.writerow([i, iid, n, s, str((Decimal(s) / Decimal(n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)), s])
Path(a.out).parent.mkdir(parents=True, exist_ok=True)
Path(a.out).write_text(buf.getvalue())
same = buf.getvalue() == (g / "ranking.csv").read_text()
print(f"{len(rows)} issues ranked -> {a.out}; identical to {g}/ranking.csv: {same}")
