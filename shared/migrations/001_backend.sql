-- Shared storage baseline. Queue tables are written only by Job Controller.
CREATE TABLE IF NOT EXISTS schema_migrations(version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS service_profiles (
 id uuid PRIMARY KEY, kind text NOT NULL, name text NOT NULL, config jsonb NOT NULL DEFAULT '{}', secret_ref text,
 version integer NOT NULL DEFAULT 1 CHECK(version>0), enabled boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(kind,name));
CREATE TABLE IF NOT EXISTS knowledge_revisions (
 id uuid PRIMARY KEY, knowledge_id uuid NOT NULL, knowledge_key text NOT NULL, revision integer NOT NULL CHECK(revision>0), kind text NOT NULL CHECK(kind IN ('runbook','policy','data_dictionary','reference','case')),
 state text NOT NULL CHECK(state IN ('draft','in_review','reviewed','published','retired')), visibility text NOT NULL CHECK(visibility IN ('common','scoped')),
 scope jsonb, content jsonb NOT NULL, content_hash text NOT NULL, compatibility jsonb NOT NULL DEFAULT '{}', source_refs jsonb NOT NULL DEFAULT '[]',
 reviewer text, reviewed_at timestamptz, published_at timestamptz, retired_at timestamptz, version integer NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(knowledge_id,revision), UNIQUE(knowledge_key,revision), CHECK(visibility<>'scoped' OR scope IS NOT NULL));
CREATE TABLE IF NOT EXISTS review_records (
 id uuid PRIMARY KEY, subject_type text NOT NULL CHECK(subject_type IN ('incident','job','knowledge')), subject_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind IN ('comment','review','action')), author text NOT NULL, occurred_at timestamptz, body jsonb NOT NULL, scope jsonb NOT NULL,
 supersedes_id uuid REFERENCES review_records(id), created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS audit_events (
 id uuid PRIMARY KEY, actor text NOT NULL, action text NOT NULL, resource_type text NOT NULL, resource_id uuid, resource_revision integer,
 occurred_at timestamptz NOT NULL DEFAULT now(), effective_at timestamptz NOT NULL DEFAULT now(), request_id text NOT NULL,
 scope jsonb, before_ref jsonb, after_ref jsonb, outcome text NOT NULL DEFAULT 'success');
CREATE TABLE IF NOT EXISTS jobs (
 id uuid PRIMARY KEY, kind text NOT NULL CHECK(kind IN ('rca','report')), source_module text NOT NULL, source_key text NOT NULL,
 scope jsonb NOT NULL, input_snapshot jsonb NOT NULL, request_hash text NOT NULL, versions jsonb NOT NULL DEFAULT '{}',
 incident_id uuid, parent_job_id uuid REFERENCES jobs(id), status text NOT NULL, stage text NOT NULL DEFAULT 'queued',
 eligible_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz,
 deadline_at timestamptz NOT NULL, attempt_no integer NOT NULL DEFAULT 0, max_attempts integer NOT NULL DEFAULT 3,
 budget_used bigint NOT NULL DEFAULT 0, token_budget bigint NOT NULL DEFAULT 1, cancel_requested_at timestamptz,
 termination_reason text, queue_reason text, published_result_id uuid, version integer NOT NULL DEFAULT 1,
 UNIQUE(source_module,source_key));
CREATE INDEX IF NOT EXISTS jobs_order ON jobs(created_at DESC,id DESC);
CREATE TABLE IF NOT EXISTS job_attempts (
 job_id uuid REFERENCES jobs(id), attempt_no integer NOT NULL, worker_id text, boot_id text, claim_token text, lease_expires_at timestamptz,
 started_at timestamptz NOT NULL, ended_at timestamptz, stage text, termination_reason text, remote_call_state text, PRIMARY KEY(job_id,attempt_no));
CREATE TABLE IF NOT EXISTS evidence (
 id uuid PRIMARY KEY, job_id uuid REFERENCES jobs(id), attempt_no integer, cluster_id text, scope jsonb NOT NULL, query_id text, query_version text, source_version text,
 input jsonb, tool_status text NOT NULL, time_start timestamptz, time_end timestamptz, data_cutoff_at timestamptz, quality jsonb NOT NULL DEFAULT '{}', snapshot jsonb,
 object_key text, checksum text, expires_at timestamptz, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS incidents (
 id uuid PRIMARY KEY, cluster_id text NOT NULL, scope jsonb NOT NULL, asset_key text, raw_asset jsonb, symptom text NOT NULL, status text NOT NULL,
 first_seen timestamptz NOT NULL, last_seen timestamptz NOT NULL, correlation_key text, episode_key text, correlation_status text, evidence_version integer NOT NULL DEFAULT 1,
 version integer NOT NULL DEFAULT 1, recurrence_of uuid REFERENCES incidents(id), last_verified_at timestamptz, verification_status text, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS identity_history (id uuid PRIMARY KEY, cluster_id text NOT NULL, relation_kind text NOT NULL, subject_key text NOT NULL, object_key text, subject_kind text NOT NULL, object_kind text,
 valid_from timestamptz NOT NULL, valid_to timestamptz, observed_at timestamptz, identity_status text NOT NULL, attributes jsonb NOT NULL DEFAULT '{}', evidence_id uuid REFERENCES evidence(id), CHECK(valid_to IS NULL OR valid_to>valid_from));
CREATE TABLE IF NOT EXISTS collection_observations (id uuid PRIMARY KEY, cluster_id text NOT NULL, source text NOT NULL, observed_at timestamptz, ingested_at timestamptz, evaluated_at timestamptz NOT NULL,
 scope jsonb NOT NULL, success boolean NOT NULL, completeness text NOT NULL, expected_count bigint, observed_count bigint, source_revision text, query_revision text, dedup_key text NOT NULL,
 quality jsonb NOT NULL DEFAULT '{}', evidence_refs jsonb NOT NULL DEFAULT '[]', UNIQUE(source,cluster_id,dedup_key));
CREATE TABLE IF NOT EXISTS allocation_observations (id uuid PRIMARY KEY, collection_id uuid REFERENCES collection_observations(id), cluster_id text NOT NULL, node text, node_uid text, gpu_uuid text,
 parent_gpu_uuid text, device_id text, mig_config_id text, namespace text, pod_name text, pod_uid text, container text, container_run_id text,
 allocation_mode text NOT NULL, relation_status text NOT NULL, identity_status text NOT NULL, time_basis text NOT NULL, observed_at timestamptz, ingested_at timestamptz,
 evaluated_at timestamptz NOT NULL, original_gpu_sample_at timestamptz, original_pod_sample_at timestamptz, valid_from timestamptz, valid_to timestamptz, boundary_uncertainty jsonb, raw_labels jsonb,
 evidence_refs jsonb NOT NULL DEFAULT '[]', relation_key text NOT NULL, allocation_episode_key text, identity_revision text, UNIQUE(collection_id,relation_key));
INSERT INTO schema_migrations(version) VALUES(1) ON CONFLICT DO NOTHING;
CREATE OR REPLACE FUNCTION dsx_scope_contains(allowed jsonb, requested jsonb) RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
 SELECT jsonb_array_length(COALESCE(requested->'clusters','[]'))>0 AND NOT EXISTS (
 SELECT 1 FROM jsonb_array_elements(requested->'clusters') r WHERE NOT EXISTS (
 SELECT 1 FROM jsonb_array_elements(allowed->'clusters') a WHERE (a->>'cluster_id')=(r->>'cluster_id')
 AND ((a->'namespaces')='null'::jsonb OR ((r->'namespaces')<>'null'::jsonb AND (a->'namespaces') @> (r->'namespaces')))));
$$;
