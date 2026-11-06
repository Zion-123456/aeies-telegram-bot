# Reconcile integration-applied 001/002 before continuing

Do not run 001 or 002 again. Do not simply insert their names into the repository
journal. Supabase integration history and `public.aeies_migrations` are independent.
No live reconciliation has been executed by this session.

1. Stop the bot and other schema writers. Inspect the approved target
   `vvfoofamchxatwyttypp`, its owners, extensions, event triggers and migration
   history through the connected integration. Verify that only 001/002 are applied.
   Preserve the already-corrected function ACL and its event trigger.
2. Prepare an **empty local disposable PostgreSQL database** named
   `aeies_reference`, preferably the same major version as the target. Configure
   `ADOPTION_REFERENCE_DATABASE_URL` securely to that local database. The tool
   rejects other reference names and non-loopback reference hosts.
3. Securely configure the target's privileged `MIGRATION_DATABASE_URL`, with
   verified TLS. Do not use the bot's runtime login. Run from the checkout:

   ```powershell
   python scripts/adopt_migrations.py
   ```

The tool constructs the reference from the exact committed 001/002 SQL inside a
transaction that always rolls back. It locks target application tables, checks
Supabase history names, compares catalog definitions, and only then records the
two SHA-256 checksums in the repository journal in a single target transaction.
It never executes 001/002 application DDL in the target or rewrites Supabase history.
Repeated adoption is safe when both schema and journal still match.

Compared evidence includes relations, columns/defaults/identity, sequence
definitions, constraints, indexes, RLS flags and policy expressions, custom
triggers, routines, schema/table/sequence/column grants, schema default grants,
backend role flags/inheritance, and exact reference seed rows. Database OIDs,
object owner identities, current sequence positions and application rows are
intentionally not compared across clusters. The target schema and all its
relations must be owned by the connected migration identity; a different owner
causes refusal and requires separate inspection, never an automatic ownership
change. This is
catalog equivalence, not proof that the integration executed identical SQL bytes.

The tool requires exactly one history row named `001_initial` and
`002_backend_role`. If the integration stored different names, do not rename its
history or loosen the check blindly: inspect the actual version/name/statements
and add a reviewed explicit mapping with tests. Missing history, added objects,
changed grants, altered definitions or seeds, later migrations already applied,
or conflicting checksums cause refusal. Cross-version catalog rendering can also
cause refusal; investigate rather than adopting a guessed checksum.

After successful adoption:

```powershell
python scripts/migrate.py
python scripts/verify_database.py
```

The runner skips adopted 001/002 and applies 003, 004 and 005. Verify
`audit_logs.details`, PDF/DOCX/MP4 MIME checks, all 16 tables and their policies,
API-role exclusion, and audit immutability. Inspect live advisors afterwards.
Never run integration test fixtures against this target.

## Index rationale

Local baseline inspection found 20 foreign keys without a **full, valid** prefix
index. Three already had a useful partial index (active roles, non-archived courses,
published resources), which an advisor may count as indexed. This explains the
distinction from the user-reported 17 notices; the live list is still uninspected.

Migration 005 adds 17 indexes and expands those three existing partial indexes
to full indexes with the same names/keys, avoiding duplicate prefix indexes. Full
coverage also supports integrity checks for archived/inactive rows. SQL comments
document each query pattern: student department/level analytics, scoped role and
course lookup, category/session/uploader resource queries, reverse bookmark and
report lookup, student/assignee feedback queues, actor audit and student deliveries.
Primary-key prefixes, feedback's department-leading queue and existing resource
access index are reused. No unused-index notice alone causes an index to be dropped.

Index creation runs transactionally on this early-stage database. It acquires
locks; schedule a maintenance window and assess row counts first. For a populated
production database, plan a separately reviewed concurrent-index rollout rather
than editing the applied migration. No live advisor improvement is claimed.
