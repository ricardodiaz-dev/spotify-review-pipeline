#!/bin/bash
# Interruption/resume demonstration for the full run (record this terminal).
cd "$(dirname "$0")/.."
status() {
  python3 - <<'PY'
import sqlite3, json, glob
d = sqlite3.connect("state/full/state.db")
print("  distinct-text status:", dict(d.execute("select status, count(*) from work group by status").fetchall()))
print("  enrichment calls logged so far:", sum(1 for _ in open("state/full/calls_raw.jsonl")))
for f in sorted(glob.glob("state/full/checkpoints/*.json")):
    j = json.load(open(f)); print(f"  checkpoint {f.split('/')[-1]}: {j['completed_count']} completed review IDs, stop={j['stop_reason']}")
PY
}
echo "== 1. Saved state after the first (interrupted) invocation =="; status
echo; echo "== 2. Resume: only pending texts are dispatched; completed IDs are never re-sent =="
echo "   (this resume is interrupted again after 60 s by its time limit; Ctrl-C would stop it the same safe way)"
python3 -u run.py enrich --state state/full --workers 32 --max-seconds 60
echo; echo "== 3. State after resume: more completed, nothing lost =="; status
python3 - <<'PY'
import json
calls = [json.loads(l) for l in open("state/full/calls_raw.jsonl")]
init = {i for c in calls if c["role"] == "enrich" and c["phase"] == "initial" and c["outcome"] == "succeeded" for i in c["review_ids"]}
res = [i for c in calls if c["role"] == "enrich" and c["phase"] == "resume" for i in c["review_ids"]]
print(f"  resume-phase review IDs sent: {len(res)}; overlap with initial-phase completed IDs: {len(init & set(res))}")
PY
