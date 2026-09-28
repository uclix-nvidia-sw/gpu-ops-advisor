-- psql -X -v ON_ERROR_STOP=1 -v incident_id=<UUID> [-v job_id=<UUID>] -f verify-flow.sql
-- Read-only diagnostics for the product PostgreSQL schema. Does not print claim tokens.
\set ON_ERROR_STOP on
\if :{?incident_id}
\else
  \echo 'Supply -v incident_id=<actual UUID>; discover it via alert_events first.'
  \quit
\endif
\if :{?job_id}
\else
  \set job_id ''
\endif
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '10s';

\echo '00 - Database context and cluster registration'
SELECT current_database(), current_schema(), now() AS inspected_at;
SELECT c.id, c.enabled FROM cluster_registry c
JOIN incidents i ON i.cluster_id=c.id WHERE i.id=:'incident_id'::uuid;

\echo '01 - Alert ledger and original webhook receipt'
SELECT a.id AS alert_event_id, a.receipt_id, a.source, a.cluster_id,
       a.fingerprint, a.starts_at, a.status, a.disposition, a.reason,
       a.observed_at, a.raw_payload, r.http_status, r.body_hash,
       r.received_at, r.response, octet_length(r.raw_body) AS raw_body_bytes
FROM alert_events a LEFT JOIN incident_webhook_receipts r ON r.id=a.receipt_id
WHERE a.incident_id=:'incident_id'::uuid ORDER BY a.observed_at DESC LIMIT 50;

\echo '02 - Incident and immutable evidence versions'
SELECT id, cluster_id, scope, target, state, alarm_status, review_status,
       evidence_version, analysis_profile_revision, rca_eligibility_reason,
       last_evidence_hash, occurred_at, last_seen, updated_at
FROM incidents WHERE id=:'incident_id'::uuid;
SELECT revision, content_hash, snapshot->'input' AS frozen_input,
       snapshot->'alert' AS original_alert, snapshot->'eligible' AS eligible,
       snapshot->>'reason' AS reason
FROM incident_evidence_versions WHERE incident_id=:'incident_id'::uuid
ORDER BY revision DESC LIMIT 50;

\echo '03 - Outbox handoff and persisted job snapshot'
SELECT o.id AS outbox_id, o.source_key, o.status AS outbox_status, o.attempts,
       o.next_retry_at, o.last_error, o.job_id, j.status AS job_status,
       j.queue_reason, o.request_hash AS outbox_hash, j.request_hash AS job_hash,
       o.request_hash=j.request_hash AS request_hash_matches,
       o.source_key=j.source_key AS source_key_matches
FROM enqueue_outbox o LEFT JOIN jobs j ON j.id=o.job_id
WHERE o.source_module='incident'
  AND o.input_snapshot->'input'->>'incident_id'=:'incident_id'
ORDER BY o.created_at DESC LIMIT 50;
SELECT j.id AS job_id, j.source_key, j.incident_id, j.evidence_version,
       j.status, j.stage, j.queue_reason, j.termination_reason, j.versions,
       j.input_snapshot,
       j.input_snapshot->'incident_snapshot'=v.snapshot AS snapshot_matches
FROM jobs j LEFT JOIN incident_evidence_versions v
  ON v.incident_id=j.incident_id AND v.revision=j.evidence_version
WHERE j.incident_id=:'incident_id'::uuid AND (:'job_id'='' OR j.id::text=:'job_id')
ORDER BY j.created_at DESC LIMIT 50;

\echo '04 - Exact Knowledge revisions pinned when JC accepted the job'
SELECT j.id AS job_id, p.ref AS pinned_reference, k.id AS revision_id,
       k.knowledge_key, k.kind, k.revision, k.state, k.compatibility,
       k.content_hash, k.reviewed_content_hash,
       k.content_hash=k.reviewed_content_hash AS reviewed_hash_matches,
       k.content_hash=p.ref->>'content_hash' AS pinned_hash_matches,
       k.content->'search'->'codes' AS codes,
       k.content->'investigation_only' AS investigation_only,
       k.content->'observation_plan' AS observation_plan
FROM jobs j
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(j.versions->'knowledge','[]')) p(ref)
LEFT JOIN knowledge_revisions k ON k.knowledge_id::text=p.ref->>'knowledge_id'
  AND k.revision=(p.ref->>'revision')::integer
WHERE j.incident_id=:'incident_id'::uuid AND (:'job_id'='' OR j.id::text=:'job_id')
ORDER BY j.created_at DESC, k.knowledge_key, k.revision;

\echo '05 - Attempts, heartbeat/lease, worker and capacity reservation'
SELECT j.id AS job_id, j.status, j.stage, j.attempt_no AS current_attempt,
       a.attempt_no, a.worker_id, a.stage AS attempt_stage, a.started_at,
       a.lease_expires_at, a.ended_at, a.remote_call_state, a.termination_reason,
       a.completion_response, w.last_seen_at, w.retired, w.draining,
       w.supported_contract_versions, s.state AS reservation_state, s.released_at
