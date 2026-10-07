#!/usr/bin/env bash
set -u
cd /home/temckee8/Documents/REPOs/copper
SRC=/srv/dicks_laboratory/data/sessions/es_20260930_9ac5a21e.sqlite3
W=/srv/dicks_laboratory/data/bench_0w5c
R=$W/results
B="/home/temckee8/.local/bin/uv run --frozen python /tmp/bench_0w5c.py run $SRC --scratch-dir $W/scratch --mode paced --real-concurrency --prefill-snapshot $W/snap/prefill_to_1957.sqlite3"
echo "$(date -u +%FT%TZ) CAMPAIGN 0W-5C actual-disk HEAD=$(git rev-parse HEAD) writer=$(sha256sum apps/dicks_laboratory/src/dicks_laboratory/durable_writer.py | cut -c1-12) bench=$(sha256sum /tmp/bench_0w5c.py | cut -c1-12) source=$(sha256sum $SRC | cut -c1-12)" >> $R/campaign.log
run() { local label=$1; shift; echo "$(date -u +%FT%TZ) START $label" >> $R/campaign.log; $B --label $label --output-json $R/$label.json "$@" > $R/$label.log 2>&1; local rc=$?; echo "$(date -u +%FT%TZ) END $label rc=$rc" >> $R/campaign.log; sleep 60; }
run a_wal_1x      --journal-mode wal    --scale 1
run a_wal_1_5x    --journal-mode wal    --scale 1.5
run a_wal_2x      --journal-mode wal    --scale 2
run a_delete_1x   --journal-mode delete --scale 1
echo "$(date -u +%FT%TZ) CAMPAIGN_DONE" >> $R/campaign.log
