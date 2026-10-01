package api

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/jackc/pgx/v5/pgconn"

	"gpu-ops-advisor/backend/internal/config"
	. "gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/internal/store"
)

type Server struct {
	DB              *store.Store
	Config          config.Config
	Client          *http.Client
	mu              sync.Mutex
	window          time.Time
	count, inflight int
}
type Request struct {
	R      *http.Request
	ID     string
	Body   Object
	Limits Object
}

func New(db *store.Store, c config.Config) *Server {
	if c.JobDeadline == 0 {
		c.JobDeadline = 48 * time.Hour
	}
	if c.DispatchWindow == 0 {
		c.DispatchWindow = 24 * time.Hour
	}
	if c.CatchupWindow == 0 {
		c.CatchupWindow = 7 * 24 * time.Hour
	}
	if c.MaxCatchup == 0 {
		c.MaxCatchup = 10
	}
	if c.ExecutionRevision == "" {
		c.ExecutionRevision = "local-v1"
	}
	return &Server{DB: db, Config: c, Client: &http.Client{Timeout: 10 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}}
}
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	id := ID()
	w.Header().Set("X-Request-ID", id)
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("Cache-Control", "no-store")
	defer func() {
		if recover() != nil {
			slog.Error("request panic", "request_id", id)
			s.writeError(w, id, Fail(500, "INTERNAL_ERROR", "요청 처리 중 오류가 발생했습니다."))
		}
		slog.Info("request", "method", r.Method, "path", r.URL.Path, "request_id", id, "duration_ms", time.Since(start).Milliseconds())
	}()
	if !strings.HasPrefix(r.URL.Path, "/api/v1/") {
		s.writeError(w, id, Fail(404, "NOT_FOUND", "경로를 찾을 수 없습니다."))
		return
	}
	path := strings.TrimPrefix(r.URL.Path, "/api/v1")
	if removed(path, r.Method) {
		s.writeError(w, id, Fail(404, "not_found", "v1.3에서 제공하지 않는 API입니다."))
		return
	}
	if path == "/health/live" || path == "/health/ready" {
		if r.Method != "GET" {
			s.writeError(w, id, Fail(405, "METHOD_NOT_ALLOWED", "허용되지 않은 메서드입니다."))
			return
		}
		if path == "/health/ready" {
			ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
			defer cancel()
			if e := s.readiness(ctx); e != nil {
				s.writeError(w, id, e)
				return
			}
		}
		s.write(w, id, 200, Object{"status": "ok", "authentication": "disabled"})
		return
	}
	req := &Request{R: r, ID: id, Body: Object{}}
	p, e := store.One(r.Context(), s.DB.Pool, "SELECT config FROM service_profiles WHERE kind='limits' AND name='C07' AND enabled")
	if e == nil {
		req.Limits = p
	} else {
		req.Limits = Object{}
	}
	mutating := r.Method != "GET" && r.Method != "HEAD"
	if mutating {
		for _, key := range []string{"max_body_bytes", "max_text_length", "max_requests_per_minute", "max_inflight_requests", "module_timeout_seconds"} {
			if Number(req.Limits, key) <= 0 {
				s.writeError(w, id, Fail(503, "LIMITS_NOT_CONFIGURED", "C07 양수 한도 설정이 필요합니다."))
				return
			}
		}
		s.mu.Lock()
		if time.Since(s.window) >= time.Minute {
			s.window = time.Now()
			s.count = 0
		}
		limited := s.count >= Number(req.Limits, "max_requests_per_minute") || s.inflight >= Number(req.Limits, "max_inflight_requests")
		if !limited {
			s.count++
			s.inflight++
		}
		s.mu.Unlock()
		if limited {
			w.Header().Set("Retry-After", "60")
			s.writeError(w, id, Fail(429, "RATE_LIMITED", "요청 한도를 초과했습니다."))
			return
		}
		defer func() { s.mu.Lock(); s.inflight--; s.mu.Unlock() }()
		if !strings.HasPrefix(path, "/webhooks/") {
			if !strings.HasPrefix(r.Header.Get("Content-Type"), "application/json") {
				s.writeError(w, id, Fail(415, "UNSUPPORTED_MEDIA_TYPE", "application/json 본문이 필요합니다."))
				return
			}
			r.Body = http.MaxBytesReader(w, r.Body, int64(Number(req.Limits, "max_body_bytes")))
			d := json.NewDecoder(r.Body)
			if e = d.Decode(&req.Body); e != nil {
				var tooBig *http.MaxBytesError
				if errors.As(e, &tooBig) {
					s.writeError(w, id, Fail(413, "BODY_TOO_LARGE", "요청 본문이 너무 큽니다."))
				} else {
					s.writeError(w, id, Fail(400, "INVALID_JSON", "JSON 객체가 필요합니다."))
				}
				return
			}
			if req.Body == nil {
				s.writeError(w, id, Invalid("body"))
				return
			}
			var trailing any
			if d.Decode(&trailing) != io.EOF {
				s.writeError(w, id, Fail(400, "INVALID_JSON", "단일 JSON 객체가 필요합니다."))
				return
			}
			if e = bounded(req.Body, Number(req.Limits, "max_text_length"), 0); e != nil {
				s.writeError(w, id, e)
				return
			}
		}
	}
	if e = s.dispatch(w, req, path); e != nil {
		s.writeError(w, id, e)
	}
}
func bounded(v any, max, depth int) error {
	if depth > 24 {
		return Invalid("body.depth")
	}
	switch x := v.(type) {
	case string:
		if len([]rune(x)) > max {
			return Invalid("text.length")
		}
	case []any:
		if len(x) > 1000 {
			return Invalid("array.length")
		}
		for _, v := range x {
			if e := bounded(v, max, depth+1); e != nil {
				return e
			}
		}
	case map[string]any:
		if len(x) > 100 {
			return Invalid("object.fields")
		}
		for _, v := range x {
			if e := bounded(v, max, depth+1); e != nil {
				return e
			}
		}
	}
	return nil
}
func (s *Server) write(w http.ResponseWriter, id string, status int, v Object) {
	v["request_id"] = id
	if version := Number(v, "version"); version > 0 {
		w.Header().Set("ETag", strconv.Quote(strconv.Itoa(version)))
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
func (s *Server) writeError(w http.ResponseWriter, id string, e error) {
	var p *Problem
	if !errors.As(e, &p) {
		var dbError *pgconn.PgError
		if errors.As(e, &dbError) {
			switch dbError.Code {
			case "23505":
				p = Fail(409, "RESOURCE_CONFLICT", "동일한 리소스 또는 키가 이미 존재합니다.")
			case "23503", "23514", "22P02":
				p = Invalid("resource")
			}
		}
	}
	if p == nil {
		slog.Error("storage or dependency failure", "request_id", id, "error_type", strings.SplitN(e.Error(), ":", 2)[0])
		p = Fail(503, "STORAGE_UNAVAILABLE", "저장소 또는 의존 서비스가 준비되지 않았습니다.")
	}
	s.write(w, id, p.Status, Object{"error": p})
}
func (s *Server) route(w http.ResponseWriter, q *Request, path string) error {
	r := q.R
	parts := strings.Split(strings.Trim(path, "/"), "/")
	kind := parts[0]
	if kind == "models" || kind == "model-routes" || kind == "settings" {
		return s.profiles(w, q, parts)
	}
	if kind == "knowledge" {
		return s.knowledge(w, q, parts)
	}
	if kind == "reviews" {
		return s.reviews(w, q, parts)
	}
	if kind == "schedules" {
		return s.schedules(w, q, parts)
	}
	if kind == "incidents" {
		return s.incidents(w, q, parts)
	}
	if path == "/procedures" && r.Method == "GET" {
		return s.page(w, q, "procedures", "true", nil, nil)
	}
	if path == "/service-status" && r.Method == "GET" {
		return s.status(w, q)
	}
	if path == "/clusters" && r.Method == "POST" {
		return s.registerCluster(w, q)
	}
	if path == "/clusters" && r.Method == "GET" {
		sc, e := s.registeredScope(q)
		if e != nil {
			return e
		}
		items := []any{}
		for _, c := range sc.Clusters {
			items = append(items, Object{"id": c.ClusterID, "cluster_id": c.ClusterID, "namespaces": nil, "collection_status": "unknown"})
		}
		s.write(w, q.ID, 200, Object{"items": items, "next_cursor": nil})
		return nil
	}
	if len(parts) == 1 && r.Method == "GET" && Has([]string{"dashboard", "assets", "workloads", "observation-quality"}, kind) {
		return s.observationGET(w, q, kind)
	}
	// Read-only compatibility aliases for the existing UI; they cannot enqueue work.
	if len(parts) == 2 && parts[1] == "query" && r.Method == "POST" && Has([]string{"dashboard", "observations", "mappings"}, kind) {
		return s.observation(w, q, kind)
	}
	if path == "/reports" && r.Method == "POST" {
		return s.submitReport(w, q)
	}
	if kind == "jobs" && len(parts) == 3 && r.Method == "POST" && Has([]string{"cancel", "retry"}, parts[2]) {
		if e := only(q.Body, "reason"); e != nil {
			return e
		}
		if String(q.Body, "reason") == "" {
			return Invalid("reason")
		}
		job, e := s.resource(q, "jobs", parts[1], false)
		if e != nil {
			return e
		}
		if String(job, "kind") != "report" {
			return Fail(409, "kind_not_allowed", "RCA 명령은 Incident에서만 처리합니다.")
		}
		if r.Header.Get("If-Match") == "" {
			return Invalid("If-Match")
		}
		return s.forward(w, q, "job_controller", path)
	}
	if kind == "jobs" && r.Method == "GET" && len(parts) >= 3 {
		if len(parts) == 3 && parts[2] == "trace" {
			return s.jobTrace(w, q, parts[1])
		}
		if parts[2] == "evidence" && (len(parts) == 3 || len(parts) == 4) {
			return s.jobEvidence(w, q, parts[1], parts[3:])
		}
	}
	if kind == "reports" && len(parts) == 3 && parts[2] == "export" && r.Method == "GET" {
		return s.exportReport(w, q, parts[1])
	}
	if r.Method == "GET" && Has([]string{"jobs", "analyses", "reports", "evidence"}, kind) {
		if len(parts) == 1 && kind != "evidence" {
			return s.list(w, q, kind)
		}
		if len(parts) == 2 {
			v, e := s.resource(q, kind, parts[1], false)
			if e != nil {
				return e
			}
			if kind != "evidence" {
				v, e = s.jobDTO(q, v, true)
				if e != nil {
					return e
				}
			} else {
				delete(v, "object_key")
				delete(v, "input")
				sanitize(v)
				v["raw_access_available"] = v["snapshot"] != nil
			}
			s.write(w, q.ID, 200, v)
			return nil
		}
	}
	return Fail(404, "not_found", "등록되지 않은 API입니다.")
}
func only(m Object, fields ...string) error {
	for k := range m {
		if !Has(fields, k) {
			return Invalid(k)
		}
	}
	return nil
}
func key(q *Request) error {
	k := q.R.Header.Get("Idempotency-Key")
	if len(k) < 1 || len(k) > 200 || strings.TrimSpace(k) != k {
		return Invalid("Idempotency-Key")
	}
	return nil
}
func match(q *Request, version int) error {
	v := q.R.Header.Get("If-Match")
	if v == "" {
		return Fail(422, "INVALID_INPUT", "If-Match가 필요합니다.")
	}
	if strings.Trim(v, "\"") != strconv.Itoa(version) {
		return Fail(409, "version_conflict", "다른 변경이 적용되었습니다. 새로 조회해 주세요.")
	}
	return nil
}
func (s *Server) resource(q *Request, kind, id string, write bool) (Object, error) {
	return s.DB.Get(q.R.Context(), kind, id)
}
