# 0X-A — Contract-Roll Foundation Evidence (2026-10-07)

All captured from robby over live Tastytrade REST (`GET /instruments/futures`
via `list_futures()`). No DXLink connection, no quote token, no `dragon` boot.
Instrument metadata is public. No tokens, credentials or account data are
stored here.

| File | Contents |
|---|---|
| `list_futures_ES_MES_NQ_MNQ_2026-10-07.json` | the 33 ES/MES/NQ/MNQ rows of the live `list_futures()` response (534 rows across all products) |
| `live_roll_check_and_chains_2026-10-07.txt` | live `dicks_lab_roll_check.py check` (`CURRENT (OK)`, action `NONE`), `chain` for ES/MES/NQ/MNQ, and the updated `dicks_lab_preflight.py` (`roll_state=CURRENT`, `PREFLIGHT_RESULT=PASS`) |
| `roll_schedule_replay_ES_Z6.txt` | offline replay of that metadata for TD 10-07, 11-27, 11-30, 12-11, 12-14, 12-17 and 12-18 (CURRENT → ROLL_APPROACHING → ROLL_DUE → PIN_STALE/FAIL) |

Design and policy: `../../FUTURES_CONTRACT_ROLL_0XA.md`.
