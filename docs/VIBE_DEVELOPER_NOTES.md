# Vibe Developer Notes

## Holodeck Commands

### One-time setup on a fresh machine
./setup.sh

uv run scripts/holodeck_sim.py --clear

## Reporting Commands

uv run enc trades -a HD
uv run enc trades -a HD --status FILLED
uv run enc pnl -a HD --month 2026-01
uv run enc trades -a HD
uv run log show 3ca6f33c
uv run captains_log show 3ca6f33c
uv run captains_log show 3ca6f33c -a HD
uv run captains_log show 3ca6f33c
uv run captains_log show 3ca6f33c -a HD
uv run enc trades -a HD
uv run captains_log show dd6b5f07 -a HD
uv run enc trades -a HD
uv run captains_log show 84cf8ca1 -a HD

### v2 Examples

- Trade Number / TradeManagerNotes (all for HD): ```uv run enc report trade-number -a HD```
- Trade Number for one trade: ```uv run enc report trade-number -a HD --trade-number HD_00001_SIC```
- Daily Notes / traders_daily_work_notes (all for HD): ```uv run enc report daily-notes -a HD```
- Daily Notes filtered by trade: ```uv run enc report daily-notes -a HD --trade-number HD_00012_SIC```
- Daily Notes filtered by underlying: ```uv run enc report daily-notes -a HD --underlying SPX```
- Trade PnL / TradeHistory (both statuses): ```uv run enc report trade-history -a HD```
- Trade PnL closed only with date window: ```uv run enc report trade-history -a HD --status CLOSED --entry-date ">=01/01/2026" --exit-date "<02/01/2026"```
- Trade PnL for one trade: ```uv run enc report trade-history -a HD --trade-number HD_00012_SIC```


### Useful Smoke Flow

- Ensure you have data first: ```uv run scripts/holodeck_sim.py --clear```
- Then run all 3 new reports quickly:
```uv run enc report trade-number -a HD && uv run enc report daily-notes -a HD && uv run enc report trade-history -a HD```

