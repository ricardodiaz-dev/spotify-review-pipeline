"""Stage 6 - Recommend (model role `memo`). Input: saved ranking/aggregates + bounded evidence pack only.
Code pre-computes every citable number (claims C###, area facts A#), then checks the memo: every cited id exists,
every number in the prose matches an allowed value, every review_id is from the evidence pack. One corrective
retry; failures are recorded in memo_validation.json, never silently accepted."""
import csv
import hashlib
import json
import re

from . import config as C
from pathlib import Path

from .common import ROOT, log_event, write_json
from .ingest import connect
from .llm import Client, InvalidOutput, Ledger

TOP_ISSUES = 12
EVIDENCE_ISSUES = 6
EVIDENCE_PER_ISSUE = 3
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
REF_GROUP = re.compile(r"\[((?:C\d{3}|A\d+)(?:\s*,\s*(?:C\d{3}|A\d+))*)\]")


class _Refs:
    """Citations may be single ([C001]) or grouped ([A11, A16]); every id inside a group is checked."""
    @staticmethod
    def findall(text):
        return [i.strip() for g in REF_GROUP.findall(text) for i in g.split(",")]

    @staticmethod
    def sub(repl, text):
        return REF_GROUP.sub(repl, text)


REF = _Refs()
NUM = re.compile(r"(?<![\w-])\d[\d,]*(?:\.\d+)?%?")


def fmt_int(v):
    return f"{int(v):,}"


