# usage: run_one.sh <label> <date> <db> <prior> <outfile>  (one heavy job; appends to run.log)
set -u
cd ~/Documents/REPOs/copper
S=/tmp/claude-1000/-home-temckee8-Documents-REPOs-copper/96ab414c-d152-44d1-8d33-1c2f8cf9c58c/scratchpad/0abd
O=$S/dev_out; M=~/secure/mp_corpus; HEAD=d3e1ee24bc8711903e6ff9293bf4454acab31d00
echo "[$1] start $(date -Is); MemAvailable $(awk '/MemAvailable/{print $2}' /proc/meminfo) kB" >> $O/run.log
/usr/bin/time -v uv run python $S/harness/run_pinned.py date $M/$3.sqlite3 --prior-db $M/$4.sqlite3 --out $O/$5 --analysis-commit $HEAD >> $O/run.log 2> $O/$1.time
rc=$?
echo "[$1] end $(date -Is) exit $rc; peak RSS $(awk -F: '/Maximum resident/{print $2}' $O/$1.time) kB; wall $(awk -F'): ' '/Elapsed/{print $2}' $O/$1.time)" >> $O/run.log
echo DONE_$1 >> $O/run.log
