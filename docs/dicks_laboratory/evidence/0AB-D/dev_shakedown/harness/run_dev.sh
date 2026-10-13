set -u
cd ~/Documents/REPOs/copper
S=${SCRATCH:?}
O=$S/dev_out; rm -rf $O; mkdir -p $O
M=~/secure/mp_corpus
DBS="$M/es_20260928_843a6ca0.sqlite3 $M/es_20260929_6af08205.sqlite3 $M/es_20260930_9ac5a21e.sqlite3 $M/es_20261001_fe280370.sqlite3 $M/es_20261002_7e8d7b5e.sqlite3"
HEAD=$(git rev-parse HEAD)
sha256sum $DBS > $O/db_sha_before.txt
echo "HEAD $HEAD; drysdale.py $(sha256sum apps/dicks_laboratory/src/dicks_laboratory/drysdale.py | cut -c1-64); drysdale_quality.py $(sha256sum apps/dicks_laboratory/src/dicks_laboratory/drysdale_quality.py | cut -c1-64); drysdale_validation (pinned) $(sha256sum $S/harness/dv_pinned.py | cut -c1-64); cli (pinned) $(sha256sum $S/harness/cli_pinned.py | cut -c1-64)" > $O/run.log
for spec in "2026-09-29 es_20260929_6af08205 es_20260928_843a6ca0" "2026-09-30 es_20260930_9ac5a21e es_20260929_6af08205" "2026-10-01 es_20261001_fe280370 es_20260930_9ac5a21e" "2026-10-02 es_20261002_7e8d7b5e es_20261001_fe280370"; do
  set -- $spec
  echo "[$1] start $(date -Is)" >> $O/run.log
  /usr/bin/time -v uv run python $S/harness/run_pinned.py date $M/$2.sqlite3 --prior-db $M/$3.sqlite3 --out $O/$1_record.json --analysis-commit $HEAD >> $O/run.log 2> $O/$1.time || echo "FAILED $1" >> $O/run.log
  echo "[$1] end $(date -Is)" >> $O/run.log
done
for spec in "2026-09-29 es_20260929_6af08205 es_20260928_843a6ca0" "2026-10-02 es_20261002_7e8d7b5e es_20261001_fe280370"; do
  set -- $spec
  echo "[$1] rerun start $(date -Is)" >> $O/run.log
  uv run python $S/harness/run_pinned.py date $M/$2.sqlite3 --prior-db $M/$3.sqlite3 --out $O/$1_record_rerun.json --analysis-commit $HEAD >> $O/run.log 2>&1 || echo "FAILED rerun $1" >> $O/run.log
  python3 -c "import json,sys; a,b=(json.load(open(f))['record_sha256'] for f in sys.argv[1:]); print('[%s] cross-process record_sha256 identical: %s' % (sys.argv[1].split('/')[-1][:10], a==b))" $O/$1_record.json $O/$1_record_rerun.json >> $O/run.log
done
uv run python $S/harness/run_pinned.py cohort $O/2026-09-29_record.json $O/2026-09-30_record.json $O/2026-10-01_record.json $O/2026-10-02_record.json --date 2026-09-29 --date 2026-09-30 --date 2026-10-01 --date 2026-10-02 --json-out $O/dev_cohort_summary.json --md-out $O/dev_readout.md >> $O/run.log 2>&1 || echo "FAILED cohort" >> $O/run.log
sha256sum $DBS > $O/db_sha_after.txt
cmp -s $O/db_sha_before.txt $O/db_sha_after.txt && echo "DATABASE SHA256 UNCHANGED" >> $O/run.log || echo "DATABASE SHA256 CHANGED" >> $O/run.log
echo DEV_DONE >> $O/run.log