def build_inputs(state_dir):
    agg = json.loads((state_dir / "aggregates.json").read_text())
    rows = list(csv.DictReader(open(state_dir / "aggregates.csv")))
    claims, cid = [], 0
    for r in rows[:TOP_ISSUES]:
        for metric in ("complaint_count", "severity_sum", "mean_severity", "priority_score"):
            if metric == "severity_sum":
                continue  # identical to priority_score; cite the score instead
            cid += 1
            v = r[metric]
            claims.append({"claim_id": f"C{cid:03d}", "issue_id": r["issue_id"], "issue_name": r["name"], "metric": metric,
                           "value": v, "display": fmt_int(v) if metric != "mean_severity" else f"{float(v):.2f}"})
    facts = []
    total_c = agg["complaint_or_cancellation"]
    facts.append({"fact_id": "A1", "fact": "completed classified reviews", "display": fmt_int(agg["completed"])})
    facts.append({"fact_id": "A2", "fact": "complaint or cancellation reviews in issue groups", "display": fmt_int(total_c)})
    q = agg["record_status"].get("quarantined", 0)
    facts.append({"fact_id": "A3", "fact": "reviews quarantined or unresolved (includes any empty texts)", "display": fmt_int(q)})
    k = 4
    vr = state_dir / "verify_report.json"
    if vr.exists():
        v = json.loads(vr.read_text())["summary"]
        for label, val in (("independent verifier sample size", fmt_int(v["compared"])),
                           ("verifier topic agreement", f"{round(100 * v['topic_agreement'], 1)}%"),
                           ("verifier intent agreement", f"{round(100 * v['intent_agreement'], 1)}%"),
                           ("verifier severity exact agreement", f"{round(100 * v['severity_exact'], 1)}%")):
            facts.append({"fact_id": f"A{k}", "fact": label, "display": val}); k += 1
    gr = ROOT / "evals" / "golden_results.json"
    if gr.exists() and Path(state_dir).resolve().name == "full":
        g = json.loads(gr.read_text())
        for label, val in (("golden-50 human-label topic agreement", f"{round(100 * g['topic_agreement'], 1)}%"),
                           ("golden-50 intent agreement", f"{round(100 * g['intent_agreement'], 1)}%"),
                           ("golden-50 severity mean absolute error", str(g["severity_mae"]))):
            facts.append({"fact_id": f"A{k}", "fact": label, "display": val}); k += 1
    # Trend facts: comparable full-month periods, complaint share of completed classifications, with denominators
    areas_t = {"playback": ("playback", "downloads"), "usability": ("usability",), "billing/support": ("billing", "support"),
               "access": ("access",)}
    trend = {m["month"]: m for m in agg["monthly_trend"]}
    for label, months in (("Aug-Oct 2022", ("2022-08", "2022-09", "2022-10")), ("Aug-Oct 2023", ("2023-08", "2023-09", "2023-10"))):
        if all(m in trend for m in months):
            den = sum(trend[m]["completed_records"] for m in months)
            facts.append({"fact_id": f"A{k}", "fact": f"{label}: completed classified reviews (denominator)", "display": fmt_int(den)}); k += 1
            for area, ts in areas_t.items():
                num = sum(trend[m][f"{t}_complaints"] for m in months for t in ts)
                facts.append({"fact_id": f"A{k}", "fact": f"{label}: '{area}' complaints as share of classified reviews ({fmt_int(num)} complaints)",
                              "display": f"{round(100 * num / den, 1)}%"}); k += 1
                facts.append({"fact_id": f"A{k}", "fact": f"{label}: '{area}' complaint count", "display": fmt_int(num)}); k += 1
    last = sorted(trend)[-1]
    facts.append({"fact_id": f"A{k}", "fact": f"note: {last} is a partial month and is excluded from the trend comparison", "display": "n/a"}); k += 1
    for a in agg["product_areas"]:
        share = round(100 * a["complaints"] / total_c, 1) if total_c else 0
        for label, val in (("complaints", fmt_int(a["complaints"])), ("share of all complaints", f"{share}%"),
                           ("severity sum (priority score)", fmt_int(a["severity_sum"])),
                           ("mean severity", f"{float(a['mean_severity']):.2f}" if a["mean_severity"] else "n/a"),
                           ("severity 4-5 complaints", fmt_int(a["severity_ge4_count"])),
                           ("cancellation-intent reviews", fmt_int(a["cancellation_count"]))):
            facts.append({"fact_id": f"A{k}", "fact": f"product area '{a['product_area']}': {label}", "display": val})
            k += 1
    db = connect(state_dir)
    members = {}
    for row in csv.DictReader(open(state_dir / "membership.csv")):
        members.setdefault(row["issue_id"], []).append(row["review_id"])
    evidence = []
    for r in rows[:EVIDENCE_ISSUES]:
        cands = []
        for rid in sorted(members[r["issue_id"]], key=lambda x: hashlib.sha256(f"memo:{x}".encode()).hexdigest())[:400]:
            text, res = db.execute("SELECT s.review_text, w.result_json FROM source s JOIN work w ON w.text_key=s.text_key "
                                   "WHERE s.review_id=?", (rid,)).fetchone()
            lab = json.loads(res)
            if len(text.split()) >= 8 and not lab["needs_review"]:
                cands.append((-lab["severity"], rid, text, lab))
        cands.sort(key=lambda x: x[0])
        seen = set()
        for _, rid, text, lab in cands:
            if text in seen:
                continue
            seen.add(text)
            evidence.append({"issue_id": r["issue_id"], "review_id": rid, "intent": lab["intent"], "severity": lab["severity"],
                             "text": text[:300]})
            if sum(e["issue_id"] == r["issue_id"] for e in evidence) == EVIDENCE_PER_ISSUE:
                break
    return claims, facts, evidence


def allowed_numbers(claims, facts):
    ok = set()
    for c in claims:
        ok |= {c["display"], c["value"]}
    for f in facts:
        ok.add(f["display"])
    ok |= {str(i) for i in range(0, 11)} | {"2022", "2023", "50"}
    return ok


