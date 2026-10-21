# Budget refresh at 100 → 500 → 10,000 reviews (measured, then projected to 484,189 distinct texts)

Each row is a real run (`state/<run>/run_summary.json`, regenerate with `python3 scripts/run_summary.py --state …`). Projection = measured enrichment $/text × 484,189 and measured texts/s at that worker count. Verification, grouping and memo add fixed overhead (< $0.05 measured).

| checkpoint | rows | distinct texts enriched | workers | enrich requests | failed attempts | enrich $ | projected full enrich $ | enrich wall s | texts/s | projected full hours at this concurrency | all-stage $ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cost_100 pilot | 100 | 100 | 1 | 2 | 0 | 0.0021 | 10.21 | 28.7 | 3.5 | 38.60 | 0.0048 |
| checkpoint_500 | 500 | 479 | 2 | 10 | 0 | 0.0098 | 9.95 | 66.5 | 7.2 | 18.67 | 0.0147 |
| analysis_10000 | 10,000 | 8,448 | 16 | 169 | 0 | 0.1797 | 10.30 | 160.9 | 52.5 | 2.56 | 0.1882 |

Decision: cost per text was stable (≈$0.000021) from 100 to 10,000, so the full run was budgeted at about $10–14 under a $25 local spend cap. Throughput scaled close to linearly from 1 to 16 workers. The full run used 32 workers (about 120 requests/min, far below the 5,000 RPM / 2M TPM tier limits). Throughput at 32 workers was measured in the full run, not modeled; see `state/full/run_summary.json` and the README.
