package api

import (
	"bytes"
	"context"
	"encoding/json"
	"github.com/jackc/pgx/v5"
	. "gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/internal/store"
	"io"
	"net/http"
	"net/url"
	"sort"
	"time"
)

func (s *Server) internal(ctx context.Context, module, method, path string, body Object, headers http.Header) (Object, int, error) {
	base := s.Config.Modules[module]
	if base == "" {
		return nil, 0, Fail(503, "dependency_unavailable", "담당 모듈이 연결되지 않았습니다.")
	}
	data, _ := json.Marshal(body)
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	req, e := http.NewRequestWithContext(ctx, method, base+"/internal/v1"+path, bytes.NewReader(data))
	if e != nil {
		return nil, 0, e
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-DSX-Contract-Version", "1.3")
	for _, k := range []string{"If-Match", "Idempotency-Key", "X-Request-ID"} {
		if v := headers.Get(k); v != "" {
			req.Header.Set(k, v)
		}
	}
	resp, e := s.Client.Do(req)
	if e != nil {
		return nil, 0, Fail(503, "dependency_unavailable", "접수 응답을 확인할 수 없습니다. 같은 키로 재시도해 주세요.")
	}
	defer resp.Body.Close()
	data, e = io.ReadAll(io.LimitReader(resp.Body, 8*1024*1024+1))
	if e != nil || len(data) > 8*1024*1024 {
		return nil, 0, Fail(503, "invalid_dependency_response", "응답을 확인할 수 없습니다.")
	}
	var out Object
	if json.Unmarshal(data, &out) != nil || out == nil {
		return nil, 0, Fail(503, "invalid_dependency_response", "응답 형식이 올바르지 않습니다.")
	}
	if resp.StatusCode >= 300 {
		status := resp.StatusCode
		if status != 404 && status != 409 && status != 422 {
			status = 503
		}
		code := "dependency_unavailable"
		message := "담당 모듈에서 요청을 완료하지 못했습니다."
		if status != 503 {
			if obj, ok := out["error"].(map[string]any); ok {
				code = String(obj, "code")
				message = String(obj, "message")
			}
		}
		return nil, status, Fail(status, code, message)
	}
	sanitize(out)
	return out, resp.StatusCode, nil
}
func (s *Server) forward(w http.ResponseWriter, q *Request, module, path string) error {
	body := Object{"contract_version": "1.3", "source_module": "backend", "input": q.Body}
	out, status, e := s.internal(q.R.Context(), module, q.R.Method, path, body, q.R.Header)
	if e != nil {
		return e
	}
	s.write(w, q.ID, status, out)
	return nil
}
func sanitize(v any) {
	switch m := v.(type) {
	case map[string]any:
		for _, k := range []string{"secret", "api_key", "password", "access_token", "worker_id", "worker_address", "boot_id", "claim_token", "stack", "checkpoint_refs", "internal_url", "delegation", "config_snapshot", "request_hash", "idempotency_key", "object_key"} {
			delete(m, k)
		}
		for _, v := range m {
			sanitize(v)
		}
	case []any:
		for _, v := range m {
			sanitize(v)
		}
	}
}
func (s *Server) envelope(input Object, source string, now time.Time) Object {
	revision := s.Config.ExecutionRevision
	topics, _ := Decode[[]string](input["topic_ids"])
	groups := ReportTopicGroups(input, "O08")
	if Has(topics, "O08") && Has(groups, "namespace") && len(groups) <= 2 && (len(groups) == 1 || Has(groups, "cluster")) {
		revision = s.Config.NamespaceReportRevision
		if revision == "" {
			revision = "report-namespace-v1"
		}
	}
	return Object{"contract_version": "1.3", "source_module": "backend", "source_key": source, "kind": "report", "input": input, "deadline_at": now.Add(s.Config.JobDeadline).UTC().Format(time.RFC3339Nano), "execution_profile_revision": revision}
}
func (s *Server) submitReport(w http.ResponseWriter, q *Request) error {
	if e := s.validateWork(q, "reports"); e != nil {
		return e
	}
	topics, _ := Decode[[]string](q.Body["topic_ids"])
	sort.Strings(topics)
	q.Body["topic_ids"] = topics
	source := "manual:" + q.R.Header.Get("Idempotency-Key")
	hash := Hash(q.Body)
	var envelope Object
	// Persist the original deadline/profile before calling JC so response loss never changes the submission.
	e := s.DB.Transaction(q.R.Context(), func(tx pgx.Tx) error {
		var old string
		e := tx.QueryRow(q.R.Context(), "SELECT request_hash,envelope FROM manual_report_intents WHERE source_key=$1", source).Scan(&old, &envelope)
		if e == nil {
			if old != hash {
				return Fail(409, "idempotency_conflict", "같은 키의 보고서 조건이 다릅니다.")
			}
			return nil
		}
		if e != pgx.ErrNoRows {
			return e
		}
		envelope = s.envelope(q.Body, source, time.Now())
		_, e = tx.Exec(q.R.Context(), "INSERT INTO manual_report_intents(source_key,request_hash,envelope) VALUES($1,$2,$3)", source, hash, envelope)
		return e
	})
	if e != nil {
		return e
	}
	result, status, e := s.internal(q.R.Context(), "job_controller", "POST", "/jobs/report", envelope, q.R.Header)
	if e != nil {
		return e
	}
	if status != 202 || String(result, "job_id") == "" || String(result, "kind") != "report" {
		return Fail(503, "invalid_receipt", "JC 영속 접수를 확인할 수 없습니다.")
	}
	id := String(result, "job_id")
	s.write(w, q.ID, 202, Object{"job_id": id, "report_id": id, "status": result["status"], "status_url": "/api/v1/jobs/" + id})
	return nil
}
func (s *Server) receipt(ctx context.Context, source string) (Object, int, error) {
	return s.internal(ctx, "job_controller", "GET", "/receipts/backend/"+url.PathEscape(source), nil, nil)
}
func (s *Server) status(w http.ResponseWriter, q *Request) error {
	items := []any{}
	for _, m := range []string{"job_controller", "incident"} {
		state := "unavailable"
		_, status, e := s.internal(q.R.Context(), m, "GET", "/health/ready", nil, nil)
		if e == nil && status == 200 {
			state = "available"
		}
		items = append(items, Object{"module": m, "status": state})
	}
	queue, _, err := s.internal(q.R.Context(), "job_controller", "GET", "/queue-status", nil, nil)
	queueState := "available"
	if err != nil {
		queue = nil
		queueState = "unavailable"
	}
	var pending int
	if e := s.DB.Pool.QueryRow(q.R.Context(), "SELECT count(*) FROM enqueue_outbox WHERE source_module='backend' AND status='pending'").Scan(&pending); e != nil {
		return e
	}
	s.write(w, q.ID, 200, Object{"items": items, "database": "available", "queue": queue, "queue_status": queueState, "scheduler": Object{"enabled": s.Config.SchedulerEnabled, "pending": pending}, "capacity_read_only": true})
	return nil
}
func (s *Server) incidents(w http.ResponseWriter, q *Request, parts []string) error {
	if q.R.Method == "GET" {
		if len(parts) == 1 {
			if e := onlyQuery(q, "scope", "status", "from", "to", "limit", "cursor", "sort"); e != nil {
				return e
			}
			sc, e := s.listScope(q)
			if e != nil {
				return e
			}
			v := q.R.URL.Query()
			return s.page(w, q, "incidents", "dsx_scope_contains($1,scope) AND ($2='' OR COALESCE(state,status)=$2) AND ($3='' OR COALESCE(occurred_at,first_seen)>=NULLIF($3,'')::timestamptz) AND ($4='' OR COALESCE(occurred_at,first_seen)<NULLIF($4,'')::timestamptz)", []any{sc, v.Get("status"), v.Get("from"), v.Get("to")}, nil)
		}
		if len(parts) == 2 {
			v, e := s.resource(q, "incidents", parts[1], false)
			if e != nil {
				return e
			}
			refs, e := store.One(q.R.Context(), s.DB.Pool, "SELECT jsonb_build_object('items',COALESCE(jsonb_agg(jsonb_build_object('job_id',id,'status',status) ORDER BY created_at DESC),'[]')) FROM jobs WHERE kind='rca' AND incident_id::text=$1", parts[1])
			if e != nil {
				return e
			}
			v["analyses"] = refs["items"]
			sanitize(v)
			s.write(w, q.ID, 200, v)
			return nil
		}
	}
	if q.R.Method == "PATCH" && len(parts) == 2 {
		if e := only(q.Body, "memo", "review_status", "state"); e != nil {
			return e
		}
		if len(q.Body) == 0 {
			return Invalid("body")
		}
		if _, ok := q.Body["memo"]; ok {
			if _, ok := q.Body["memo"].(string); !ok {
				return Invalid("memo")
			}
		}
		if v, ok := q.Body["review_status"]; ok {
			if !Has([]string{"unreviewed", "reviewing", "reviewed"}, String(Object{"v": v}, "v")) {
				return Invalid("review_status")
			}
		}
		if _, exists := q.Body["state"]; exists && !Has([]string{"open", "acknowledged", "closed"}, String(q.Body, "state")) {
			return Invalid("state")
		}
		if q.R.Header.Get("If-Match") == "" {
			return Invalid("If-Match")
		}
		return s.forward(w, q, "incident", "/incidents/"+url.PathEscape(parts[1]))
	}
	return Fail(404, "not_found", "등록되지 않은 사건 API입니다.")
}
