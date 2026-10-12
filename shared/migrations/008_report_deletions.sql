-- Explicit terminal-report deletion keeps lifecycle/audit history and never deletes RCA.
CREATE TABLE IF NOT EXISTS jc_migrations(version integer PRIMARY KEY,applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS report_deletions (
 job_id uuid PRIMARY KEY REFERENCES jobs(id), deleted_at timestamptz NOT NULL,
 reason text NOT NULL, published_result_id uuid, content_hash text,
 evidence_count bigint NOT NULL CHECK(evidence_count>=0), candidate_count bigint NOT NULL CHECK(candidate_count>=0),
 artifact_cleanup_state text NOT NULL DEFAULT 'pending' CHECK(artifact_cleanup_state IN ('pending','complete','failed')),
 artifact_cleanup_at timestamptz, artifact_cleanup_error text
);
CREATE INDEX IF NOT EXISTS evidence_job ON evidence(job_id);
INSERT INTO jc_migrations(version) VALUES(4) ON CONFLICT DO NOTHING;
