"""Stage 2 - Enrich (model role `enrich`, code-controlled).

Code: builds bounded requests (<=50 distinct texts), validates every returned index/ID, derives the exact
evidence quote and entities deterministically, saves each batch atomically in SQLite, retries invalid items
once, then quarantines. Model: topic / intent / severity / sentiment / subtopic / quote anchor / needs_review.
"""
import concurrent.futures as cf
import json
import re
import signal
import threading
import time

from . import config as C
from .common import ALL_SUBTOPICS, INTENTS, SUBTOPICS, SUBTOPIC_TOPIC, TOPICS, log_event, now_iso
from .ingest import connect
from .llm import BudgetExceeded, Client, InvalidOutput, Ledger

SCHEMA = {"name": "enrich_batch", "schema": {
    "type": "object", "additionalProperties": False, "required": ["results"],
    "properties": {"results": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["i", "t", "n", "s", "m", "u", "q", "r"],
        "properties": {
            "i": {"type": "integer"}, "t": {"type": "string", "enum": list(TOPICS)},
            "n": {"type": "string", "enum": list(INTENTS)}, "s": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
            "m": {"type": "integer", "enum": [-2, -1, 0, 1, 2]}, "u": {"type": "string", "enum": ALL_SUBTOPICS},
            "q": {"type": "string"}, "r": {"type": "boolean"}}}}}}}

ENTITY_TERMS = {
    "ads": r"\bads?\b|advert", "shuffle": r"shuffl", "skip": r"\bskip", "lyrics": r"lyric", "podcast": r"podcast",
    "audiobook": r"audiobook", "offline": r"offline", "download": r"download", "premium": r"premium",
    "login": r"log ?in|sign ?in|password", "playlist": r"playlist", "queue": r"\bqueue", "bluetooth": r"bluetooth",
    "android auto": r"android auto", "car": r"\bcar\b", "widget": r"widget", "smartwatch": r"wear ?os|watch",
    "spotify connect": r"spotify connect|\bconnect\b", "chromecast": r"chromecast|cast", "family plan": r"family",
    "student plan": r"student", "wrapped": r"wrapped", "dj": r"\bdj\b", "update": r"updat", "notification": r"notification",
    "battery": r"battery", "price": r"price|expensive|cost", "refund": r"refund", "search": r"search",
    "recommendations": r"recommend", "crash": r"crash", "lock screen": r"lock ?screen",
}
ENTITY_RE = {k: re.compile(v, re.IGNORECASE) for k, v in ENTITY_TERMS.items()}
SENT_END = re.compile(r"[.!?\n]")


def entities(text):
    return [k for k, rx in ENTITY_RE.items() if rx.search(text)]


def shown(text):
    return text.replace("\t", " ").replace("\r\n", " ⏎ ").replace("\n", " ⏎ ")


def find_anchor(text, q):
    q = q.strip().replace(" ⏎ ", " ").replace("⏎", " ")
    if not q:
        return None
    i = text.find(q)
    if i >= 0:
        return i, i + len(q)
    low = text.lower()
    if len(low) == len(text):
        i = low.find(q.lower())
        if i >= 0:
            return i, i + len(q)
    pattern = r"\s+".join(re.escape(tok) for tok in q.split())
    m = re.search(pattern, text, re.IGNORECASE)
    return (m.start(), m.end()) if m else None


def sentence_around(text, a, b, cap=300):
    start = 0
    for m in SENT_END.finditer(text, 0, a):
        start = m.end()
    m = SENT_END.search(text, b)
    end = m.end() if m else len(text)
    s = text[start:end].strip()
    if not s or len(s) > cap:
        s = text[a:b].strip()
    return s


def derive_quote(text, q):
    """Returns (quote, problem). Quote is always an exact substring of text."""
    if len(text.split()) <= 30:
        return text.strip(), None
    span = find_anchor(text, q)
    if span:
        return sentence_around(text, *span), None
    m = SENT_END.search(text)
    first = text[: m.end() if m else len(text)].strip()[:300].strip() or text.strip()[:300].strip()
    return first, "quote_anchor_not_found"


def postprocess(item, text, lc):
    topic, sub = item["t"], item["u"]
    review = bool(item["r"])
    reasons = []
    if SUBTOPIC_TOPIC.get(sub) != topic:  # code keeps taxonomy consistent; model cannot invent groups
        sub = SUBTOPICS[topic][-1]
        reasons.append("subtopic_topic_mismatch")
    quote, problem = derive_quote(text, item["q"])
    if problem:
        reasons.append(problem)
        review = True
    if item["r"]:
        reasons.append("model_flagged")
    return {"topic": topic, "intent": item["n"], "sentiment": item["m"] / 2, "severity": item["s"], "subtopic": sub,
            "entities": entities(text), "evidence_quote": quote, "needs_review": review, "review_reasons": reasons,
            "label_config": lc}


