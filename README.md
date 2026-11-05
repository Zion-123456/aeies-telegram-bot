# AEIES Academic Assistant

A Telegram-first academic resource assistant for Covenant University students.
The initial reference data covers Electrical & Electronics Engineering (EEE),
Information & Communication Engineering (ICE), and Computer Engineering (CPE).
Administrators can add departments without changing the application structure.

## Current readiness

The application implements registration and profile updates, course browsing and
search, resource discovery and delivery, bookmarks, resource requests, feedback
tracking, scoped administrator roles, resource and course management, audit logs,
and basic analytics. Automated tests use real local PostgreSQL and mocked Telegram
APIs. These tests do **not** verify live Telegram delivery or a live Supabase project.

**Account setup remains blocked:** no Supabase integration or credentials were
exposed to the implementation session. No Supabase organisation was inspected and
no remote project was created. No Formz or Forge project was accessed or changed.
No paid resources were created. Do not treat this repository as a completed live
deployment until the account and integration checks below have succeeded.

## Architecture

- `aeies/__main__.py`: async Telegram long-polling application and startup checks.
- `aeies/handlers/router.py`: thin Telegram transport, keyboard rendering, rate-limit
  retries, document backup, and delivery result handling.
- `aeies/services/academic_service.py`: transactional use cases and persisted
  conversation transitions. Keeping a transition and its database writes in one
  service transaction prevents partially saved publication workflows.
- `aeies/services/permission_service.py`: deny-by-default backend authorization.
- `aeies/services/storage_service.py`: replaceable storage protocol, Telegram file
  delivery, original-file validation and local backups.
- `aeies/database/queries.py`: parameterized PostgreSQL access with safe failures.
- `aeies/database/client.py`: optional Supabase SDK adapter; runtime use cases use
  PostgreSQL directly to obtain transactions and row locks across related writes.
- `aeies/keyboards/`, `aeies/middleware/`: expansion points; the initial keyboard
  renderer lives in the transport and authorization lives in services.
- `migrations/`: immutable, checksum-verified migrations and initial reference data.
- `scripts/`: migrations, verification, first-admin bootstrap, runtime login, backups.
- `tests/`: service, PostgreSQL, file storage, transport, and mocked polling tests.
- `backups/`: ignored local originals; never commit academic files or student data.

There is no web dashboard, AI API, Supabase Storage, or hosting dependency.

## Windows installation

