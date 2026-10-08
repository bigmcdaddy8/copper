# Market Profile Validation Corpus (0Y-D)

A reusable local research corpus of authentic ES datasets for Market Profile
phases. It means later work does not have to boot dragon. **Database files are
never in Git.** This file is the metadata of record.

## Location and integrity

- **Copied from dragon:** `~/secure/mp_corpus/` on the workstation (mode 700;
  files 444). It holds the 13 finalized datasets from
  `dragon:/srv/dicks_laboratory/data/sessions/` and `az4_live_verification/`,
  each with its `.manifest.json`.
  - The copy was read-only, made on 2026-10-08 between 17:44 and 17:52 UTC
    with rsync and zstd transport.
  - Every file matched its manifest sha256 on dragon before the copy and
    locally after it (`~/secure/mp_corpus/sha256_verification.txt`).
- **Pre-existing local datasets** keep their existing paths: 9 files under
  `apps/dicks_laboratory/data/`, git-ignored.
- **Excluded:** `~/secure/0w5b/snap/prefill_to_1957.sqlite3`. It is a 0W-5B
  write-benchmark replay snapshot, not an authentic capture.
- **Duplicates:** `~/secure/0w5a/…9ac5a21e` and `~/secure/att4/…3716af9f` are
  byte-identical to their corpus copies, which have the same sha256.
- **Dragon operation:**
  - Dragon was started with `az vm start` (the accepted administrative path).
  - Guest timers were checked before and after: `dicks-lab-es-session.timer`
    static/inactive; `dicks-lab-preflight-gate.timer` and
    `dicks-lab-launch-gate.timer` disabled/inactive.
  - No collector ran, no quote token was requested, and no capture was
    launched.
  - Dragon was deallocated afterwards (up about 17:37–17:55 UTC).

## Datasets (eligibility under the frozen 0Y-C V1 policy)

