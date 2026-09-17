-- Incident owns webhook receipts, raw alerts, incident metadata/evidence and its own outbox rows.
CREATE TABLE IF NOT EXISTS incident_migrations(version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS incident_sources(source text PRIMARY KEY,config_revision text NOT NULL,snapshot jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS incident_analysis_profiles(revision text PRIMARY KEY, content_hash text NOT NULL, snapshot jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS incident_webhook_receipts(id uuid PRIMARY KEY, source text NOT NULL, body_hash text NOT NULL, raw_payload jsonb NOT NULL, received_at timestamptz NOT NULL, response jsonb NOT NULL, http_status integer NOT NULL, UNIQUE(source,body_hash));
ALTER TABLE incident_webhook_receipts ADD COLUMN IF NOT EXISTS raw_body bytea;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS memo text NOT NULL DEFAULT '';
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS review_status text NOT NULL DEFAULT 'unreviewed';
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS alarm_status text;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS alarm_resolved_at timestamptz;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS last_evidence_hash text;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS rca_eligibility_reason text;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
CREATE UNIQUE INDEX IF NOT EXISTS incident_event_key ON incidents(event_key) WHERE event_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS incidents_occurred ON incidents(cluster_id,occurred_at DESC,id DESC);
CREATE TABLE IF NOT EXISTS alert_events(id uuid PRIMARY KEY, source text NOT NULL, cluster_id text, fingerprint text, starts_at timestamptz, status text, payload_hash text NOT NULL, raw_payload jsonb NOT NULL, observed_at timestamptz NOT NULL, receipt_id uuid NOT NULL REFERENCES incident_webhook_receipts(id), alert_index integer NOT NULL, incident_id uuid REFERENCES incidents(id), disposition text NOT NULL, reason text, UNIQUE(source,cluster_id,fingerprint,starts_at,payload_hash));
CREATE INDEX IF NOT EXISTS alerts_incident ON alert_events(incident_id,observed_at,id);
CREATE TABLE IF NOT EXISTS incident_evidence_versions(incident_id uuid REFERENCES incidents(id),revision integer NOT NULL,snapshot jsonb NOT NULL,content_hash text NOT NULL,PRIMARY KEY(incident_id,revision));
CREATE OR REPLACE FUNCTION protect_incident_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 RAISE EXCEPTION 'incident evidence snapshot is immutable; append a new revision' USING ERRCODE='23514';
END $$;
DROP TRIGGER IF EXISTS incident_snapshot_immutable ON incident_evidence_versions;
CREATE TRIGGER incident_snapshot_immutable BEFORE UPDATE OR DELETE ON incident_evidence_versions FOR EACH ROW EXECUTE FUNCTION protect_incident_snapshot();
CREATE TABLE IF NOT EXISTS incident_command_receipts(incident_id uuid REFERENCES incidents(id),key text NOT NULL,request_hash text NOT NULL,response jsonb NOT NULL,PRIMARY KEY(incident_id,key));
INSERT INTO incident_migrations(version) VALUES(1) ON CONFLICT DO NOTHING;
