CREATE TABLE IF NOT EXISTS etl_run (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed')),
    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    received INTEGER NOT NULL DEFAULT 0,
    accepted INTEGER NOT NULL DEFAULT 0,
    rejected INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    unchanged INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
CREATE TABLE IF NOT EXISTS dim_station (
    station_id TEXT PRIMARY KEY,
    station_name TEXT NOT NULL,
    region TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dim_parameter (
    parameter_code TEXT PRIMARY KEY,
    parameter_name TEXT NOT NULL,
    canonical_unit TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dim_date (
    date_key TEXT PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    season TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stg_observation (
    run_id TEXT NOT NULL REFERENCES etl_run(run_id),
    row_number INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    PRIMARY KEY(run_id, row_number)
);
CREATE TABLE IF NOT EXISTS data_quality_issue (
    run_id TEXT NOT NULL REFERENCES etl_run(run_id),
    row_number INTEGER NOT NULL,
    reason TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    PRIMARY KEY(run_id, row_number)
);
CREATE TABLE IF NOT EXISTS fact_observation (
    station_id TEXT NOT NULL REFERENCES dim_station(station_id),
    parameter_code TEXT NOT NULL REFERENCES dim_parameter(parameter_code),
    observed_at TEXT NOT NULL,
    date_key TEXT NOT NULL REFERENCES dim_date(date_key),
    value DOUBLE PRECISION NOT NULL,
    last_run_id TEXT NOT NULL REFERENCES etl_run(run_id),
    PRIMARY KEY(station_id, parameter_code, observed_at)
);
CREATE INDEX IF NOT EXISTS ix_observation_date ON fact_observation(date_key);
CREATE INDEX IF NOT EXISTS ix_issue_run ON data_quality_issue(run_id);
CREATE VIEW IF NOT EXISTS vw_monthly_monitoring AS
SELECT s.region, s.station_id, s.station_name, p.parameter_code,
       p.parameter_name, p.canonical_unit, d.year, d.month,
       COUNT(*) AS observation_count, AVG(f.value) AS mean_value,
       MIN(f.value) AS min_value, MAX(f.value) AS max_value
FROM fact_observation f
JOIN dim_station s ON s.station_id=f.station_id
JOIN dim_parameter p ON p.parameter_code=f.parameter_code
JOIN dim_date d ON d.date_key=f.date_key
GROUP BY s.region,s.station_id,s.station_name,p.parameter_code,
         p.parameter_name,p.canonical_unit,d.year,d.month;
CREATE VIEW IF NOT EXISTS vw_pipeline_health AS
SELECT run_id,started_at,finished_at,status,source_file,received,accepted,
       rejected,inserted,updated,unchanged,error FROM etl_run;
