"""Stage 4 - Group. Code owns membership (one issue per complaint/cancellation record, keyed by subtopic);
the `group` model role only names/describes each issue from a bounded evidence pack. Outputs:
membership.csv, issues.json (accepted mapping + names), group_input.json (exact evidence pack sent)."""
import csv
import hashlib
import json
from collections import defaultdict

from . import config as C
from .common import SUBTOPIC_TOPIC, log_event, write_json
from .ingest import connect
from .llm import Client, InvalidOutput, Ledger
from .records import iter_records

EXAMPLES_PER_ISSUE = 6


def issue_id(subtopic):
    return f"ISS-{SUBTOPIC_TOPIC[subtopic]}-{subtopic}"


def build_membership(state_dir):
    members = defaultdict(list)
    for r in iter_records(state_dir, internal=True):
        if r["status"] == "completed" and r["intent"] in ("complaint", "cancellation"):
            members[issue_id(r["subtopic"])].append(r["review_id"])
    with open(state_dir / "membership.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["issue_id", "review_id"])
        for iid in sorted(members):
            for rid in members[iid]:
                w.writerow([iid, rid])
    return members


def schema(ids):
    return {"name": "issue_names", "schema": {"type": "object", "additionalProperties": False, "required": ["issues"],
            "properties": {"issues": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                "required": ["issue_id", "name", "description", "coherence", "note"],
                "properties": {"issue_id": {"type": "string", "enum": ids}, "name": {"type": "string"},
                               "description": {"type": "string"},
                               "coherence": {"type": "string", "enum": ["coherent", "mixed"]},
                               "note": {"type": "string"}}}}}}}


def run(state_dir, cfg, phase="initial"):
    members = build_membership(state_dir)
    db = connect(state_dir)
    pack = []
    for iid in sorted(members):
        ids = members[iid]
        # deterministic, bounded example choice; distinct texts only
        chosen, seen = [], set()
        for rid in sorted(ids, key=lambda x: hashlib.sha256(f"group:{x}".encode()).hexdigest()):
            text = db.execute("SELECT review_text FROM source WHERE review_id=?", (rid,)).fetchone()[0]
            if text in seen:
                continue
            seen.add(text)
            chosen.append({"review_id": rid, "text": text[:240]})
            if len(chosen) == EXAMPLES_PER_ISSUE:
                break
        sub = iid.split("-", 2)[2]
        pack.append({"issue_id": iid, "topic": SUBTOPIC_TOPIC[sub], "subtopic": sub, "member_count": len(ids),
                     "examples": chosen})
    write_json(state_dir / "group_input.json", pack)
    cache = state_dir / "issues.json"
    key = hashlib.sha256((json.dumps(pack, sort_keys=True) + C.prompt_text(cfg, "group") + json.dumps(cfg["roles"]["group"])).encode()).hexdigest()
    if cache.exists() and json.loads(cache.read_text()).get("input_key") == key:
        print("group: cached issue names reused (same inputs/config); 0 new calls")
        return json.loads(cache.read_text())
    client = Client(cfg, state_dir, Ledger(cfg["limits"]["spend_cap_usd"]), phase=phase)
    ids = [p["issue_id"] for p in pack]

    def validate(parsed):
        got = [x["issue_id"] for x in parsed.get("issues", [])]
        if sorted(set(got)) != sorted(ids):
            raise InvalidOutput(f"issue ids returned {len(set(got))} != {len(ids)}")

    def fake(_):
        return {"issues": [{"issue_id": i, "name": i, "description": "offline test", "coherence": "coherent", "note": ""} for i in ids]}
    try:
        parsed, meta = client.call("group", C.prompt_text(cfg, "group"), json.dumps(pack, ensure_ascii=False), schema(ids),
                                   [], None, validate, fake)
        names = {x["issue_id"]: x for x in parsed["issues"]}
        req = meta["request_id"]
    except InvalidOutput as e:
        print("group naming failed; falling back to code names:", e)
        names, req = {}, None
    issues = {"input_key": key, "request_id": req, "membership_rule": "issue = enrichment subtopic of each completed complaint/cancellation record; one issue per record",
              "issues": [{"issue_id": p["issue_id"], "topic": p["topic"], "subtopic": p["subtopic"], "member_count": p["member_count"],
                          "name": names.get(p["issue_id"], {}).get("name", p["subtopic"].replace("_", " ")),
                          "description": names.get(p["issue_id"], {}).get("description", ""),
                          "coherence": names.get(p["issue_id"], {}).get("coherence", "unknown"),
                          "note": names.get(p["issue_id"], {}).get("note", ""),
                          "example_review_ids": [e["review_id"] for e in p["examples"]]} for p in pack]}
    write_json(cache, issues)
    log_event(state_dir, "group", issues=len(pack), members=sum(len(v) for v in members.values()), request_id=req)
    print(f"group: {len(pack)} issues, {sum(len(v) for v in members.values())} memberships")
    return issues
