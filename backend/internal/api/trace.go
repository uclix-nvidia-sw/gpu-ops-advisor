package api

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	. "gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/internal/store"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
)

// Diagnostic responses expose stored inputs, never lease credentials or private candidates.
func cleanTrace(v any) {
	sanitize(v)
	switch m := v.(type) {
	case map[string]any:
		for key, value := range m {
			normalized := strings.ToLower(strings.ReplaceAll(strings.ReplaceAll(key, "-", ""), "_", ""))
			switch normalized {
			case "authorization", "proxyauthorization", "headers", "cookie", "setcookie", "apikey", "password", "secret", "accesstoken", "refreshtoken", "claimtoken", "rawbody":
				delete(m, key)
			default:
				cleanTrace(value)
			}
		}
	case []any:
		for _, value := range m {
			cleanTrace(value)
		}
	}
}

func (s *Server) jobTrace(w http.ResponseWriter, q *Request, id string) error {
	if e := onlyQuery(q); e != nil {
		return e
	}
	ctx := q.R.Context()
	tx, e := s.DB.Pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	job, e := store.One(ctx, tx, "SELECT to_jsonb(j) FROM jobs j WHERE id::text=$1", id)
	if e != nil {
		return e
	}
	out := Object{"job_id": id, "kind": job["kind"], "input_snapshot": job["input_snapshot"], "versions": job["versions"], "incident_id": job["incident_id"], "evidence_version": job["evidence_version"], "source_module": job["source_module"], "source_key": job["source_key"]}
	// Each section reports schema absence separately from a missing linked row.
	sections := []struct {
		name, table, sql string
		args             []any
	}{
		{"incident_snapshot", "incident_evidence_versions", "SELECT to_jsonb(v) FROM incident_evidence_versions v WHERE incident_id::text=$1 AND revision=$2", []any{job["incident_id"], job["evidence_version"]}},
		{"outbox", "enqueue_outbox", "SELECT jsonb_build_object('id',o.id,'job_id',o.job_id,'source_module',o.source_module,'source_key',o.source_key,'status',o.status,'attempts',o.attempts,'last_error',o.last_error,'created_at',o.created_at,'input_snapshot',o.input_snapshot) FROM enqueue_outbox o WHERE source_module=$1 AND source_key=$2 AND (job_id IS NULL OR job_id::text=$3)", []any{job["source_module"], job["source_key"], id}},
		{"manual_request", "manual_report_intents", "SELECT jsonb_build_object('source_key',source_key,'envelope',envelope,'created_at',created_at) FROM manual_report_intents WHERE source_key=$1 AND $2='backend'", []any{job["source_key"], job["source_module"]}},
		{"schedule", "schedule_occurrences", "SELECT jsonb_build_object('occurrence',to_jsonb(o),'revision',to_jsonb(r)) FROM schedule_occurrences o LEFT JOIN schedule_revisions r ON r.schedule_id=o.schedule_id AND r.revision=o.revision WHERE o.job_id::text=$1", []any{id}},
		{"publication", "result_candidates", "SELECT jsonb_build_object('id',id,'job_id',job_id,'attempt_no',attempt_no,'kind',kind,'schema_version',schema_version,'validation_status',validation_status,'content_hash',content_hash,'created_at',created_at) FROM result_candidates WHERE id::text=$1 AND job_id::text=$2 AND kind=$3", []any{job["published_result_id"], id, job["kind"]}},
	}
	for _, section := range sections {
		var exists bool
		if e = tx.QueryRow(ctx, "SELECT to_regclass($1) IS NOT NULL", section.table).Scan(&exists); e != nil {
			return e
		}
		state := Object{"state": "schema_unavailable", "record": nil}
		if exists {
			var raw []byte
			e = tx.QueryRow(ctx, section.sql, section.args...).Scan(&raw)
			if e == pgx.ErrNoRows {
				state["state"] = "not_found"
			} else if e != nil {
				return e
			} else {
				var record Object
				if e = json.Unmarshal(raw, &record); e != nil {
					return e
				}
				state["state"], state["record"] = "available", record
			}
		}
		out[section.name] = state
	}
	var alertTables bool
	if e = tx.QueryRow(ctx, "SELECT to_regclass('alert_events') IS NOT NULL AND to_regclass('incident_webhook_receipts') IS NOT NULL").Scan(&alertTables); e != nil {
		return e
	}
	out["alerts"] = Object{"state": "schema_unavailable", "items": []any{}}
	if alertTables {
		alerts, e := store.One(ctx, tx, `SELECT jsonb_build_object('state','available','items',COALESCE(jsonb_agg(v ORDER BY v->>'observed_at',v->>'id'),'[]')) FROM (
   SELECT jsonb_build_object('id',a.id,'incident_id',a.incident_id,'status',a.status,'starts_at',a.starts_at,'observed_at',a.observed_at,'disposition',a.disposition,'reason',a.reason,'labels',a.raw_payload->'labels','annotations',a.raw_payload->'annotations','receipt_id',a.receipt_id,'received_at',r.received_at,'http_status',r.http_status) v
   FROM alert_events a JOIN incident_webhook_receipts r ON r.id=a.receipt_id WHERE a.incident_id::text=$1 ORDER BY a.observed_at DESC,a.id DESC LIMIT 201) t`, job["incident_id"])
		if e != nil {
			return e
		}
		items, _ := alerts["items"].([]any)
		alerts["truncated"] = len(items) > 200
		if len(items) > 200 {
			alerts["items"] = items[1:]
		}
		out["alerts"] = alerts
	}
	cleanTrace(out)
	if e = tx.Commit(ctx); e != nil {
		return e
	}
	s.write(w, q.ID, 200, out)
	return nil
}

