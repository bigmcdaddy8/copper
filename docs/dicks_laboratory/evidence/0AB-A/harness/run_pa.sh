set -u
cd ~/Documents/REPOs/copper
S=${SCRATCH:?set SCRATCH}
O=$S/out; rm -rf $O; mkdir -p $O
M=~/secure/mp_corpus
DBS="$M/es_20260930_9ac5a21e.sqlite3 $M/es_20260929_6af08205.sqlite3 $M/es_20260928_843a6ca0.sqlite3 $M/es_20261002_7e8d7b5e.sqlite3 $M/es_20261001_fe280370.sqlite3"
HEAD=$(git rev-parse HEAD)
sha256sum $DBS > $O/db_sha_before.txt
echo "analysis HEAD $HEAD (worktree: $(git status --porcelain -- apps scripts | wc -l) modified paths under apps/ scripts/)" > $O/run.log
P=$S/pa_proof.py
T="08:00,09:00,10:00,12:00,15:00,16:00"
/usr/bin/time -v uv run python $P $O 2026-09-30 $M/es_20260930_9ac5a21e.sqlite3 $M/es_20260929_6af08205.sqlite3 $HEAD $T >> $O/run.log 2> $O/0930.time
/usr/bin/time -v uv run python $P $O 2026-09-29 $M/es_20260929_6af08205.sqlite3 $M/es_20260928_843a6ca0.sqlite3 $HEAD $T >> $O/run.log 2> $O/0929.time
/usr/bin/time -v uv run python $P $O 2026-10-02 $M/es_20261002_7e8d7b5e.sqlite3 $M/es_20261001_fe280370.sqlite3 $HEAD $T >> $O/run.log 2> $O/1002.time
/usr/bin/time -v uv run python $S/pa_mutation.py $O $M/es_20260929_6af08205.sqlite3 $M/es_20260928_843a6ca0.sqlite3 $HEAD $HOME/.cache/dicks_lab_0aba >> $O/run.log 2> $O/mutation.time
sha256sum $DBS > $O/db_sha_after.txt
cmp -s $O/db_sha_before.txt $O/db_sha_after.txt && echo "DATABASE SHA256 UNCHANGED" >> $O/run.log || echo "DATABASE SHA256 CHANGED" >> $O/run.log
for x in 0930 0929 1002 mutation; do echo "$x: $(grep -E 'Maximum resident|Elapsed|Exit status' $O/$x.time | tr '\n' ' ')" >> $O/run.log; done
echo PA_DONE >> $O/run.log
