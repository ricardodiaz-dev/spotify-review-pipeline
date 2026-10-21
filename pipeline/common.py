"""Shared helpers: source hashing (identical to check_submission.row_sha), CSV reading, atomic writes, config."""
import csv
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ("review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp")
TOPICS = ("access", "usability", "playback", "downloads", "catalog", "billing", "support", "other")
INTENTS = ("cancellation", "complaint", "request", "praise", "unclear")  # precedence order

# Subtopics used for deterministic issue grouping. Every subtopic belongs to exactly one topic.
SUBTOPICS = {
    "access": ["login_failure", "account_lost_or_hacked", "signup_verification", "unexpected_logout", "access_other"],
    "usability": ["ads_interruptions", "ui_layout_redesign", "queue_playlist_management", "controls_shuffle_skip",
                  "usability_other"],
    "playback": ["crash_or_wont_open", "playback_stops_or_skips", "lag_slow_or_freeze", "connection_error",
                 "audio_quality", "device_integration", "battery_resource_use", "playback_other"],
    "downloads": ["downloads_disappearing", "download_failure", "offline_mode", "downloads_other"],
    "catalog": ["missing_or_removed_content", "search_discovery", "recommendations_repetitive", "lyrics",
                "podcasts_audiobooks", "catalog_other"],
    "billing": ["free_tier_restrictions", "premium_price", "charges_refunds", "subscription_activation",
                "billing_other"],
    "support": ["support_unresponsive", "support_other"],
    "other": ["general_negative", "general_positive", "unrelated_or_political", "other_misc"],
}
ALL_SUBTOPICS = [s for v in SUBTOPICS.values() for s in v]
SUBTOPIC_TOPIC = {s: t for t, v in SUBTOPICS.items() for s in v}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def row_sha(row):
    return hashlib.sha256(canonical([row[k] for k in FIELDS]).encode("utf-8")).hexdigest()


def text_key(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def csv_rows(path):
    csv.field_size_limit(sys.maxsize)
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, strict=True)
        missing = [k for k in FIELDS if k not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Input CSV missing columns: {missing}")
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError("Malformed CSV row")
            yield row


def write_json(path, value):
    """Atomic JSON write: temp file + rename, so readers never see a partial file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(tmp, path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def append_jsonl(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def log_event(state_dir, stage, **fields):
    append_jsonl(Path(state_dir) / "run_log.jsonl", {"ts": now_iso(), "stage": stage, **fields})