def check(memo, claims, facts, evidence):
    problems = []
    cids = {c["claim_id"] for c in claims} | {f["fact_id"] for f in facts}
    refs = REF.findall(memo)
    for r in refs:
        if r not in cids:
            problems.append(f"unknown citation [{r}]")
    ev_ids = {e["review_id"] for e in evidence}
    for u in UUID.findall(memo):
        if u not in ev_ids:
            problems.append(f"review_id not in evidence pack: {u}")
    known_issue = {c["issue_id"] for c in claims}
    for iid in re.findall(r"ISS-[a-z]+-[a-z_]+", memo):
        if iid not in known_issue and iid not in {e["issue_id"] for e in evidence}:
            problems.append(f"unknown issue id {iid}")
    stripped = UUID.sub(" ", REF.sub(" ", memo))
    stripped = re.sub(r"ISS-[a-z]+-[a-z_]+", " ", stripped)
    ok = allowed_numbers(claims, facts)
    for n in NUM.findall(stripped):
        if n not in ok and n.rstrip(".,") not in ok:
            problems.append(f"unsupported number {n}")
    # claim display values must sit next to the claim cited
    for c in claims:
        if f"[{c['claim_id']}]" in memo and c["display"] not in memo:
            problems.append(f"{c['claim_id']} cited without its value {c['display']}")
    return sorted(set(problems)), sorted(set(r for r in refs if r.startswith("C")))


def run(state_dir, cfg, phase="initial"):
    claims, facts, evidence = build_inputs(state_dir)
    issues = {}
    if (state_dir / "issues.json").exists():
        issues = {i["issue_id"]: i for i in json.loads((state_dir / "issues.json").read_text())["issues"]}
    pack = {"CLAIMS": [{k: c[k] for k in ("claim_id", "issue_id", "issue_name", "metric", "display")} for c in claims],
            "AREA_FACTS": [{"id": f["fact_id"], "fact": f["fact"], "value": f["display"]} for f in facts],
            "ISSUE_DESCRIPTIONS": [{"issue_id": c["issue_id"], "description": issues.get(c["issue_id"], {}).get("description", "")}
                                   for c in claims if c["metric"] == "complaint_count"],
            "EVIDENCE_PACK": evidence,
            "SEVERITY_SCALE": "1 none, 2 annoyance, 3 degraded, 4 core task blocked, 5 serious financial/privacy/data harm"}
    write_json(state_dir / "memo_input.json", pack)
    key = hashlib.sha256((json.dumps(pack, sort_keys=True) + C.prompt_text(cfg, "memo") + json.dumps(cfg["roles"]["memo"])).encode()).hexdigest()
    mv = state_dir / "memo_validation.json"
    if mv.exists() and json.loads(mv.read_text()).get("input_key") == key and (state_dir / "memo.md").exists():
        print("memo: cached memo reused (same inputs/config); 0 new calls")
        return
    client = Client(cfg, state_dir, Ledger(cfg["limits"]["spend_cap_usd"]), phase=phase)
    instr = C.prompt_text(cfg, "memo")
    user = json.dumps(pack, ensure_ascii=False, indent=1)
    memo, problems, cited = "", ["not generated"], []
    for attempt in range(2):
        try:
            memo, meta = client.call("memo", instr, user, None, [], None, None,
                                     lambda _: "## Recommendation\nOffline test memo [C001] " + claims[0]["display"])
        except InvalidOutput as e:
            problems = [f"call failed: {e}"]
            continue
        problems, cited = check(memo, claims, facts, evidence)
        if not problems:
            break
        user = user + "\n\nYOUR PREVIOUS DRAFT FAILED CODE CHECKS. Fix exactly these problems and rewrite the full memo:\n- " + "\n- ".join(problems)
    (state_dir / "memo.md").write_text(memo + "\n")
    with open(state_dir / "claims.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["claim_id", "issue_id", "metric", "value"])
        for c in claims:
            if c["claim_id"] in cited:
                w.writerow([c["claim_id"], c["issue_id"], c["metric"], c["value"]])
    with open(state_dir / "claims_all.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["claim_id", "issue_id", "issue_name", "metric", "value", "display"], lineterminator="\n")
        w.writeheader()
        w.writerows(claims)
    write_json(mv, {"input_key": key, "status": "pass" if not problems else "review_required", "problems": problems,
                    "cited_claims": cited, "attempts": attempt + 1})
    log_event(state_dir, "memo", status="pass" if not problems else "review_required", problems=problems[:10], cited=len(cited))
    print(f"memo: {'pass' if not problems else 'REVIEW REQUIRED'}; cited {len(cited)} claims; problems={problems[:5]}")
