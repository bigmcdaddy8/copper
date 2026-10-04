#!/usr/bin/env bash
set -u
cd /home/temckee8/Documents/REPOs/copper
SRC=/home/temckee8/secure/0w5a/es_20260930_9ac5a21e.sqlite3
R=/home/temckee8/secure/0w5b/results
SNAP=/home/temckee8/secure/0w5b/snap/prefill_to_1957.sqlite3
B="uv run python scripts/dicks_lab_writer_burst_benchmark.py run $SRC --scratch-dir /home/temckee8/secure/0w5b/scratch"
echo "$(date -u +%FT%TZ) CAMPAIGN5 (reruns after benchmark-only fixes: synthetic index overflow, overload recording) code: $(sha256sum apps/dicks_laboratory/src/dicks_laboratory/durable_writer.py apps/dicks_laboratory/src/dicks_laboratory/store.py apps/dicks_laboratory/src/dicks_laboratory/long_running_capture.py scripts/dicks_lab_writer_burst_benchmark.py | awk '{print substr($1,1,12)}' | tr '\n' ' ')" >> $R/campaign.log
run() { local label=$1; shift; echo "$(date -u +%FT%TZ) START $label" >> $R/campaign.log; $B --label $label --output-json $R/$label.json "$@" > $R/$label.log 2>&1; local rc=$?; echo "$(date -u +%FT%TZ) END $label rc=$rc" >> $R/campaign.log; }
P="--mode paced --emulate-iops 603 --prefill-snapshot $SNAP"
run p_wal_1_5x          $P --journal-mode wal --scale 1.5
run p_wal_2x            $P --journal-mode wal --scale 2
run p_delete_1_5x       $P --journal-mode delete --scale 1.5
run p_delete_2x         $P --journal-mode delete --scale 2
run h_delete_2x_1100iops --mode paced --emulate-iops 1100 --emulate-mbps 125 --prefill-snapshot $SNAP --journal-mode delete --scale 2
echo "$(date -u +%FT%TZ) CAMPAIGN5_DONE" >> $R/campaign.log
