set -u
cd ~/Documents/REPOs/copper
S=$SCRATCH
O=$S/rp_formal2; rm -rf $O; mkdir -p $O
M=~/secure/mp_corpus; CUR=$M/es_20260930_9ac5a21e.sqlite3; PRI=$M/es_20260929_6af08205.sqlite3; C1002=$M/es_20261002_7e8d7b5e.sqlite3
HEAD=$(git rev-parse HEAD)
sha256sum $CUR $PRI $C1002 > $O/db_sha_before.txt
echo "analysis HEAD $HEAD; analysis code identical to a8edf2fb: $(git diff --quiet a8edf2fb676f041af6f9dd013b31e47e260a77f2 HEAD -- apps scripts && echo yes || echo NO)" > $O/run.log
echo "== A snapshots" >> $O/run.log
/usr/bin/time -v uv run python $S/replay_proof.py $O/A $CUR $PRI $HEAD clean >> $O/run.log 2> $O/A.time
echo "== B final state (0Z-A CLI)" >> $O/run.log
/usr/bin/time -v uv run python scripts/dicks_lab_market_study_state.py $CUR --prior-database $PRI --json-out $O/final_state.json > $O/final_state_summary.txt 2> $O/B.time
echo "== C compare" >> $O/run.log
/usr/bin/time -v python3 $S/compare_convergence.py $O/A/terminal_snapshot_1700.json $O/final_state.json $O/convergence.json >> $O/run.log 2> $O/C.time
echo "== D 10-02 cancel" >> $O/run.log
/usr/bin/time -v uv run python $S/cancel_1002.py $C1002 $O/cancel_2026-10-02.txt $HEAD >> $O/run.log 2> $O/D.time
sha256sum $CUR $PRI $C1002 > $O/db_sha_after.txt
cmp -s $O/db_sha_before.txt $O/db_sha_after.txt && echo "DATABASE SHA256 UNCHANGED" >> $O/run.log || echo "DATABASE SHA256 CHANGED" >> $O/run.log
for x in A B C D; do echo "$x: $(grep -E 'Maximum resident|Elapsed' $O/$x.time | tr '\n' ' ')" >> $O/run.log; done
echo FORMAL_DONE >> $O/run.log
