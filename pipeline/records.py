"""Expands per-distinct-text results to one final record per source review ID (code only)."""
import json

from .ingest import connect

EXPORT_KEYS = ("topic", "intent", "sentiment", "severity", "entities", "evidence_quote", "needs_review", "label_config")


def iter_records(state_dir, internal=False):
    """Yields records in source order. Exact-duplicate texts reuse the representative's validated result and point
    to it directly via cache_source_id (never a chain). Unfinished work is exported as quarantined, never completed."""
    db = connect(state_dir)
    q = ("SELECT s.review_id, s.source_sha256, s.is_empty, s.review_timestamp, s.review_rating, w.rep_review_id, w.status, "
         "w.result_json, w.reason, w.attempts FROM source s LEFT JOIN work w ON w.text_key = s.text_key "
         "ORDER BY s.row_idx")
    for rid, sha, empty, ts, rating, rep, status, res, reason, attempts in db.execute(q):
        if empty:
            yield {"review_id": rid, "source_sha256": sha, "status": "quarantined", "reason": "empty_review_text"}
            continue
        if status == "completed":
            r = json.loads(res)
            rec = {"review_id": rid, "source_sha256": sha, "status": "completed", **{k: r[k] for k in EXPORT_KEYS}}
            if rep != rid:
                rec["cache_source_id"] = rep
            if internal:
                rec.update(subtopic=r["subtopic"], review_timestamp=ts, review_rating=rating,
                           review_reasons=r.get("review_reasons", []))
            yield rec
        else:
            yield {"review_id": rid, "source_sha256": sha, "status": "quarantined",
                   "reason": (reason or "not_processed") if status == "quarantined" else "pending_not_processed",
                   "attempts": attempts}
