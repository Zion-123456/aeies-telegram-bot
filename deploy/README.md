# Continuous polling deployment

Use an existing always-on Linux host with Python 3.12, PostgreSQL network access,
and persistent original-file storage. Do not use a short-lived serverless function.
No host has been provisioned or charged for by this change. Obtain approval before
buying a host. Windows local operation remains supported by the main README.
The GitHub Actions workflow is manually dispatched to avoid consuming an unknown
billed runner allowance on push. Confirm runner billing before running it or
enabling push/pull-request triggers. Its jobs automate the full checks.

Install a reviewed checkout at `/opt/aeies`, create a dedicated `aeies` OS user,
and install requirements into `/opt/aeies/.venv`. Keep the checkout read-only to
the service. Create `/var/lib/aeies/originals` owned by that user with mode 0700.
Create `/etc/aeies/runtime.env` readable only by root (0600), containing the real
`TELEGRAM_BOT_TOKEN`, dedicated-login `DATABASE_URL` with verified TLS,
`BACKUP_DIRECTORY=/var/lib/aeies/originals`, and `LOG_LEVEL=INFO`.
Do not place migration credentials, SDK privileged keys, or a `.env` file in
the deployed checkout. Keep required database CA certificates in a read-only path.

Deploy only to the user-approved Supabase project `vvfoofamchxatwyttypp` (Zion 2,
eu-west-2). Inspect the remote schema and `public.rls_auto_enable()` dependencies
before making changes. Run immutable migrations using a separately secured
connection only after reconciling the integration-applied 001/002 as described in
`deploy/MIGRATION_ADOPTION.md`. Do not assume an empty application schema. Use
`MIGRATION_DATABASE_URL`, verify the schema, and provision `aeies_runtime` with
the existing scripts. Do not create another project or modify Formz or Forge.

After successful live checks, copy `deploy/aeies.service` into
`/etc/systemd/system/`, run `systemd-analyze verify` on it, then:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now aeies
sudo systemctl status aeies
sudo journalctl -u aeies --since today
```

Run exactly one instance for this bot token. The service restarts failures with
backoff and stops retrying after repeated startup failures; investigate before
`systemctl reset-failed aeies`. Restart with `systemctl restart aeies`; PostgreSQL
preserves conversations and update deduplication. Telegram sends may still be
repeated or missed around a crash; no exactly-once network-delivery claim is made.

Monitor service state, error-event frequency, original-file disk usage, database
availability and backup freshness. Configure host monitoring separately without
including user messages, tokens or database URLs. Keep encrypted off-host copies
of original files and separate database backups, and test restores. The file-copy
script does not back up PostgreSQL.

This unit is a deployment template, not evidence of an active deployment. Confirm
all paths/users on the chosen host; live Supabase connectivity, Telegram delivery,
security/performance advisors and the two-student end-to-end journey require real
access. No live hosting or Windows service lifecycle has been tested here.
