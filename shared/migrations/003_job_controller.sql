-- JC owns all queue state. Additive and safe for existing v1.3 Backend records.
CREATE TABLE IF NOT EXISTS jc_migrations(version integer PRIMARY KEY,applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS incident_evidence_versions(incident_id uuid REFERENCES incidents(id),revision integer NOT NULL,snapshot jsonb NOT NULL,content_hash text NOT NULL,PRIMARY KEY(incident_id,revision));
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS evidence_version integer;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS retryable boolean NOT NULL DEFAULT false;
ALTER TABLE job_attempts ADD COLUMN IF NOT EXISTS budget_reserved bigint NOT NULL DEFAULT 0;
ALTER TABLE job_attempts ADD COLUMN IF NOT EXISTS completion_response jsonb;
CREATE UNIQUE INDEX IF NOT EXISTS attempt_claim_token ON job_attempts(claim_token) WHERE claim_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS queue_fifo ON jobs(kind,status,eligible_at,created_at,id);
CREATE INDEX IF NOT EXISTS attempt_lease ON job_attempts(lease_expires_at) WHERE ended_at IS NULL;
CREATE TABLE IF NOT EXISTS command_receipts(job_id uuid REFERENCES jobs(id),operation text NOT NULL,key text NOT NULL,request_hash text NOT NULL,response jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(job_id,operation,key));
CREATE TABLE IF NOT EXISTS workers(worker_id text NOT NULL,boot_id uuid NOT NULL,kind text NOT NULL CHECK(kind IN ('rca','report')),profile_id text NOT NULL,last_seen_at timestamptz NOT NULL,draining boolean NOT NULL DEFAULT false,retired boolean NOT NULL DEFAULT false,PRIMARY KEY(worker_id,boot_id));
CREATE UNIQUE INDEX IF NOT EXISTS worker_current_boot ON workers(worker_id) WHERE NOT retired;
CREATE TABLE IF NOT EXISTS capacity_state(pool_id text PRIMARY KEY,config_revision text NOT NULL,kind_limits jsonb NOT NULL,shared_limit integer NOT NULL CHECK(shared_limit>0),last_granted_kind text,config_snapshot jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS slot_reservations(id uuid PRIMARY KEY,job_id uuid REFERENCES jobs(id),attempt_no integer NOT NULL,worker_id text NOT NULL,boot_id uuid NOT NULL,kind text NOT NULL,state text NOT NULL CHECK(state IN ('active','quarantined','released')),reserved_at timestamptz NOT NULL,released_at timestamptz,remote_deadline timestamptz,release_evidence text,UNIQUE(job_id,attempt_no));
CREATE INDEX IF NOT EXISTS reservations_live ON slot_reservations(kind,worker_id) WHERE state<>'released';
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='jc_source_kind' AND conrelid='jobs'::regclass) THEN
 ALTER TABLE jobs ADD CONSTRAINT jc_source_kind CHECK(source_module IS NOT NULL AND ((kind='report' AND source_module='backend') OR (kind='rca' AND source_module='incident'))) NOT VALID;
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='jc_incident_snapshot' AND conrelid='jobs'::regclass) THEN
 ALTER TABLE jobs ADD CONSTRAINT jc_incident_snapshot FOREIGN KEY(incident_id,evidence_version) REFERENCES incident_evidence_versions(incident_id,revision) NOT VALID;
 ALTER TABLE jobs ADD CONSTRAINT jc_rca_snapshot_required CHECK(kind<>'rca' OR (incident_id IS NOT NULL AND evidence_version IS NOT NULL)) NOT VALID;
 END IF;
END $$;
CREATE OR REPLACE FUNCTION protect_published_candidate() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF EXISTS(SELECT 1 FROM jobs WHERE published_result_id=OLD.id) THEN RAISE EXCEPTION 'published candidate is immutable' USING ERRCODE='23514'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS published_candidate_immutable ON result_candidates;
CREATE TRIGGER published_candidate_immutable BEFORE UPDATE OR DELETE ON result_candidates FOR EACH ROW EXECUTE FUNCTION protect_published_candidate();
INSERT INTO jc_migrations(version) VALUES(1) ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION protect_incident_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 RAISE EXCEPTION 'incident evidence snapshot is immutable; append a new revision' USING ERRCODE='23514';
END $$;
DROP TRIGGER IF EXISTS incident_snapshot_immutable ON incident_evidence_versions;
CREATE TRIGGER incident_snapshot_immutable BEFORE UPDATE OR DELETE ON incident_evidence_versions FOR EACH ROW EXECUTE FUNCTION protect_incident_snapshot();
