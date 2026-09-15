-- Run after Airflow has migrated its metadata DB. Never grant raw metadata access.
BEGIN;
SELECT format('CREATE ROLE airflow_monitor LOGIN PASSWORD %L', :'monitor_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='airflow_monitor') \gexec
SELECT format('ALTER ROLE airflow_monitor PASSWORD %L', :'monitor_password') \gexec
ALTER ROLE airflow_monitor SET default_transaction_read_only=on;
ALTER ROLE airflow_monitor SET statement_timeout='5s';
CREATE SCHEMA IF NOT EXISTS monitoring;
REVOKE ALL ON SCHEMA monitoring FROM PUBLIC;
CREATE OR REPLACE VIEW monitoring.dag_latest AS
SELECT d.dag_id, d.is_paused, r.run_id, r.state::text AS state,
       r.start_date, r.end_date,
       extract(epoch FROM (coalesce(r.end_date,now())-r.start_date)) AS duration_seconds
FROM public.dag d LEFT JOIN LATERAL (
    SELECT run_id,state,start_date,end_date FROM public.dag_run
    WHERE dag_id=d.dag_id ORDER BY id DESC LIMIT 1
) r ON true;
CREATE OR REPLACE VIEW monitoring.task_states AS
SELECT t.dag_id,coalesce(t.state::text,'none') AS state,count(*) AS tasks
FROM public.task_instance t JOIN monitoring.dag_latest d ON d.dag_id=t.dag_id AND d.run_id=t.run_id
GROUP BY t.dag_id,t.state;
CREATE OR REPLACE VIEW monitoring.recent_runs AS
SELECT dag_id,run_id,state::text AS state,start_date,end_date,
       extract(epoch FROM (coalesce(end_date,now())-start_date)) AS duration_seconds
FROM public.dag_run WHERE coalesce(start_date,queued_at)>=now()-interval '7 days';
CREATE OR REPLACE VIEW monitoring.job_heartbeats AS
SELECT DISTINCT ON(job_type) job_type,hostname,state::text AS state,
       latest_heartbeat,extract(epoch FROM now()-latest_heartbeat) AS heartbeat_age_seconds
FROM public.job ORDER BY job_type,id DESC;
CREATE OR REPLACE VIEW monitoring.import_errors AS
SELECT filename,timestamp FROM public.import_error;
GRANT CONNECT ON DATABASE airflow TO airflow_monitor;
GRANT USAGE ON SCHEMA monitoring TO airflow_monitor;
GRANT SELECT ON ALL TABLES IN SCHEMA monitoring TO airflow_monitor;
COMMIT;
