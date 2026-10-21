#!/usr/bin/env python3
"""Load saved pipeline outputs into Postgres (Neon) for the dashboard backend. No model calls.

  DATABASE_URL=... python3 scripts/load_db.py --state state/full

Tables (schema `spotify`): run_meta, records (one row per source review, incl. text + labels), issues, topics,
areas, monthly_trend, memo, claims, evidence, verify_summary, golden_summary.
"""
import argparse
import csv
import io
import json
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.common import load_env  # noqa: E402
from pipeline.ingest import connect  # noqa: E402
from pipeline.records import iter_records  # noqa: E402

DDL = """
DROP SCHEMA IF EXISTS spotify CASCADE;
CREATE SCHEMA spotify;
CREATE TABLE spotify.run_meta(k text PRIMARY KEY, v jsonb);
CREATE TABLE spotify.records(review_id text PRIMARY KEY, status text, reason text, topic text, subtopic text, intent text,
  severity smallint, sentiment real, needs_review boolean, evidence_quote text, cache_source_id text, review_text text,
  review_rating text, review_timestamp text, app_version text, issue_id text);
CREATE TABLE spotify.issues(rank int PRIMARY KEY, issue_id text UNIQUE, name text, description text, topic text, coherence text,
  complaint_count int, severity_sum int, mean_severity text, priority_score int, cancellation_count int,
  severity_ge4_count int, needs_review_count int);
CREATE TABLE spotify.topics(topic text PRIMARY KEY, product_area text, completed_records int, complaints int, severity_sum int,
  mean_severity text, cancellation_count int, severity_ge4_count int, needs_review_count int);
CREATE TABLE spotify.areas(product_area text PRIMARY KEY, complaints int, severity_sum int, mean_severity text,
  cancellation_count int, severity_ge4_count int);
CREATE TABLE spotify.monthly_trend(month text PRIMARY KEY, data jsonb);
CREATE TABLE spotify.memo(id int PRIMARY KEY, markdown text, validation jsonb, input jsonb);
CREATE TABLE spotify.claims(claim_id text PRIMARY KEY, issue_id text, issue_name text, metric text, value text, display text);
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(ROOT / "state/full"))
    a = ap.parse_args()
    load_env()
    st = Path(a.state)
    url = os.environ["DATABASE_URL"]
    src = connect(st)
    meta = {r[0]: r[1:] for r in src.execute("SELECT review_id, review_text, review_rating, review_timestamp, app_version FROM source")}
    issue_of = {}
    for row in csv.DictReader(open(st / "membership.csv")):
        issue_of[row["review_id"]] = row["issue_id"]
    with psycopg.connect(url, autocommit=False) as db:
        db.execute(DDL)
        buf = io.StringIO()
        w = csv.writer(buf)
        n = 0
        with db.cursor().copy("COPY spotify.records FROM STDIN WITH (FORMAT csv)") as cp:
            for r in iter_records(st, internal=True):
                text, rating, ts, appv = meta[r["review_id"]]
                c = r["status"] == "completed"
                w.writerow([r["review_id"], r["status"], r.get("reason", ""), r.get("topic", ""), r.get("subtopic", ""),
                            r.get("intent", ""), r.get("severity", "") if c else "", r.get("sentiment", "") if c else "",
                            ("t" if r["needs_review"] else "f") if c else "", r.get("evidence_quote", ""),
                            r.get("cache_source_id", ""), text, rating, ts, appv, issue_of.get(r["review_id"], "")])
                n += 1
                if n % 20000 == 0:
                    cp.write(buf.getvalue()); buf.seek(0); buf.truncate()
            cp.write(buf.getvalue())
        db.execute("UPDATE spotify.records SET severity=NULL WHERE status<>'completed'")
        db.execute("CREATE INDEX ON spotify.records(issue_id, severity DESC)")
        db.execute("CREATE INDEX ON spotify.records(topic, intent)")
        agg = json.loads((st / "aggregates.json").read_text())
        issues = {i["issue_id"]: i for i in json.loads((st / "issues.json").read_text())["issues"]}
        for r in csv.DictReader(open(st / "aggregates.csv")):
            i = issues.get(r["issue_id"], {})
            db.execute("INSERT INTO spotify.issues VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                       (int(r["rank"]), r["issue_id"], i.get("name") or r["name"], i.get("description", ""), r["topic"],
                        i.get("coherence", ""), int(r["complaint_count"]), int(r["severity_sum"]), r["mean_severity"],
                        int(r["priority_score"]), int(r["cancellation_count"]), int(r["severity_ge4_count"]), int(r["needs_review_count"])))
        for t in agg["topics"]:
            db.execute("INSERT INTO spotify.topics VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                       (t["topic"], t["product_area"], t["completed_records"], t["complaints"], t["severity_sum"], t["mean_severity"],
                        t["cancellation_count"], t["severity_ge4_count"], t["needs_review_count"]))
        for a_ in agg["product_areas"]:
            db.execute("INSERT INTO spotify.areas VALUES (%s,%s,%s,%s,%s,%s)",
                       (a_["product_area"], a_["complaints"], a_["severity_sum"], a_["mean_severity"], a_["cancellation_count"], a_["severity_ge4_count"]))
        for m in agg["monthly_trend"]:
            db.execute("INSERT INTO spotify.monthly_trend VALUES (%s,%s)", (m["month"], json.dumps(m)))
        db.execute("INSERT INTO spotify.memo VALUES (1,%s,%s,%s)", ((st / "memo.md").read_text(),
                   (st / "memo_validation.json").read_text(), (st / "memo_input.json").read_text()))
        plain = ROOT / "outputs" / "memo.md"
        if plain.exists() and (ROOT / "outputs" / "memo_validation.json").exists():
            db.execute("INSERT INTO spotify.memo VALUES (2,%s,%s,%s)", (plain.read_text(),
                       (ROOT / "outputs" / "memo_validation.json").read_text(), (st / "memo_input.json").read_text()))
        for c in csv.DictReader(open(st / "claims_all.csv")):
            db.execute("INSERT INTO spotify.claims VALUES (%s,%s,%s,%s,%s,%s)",
                       (c["claim_id"], c["issue_id"], c["issue_name"], c["metric"], c["value"], c["display"]))
        extras = {"record_status": agg["record_status"], "completed": agg["completed"],
                  "complaint_or_cancellation": agg["complaint_or_cancellation"], "issues": agg["issues"]}
        for name, path in (("ingestion", "ingestion_report.json"), ("verify", "verify_report.json"),
                           ("planted", "planted_error_test.json")):
            if (st / path).exists():
                v = json.loads((st / path).read_text())
                extras[name] = v.get("summary", v) if name == "verify" else v
        for name, path in (("golden", ROOT / "evals/golden_results.json"), ("system_tests", ROOT / "evals/system_tests.json"),
                           ("run_summary", st / "run_summary.json")):
            if Path(path).exists():
                extras[name] = json.loads(Path(path).read_text())
        for k, v in extras.items():
            db.execute("INSERT INTO spotify.run_meta VALUES (%s,%s)", (k, json.dumps(v)))
        db.commit()
    print(f"loaded {n} records + aggregates into spotify schema")


if __name__ == "__main__":
    main()