FROM jobs j LEFT JOIN job_attempts a ON a.job_id=j.id
LEFT JOIN workers w ON w.worker_id=a.worker_id AND w.boot_id::text=a.boot_id
LEFT JOIN slot_reservations s ON s.job_id=a.job_id AND s.attempt_no=a.attempt_no
WHERE j.incident_id=:'incident_id'::uuid AND (:'job_id'='' OR j.id::text=:'job_id')
ORDER BY j.created_at DESC, a.attempt_no DESC;

\echo '06 - Saved evidence; these rows appear only after Store.save'
SELECT e.id, e.job_id, e.attempt_no, e.query_id, e.query_version, e.cluster_id,
       e.time_start, e.time_end, e.tool_status, e.quality, e.input, e.checksum
FROM evidence e JOIN jobs j ON j.id=e.job_id
WHERE j.incident_id=:'incident_id'::uuid AND (:'job_id'='' OR j.id::text=:'job_id')
ORDER BY e.attempt_no, e.query_id, e.time_start, e.id LIMIT 500;
SELECT e.job_id, e.attempt_no, e.query_id, e.snapshot
FROM evidence e JOIN jobs j ON j.id=e.job_id
WHERE j.incident_id=:'incident_id'::uuid AND (:'job_id'='' OR j.id::text=:'job_id')
  AND e.query_id IN ('alert_clues','runbook_selection','observation_plan','sufficiency','rca_synthesis')
ORDER BY e.attempt_no, e.query_id, e.id LIMIT 100;

\echo '07 - Saved candidate versus actually published result'
SELECT c.id AS candidate_id, c.job_id, c.attempt_no, c.validation_status,
       c.schema_version, c.content_hash, j.published_result_id,
       c.id=j.published_result_id AS is_published,
       c.body->>'result_schema_version' AS body_schema,
       c.body->>'result_status' AS result_status,
       c.body->>'termination_reason' AS analysis_termination,
       c.body->'quality'->'analysis' AS analysis,
       c.body->'assessments' AS assessments,
       c.body->'cause_candidates' AS cause_candidates,
       c.body->'missing_inputs' AS missing_inputs,
       c.body->'runbook_revisions' AS runbook_revisions
FROM result_candidates c JOIN jobs j ON j.id=c.job_id
WHERE j.incident_id=:'incident_id'::uuid AND (:'job_id'='' OR j.id::text=:'job_id')
ORDER BY c.created_at DESC;

\echo '08 - Publication and evidence-reference integrity'
SELECT j.id AS job_id, j.status, j.published_result_id, c.content_hash,
       c.job_id=j.id AS candidate_job_matches,
       c.attempt_no=j.attempt_no AS candidate_attempt_matches,
       a.completion_response->>'content_hash'=c.content_hash AS completion_hash_matches,
       c.body->>'incident_id'=j.incident_id::text AS incident_matches,
       c.body->>'result_status' AS analysis_status
FROM jobs j LEFT JOIN result_candidates c ON c.id=j.published_result_id
LEFT JOIN job_attempts a ON a.job_id=j.id AND a.attempt_no=j.attempt_no
WHERE j.incident_id=:'incident_id'::uuid AND (:'job_id'='' OR j.id::text=:'job_id');
SELECT j.id AS job_id, c.id AS candidate_id, ref.id AS evidence_ref,
       e.query_id, e.id IS NOT NULL AS evidence_exists,
       e.job_id=c.job_id AND e.attempt_no=c.attempt_no AS same_attempt
FROM jobs j JOIN result_candidates c ON c.id=j.published_result_id
CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(c.body->'evidence_refs','[]')) ref(id)
LEFT JOIN evidence e ON e.id::text=ref.id
WHERE j.incident_id=:'incident_id'::uuid AND (:'job_id'='' OR j.id::text=:'job_id');

\echo '09 - Published result available to Backend and later reports'
SELECT j.id AS job_id, j.incident_id, c.id AS result_id, c.content_hash,
       c.body->>'result_status' AS result_status, c.body->'recommendations' AS recommendations
FROM jobs j JOIN result_candidates c ON c.id=j.published_result_id
WHERE j.kind='rca' AND j.status='succeeded' AND j.incident_id=:'incident_id'::uuid
  AND (:'job_id'='' OR j.id::text=:'job_id') ORDER BY j.created_at DESC;

\echo '10 - Configuration provenance and available worker capacity'
SELECT s.source, s.config_revision, s.snapshot->'analysis_policies' AS policies,
       s.snapshot->'episode_policy' AS episode_policy
FROM incident_sources s WHERE s.source IN
  (SELECT source FROM alert_events WHERE incident_id=:'incident_id'::uuid);
SELECT p.revision, p.content_hash, p.snapshot FROM incident_analysis_profiles p
JOIN incidents i ON i.analysis_profile_revision=p.revision WHERE i.id=:'incident_id'::uuid;
SELECT pool_id, config_revision, shared_limit, kind_limits, last_granted_kind FROM capacity_state;
COMMIT;
