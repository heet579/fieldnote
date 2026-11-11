-- Run with an administrator after `python -m warehouse init`.
-- Roles intentionally have NOLOGIN. Provision per-person LOGIN identities separately.
-- Never commit passwords to this file.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE ROLE monitoring_reader NOLOGIN;
CREATE ROLE monitoring_loader NOLOGIN;
GRANT CONNECT ON DATABASE environment TO monitoring_reader, monitoring_loader;
GRANT USAGE ON SCHEMA public TO monitoring_reader, monitoring_loader;
GRANT SELECT ON dim_station, dim_parameter, dim_date,
    vw_monthly_monitoring, vw_pipeline_health TO monitoring_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO monitoring_loader;
GRANT INSERT, UPDATE ON etl_run, dim_date, fact_observation TO monitoring_loader;
GRANT INSERT ON stg_observation, data_quality_issue TO monitoring_loader;
-- LOCK TABLE ... IN SHARE ROW EXCLUSIVE MODE requires UPDATE privilege (granted above).
-- The loader cannot create schema objects, delete data, or change station/parameter metadata.
-- Use the owner identity for init/migrations; use a loader member for `load`.
-- The offline report export currently needs raw fact and issue access: run with owner
-- or a separately reviewed exporter identity. monitoring_reader is for reporting views.
