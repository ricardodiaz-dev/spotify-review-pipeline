"""Stage 1 - Prepare (code only, no model).

Reads every row of the input CSV with a multiline-safe parser, preserves the six source strings exactly,
computes the contract row hash, profiles quality, finds exact duplicate texts and builds the pending queue
(one representative review per distinct nonempty text). Empty texts are quarantined as empty_review_text.
Outputs: <state>/state.db (source + work tables), ingestion_report.json, data_manifest.json.
"""
import sqlite3
import statistics
import time
from collections import Counter
from pathlib import Path

from .common import FIELDS, ROOT, csv_rows, file_sha, log_event, row_sha, text_key, write_json

SCHEMA = """
CREATE TABLE IF NOT EXISTS source(
  row_idx INTEGER PRIMARY KEY, review_id TEXT UNIQUE NOT NULL, review_text TEXT, review_rating TEXT,
  review_likes TEXT, app_version TEXT, review_timestamp TEXT, source_sha256 TEXT, text_key TEXT, is_empty INTEGER);
CREATE INDEX IF NOT EXISTS source_text ON source(text_key);
-- one row per distinct nonempty text: the representative (first occurrence) is what the model sees
CREATE TABLE IF NOT EXISTS work(
  text_key TEXT PRIMARY KEY, rep_review_id TEXT NOT NULL, n_reviews INTEGER, status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0, reason TEXT, label_config TEXT, result_json TEXT, request_id TEXT,
  phase TEXT, completed_at TEXT);
CREATE INDEX IF NOT EXISTS work_status ON work(status);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""


def connect(state_dir):
    db = sqlite3.connect(Path(state_dir) / "state.db", isolation_level=None, timeout=60)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.executescript(SCHEMA)
    return db


def run(input_csv, state_dir):
    t0 = time.time()
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    db = connect(state_dir)
    if db.execute("SELECT COUNT(*) FROM source").fetchone()[0]:
        prev = db.execute("SELECT v FROM meta WHERE k='input_sha256'").fetchone()[0]
        if prev != file_sha(input_csv):
            raise SystemExit("state dir already holds a different input; use a new --state dir")
        print("ingest: already done, reusing saved source table")
        return
    ids, months, ratings, text_counts = set(), Counter(), Counter(), Counter()
    counts = Counter()
    lengths = []
    rows = []
    for i, row in enumerate(csv_rows(input_csv)):
        rid = row["review_id"]
        counts["records"] += 1
        if rid in ids:
            counts["duplicate_review_ids"] += 1
        ids.add(rid)
        empty = not row["review_text"].strip()
        counts["empty_review_text"] += empty
        counts["missing_app_version"] += not row["app_version"].strip()
        counts["missing_timestamp"] += not row["review_timestamp"].strip()
        counts["multiline_text"] += ("\n" in row["review_text"])
        if row["review_rating"] not in {"1", "2", "3", "4", "5"}:
            counts["invalid_rating"] += 1
        months[row["review_timestamp"][:7]] += 1
        ratings[row["review_rating"]] += 1
        tk = text_key(row["review_text"])
        if not empty:
            text_counts[tk] += 1
            lengths.append(len(row["review_text"]))
        rows.append((i, *[row[k] for k in FIELDS], row_sha(row), tk, int(empty)))
    if counts["duplicate_review_ids"]:
        raise SystemExit("duplicate review IDs in input; refusing to continue")
    db.execute("BEGIN")
    db.executemany("INSERT INTO source VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    seen = set()
    work = []
    for r in rows:
        tk, empty = r[8], r[9]
        if not empty and tk not in seen:
            seen.add(tk)
            work.append((tk, r[1], text_counts[tk]))
    db.executemany("INSERT INTO work(text_key, rep_review_id, n_reviews) VALUES (?,?,?)", work)
    sha = file_sha(input_csv)
    db.execute("INSERT OR REPLACE INTO meta VALUES ('input_sha256', ?)", (sha,))
    db.execute("INSERT OR REPLACE INTO meta VALUES ('input_path', ?)", (str(input_csv),))
    db.execute("COMMIT")
    nonempty = counts["records"] - counts["empty_review_text"]
    dup_groups = sum(1 for c in text_counts.values() if c > 1)
    top_dups = text_counts.most_common(10)
    tk_to_text = {}
    if top_dups:
        wanted = {k for k, _ in top_dups}
        for r in rows:
            if r[8] in wanted and r[8] not in tk_to_text:
                tk_to_text[r[8]] = r[2]
    report = {
        "input_path": str(Path(input_csv).name), "input_sha256": sha, "input_bytes": Path(input_csv).stat().st_size,
        "counts": dict(counts), "nonempty_reviews": nonempty, "distinct_nonempty_texts": len(text_counts),
        "reviews_reusing_exact_text": nonempty - len(text_counts), "duplicate_text_groups": dup_groups,
        "empty_text_review_ids": [r[1] for r in rows if r[9]],
        "reviews_by_month": dict(sorted(months.items())), "reviews_by_rating": dict(sorted(ratings.items())),
        "first_review": min(r[6] for r in rows) if rows else None, "last_review": max(r[6] for r in rows) if rows else None,
        "text_length_chars": {"min": min(lengths), "median": statistics.median(lengths), "mean": round(statistics.mean(lengths), 2),
                              "p95": sorted(lengths)[int(len(lengths) * .95)], "max": max(lengths)} if lengths else {},
        "most_common_texts": [{"text": tk_to_text[k][:80], "count": c} for k, c in top_dups],
        "pending_distinct_texts": len(work), "quarantined_empty": counts["empty_review_text"],
        "notes": ["review_rating is metadata only, never used as a label input.",
                  "Missing app_version does not prevent classification.",
                  "Timestamps have no specified timezone; months are taken from the source string."],
        "elapsed_s": round(time.time() - t0, 2),
    }
    write_json(state_dir / "ingestion_report.json", report)
    write_json(state_dir / "data_manifest.json", {"input": report["input_path"], "input_sha256": sha,
               "records": counts["records"], "fields": list(FIELDS), "row_hash": "sha256(canonical JSON of six field strings)",
               "dataset_source": "https://drive.google.com/file/d/1P0rUoAS_wVjp3BYKqXMEyD4u0uJP1Bvf/view"})
    log_event(state_dir, "ingest", records=counts["records"], distinct=len(text_counts), empty=counts["empty_review_text"],
              elapsed_s=report["elapsed_s"])
    print(f"ingest: {counts['records']} rows, {nonempty} nonempty, {len(text_counts)} distinct texts, "
          f"{counts['empty_review_text']} empty, {counts['missing_app_version']} missing app_version ({report['elapsed_s']}s)")
