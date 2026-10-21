#!/usr/bin/env python3
"""Summarise a run from saved logs only (no model calls): calls, attempts, failures, usage, cost, wall time, statuses.

  python3 scripts/run_summary.py --state state/full
Writes <state>/run_summary.json.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline import config as C  # noqa: E402
from pipeline.common import file_sha, write_json  # noqa: E402
from pipeline.ingest import connect  # noqa: E402
from pipeline.llm import usage_cost  # noqa: E402


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(ROOT / "state/full"))
    st = Path(ap.parse_args().state)
    cfg = C.load()
    calls = [json.loads(l) for l in open(st / "calls_raw.jsonl")]
    by = defaultdict(Counter)
    for c in calls:
        b = by[(c["role"], c["phase"])]
        b["attempts"] += 1
        b["succeeded"] += c["outcome"] == "succeeded"
        b["failed"] += c["outcome"] != "succeeded"
        b["reviews_sent"] += len(c["review_ids"])
        u = c.get("usage") or {}
        d = u.get("input_tokens_details") or {}
        b["input_tokens"] += c.get("input_tokens") or 0
        b["cached_tokens"] += d.get("cached_tokens") or 0
        b["cache_write_tokens"] += d.get("cache_write_tokens") or 0
        b["output_tokens"] += c.get("output_tokens") or 0
        b["reasoning_tokens"] += (u.get("output_tokens_details") or {}).get("reasoning_tokens") or 0
        b["cost_usd_micro"] += round((usage_cost(cfg["prices_per_mtok"][c["model"]], u) if u else 0) * 1e6)
    log = [json.loads(l) for l in open(st / "run_log.jsonl")]
    enr = [e for e in log if e["stage"] in ("enrich_start", "enrich_end")]
    inv = [e for e in log if e["stage"] == "enrich_end"]
    errors = Counter((c.get("error") or "").split(":")[0] for c in calls if c["outcome"] != "succeeded")
    db = connect(st)
    work = dict(db.execute("SELECT status, COUNT(*) FROM work GROUP BY status").fetchall())
    reasons = dict(db.execute("SELECT reason, COUNT(*) FROM work WHERE status='quarantined' GROUP BY reason").fetchall())
    first, last = ts(calls[0]["ts"]), ts(calls[-1]["ts"])
    total_cost = sum(b["cost_usd_micro"] for b in by.values()) / 1e6
    out = {"state": st.name, "input_sha256": db.execute("SELECT v FROM meta WHERE k='input_sha256'").fetchone()[0],
           "code_version": "git HEAD at export (see README)", "label_config": C.label_config(cfg),
           "models": sorted({c["model"] for c in calls}), "roles_config": cfg["roles"], "limits": cfg["limits"],
           "prices_per_mtok": cfg["prices_per_mtok"], "service_tier": "standard",
           "by_role_phase": {f"{r}/{p}": {k: (v / 1e6 if k == "cost_usd_micro" else v) for k, v in b.items()} for (r, p), b in sorted(by.items())},
           "enrich_requests": sum(b["attempts"] for (r, _), b in by.items() if r == "enrich"),
           "failed_attempts": sum(b["failed"] for b in by.values()), "failure_reasons": dict(errors),
           "input_tokens": sum(b["input_tokens"] for b in by.values()), "output_tokens": sum(b["output_tokens"] for b in by.values()),
           "api_cost_usd": round(total_cost, 4), "cost_note": "computed from logged provider usage x rates in config.json (standard tier); not a provider invoice",
           "enrich_invocations": [{k: e.get(k) for k in ("phase", "elapsed_s", "batches", "stop_reason", "spent_usd", "work_status")} for e in inv],
           "enrich_wall_seconds_sum": round(sum(e["elapsed_s"] for e in inv), 1),
           "first_call": calls[0]["ts"], "last_call": calls[-1]["ts"],
           "wall_hours": round(sum(e["elapsed_s"] for e in inv) / 3600, 3),
           "span_hours_first_to_last_call": round((last - first).total_seconds() / 3600, 3),
           "distinct_text_status": work, "quarantine_reasons": reasons}
    write_json(st / "run_summary.json", out)
    print(json.dumps({k: out[k] for k in ("enrich_requests", "failed_attempts", "input_tokens", "output_tokens", "api_cost_usd",
                                          "wall_hours", "distinct_text_status", "quarantine_reasons", "failure_reasons")}, indent=1))


if __name__ == "__main__":
    main()
