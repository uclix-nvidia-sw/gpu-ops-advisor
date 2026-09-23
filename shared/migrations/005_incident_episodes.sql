-- Additive preparation only. Legacy lifecycle attribution runs at producer cutover.
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS source text;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS fingerprint text;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS starts_at timestamptz;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS dedup_group text CHECK (octet_length(dedup_group) <= 2000);
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS episode_started_at timestamptz;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS last_observed_at timestamptz;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS observation_count bigint;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS observation_gap_seconds integer;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS ended_at timestamptz;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS ended_reason text;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS closed_at timestamptz;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS prior_incident_id uuid REFERENCES incidents(id);
CREATE UNIQUE INDEX IF NOT EXISTS incident_open_episode ON incidents(dedup_group) WHERE ended_at IS NULL AND dedup_group IS NOT NULL;
CREATE INDEX IF NOT EXISTS incident_episode_history ON incidents(dedup_group,episode_started_at DESC,id DESC);
CREATE TABLE IF NOT EXISTS incident_alert_lifecycles (
 source text NOT NULL, cluster_id text NOT NULL, fingerprint text NOT NULL, starts_at timestamptz NOT NULL,
 dedup_group text CHECK (octet_length(dedup_group) <= 2000), latest_incident_id uuid REFERENCES incidents(id),
 resolved_at timestamptz, last_received_at timestamptz NOT NULL, last_disposition text NOT NULL,
 legacy boolean NOT NULL DEFAULT false, PRIMARY KEY(source,cluster_id,fingerprint,starts_at)
);
CREATE INDEX IF NOT EXISTS incident_lifecycle_episode ON incident_alert_lifecycles(latest_incident_id);
-- Existing 1.3 evidence revisions remain valid; new episodes have one snapshot.
CREATE OR REPLACE FUNCTION check_incident_episode_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.revision <> 1 AND EXISTS(SELECT 1 FROM incidents WHERE id=NEW.incident_id AND dedup_group IS NOT NULL) THEN
  RAISE EXCEPTION 'episode evidence revision must be 1' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS incident_episode_snapshot_revision ON incident_evidence_versions;
CREATE TRIGGER incident_episode_snapshot_revision BEFORE INSERT ON incident_evidence_versions FOR EACH ROW EXECUTE FUNCTION check_incident_episode_snapshot();
INSERT INTO incident_migrations(version) VALUES(2) ON CONFLICT DO NOTHING;
