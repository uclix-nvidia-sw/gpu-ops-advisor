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
)

type cursor struct {
	At     string `json:"at"`
	ID     string `json:"id"`
	Filter string `json:"filter"`
}

func validateList(q *Request) error {
	values := q.R.URL.Query()
	if v := values.Get("limit"); v != "" {
		n, e := strconv.Atoi(v)
		if e != nil || n < 1 || n > 200 {
			return Invalid("limit")
		}
	}
	for _, field := range []string{"from", "to"} {
		if v := values.Get(field); v != "" {
			if _, e := time.Parse(time.RFC3339Nano, v); e != nil {
				return Invalid(field)
			}
		}
	}
	if values.Get("from") != "" && values.Get("to") != "" {
		a, _ := time.Parse(time.RFC3339Nano, values.Get("from"))
		b, _ := time.Parse(time.RFC3339Nano, values.Get("to"))
		if !a.Before(b) {
			return Invalid("from/to")
		}
	}
	if v := values.Get("sort"); v != "" && v != "created_at_desc" {
		return Invalid("sort")
	}
	return nil
}
func (s *Server) list(w http.ResponseWriter, q *Request, kind string) error {
	if e := validateList(q); e != nil {
		return e
	}
	scope, e := s.listScope(q)
	if e != nil {
		return e
	}
	values := q.R.URL.Query()
	if e = onlyQuery(q, "scope", "kind", "status", "from", "to", "cursor", "limit", "sort", "target", "topic_id", "incident_id"); e != nil {
		return e
	}
	want := values.Get("kind")
	if kind == "analyses" {
		want = "rca"
	}
	if kind == "reports" {
		want = "report"
	}
	if want != "" && !Has([]string{"rca", "report"}, want) {
		return Invalid("kind")
	}
	status := values.Get("status")
	if status != "" && !Has([]string{"queued", "running", "retry_wait", "succeeded", "failed", "cancelled", "expired"}, status) {
		return Invalid("status")
	}
	filter := Hash(Object{"scope": scope, "kind": want, "status": status, "from": values.Get("from"), "to": values.Get("to"), "target": values.Get("target"), "topic_id": values.Get("topic_id"), "incident_id": values.Get("incident_id"), "sort": values.Get("sort")})
	args := []any{scope}
	where := "dsx_scope_contains($1,scope)"
	add := func(clause string, v any) { args = append(args, v); where += " AND " + fmt.Sprintf(clause, len(args)) }
	if want != "" {
		add("kind=$%d", want)
	}
	if id := values.Get("incident_id"); id != "" {
		add("incident_id::text=$%d", id)
	}
	if status != "" {
		add("status=$%d", status)
	}
	if v := values.Get("from"); v != "" {
		add("created_at >= $%d::timestamptz", v)
	}
	if v := values.Get("to"); v != "" {
		add("created_at < $%d::timestamptz", v)
	}
	if v := values.Get("target"); v != "" {
		var target Object
		if json.Unmarshal([]byte(v), &target) != nil {
			return Invalid("target")
		}
		at := time.Now().UTC()
		if raw := values.Get("from"); raw != "" {
			at, _ = time.Parse(time.RFC3339Nano, raw)
		}
		if e = s.target(q, scope, target, at); e != nil {
			return e
		}
		add("input_snapshot->'target' @> $%d::jsonb", target)
	}
	if v := values.Get("topic_id"); v != "" {
		add("input_snapshot->'topic_ids' ? $%d", v)
	}
	if raw := values.Get("cursor"); raw != "" {
		var c cursor
		b, e := base64.RawURLEncoding.DecodeString(raw)
		if e != nil || json.Unmarshal(b, &c) != nil || c.Filter != filter {
			return Invalid("cursor")
		}
		if _, e = time.Parse(time.RFC3339Nano, c.At); e != nil || c.ID == "" {
			return Invalid("cursor")
		}
		args = append(args, c.At, c.ID)
		where += fmt.Sprintf(" AND (created_at,id::text)<($%d::timestamptz,$%d)", len(args)-1, len(args))
	}
	limit := 50
	if v := values.Get("limit"); v != "" {
		limit, _ = strconv.Atoi(v)
	}
	args = append(args, limit+1)
	rows, e := s.DB.Pool.Query(q.R.Context(), "SELECT to_jsonb(j) FROM jobs j WHERE "+where+fmt.Sprintf(" ORDER BY created_at DESC,id DESC LIMIT $%d", len(args)), args...)
	if e != nil {
		return e
	}
	defer rows.Close()
	rawItems := []Object{}
	for rows.Next() {
		var b []byte
		if e = rows.Scan(&b); e != nil {
			return e
		}
		var v Object
		if e = json.Unmarshal(b, &v); e != nil {
			return e
		}
		rawItems = append(rawItems, v)
	}
	if e = rows.Err(); e != nil {
		return e
	}
	var next any
	if len(rawItems) > limit {
		last := rawItems[limit-1]
		b, _ := json.Marshal(cursor{String(last, "created_at"), String(last, "id"), filter})
		next = base64.RawURLEncoding.EncodeToString(b)
		rawItems = rawItems[:limit]
	}
	items := []Object{}
	for _, v := range rawItems {
		dto, e := s.jobDTO(q, v, false)
		if e != nil {
			return e
		}
		items = append(items, dto)
	}
	s.write(w, q.ID, 200, Object{"items": items, "next_cursor": next})
	return nil
}
func onlyQuery(q *Request, keys ...string) error {
	for k, v := range q.R.URL.Query() {
		if !Has(keys, k) || len(v) != 1 {
			return Invalid(k)
		}
	}
	return nil
}
func (s *Server) jobDTO(q *Request, v Object, detail bool) (Object, error) {
	out := Object{}
	if String(v, "kind") == "report" {
		out["report_origin"] = "unknown"
		prefix, key, ok := strings.Cut(String(v, "source_key"), ":")
		if String(v, "source_module") == "backend" && ok && key != "" && (prefix == "manual" || prefix == "schedule") {
			out["report_origin"] = prefix
		}
	}
	for _, k := range []string{"id", "kind", "status", "stage", "attempt_no", "created_at", "started_at", "deadline_at", "queue_reason", "cancel_requested_at", "termination_reason", "version", "parent_job_id", "scope"} {
		out[k] = v[k]
	}
	if input, ok := v["input_snapshot"].(map[string]any); ok {
		for _, k := range []string{"target", "time_range", "timezone", "topic_ids", "purpose_ids", "group_by", "comparison_range", "incident_id", "symptom"} {
			if x, ok := input[k]; ok {
				out[k] = x
			}
		}
	}
	deadline, _ := time.Parse(time.RFC3339Nano, String(v, "deadline_at"))
	remaining := time.Now().Before(deadline) && String(v, "kind") == "report"
	out["can_cancel"] = remaining && Has([]string{"queued", "running", "retry_wait"}, String(v, "status")) && v["cancel_requested_at"] == nil
	versions, _ := v["versions"].(map[string]any)
	execution, _ := versions["execution"].(map[string]any)
	attemptBudget := Number(execution, "attempt_budget")
	out["can_retry"] = remaining && String(v, "status") == "failed" && v["retryable"] == true && attemptBudget > 0 && Number(v, "attempt_no") < Number(v, "max_attempts") && Number(v, "budget_used")+attemptBudget <= Number(v, "token_budget") && Has([]string{"transient_error", "dependency_unavailable", "timeout"}, String(v, "termination_reason"))
	out["result_ref"] = nil
	out["result_status"] = "unpublished"
	out["narrative_status"] = nil
	if id := String(v, "published_result_id"); id != "" {
		result, e := store.One(q.R.Context(), s.DB.Pool, "SELECT to_jsonb(c) FROM result_candidates c WHERE id::text=$1 AND job_id::text=$2 AND kind=$3", id, String(v, "id"), String(v, "kind"))
		if e != nil {
			return nil, e
		}
		body, _ := result["body"].(map[string]any)
		out["result_ref"] = id
		out["result_status"] = body["result_status"]
		out["narrative_status"] = body["narrative_status"]
		if detail {
			sanitize(body)
			out["result"] = body
		}
	}
	if detail {
		result, e := store.One(q.R.Context(), s.DB.Pool, "SELECT jsonb_build_object('items',COALESCE(jsonb_agg(jsonb_build_object('attempt_no',attempt_no,'started_at',started_at,'ended_at',ended_at,'stage',stage,'termination_reason',termination_reason) ORDER BY attempt_no),'[]')) FROM job_attempts WHERE job_id::text=$1", String(v, "id"))
		if e != nil {
			return nil, e
		}
		out["attempts"] = result["items"]
	}
	return out, nil
}
func (s *Server) observation(w http.ResponseWriter, q *Request, kind string) error {
	if e := only(q.Body, "scope", "time_range", "timezone", "target", "at", "query_id", "parameters"); e != nil {
		return e
	}
	period := q.Body["time_range"] != nil
	if kind != "mappings" && !period {
		return Invalid("time_range")
	}
	scope, e := s.common(q, q.Body, false, period)
	if e != nil {
		return e
	}
	at := time.Now().UTC()
	if v := String(q.Body, "at"); v != "" {
		if period {
			return Invalid("at_or_time_range")
		}
		at, e = time.Parse(time.RFC3339Nano, v)
		if e != nil {
			return Invalid("at")
		}
	} else if kind == "mappings" && !period {
		return Invalid("at_or_time_range")
	}
	if period {
		tr := q.Body["time_range"].(map[string]any)
		at, _ = time.Parse(time.RFC3339Nano, String(tr, "start"))
	}
	if q.Body["target"] != nil {
		if e = s.target(q, scope, q.Body["target"], at); e != nil {
			return e
		}
	} else if kind == "mappings" {
		return Invalid("target")
	}
	if kind == "observations" {
		id := String(q.Body, "query_id")
		if !Has([]string{"gpu_utilization", "gpu_memory", "node_metrics", "pod_status", "resource_catalog", "collection_quality", "logs"}, id) {
			return Invalid("query_id")
		}
		params, _ := q.Body["parameters"].(map[string]any)
		if q.Body["parameters"] != nil && params == nil {
			return Invalid("parameters")
		}
		if e = only(params, "limit"); e != nil {
			return e
		}
		if raw, ok := params["limit"]; ok {
			n, valid := raw.(float64)
			if !valid || n != float64(int(n)) || n < 1 || n > float64(Number(q.Limits, "max_log_lines")) {
				return Invalid("parameters.limit")
			}
		}
		tr := q.Body["time_range"].(map[string]any)
		rows, e := s.DB.Pool.Query(q.R.Context(), "SELECT to_jsonb(e) FROM evidence e WHERE query_id=$1 AND dsx_scope_contains($2,scope) AND time_start >= $3::timestamptz AND time_end <= $4::timestamptz AND ($5::jsonb IS NULL OR input->'target' @> $5::jsonb) ORDER BY created_at DESC LIMIT 50", id, scope, tr["start"], tr["end"], q.Body["target"])
		if e != nil {
			return e
		}
		defer rows.Close()
		items := []any{}
		refs := []string{}
		tool := "unavailable"
		statuses := map[string]bool{}
		for rows.Next() {
			var b []byte
			if e = rows.Scan(&b); e != nil {
				return e
			}
			var v Object
			_ = json.Unmarshal(b, &v)
			items = append(items, Object{"snapshot": v["snapshot"], "tool_status": v["tool_status"], "quality": v["quality"], "time_start": v["time_start"], "time_end": v["time_end"]})
			refs = append(refs, String(v, "id"))
			statuses[String(v, "tool_status")] = true
		}
		if e = rows.Err(); e != nil {
			return e
		}
		if len(statuses) == 1 {
			for state := range statuses {
				tool = state
			}
		} else if len(statuses) > 1 {
			tool = "partial"
		}
		s.write(w, q.ID, 200, Object{"query_id": id, "tool_status": tool, "items": items, "evidence_refs": refs, "quality": Object{"source": "stored_snapshot", "live_query_configured": false, "reason": "only_verified_stored_snapshots_available"}})
		return nil
	}
	if kind == "mappings" {
		t := q.Body["target"].(map[string]any)
		args := []any{scope, String(t, "cluster_id"), String(t, "gpu_uuid"), String(t, "pod_uid"), at, String(t, "namespace"), String(t, "pod_name")}
		condition := "a.observed_at<=$5::timestamptz"
		if period {
			tr := q.Body["time_range"].(map[string]any)
			args = append(args, tr["end"])
			condition = "a.observed_at>=$5::timestamptz AND a.observed_at<$8::timestamptz"
		}
		rows, e := s.DB.Pool.Query(q.R.Context(), "SELECT to_jsonb(a) FROM allocation_observations a JOIN collection_observations c ON c.id=a.collection_id WHERE dsx_scope_contains($1,c.scope) AND a.cluster_id=$2 AND ($3='' OR a.gpu_uuid=$3) AND ($4='' OR a.pod_uid=$4) AND ($6='' OR a.namespace=$6) AND ($7='' OR a.pod_name=$7) AND "+condition+" ORDER BY a.observed_at DESC LIMIT 200", args...)
		if e != nil {
			return e
		}
		defer rows.Close()
		items := []any{}
		for rows.Next() {
			var b []byte
			if e = rows.Scan(&b); e != nil {
				return e
			}
			var v Object
			_ = json.Unmarshal(b, &v)
			delete(v, "raw_labels")
			items = append(items, v)
		}
		if e = rows.Err(); e != nil {
			return e
		}
		tool := "partial"
		if len(items) == 0 {
			tool = "unavailable"
		}
		s.write(w, q.ID, 200, Object{"items": items, "tool_status": tool, "relation_status": "unknown", "quality": Object{"complete": false, "reason": "observed_snapshots_only"}})
		return nil
	}
	tr := q.Body["time_range"].(map[string]any)
	var count int
	e = s.DB.Pool.QueryRow(q.R.Context(), "SELECT count(*) FROM incidents WHERE dsx_scope_contains($1,scope) AND COALESCE(occurred_at,first_seen) >= $2::timestamptz AND COALESCE(occurred_at,first_seen) < $3::timestamptz", scope, tr["start"], tr["end"]).Scan(&count)
	if e != nil {
		return e
	}
	summary, e := store.One(q.R.Context(), s.DB.Pool, "SELECT jsonb_build_object('total',count(*),'queued',count(*) FILTER(WHERE status IN ('queued','retry_wait')),'running',count(*) FILTER(WHERE status='running')) FROM jobs WHERE dsx_scope_contains($1,scope) AND created_at >= $2::timestamptz AND created_at < $3::timestamptz", scope, tr["start"], tr["end"])
	if e != nil {
		return e
	}
	s.write(w, q.ID, 200, Object{"scope": scope, "time_range": q.Body["time_range"], "tool_status": "partial", "incident_count": count, "jobs": summary, "allocation_summary": nil, "quality": Object{"status": "unavailable", "reason": "live_observation_not_configured"}, "evidence_refs": []string{}})
	return nil
}
