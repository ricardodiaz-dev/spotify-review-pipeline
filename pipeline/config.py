"""Versioned run configuration. Changing any field that feeds label_config invalidates the result cache."""
import json
from pathlib import Path

from .common import ROOT

CONFIG_PATH = ROOT / "config.json"

DEFAULT = {
    "provider": "openai",
    "endpoint": "https://api.openai.com/v1/responses",
    "model_allowlist": ["gpt-6-luna"],
    "roles": {
        "enrich": {"model": "gpt-6-luna", "effort": "none", "prompt": "prompts/enrich_v1.md", "prompt_version": "enrich-v1",
                   "schema_version": "schema-v1", "batch_size": 50, "max_output_tokens": 4000},
        "verify": {"model": "gpt-6-luna", "effort": "none", "prompt": "prompts/verify_v1.md", "prompt_version": "verify-v1",
                   "schema_version": "vschema-v1", "batch_size": 25, "max_output_tokens": 2000},
        "group": {"model": "gpt-6-luna", "effort": "low", "prompt": "prompts/group_v1.md", "prompt_version": "group-v1",
                  "max_output_tokens": 6000},
        "memo": {"model": "gpt-6-luna", "effort": "low", "prompt": "prompts/memo_v1.md", "prompt_version": "memo-v1",
                 "max_output_tokens": 6000},
    },
    "limits": {
        "spend_cap_usd": 25.0,          # hard local cap for one invocation's ledger (reserved + spent)
        "max_workers": 8,
        "transient_retries": 4,          # 429/5xx/timeout retries with exponential backoff + jitter
        "invalid_output_retries": 1,     # contract: retry invalid output once, then quarantine
        "request_timeout_s": 120,
        "fallback_fraction": 0.0,        # no stronger-model fallback configured (declared cap)
    },
    # USD per 1M tokens, standard tier, checked 2026-10-20 at
    # https://developers.openai.com/api/docs/models/gpt-6-luna
    "prices_per_mtok": {"gpt-6-luna": {"input": 0.10, "cached_input": 0.01, "cache_write": 0.125, "output": 0.50}},
    "verification": {"sample_size": 1000, "seed": "verify-seed-2026-10-20"},
}


def load():
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text())
    else:
        cfg = DEFAULT
        CONFIG_PATH.write_text(json.dumps(DEFAULT, indent=2) + "\n")
    return cfg


def label_config(cfg):
    r = cfg["roles"]["enrich"]
    return f"{r['model']}+effort-{r['effort']}+{r['prompt_version']}+{r['schema_version']}"


def prompt_text(cfg, role):
    return (ROOT / cfg["roles"][role]["prompt"]).read_text(encoding="utf-8")
