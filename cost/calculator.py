#!/usr/bin/env python3
"""100-review cost & runtime calculator.

  python3 cost/calculator.py                 # DEFAULT: offline replay from saved usage + editable rates (no key, no calls)
  python3 cost/calculator.py replay --rates cost/rates.csv --assumptions cost/assumptions.json
  python3 cost/calculator.py pilot           # EXPLICIT PAID: real cold + warm run of the pipeline on data/cost_100.csv

Formulas: item_cost = billed_units x price_per_unit (price per 1M tokens / 1,000,000). Input categories are mutually
exclusive: uncached_input = input_tokens - cached_tokens - cache_write_tokens. Reasoning tokens are already inside
output_tokens and are not added again. Measured wall-clock comes from a clock around each run, not summed latencies.
"""
import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FULL = {"rows": 660622, "nonempty": 660609, "empty": 13, "distinct": 484189}


def load_rates(path):
    rates = {}
    for r in csv.DictReader(open(path)):
        rates.setdefault(r["model"], {})[r["item"]] = {"usd_per_unit": float(r["price"]) / float(r["per_units"]),
                                                       "unit": r["unit"], "source": r["source"], "checked": r["checked"]}
    return rates


def split_usage(c):
    u = c.get("usage") or {}
    inp = int(c.get("input_tokens") or 0)
    det = u.get("input_tokens_details") or {}
    cached = int(det.get("cached_tokens") or 0)
    write = int(det.get("cache_write_tokens") or det.get("cache_creation_tokens") or 0)
    out = int(c.get("output_tokens") or 0)
    reasoning = int((u.get("output_tokens_details") or {}).get("reasoning_tokens") or 0)
    return {"input_uncached": max(inp - cached - write, 0), "input_cached": cached, "input_cache_write": write,
            "output": out, "reasoning_within_output": reasoning}


def cost_of(model, units, rates):
    r = rates[model]
    items = {"input_uncached": "input", "input_cached": "cached_input", "input_cache_write": "cache_write", "output": "output"}
    return sum(units[k] * r[v]["usd_per_unit"] for k, v in items.items())


