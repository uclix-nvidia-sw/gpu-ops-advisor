package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	. "gpu-ops-advisor/shared/contract"
)

type episodeAlert struct {
	alert
	group, timeBasis string
	occurred, at     time.Time
	missing          []string
	excluded         bool
}

func (s *Server) parseEpisode(raw any, now time.Time) (episodeAlert, string) {
	a, reason := s.parse(raw, now)
	v := episodeAlert{alert: a, at: a.starts, timeBasis: "starts_at", missing: []string{}}
	if reason != "" {
		return v, reason
	}
	if strings.TrimSpace(a.fingerprint) == "" || strings.TrimSpace(a.labels["alertname"]) == "" {
		return v, "missing_alert_identity"
	}
	if a.starts.Before(now.Add(-time.Duration(s.Config.MaxAgeSeconds) * time.Second)) {
		return v, "stale_alert"
	}
	v.occurred, _ = time.Parse("2006-01-02 15:04:05.999999999 -0700 MST", a.annotations["occurred_at"])
	if v.occurred.IsZero() {
		v.occurred, _ = time.Parse(time.RFC3339Nano, a.annotations["occurred_at"])
	}
	v.occurred = v.occurred.UTC()
	switch {
	case a.annotations["occurred_at"] == "":
		v.timeBasis = "occurred_at_missing"
	case v.occurred.IsZero():
		v.timeBasis = "occurred_at_invalid"
	case s.Config.Episodes.OccurredAtContractRevision == "":
		v.timeBasis = "occurred_at_unverified"
	default:
		if v.occurred.Before(now.Add(-time.Duration(s.Config.MaxAgeSeconds) * time.Second)) {
			return v, "stale_occurred_at"
		}
		if v.occurred.After(now.Add(time.Duration(s.Config.FutureSeconds) * time.Second)) {
			return v, "future_occurred_at"
		}
		v.at, v.timeBasis = v.occurred, "occurred_at"
	}
	for _, key := range []string{"machine_id", "component"} {
		if strings.TrimSpace(a.labels[key]) == "" {
			v.missing = append(v.missing, key)
		} else {
			v.target[key] = a.labels[key]
		}
	}
	// PostgreSQL timestamptz stores microseconds; use that same precision in fallback keys.
	v.starts = a.starts.Truncate(time.Microsecond)
	v.excluded = Has([]string{"DatasourceNoData", "DatasourceError"}, a.labels["alertname"])
	parts := []string{"component", s.Config.Source, a.cluster, a.labels["machine_id"], a.labels["component"]}
	if len(v.missing) != 0 {
		parts = []string{"alert", s.Config.Source, a.cluster, a.fingerprint, v.starts.Format(time.RFC3339Nano)}
	}
	if v.excluded {
		parts = []string{"excluded", s.Config.Source, a.cluster, a.labels["alertname"], a.fingerprint, v.starts.Format(time.RFC3339Nano)}
	}
	b, _ := json.Marshal(parts)
	v.group = string(b)
	if len(b) > 2000 {
		return v, "identity_too_long"
	}
	return v, ""
}

func lockEpisode(ctx context.Context, tx pgx.Tx, group string) error {
	_, e := tx.Exec(ctx, "SELECT pg_advisory_xact_lock(hashtextextended($1,72931023))", group)
	return e
}

func (s *Server) lockEpisodeGroups(ctx context.Context, tx pgx.Tx, children []any, now time.Time) error {
	groups := map[string]bool{}
	for _, child := range children {
		if a, reason := s.parseEpisode(child, now); reason == "" {
			groups[a.group] = true
		}
	}
	keys := make([]string, 0, len(groups))
	for key := range groups {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		if e := lockEpisode(ctx, tx, key); e != nil {
			return e
		}
	}
	return nil
}

