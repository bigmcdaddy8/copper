# 0Z-A evidence — MARKET_STUDY_STATE_V1 real-data proof

Produced with commit `73c6b6d2cb82898146e59f8983b628b8360d3d1e`:

```
uv run python scripts/dicks_lab_market_study_state.py CURRENT_DB [--prior-database PRIOR_DB] --json
uv run python scripts/dicks_lab_market_study_state.py CURRENT_DB [--prior-database PRIOR_DB] --json-out FILE
```

Each date was built twice in separate processes. Database paths are in
`MARKET_PROFILE_CORPUS_0YD.md`.

| File | Content |
|---|---|
| `validation.tsv` | per date: build times, bytes, byte-identity, both state hashes, database sha256 unchanged |
| `states/` | the canonical JSON documents (payload + `market_study_state_sha256`) |
| `summaries/` | the human summary of each state |

Findings: `docs/dicks_laboratory/MARKET_STUDY_STATE_0ZA.md`.
