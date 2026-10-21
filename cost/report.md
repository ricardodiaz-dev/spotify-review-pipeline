# 100-review cost & runtime calculator — measured pilot + full-run projection

Generated offline by `python3 cost/calculator.py` from `pilot_calls.jsonl`, `pilot_runs.json`, `rates.csv`, `assumptions.json`. No API key or model call is used.

## Measured on cost_100.csv

- Input: `data/cost_100.csv`, sha256 `c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e` (100 IDs; manifest checksum match: True)
- Records: 100 completed, 0 failed/quarantined; unique texts 100; result-cache hits cold=0, warm=100
- Workers: 1 (cold and warm); batch size 50; service tier: standard (no Batch API)
- Wall clock: **cold 64.7 s**, **warm 1.0 s** (clock around the whole run)
- API cost: **cold $0.004773**, **warm $0.000000** (incremental). Cost per 1,000 input rows (cold): $0.0477; per completed record: $0.000048
- Enrichment throughput (cold, 1 worker): 3.43 texts/s

| run | role | model | effort | prompt | requests | failed | reviews sent | uncached in | cached in | cache-write in | output (reasoning incl.) | cost USD | summed latency s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cold | enrich | gpt-6-luna | none | enrich-v1 | 2 | 0 | 100 | 6 | 3516 | 2241 | 3584 (0) | 0.002108 | 28.7 |
| cold | group | gpt-6-luna | low | group-v1 | 1 | 0 | 0 | 3 | 0 | 3630 | 1006 (131) | 0.000957 | 14.1 |
| cold | memo | gpt-6-luna | low | memo-v1 | 1 | 0 | 0 | 3 | 0 | 5441 | 1401 (413) | 0.001381 | 15.1 |
| cold | verify | gpt-6-luna | none | verify-v1 | 1 | 0 | 20 | 3 | 0 | 1186 | 357 (0) | 0.000327 | 4.5 |
| warm | enrich | — | — | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 (0) | 0.000000 | 0.0 |
| warm | group | — | — | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 (0) | 0.000000 | 0.0 |
| warm | memo | — | — | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 (0) | 0.000000 | 0.0 |
| warm | verify | — | — | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 (0) | 0.000000 | 0.0 |

Warm run: 0 enrichment calls, 0 calls in total (downstream group/memo/verify reuse cached artifacts keyed by input + config).

Stage wall-clock seconds (cold): ingest 0.16, enrich 29.15, verify 5.45, group 14.50, rank 0.16, memo 15.32

Stage wall-clock seconds (warm): ingest 0.15, enrich 0.21, verify 0.20, group 0.18, rank 0.12, memo 0.19

## Rates used (editable `cost/rates.csv`)

| model | item | price | unit | source | checked |
|---|---|---|---|---|---|
| gpt-6-luna | input | $0.1000 | per 1M tokens | https://developers.openai.com/api/docs/models/gpt-6-luna | 2026-10-20 |
| gpt-6-luna | cached_input | $0.0100 | per 1M tokens | https://developers.openai.com/api/docs/models/gpt-6-luna | 2026-10-20 |
| gpt-6-luna | cache_write | $0.1250 | per 1M tokens | https://developers.openai.com/api/docs/models/gpt-6-luna | 2026-10-20 |
| gpt-6-luna | output | $0.5000 | per 1M tokens | https://developers.openai.com/api/docs/models/gpt-6-luna | 2026-10-20 |
| claude-sonnet-5 | input | $2.0000 | per 1M tokens | https://www.anthropic.com/news/claude-sonnet-5 (as quoted in GRADING_CONTRACT.md) | 2026-10-20 |
| claude-sonnet-5 | output | $10.0000 | per 1M tokens | https://www.anthropic.com/news/claude-sonnet-5 (as quoted in GRADING_CONTRACT.md) | 2026-10-20 |

Local compute: the pipeline runs on a laptop CPU (SQLite + Python); its cost is not metered and is reported as **unknown (not zero)**. Hosting: Neon free tier + Vercel hobby, $0 list price at this scale.

## Full-run projection (660,622 rows; 660,609 nonempty; 13 empty quarantined)

Controls (editable `cost/assumptions.json`): spend limit **$25.0**, output cap 4000 tokens/request, max workers 32, declared max fallback fraction 0.01 (claude-sonnet-5), verification sample 1000.
Per-text measurements used: 0.1 uncached input tok, 22.4 cache-write input tok, 35.8 output tok, 1758 cached prompt tok per request; measured enrich failure rate 0.000. Group+memo are fixed overhead counted once.

| scenario | exact-text reuse | texts | requests | enrich $ | verify $ | fallback $ | group+memo $ | **total API $** | est. hours | budget |
|---|---|---|---|---|---|---|---|---|---|---|
| base | yes | 484,189 | 9,684 | 10.41 | 0.017 | 0.00 | 0.007 | **10.43** | 1.79 | ok |
| base | no | 660,609 | 13,213 | 14.20 | 0.017 | 0.00 | 0.007 | **14.23** | 2.44 | ok |
| conservative | yes | 484,189 | 9,684 | 11.23 | 0.018 | 2.29 | 0.014 | **13.55** | 3.37 | ok |
| conservative | no | 660,609 | 13,213 | 15.32 | 0.018 | 3.13 | 0.014 | **18.48** | 4.60 | ok |

Hours are modeled (measured 1-worker throughput × workers × parallel efficiency), not measured. Batch-API (50% off) is not used; it would be an estimate only.
