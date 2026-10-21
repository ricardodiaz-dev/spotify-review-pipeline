"""Model client shared by all roles: spend ledger with reservations, bounded retries, per-attempt call log.

Every HTTP attempt (success or failure) is appended to <state>/calls_raw.jsonl with role, review IDs,
model, settings, raw usage, latency and outcome. Keys are read from the environment and never logged.
"""
import json
import os
import random
import threading
import time
import uuid

import requests

from .common import append_jsonl, now_iso


class BudgetExceeded(Exception):
    pass


class InvalidOutput(Exception):
    pass


class Ledger:
    """One spend ledger shared by all workers. Reserve worst-case cost before dispatch; settle on completion."""

    def __init__(self, cap_usd, spent_usd=0.0):
        self.cap = cap_usd
        self.spent = spent_usd
        self.reserved = 0.0
        self.lock = threading.Lock()

    def reserve(self, amount):
        with self.lock:
            if self.spent + self.reserved + amount > self.cap:
                raise BudgetExceeded(f"spent {self.spent:.4f} + reserved {self.reserved:.4f} + next {amount:.4f} > cap {self.cap}")
            self.reserved += amount

    def settle(self, reserved, actual):
        with self.lock:
            self.reserved -= reserved
            self.spent += actual


def usage_cost(prices, usage):
    """Mutually exclusive categories: uncached input, cached input, cache-write input, output (incl. reasoning)."""
    inp = usage.get("input_tokens", 0) or 0
    det = usage.get("input_tokens_details") or {}
    cached = det.get("cached_tokens", 0) or 0
    write = det.get("cache_write_tokens", 0) or det.get("cache_creation_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    uncached = max(inp - cached - write, 0)
    return (uncached * prices["input"] + cached * prices["cached_input"] + write * prices.get("cache_write", prices["input"])
            + out * prices["output"]) / 1e6


class Client:
    def __init__(self, cfg, state_dir, ledger, phase="initial", run_id=None):
        self.cfg = cfg
        self.state_dir = state_dir
        self.ledger = ledger
        self.phase = phase
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.fake = os.environ.get("PIPELINE_FAKE") == "1"
        self.key = os.environ.get("OPENAI_API_KEY", "")
        if not self.fake and not self.key:
            raise SystemExit("OPENAI_API_KEY is not set (put it in .env). Offline commands do not need it.")
        self.session = requests.Session()
        self.fail_injector = None  # tests can set a callable(attempt_no) -> exception or None

    def call(self, role, instructions, user_input, schema, review_ids, label_config=None, validate=None, fake_fn=None):
        """Call the model with retries. validate(parsed) raises InvalidOutput to trigger one invalid-output retry.
        Returns (parsed, meta). Raises InvalidOutput after retries, BudgetExceeded when the cap would be crossed."""
        rc = self.cfg["roles"][role]
        model = rc["model"]
        if model not in self.cfg["model_allowlist"]:
            raise SystemExit(f"model {model} not in allowlist")
        prices = self.cfg["prices_per_mtok"][model]
        lim = self.cfg["limits"]
        est_in = (len(instructions) + len(user_input)) / 3.0  # conservative chars->tokens
        worst = (est_in * prices["input"] + rc["max_output_tokens"] * prices["output"]) / 1e6
        invalid_left = lim["invalid_output_retries"]
        transient_left = lim["transient_retries"]
        attempt = 0
        last_err = None
        while True:
            attempt += 1
            self.ledger.reserve(worst)
            t0 = time.time()
            rec = {"ts": now_iso(), "run_id": self.run_id, "role": role, "phase": self.phase, "model": model,
                   "effort": rc["effort"], "prompt_version": rc["prompt_version"], "label_config": label_config,
                   "review_ids": list(review_ids), "attempt": attempt, "max_output_tokens": rc["max_output_tokens"],
                   "service_tier": "standard"}
            actual = 0.0
            try:
                if self.fail_injector:
                    exc = self.fail_injector(attempt)
                    if exc:
                        raise exc
                if self.fake:
                    parsed, usage, req_id = fake_fn(user_input), {"input_tokens": int(est_in), "output_tokens": 0}, "fake-" + uuid.uuid4().hex[:16]
                    rec["model"] = "FAKE-OFFLINE-TEST"
                else:
                    parsed, usage, req_id = self._http(rc, instructions, user_input, schema)
                actual = usage_cost(prices, usage) if not self.fake else 0.0
                rec.update(request_id=req_id, usage=usage, input_tokens=usage.get("input_tokens", 0),
                           output_tokens=usage.get("output_tokens", 0), cost_usd=round(actual, 8))
                if validate:
                    validate(parsed)
                rec.update(outcome="succeeded", latency_s=round(time.time() - t0, 3))
                append_jsonl(self.state_dir / "calls_raw.jsonl", rec)
                self.ledger.settle(worst, actual)
                return parsed, rec
            except InvalidOutput as e:
                last_err = e
                if getattr(e, "usage", None) is not None and "usage" not in rec:  # billed even though output was unusable
                    actual = usage_cost(prices, e.usage)
                    rec.update(request_id=e.request_id, usage=e.usage, input_tokens=e.usage.get("input_tokens", 0),
                               output_tokens=e.usage.get("output_tokens", 0), cost_usd=round(actual, 8))
                rec.update(outcome="failed", error=f"invalid_output: {str(e)[:300]}", latency_s=round(time.time() - t0, 3))
                rec.setdefault("request_id", "local-" + uuid.uuid4().hex[:16])
                rec.setdefault("input_tokens", 0)
                rec.setdefault("output_tokens", 0)
                append_jsonl(self.state_dir / "calls_raw.jsonl", rec)
                self.ledger.settle(worst, actual)
                if invalid_left <= 0:
                    raise
                invalid_left -= 1
            except TransientError as e:
                last_err = e
                rec.update(outcome="failed", error=f"transient: {str(e)[:300]}", latency_s=round(time.time() - t0, 3),
                           request_id=getattr(e, "request_id", None) or "local-" + uuid.uuid4().hex[:16],
                           input_tokens=0, output_tokens=0, usage_note="no usage returned; charge unknown for timeouts")
                append_jsonl(self.state_dir / "calls_raw.jsonl", rec)
                self.ledger.settle(worst, 0.0)
                if transient_left <= 0:
                    raise InvalidOutput(f"transient_retries_exhausted: {e}")
                transient_left -= 1
                time.sleep(min(60, (2 ** (lim["transient_retries"] - transient_left)) + random.random() * 2))

    def _http(self, rc, instructions, user_input, schema):
        body = {"model": rc["model"], "instructions": instructions, "input": user_input,
                "reasoning": {"effort": rc["effort"]}, "max_output_tokens": rc["max_output_tokens"], "store": False}
        if schema:
            body["text"] = {"format": {"type": "json_schema", "name": schema["name"], "schema": schema["schema"], "strict": True}}
        limit = self.cfg["limits"]["request_timeout_s"]
        t0 = time.time()
        try:
            # stream + wall-clock deadline: a per-read timeout alone never fires if the server trickles bytes
            r = self.session.post(self.cfg["endpoint"], json=body, timeout=(10, limit), stream=True,
                                  headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
            buf = bytearray()
            for chunk in r.iter_content(8192):
                buf.extend(chunk)
                if time.time() - t0 > limit:
                    r.close()
                    raise TransientError(f"wall_timeout>{limit}s")
            r._content = bytes(buf)
        except requests.RequestException as e:
            raise TransientError(type(e).__name__)
        req_id = r.headers.get("x-request-id", "")
        if r.status_code == 429 or r.status_code >= 500:
            err = TransientError(f"HTTP {r.status_code}: {r.text[:200]}")
            err.request_id = req_id
            raise err
        if r.status_code != 200:
            raise SystemExit(f"Non-retryable HTTP {r.status_code}: {r.text[:500]}")
        data = r.json()
        usage = data.get("usage") or {}
        req_id = data.get("id") or req_id
        if data.get("status") != "completed":
            e = InvalidOutput(f"status={data.get('status')} {data.get('incomplete_details')}")
            raise _with_usage(e, usage, req_id)
        text = ""
        for item in data.get("output", []):
            if item.get("type") == "message":
                for c in item.get("content", []):
                    if c.get("type") == "output_text":
                        text += c.get("text", "")
                    elif c.get("type") == "refusal":
                        raise _with_usage(InvalidOutput("refusal: " + c.get("refusal", "")[:200]), usage, req_id)
        if schema:
            try:
                return json.loads(text), usage, req_id
            except json.JSONDecodeError as e:
                raise _with_usage(InvalidOutput(f"bad json: {e}"), usage, req_id)
        return text, usage, req_id


class TransientError(Exception):
    pass


def _with_usage(e, usage, req_id):
    e.usage, e.request_id = usage, req_id
    return e
