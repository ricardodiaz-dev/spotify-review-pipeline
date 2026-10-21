#!/usr/bin/env python3
"""Orchestrator CLI. Stages run in fixed order under code control; each stage reads/writes saved artifacts in --state.

  python3 run.py all     --input data/cost_100.csv --state state/pilot      # paid: ingest->enrich->verify->group->rank->memo
  python3 run.py enrich  --state state/full --max-batches 40               # paid, bounded; Ctrl-C stops admitting work safely
  python3 run.py rank    --state state/full                                # offline: deterministic ranking from saved outputs
  python3 run.py export  --state state/full --input data/spotify_reviews_18months.csv --out grading
"""
import argparse
import sys
import time
from pathlib import Path

from pipeline import config as C
from pipeline.common import load_env, log_event


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["ingest", "enrich", "verify", "group", "rank", "memo", "export", "all"])
    ap.add_argument("--input", help="input CSV path (any CSV with the six source columns)")
    ap.add_argument("--state", required=True, help="state/output directory for this run")
    ap.add_argument("--workers", type=int)
    ap.add_argument("--max-batches", type=int, help="stop after N enrichment batches (bounded run / interruption demo)")
    ap.add_argument("--max-seconds", type=float)
    ap.add_argument("--limit", type=int, help="only the first N pending distinct texts")
    ap.add_argument("--verify-n", type=int)
    ap.add_argument("--spend-cap", type=float, help="override USD spend cap for this invocation")
    ap.add_argument("--out", default="grading")
    a = ap.parse_args()
    load_env()
    cfg = C.load()
    if a.spend_cap is not None:
        cfg["limits"]["spend_cap_usd"] = a.spend_cap
    state = Path(a.state)
    state.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    stages = ["ingest", "enrich", "verify", "group", "rank", "memo"] if a.stage == "all" else [a.stage]
    for s in stages:
        ts = time.time()
        if s == "ingest":
            from pipeline import ingest
            if not a.input:
                sys.exit("--input is required for ingest")
            ingest.run(a.input, state)
        elif s == "enrich":
            from pipeline.enrich import Enricher
            st = Enricher(state, cfg, a.workers, a.max_batches, a.max_seconds, limit=a.limit).run()
            if a.stage == "all" and st.get("pending"):
                sys.exit("enrichment incomplete (budget/time/interrupt); later stages not run. Re-run to resume.")
        elif s == "verify":
            from pipeline import verify
            verify.run(state, cfg, a.verify_n)
        elif s == "group":
            from pipeline import group
            group.run(state, cfg)
        elif s == "rank":
            from pipeline import rank
            rank.run(state)
        elif s == "memo":
            from pipeline import memo
            memo.run(state, cfg)
        elif s == "export":
            from pipeline import export
            export.run(state, a.out, a.input)
        log_event(state, "stage_time", name=s, elapsed_s=round(time.time() - ts, 3))
    log_event(state, "invocation", stages=stages, elapsed_s=round(time.time() - t0, 3))
    print(f"done: {stages} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
