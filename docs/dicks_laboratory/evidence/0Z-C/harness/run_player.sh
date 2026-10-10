set -u
cd ~/Documents/REPOs/copper
S=$SCRATCH
O=$S/player_run; rm -rf $O; mkdir -p $O
M=~/secure/mp_corpus; L=apps/dicks_laboratory/data
DBS="$M/es_20260930_9ac5a21e.sqlite3 $M/es_20260929_6af08205.sqlite3 $M/es_20261002_7e8d7b5e.sqlite3 $M/es_20260921_64d684c9.sqlite3 $L/0w2_attempt2/es_20260831_c9ebc043.sqlite3 $L/0w2a_verification/es_20260828_5a5fbbce.sqlite3"
HEAD=$(git rev-parse HEAD)
sha256sum $DBS > $O/db_sha_before.txt
echo "analysis HEAD $HEAD (worktree: $(git status --porcelain -- apps scripts | wc -l) modified paths)" > $O/run.log
P=$S/player_proof.py
/usr/bin/time -v uv run python $P $O 2026-09-30 $M/es_20260930_9ac5a21e.sqlite3 $M/es_20260929_6af08205.sqlite3 $HEAD "09:47,12:14,14:32,09:29,09:30,14:59,15:00" "12:14:00~12:14:01,09:29~09:30,14:59~15:00" >> $O/run.log 2> $O/0930.time
/usr/bin/time -v uv run python $P $O 2026-10-02 $M/es_20261002_7e8d7b5e.sqlite3 - $HEAD "09:30" "2026-10-02T07:40:03.790478+00:00~2026-10-02T07:40:05.790478+00:00" >> $O/run.log 2> $O/1002.time
/usr/bin/time -v uv run python $P $O 2026-09-21 $M/es_20260921_64d684c9.sqlite3 - $HEAD "08:31" "2026-09-21T02:55:11+00:00~2026-09-21T02:55:12.5+00:00,2026-09-21T02:55:12.5+00:00~2026-09-21T02:55:14+00:00" >> $O/run.log 2> $O/0921.time
/usr/bin/time -v uv run python $P $O 2026-08-31 $L/0w2_attempt2/es_20260831_c9ebc043.sqlite3 $L/0w2a_verification/es_20260828_5a5fbbce.sqlite3 $HEAD "08:45,09:30,10:00" "08:45~09:30" >> $O/run.log 2> $O/0831.time
sha256sum $DBS > $O/db_sha_after.txt
cmp -s $O/db_sha_before.txt $O/db_sha_after.txt && echo "DATABASE SHA256 UNCHANGED" >> $O/run.log || echo "DATABASE SHA256 CHANGED" >> $O/run.log
for x in 0930 1002 0921 0831; do echo "$x: $(grep -E 'Maximum resident|Elapsed' $O/$x.time | tr '\n' ' ')" >> $O/run.log; done
echo PLAYER_DONE >> $O/run.log
