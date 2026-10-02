package controller

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
	"math"
	"net/http"
	"strconv"
	"strings"
	"time"
)

type Controller struct {
	DB       *pgxpool.Pool
	Config   Config
	Revision string
}

func New(db *pgxpool.Pool, c Config) (*Controller, error) {
	if e := c.Validate(); e != nil {
		return nil, e
	}
	return &Controller{db, c, Hash(c)}, nil
}
func (c *Controller) Prepare(ctx context.Context, apply bool) error {
	tx, e := c.DB.Begin(ctx)
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	if _, e = tx.Exec(ctx, "SELECT pg_advisory_xact_lock(72931021)"); e != nil {
		return e
	}
	// Existing installations take the capacity lock before schema/job locks too.
	var capacityTable *string
	if e = tx.QueryRow(ctx, "SELECT to_regclass('capacity_state')::text").Scan(&capacityTable); e != nil {
		return e
	}
	if capacityTable != nil {
		if _, e = tx.Exec(ctx, "SELECT pool_id FROM capacity_state WHERE pool_id='default' FOR UPDATE"); e != nil {
			return e
		}
	}
	for _, sql := range []string{migrations.Baseline, migrations.Upgrade, migrations.Queue, migrations.WorkerContracts, migrations.RunbookContract} {
		if _, e = tx.Exec(ctx, sql); e != nil {
			return e
		}
	}
	_, e = tx.Exec(ctx, "INSERT INTO capacity_state(pool_id,config_revision,kind_limits,shared_limit,config_snapshot) VALUES('default',$1,$2,$3,$4) ON CONFLICT DO NOTHING", c.Revision, c.Config.KindLimits, c.Config.SharedLimit, c.Config)
	if e != nil {
		return e
	}
	if apply {
		_, e = tx.Exec(ctx, "UPDATE capacity_state SET config_revision=$1,kind_limits=$2,shared_limit=$3,config_snapshot=$4 WHERE pool_id='default'", c.Revision, c.Config.KindLimits, c.Config.SharedLimit, c.Config)
		if e != nil {
			return e
		}
	}
	var rev string
	if e = tx.QueryRow(ctx, "SELECT config_revision FROM capacity_state WHERE pool_id='default'").Scan(&rev); e != nil {
		return e
	}
	if rev != c.Revision {
		return Fail(503, "configuration_mismatch", "운영 설정 revision이 일치하지 않습니다.")
	}
	return tx.Commit(ctx)
}
func (c *Controller) transaction(ctx context.Context, fn func(pgx.Tx, time.Time) error) error {
	tx, e := c.DB.Begin(ctx)
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	var rev string
	if e = tx.QueryRow(ctx, "SELECT config_revision FROM capacity_state WHERE pool_id='default' FOR UPDATE").Scan(&rev); e != nil {
		return e
	}
	if rev != c.Revision {
		return Fail(503, "configuration_mismatch", "운영 설정 revision이 일치하지 않습니다.")
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
func one(ctx context.Context, q interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}, sql string, args ...any) (Object, error) {
	var out Object
	e := q.QueryRow(ctx, sql, args...).Scan(&out)
	if errors.Is(e, pgx.ErrNoRows) {
		return nil, Fail(404, "not_found", "기록이 없습니다.")
	}
	return out, e
}
func instant(v Object, k string) time.Time {
	t, _ := time.Parse(time.RFC3339Nano, String(v, k))
	return t
}
func only(b Object, keys ...string) error {
	for k := range b {
		if !Has(keys, k) {
			return Invalid(k)
		}
	}
	return nil
}
func integer(v Object, k string) bool {
	switch n := v[k].(type) {
	case float64:
		return n >= 1 && n <= 2147483647 && math.Trunc(n) == n
	case int:
		return n >= 1 && n <= 2147483647
	default:
		return false
	}
}
func missing(e error) bool { var p *Problem; return errors.As(e, &p) && p.Status == 404 }
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
func (c *Controller) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	id := ID()
	w.Header().Set("X-Request-ID", id)
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()
	r = r.WithContext(ctx)
	var out Object
	status := 200
	var e error
	defer func() {
		if recover() != nil {
			write(w, id, 500, Object{"error": Fail(500, "internal_error", "처리 오류입니다.")})
		}
	}()
	if !strings.HasPrefix(r.URL.Path, "/internal/v1/") {
		e = Fail(404, "not_found", "경로가 없습니다.")
	} else {
		path := strings.TrimPrefix(r.URL.Path, "/internal/v1")
		body := Object{}
		if r.Method == "POST" {
			if !strings.HasPrefix(r.Header.Get("Content-Type"), "application/json") {
				e = Invalid("Content-Type")
			} else {
				dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1024*1024))
				if err := dec.Decode(&body); err != nil || body == nil {
					e = Invalid("body")
				} else {
					var extra any
					if dec.Decode(&extra) != io.EOF {
						e = Invalid("body")
					}
				}
			}
		}
		if e == nil {
			out, status, e = c.route(r, path, body)
		}
	}
	if e != nil {
		var p *Problem
		if !errors.As(e, &p) {
			slog.Error("JC dependency failure", "request_id", id, "error", e)
			p = Fail(503, "dependency_unavailable", "저장소 또는 실행 설정이 준비되지 않았습니다.")
		}
		write(w, id, p.Status, Object{"error": p})
		return
	}
	write(w, id, status, out)
}
func write(w http.ResponseWriter, id string, status int, v Object) {
	if status == 204 {
		w.WriteHeader(status)
		return
	}
	if v == nil {
		v = Object{}
	}
	v["request_id"] = id
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	if n := Number(v, "version"); n > 0 {
		w.Header().Set("ETag", strconv.Quote(strconv.Itoa(n)))
	}
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
func (c *Controller) route(r *http.Request, path string, b Object) (Object, int, error) {
	ctx := r.Context()
	parts := strings.Split(strings.Trim(path, "/"), "/")
	if r.Method == "GET" && (path == "/health/live" || path == "/health/ready") {
		if path == "/health/ready" {
			var ready bool
			e := c.DB.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM jc_migrations WHERE version=2) AND EXISTS(SELECT 1 FROM capacity_state WHERE config_revision=$1)", c.Revision).Scan(&ready)
			if e != nil {
				return nil, 0, e
			}
			if !ready {
				return nil, 0, Fail(503, "configuration_mismatch", "큐 설정이 준비되지 않았습니다.")
			}
		}
		return Object{"status": "ok", "contract_version": "1.3", "config_revision": c.Revision}, 200, nil
	}
	if r.Method == "GET" && len(parts) >= 3 && parts[0] == "receipts" {
		if !Has([]string{"backend", "incident"}, parts[1]) {
			return nil, 0, Invalid("source_module")
		}
		v, e := one(ctx, c.DB, "SELECT jsonb_build_object('job_id',id,'kind',kind,'status',status,'version',version) FROM jobs WHERE source_module=$1 AND source_key=$2", parts[1], strings.Join(parts[2:], "/"))
		return v, 200, e
	}
	if e := c.Sweep(ctx); e != nil {
		return nil, 0, e
	}
	if r.Method == "GET" && path == "/queue-status" {
		v, e := c.queueStatus(ctx)
		return v, 200, e
	}
	if r.Method == "GET" && parts[0] == "jobs" {
		return c.readJobs(r, parts)
	}
	if r.Method == "POST" {
		if path == "/jobs/report" || path == "/jobs/rca" {
			v, e := c.submit(ctx, parts[1], b)
			return v, 202, e
		}
		if path == "/workers/register" {
			v, e := c.register(ctx, b)
			return v, 200, e
		}
		if path == "/claims" {
			v, e := c.claim(ctx, b)
			status := 200
			if v == nil && e == nil {
				status = 204
			}
			return v, status, e
		}
		if len(parts) == 3 && parts[0] == "jobs" && uuid(parts[1]) {
			if Has([]string{"cancel", "retry"}, parts[2]) {
				v, e := c.command(ctx, parts[1], parts[2], b, r.Header)
				return v, 200, e
			}
			if Has([]string{"heartbeat", "complete", "fail"}, parts[2]) {
				v, e := c.attempt(ctx, parts[1], parts[2], b)
				return v, 200, e
			}
		}
	}
	return nil, 0, Fail(404, "not_found", "제공하지 않는 API입니다.")
}
func publicJob(v Object) Object {
	o := Object{}
	for _, k := range []string{"id", "kind", "status", "stage", "attempt_no", "created_at", "started_at", "deadline_at", "queue_reason", "cancel_requested_at", "termination_reason", "version", "published_result_id", "retryable", "max_attempts", "budget_used", "token_budget"} {
		o[k] = v[k]
	}
	o["job_id"] = v["id"]
	return o
}
func execution(job Object) Execution {
	versions, _ := job["versions"].(map[string]any)
	e, _ := Decode[Execution](versions["execution"])
	return e
}
func (c *Controller) Run(ctx context.Context) {
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if e := c.Sweep(ctx); e != nil && ctx.Err() == nil {
				slog.Error("queue recovery", "error", e)
			}
		}
	}
}