func (s *Server) jobEvidence(w http.ResponseWriter, q *Request, id string, detail []string) error {
	if e := onlyQuery(q, "attempt", "cursor", "limit"); e != nil {
		return e
	}
	if e := validateList(q); e != nil {
		return e
	}
	job, e := s.resource(q, "jobs", id, false)
	if e != nil {
		return e
	}
	attempt := Number(job, "attempt_no")
	if raw := q.R.URL.Query().Get("attempt"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed < 0 {
			return Invalid("attempt")
		}
		attempt = parsed
	}
	if len(detail) > 0 {
		v, e := store.One(q.R.Context(), s.DB.Pool, "SELECT to_jsonb(e) FROM evidence e WHERE id::text=$1 AND job_id::text=$2 AND attempt_no=$3", detail[0], id, attempt)
		if e != nil {
			return e
		}
		// Keep only stored query arguments, not arbitrary transport configuration.
		input, _ := v["input"].(map[string]any)
		allowed := Object{}
		for _, key := range []string{"datasourceUid", "logql", "expr", "query", "startRfc3339", "endRfc3339", "startTime", "endTime", "stepSeconds", "queryType", "limit", "direction", "target", "scope", "time_range"} {
			if value, ok := input[key]; ok {
				allowed[key] = value
			}
		}
		v["input"] = allowed
		cleanTrace(v)
		s.write(w, q.ID, 200, v)
		return nil
	}
	filter := Hash(Object{"job": id, "attempt": attempt})
	args := []any{id, attempt}
	where := "job_id::text=$1 AND attempt_no=$2"
	if raw := q.R.URL.Query().Get("cursor"); raw != "" {
		var c cursor
		b, err := base64.RawURLEncoding.DecodeString(raw)
		if err != nil || json.Unmarshal(b, &c) != nil || c.Filter != filter || c.ID == "" {
			return Invalid("cursor")
		}
		if _, err = time.Parse(time.RFC3339Nano, c.At); err != nil {
			return Invalid("cursor")
		}
		args = append(args, c.At, c.ID)
		where += " AND (created_at,id::text)>($3::timestamptz,$4)"
	}
	limit := 50
	if raw := q.R.URL.Query().Get("limit"); raw != "" {
		limit, _ = strconv.Atoi(raw)
	}
	args = append(args, limit+1)
	records, e := s.DB.Pool.Query(q.R.Context(), `SELECT jsonb_build_object('id',id,'job_id',job_id,'attempt_no',attempt_no,'query_id',query_id,'query_version',query_version,'cluster_id',cluster_id,'tool_status',tool_status,'quality',quality,'time_start',time_start,'time_end',time_end,'created_at',created_at,'checksum',checksum) FROM evidence WHERE `+where+fmt.Sprintf(" ORDER BY created_at,id::text LIMIT $%d", len(args)), args...)
	if e != nil {
		return e
	}
	defer records.Close()
	items := []Object{}
	for records.Next() {
		var b []byte
		var v Object
		if e = records.Scan(&b); e != nil {
			return e
		}
		if e = json.Unmarshal(b, &v); e != nil {
			return e
		}
		cleanTrace(v)
		items = append(items, v)
	}
	if e = records.Err(); e != nil {
		return e
	}
	var next any
	if len(items) > limit {
		last := items[limit-1]
		b, _ := json.Marshal(cursor{String(last, "created_at"), String(last, "id"), filter})
		next = base64.RawURLEncoding.EncodeToString(b)
		items = items[:limit]
	}
	s.write(w, q.ID, 200, Object{"items": items, "next_cursor": next, "order": "stored_at_asc", "attempt_no": attempt})
	return nil
}