def fake_labels(user_input):
    """Deterministic offline stand-in used ONLY for code tests (PIPELINE_FAKE=1); never exported as real results."""
    out = []
    for line in user_input.splitlines():
        idx, _, text = line.partition("\t")
        low = text.lower()
        t, u, n, s, m = "other", "general_positive", "praise", 1, 1
        if any(w in low for w in ("crash", "not working", "stops")):
            t, u, n, s, m = "playback", "crash_or_wont_open", "complaint", 4, -2
        elif "ads" in low:
            t, u, n, s, m = "usability", "ads_interruptions", "complaint", 2, -1
        elif any(w in low for w in ("bad", "worst", "hate")):
            t, u, n, s, m = "other", "general_negative", "complaint", 2, -2
        out.append({"i": int(idx), "t": t, "n": n, "s": s, "m": m, "u": u, "q": " ".join(text.split()[:5]), "r": False})
    return {"results": out}


class Enricher:
    def __init__(self, state_dir, cfg, workers=None, max_batches=None, max_seconds=None, phase=None, limit=None):
        self.state_dir, self.cfg = state_dir, cfg
        self.db = connect(state_dir)
        self.lc = C.label_config(cfg)
        self.instructions = C.prompt_text(cfg, "enrich").replace(
            "{SUBTOPICS}", "; ".join(f"{t}: {', '.join(v)}" for t, v in SUBTOPICS.items()))
        self.workers = workers or cfg["limits"]["max_workers"]
        self.max_batches, self.max_seconds, self.limit = max_batches, max_seconds, limit
        n_prev = int((self.db.execute("SELECT v FROM meta WHERE k='enrich_invocations'").fetchone() or ["0"])[0])
        self.phase = phase or ("initial" if n_prev == 0 else "resume")
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('enrich_invocations', ?)", (str(n_prev + 1),))
        spent = float((self.db.execute("SELECT v FROM meta WHERE k='spent_usd'").fetchone() or ["0"])[0])
        self.ledger = Ledger(cfg["limits"]["spend_cap_usd"], spent)
        self.client = Client(cfg, state_dir, self.ledger, phase=self.phase)
        self.stop = threading.Event()
        self.stop_reason = None

    def pending(self):
        sql = ("SELECT w.text_key, w.rep_review_id, s.review_text, w.attempts FROM work w JOIN source s "
               "ON s.review_id = w.rep_review_id WHERE w.status='pending' ORDER BY s.row_idx")
        if self.limit:
            sql += f" LIMIT {int(self.limit)}"
        return self.db.execute(sql).fetchall()

    def call_batch(self, batch):
        bs = self.cfg["roles"]["enrich"]["batch_size"]
        assert 1 <= len(batch) <= min(bs, 50)
        user = "\n".join(f"{n}\t{shown(text)}" for n, (_, _, text, _) in enumerate(batch, 1))
        ids = [rid for _, rid, _, _ in batch]

        def validate(parsed):
            if not isinstance(parsed, dict) or not isinstance(parsed.get("results"), list) or not parsed["results"]:
                raise InvalidOutput("missing results array")
        try:
            parsed, meta = self.client.call("enrich", self.instructions, user, SCHEMA, ids, self.lc, validate, fake_labels)
            return batch, parsed, meta, None
        except InvalidOutput as e:
            return batch, None, None, str(e)

    def commit(self, batch, parsed, meta, err, final_try):
        """Validate every returned index, save good items, return items needing a retry. One transaction per batch."""
        good, bad = {}, {}
        if parsed:
            seen = {}
            for item in parsed["results"]:
                k = item.get("i")
                if not isinstance(k, int) or not 1 <= k <= len(batch):
                    continue  # unknown index -> ignored (logged via missing)
                if k in seen:
                    bad[k] = "duplicate_index_in_output"
                    continue
                seen[k] = item
            for k in range(1, len(batch) + 1):
                if k in bad:
                    continue
                if k not in seen:
                    bad[k] = "missing_from_output"
                else:
                    good[k] = postprocess(seen[k], batch[k - 1][2], self.lc)
        else:
            for k in range(1, len(batch) + 1):
                bad[k] = err or "call_failed"
        retry = []
        self.db.execute("BEGIN IMMEDIATE")
        for k, (tk, rid, text, att) in enumerate(batch, 1):
            if k in good:
                self.db.execute("UPDATE work SET status='completed', attempts=attempts+1, label_config=?, result_json=?, "
                                "request_id=?, phase=?, completed_at=?, reason=NULL WHERE text_key=?",
                                (self.lc, json.dumps(good[k], ensure_ascii=False), meta["request_id"], self.phase, now_iso(), tk))
            elif final_try or parsed is None or att + 1 > self.cfg["limits"]["invalid_output_retries"]:
                self.db.execute("UPDATE work SET status='quarantined', attempts=attempts+1, reason=? WHERE text_key=?",
                                (bad[k][:200], tk))
            else:
                self.db.execute("UPDATE work SET attempts=attempts+1, reason=? WHERE text_key=?", (bad[k][:200], tk))
                retry.append((tk, rid, text, att + 1))
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('spent_usd', ?)", (repr(self.ledger.spent),))
        self.db.execute("COMMIT")
        return retry

    def run(self):
        t0 = time.time()
        old = signal.signal(signal.SIGINT, lambda *a: (self.stop.set(), setattr(self, "stop_reason", "SIGINT")))
        todo = self.pending()
        bs = self.cfg["roles"]["enrich"]["batch_size"]
        batches = [todo[i:i + bs] for i in range(0, len(todo), bs)]
        if self.max_batches is not None:
            batches = batches[: self.max_batches]
        log_event(self.state_dir, "enrich_start", phase=self.phase, pending=len(todo), batches=len(batches),
                  workers=self.workers, label_config=self.lc, cap=self.ledger.cap, spent=self.ledger.spent)
        print(f"enrich[{self.phase}]: {len(todo)} pending distinct texts, {len(batches)} batches, {self.workers} workers")
        done_items = done_batches = 0
        retries = []
        with cf.ThreadPoolExecutor(self.workers) as ex:
            it = iter(batches)
            inflight = {}

            def submit_next():
                if self.stop.is_set():
                    return False
                if self.max_seconds and time.time() - t0 > self.max_seconds:
                    self.stop.set(); self.stop_reason = "max_seconds"
                    return False
                b = next(it, None)
                if b is None:
                    return False
                inflight[ex.submit(self.call_batch, b)] = (b, False)
                return True

            for _ in range(self.workers * 2):
                if not submit_next():
                    break
            while inflight:
                fin, _ = cf.wait(list(inflight), return_when=cf.FIRST_COMPLETED)
                for f in fin:
                    b, is_retry = inflight.pop(f)
                    try:
                        batch, parsed, meta, err = f.result()
                    except BudgetExceeded as e:
                        self.stop.set(); self.stop_reason = f"budget: {e}"
                        continue
                    r = self.commit(batch, parsed, meta, err, final_try=is_retry)
                    done_batches += 1
                    done_items += len(batch) - len(r)
                    retries.extend(r)
                    # retry invalid items once, in their own bounded request
                    while len(retries) >= bs or (retries and not inflight):
                        chunk, retries = retries[:bs], retries[bs:]
                        if self.stop.is_set():
                            retries = chunk + retries
                            break
                        inflight[ex.submit(self.call_batch, chunk)] = (chunk, True)
                    if done_batches % 50 == 0:
                        el = time.time() - t0
                        print(f"  {done_batches} batches, {done_items} items, ${self.ledger.spent:.4f}, {done_items / el:.1f} items/s")
                    submit_next()
        signal.signal(signal.SIGINT, old)
        el = round(time.time() - t0, 2)
        st = dict(self.db.execute("SELECT status, COUNT(*) FROM work GROUP BY status").fetchall())
        log_event(self.state_dir, "enrich_end", phase=self.phase, elapsed_s=el, batches=done_batches,
                  stop_reason=self.stop_reason, spent_usd=self.ledger.spent, work_status=st)
        print(f"enrich[{self.phase}] done in {el}s; status={st}; spent=${self.ledger.spent:.4f}; stop={self.stop_reason}")
        self.snapshot()
        return st

    def snapshot(self):
        """Checkpoint snapshot after every invocation: all review IDs whose result is saved (incl. exact-text reuse)."""
        from .common import write_json
        n = int(self.db.execute("SELECT v FROM meta WHERE k='enrich_invocations'").fetchone()[0])
        ids = [r[0] for r in self.db.execute("SELECT s.review_id FROM source s JOIN work w ON w.text_key=s.text_key "
                                             "WHERE w.status='completed' ORDER BY s.row_idx")]
        write_json(self.state_dir / "checkpoints" / f"invocation_{n:03d}_{self.phase}.json",
                   {"invocation": n, "phase": self.phase, "label_config": self.lc, "saved_at": now_iso(),
                    "stop_reason": self.stop_reason, "completed_count": len(ids), "completed_ids": ids})
