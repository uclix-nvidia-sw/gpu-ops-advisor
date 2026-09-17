package api

import (
	"encoding/json"
	. "gpu-ops-advisor/backend/internal/contract"
	"net/http"
	"time"
)

func (s *Server) observationGET(w http.ResponseWriter, q *Request, kind string) error {
	if e := onlyQuery(q, "scope", "target", "at", "time_range", "from", "to", "timezone", "kind", "cluster", "namespace", "limit", "cursor", "sort"); e != nil {
		return e
	}
	sc, e := s.listScope(q)
	if e != nil {
		return e
	}
	v := q.R.URL.Query()
	at := time.Now().UTC()
	var end any
	if raw := v.Get("at"); raw != "" {
		at, e = time.Parse(time.RFC3339Nano, raw)
		if e != nil {
			return Invalid("at")
		}
	}
	var tr Object
	if raw := v.Get("time_range"); raw != "" {
		if json.Unmarshal([]byte(raw), &tr) != nil {
			return Invalid("time_range")
		}
	} else if v.Get("from") != "" || v.Get("to") != "" {
		tr = Object{"start": v.Get("from"), "end": v.Get("to")}
	}
	if tr != nil {
		if v.Get("at") != "" {
			return Invalid("at_or_period")
		}
		if e = TimeRange(tr, time.Duration(Number(q.Limits, "max_query_days"))*24*time.Hour); e != nil {
			return e
		}
		at, _ = time.Parse(time.RFC3339Nano, String(tr, "start"))
		end = tr["end"]
	}
	var target Object
	if raw := v.Get("target"); raw != "" {
		if json.Unmarshal([]byte(raw), &target) != nil {
			return Invalid("target")
		}
		if e = s.target(q, sc, target, at); e != nil {
			return e
		}
	}
	if kind == "dashboard" {
		if tr == nil {
			return Invalid("time_range")
		}
		q.Body = Object{"scope": scopeObject(sc), "time_range": tr, "timezone": v.Get("timezone")}
		if target != nil {
			q.Body["target"] = target
		}
		return s.observation(w, q, "dashboard")
	}
	if kind == "observation-quality" {
		return s.page(w, q, "(SELECT c.*,evaluated_at AS created_at FROM collection_observations c)", "dsx_scope_contains($1,scope) AND (($3::timestamptz IS NULL AND evaluated_at<=$2) OR ($3::timestamptz IS NOT NULL AND evaluated_at>=$2 AND evaluated_at<$3))", []any{sc, at, end}, nil)
	}
	assetKind := v.Get("kind")
	if kind == "workloads" {
		assetKind = "pod"
	}
	if assetKind != "" && !Has([]string{"pod", "node", "gpu", "workload"}, assetKind) {
		return Invalid("kind")
	}
	cluster := v.Get("cluster")
	namespace := v.Get("namespace")
	if cluster != "" {
		filtered := Scope{Clusters: []ClusterScope{{ClusterID: cluster}}}
		if namespace != "" {
			filtered.Clusters[0].Namespaces = []string{namespace}
		}
		found := false
		for _, c := range sc.Clusters {
			if c.ClusterID == cluster {
				found = true
				if namespace != "" && c.Namespaces != nil && !Has(c.Namespaces, namespace) {
					return Invalid("namespace")
				}
				if namespace == "" {
					filtered.Clusters[0].Namespaces = c.Namespaces
				}
			}
		}
		if !found {
			return Invalid("cluster")
		}
		sc = filtered
	}
	predicate := `EXISTS(SELECT 1 FROM jsonb_array_elements($1::jsonb->'clusters') c WHERE c->>'cluster_id'=cluster_id AND (c->'namespaces'='null'::jsonb OR c->'namespaces' ? (attributes->>'namespace'))) AND ($2='' OR subject_kind=$2) AND valid_from<COALESCE($4::timestamptz,$3::timestamptz+interval '1 microsecond') AND (valid_to IS NULL OR valid_to>$3) AND ($5::jsonb IS NULL OR (cluster_id=$5->>'cluster_id' AND subject_kind=$5->>'kind' AND (subject_key=COALESCE($5->>'pod_uid',$5->>'gpu_uuid',$5->>'node_uid',$5->>'node') OR attributes->>'pod_name'=$5->>'pod_name')))`
	return s.page(w, q, "identity_history", predicate, []any{sc, assetKind, at, end, target}, nil)
}
func scopeObject(sc Scope) Object { v, _ := Decode[Object](sc); return v }
