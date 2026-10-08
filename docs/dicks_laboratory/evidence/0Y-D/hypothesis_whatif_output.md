H1  NEUTRAL_DAY would require BOTH extensions >= X * IB
| X | Neutral candidates still passing (of 5) | dates no longer passing |
|---|---|---|
| 0.10 | 2 | 2026-09-30, 2026-10-01, 2026-10-02 |
| 0.25 | 1 | 2026-09-24, 2026-09-30, 2026-10-01, 2026-10-02 |
| 0.50 | 1 | 2026-09-24, 2026-09-30, 2026-10-01, 2026-10-02 |
| 1.00 | 0 | 2026-09-24, 2026-09-28, 2026-09-30, 2026-10-01, 2026-10-02 |

H2  NORMAL_VARIATION_DAY would require extension >= Y * IB
| Y | NV candidates still passing (of 6) | dates no longer passing |
|---|---|---|
| 0.10 | 6 | - |
| 0.25 | 5 | 2026-09-02 |
| 0.50 | 2 | 2026-09-02, 2026-09-15, 2026-09-23, 2026-10-06 |
| 1.00 | 0 | 2026-09-02, 2026-09-15, 2026-09-23, 2026-09-25, 2026-09-29, 2026-10-06 |

H3  BOTH_SIDES days whose smaller side is < X * IB ('token counter-extension'); dominant side shown
| X | days | dominant side (larger extension) and larger/IB |
|---|---|---|
| 0.10 | 3 | 2026-09-30 DOWN 1.2302, 2026-10-01 DOWN 0.1645, 2026-10-02 DOWN 0.5532 |
| 0.25 | 4 | 2026-09-24 UP 0.9107, 2026-09-30 DOWN 1.2302, 2026-10-01 DOWN 0.1645, 2026-10-02 DOWN 0.5532 |
