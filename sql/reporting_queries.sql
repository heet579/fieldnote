-- Monthly observation-weighted summaries, separated by parameter and unit.
SELECT * FROM vw_monthly_monitoring ORDER BY year,month,station_id,parameter_code;

-- Successful-load reconciliation: both differences must equal zero.
SELECT run_id, received-accepted-rejected AS intake_difference,
       accepted-inserted-updated-unchanged AS outcome_difference
FROM etl_run WHERE status='succeeded';

-- Latest successfully loaded observations (not a real-time freshness guarantee).
SELECT station_id, parameter_code, MAX(observed_at) AS latest_observed_at,
       COUNT(*) AS observations
FROM fact_observation GROUP BY station_id,parameter_code;

-- Rejection events, including events repeated on file reruns.
SELECT reason, COUNT(*) AS rejection_events
FROM data_quality_issue GROUP BY reason ORDER BY rejection_events DESC;

-- Failures requiring review. Injected demo failures are intentional.
SELECT started_at,source_file,error FROM etl_run WHERE status='failed' ORDER BY started_at DESC;
