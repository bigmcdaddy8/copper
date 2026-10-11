# 0AB-B freeze: DRYSDALE_V1 (before any real-data audit)

Frozen before the authentic development corpus was run with this code. The
September / October dates are DEVELOPMENT / DESCRIPTIVE evidence, not
validation. No policy may be revised because of their setup counts. A changed
threshold or rule is V2. Future unseen dates are the prospective validation
cohort.

Frozen policies: VWAP_BANDS_GLOBEX_V1, DRYSDALE_VALUE_AREA_V1, LAB_VWAP_SLOPE_V1,
LAB_VOLUME_CONTEXT_V1, LAB_BREAKOUT_TRIGGER_V1, LAB_ACCEPTANCE_TIME_V1,
LAB_RETEST_V1, LAB_REJECTION_V1, LAB_DIRECTIONAL_CONFIRMATION_V1,
LAB_RETURN_TO_VALUE_V1, LAB_VWAP_TEST_V1, LAB_TREND_CONTEXT_V1,
DRYSDALE_SETUP_CANDIDATES_V1 (reused unchanged: BARS_5M_V1, ATR_5M_V1).

sha256 of the frozen files (policy code, policy documentation, fixtures, and the
integration modules it ships with). The freeze commit is the commit that adds
this file.

```text
51948f806acd86d295f1a12432d2e0e37d49ec7de709e7afc1f1b957920165af  apps/dicks_laboratory/src/dicks_laboratory/drysdale.py
8bb1e4c14da0153ddb04ca97b32a4eb28924a4763c285d747c6e629df395d29a  docs/dicks_laboratory/DRYSDALE_VWAP_TRAINING_CANDIDATES.md
2a39fac87bddbfafc4cfe2a0c8078ca631cbe5d67200200a10fd376b8e1f9cb3  apps/dicks_laboratory/tests/test_drysdale.py
3143f8d63a59f88e39419751c64d5553a11a70bfc47c4f55ee5dfe1ca53b825b  apps/dicks_laboratory/src/dicks_laboratory/price_action.py
898dd904ab99b3eceba216433ded09acc55956df5483c31f540a0edfda10cbf3  apps/dicks_laboratory/src/dicks_laboratory/tutor_evidence.py
34b14f65ab1f8729027ae129bbe4628190f0814c1006298f77cb1a305ed47143  apps/dicks_laboratory/src/dicks_laboratory/tutor_ai.py
```
