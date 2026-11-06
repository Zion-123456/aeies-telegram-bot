# Deployment readiness — 6 November 2026

## Repository

PASS — continued clean `feature/deployment-readiness` at `a714ef4`, fetched remote
branches, and preserved existing work. Main remains at
`fbf3a85c10b5da777e7b48b8366b3433c9c91d4e`; no merge/reset/force-push performed.
This report is committed with the changes described below; use `git log -1` for
the resulting documentation commit rather than a self-referential commit hash.

## Live Supabase state

NOT TESTED — independent reinspection in this session. The user supplied verified
external evidence for project `vvfoofamchxatwyttypp`, eu-west-2:

- 001_initial and 002_backend_role applied through the integration.
- 16 private aeies tables with RLS and reference data seeded.
- PUBLIC/anon/authenticated EXECUTE revoked on public.rls_auto_enable(), with its
  event trigger preserved.
- Security advisor zero findings; performance advisor 17 unindexed foreign keys
  and 7 unused-index notices.

These are the latest known live facts, not claims of an empty database. They were
not repeated, reverted, or re-applied here. The bot and verification code require
003's audit details column and 004's MP4 constraint, so this partial live schema
must not be treated as application-ready.

BLOCKED — live reconciliation, 003/004/005 application, runtime login inspection,
security/performance advisor reruns and remote RLS verification. No Supabase tools
are exposed and no MIGRATION_DATABASE_URL, DATABASE_URL, SUPABASE_ACCESS_TOKEN or
TELEGRAM_BOT_TOKEN is present. No new project, paid service or credential rotation
was performed. Formz, Forge and managed infrastructure schemas were untouched.

## Reconciliation evidence and changes

PASS — the runner records exact SQL-file SHA-256 hashes in public.aeies_migrations,
which is separate from Supabase's migration history. It now refuses an existing
application schema without an initial repository journal entry before attempting
application migrations. It does not guess adoption or re-execute 001/002.

PASS — added scripts/adopt_migrations.py and deploy/MIGRATION_ADOPTION.md. Adoption
builds a reference from the exact committed 001/002 in an empty local
`aeies_reference` database, inside a transaction that always rolls back. It checks
Supabase history names and compares relations, columns/defaults, sequences,
constraints, indexes, policies, custom triggers/routines, grants, reference seeds
and backend-role flags/inheritance. Target objects must belong to the connected
migration identity; different owners cause refusal. Only an equivalent target receives 001/002
checksums in a transaction. The target's application DDL/data and Supabase history
are not rewritten. Object owners, operational sequence positions and application
rows are deliberately not compared; owners require separate live inspection.

PASS — fresh installation, repeat adoption, continuation through later migrations,
and fail-closed refusal of column, seed, policy, history, grant and sequence drift
were tested against disposable PostgreSQL databases. Refused adoption leaves no
repository journal, and reference DDL is rolled back. Existing migration files
001–004 are unchanged. The evidence proves local catalog equivalence checks,
not that remote reconciliation has happened or that remote SQL bytes matched.

BLOCKED — actual live equivalence and journal reconciliation. If migration names,
owner privileges, defaults or definitions differ, inspect and document the
specific discrepancy; never mark unverified migrations as adopted.

## Index investigation

PASS — local baseline inspection found 20 foreign keys without a full valid
prefix index. Three were already partly covered by partial indexes. This is a
stricter check than accepting partial coverage and is consistent with needing
17 additional indexes, but the live advisor's exact list remains uninspected.

PASS — new migration 005_foreign_key_indexes.sql adds 17 indexes and expands the
three existing partial indexes to full indexes with the same names/keys. This
avoids redundant full-prefix indexes and covers archived/inactive child rows.
SQL comments and MIGRATION_ADOPTION.md explain every access pattern: academic
profile aggregates, scope lookup, course filters, category/session/uploader queries,
reverse bookmarks/reports, feedback student/assignee queues, actor audit and
student delivery history. Existing primary-key and other suitable index prefixes
are reused. No indexes were removed solely because a new database reports them
unused. Index replacement requires a maintenance window before live execution.

PASS — all local application foreign keys have a full valid prefix index after
005. BLOCKED — live index deployment and performance-advisor rerun. No claim is
made that live notices have cleared.

