"""Writes the standardized grading/ folder from saved state (code only, no model)."""
import gzip
import os
import json
import shutil
from pathlib import Path

from .common import file_sha, read_json, write_json
from .records import iter_records


def run(state_dir, out_dir, input_csv, compress=True):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "run.json", {"version": "a5-audit-v1", "analysis_count": sum(1 for _ in iter_records(state_dir)),
                                  "analysis_sha256": file_sha(input_csv), "classification_input_fields": ["review_text"],
                                  "allow_multi_issue": False})
    opener = (lambda p: gzip.open(str(p) + ".gz", "wt", encoding="utf-8")) if compress else (lambda p: open(p, "w", encoding="utf-8"))
    for name in ("records.jsonl", "calls.jsonl"):
        for p in (out / name, out / (name + ".gz")):
            if p.exists():
                p.unlink()
    with opener(out / "records.jsonl") as f:
        for r in iter_records(state_dir):
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    seen = set()
    with opener(out / "calls.jsonl") as f:
        for line in open(state_dir / "calls_raw.jsonl", encoding="utf-8"):
            c = json.loads(line)
            if c["model"] == "FAKE-OFFLINE-TEST" and os.environ.get("PIPELINE_FAKE") != "1":
                continue
            rid = c.get("request_id") or "local"
            while rid in seen:
                rid += "#dup"
            seen.add(rid)
            f.write(json.dumps({"request_id": rid, "role": c["role"], "review_ids": c["review_ids"], "model": c["model"],
                                "phase": c["phase"], "outcome": c["outcome"], "label_config": c.get("label_config"),
                                "input_tokens": int(c.get("input_tokens") or 0), "output_tokens": int(c.get("output_tokens") or 0),
                                "attempt": c.get("attempt"), "effort": c.get("effort"), "prompt_version": c.get("prompt_version"),
                                "cost_usd_at_standard_rates": c.get("cost_usd"), "latency_s": c.get("latency_s"),
                                "error": c.get("error"), "ts": c.get("ts"), "run_id": c.get("run_id")},
                               ensure_ascii=False, sort_keys=True) + "\n")
    for name in ("membership.csv", "ranking.csv", "claims.csv"):
        shutil.copy(state_dir / name, out / name)
    snaps = sorted((state_dir / "checkpoints").glob("invocation_*.json"))
    if len(snaps) >= 2:
        write_json(out / "checkpoint_before.json", {"completed_ids": read_json(snaps[0])["completed_ids"],
                                                    "source": snaps[0].name})
        write_json(out / "checkpoint_after.json", {"completed_ids": read_json(snaps[-1])["completed_ids"],
                                                   "source": snaps[-1].name})
    print(f"export: grading folder written to {out}")