| TD | Dataset ID | Contract | Lifecycle | Dataset quality | 0Y-D eligibility | sha256 | Local path | Source |
|---|---|---|---|---|---|---|---|---|
| 2026-08-26 | `30960d24-c597-4644-96df-133ceb50a260` | ES 2026-09 | FINALIZED | COMPLETE | NO_PROFILE | `45d14cc9cf5ae04c89dab87313ad3b86ec7c342ca899738c5705ff2ce9074437` | `apps/dicks_laboratory/data/0w_soak/es_20260826_30960d24.sqlite3` | pre-existing local |
| 2026-08-27 | `e068b74f-39aa-494f-8786-028913e48906` | ES 2026-09 | INTERRUPTED | INCOMPLETE | NO_PROFILE | `6ad17e5d39b528869a75b6d1465ecf6627f203ce39c5d4fc8b6e79580362098b` | `apps/dicks_laboratory/data/0w_soak/es_20260827_e068b74f.sqlite3` | pre-existing local |
| 2026-08-28 | `5a5fbbce-045b-4da2-b57b-ce1a2e2b76b4` | ES 2026-09 | FINALIZED | COMPLETE | NO_PROFILE | `ec6fc040de835c6a96acd8af3887b43a49b7bfe0f6ae950d005c78e6a4dcc3e3` | `apps/dicks_laboratory/data/0w2a_verification/es_20260828_5a5fbbce.sqlite3` | pre-existing local |
| 2026-08-31 | `befb7b0e-9a69-4001-ac2b-90405e0c28ed` | ES 2026-09 | FINALIZED | COMPLETE | NOT_CLASSIFIED | `ca92dab0c386a6e7785130cdf90afbfb505f693180f120b7276d1d2433d4fdfa` | `apps/dicks_laboratory/data/0w2b1_verification/es_20260831_befb7b0e.sqlite3` | pre-existing local |
| 2026-08-31 | `c9ebc043-beaa-4931-a5d6-29064f7a6e3c` | ES 2026-09 | INTERRUPTED | INCOMPLETE | NOT_CLASSIFIED | `cc8e92aec77809dacda80c1d788987d8defb99f758e9a18a2a2de34f232d3e37` | `apps/dicks_laboratory/data/0w2_attempt2/es_20260831_c9ebc043.sqlite3` | pre-existing local |
| 2026-09-01 | `bb8cce1f-5c8c-478f-81c9-1ce1b4ef2de5` | ES 2026-09 | FINALIZED | COMPLETE | NO_PROFILE | `92e958135d5e3bb6f8cacbdb5346bcef627a56d7ba40c98de3c6a1533643dc43` | `apps/dicks_laboratory/data/0w2b1_verification/es_20260901_bb8cce1f.sqlite3` | pre-existing local |
| 2026-09-02 | `9c76e79c-f4dd-45c7-acb9-d9890dc20671` | ES 2026-09 | FINALIZED | INCOMPLETE | ELIGIBLE | `24efe7e84859550978f8b278eef4d82b2ed239e5f6d6e4e24d61cf82389e1079` | `apps/dicks_laboratory/data/0w2_attempt3/es_20260902_9c76e79c.sqlite3` | pre-existing local |
| 2026-09-07 | `85eccb13-9432-4163-a078-f9bdbb2f5973` | ES 2026-09 | FINALIZED | COMPLETE | NOT_CLASSIFIED | `bd829b118873bbe06894c7357c6eaf760b7dda74b6dce305215ecb19173abb34` | `apps/dicks_laboratory/data/0wh1_labor_day/h1a/es_20260907_85eccb13.sqlite3` | pre-existing local |
| 2026-09-08 | `e3110b72-9cb3-4478-96fa-84b7f3aedd0d` | ES 2026-09 | OPEN | COMPLETE | NOT_CLASSIFIED | `bbcbf73813d1c86e30955572ded44f566474a6af87a1e21490eb1dffa4d7396f` | `apps/dicks_laboratory/data/0wh1_labor_day/h1b/es_20260908_e3110b72.sqlite3` | pre-existing local |
| 2026-09-10 | `f6553efa-30e3-4410-b49d-b659a36b9048` | ES 2026-09 | FINALIZED | COMPLETE | NO_PROFILE | `b5cf4fa530f957660878f7007402e47be781ced8a736f40eff4f52d4c61fa6b4` | `~/secure/mp_corpus/es_20260910_f6553efa.sqlite3` | dragon (0Y-D copy) |
| 2026-09-11 | `3716af9f-28bf-4611-b56c-cbeb8a4f0fff` | ES 2026-09 | FINALIZED | COMPLETE | NOT_CLASSIFIED | `007fd66fe63d0ee1a6bc07a8edbc3e2f3b3f23edabfc764a75244dea6e07bc19` | `~/secure/mp_corpus/es_20260911_3716af9f.sqlite3` | dragon (0Y-D copy) |
| 2026-09-15 | `b07e92d4-fcdd-4731-a670-f2acbdeba7f0` | ES 2026-09 | FINALIZED | COMPLETE | ELIGIBLE | `7c969950e2df9616dbd2897f80200336a9ab5bd2046bb55294237eaaa9cf50da` | `~/secure/mp_corpus/es_20260915_b07e92d4.sqlite3` | dragon (0Y-D copy) |
| 2026-09-21 | `64d684c9-c22b-4a87-8224-a2a9f7b17e40` | ES 2026-12 | FINALIZED | INCOMPLETE | ELIGIBLE | `2e5968897f49dc4042ebae34d65ca624b3b0efe32dc6ac88cfc2f527d35b216f` | `~/secure/mp_corpus/es_20260921_64d684c9.sqlite3` | dragon (0Y-D copy) |
| 2026-09-23 | `b2856c52-17a5-43f4-941c-aa311e8558e9` | ES 2026-12 | FINALIZED | COMPLETE | ELIGIBLE | `64ad1f3a5ea2583a5981c051902d2030c3a258410e0a5b52aeccd9e1798252a6` | `~/secure/mp_corpus/es_20260923_b2856c52.sqlite3` | dragon (0Y-D copy) |
| 2026-09-24 | `31c92a57-242c-4b25-a983-0086c811ed9a` | ES 2026-12 | FINALIZED | COMPLETE | ELIGIBLE | `c8a3524bbb7f4635f87f45dbe2418aff17f3b0f7f65808cd806b3d9dba7c0106` | `~/secure/mp_corpus/es_20260924_31c92a57.sqlite3` | dragon (0Y-D copy) |
| 2026-09-25 | `c690ff8e-28ac-4d7b-9107-e896987a6520` | ES 2026-12 | FINALIZED | COMPLETE | ELIGIBLE | `a57cc42d10f2eb36b55556bf21ea5fc700f0eb75a69f2dac38c85b005ffcadf5` | `~/secure/mp_corpus/es_20260925_c690ff8e.sqlite3` | dragon (0Y-D copy) |
| 2026-09-28 | `843a6ca0-3cf3-4878-b53c-a848e72bece5` | ES 2026-12 | FINALIZED | COMPLETE | ELIGIBLE | `c3159322fc15a56d1da981b623b9e44bbc550b853207cd53f2383c04f33f1917` | `~/secure/mp_corpus/es_20260928_843a6ca0.sqlite3` | dragon (0Y-D copy) |
| 2026-09-29 | `6af08205-90f9-4735-809f-c7b8a62bda65` | ES 2026-12 | FINALIZED | INCOMPLETE | ELIGIBLE | `0b59b7197d486c7ed5fcf5afa08f83e42ec19ed889b44ef421f1eecbf3d07dde` | `~/secure/mp_corpus/es_20260929_6af08205.sqlite3` | dragon (0Y-D copy) |
| 2026-09-30 | `9ac5a21e-a5c0-427c-91fc-af300539b711` | ES 2026-12 | FINALIZED | COMPLETE | ELIGIBLE | `61489eea4ace51dee3aafaa1e1dff5fc7d843e491205f42c2e0dbd098a8aa17c` | `~/secure/mp_corpus/es_20260930_9ac5a21e.sqlite3` | dragon (0Y-D copy) |
| 2026-10-01 | `fe280370-99f6-4265-8bf1-a4ce7580f940` | ES 2026-12 | FINALIZED | COMPLETE | ELIGIBLE | `58545a1b7507ab0dc934adef9e6699fb11cc17745d7526e413b00897093bd95e` | `~/secure/mp_corpus/es_20261001_fe280370.sqlite3` | dragon (0Y-D copy) |
| 2026-10-02 | `7e8d7b5e-d7b8-4286-92a2-320bfd26723d` | ES 2026-12 | FINALIZED | COMPLETE | ELIGIBLE | `cd47e987c8edbec758d590c7580d4a4bb982ed802da18d21fea338f020c3fae2` | `~/secure/mp_corpus/es_20261002_7e8d7b5e.sqlite3` | dragon (0Y-D copy) |
| 2026-10-06 | `2b6cc528-8928-4c2b-a27d-77794fc61d26` | ES 2026-12 | FINALIZED | COMPLETE | ELIGIBLE | `a97c6ba09853bb418d6f65d48cf1e53f3ae554535f9d874849cd3ff9ceef9bf3` | `~/secure/mp_corpus/es_20261006_2b6cc528.sqlite3` | dragon (0Y-D copy) |

Eligibility meanings and reasons are in `MARKET_PROFILE_VALIDATION_0YD.md` §2.
The frozen per-day records are in `evidence/0Y-D/blind_run/records.jsonl`.

## Use

```
uv run python scripts/dicks_lab_tpo_profile.py ~/secure/mp_corpus/es_20260921_64d684c9.sqlite3 --structure --day-structure
uv run python scripts/dicks_lab_mp_validation.py run OUT_DIR ~/secure/mp_corpus/*.sqlite3 [local paths…]
uv run python scripts/dicks_lab_mp_validation.py analyze OUT_DIR
```

To extend the corpus with new finalized days, copy them the same way. Verify
each file against its manifest sha256 and add a row here. Do not overwrite or
modify existing files.
