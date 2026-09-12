# WARHUB independent backup scheduler

Prepared for Ubuntu 24.04/systemd; **not installed or enabled by committing these files**.

The service checks GitHub's main snapshot every 30 minutes. It only dispatches the existing workflow after 130 minutes of snapshot age, with no unfinished workflow runs. GitHub's existing concurrency lock and 110-minute guard still decide whether collection is needed. It uses auto mode and quiet=true (no Telegram/Discord). It does not clone or collect on the VPS, force full refresh, change GitHub cron, or directly deploy Vercel.

A 120-minute local cooldown is persisted before dispatch, including ambiguous network failures. This deliberately sacrifices a retry opportunity to avoid duplicate requests. API acceptance does not establish successful collection. Invalid timestamps/state and API errors fail closed. Monitor the journal; unresolved invalid state or a permanently waiting workflow needs operator attention.

## Credential and installation

Use a dedicated fine-grained GitHub token scoped only to virus11456/warhub with Contents read and Actions write. Actions write is broader than dispatch alone: it can manage workflow runs; do not reuse a broad personal token. An operator must authorize this new access and provision the token directly as `/etc/warhub-backup/github-token` (root-owned directory 0700 and file 0600). Do not put it in Git, browser chat, command arguments or logs. Record its actual expiry separately. No credential is included here.

Official permissions: https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event

After reviewing the specific server and provisioning the credential:

1. Install `scripts/backup_scheduler.py` to `/opt/warhub-backup/backup_scheduler.py` (root-owned, 0644).
2. Install the two unit files in `/etc/systemd/system/`, then run `systemd-analyze verify` on them and `systemctl daemon-reload`.
3. Before enabling, run the service's Python command with the credential loaded but **without --apply**; confirm fresh/would_dispatch, with no POST or state mutation.
4. Enable/start `warhub-backup.timer`. Verify its next activation with `systemctl list-timers warhub-backup.timer` and inspect `journalctl -u warhub-backup.service`.
5. Verify a due execution's Actions run, persisted snapshot/archive, quiet notification behavior, and data-only build skip. Only then call the end-to-end recovery verified.

The service uses a dynamic user and systemd credentials, with only its own StateDirectory writable. Do not restart the VPS or alter unrelated services to install it. Stop/disable the timer to roll back; leave the original GitHub schedule in place. Keep the state across ordinary restarts.

Checks: `python -m unittest discover -s tests -p test_backup_scheduler.py -v` (offline fixtures; no requests, messages or dispatch).
