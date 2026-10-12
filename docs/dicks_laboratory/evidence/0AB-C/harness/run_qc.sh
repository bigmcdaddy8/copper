set -u
cd ~/Documents/REPOs/copper
S=${SCRATCH:?set SCRATCH}
O=$S/qc_out; rm -rf $O; mkdir -p $O
M=~/secure/mp_corpus
DBS="$M/es_20260930_9ac5a21e.sqlite3 $M/es_20260929_6af08205.sqlite3 $M/es_20260928_843a6ca0.sqlite3 $M/es_20261002_7e8d7b5e.sqlite3 $M/es_20261001_fe280370.sqlite3"
HEAD=$(git rev-parse HEAD)
sha256sum $DBS > $O/db_sha_before.txt
echo "analysis HEAD $HEAD; drysdale.py sha $(sha256sum apps/dicks_laboratory/src/dicks_laboratory/drysdale.py | cut -c1-64); drysdale_quality (pinned) sha $(sha256sum $S/harness/dq_pinned.py | cut -c1-64)" > $O/run.log
P=$S/harness/qc_audit.py
for spec in "2026-09-29 es_20260929_6af08205 es_20260928_843a6ca0" "2026-09-30 es_20260930_9ac5a21e es_20260929_6af08205" "2026-10-01 es_20261001_fe280370 es_20260930_9ac5a21e" "2026-10-02 es_20261002_7e8d7b5e es_20261001_fe280370"; do
  set -- $spec
  /usr/bin/time -v uv run python $P $O $1 $M/$2.sqlite3 $M/$3.sqlite3 $HEAD >> $O/run.log 2> $O/$1.time || echo "FAILED $1" >> $O/run.log
done
sha256sum $DBS > $O/db_sha_after.txt
cmp -s $O/db_sha_before.txt $O/db_sha_after.txt && echo "DATABASE SHA256 UNCHANGED" >> $O/run.log || echo "DATABASE SHA256 CHANGED" >> $O/run.log
echo QC_DONE >> $O/run.log
