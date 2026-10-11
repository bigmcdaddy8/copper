set -u
cd ~/Documents/REPOs/copper
S=${SCRATCH:?set SCRATCH}
O=$S/out; rm -rf $O; mkdir -p $O
M=~/secure/mp_corpus; L=apps/dicks_laboratory/data
DBS="$M/es_20260930_9ac5a21e.sqlite3 $M/es_20260929_6af08205.sqlite3 $L/0w2_attempt2/es_20260831_c9ebc043.sqlite3 $L/0w2a_verification/es_20260828_5a5fbbce.sqlite3"
HEAD=$(git rev-parse HEAD)
sha256sum $DBS > $O/db_sha_before.txt
echo "analysis HEAD $HEAD (worktree: $(git status --porcelain -- apps scripts | wc -l) modified paths under apps/ scripts/); claude $(claude --version 2>/dev/null)" > $O/run.log
P=$S/ai_proof.py
uv run python $P $O 2026-09-30 $M/es_20260930_9ac5a21e.sqlite3 $M/es_20260929_6af08205.sqlite3 $HEAD \
  "vwap_1000_reveal_1030|PRICE_VS_CASH_VWAP|10:00||10:30" \
  "ib_0915|INITIAL_BALANCE_STATUS|09:15||" "ib_0930|INITIAL_BALANCE_STATUS|09:30||" \
  "changes_121400_121401|EVIDENCE_CHANGES|12:14:01|12:14:00|" \
  "acceptance_1000|VWAP_ACCEPTANCE|10:00||" \
  "injection_vwap_1000|PRICE_VS_CASH_VWAP|10:00|||poison" >> $O/run.log 2> $O/0930.err
uv run python $P $O 2026-08-31 $L/0w2_attempt2/es_20260831_c9ebc043.sqlite3 $L/0w2a_verification/es_20260828_5a5fbbce.sqlite3 $HEAD \
  "vwap_1000_stale|PRICE_VS_CASH_VWAP|10:00||" >> $O/run.log 2> $O/0831.err
sha256sum $DBS > $O/db_sha_after.txt
cmp -s $O/db_sha_before.txt $O/db_sha_after.txt && echo "DATABASE SHA256 UNCHANGED" >> $O/run.log || echo "DATABASE SHA256 CHANGED" >> $O/run.log
echo AI_DONE >> $O/run.log
