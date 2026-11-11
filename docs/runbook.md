# ETL and database operations runbook

## Real-data workflow

The public report uses `runtime/real-v2/warehouse.sqlite`. Reproduce from a fresh copy with `python -m scripts.fetch_torrens`, `python -m scripts.real_demo`, `python -m scripts.verify_real`, then `node scripts/check_report.cjs`. To preserve previous evidence, a repeat full real demo requires a new `--run-dir`. Update the verifier and refresh-script target when using another DB.

Real-input loads require `--timestamp-basis source_unspecified`: do not mix these clocks with UTC-normalised fixtures. Normalisation verifies units, records member hashes and selects the 120 monthly files for 2015–2018 under `torrens/` only. Do not blindly ingest overlapping root-level copies.

Refresh with `python -m scripts.refresh_report`, verify, package using `python -m scripts.package`, then run `python -m scripts.build_site`. Vercel hosts static output; local Python performs loads and recovery. The real-data failed run is an intentional exercise using an unchanged original reading.

Use `--db runtime/real-v2/warehouse.sqlite` explicitly for backup/fingerprint commands below. The synthetic commands below separately exercise changed values and schema drift. See README for production publishing and docs/deployment.md for the returned deployment URL.

Run commands from the repository root. Replace example filenames with new, unused paths. Never restore over the active database. Default CLI target: `WAREHOUSE_DSN`, otherwise `runtime/warehouse.sqlite`; the supplied full demo instead uses `runtime/demo/warehouse.sqlite` explicitly.

## Normal operation

```powershell
python -m warehouse --db runtime/warehouse.sqlite init
python -m warehouse generate
python -m warehouse --db runtime/warehouse.sqlite load data/synthetic/observations.csv
python -m warehouse --db runtime/warehouse.sqlite report
```

Check command exit code (`$LASTEXITCODE` in PowerShell): zero means success, one means error. Review `etl_run` or the operations section in a freshly exported report. For a successful load, reconcile both count identities in `sql/reporting_queries.sql` and check that new rejection reasons are expected.

Do not use the owner identity for routine PostgreSQL loads after provisioning a loader identity. SQLite access is controlled by filesystem permissions, not SQL login roles.

## Failed load

1. Stop dependent publication until the incident is understood. Existing committed facts are retained.
2. Find the failed run by UTC start time/source basename. Inspect status/error and locate the archived CSV using its SHA-256 hash. No credentials are intentionally logged.
3. Investigate the source contract or reference data. Do not silently rename an unexpected column or discard an unknown station.
4. Correct the approved input/mapping and use a new source file. Run `load` again; every retry receives a new audit identity.
5. Check counts, changed values and rejection reasons. Export a new report.
6. Record cause, recovery action and evidence. `docs/incident-example.md` supplies a completed synthetic example.

If the process was terminated and status remains `running`, confirm no process/session is still active, inspect facts and the database transaction outcome, then record an explicitly reviewed incident status update. An automatic timeout is not proof of a failed or successful load.

## Exercise rollback

Use a disposable database loaded with the initial fixture:

```powershell
python -m warehouse --db runtime/warehouse.sqlite load data/synthetic/failure_fixture.csv --fail-after 1
# Expected: nonzero exit; failed audit; zero committed changes from this run.
python -m warehouse --db runtime/warehouse.sqlite load data/synthetic/failure_fixture.csv
# Expected: succeeds and applies the two fixture corrections.
```

The test suite compares all facts before and after failure, checks staging rollback, then exercises recovery. This proves the fixture scenario, not protection against every possible failure.

## SQLite backup and isolated restore

```powershell
python -m warehouse --db runtime/warehouse.sqlite backup runtime/backups/warehouse-001.sqlite
python -m warehouse restore runtime/backups/warehouse-001.sqlite runtime/restore-check-001.sqlite
```

Backup uses SQLite's online backup API and verifies database integrity. It produces a sidecar JSON manifest with a binary file SHA-256 and per-table logical hashes computed from the backup snapshot. Restore refuses existing targets, verifies the file checksum, performs integrity/foreign-key checks and compares all seven table fingerprints with that manifest.

For a comparison with the live database, pause writers or compare against a known snapshot boundary:

```powershell
python -m warehouse --db runtime/warehouse.sqlite fingerprint
python -m warehouse --db runtime/restore-check-001.sqlite fingerprint
```

Do not expect equality if successful loads occurred after the backup. Keep the manifest and backup together. The manifest is a corruption check, not cryptographic authentication against an attacker who can modify both files. Store copies away from the working directory and test restores before relying on them. Raw CSV archives are separate: copy `runtime/raw` with the matching hashes as part of a complete recovery package.

## PostgreSQL provisioning and verification — not locally executed

1. Start the Compose service using the README steps and initialise as owner.
2. Run `sql/postgres_roles.sql` once as administrator. It creates NOLOGIN group roles; create separate LOGIN accounts using your secret-management process, then grant group membership. Avoid shared owner credentials.
3. As a reader member, confirm SELECT on `vw_monthly_monitoring` works; confirm INSERT on `fact_observation` fails. As a loader member, confirm a valid load succeeds and CREATE TABLE fails. Use a disposable database for permission tests.
4. Run initial/repeat/correction/failure/schema-drift scenarios and compare outcomes against SQLite evidence before describing PostgreSQL as tested.

Native PostgreSQL tools must be installed on the machine where these commands run. Use libpq service definitions and a protected password file rather than passwords on command lines. Example: configure `fieldnote_owner` for the source database and `fieldnote_restore` for a new, empty restore database.

```powershell
pg_dump --dbname='service=fieldnote_owner' --format=custom --file=runtime/fieldnote.dump
pg_restore --dbname='service=fieldnote_restore' --no-owner --no-privileges --exit-on-error runtime/fieldnote.dump
# Set WAREHOUSE_DSN separately to each source/restore database and run:
python -m warehouse fingerprint
```

Restore only into a separately created empty database. Pause writes for source-versus-restore fingerprint comparison, or compare with a source export from the same snapshot boundary. Logical fingerprints normalise row order, not cross-version floating-point representations. `pg_dump` does not include cluster roles or the raw CSV archive; provision roles separately. Capture actual restore evidence before making a recovery claim.

## Operational boundaries

No scheduler or notification service is installed. A future scheduler should run one loader at a time, capture exit status and notify on failed or stale loads. Prototype writer locks serialize fact updates, but larger datasets need batch operations, source version control, tuned indexes, retention policy and load testing. Schema changes require reviewed migration scripts; `init` creates missing objects, it does not migrate existing tables. No recovery time or recovery point service-level target has been measured.
