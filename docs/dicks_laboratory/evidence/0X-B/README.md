# 0X-B — Contract-Roll Production Policy Evidence (2026-10-07)

| File | Contents |
|---|---|
| `dragon_deploy_2026-10-07.txt` | timer state at boot, ff-merge `a27013b → 25ec3eb`, `uv sync`, comment-only preflight-unit install + `daemon-reload` + `systemd-analyze verify`, installed-vs-repo sha256 of all six units, pin/unit agreement, timers after |
| `rest_readiness_smoke.sh` | the exact read-only smoke run on dragon |
| `rest_readiness_smoke_output_2026-10-07.txt` | its output: live preflight PASS/CURRENT, live check, offline 11-30 / 12-11 / 12-14 (Z6 and H7) / 12-18 replays, 107 tests passed |

REST `list_futures()` only. No DXLink quote token, no capture, no gate
marker. No tokens, credentials or account data are stored here. Policy:
`../../FUTURES_CONTRACT_ROLL_0XA.md` §15.
