# Deployment readiness audit — 6 November 2026

## Repository

PASS: started with a clean checkout of main at
`fbf3a85c10b5da777e7b48b8366b3433c9c91d4e`, fetched remote main, and reproduced
the original 51 tests. Changes are on `feature/deployment-readiness`; no merge
into main is authorized or performed. The existing test container was stopped
after environment restoration and was restarted before the successful baseline.

## Defects and fixes

- Remote PostgreSQL `hostaddr` could bypass the TLS guard when `host` was empty
  or local. Address selection now includes `hostaddr`; regression coverage added.
- Cached update responses were keyed only by update ID. Bind cached responses to
  the originating actor and reject cross-user or legacy unbound replays. Actual
  Telegram update IDs come from the API; this strengthens the service boundary.
- Migration CLI could silently use DATABASE_URL. It now requires the explicitly
  privileged MIGRATION_DATABASE_URL and has a subprocess regression test.
- Runtime startup accepted superuser/BYPASSRLS connections. These now fail with
  a safe configuration error; polling tests use a restricted backend role.
- Schema verification did not check effective API-role schema/table access or
  excessive runtime-role privileges. Those checks and a negative access-grant
  regression test were added. This is not a complete role-membership audit.
- Vulnerability scan reported python-dotenv 1.2.1 (PYSEC-2026-2270) and pytest
  8.4.2 (PYSEC-2026-1845). Updated to 1.2.2 and 9.0.3, respectively, with
  pytest-asyncio 1.3.0 for compatibility. No advisory exceptions were suppressed.

## Validation results

| Check | Result |
| --- | --- |
| Original full suite | PASS — 51 tests |
| Final full pytest suite | PASS — 57 tests, no skips, 28.62 seconds |
| Focused application/readiness suite | PASS — 10 tests, 2.27 seconds |
| Local schema verifier | PASS — 16 tables, RLS policies, indexes, uniqueness, audit protections, checksums and API-role checks |
| Fresh database migration/runtime login | PASS — exercised by full suite, including Supabase-style default grants |
| PDF, DOCX, MP4 originals and mocked delivery | PASS — full-suite coverage |
| Scoped authorization, feedback, bookmarks, isolation, rollback | PASS — full-suite coverage |
| Mocked polling start/stop/restart | PASS — full-suite coverage |
| Ruff lint and formatting | PASS — 25 Python files formatted, no lint findings |
| pip check | PASS — no broken requirements |
| pip-audit -r requirements.txt | PASS — no known vulnerabilities reported after patches |
| git diff --check | PASS |
| Existing migration files | PASS — unchanged |
| GitHub Actions execution | BLOCKED/not run — manual trigger pending runner billing confirmation |

Full suite used PostgreSQL 17 on loopback with synthetic identities and files,
never Supabase. Run it with a dedicated disposable aeies_test database:

```sh
TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/aeies_test PTB_TIMEDELTA=1 .venv/bin/python -m pytest -q
```

## Live infrastructure status

BLOCKED: user-confirmed project `vvfoofamchxatwyttypp`, AEIES Academic Assistant,
Zion 2 organisation `zhbulwchngsxiflikoze`, eu-west-2. The user authorized this
project and prohibited creating another. No Supabase tools are exposed in this
session and no access token, migration connection, runtime connection or Telegram
bot token is configured. Platform status also reports no secret bindings or
runtime variables. User-reported ACTIVE_HEALTHY has not been independently checked.

No remote schema inspection, migration application, runtime-login provisioning,
`public.rls_auto_enable()` dependency inspection or privilege change, or security
and performance advisor run was possible. These are BLOCKED, not PASS. The event
trigger must be inspected before revoking unnecessary function execution rights.
All Supabase-managed schemas, Formz and Forge remain untouched.

Actual Telegram registration, upload/delivery, two-student journey, bookmark,
feedback resolution, analytics, and restart checks are BLOCKED. Mocked successful
and failed sends do not establish real Telegram delivery. Existing tests preserve
the product's cross-department academic discovery; administrative mutations and
private feedback/profile access remain scoped. No new student department-only
restriction was invented without a product requirement.

## Deployment and remaining actions

Prepared, not deployed: systemd unit and operating instructions in deploy/README.md.
Use one continuously running polling worker with persistent original-file storage;
no serverless polling function or paid host was created. No charges were incurred
by provisioning in this task. GitHub Actions remains manual until billing is known.

1. Expose the Supabase integration for the confirmed project, or securely bind its
   privileged MIGRATION_DATABASE_URL. Never paste credentials into chat.
2. Inspect the remote schema, roles, extensions, event triggers and advisors, apply
   immutable migrations transactionally, verify, and provision the dedicated login.
3. Securely configure runtime DATABASE_URL (verified TLS) and a dedicated
   TELEGRAM_BOT_TOKEN, excluding migration credentials from the bot process.
4. Complete the real two-student Telegram journey with human-controlled test
   accounts and a non-sensitive sample file, then verify persistence after restart.
5. Review the feature branch and host configuration, confirm costs before any
   hosting purchase or billed CI run, and deploy only after live checks succeed.

Environment startup instructions were updated in the saved configuration draft
to use the approved existing project. That save does not apply runtime settings,
publish an environment, or establish deployment readiness.

## Windows startup

After securely setting DATABASE_URL and TELEGRAM_BOT_TOKEN in local .env:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m aeies
```

If .env does not exist, copy .env.example first without overwriting existing
configuration. The laptop must remain awake and online. These commands are
documented; a real Windows runtime and live bot were not tested in this session.