Install Python 3.12 and Git. From the checkout in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` directly in
place of `python`; changing machine-wide execution policy is unnecessary.
Enter values in the local `.env` using an editor, or secure environment settings.
Never paste secrets into Telegram, GitHub, logs, or chat.

| Variable | Purpose |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | BotFather token for this bot; required at startup |
| `DATABASE_URL` | Private PostgreSQL runtime connection; required at startup |
| `MIGRATION_DATABASE_URL` | Privileged connection used only by setup scripts |
| `SUPABASE_URL` | Optional SDK project URL, retained for future integrations |
| `SUPABASE_KEY` | Optional server-only SDK key; not needed for direct SQL runtime |
| `BACKUP_DIRECTORY` | Durable original-file folder, default `backups/originals` |
| `LOG_LEVEL` | Application logging level, default `INFO` |

Direct dependencies are pinned. Transitive dependencies are not yet locked.
Windows installation commands are documented; automated execution was on Linux
with Python 3.12 and PostgreSQL 17, not on a physical Windows laptop.

## Supabase configuration and migrations

1. Connect the intended Supabase account and inspect its organisations, project
   capacity, and billing before provisioning anything. Do not use the account
   containing Formz. Do not reuse or alter Formz or Forge.
2. Create a **new** project named `AEIES-Academic-Assistant`, preferring a free
   `eu-west-1` project. If unavailable, document a suitable available region. Stop
   for approval if any subscription or charge is required.
3. Confirm healthy PostgreSQL connectivity. Copy the project connection details
   only into secure local configuration. Use the dashboard's pooler connection
   details when direct IPv6 access is unavailable; use `sslmode=verify-full`
   with the appropriate trusted certificate. The app supplies public CA roots
   by default; configure `sslrootcert` using Supabase's official database CA
   certificate if required. Never disable TLS
   verification to work around a trust error. Do not put a connection string on a
   command line, where it may appear in process listings.
4. Set `MIGRATION_DATABASE_URL` to the new project's privileged database connection.
   From the repository root, run:

   ```powershell
   python scripts/migrate.py
   python scripts/verify_database.py
   ```

5. Create a separate backend login: securely set a generated
   `DATABASE_RUNTIME_PASSWORD` of at least 24 characters, run
   `python scripts/create_runtime_login.py`, then remove that temporary variable.
   Configure `DATABASE_URL` using the new `aeies_runtime` login and the pooler's
   documented custom-role username syntax (commonly `aeies_runtime.PROJECT_REF`).
   Verify connectivity with the bot before removing privileged configuration from
   the laptop's runtime environment. Keep migration credentials separately for
   future schema updates.

The private `aeies` schema is not a PostgREST API schema. Every table has RLS.
No policies assume Telegram users have a Supabase Auth identity. `anon`,
`authenticated`, and `service_role` receive no schema access; only the private
backend database role has the explicit backend policy. The runtime role cannot
update or delete audit records. This role is trusted and can access all application
rows, so every administrative use case also checks server-side roles and scope.
Do not give students database credentials or expose the schema via the Data API.

Migration scripts use a transaction and an advisory lock, and refuse modified
already-applied migrations. Schema verification checks tables, RLS policies,
indexes, uniqueness constraints, audit permissions, and migration checksums.
Initial departments, levels (100L–500L), semesters (Alpha/Omega), and resource
categories are seeded. Sessions and real course lists must be entered by an
administrator; no unofficial course catalogue is invented.

## Telegram setup and startup

Create a dedicated bot through Telegram's BotFather, store its token securely,
and run from the repository root:

```powershell
python -m aeies
```

Use private chat with the bot. Commands and inline keyboards provide the student
and administrator interface. Only one poller may run per bot token. Stop with
Ctrl+C and use the same command to restart; conversations are stored in PostgreSQL.
Use `/resume` to see the saved workflow step, or `/cancel` to leave it.

Students can use the bot remotely through Telegram while it runs on your laptop.
**The bot stops responding when the laptop is off, asleep, or disconnected from
the internet.** No paid hosting is required for this deployment.

## Student workflows

`/start` begins registration: full name, department, level, and preferred semester.
`/register` updates these choices. Registration is required for resources; this
does not verify Covenant University enrolment. `/profile` shows the student's
own profile and Telegram ID.

The main menu has Browse resources, Search resources, My bookmarks, Recently
added, Request a resource, Feedback and support, My profile, and Help.
Browse follows department → level → semester → course → category. `/courses QUERY`
searches the course catalogue even when a course has no files. `/search QUERY`
searches resource titles, course titles, and course codes. Results are paginated.

Open a resource to receive its document with course, category, session, upload
date, and description. Save or remove its bookmark with the inline buttons.
Unavailable material can be requested through `/request`. `/feedback` offers all
seven issue categories; `/report RESOURCE_ID` links feedback to a particular file.
Every submission receives an `AEIES-...` reference. `/track REFERENCE` shows its
status to its owner only.

## First super administrator and scoped roles

Complete your own registration, get your Telegram ID from `/profile`, then run
this **one-time local bootstrap**, substituting your own numeric ID:

```powershell
python scripts/bootstrap_admin.py --telegram-id YOUR_NUMERIC_TELEGRAM_ID
```

It refuses to run if an active super administrator already exists and records
the bootstrap in the audit log. Subsequent role management happens in Telegram.
The last active super-administrator role cannot be revoked.

From a super administrator's private bot chat:

```text
/catalog
/roles grant TELEGRAM_ID resource_admin DEPT_ID LEVEL_ID resources,feedback
/roles grant TELEGRAM_ID executive DEPT_ID LEVEL_ID resources,feedback,courses
/roles grant TELEGRAM_ID executive * * resources,feedback,courses,analytics
/roles revoke ROLE_ID
```

Replace symbolic values with IDs displayed by `/catalog`. New administrators must
register first. `*` means any department or level for executives. Student resource
administrators always require both a department and a level. Allowed permissions
are `resources`, `feedback`, `courses`, `analytics`, `audit`, `reference`, and
`roles`; **only super administrators can manage roles**, even if someone assigns
the `roles` permission to another role. Global analytics, audit, and reference
management require an unscoped applicable role. Students cannot access them.

## Academic reference data and course management

Authorized administrators use `/catalog` for IDs and `/reference` for help:

```text
/reference add academic_sessions 2025/2026
/reference add departments NEW|New Department Name
/reference edit semesters ID|New Name
/reference archive academic_sessions ID
/reference restore academic_sessions ID
/course add CODE|Course title|DEPT_ID|LEVEL_ID|SEMESTER_ID
/course edit COURSE_ID title Updated course title
/course edit COURSE_ID semester_id SEMESTER_ID
/course archive COURSE_ID
/course restore COURSE_ID
```

Example session years above are syntax examples, not seeded current-session
claims. Course codes must resemble `EEE311`. Uniqueness is enforced per
department, level, semester, and code. Moving a course with existing resources
between departments/levels requires super-administrator access because it changes
every attached resource's authorization scope. Other changes check both old and
new scope. Reference data, courses, and resources are archived, not deleted.

## Resource uploads and management

`/upload` guides an authorized administrator through document → title → department
→ level → semester → course → category → academic session → description → final
publication confirmation. Complete course and session setup before uploading.
PDF, DOCX, and MP4 originals up to **20 MB** are accepted; this is an AEIES policy,
not Telegram's stated API maximum. MIME, extension, file signature, size, backup
integrity, active metadata, scope, and duplicate `file_unique_id` are checked.
Publication and its audit event commit together. Failed publication leaves the
original backup and resumable metadata; `/cancel` never deletes originals.

`/manage [search]` lists published and archived resources within the administrator's
scope, with archive/restore buttons. `/edit ID FIELD VALUE` edits `title`,
`description`, `category_id`, `session_id`, or `course_id`. Moving a resource
requires permissions in both source and destination scopes. `/archive ID` and
`/restore ID` retain all original files and metadata.

Categories include educational videos and course advice. Send MP4 videos as
Telegram **files/documents**, not compressed video messages; delivery uses the
same document file type. The same 20 MB limit applies. There is no video-link
publishing workflow, external object storage, or AI dependency.

## Feedback administration and analytics

`/feedbackqueue` shows scoped totals, unresolved volume, status and issue counts,
department breakdown, recent resolutions, and paginated submissions.
`/submission REFERENCE` opens details. Update or assign a submission with:

```text
/status REFERENCE|Under Review|ADMIN_TELEGRAM_ID
/status REFERENCE|Resolved
```

Statuses are New, Under Review, Resolved, and Declined. Assignees must have feedback
permission for the submission's department and level. Status/assignment changes
are audited. Student requests appear as Missing resource feedback.

`/analytics` reports registered students by department/level, published resources
by department/category, recent uploads, feedback status totals, and most delivered
resources. Access events are recorded **only after Telegram confirms a successful
send**, once per update ID. They measure confirmed delivery requests, not reading
or comprehension. `/audit` shows recent administrative actions.

## Original-file and database backups

Telegram `file_id` is for this bot's delivery; `file_unique_id` identifies duplicate
files. Neither is a permanent backup. Originals are downloaded to
`BACKUP_DIRECTORY` before metadata publication. PDF/DOCX/MP4 files receive random
filenames and checksums; partially downloaded files are cleaned up. Completed
originals are deliberately retained if a workflow is cancelled or publication
fails, so reconcile unused files manually rather than deleting them automatically.

Copy originals to a separate drive using:

```powershell
python scripts/backup_originals.py --destination E:\AEIES-Backups
```

Each run creates a new directory with checksum-verified originals and a manifest;
it never overwrites or deletes originals. Protect backups with disk encryption
and access controls. Do not expose them in a public folder or commit them to Git.
Also take separate PostgreSQL logical backups with a compatible `pg_dump` using
secure libpq configuration (such as a protected password file), and periodically
test restoration into a separate disposable database. The file-copy script does
not export the database. Database restore automation is not implemented.

If a Telegram file ID fails, retain the original and report the resource. Automatic
reupload from local backup is not yet implemented. Moving between laptops requires
copying the originals along with secure configuration; filesystem paths must be
reconciled before resuming a pending upload on a different machine.

## Tests

```powershell
python -m pytest -q
```

Without `TEST_DATABASE_URL`, database-backed tests are explicitly skipped, and
that run does not establish full readiness. For the full suite, start an isolated
local PostgreSQL database named **aeies_test**, accessible only on loopback. Set
`TEST_DATABASE_URL` securely and rerun the command. The integration fixture refuses
other database names and non-loopback hosts; it truncates the dedicated test data.
**Never point it at Supabase or any database containing real data.**

Tests exercise registration, selections, updates, EEE/ICE browsing, searches,
bookmarks, feedback, requests, scoped roles, duplicate detection, audit logs,
atomic rollback, file validation/backups, error handling, concurrent students,
persisted conversation recovery, and actual PTB polling lifecycle calls against
a mocked Telegram API. They also apply migrations and verify PostgreSQL protections.

Before a live handover, verify the new Supabase project's account, free plan,
region, health, schema, and dedicated runtime login. Then use a dedicated real bot
to register, upload a sample PDF, receive it from a second student account,
bookmark it, report it, resolve the report, and restart polling. Those live checks
remain outstanding and must not be inferred from mocked tests.

## Reliability, security, and troubleshooting

- Database writes use transactions. Per-user advisory locks serialize concurrent
  transitions; processed update IDs prevent duplicate database effects. Persisted
  state isolates users and survives process restarts. Expired inline selections
  are rejected; `/resume` refreshes the current selection.
- Telegram and PostgreSQL cannot share an atomic transaction. A crash or network
  timeout around a Telegram send can produce a missing or repeated response.
  Exactly-once delivery is not promised; `/open` safely retries access, and no
  access metric is recorded for a known failed send.
- Telegram RetryAfter responses use bounded retry attempts with the server's
  delay. Transient database failures return a safe message without connection
  strings or private exception details. Logs contain event names/error classes,
  not student text, document URLs, database URLs, or token values.
- `Conflict` on polling usually means another bot process uses the same token.
  Stop the other process; do not discard pending updates as a workaround.
- Database startup failures: verify migrations, credentials, pooler role syntax,
  connectivity, and TLS trust. Never paste the URL into issue reports.
- Empty results: add real courses, an academic session, and confirmed resources;
  use `/request` for unavailable content. No sample university files are shipped.
- Backup failures: check writable storage, capacity, file type, and upload size.
  Failed backup means no resource is published.
- Permissions denied: check `/roles`, academic scope, and assigned permission.
  Hiding a button never substitutes for backend authorization.
- Do not add `aeies` to Supabase's exposed API schemas or grant students the
  backend database login. Keep privileged migration credentials off the normal
  running process once configuration is complete.

## Limitations and future deployment

Current external blockers are connected Supabase project access and live bot
credentials. Linux/local PostgreSQL/mocked Telegram coverage does not certify
Windows or Supabase-specific provisioning. Application state and processed-update
history currently have no automated retention policy; plan one before large-scale
use. Advanced audit/analytics views return bounded recent details rather than an
export dashboard. External video-link publishing, database restore automation, automatic
file-ID repair, and antivirus scanning are not implemented.

The same polling process can later move to an always-on machine with durable
original storage; decide hosting and cost separately. Webhooks are not required.
Semantic search, AI summaries, recommendations, ZIP downloads, question generation,
and grounded AI answers are future versions and are not implemented or funded.