def replay(rates_path, assumptions_path, out_md):
    rates = load_rates(rates_path)
    A = json.load(open(assumptions_path))
    calls = [json.loads(l) for l in open(HERE / "pilot_calls.jsonl")]
    runs = json.load(open(HERE / "pilot_runs.json"))
    recs = [json.loads(l) for l in open(HERE / "pilot_records.jsonl")]
    usage_rows = []
    by = defaultdict(lambda: defaultdict(float))
    for c in calls:
        u = split_usage(c)
        cost = cost_of(c["model"], u, rates) if c["model"] in rates else None
        usage_rows.append({"run": c["pilot_run"], "request_id": c["request_id"], "role": c["role"], "model": c["model"],
                           "effort": c.get("effort"), "outcome": c["outcome"], "attempt": c.get("attempt"),
                           "n_reviews": len(c.get("review_ids", [])), **u,
                           "cost_usd": round(cost, 8) if cost is not None else "UNKNOWN", "latency_s": c.get("latency_s")})
        k = (c["pilot_run"], c["role"])
        b = by[k]
        b["requests"] += 1
        b["failed"] += c["outcome"] == "failed"
        b["reviews_sent"] += len(c.get("review_ids", []))
        for kk, v in u.items():
            b[kk] += v
        b["cost"] += cost or 0
        b["latency"] += c.get("latency_s") or 0
        b["model"] = c["model"]
        b["effort"] = c.get("effort")
        b["prompt_version"] = c.get("prompt_version")
    with open(HERE / "usage.csv", "w", newline="") as f:
        w = csv.DictWriter(f, list(usage_rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(usage_rows)
    completed = sum(r["status"] == "completed" for r in recs)
    failed = sum(r["status"] != "completed" for r in recs)
    cold = {r: by[("cold", r)] for r in ("enrich", "verify", "group", "memo")}
    warm = {r: by[("warm", r)] for r in ("enrich", "verify", "group", "memo")}
    cold_cost = sum(b["cost"] for b in cold.values())
    warm_cost = sum(b["cost"] for b in warm.values())
    ce = cold["enrich"]
    texts_sent = max(ce["reviews_sent"], 1)
    # ---- projection (per-stage, own work counts) ----
    per_text_cost = ce["cost"] / texts_sent
    per_text_unc = ce["input_uncached"] / texts_sent
    per_text_out = ce["output"] / texts_sent
    per_req_cached = ce["input_cached"] / max(ce["requests"], 1)
    per_text_write = ce["input_cache_write"] / texts_sent  # provider bills review content as cache writes
    r_l = rates[ce["model"] or "gpt-6-luna"]
    cv = cold["verify"]
    verify_per_review = cv["cost"] / max(cv["reviews_sent"], 1)
    fixed = cold["group"]["cost"] + cold["memo"]["cost"]
    measured_retry = ce["failed"] / max(ce["requests"], 1)
    enrich_tput = texts_sent / max(runs["cold"]["stage_seconds"].get("enrich", 1), 1e-9)  # texts/s, 1 worker
    fb = A["fallback"]
    fb_rates = rates.get(fb["model"])
    scenarios = []
    for name, sc in A["scenarios"].items():
        for reuse in (True, False):
            n = FULL["distinct"] if reuse else FULL["nonempty"]
            reqs = math.ceil(n / A["batch_size"])
            enrich = (n * (per_text_unc * r_l["input"]["usd_per_unit"] + per_text_write * r_l["cache_write"]["usd_per_unit"]
                           + per_text_out * r_l["output"]["usd_per_unit"])
                      + reqs * per_req_cached * r_l["cached_input"]["usd_per_unit"])
            enrich *= (1 + max(measured_retry, sc["retry_rate"]))
            verify = A["verify_sample"] * verify_per_review * (1 + sc["retry_rate"])
            fallback = 0.0
            if sc["fallback_fraction"] > 0:
                if fb_rates:
                    fallback = n * sc["fallback_fraction"] * ((per_text_unc + per_text_write + per_req_cached / A["batch_size"]) * fb_rates["input"]["usd_per_unit"]
                                                              + per_text_out * fb_rates["output"]["usd_per_unit"])
                else:
                    fallback = float("nan")
            fixed_s = fixed * sc["fixed_overhead_multiplier"]
            total = enrich + verify + fallback + fixed_s
            secs = n / (enrich_tput * A["max_workers"] * sc["parallel_efficiency"]) * (1 + sc["retry_rate"])
            scenarios.append({"scenario": name, "exact_text_reuse": reuse, "texts_to_enrich": n, "requests": reqs,
                              "enrich_usd": enrich, "verify_usd": verify, "fallback_usd": fallback, "group_memo_usd": fixed_s,
                              "total_api_usd": total, "est_hours": secs / 3600, "over_budget": total > A["spend_limit_usd"]})
    # ---- report ----
    L = []
    L.append("# 100-review cost & runtime calculator — measured pilot + full-run projection\n")
    L.append(f"Generated offline by `python3 cost/calculator.py` from `pilot_calls.jsonl`, `pilot_runs.json`, `rates.csv`, `assumptions.json`. No API key or model call is used.\n")
    L.append("## Measured on cost_100.csv\n")
    L.append(f"- Input: `data/cost_100.csv`, sha256 `{runs['input_sha256']}` ({runs['ids']} IDs; manifest checksum match: {runs['checksum_ok']})")
    L.append(f"- Records: {completed} completed, {failed} failed/quarantined; unique texts {runs['unique_texts']}; result-cache hits cold={runs['cold']['cache_hits']}, warm={runs['warm']['cache_hits']}")
    L.append(f"- Workers: {runs['workers']} (cold and warm); batch size {A['batch_size']}; service tier: standard (no Batch API)")
    L.append(f"- Wall clock: **cold {runs['cold']['wall_s']:.1f} s**, **warm {runs['warm']['wall_s']:.1f} s** (clock around the whole run)")
    L.append(f"- API cost: **cold ${cold_cost:.6f}**, **warm ${warm_cost:.6f}** (incremental). Cost per 1,000 input rows (cold): ${cold_cost * 10:.4f}; per completed record: ${cold_cost / max(completed, 1):.6f}")
    L.append(f"- Enrichment throughput (cold, 1 worker): {enrich_tput:.2f} texts/s\n")
    L.append("| run | role | model | effort | prompt | requests | failed | reviews sent | uncached in | cached in | cache-write in | output (reasoning incl.) | cost USD | summed latency s |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for (run, role), b in sorted(by.items()):
        if not b["requests"]:
            L.append(f"| {run} | {role} | — | — | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 (0) | 0.000000 | 0.0 |")
            continue
        L.append(f"| {run} | {role} | {b['model']} | {b['effort']} | {b['prompt_version']} | {int(b['requests'])} | {int(b['failed'])} | {int(b['reviews_sent'])} | "
                 f"{int(b['input_uncached'])} | {int(b['input_cached'])} | {int(b['input_cache_write'])} | {int(b['output'])} ({int(b['reasoning_within_output'])}) | {b['cost']:.6f} | {b['latency']:.1f} |")
    for run in ("warm",):
        if not any(k[0] == run for k in by):
            L.append(f"| {run} | all | — | — | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.000000 | 0 |")
    L.append(f"\nWarm run: {int(warm['enrich']['requests'])} enrichment calls, {int(sum(b['requests'] for b in warm.values()))} calls in total (downstream group/memo/verify reuse cached artifacts keyed by input + config).\n")
    L.append("Stage wall-clock seconds (cold): " + ", ".join(f"{k} {v:.2f}" for k, v in runs["cold"]["stage_seconds"].items()))
    L.append("\nStage wall-clock seconds (warm): " + ", ".join(f"{k} {v:.2f}" for k, v in runs["warm"]["stage_seconds"].items()))
    L.append("\n## Rates used (editable `cost/rates.csv`)\n")
    L.append("| model | item | price | unit | source | checked |\n|---|---|---|---|---|---|")
    for m, items in rates.items():
        for it, r in items.items():
            L.append(f"| {m} | {it} | ${r['usd_per_unit'] * 1e6:.4f} | per 1M {r['unit']} | {r['source']} | {r['checked']} |")
    L.append("\nLocal compute: the pipeline runs on a laptop CPU (SQLite + Python); its cost is not metered and is reported as **unknown (not zero)**. Hosting: Neon free tier + Vercel hobby, $0 list price at this scale.\n")
    L.append("## Full-run projection (660,622 rows; 660,609 nonempty; 13 empty quarantined)\n")
    L.append(f"Controls (editable `cost/assumptions.json`): spend limit **${A['spend_limit_usd']}**, output cap {A['max_output_tokens']} tokens/request, max workers {A['max_workers']}, declared max fallback fraction {A['fallback']['max_fraction']} ({A['fallback']['model']}), verification sample {A['verify_sample']}.")
    L.append(f"Per-text measurements used: {per_text_unc:.1f} uncached input tok, {per_text_write:.1f} cache-write input tok, {per_text_out:.1f} output tok, {per_req_cached:.0f} cached prompt tok per request; measured enrich failure rate {measured_retry:.3f}. Group+memo are fixed overhead counted once.\n")
    L.append("| scenario | exact-text reuse | texts | requests | enrich $ | verify $ | fallback $ | group+memo $ | **total API $** | est. hours | budget |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for s in scenarios:
        L.append(f"| {s['scenario']} | {'yes' if s['exact_text_reuse'] else 'no'} | {s['texts_to_enrich']:,} | {s['requests']:,} | {s['enrich_usd']:.2f} | {s['verify_usd']:.3f} | "
                 f"{s['fallback_usd']:.2f} | {s['group_memo_usd']:.3f} | **{s['total_api_usd']:.2f}** | {s['est_hours']:.2f} | {'**EXCEEDS BUDGET**' if s['over_budget'] else 'ok'} |")
    L.append("\nHours are modeled (measured 1-worker throughput × workers × parallel efficiency), not measured. Batch-API (50% off) is not used; it would be an estimate only.")
    out_md.write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return scenarios


def pilot():
    """EXPLICIT PAID COMMAND. Cold: fresh state, 1 worker, all stages. Warm: same state again (must make 0 enrich calls)."""
    sys.path.insert(0, str(ROOT))
    from pipeline.common import file_sha, read_json
    inp = ROOT / "data" / "cost_100.csv"
    sha = file_sha(inp)
    manifest = json.load(open(ROOT / "data" / "manifest.json"))
    state = ROOT / "state" / "pilot"
    if state.exists():
        shutil.rmtree(state)  # empty result cache for the cold experiment
    runs = {"input_sha256": sha, "checksum_ok": sha == manifest["files"]["cost_100.csv"]["sha256"], "workers": 1}
    for phase in ("cold", "warm"):
        n_before = sum(1 for _ in open(state / "calls_raw.jsonl")) if (state / "calls_raw.jsonl").exists() else 0
        t0 = time.time()
        stage_s = {}
        for stage in ("ingest", "enrich", "verify", "group", "rank", "memo"):
            ts = time.time()
            subprocess.run([sys.executable, str(ROOT / "run.py"), stage, "--input", str(inp), "--state", str(state),
                            "--workers", "1", "--verify-n", "20"], check=True, cwd=ROOT)
            stage_s[stage] = round(time.time() - ts, 3)
        wall = time.time() - t0
        lines = open(state / "calls_raw.jsonl").read().splitlines()[n_before:]
        runs[phase] = {"wall_s": round(wall, 3), "stage_seconds": stage_s, "calls": len(lines)}
        with open(HERE / "pilot_calls.jsonl", "a" if phase == "warm" else "w") as f:
            for l in lines:
                c = json.loads(l)
                c["pilot_run"] = phase
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
    from pipeline.records import iter_records
    recs = list(iter_records(state))
    import sqlite3
    db = sqlite3.connect(state / "state.db")
    runs["unique_texts"] = db.execute("SELECT COUNT(*) FROM work").fetchone()[0]
    runs["ids"] = len(recs)
    runs["cold"]["cache_hits"] = sum(1 for r in recs if r.get("cache_source_id"))
    runs["warm"]["cache_hits"] = sum(1 for r in recs if r["status"] == "completed")  # all served from saved results
    with open(HERE / "pilot_records.jsonl", "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    for name in ("verify_report.json", "memo.md", "ranking.csv", "run_log.jsonl"):
        shutil.copy(state / name, HERE / f"pilot_{name}")
    json.dump(runs, open(HERE / "pilot_runs.json", "w"), indent=2)
    print(json.dumps(runs, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="replay", choices=["replay", "pilot"])
    ap.add_argument("--rates", default=str(HERE / "rates.csv"))
    ap.add_argument("--assumptions", default=str(HERE / "assumptions.json"))
    ap.add_argument("--out", default=str(HERE / "report.md"))
    a = ap.parse_args()
    if a.cmd == "pilot":
        pilot()
    replay(Path(a.rates), Path(a.assumptions), Path(a.out))
