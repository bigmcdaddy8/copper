#!/usr/bin/env bash
# Read-only 0W-4 host evidence; output streamed as tar on stdout, temp dir removed.
set -u
O=$(mktemp -d /tmp/0w4audit.XXXX)
R=/home/temckee8/Documents/REPOs/copper
sec(){ echo; echo "##### $*"; }
{
sec DATE; date -u; TZ=America/Chicago date
sec UPTIME; uptime; uptime -s; who -b
sec BOOTS; journalctl --list-boots --no-pager | tail -15
sec LAST_X; last -x -F | head -30
sec FAILED_NOW; systemctl --failed --no-pager
sec GIT; cd $R && git rev-parse HEAD; git status --porcelain=v1 | head -30; echo "porcelain_lines=$(git status --porcelain | wc -l)"; git rev-parse origin/master 2>&1; git log -3 --format='%H %ci %s'; git reflog -10 --date=iso 2>&1
sec GIT_FETCH_DRYRUN; timeout 25 git -C $R fetch --dry-run origin 2>&1 | tail -5; echo "fetch_rc=$?"
sec GIT_REMOTE; git -C $R remote -v; ls -la ~/.ssh/ 2>&1; cat ~/.ssh/config 2>/dev/null | sed -E 's/(IdentityFile.*)/\1/'
sec GIT_SSH_TEST; timeout 20 ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -T git@github.com 2>&1 | head -3
sec FILE_MTIMES_SINCE_SOAK; find $R -path $R/.git -prune -o -path $R/.venv -prune -o -type f -newermt '2026-09-20 15:00' -print 2>/dev/null | grep -v __pycache__ | head -30
sec UNIT_FILES; for u in dicks-lab-es-session.service dicks-lab-es-session.timer dicks-lab-launch-gate.service dicks-lab-launch-gate.timer dicks-lab-preflight-gate.service dicks-lab-preflight-gate.timer; do f=$(systemctl show -p FragmentPath --value $u); echo "$u frag=$f $(stat -c '%y' $f) sha=$(sha256sum $f|cut -c1-16) repo=$(sha256sum $R/deploy/dicks_laboratory/systemd/$u 2>/dev/null|cut -c1-16) dropins=$(systemctl show -p DropInPaths --value $u)"; done
ls -la --time-style=full-iso /etc/systemd/system/ | grep -i dicks
sec TIMERS; systemctl list-timers --all --no-pager | grep -iE "dicks|NEXT"
for u in dicks-lab-preflight-gate.timer dicks-lab-launch-gate.timer dicks-lab-es-session.timer; do echo "$u enabled=$(systemctl is-enabled $u) active=$(systemctl is-active $u)"; systemctl show $u -p NextElapseUSecRealtime -p LastTriggerUSec -p UnitFileState; done
sec SESSION_SERVICE_NOW; systemctl show dicks-lab-es-session.service -p ActiveState -p SubState -p Result -p ExecMainStatus -p NRestarts -p ExecMainPID -p InvocationID
pgrep -af dicks_lab || echo "no dicks_lab processes"
sec MARKER; ls -la --time-style=full-iso /run/dicks-lab-launch-gate/ 2>&1; cat /run/dicks-lab-launch-gate/preflight-ok 2>&1
sec DISK; df -h / /srv/dicks_laboratory; df -B1 /srv/dicks_laboratory; findmnt /srv/dicks_laboratory; du -sh /srv/dicks_laboratory/* 2>/dev/null; ls -la --time-style=full-iso /srv/dicks_laboratory/data/sessions/ /srv/dicks_laboratory/logs /srv/dicks_laboratory/forensic 2>&1
sec JOURNAL; journalctl --disk-usage; grep -rhE "^\s*SystemMaxUse|^\s*SystemKeepFree|^\s*MaxRetentionSec|^\s*Storage" /etc/systemd/journald.conf /etc/systemd/journald.conf.d/ 2>/dev/null; ls -la --time-style=full-iso /var/log/journal/*/ | head -30
journalctl --header 2>/dev/null | grep -E "File path|Head real|Tail real|Disk usage" | head -40
sec JOURNAL_OLDEST; journalctl --no-pager -o short-iso -n 1 -r --reverse 2>/dev/null | head -2; journalctl --no-pager -o short-iso | head -2
sec OOM_KERNEL; journalctl -k --since '2026-09-20 15:00' --no-pager | grep -iE "oom|error|fail|hung|blocked for|I/O error|EXT4-fs|reset" | head -30
sec APT_UNATTENDED; systemctl is-enabled apt-daily.timer apt-daily-upgrade.timer unattended-upgrades.service 2>&1; ls -la --time-style=full-iso /var/log/apt/ 2>&1 | head; zgrep -h "Start-Date" /var/log/apt/history.log* 2>/dev/null | tail -5
sec OTHER_TIMERS_1500CT; systemctl list-timers --all --no-pager
sec SMART_FAIL_HISTORY; journalctl --since '2026-09-20 15:00' --no-pager -o short-iso | grep -iE "entered failed state|Failed with result|failed to start" | head -30
sec TAILSCALE_NET; journalctl --since '2026-09-20 15:00' -u tailscaled --no-pager -o short-iso | grep -iE "link change|netcheck|derp.*(home|conn)|down|major" | head -30
sec MEM; free -m
} > $O/host.txt 2>&1
for u in dicks-lab-preflight-gate.service dicks-lab-launch-gate.service dicks-lab-es-session.service dicks-lab-preflight-gate.timer dicks-lab-launch-gate.timer; do
  journalctl -u $u --since '2026-09-20 15:00' --no-pager -o short-iso-precise > $O/j_$u.txt 2>&1
done
journalctl --since '2026-09-20 15:00' --until '2026-09-25 17:00' --no-pager -o short-iso-precise _SYSTEMD_UNIT=init.scope + SYSLOG_IDENTIFIER=systemd 2>/dev/null | grep -iE "dicks|Starting|Started|Finished|Deactivated|Consumed|memory peak|Stopping|Reached target|Shutting|shutdown" | grep -iE "dicks|shutdown|Shutting|power" > $O/j_systemd_dicks.txt
journalctl --since '2026-09-20 15:00' --no-pager -o short-iso-precise -u dicks-lab-es-session.service -o json --output-fields=MESSAGE,_PID,INVOCATION_ID,__REALTIME_TIMESTAMP,_SYSTEMD_INVOCATION_ID > $O/j_session.json 2>&1
journalctl --since '2026-09-20 15:00' --no-pager -o short-iso-precise --grep 'dicks-lab' > $O/j_all_dicks.txt 2>&1
tar -C $O -czf - . ; rm -rf "$O"
