package service

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	. "gpu-ops-advisor/shared/contract"
	"gpu-ops-advisor/shared/migrations"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

type Server struct {
	DB     *pgxpool.Pool
	Config Config
	Client *http.Client
}

func New(db *pgxpool.Pool, c Config) (*Server, error) {
	if e := c.Validate(); e != nil {
		return nil, e
	}
	return &Server{DB: db, Config: c, Client: &http.Client{Timeout: 8 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}}, nil
}
func (s *Server) Prepare(ctx context.Context, apply ...bool) error {
	tx, e := s.DB.Begin(ctx)
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	if _, e = tx.Exec(ctx, "SELECT pg_advisory_xact_lock(72931021)"); e != nil {
		return e
	}
	if _, e = tx.Exec(ctx, "SELECT pg_advisory_xact_lock(72931022)"); e != nil {
		return e
	}
	for _, sql := range []string{migrations.Baseline, migrations.Upgrade, migrations.Incident} {
		if _, e = tx.Exec(ctx, sql); e != nil {
			return e
		}
	}
	_, e = tx.Exec(ctx, "INSERT INTO incident_sources(source,config_revision,snapshot) VALUES($1,$2,$3) ON CONFLICT DO NOTHING", s.Config.Source, Hash(s.Config), s.Config)
	if e != nil {
		return e
	}
	if len(apply) > 0 && apply[0] {
		if _, e = tx.Exec(ctx, "UPDATE incident_sources SET config_revision=$2,snapshot=$3 WHERE source=$1", s.Config.Source, Hash(s.Config), s.Config); e != nil {
			return e
		}
	}
	if e = s.configuration(ctx, tx); e != nil {
		return e
	}
	for _, p := range s.Config.Policies {
		hash := Hash(p)
		if _, e = tx.Exec(ctx, "INSERT INTO incident_analysis_profiles(revision,content_hash,snapshot) VALUES($1,$2,$3) ON CONFLICT DO NOTHING", p.Revision, hash, p); e != nil {
			return e
		}
		var old string
		if e = tx.QueryRow(ctx, "SELECT content_hash FROM incident_analysis_profiles WHERE revision=$1", p.Revision).Scan(&old); e != nil {
			return e
		}
		if old != hash {
			return errors.New("analysis policy revision is immutable; use a new revision")
		}
	}
	return tx.Commit(ctx)
}
func (s *Server) transaction(ctx context.Context, fn func(pgx.Tx, time.Time) error) error {
	tx, e := s.DB.Begin(ctx)
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	if _, e = tx.Exec(ctx, "SELECT pg_advisory_xact_lock(72931022)"); e != nil {
		return e
	}
	if e = s.configuration(ctx, tx); e != nil {
		return e
	}
	var now time.Time
	if e = tx.QueryRow(ctx, "SELECT clock_timestamp()").Scan(&now); e != nil {
		return e
	}
	if e = fn(tx, now); e != nil {
		return e
	}
	return tx.Commit(ctx)
}
func (s *Server) configuration(ctx context.Context, q interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}) error {
	var rev string
	if e := q.QueryRow(ctx, "SELECT config_revision FROM incident_sources WHERE source=$1 FOR SHARE", s.Config.Source).Scan(&rev); e != nil {
		return e
	}
	if rev != Hash(s.Config) {
		return Fail(503, "configuration_mismatch", "Incident 운영 설정 revision이 다릅니다.")
	}
	return nil
}
func one(ctx context.Context, q interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}, sql string, args ...any) (Object, error) {
	var o Object
	e := q.QueryRow(ctx, sql, args...).Scan(&o)
	if errors.Is(e, pgx.ErrNoRows) {
		return nil, Fail(404, "not_found", "기록이 없습니다.")
	}
	return o, e
}
func missing(e error) bool { var p *Problem; return errors.As(e, &p) && p.Status == 404 }
func only(b Object, keys ...string) error {
	for k := range b {
		if !Has(keys, k) {
			return Invalid(k)
		}
	}
	return nil
}
func uuid(v string) bool {
	if len(v) != 36 {
		return false
	}
	for i, r := range v {
		if i == 8 || i == 13 || i == 18 || i == 23 {
			if r != '-' {
				return false
			}
		} else if !strings.ContainsRune("0123456789abcdefABCDEF", r) {
			return false
		}
	}
	return true
}
func instant(o Object, k string) time.Time {
	t, _ := time.Parse(time.RFC3339Nano, String(o, k))
	return t
}
func write(w http.ResponseWriter, id string, status int, o Object) {
	if o == nil {
		o = Object{}
	}
	o["request_id"] = id
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	if v := Number(o, "version"); v > 0 {
		w.Header().Set("ETag", strconv.Quote(strconv.Itoa(v)))
	}
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(o)
}
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	id := ID()
	w.Header().Set("X-Request-ID", id)
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	ctx, cancel := context.WithTimeout(r.Context(), 20*time.Second)
	defer cancel()
	r = r.WithContext(ctx)
	out, status, e := s.route(w, r)
	if e != nil {
		var p *Problem
		if !errors.As(e, &p) {
			slog.Error("incident request", "request_id", id, "error", e)
			p = Fail(503, "dependency_unavailable", "저장소 또는 전달 설정을 확인해 주세요.")
		}
		out, status = Object{"error": p}, p.Status
	}
	write(w, id, status, out)
}
func (s *Server) route(w http.ResponseWriter, r *http.Request) (Object, int, error) {
	path := r.URL.Path
	ctx := r.Context()
	if r.Method == "GET" && (path == "/internal/v1/health/live" || path == "/internal/v1/health/ready") {
		out := Object{"status": "ok", "contract_version": "1.3"}
		if strings.HasSuffix(path, "ready") {
			if e := s.configuration(ctx, s.DB); e != nil {
				return nil, 0, e
			}
			var ready bool
			if e := s.DB.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM incident_migrations WHERE version=1)").Scan(&ready); e != nil {
				return nil, 0, e
			}
			if !ready {
				return nil, 0, Fail(503, "schema_not_ready", "스키마가 준비되지 않았습니다.")
			}
			var pending int
			if e := s.DB.QueryRow(ctx, "SELECT count(*) FROM enqueue_outbox WHERE source_module='incident' AND status='pending'").Scan(&pending); e != nil {
				return nil, 0, e
			}
			out["pending_outbox"] = pending
			out["delivery_configured"] = true
		}
		return out, 200, nil
	}
	if r.Method == "GET" && strings.HasPrefix(path, "/internal/v1/incidents") {
		out, e := s.read(r)
		return out, 200, e
	}
	if r.Method != "POST" && r.Method != "PATCH" {
		return nil, 0, Fail(404, "not_found", "제공하지 않는 API입니다.")
	}
	if path != "/webhooks/grafana" && !(r.Method == "PATCH" && strings.HasPrefix(path, "/internal/v1/incidents/")) {
		return nil, 0, Fail(404, "not_found", "제공하지 않는 API입니다.")
	}
	if !strings.HasPrefix(r.Header.Get("Content-Type"), "application/json") {
		return nil, 0, Fail(415, "unsupported_media_type", "JSON 본문이 필요합니다.")
	}
	body, e := io.ReadAll(http.MaxBytesReader(w, r.Body, int64(s.Config.MaxBodyBytes)))
	if e != nil {
		var large *http.MaxBytesError
		if errors.As(e, &large) {
			return nil, 0, Fail(413, "body_too_large", "본문 한도를 초과했습니다.")
		}
		return nil, 0, Fail(400, "invalid_body", "본문을 읽을 수 없습니다.")
	}
	var b Object
	if !utf8.Valid(body) || json.Unmarshal(body, &b) != nil || b == nil {
		return nil, 0, Fail(400, "invalid_json", "JSON 객체가 필요합니다.")
	}
	if path == "/webhooks/grafana" && r.Method == "POST" {
		return s.ingest(ctx, b, body)
	}
	if r.Method == "PATCH" {
		id := strings.TrimPrefix(path, "/internal/v1/incidents/")
		if !uuid(id) {
			return nil, 0, Invalid("incident_id")
		}
		out, e := s.patch(ctx, id, b, r.Header)
		return out, 200, e
	}
	return nil, 0, Fail(404, "not_found", "제공하지 않는 API입니다.")
}
