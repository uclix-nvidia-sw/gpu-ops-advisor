package api

import (
	"encoding/json"
	. "gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/internal/store"
	"time"
)

func (s *Server) scope(q *Request, v any, write bool) (Scope, error) {
	scope, e := ParseScope(v)
	if e != nil {
		return scope, e
	}
	for _, c := range scope.Clusters {
		var exists bool
		if e = s.DB.Pool.QueryRow(q.R.Context(), "SELECT EXISTS(SELECT 1 FROM cluster_registry WHERE id=$1 AND enabled)", c.ClusterID).Scan(&exists); e != nil {
			return scope, e
		}
		if !exists {
			return scope, Invalid("scope.cluster_id")
		}
	}
	return scope, nil
}
func (s *Server) listScope(q *Request) (Scope, error) {
	raw := q.R.URL.Query().Get("scope")
	if raw == "" {
		return s.registeredScope(q)
	}
	var v any
	if json.Unmarshal([]byte(raw), &v) != nil {
		return Scope{}, Invalid("scope")
	}
	return s.scope(q, v, false)
}
func (s *Server) common(q *Request, b Object, write, period bool) (Scope, error) {
	scope, e := s.scope(q, b["scope"], write)
	if e != nil {
		return scope, e
	}
	b["scope"] = scope
	if period {
		if e = TimeRange(b["time_range"], time.Duration(Number(q.Limits, "max_query_days"))*24*time.Hour); e != nil {
			return scope, e
		}
		tz := String(b, "timezone")
		if tz != "" {
			if _, e = time.LoadLocation(tz); e != nil {
				return scope, Invalid("timezone")
			}
		}
	}
	return scope, nil
}
func (s *Server) target(q *Request, scope Scope, raw any, at time.Time) error {
	t, ok := raw.(map[string]any)
	if !ok {
		return Invalid("target")
	}
	if e := only(t, "kind", "cluster_id", "node_uid", "node", "gpu_uuid", "pod_uid", "namespace", "pod_name"); e != nil {
		return e
	}
	kind, cluster := String(t, "kind"), String(t, "cluster_id")
	if !Has([]string{"pod", "gpu", "node"}, kind) || cluster == "" {
		return Invalid("target")
	}
	ns := String(t, "namespace")
	targetScope := Scope{Clusters: []ClusterScope{{ClusterID: cluster}}}
	if kind == "pod" {
		if ns == "" || String(t, "pod_uid") == "" && String(t, "pod_name") == "" {
			return Invalid("target.pod")
		}
		targetScope.Clusters[0].Namespaces = []string{ns}
	}
	if !Contains(scope, targetScope) && kind == "pod" {
		return Fail(422, "TARGET_SCOPE_MISMATCH", "대상이 요청 범위에 포함되지 않습니다.")
	}
	exists := false
	for _, c := range scope.Clusters {
		if c.ClusterID == cluster {
			exists = true
		}
	}
	if !exists {
		return Fail(422, "TARGET_SCOPE_MISMATCH", "대상이 요청 범위에 포함되지 않습니다.")
	}
	id := String(t, "pod_uid")
	if kind == "gpu" {
		id = String(t, "gpu_uuid")
	}
	if kind == "node" {
		id = String(t, "node_uid")
		if id == "" {
			id = String(t, "node")
		}
	}
	if id == "" {
		if kind != "pod" {
			return Invalid("target.identity")
		}
		id = String(t, "pod_name")
	}
	row, e := store.One(q.R.Context(), s.DB.Pool, "SELECT to_jsonb(t) FROM identity_history t WHERE cluster_id=$1 AND subject_kind=$2 AND (subject_key=$3 OR ($2='pod' AND attributes->>'pod_name'=$3)) AND valid_from<=$4 AND (valid_to IS NULL OR valid_to>$4) ORDER BY valid_from DESC LIMIT 1", cluster, kind, id, at)
	if e != nil {
		return Fail(422, "TARGET_IDENTITY_UNVERIFIED", "대상의 소속과 기준 시각을 확인할 수 없습니다.")
	}
	attrs, _ := row["attributes"].(map[string]any)
	if kind == "pod" && String(attrs, "namespace") != ns {
		return Fail(422, "TARGET_SCOPE_MISMATCH", "대상이 요청 범위에 포함되지 않습니다.")
	}
	// Validate every supplied stable identifier, including optional related assets.
	for field, relatedKind := range map[string]string{"gpu_uuid": "gpu", "node_uid": "node", "pod_uid": "pod"} {
		value := String(t, field)
		if value == "" || relatedKind == kind {
			continue
		}
		var verified bool
		e = s.DB.Pool.QueryRow(q.R.Context(), "SELECT EXISTS(SELECT 1 FROM identity_history WHERE cluster_id=$1 AND subject_kind=$2 AND subject_key=$3 AND valid_from<=$4 AND (valid_to IS NULL OR valid_to>$4) AND ($2<>'pod' OR attributes->>'namespace'=$5))", cluster, relatedKind, value, at, ns).Scan(&verified)
		if e != nil {
			return e
		}
		if !verified {
			return Fail(422, "RELATED_IDENTITY_UNVERIFIED", "함께 지정한 자산의 소속과 기준 시각을 확인할 수 없습니다.")
		}
	}
	return nil
}
func (s *Server) validateWork(q *Request, kind string) error {
	b := q.Body
	if e := only(b, "scope", "time_range", "timezone", "parent_job_id", "topic_ids", "group_by", "comparison_range", "action_record_ids", "resource_selectors"); e != nil {
		return e
	}
	scope, e := s.common(q, b, true, true)
	if e != nil {
		return e
	}
	if String(b, "timezone") == "" {
		return Invalid("timezone")
	}
	if e = enums(b, "topic_ids", []string{"O01", "O02", "O03", "O04", "O05", "O06", "O07", "O08", "O09", "O10", "O11"}, true); e != nil {
		return e
	}
	if e = enums(b, "group_by", []string{"cluster", "model", "node", "namespace", "pod", "workload"}, true); e != nil {
		return e
	}
	if b["comparison_range"] != nil {
		if e = TimeRange(b["comparison_range"], time.Duration(Number(q.Limits, "max_query_days"))*24*time.Hour); e != nil {
			return e
		}
	}
	for field, resource := range map[string]string{"parent_job_id": "jobs"} {
		if id := String(b, field); id != "" {
			v, e := s.resource(q, resource, id, false)
			if e != nil {
				return e
			}
			old, _ := Decode[Scope](v["scope"])
			if !Contains(scope, old) || !Contains(old, scope) {
				return Fail(422, "CONTEXT_SCOPE_MISMATCH", "참조와 요청 범위가 일치해야 합니다.")
			}
			if field == "parent_job_id" {
				want := "rca"
				if kind == "reports" {
					want = "report"
				}
				if String(v, "kind") != want {
					return Invalid(field)
				}
			}

		}
	}
	if refs, ok := b["action_record_ids"]; ok {
		ids, e := Decode[[]string](refs)
		if e != nil {
			return Invalid("action_record_ids")
		}
		for _, id := range ids {
			v, e := s.resource(q, "reviews", id, false)
			if e != nil {
				return e
			}
			old, _ := Decode[Scope](v["scope"])
			if String(v, "kind") != "action" || !Contains(scope, old) {
				return Invalid("action_record_ids")
			}
		}
	}
	if selectors, ok := b["resource_selectors"]; ok {
		items, e := Decode[[]Object](selectors)
		if e != nil {
			return Invalid("resource_selectors")
		}
		for _, item := range items {
			if e = only(item, "cluster_id", "resource_name", "unit"); e != nil {
				return e
			}
			registered := false
			for _, c := range scope.Clusters {
				if c.ClusterID == String(item, "cluster_id") {
					registered = true
				}
			}
			if !registered || String(item, "resource_name") == "" || String(item, "unit") == "" {
				return Invalid("resource_selectors")
			}
			var found bool
			e = s.DB.Pool.QueryRow(q.R.Context(), "SELECT EXISTS(SELECT 1 FROM evidence WHERE query_id='resource_catalog' AND tool_status='ok' AND dsx_scope_contains($1,scope) AND snapshot @> $2::jsonb)", scope, Object{"items": []any{item}}).Scan(&found)
			if e != nil {
				return e
			}
			if !found {
				return Fail(422, "RESOURCE_UNVERIFIED", "등록된 자원 이름과 단위가 필요합니다.")
			}
		}
	}
	return nil
}
func enums(b Object, key string, allowed []string, required bool) error {
	raw, ok := b[key]
	if !ok && !required {
		return nil
	}
	values, e := Decode[[]string](raw)
	if e != nil || required && len(values) == 0 {
		return Invalid(key)
	}
	seen := map[string]bool{}
	for _, v := range values {
		if !Has(allowed, v) || seen[v] {
			return Invalid(key)
		}
		seen[v] = true
	}
	return nil
}
func (s *Server) registeredScope(q *Request) (Scope, error) {
	out := Scope{Clusters: []ClusterScope{}}
	rows, e := s.DB.Pool.Query(q.R.Context(), "SELECT id FROM cluster_registry WHERE enabled ORDER BY id")
	if e != nil {
		return out, e
	}
	defer rows.Close()
	for rows.Next() {
		var id string
		if e = rows.Scan(&id); e != nil {
			return out, e
		}
		out.Clusters = append(out.Clusters, ClusterScope{ClusterID: id})
	}
	return out, rows.Err()
}