## Security and runtime identity

PASS — local tests verify private-schema RLS/API-role exclusion, restricted
runtime-login operation, audit UPDATE/DELETE denial, server-side administrative
scope checks, cross-user private-data isolation, actor-bound replay checks,
verified-TLS configuration, and rejection of superuser/BYPASSRLS bot connections.
The runtime backend is trusted with application-wide access; Telegram user
permissions are enforced by services, not by imaginary Supabase Auth identities.

NOT TESTED — live owner-role inheritance and complete function/sequence grants,
remote runtime identity, TLS handshake and exposed Data API schema configuration.
BLOCKED — these need the remote connection/integration. Existing credentials were
not inspected for values, changed or rotated. Previous readiness fixes remain.

## Executed checks

| Check | Status and exact result |
| --- | --- |
| Full suite including PostgreSQL and mocked Telegram | PASS — 65 passed, 0 failed/skipped, 34.93 seconds |
| Adoption tests | PASS — matching prefix and drift/refusal cases included in full suite |
| Fresh installation and restricted login | PASS — full-suite fresh-database coverage |
| Registration, resources, PDF/DOCX/MP4 backups and delivery mocks | PASS — full-suite coverage |
| Scope boundaries, RLS, feedback, bookmarks and audit rollback | PASS — full-suite coverage |
| Cross-user isolation and update replay | PASS — full-suite coverage |
| Polling lifecycle and restart recovery | PASS — full-suite mocked API coverage |
| Foreign-key prefix index coverage | PASS — no uncovered FK after 005 |
| Ruff lint and formatting | PASS — 28 Python files formatted, no lint findings |
| Dependency consistency | PASS — pip check reports no broken requirements |
| Vulnerability audit | PASS — pip-audit reports no known vulnerabilities |
| Immutable migrations 001–004 | PASS — no differences from starting branch |
| git diff --check | PASS |
| Real Supabase migrations/security/performance advisors | BLOCKED — no integration or connection |
| Real Telegram sends/two-student journey | BLOCKED — no token or human test-account access |
| Installed host/service health and graceful shutdown | NOT TESTED — no host provisioned; service template only |
| GitHub Actions run | NOT TESTED — workflow remains manual, billing not confirmed |

Commands used the disposable loopback aeies_test PostgreSQL database, never the
live project. No real student information or original academic documents were
used. An initial adoption-test failure exposed a PostgreSQL catalog type-cast
error; it was fixed and the final suite passed without weakening assertions.

## Telegram and final deployment decision

BLOCKED — production deployment approval. Do not launch against the partially
migrated live schema. No live Telegram functionality or end-to-end success is
claimed from mocked tests. No polling worker or paid host was deployed here.

1. Expose the integration for the approved project or securely configure its
   privileged MIGRATION_DATABASE_URL. Never paste secrets into chat.
2. Inspect actual history, schema, owners, roles, extensions and preserved event
   trigger. Follow MIGRATION_ADOPTION.md; stop on any equivalence discrepancy.
3. After verified adoption, run scripts/migrate.py and scripts/verify_database.py
   with migration credentials; independently verify 003/004/005 and rerun advisors.
4. Inspect existing runtime identity before provisioning anything. Use the
   existing provisioning script only if the login is absent; do not rotate or
   overwrite existing credentials. Check effective ownership/inheritance and
   least-required privileges. Configure a separate verified-TLS DATABASE_URL.
5. Configure TELEGRAM_BOT_TOKEN securely in the local .env or host secret store;
   migration credentials must not be present in the normal bot process.
6. Use human-controlled synthetic accounts for actual registration, scoped upload,
   file receipt by two students, bookmarks, requests, feedback resolution, audit
   and analytics checks; restart and verify persisted state and private-data
   isolation. Test failed as well as successful delivery.
7. Review host settings before using deploy/aeies.service. One continuous worker,
   durable originals, restart limits and journal monitoring are documented. No
   purchase, paid provisioning, merge to main or billed CI run is authorized here.

Windows startup after schema readiness and secure local configuration:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m aeies
```

Copy .env.example only if .env does not already exist, then enter the dedicated
runtime connection and BotFather token locally. Keep the laptop awake/online.
Windows execution and a real deployed service remain NOT TESTED.
