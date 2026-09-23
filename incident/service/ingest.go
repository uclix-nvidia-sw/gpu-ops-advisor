package service

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"github.com/jackc/pgx/v5"
	. "gpu-ops-advisor/shared/contract"
	"sort"
	"strings"
	"time"
)

type alert struct {
	raw                                    Object
	labels, annotations                    map[string]string
	cluster, fingerprint, status, eventKey string
	starts, ends                           time.Time
	scope                                  Scope
	target                                 Object
	policy                                 *Policy
}

func stringMap(v any, required bool) (map[string]string, bool) {
	if v == nil && !required {
		return map[string]string{}, true
	}
	m, ok := v.(map[string]any)
	if !ok || len(m) > 200 {
		return nil, false
	}
	out := map[string]string{}
	for k, v := range m {
		s, ok := v.(string)
		if !ok || strings.TrimSpace(k) == "" || len(k) > 200 || len(s) > 4096 {
			return nil, false
		}
		out[k] = s
	}
	return out, true
}
func (s *Server) parse(raw any, now time.Time) (alert, string) {
	a := alert{}
	b, ok := raw.(map[string]any)
	if !ok {
		return a, "invalid_alert_object"
	}
	if containsNUL(b) {
		return a, "invalid_unicode"
	}
	a.raw = b
	var valid bool
	a.labels, valid = stringMap(b["labels"], true)
	if !valid {
		return a, "invalid_labels"
	}
	a.annotations, valid = stringMap(b["annotations"], false)
	if !valid {
		return a, "invalid_annotations"
	}
	a.cluster = a.labels[s.Config.ClusterLabel]
	a.fingerprint = String(b, "fingerprint")
	a.status = String(b, "status")
	if a.cluster == "" || len(a.cluster) > 200 || a.labels["alertname"] == "" || a.fingerprint == "" || len(a.fingerprint) > 256 || !Has([]string{"firing", "resolved"}, a.status) {
		return a, "missing_alert_identity"
	}
	var e error
	a.starts, e = time.Parse(time.RFC3339Nano, String(b, "startsAt"))
	if e != nil || a.starts.IsZero() {
		return a, "invalid_starts_at"
	}
	a.starts = a.starts.UTC()
	if a.starts.After(now.Add(time.Duration(s.Config.FutureSeconds) * time.Second)) {
		return a, "future_timestamp"
	}
	if v := String(b, "endsAt"); v != "" {
		a.ends, e = time.Parse(time.RFC3339Nano, v)
		if e != nil {
			return a, "invalid_ends_at"
		}
	}
	if a.status == "resolved" && (a.ends.IsZero() || a.ends.Before(a.starts) || a.ends.After(now.Add(time.Duration(s.Config.FutureSeconds)*time.Second))) {
		return a, "invalid_ends_at"
	}
	var ns []string
	if value := a.labels["namespace"]; value != "" {
		if len(value) > 253 {
			return a, "invalid_namespace"
		}
		ns = []string{value}
	}
	a.scope = Scope{Clusters: []ClusterScope{{ClusterID: a.cluster, Namespaces: ns}}}
	a.target = Object{"cluster_id": a.cluster, "alertname": a.labels["alertname"]}
	for _, key := range []string{"namespace", "node", "node_uid", "gpu_uuid", "pod", "pod_uid", "container"} {
		if v := a.labels[key]; v != "" {
			a.target[key] = v
		}
	}
	// Fingerprint+start identify the alarm lifecycle; target is explicit, never invented.
	a.eventKey = Hash(Object{"source": s.Config.Source, "cluster": a.cluster, "fingerprint": a.fingerprint, "starts_at": a.starts, "target": a.target})
	for i := range s.Config.Policies {
		if s.Config.Policies[i].AlertName == a.labels["alertname"] {
			a.policy = &s.Config.Policies[i]
			break
		}
	}
	return a, ""
}
func (s *Server) ingest(ctx context.Context, b Object, raw []byte) (Object, int, error) {
	children, ok := b["alerts"].([]any)
	bad := !ok || len(children) == 0
	batchReason := "alerts"
	if len(children) > s.Config.MaxAlerts {
		return nil, 0, Fail(413, "too_many_alerts", "알람 배열 한도를 초과했습니다.")
	}
	if v, exists := b["truncatedAlerts"]; exists {
		n, ok := v.(float64)
		if !ok || n < 0 || n != float64(int(n)) {
			bad, batchReason = true, "truncatedAlerts"
		}
	}
	sum := sha256.Sum256(raw)
	hash := hex.EncodeToString(sum[:])
	var result Object
	status := 202
	e := s.transaction(ctx, func(tx pgx.Tx, now time.Time) error {
		var old Object
		var oldStatus int
		var receipt string
		e := tx.QueryRow(ctx, "SELECT id,response,http_status FROM incident_webhook_receipts WHERE source=$1 AND body_hash=$2", s.Config.Source, hash).Scan(&receipt, &old, &oldStatus)
		if e == nil {
			result, status = old, oldStatus
			if s.Config.Episodes == nil || bad || oldStatus != 202 {
				return nil
			}
		}
		if e != nil && e != pgx.ErrNoRows {
			return e
		}
		replay := e == nil
		if !replay {
			receipt = ID()
			_, e = tx.Exec(ctx, "INSERT INTO incident_webhook_receipts(id,source,body_hash,raw_payload,received_at,response,http_status,raw_body) VALUES($1,$2,$3,$4,$5,'{}',202,$6)", receipt, s.Config.Source, hash, safeJSON(b), now, raw)
			if e != nil {
				return e
			}
		}
		if bad {
			status = 422
			result = Object{"receipt_id": receipt, "error": Invalid(batchReason)}
		} else {
			if s.Config.Episodes != nil {
				if e = s.lockEpisodeGroups(ctx, tx, children, now); e != nil {
					return e
				}
			}
			counted := map[string]bool{}
			items := []Object{}
			accepted, rejected := 0, 0
			for i, rawAlert := range children {
				var item Object
				if s.Config.Episodes != nil {
					item, e = s.episodeChild(ctx, tx, now, receipt, i, rawAlert, counted)
				} else {
					item, e = s.child(ctx, tx, now, receipt, i, rawAlert)
				}
				if e != nil {
					return e
				}
				items = append(items, item)
				if item["disposition"] == "invalid" {
					rejected++
				} else {
					accepted++
				}
			}
			if replay {
				return nil // Continuity is committed, but the original receipt stays immutable.
			}
			warnings := []string{}
			if Number(b, "truncatedAlerts") > 0 {
				warnings = append(warnings, "grafana_truncated_alerts")
			}
			result = Object{"receipt_id": receipt, "status": "accepted", "accepted_alerts": accepted, "invalid_alerts": rejected, "items": items, "warnings": warnings, "truncated_alerts": Number(b, "truncatedAlerts")}
		}
		_, e = tx.Exec(ctx, "UPDATE incident_webhook_receipts SET response=$2,http_status=$3 WHERE id=$1", receipt, result, status)
		return e
	})
	return result, status, e
}
func (s *Server) child(ctx context.Context, tx pgx.Tx, now time.Time, receipt string, index int, raw any) (Object, error) {
	a, reason := s.parse(raw, now)
	payloadHash := Hash(raw)
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
		if raw == nil {
			raw = json.RawMessage("null")
		}
		id := ID()
		_, e := tx.Exec(ctx, "INSERT INTO alert_events(id,source,payload_hash,raw_payload,observed_at,receipt_id,alert_index,disposition,reason) VALUES($1,$2,$3,$4,$5,$6,$7,'invalid',$8)", id, s.Config.Source, payloadHash, safeJSON(raw), now, receipt, index, reason)
		return Object{"index": index, "alert_event_id": id, "disposition": "invalid", "reason": reason}, e
	}
	old, e := one(ctx, tx, "SELECT jsonb_build_object('id',id,'incident_id',incident_id,'disposition',disposition,'reason',reason) FROM alert_events WHERE source=$1 AND cluster_id=$2 AND fingerprint=$3 AND starts_at=$4 AND payload_hash=$5", s.Config.Source, a.cluster, a.fingerprint, a.starts, payloadHash)
	if e == nil {
		return Object{"index": index, "alert_event_id": old["id"], "incident_id": old["incident_id"], "disposition": old["disposition"], "reason": old["reason"], "duplicate": true}, nil
	}
	if !missing(e) {
		return nil, e
	}
	j, e := one(ctx, tx, "SELECT to_jsonb(i) FROM incidents i WHERE event_key=$1 FOR UPDATE", a.eventKey)
	if e != nil && !missing(e) {
		return nil, e
	}
	if missing(e) {
		id := ID()
		_, e = tx.Exec(ctx, "INSERT INTO incidents(id,event_key,cluster_id,occurred_at,target,scope,state,evidence_version,version,alarm_status,first_seen,last_seen,updated_at) VALUES($1,$2,$3,$4,$5,$6,'open',0,1,$7,$4,$8,$8)", id, a.eventKey, a.cluster, a.starts, a.target, a.scope, a.status, now)
		if e != nil {
			return nil, e
		}
		j, e = one(ctx, tx, "SELECT to_jsonb(i) FROM incidents i WHERE id=$1", id)
		if e != nil {
			return nil, e
		}
	}
	id := String(j, "id")
	eventID := ID()
	alarmStatus := a.status
	if j["alarm_status"] == "resolved" {
		alarmStatus = "resolved"
	}
	reason = ""
	if a.policy == nil {
		reason = "analysis_policy_unconfigured"
	} else if alarmStatus == "resolved" {
		reason = "alarm_resolved"
	} else if j["state"] == "closed" {
		reason = "incident_closed"
	} else if a.starts.Before(now.Add(-time.Duration(s.Config.MaxAgeSeconds) * time.Second)) {
		reason = "stale_alert"
	} else if a.starts.After(now) {
		reason = "future_timestamp"
	}
	eligible := reason == ""
	meaningful := Object{"target": a.target}
	if a.policy != nil {
		meaningful["policy_revision"] = a.policy.Revision
		fields := Object{}
		for _, key := range a.policy.EvidenceLabels {
			fields["label:"+key] = a.labels[key]
		}
		for _, key := range a.policy.EvidenceAnnotations {
			fields["annotation:"+key] = a.annotations[key]
		}
		meaningful["evidence"] = fields
	}
	evidenceHash := Hash(meaningful)
	revision := Number(j, "evidence_version")
	changed := revision == 0 || (eligible && (j["last_evidence_hash"] != evidenceHash || String(j, "rca_eligibility_reason") != ""))
	disposition := "recorded"
	if !eligible {
		disposition = "ineligible"
	}
	if !changed && eligible {
		reason = "repeated_evidence"
	}
	_, e = tx.Exec(ctx, "INSERT INTO alert_events(id,source,cluster_id,fingerprint,starts_at,status,payload_hash,raw_payload,observed_at,receipt_id,alert_index,incident_id,disposition,reason) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,NULLIF($14,''))", eventID, s.Config.Source, a.cluster, a.fingerprint, a.starts, a.status, payloadHash, raw, now, receipt, index, id, disposition, reason)
	if e != nil {
		return nil, e
	}
	var outbox any
	if changed {
		revision++
		var input any
		var policyRevision any
		if a.policy != nil {
			p := a.policy
			policyRevision = p.Revision
			purposes := append([]string(nil), p.PurposeIDs...)
			sort.Strings(purposes)
			end := a.starts.Add(time.Duration(s.Config.AfterSeconds) * time.Second)
			if now.After(a.starts) && end.After(now) {
				end = now
			}
			input = Object{"incident_id": id, "evidence_version": revision, "analysis_profile_revision": p.Revision, "scope": a.scope, "target": a.target, "incident_time": a.starts.Format(time.RFC3339Nano), "time_range": Object{"start": a.starts.Add(-time.Duration(s.Config.BeforeSeconds) * time.Second).Format(time.RFC3339Nano), "end": end.UTC().Format(time.RFC3339Nano)}, "purpose_ids": purposes}
		}
		snapshot := Object{"input": input, "alert": raw, "alert_event_id": eventID, "received_at": now, "analysis_policy": a.policy, "eligible": eligible, "reason": reason}
		// Hash the JSON object representation that PostgreSQL/JC will read, including nested policy structs.
		snapshot, e = Decode[Object](snapshot)
		if e != nil {
			return nil, e
		}
		_, e = tx.Exec(ctx, "INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES($1,$2,$3,$4)", id, revision, snapshot, Hash(snapshot))
		if e != nil {
			return nil, e
		}
		_, e = tx.Exec(ctx, "UPDATE incidents SET evidence_version=$2,last_evidence_hash=$3,analysis_profile_revision=$4,version=version+1 WHERE id=$1", id, revision, evidenceHash, policyRevision)
		if e != nil {
			return nil, e
		}
		if eligible {
			source := fmt.Sprintf("incident:%s:evidence:%d:profile:%s", id, revision, a.policy.Revision)
			oid := ID()
			outbox = oid
			deadline := now.Add(time.Duration(s.Config.DispatchSeconds) * time.Second)
			envelope := Object{"contract_version": "1.3", "source_module": "incident", "source_key": source, "kind": "rca", "input": input, "dispatch_deadline": deadline.UTC().Format(time.RFC3339Nano), "deadline_at": now.Add(time.Duration(s.Config.DeadlineSeconds) * time.Second).UTC().Format(time.RFC3339Nano), "snapshot_ref": Object{"incident_id": id, "revision": revision}, "execution_profile_revision": s.Config.ExecutionRevision}
			_, e = tx.Exec(ctx, "INSERT INTO enqueue_outbox(id,source_module,source_key,kind,input_snapshot,request_hash,status,dispatch_deadline) VALUES($1,'incident',$2,'rca',$3,$4,'pending',$5)", oid, source, envelope, Hash(envelope), deadline)
			if e != nil {
				return nil, e
			}
		}
	}
	// Repeated firing does not reset a resolved lifecycle or the human review state.
	eligibilityReason := reason
	if eligible {
		eligibilityReason = ""
	}
	var resolvedAt any
	if a.status == "resolved" {
		resolvedAt = a.ends
	}
	_, e = tx.Exec(ctx, "UPDATE incidents SET alarm_status=$2,alarm_resolved_at=COALESCE($3,alarm_resolved_at),last_seen=$4,updated_at=$4,rca_eligibility_reason=NULLIF($5,''),version=version+CASE WHEN alarm_status IS DISTINCT FROM $2 THEN 1 ELSE 0 END WHERE id=$1", id, alarmStatus, resolvedAt, now, eligibilityReason)
	if e != nil {
		return nil, e
	}
	return Object{"index": index, "alert_event_id": eventID, "incident_id": id, "evidence_version": revision, "disposition": disposition, "reason": reason, "outbox_id": outbox}, nil
}

// PostgreSQL jsonb cannot represent U+0000. Preserve such invalid children as encoded JSON,
// and retain the exact webhook bytes separately without discarding valid sibling alerts.
func containsNUL(v any) bool {
	switch m := v.(type) {
	case string:
		return strings.ContainsRune(m, 0)
	case map[string]any:
		for k, v := range m {
			if strings.ContainsRune(k, 0) || containsNUL(v) {
				return true
			}
		}
	case []any:
		for _, v := range m {
			if containsNUL(v) {
				return true
			}
		}
	}
	return false
}
func safeJSON(v any) any {
	if containsNUL(v) {
		b, _ := json.Marshal(v)
		return Object{"encoding": "base64-json", "data": base64.StdEncoding.EncodeToString(b)}
	}
	return v
}
