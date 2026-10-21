"""Stage 3 - Verify (model role `verify`, blind to enrichment output).

Code draws a seeded random sample of completed distinct texts, sends only the original text + rubric to a
separately prompted verifier, then compares field by field. Outputs verify_predictions.jsonl and
verify_report.json. A planted-error copy (flipped labels, synthetic, never exported) checks the comparator.
"""
import hashlib
import json
import time
from collections import Counter

from . import config as C
from .common import INTENTS, TOPICS, append_jsonl, log_event, write_json
from .enrich import shown
from .ingest import connect
from .llm import BudgetExceeded, Client, InvalidOutput, Ledger

SCHEMA = {"name": "verify_batch", "schema": {
    "type": "object", "additionalProperties": False, "required": ["results"],
    "properties": {"results": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["i", "topic", "intent", "severity"],
        "properties": {"i": {"type": "integer"}, "topic": {"type": "string", "enum": list(TOPICS)},
                       "intent": {"type": "string", "enum": list(INTENTS)},
                       "severity": {"type": "integer", "enum": [1, 2, 3, 4, 5]}}}}}}}


def fake_verify(user_input):
    out = []
    for line in user_input.splitlines():
        idx, _, text = line.partition("\t")
        bad = any(w in text.lower() for w in ("bad", "worst", "crash", "ads"))
        out.append({"i": int(idx), "topic": "other", "intent": "complaint" if bad else "praise", "severity": 2 if bad else 1})
    return {"results": out}


def sample(db, n, seed):
    rows = db.execute("SELECT w.text_key, w.rep_review_id, s.review_text, w.result_json FROM work w JOIN source s "
                      "ON s.review_id=w.rep_review_id WHERE w.status='completed'").fetchall()
    rows.sort(key=lambda r: hashlib.sha256(f"{seed}:{r[1]}".encode()).hexdigest())
    return rows[:n]


def compare(enriched, verified):
    """Pure code comparison. Returns per-field agreement and the disagreement list."""
    agree = Counter()
    sev_abs = 0
    dis = []
    for rid, e in enriched.items():
        v = verified.get(rid)
        if not v:
            continue
        agree["n"] += 1
        diffs = {}
        for f in ("topic", "intent"):
            if e[f] == v[f]:
                agree[f] += 1
            else:
                diffs[f] = [e[f], v[f]]
        if e["severity"] == v["severity"]:
            agree["severity"] += 1
        else:
            diffs["severity"] = [e["severity"], v["severity"]]
        sev_abs += abs(e["severity"] - v["severity"])
        agree["severity_within1"] += abs(e["severity"] - v["severity"]) <= 1
        agree["all3"] += not diffs
        if diffs:
            dis.append({"review_id": rid, "diffs": diffs})
    n = agree["n"] or 1
    return {"compared": agree["n"], "topic_agreement": round(agree["topic"] / n, 4),
            "intent_agreement": round(agree["intent"] / n, 4), "severity_exact": round(agree["severity"] / n, 4),
            "severity_within_1": round(agree["severity_within1"] / n, 4), "severity_mae": round(sev_abs / n, 4),
            "all_three_agree": round(agree["all3"] / n, 4), "disagreements": len(dis)}, dis


def run(state_dir, cfg, n=None, phase="initial"):
    t0 = time.time()
    db = connect(state_dir)
    vc = cfg["verification"]
    n = n or vc["sample_size"]
    rows = sample(db, n, vc["seed"])
    out_path = state_dir / "verify_predictions.jsonl"
    done = {}
    if out_path.exists():
        for line in out_path.open():
            d = json.loads(line)
            done[d["review_id"]] = d
    todo = [r for r in rows if r[1] not in done]
    ledger = Ledger(cfg["limits"]["spend_cap_usd"])
    client = Client(cfg, state_dir, ledger, phase=phase)
    instr = C.prompt_text(cfg, "verify")
    bs = cfg["roles"]["verify"]["batch_size"]
    for i in range(0, len(todo), bs):
        b = todo[i:i + bs]
        user = "\n".join(f"{k}\t{shown(r[2])}" for k, r in enumerate(b, 1))
        try:
            parsed, meta = client.call("verify", instr, user, SCHEMA, [r[1] for r in b], None, None, fake_verify)
        except (InvalidOutput, BudgetExceeded) as e:
            print("verify batch failed:", e)
            continue
        got = {it["i"]: it for it in parsed["results"] if isinstance(it.get("i"), int)}
        for k, r in enumerate(b, 1):
            if k in got:
                rec = {"review_id": r[1], "topic": got[k]["topic"], "intent": got[k]["intent"],
                       "severity": got[k]["severity"], "request_id": meta["request_id"],
                       "verify_config": f"{cfg['roles']['verify']['model']}+{cfg['roles']['verify']['prompt_version']}"}
                append_jsonl(out_path, rec)
                done[r[1]] = rec
    enriched = {r[1]: json.loads(r[3]) for r in rows}
    summary, dis = compare(enriched, done)
    # Disagreement detail with the text, for human investigation
    texts = {r[1]: r[2] for r in rows}
    detail = [{**d, "text": texts[d["review_id"]][:400], "enrich_quote": enriched[d["review_id"]]["evidence_quote"][:200]}
              for d in dis]
    conf = Counter((enriched[d["review_id"]]["topic"], done[d["review_id"]]["topic"]) for d in dis if "topic" in d["diffs"])
    summary.update(sample_seed=vc["seed"], sample_size=len(rows), sampled_from="completed distinct texts",
                   topic_confusions_top=[{"enrich": a, "verify": b, "n": c} for (a, b), c in conf.most_common(15)],
                   elapsed_s=round(time.time() - t0, 2), spent_usd=round(ledger.spent, 6))
    write_json(state_dir / "verify_report.json", {"summary": summary, "disagreements": detail})
    # Planted-error test: synthetic copy with deliberately wrong labels; comparator must flag every flipped topic.
    planted = {}
    flips = 0
    for k, (rid, e) in enumerate(list(enriched.items())[:40]):
        if rid not in done:
            continue
        e2 = dict(e)
        if k % 2 == 0:
            vt = done[rid]["topic"]
            e2["topic"] = next(t for t in TOPICS if t not in (vt, e["topic"]))  # wrong vs both labels
            flips += 1
        planted[rid] = e2
    ps, pdis = compare(planted, done)
    flagged = sum(1 for d in pdis if "topic" in d["diffs"] and planted[d["review_id"]]["topic"] != enriched[d["review_id"]]["topic"])
    write_json(state_dir / "planted_error_test.json", {"synthetic": True, "excluded_from_business_aggregates": True,
               "planted_topic_errors": flips, "planted_errors_flagged_by_comparator": flagged,
               "result": "pass" if flagged == flips else "fail", "comparison": ps})
    log_event(state_dir, "verify", **{k: v for k, v in summary.items() if k != "topic_confusions_top"})
    print("verify:", json.dumps({k: v for k, v in summary.items() if k != "topic_confusions_top"}))
    return summary
