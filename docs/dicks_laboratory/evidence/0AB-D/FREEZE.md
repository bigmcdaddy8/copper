# 0AB-D freeze: Drysdale prospective validation plan (DRYSDALE_PROSPECTIVE_VALIDATION_PLAN_V1)

Additive record. Earlier freeze records are not edited:
[../0AB-B/FREEZE.md](../0AB-B/FREEZE.md) (DRYSDALE_V1) and
[../0AB-C/FREEZE_ADDENDUM.md](../0AB-C/FREEZE_ADDENDUM.md) (tutor integration layer).

| Field | Value |
|---|---|
| Recorded | 2026-10-13T03:09:13Z (2026-10-12 22:09 CDT) |
| Plan commit (all files below, as committed) | `1a0a20bac613dad30e68cf34b35730e5ddedc868` |
| Campaign analysis performed before this freeze | **NONE** (no campaign date opened, analyzed, summarized or previewed) |
| Validation cohort | 2026-10-12 .. 2026-11-06 (20 trading dates), UNSEEN |

`scripts/dicks_lab_drysdale_validation.py` refuses campaign data unless every file listed in the block below
verifies and `--frozen-plan` equals the plan sha256 listed here. A later edit of any listed file blocks the
readout until a recorded addendum (old and new sha256, reason) is authorized.

## Frozen set (sha256  path)

Validation plan and the accepted quality reporting pre-registration; frozen market policy (DRYSDALE_V1,
byte-identical to the 0AB-B freeze); frozen quality policy (0AB-C, frozen for the first readout); the validation
machinery.

```text
6aa461bb6a5e49bdddd534bbcea6c2e1c36b3b8ff8786eae263879904a7be377  docs/dicks_laboratory/DRYSDALE_PROSPECTIVE_VALIDATION_PLAN.md
49b07a7138f978b136f68f8dcdcaa68c33b4f1cc5c24821a16ea05ff31fcfa0a  docs/dicks_laboratory/DRYSDALE_PROSPECTIVE_REPORTING_PREREGISTRATION.md
51948f806acd86d295f1a12432d2e0e37d49ec7de709e7afc1f1b957920165af  apps/dicks_laboratory/src/dicks_laboratory/drysdale.py
8bb1e4c14da0153ddb04ca97b32a4eb28924a4763c285d747c6e629df395d29a  docs/dicks_laboratory/DRYSDALE_VWAP_TRAINING_CANDIDATES.md
2a39fac87bddbfafc4cfe2a0c8078ca631cbe5d67200200a10fd376b8e1f9cb3  apps/dicks_laboratory/tests/test_drysdale.py
3143f8d63a59f88e39419751c64d5553a11a70bfc47c4f55ee5dfe1ca53b825b  apps/dicks_laboratory/src/dicks_laboratory/price_action.py
1d54d63e808ca6bdc77dd2258e70e81b6600dbce37c8701cc9b7870258c7cc8d  apps/dicks_laboratory/src/dicks_laboratory/drysdale_quality.py
902c36e766f63c555856543c78d565b38d51f131effd8ccd21e681c60bded79d  docs/dicks_laboratory/DRYSDALE_QUALITY_SCOPE.md
ba188eb55998b2ae21358dcbb988a9ab4112f5e1b857f2f80bf30999b8ea3133  apps/dicks_laboratory/src/dicks_laboratory/drysdale_validation.py
b14c967554a460e4d6bc25980e23a4056077ca2e901e3ea278d896bb66ee8cbe  scripts/dicks_lab_drysdale_validation.py
```

## Statement

```text
DRYSDALE_V1:                 FROZEN / UNCHANGED (four market-rule files verify against 0AB-B FREEZE.md)
QUALITY POLICIES:            FROZEN FOR FIRST READOUT
VALIDATION PLAN:             PRE-REGISTERED / FROZEN
CAMPAIGN:                    ARMED / UNINSPECTED
ANALYTIC CAMPAIGN ACCESS:    NOT YET PERFORMED
```
