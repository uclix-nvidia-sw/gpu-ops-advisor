-- Additive migration: legacy records/tables remain intact; unpublished legacy results stay private.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source_module text;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source_key text;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS input_snapshot jsonb;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS eligible_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS budget_used bigint NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS queue_reason text;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS published_result_id uuid;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='jobs' AND column_name='request') THEN
  EXECUTE 'UPDATE jobs SET input_snapshot=request WHERE input_snapshot IS NULL';
  EXECUTE 'ALTER TABLE jobs ALTER COLUMN principal DROP NOT NULL, ALTER COLUMN request DROP NOT NULL, ALTER COLUMN request_operation DROP NOT NULL, ALTER COLUMN idempotency_key DROP NOT NULL';
 END IF;
 IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='schedules' AND column_name='owner') THEN
  ALTER TABLE schedules RENAME TO legacy_schedules_v12;
 END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS jobs_source_key ON jobs(source_module,source_key);
ALTER TABLE job_attempts ADD COLUMN IF NOT EXISTS stage text;
ALTER TABLE job_attempts ADD COLUMN IF NOT EXISTS boot_id text;
ALTER TABLE job_attempts ADD COLUMN IF NOT EXISTS claim_token text;
ALTER TABLE job_attempts ADD COLUMN IF NOT EXISTS remote_call_state text;
CREATE TABLE IF NOT EXISTS result_candidates (
 id uuid PRIMARY KEY, job_id uuid NOT NULL REFERENCES jobs(id), attempt_no integer NOT NULL, kind text NOT NULL,
 schema_version text NOT NULL, body jsonb NOT NULL, content_hash text NOT NULL, validation_status text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(job_id,attempt_no));
CREATE TABLE IF NOT EXISTS cluster_registry (id text PRIMARY KEY, enabled boolean NOT NULL DEFAULT true);
CREATE TABLE IF NOT EXISTS procedures (id uuid PRIMARY KEY, code text UNIQUE NOT NULL, metadata jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
ALTER TABLE knowledge_revisions ADD COLUMN IF NOT EXISTS reviewed_content_hash text;
ALTER TABLE identity_history ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE incidents ALTER COLUMN symptom DROP NOT NULL, ALTER COLUMN status DROP NOT NULL, ALTER COLUMN first_seen DROP NOT NULL, ALTER COLUMN last_seen DROP NOT NULL;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS event_key text;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS occurred_at timestamptz;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS target jsonb;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS state text;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS analysis_profile_revision text;
CREATE TABLE IF NOT EXISTS backend_receipts (operation text NOT NULL, key text NOT NULL, request_hash text NOT NULL,
 status integer NOT NULL, response jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(operation,key));
CREATE TABLE IF NOT EXISTS manual_report_intents (source_key text PRIMARY KEY, request_hash text NOT NULL, envelope jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS schedules (id uuid PRIMARY KEY, enabled boolean NOT NULL, current_revision integer NOT NULL,
 effective_at timestamptz NOT NULL, next_run_at timestamptz NOT NULL, version integer NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS schedule_revisions (schedule_id uuid REFERENCES schedules(id), revision integer NOT NULL,
 frequency text NOT NULL, local_time text NOT NULL, timezone text NOT NULL, weekday integer, day integer, period text NOT NULL,
 report_spec jsonb NOT NULL, enabled boolean NOT NULL, effective_at timestamptz NOT NULL, PRIMARY KEY(schedule_id,revision));
CREATE TABLE IF NOT EXISTS enqueue_outbox (id uuid PRIMARY KEY, source_module text NOT NULL, source_key text NOT NULL, kind text NOT NULL,
 input_snapshot jsonb NOT NULL, request_hash text NOT NULL, status text NOT NULL, dispatch_deadline timestamptz NOT NULL,
 job_id uuid, attempts integer NOT NULL DEFAULT 0, next_retry_at timestamptz NOT NULL DEFAULT now(), last_error text,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(source_module,source_key));
CREATE TABLE IF NOT EXISTS schedule_occurrences (id uuid PRIMARY KEY, schedule_id uuid REFERENCES schedules(id), revision integer NOT NULL,
 scheduled_for timestamptz NOT NULL, period_start timestamptz NOT NULL, period_end timestamptz NOT NULL,
 canonical boolean NOT NULL, status text NOT NULL CHECK(status IN ('pending','accepted','missed','failed')), reason text,
 outbox_id uuid REFERENCES enqueue_outbox(id), job_id uuid, canonical_occurrence_id uuid REFERENCES schedule_occurrences(id),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(schedule_id,scheduled_for));
CREATE UNIQUE INDEX IF NOT EXISTS schedule_canonical_period ON schedule_occurrences(schedule_id,period_start,period_end) WHERE canonical;
CREATE TABLE IF NOT EXISTS profile_revisions (profile_id uuid REFERENCES service_profiles(id), revision integer NOT NULL, snapshot jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(profile_id,revision));
INSERT INTO profile_revisions SELECT id,version,to_jsonb(p),now() FROM service_profiles p ON CONFLICT DO NOTHING;
UPDATE service_profiles SET config=jsonb_build_object('rca',COALESCE(config->'rca',config->'default'),'report',COALESCE(config->'report',config->'default')),version=version+1
 WHERE kind='routing' AND (config ? 'default' OR config ? 'assistant');
INSERT INTO schema_migrations(version) VALUES(2) ON CONFLICT DO NOTHING;
