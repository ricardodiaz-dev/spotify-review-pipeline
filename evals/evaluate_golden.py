#!/usr/bin/env python3
"""Compare pipeline predictions with the human-labeled golden 50 (offline, no model calls).

  python3 evals/evaluate_golden.py --labels evals/golden_50_labeled.csv --state state/full

Human labels are read ONLY here, after prediction; they are never model inputs.
Outputs: evals/golden_results.json (per-field metrics, confusion), evals/golden_cases.csv (per case pass/fail).
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.records import iter_records  # noqa: E402
from pipeline.common import TOPICS  # noqa: E402

SENT_TOL = 0.5  # predeclared sentiment tolerance


def alts(s):
    out = {}
    for part in (s or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out.setdefault(k.strip(), set()).add(v.strip())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default=str(ROOT / "evals/golden_50_labeled.csv"))
    ap.add_argument("--state", default=str(ROOT / "state/full"))
    ap.add_argument("--golden-csv", default=str(ROOT / "data/golden_50_to_label.csv"))
    a = ap.parse_args()
    gold = {r["review_id"]: r for r in csv.DictReader(open(a.labels, encoding="utf-8"))}
    texts = {r["review_id"]: r["review_text"] for r in csv.DictReader(open(a.golden_csv, encoding="utf-8"))}
    preds = {r["review_id"]: r for r in iter_records(Path(a.state), internal=True) if r["review_id"] in gold}
    tot = Counter()
    conf = Counter()
    cases = []
    for rid, g in gold.items():
        p = preds.get(rid, {})
        ok = p.get("status") == "completed"
        al = alts(g.get("alt_labels"))
        acc = {f: {g[f]} | al.get(f, set()) for f in ("topic", "intent", "severity")}
        row = {"review_id": rid, "text": texts.get(rid, "")[:200], "ambiguous": g.get("ambiguous") == "true"}
        for f in ("topic", "intent", "severity"):
            row[f"gold_{f}"] = g[f]
            row[f"pred_{f}"] = p.get(f, "<missing>")
            row[f"{f}_ok"] = ok and str(p.get(f)) in acc[f]
            tot[f] += row[f"{f}_ok"]
        if ok:
            d = abs(int(p["severity"]) - int(g["severity"]))
            tot["sev_abs"] += d
            tot["sev_n"] += 1
            sd = abs(float(p["sentiment"]) - float(g["sentiment"]))
            tot["sent_abs"] += sd
            tot["sent_ok"] += sd <= SENT_TOL
            row["pred_sentiment"], row["gold_sentiment"] = p["sentiment"], g["sentiment"]
            row["quote_exact_substring"] = p["evidence_quote"] in texts.get(rid, "")
            tot["quote_ok"] += row["quote_exact_substring"]
            row["pred_quote"] = p["evidence_quote"][:160]
            row["entities_unsupported"] = [e for e in p["entities"] if not e]  # code-matched terms; filled in by manual review
            row["pred_needs_review"] = p["needs_review"]
            nr_gold = g.get("needs_review") == "true" or g.get("ambiguous") == "true"
            tot["nr_tp"] += p["needs_review"] and nr_gold
            tot["nr_fp"] += p["needs_review"] and not nr_gold
            tot["nr_fn"] += (not p["needs_review"]) and nr_gold
        conf[(g["topic"], p.get("topic", "<missing>"))] += 1
        tot["joint"] += row["topic_ok"] and row["intent_ok"] and row["severity_ok"]
        tot["ambiguous"] += row["ambiguous"]
        row["notes"] = g.get("notes", "")
        cases.append(row)
    n = len(gold)
    res = {"n": n, "predictions_completed": sum(1 for r in preds.values() if r["status"] == "completed"),
           "topic_agreement": round(tot["topic"] / n, 4), "intent_agreement": round(tot["intent"] / n, 4),
           "severity_exact": round(tot["severity"] / n, 4), "joint_agreement": round(tot["joint"] / n, 4),
           "severity_mae": round(tot["sev_abs"] / max(tot["sev_n"], 1), 4),
           "sentiment_mae": round(tot["sent_abs"] / max(tot["sev_n"], 1), 4),
           f"sentiment_within_{SENT_TOL}": round(tot["sent_ok"] / max(tot["sev_n"], 1), 4),
           "quote_exact_substring_rate": round(tot["quote_ok"] / max(tot["sev_n"], 1), 4),
           "needs_review_vs_human_ambiguous": {"tp": tot["nr_tp"], "fp": tot["nr_fp"], "fn": tot["nr_fn"]},
           "ambiguous_cases": tot["ambiguous"],
           "gold_topic_counts": dict(Counter(g["topic"] for g in gold.values())),
           "gold_intent_counts": dict(Counter(g["intent"] for g in gold.values())),
           "topic_confusion": {gt: {pt: conf[(gt, pt)] for pt in list(TOPICS) + ["<missing>"] if conf[(gt, pt)]} for gt in TOPICS},
           "note": "Accepted labels include the human 'also acceptable' alternatives. 50 cases are a small diagnostic sample, not a population accuracy estimate."}
    out = ROOT / "evals"
    (out / "golden_results.json").write_text(json.dumps(res, indent=2) + "\n")
    with open(out / "golden_cases.csv", "w", newline="", encoding="utf-8") as f:
        keys = sorted({k for c in cases for k in c})
        w = csv.DictWriter(f, keys, lineterminator="\n")
        w.writeheader()
        w.writerows(cases)
    print(json.dumps({k: v for k, v in res.items() if k != "topic_confusion"}, indent=1))


if __name__ == "__main__":
    main()