func (s *Server) prepareEpisodes(ctx context.Context, tx pgx.Tx) error {
	if s.Config.Episodes == nil {
		var exists bool
		if e := tx.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM incident_alert_lifecycles WHERE source=$1 AND NOT legacy)", s.Config.Source).Scan(&exists); e != nil {
			return e
		}
		if exists {
			return errors.New("episode source cannot restart as a 1.3 producer; preserve pending work and use a compatible producer")
		}
		return nil
	}
	// The existing global intake lock also drains concurrent 1.3 transactions at cutover.
	var conflict bool
	if e := tx.QueryRow(ctx, `SELECT EXISTS(
	 SELECT 1 FROM incident_evidence_versions v JOIN incidents i ON i.id=v.incident_id
	 WHERE i.source=$1 AND v.snapshot->'episode_policy'->>'revision'=$2 AND v.snapshot->'episode_policy'<>$3::jsonb
	 UNION ALL SELECT 1 FROM incident_sources WHERE source=$1 AND snapshot->'episode_policy'->>'revision'=$2 AND snapshot->'episode_policy'<>$3::jsonb)`, s.Config.Source, s.Config.Episodes.Revision, s.Config.Episodes).Scan(&conflict); e != nil {
		return e
	}
	if conflict {
		return errors.New("episode policy revision is immutable; use a new revision")
	}
	if e := tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM alert_events a JOIN incidents i ON i.id=a.incident_id
	 WHERE a.source=$1 AND a.disposition<>'invalid' AND i.dedup_group IS NULL
	 GROUP BY a.cluster_id,a.fingerprint,a.starts_at HAVING count(DISTINCT a.incident_id)>1)`, s.Config.Source).Scan(&conflict); e != nil {
		return e
	}
	if conflict {
		return errors.New("legacy lifecycle belongs to multiple incidents; resolve attribution before episode cutover")
	}
	_, e := tx.Exec(ctx, `INSERT INTO incident_alert_lifecycles(source,cluster_id,fingerprint,starts_at,latest_incident_id,resolved_at,last_received_at,last_disposition,legacy)
	 SELECT a.source,a.cluster_id,a.fingerprint,a.starts_at,a.incident_id,
	 max(i.alarm_resolved_at),max(a.observed_at),'legacy',true
	 FROM alert_events a JOIN incidents i ON i.id=a.incident_id
	 WHERE a.source=$1 AND a.disposition<>'invalid' AND i.dedup_group IS NULL
	 GROUP BY a.source,a.cluster_id,a.fingerprint,a.starts_at,a.incident_id
	 ON CONFLICT DO NOTHING`, s.Config.Source)
	if e != nil {
		return e
	}
	_, e = tx.Exec(ctx, `UPDATE incidents i SET source=a.source,fingerprint=a.fingerprint,starts_at=a.starts_at
	 FROM (SELECT DISTINCT ON (incident_id) incident_id,source,fingerprint,starts_at FROM alert_events
	 WHERE source=$1 AND disposition<>'invalid' AND incident_id IS NOT NULL ORDER BY incident_id,observed_at,alert_index,id) a
	 WHERE i.id=a.incident_id AND i.dedup_group IS NULL AND i.source IS NULL`, s.Config.Source)
	return e
}

func episodeEnd(j Object, now time.Time) (time.Time, string) {
	if j["dedup_group"] == nil || j["ended_at"] != nil || !now.After(instant(j, "last_observed_at").Add(time.Duration(Number(j, "observation_gap_seconds"))*time.Second)) {
		return time.Time{}, ""
	}
	if j["alarm_status"] == "resolved" && !instant(j, "alarm_resolved_at").IsZero() {
		return instant(j, "alarm_resolved_at"), "alarm_resolved"
	}
	return instant(j, "last_observed_at"), "observation_gap"
}

func endEpisode(ctx context.Context, tx pgx.Tx, j Object, now time.Time) error {
	at, reason := episodeEnd(j, now)
	if reason == "" {
		return nil
	}
	_, e := tx.Exec(ctx, "UPDATE incidents SET ended_at=$2,ended_reason=$3,version=version+1,updated_at=$4 WHERE id=$1", j["id"], at, reason, now)
	if e == nil {
		j["ended_at"], j["ended_reason"] = at.Format(time.RFC3339Nano), reason
	}
	return e
}

func (s *Server) episodeChild(ctx context.Context, tx pgx.Tx, now time.Time, receipt string, index int, raw any, counted map[string]bool) (Object, error) {
	a, reason := s.parseEpisode(raw, now)
	if reason == "" {
		var exists bool
		if e := tx.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM cluster_registry WHERE id=$1 AND enabled)", a.cluster).Scan(&exists); e != nil {
			return nil, e
		}
		if !exists {
			reason = "cluster_unregistered"
		}
	}
	if reason != "" {
		old, e := one(ctx, tx, "SELECT jsonb_build_object('alert_event_id',id,'disposition',disposition,'reason',reason) FROM alert_events WHERE receipt_id=$1 AND alert_index=$2 LIMIT 1", receipt, index)
		if e == nil {
			return old, nil
		}
		if !missing(e) {
			return nil, e
		}
		id := ID()
		if raw == nil {
			raw = json.RawMessage("null")
		}
		_, e = tx.Exec(ctx, "INSERT INTO alert_events(id,source,payload_hash,raw_payload,observed_at,receipt_id,alert_index,disposition,reason) VALUES($1,$2,$3,$4,$5,$6,$7,'invalid',$8)", id, s.Config.Source, Hash(raw), safeJSON(raw), now, receipt, index, reason)
		return Object{"index": index, "alert_event_id": id, "disposition": "invalid", "reason": reason}, e
	}
	old, e := one(ctx, tx, "SELECT to_jsonb(a) FROM alert_events a WHERE source=$1 AND cluster_id=$2 AND fingerprint=$3 AND starts_at=$4 AND payload_hash=$5", s.Config.Source, a.cluster, a.fingerprint, a.starts, Hash(raw))
	duplicate := e == nil
	if e != nil && !missing(e) {
		return nil, e
	}
	eventID := String(old, "id")
	if !duplicate {
		eventID = ID()
	}
	_, e = tx.Exec(ctx, `INSERT INTO incident_alert_lifecycles(source,cluster_id,fingerprint,starts_at,dedup_group,last_received_at,last_disposition)
	 VALUES($1,$2,$3,$4,$5,$6,'received') ON CONFLICT DO NOTHING`, s.Config.Source, a.cluster, a.fingerprint, a.starts, a.group, now)
	if e != nil {
		return nil, e
	}
	life, e := one(ctx, tx, "SELECT to_jsonb(l) FROM incident_alert_lifecycles l WHERE source=$1 AND cluster_id=$2 AND fingerprint=$3 AND starts_at=$4 FOR UPDATE", s.Config.Source, a.cluster, a.fingerprint, a.starts)
	if e != nil {
		return nil, e
	}
	var incidentID any = life["latest_incident_id"]
	var outbox any
	switch {
	case life["legacy"] == true:
		reason = "legacy_lifecycle"
		if a.status == "resolved" {
			_, e = tx.Exec(ctx, `UPDATE incident_alert_lifecycles SET resolved_at=GREATEST(resolved_at,$5)
			 WHERE source=$1 AND cluster_id=$2 AND fingerprint=$3 AND starts_at=$4`, s.Config.Source, a.cluster, a.fingerprint, a.starts, a.ends)
			if e != nil {
				return nil, e
			}
			_, e = tx.Exec(ctx, "UPDATE incidents SET alarm_status='resolved',alarm_resolved_at=GREATEST(alarm_resolved_at,$2),updated_at=$3,version=version+1 WHERE id=$1 AND alarm_status IS DISTINCT FROM 'resolved'", incidentID, a.ends, now)
			if e != nil {
				return nil, e
			}
		}
	case life["dedup_group"] != a.group:
		reason = "identity_conflict"
	default:
		if a.status == "resolved" {
			_, e = tx.Exec(ctx, `UPDATE incident_alert_lifecycles SET resolved_at=GREATEST(resolved_at,$5)
			 WHERE source=$1 AND cluster_id=$2 AND fingerprint=$3 AND starts_at=$4`, s.Config.Source, a.cluster, a.fingerprint, a.starts, a.ends)
			if e != nil {
				return nil, e
			}
			life["resolved_at"] = a.ends.Format(time.RFC3339Nano)
		}
		if incidentID != nil {
			if e = refreshAlarm(ctx, tx, incidentID, now); e != nil {
				return nil, e
			}
		}
		j, err := one(ctx, tx, "SELECT to_jsonb(i) FROM incidents i WHERE dedup_group=$1 ORDER BY episode_started_at DESC,id DESC LIMIT 1 FOR UPDATE", a.group)
		if err != nil && !missing(err) {
			return nil, err
		}
		if j != nil {
			if e = endEpisode(ctx, tx, j, now); e != nil {
				return nil, e
			}
		}
		switch {
		case life["resolved_at"] != nil:
			reason = "alarm_resolved"
		case j != nil && j["ended_at"] == nil:
			incidentID, reason = j["id"], "repeated_observation"
		case j != nil && (duplicate || !freshAfterEpisode(a, j)):
			reason = "post_episode_freshness_unknown"
		default:
			reason = ""
			if j != nil && j["state"] != "closed" {
				reason = "prior_analysis_open"
			}
			if a.excluded {
				reason = "analysis_excluded"
			}
			incidentID, outbox, e = s.createEpisode(ctx, tx, a, j, raw, eventID, now, reason)
			if e != nil {
				return nil, e
			}
		}
		if reason == "" || reason == "prior_analysis_open" || reason == "analysis_excluded" || reason == "repeated_observation" {
			_, e = tx.Exec(ctx, `UPDATE incident_alert_lifecycles SET latest_incident_id=$5 WHERE source=$1 AND cluster_id=$2 AND fingerprint=$3 AND starts_at=$4`, s.Config.Source, a.cluster, a.fingerprint, a.starts, incidentID)
			if e != nil {
				return nil, e
			}
			if !counted[a.group] {
				_, e = tx.Exec(ctx, "UPDATE incidents SET last_observed_at=$2,last_seen=$2,observation_count=observation_count+1,updated_at=$2,version=version+1 WHERE id=$1", incidentID, now)
				if e != nil {
					return nil, e
				}
				counted[a.group] = true
			}
			if e = refreshAlarm(ctx, tx, incidentID, now); e != nil {
				return nil, e
			}
		}
	}
	_, e = tx.Exec(ctx, `UPDATE incident_alert_lifecycles SET last_received_at=$5,last_disposition=$6
	 WHERE source=$1 AND cluster_id=$2 AND fingerprint=$3 AND starts_at=$4`, s.Config.Source, a.cluster, a.fingerprint, a.starts, now, reason)
	if e != nil {
		return nil, e
	}
	if !duplicate {
		_, e = tx.Exec(ctx, `INSERT INTO alert_events(id,source,cluster_id,fingerprint,starts_at,status,payload_hash,raw_payload,observed_at,receipt_id,alert_index,incident_id,disposition,reason)
		 VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'recorded',NULLIF($13,''))`, eventID, s.Config.Source, a.cluster, a.fingerprint, a.starts, a.status, Hash(raw), raw, now, receipt, index, incidentID, reason)
	}
	warnings := []string{}
	if len(a.missing) != 0 {
		warnings = append(warnings, "identity_incomplete")
	}
	return Object{"index": index, "alert_event_id": eventID, "incident_id": incidentID, "disposition": "recorded", "reason": reason, "duplicate": duplicate, "outbox_id": outbox, "warnings": warnings}, e
}

func freshAfterEpisode(a episodeAlert, j Object) bool {
	boundary := instant(j, "last_observed_at").Add(time.Duration(Number(j, "observation_gap_seconds")) * time.Second)
	if !instant(j, "closed_at").IsZero() {
		boundary = instant(j, "closed_at")
	}
	return a.starts.After(boundary) || a.timeBasis == "occurred_at" && a.occurred.After(boundary)
}

func refreshAlarm(ctx context.Context, tx pgx.Tx, id any, now time.Time) error {
	_, e := tx.Exec(ctx, `UPDATE incidents i SET alarm_status=a.status,alarm_resolved_at=a.resolved_at,
	 version=version+CASE WHEN alarm_status IS DISTINCT FROM a.status THEN 1 ELSE 0 END,updated_at=$2
	 FROM (SELECT CASE WHEN bool_or(resolved_at IS NULL) THEN 'firing' ELSE 'resolved' END AS status,
	 CASE WHEN bool_or(resolved_at IS NULL) THEN NULL ELSE max(resolved_at) END AS resolved_at
	 FROM incident_alert_lifecycles WHERE latest_incident_id=$1) a
	 WHERE i.id=$1 AND i.dedup_group IS NOT NULL`, id, now)
	return e
}

func (s *Server) createEpisode(ctx context.Context, tx pgx.Tx, a episodeAlert, prior Object, raw any, eventID string, now time.Time, reason string) (string, any, error) {
	id := ID()
	var priorID any
	if prior != nil {
		priorID = prior["id"]
	}
	_, e := tx.Exec(ctx, `INSERT INTO incidents(id,cluster_id,occurred_at,target,scope,state,evidence_version,version,alarm_status,first_seen,last_seen,updated_at,
	 source,fingerprint,starts_at,dedup_group,episode_started_at,last_observed_at,observation_count,observation_gap_seconds,prior_incident_id,rca_eligibility_reason)
	 VALUES($1,$2,$3,$4,$5,'open',1,1,'firing',$3,$6,$6,$7,$8,$9,$10,$6,$6,0,$11,$12,NULLIF($13,''))`, id, a.cluster, a.at, a.target, a.scope, now, s.Config.Source, a.fingerprint, a.starts, a.group, s.Config.Episodes.ObservationGapSeconds, priorID, reason)
	if e != nil {
		return "", nil, e
	}
	start, end := s.analysisWindow(a.at, now)
	input := Object{"incident_id": id, "evidence_version": 1, "scope": a.scope, "target": a.target, "incident_time": a.at.Format(time.RFC3339Nano), "time_range": Object{"start": start.Format(time.RFC3339Nano), "end": end.Format(time.RFC3339Nano)}}
	if priorID != nil {
		input["prior_incident_id"] = priorID
	}
	var occurred any
	if !a.occurred.IsZero() {
		occurred = a.occurred.Format(time.RFC3339Nano)
	}
	warnings := []string{}
	if len(a.missing) > 0 {
		warnings = append(warnings, "identity_incomplete")
	}
	snapshot, e := Decode[Object](Object{"input": input, "alert": raw, "alert_event_id": eventID, "received_at": now, "eligible": reason == "", "reason": reason,
		"dedup_group": a.group, "episode_policy": s.Config.Episodes, "config_revision": Hash(s.Config), "parsed_occurred_at": occurred,
		"incident_time_basis": a.timeBasis, "occurred_at_contract_revision": s.Config.Episodes.OccurredAtContractRevision, "warnings": warnings, "missing_identity_fields": a.missing})
	if e != nil {
		return "", nil, e
	}
	_, e = tx.Exec(ctx, "INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES($1,1,$2,$3)", id, snapshot, Hash(snapshot))
	if e != nil || reason != "" {
		return id, nil, e
	}
	source, oid := fmt.Sprintf("incident:%s:first", id), ID()
	deadline := now.Add(time.Duration(s.Config.DispatchSeconds) * time.Second)
	envelope := Object{"contract_version": "1.4", "source_module": "incident", "source_key": source, "kind": "rca", "input": input,
		"dispatch_deadline": deadline.Format(time.RFC3339Nano), "deadline_at": now.Add(time.Duration(s.Config.DeadlineSeconds) * time.Second).Format(time.RFC3339Nano),
		"snapshot_ref": Object{"incident_id": id, "revision": 1}, "execution_profile_revision": s.Config.ExecutionRevision}
	_, e = tx.Exec(ctx, "INSERT INTO enqueue_outbox(id,source_module,source_key,kind,input_snapshot,request_hash,status,dispatch_deadline) VALUES($1,'incident',$2,'rca',$3,$4,'pending',$5)", oid, source, envelope, Hash(envelope), deadline)
	return id, oid, e
}
